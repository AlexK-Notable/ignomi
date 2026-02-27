"""
Backdrop Panel - Full-screen blurred screenshot behind launcher panels.

Captures the current monitor via grim, applies animated Gaussian blur
with PIL, and displays the result as a full-screen layer surface.

Animation: on open, blur ramps from sharp → full blur synced with panel
slide-in. On close, blur reverses from full → sharp before fading out.

Frames are streamed from the background thread as they're generated,
so the sharp screenshot appears immediately and blur builds progressively.

Per-monitor settings allow different blur radius and brightness for
HDR vs SDR monitors.
"""

import io
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from gi.repository import Gdk, GdkPixbuf, GLib
from ignis import widgets
from loguru import logger
from PIL import Image, ImageEnhance, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.helpers import get_monitor_under_cursor

# Default blur settings
_BLUR_DEFAULTS = {
    "radius": 20,
    "brightness": 1.0,
}

# Per-monitor overrides (connector name → settings)
_MONITOR_SETTINGS = {
    "DP-1": {
        "radius": 20,
        "brightness": 1.3,
    },
}

# Animation timing — tuned to match Hyprland panel slide animations
_BLUR_STEPS = 7            # Number of blur frames (including sharp)
_OPEN_DURATION_MS = 150    # Total open blur animation time
_CLOSE_DURATION_MS = 150   # Total close blur animation time


def _ease_in_intervals(total_ms: int, steps: int) -> list[int]:
    """Compute per-frame intervals with ease-in timing (slow start, fast finish).

    Uses quadratic ease-in: t^2. Early frames get longer intervals,
    later frames get shorter — blur accelerates as it progresses.
    """
    if steps <= 1:
        return [total_ms]

    # Quadratic ease-in: normalized positions 0..1, squared
    raw = [i / (steps - 1) for i in range(steps)]
    # Intervals are the differences between consecutive positions
    deltas = [raw[i + 1] - raw[i] for i in range(steps - 1)]
    total_delta = sum(deltas)
    # Scale to actual milliseconds, ensure minimum 10ms per frame
    intervals = [max(10, int(d / total_delta * total_ms)) for d in deltas]
    return intervals


def _get_connector_for_monitor(monitor_idx: int) -> str:
    """Get the Wayland connector name for a GTK monitor index."""
    display = Gdk.Display.get_default()
    if display:
        monitors = display.get_monitors()
        if monitor_idx < monitors.get_n_items():
            return monitors.get_item(monitor_idx).get_connector()
    return ""


def _capture_and_prepare(connector: str):
    """Capture screenshot and prepare base image.

    Returns (img, max_radius) or (None, None) on failure.
    """
    settings = _MONITOR_SETTINGS.get(connector, _BLUR_DEFAULTS)
    max_radius = settings.get("radius", _BLUR_DEFAULTS["radius"])
    brightness = settings.get("brightness", _BLUR_DEFAULTS["brightness"])

    try:
        result = subprocess.run(
            ["grim", "-o", connector, "-t", "ppm", "-"],
            capture_output=True,
            timeout=2,
        )
        if result.returncode != 0:
            logger.warning(f"grim failed for {connector}: {result.stderr.decode()}")
            return None, None

        img = Image.open(io.BytesIO(result.stdout))

        if brightness != 1.0:
            img = ImageEnhance.Brightness(img).enhance(brightness)

        return img, max_radius

    except subprocess.TimeoutExpired:
        logger.warning(f"grim timed out for {connector}")
        return None, None
    except Exception as e:
        logger.warning(f"Backdrop capture failed for {connector}: {e}")
        return None, None


def _rgb_to_texture(rgb_bytes: bytes, width: int, height: int) -> Gdk.Texture:
    """Convert raw RGB bytes to a Gdk.Texture."""
    pixbuf = GdkPixbuf.Pixbuf.new_from_data(
        rgb_bytes,
        GdkPixbuf.Colorspace.RGB,
        False,
        8,
        width,
        height,
        width * 3,
    )
    return Gdk.Texture.new_for_pixbuf(pixbuf)


def create_backdrop_window():
    """Create a full-screen backdrop with animated blur.

    On open: captures monitor, streams frames sharp → blurred.
    On close: animates blurred → sharp from cached frames, then hides.
    """
    picture = widgets.Picture(
        content_fit="cover",
        hexpand=True,
        vexpand=True,
    )

    window = widgets.Window(
        namespace="ignomi-backdrop",
        css_classes=["ignomi-window", "ignomi-backdrop"],
        monitor=get_monitor_under_cursor(),
        anchor=["top", "bottom", "left", "right"],
        exclusivity="ignore",
        kb_mode="none",
        layer="top",
        visible=False,
        child=picture,
    )

    window._backdrop_picture = picture
    window._blur_frames = None   # List of (rgb_bytes, w, h) from sharp → blurred
    window._anim_gen = 0         # Generation counter to cancel stale animations
    window._closing = False      # True during close animation

    # Export close animation for helpers.py to call
    window._start_close_animation = lambda on_done: _start_close_animation(window, on_done)

    window.connect("notify::visible", _on_visibility_changed)

    return window


def _on_visibility_changed(window, param):
    """Handle visibility changes — start open animation or clean up."""
    if window.get_visible():
        window._closing = False
        window._anim_gen += 1
        gen = window._anim_gen

        connector = _get_connector_for_monitor(window.monitor)
        logger.debug(f"Backdrop opening: monitor_idx={window.monitor}, connector='{connector}'")

        def do_capture_and_stream():
            img, max_radius = _capture_and_prepare(connector)
            if img is None:
                logger.warning(f"Backdrop capture failed: connector='{connector}'")
                return

            width, height = img.size
            intervals = _ease_in_intervals(_OPEN_DURATION_MS, _BLUR_STEPS)

            # Pre-load image data — PIL Image is NOT thread-safe, so
            # img.tobytes() / img.filter() from multiple threads races.
            # Load pixels once, then give each thread its own Image copy.
            img.load()
            base_bytes = img.tobytes()

            def blur_frame(i):
                radius = int(max_radius * i / (_BLUR_STEPS - 1))
                if radius == 0:
                    return i, (base_bytes, width, height)
                # Each thread gets its own Image from the shared bytes
                frame_img = Image.frombytes("RGB", (width, height), base_bytes)
                blurred = frame_img.filter(ImageFilter.GaussianBlur(radius=radius))
                return i, (blurred.tobytes(), width, height)

            # Generate all blur frames concurrently — ~60ms instead of ~400ms
            with ThreadPoolExecutor(max_workers=_BLUR_STEPS) as pool:
                results = list(pool.map(blur_frame, range(_BLUR_STEPS)))

            # Stream frames to main thread in order
            for i, frame in results:
                delay = intervals[i] if i < len(intervals) else 0
                GLib.idle_add(_show_streamed_frame, window, frame, i, gen, delay)

        threading.Thread(target=do_capture_and_stream, daemon=True).start()
    else:
        # Window hidden (after close animation or external close)
        window._anim_gen += 1
        window._backdrop_picture.set_paintable(None)
        window._blur_frames = None
        window._closing = False


def _show_streamed_frame(window, frame, idx, gen, delay_ms):
    """Display a frame streamed from the background thread.

    Frame 0 shows immediately. Subsequent frames are delayed by their
    eased interval, but only relative to when they arrive from the
    background thread — no artificial wait for all frames to generate.
    """
    if window._anim_gen != gen or not window.get_visible():
        return False

    # Store frame for close animation
    if window._blur_frames is None:
        window._blur_frames = []
    window._blur_frames.append(frame)

    if idx == 0:
        # First frame (sharp) — show immediately
        _display_frame(window, frame)
    else:
        # Subsequent frames — show with eased delay
        GLib.timeout_add(delay_ms, _display_frame_cb, window, frame, gen)

    return False


def _display_frame(window, frame):
    """Set a frame as the backdrop image."""
    rgb_bytes, w, h = frame
    try:
        texture = _rgb_to_texture(rgb_bytes, w, h)
        window._backdrop_picture.set_paintable(texture)
        logger.debug(f"Backdrop: displayed frame {w}x{h} on monitor_idx={window.monitor}")
    except Exception as e:
        logger.warning(f"Failed to set backdrop frame: {e}")


def _display_frame_cb(window, frame, gen):
    """GLib.timeout_add callback to display a frame (checks generation)."""
    if window._anim_gen != gen:
        return False
    _display_frame(window, frame)
    return False


def _start_close_animation(window, on_done):
    """Start the reverse blur animation, call on_done when finished.

    Called by close_launcher() instead of immediately hiding the window.
    Uses cached frames from the open animation played in reverse.
    """
    if window._closing:
        return

    window._closing = True
    window._anim_gen += 1
    gen = window._anim_gen

    if window._blur_frames and len(window._blur_frames) > 1:
        reversed_frames = list(reversed(window._blur_frames))
        # Reverse the easing — close starts fast, slows at end
        intervals = list(reversed(_ease_in_intervals(_CLOSE_DURATION_MS, len(reversed_frames))))
        _play_frame(window, reversed_frames, 0, gen, intervals, on_done)
    else:
        if on_done:
            on_done()


def _play_frame(window, frames, idx, gen, intervals, on_done):
    """Display a single animation frame, schedule the next one.

    Used for close animation (open uses streaming instead).
    """
    if window._anim_gen != gen:
        return False

    _display_frame(window, frames[idx])

    if idx + 1 < len(frames):
        delay = intervals[idx] if idx < len(intervals) else intervals[-1]
        GLib.timeout_add(delay, _play_frame, window, frames,
                         idx + 1, gen, intervals, on_done)
    elif on_done:
        delay = intervals[-1] if intervals else 30
        GLib.timeout_add(delay, _fire_callback, on_done)

    return False


def _fire_callback(callback):
    """Wrapper for GLib.timeout_add callbacks."""
    callback()
    return False
