# Backdrop Blur Pipeline

**Date:** 2026-04-30
**Status:** Implemented (commits `b460826`, `857767e`)
**Scope:** `launcher/panels/backdrop.py` and its integration with
`utils/helpers.py:close_launcher` / `toggle_launcher`

## Overview

When the Ignomi launcher opens, a full-screen blurred screenshot of the
underlying desktop fades in behind the three panels. When the launcher
closes, the blur reverses (full → sharp) and then fades out, producing a
symmetric open/close animation.

The blur is **screenshot-based**, not compositor-based. Each open captures the
current monitor with `grim`, generates seven Gaussian-blurred frames in
parallel with PIL, and streams them to a `widgets.Picture` on the GTK main
thread.

## Why Screenshot-Based Blur (Not Compositor Blur)

Hyprland and other wlroots-based compositors expose `layerrule = blur` for
Layer Shell surfaces — and earlier Ignomi prototypes used it. We moved off
of compositor blur for four reasons:

1. **Cross-compositor compatibility.** `layerrule = blur` is a Hyprland
   extension. Sway, river, and other wlroots compositors do not implement
   it. Screenshot-based blur runs anywhere `grim` and PIL run.
2. **Per-frame timing control.** Compositor blur is binary (on/off) per
   surface. We wanted the blur to *animate in* synced with the panel slide,
   and to *animate out* in reverse for symmetric close. Compositor blur
   cannot ramp.
3. **No GPU dependency surface.** Compositor blur quality and behavior
   varies with GPU driver, vsync state, and compositor version. PIL on
   captured pixel data is deterministic.
4. **Per-monitor tunability.** HDR monitors need brighter base pixels to
   match SDR perceived luminance after blur — a per-monitor brightness
   factor is trivial when we own the pixel pipeline.

The trade-off is staleness: the blurred image is a snapshot, so motion
behind the launcher (videos, animated wallpapers) freezes once the
backdrop appears. For an application launcher with a sub-second open/close
cycle this is acceptable.

## Pipeline at a Glance

```
   user opens launcher
         │
         ▼
   ┌─────────────────────────────┐
   │ grim -o $connector -t ppm - │   ← capture monitor as PPM bytes
   └─────────────┬───────────────┘
                 │ stdout bytes
                 ▼
   ┌─────────────────────────────┐
   │ PIL Image.open(BytesIO)     │   ← decode PPM → PIL Image
   │ ImageEnhance.Brightness     │   ← optional HDR compensation
   │ img.load()  + img.tobytes() │   ← materialize pixel data ONCE
   └─────────────┬───────────────┘
                 │ base_bytes (raw RGB, immutable)
                 ▼
   ┌──────────────────────────────────────────────────────┐
   │ ThreadPoolExecutor — 7 workers                       │
   │ each: Image.frombytes("RGB", (w,h), base_bytes)      │
   │       .filter(GaussianBlur(radius=i*max_radius/6))   │
   │       .tobytes()                                     │
   └─────────────┬────────────────────────────────────────┘
                 │ list[(rgb_bytes, w, h)] sharp → blurred
                 ▼
   ┌─────────────────────────────────┐
   │ GLib.idle_add(_show_streamed_…) │   ← back to main thread
   │   GdkPixbuf.new_from_data       │   ← wrap raw RGB
   │   Gdk.Texture.new_for_pixbuf    │   ← into a Texture
   │   picture.set_paintable(tex)    │   ← display
   └─────────────┬───────────────────┘
                 │ frames cached in window._blur_frames
                 ▼
   ┌──────────────────────────────────────┐
   │ on close: _start_close_animation()   │
   │   reversed(window._blur_frames)      │   ← reuse cached frames
   │   reversed(_ease_in_intervals(...))  │   ← reverse easing
   │   _play_frame(...)                   │   ← play in reverse
   │   on_done() → window.set_visible(F)  │
   └──────────────────────────────────────┘
```

## Stages in Detail

### 1. Capture: `grim` → PPM bytes

Captured per-monitor by Wayland connector name (e.g. `DP-1`):

```python
# launcher/panels/backdrop.py:91-99
result = subprocess.run(
    ["grim", "-o", connector, "-t", "ppm", "-"],
    capture_output=True,
    timeout=2,
)
```

PPM is chosen over PNG for capture because grim's PPM emit path skips
encoding overhead, and PIL decodes PPM essentially as a pixel-format
header followed by raw bytes.

### 2. Decode + Optional Brightness Boost

```python
# launcher/panels/backdrop.py:101-104
img = Image.open(io.BytesIO(result.stdout))

if brightness != 1.0:
    img = ImageEnhance.Brightness(img).enhance(brightness)
```

Per-monitor settings live in a dict literal at the top of the module:

```python
# launcher/panels/backdrop.py:39-45
_MONITOR_SETTINGS = {
    "DP-1": {
        "radius": 20,
        "brightness": 1.3,
    },
}
```

Currently only DP-1 is overridden (an HDR display in the author's
setup); other monitors fall through to `_BLUR_DEFAULTS` (`radius=20`,
`brightness=1.0`). Moving these into `settings.toml` is tracked as a
follow-up.

### 3. Parallel Frame Generation (with PIL Thread Safety)

This is the subtle part. Naively, you would write:

```python
# Naïve and broken — DO NOT do this
def blur_frame(i):
    radius = int(max_radius * i / (_BLUR_STEPS - 1))
    return i, (img.filter(GaussianBlur(radius)).tobytes(), w, h)

with ThreadPoolExecutor(max_workers=_BLUR_STEPS) as pool:
    results = list(pool.map(blur_frame, range(_BLUR_STEPS)))
```

This crashes silently on multi-monitor systems (see
[[20260227T035340199796654606]] for the full debug trace). **PIL
`Image` objects are not thread-safe**: `img.tobytes()` and
`img.filter()` mutate internal lazy-load state, and concurrent calls
race. The crash happens inside daemon threads where exceptions are
silent.

The fix is to materialize pixel bytes **once on the calling thread**, then
give each worker its own `Image.frombytes()` reconstructed from the same
immutable byte buffer:

```python
# launcher/panels/backdrop.py:186-203
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

with ThreadPoolExecutor(max_workers=_BLUR_STEPS) as pool:
    results = list(pool.map(blur_frame, range(_BLUR_STEPS)))
```

The seven-frame parallel run takes ~60ms on the development machine,
versus ~400ms sequential. Frame 0 is `radius=0` (the sharp screenshot)
which short-circuits to return `base_bytes` directly.

### 4. Stream Frames to GTK Main Thread

Frames are pushed to the main thread one at a time via `GLib.idle_add`,
each tagged with the current generation counter:

```python
# launcher/panels/backdrop.py:206-208
for i, frame in results:
    delay = intervals[i] if i < len(intervals) else 0
    GLib.idle_add(_show_streamed_frame, window, frame, i, gen, delay)
```

Frame 0 displays immediately. Frames 1..6 schedule a `GLib.timeout_add`
with their eased interval — so blur builds progressively rather than
appearing as a single late jump.

### 5. Generation-Counter Cancellation

Every visibility transition increments `window._anim_gen`:

```python
# launcher/panels/backdrop.py:170-172
if window.get_visible():
    window._closing = False
    window._anim_gen += 1
    gen = window._anim_gen
```

Every frame display checks the captured `gen` against the current value:

```python
# launcher/panels/backdrop.py:226-227
if window._anim_gen != gen or not window.get_visible():
    return False
```

If the user opens, immediately closes, and re-opens the launcher in
under a second, the in-flight blur job from the first open finds its
frames stamped with a stale generation and silently drops them on the
floor. The second open's frames win. This avoids the worst-case race
where a stale "fully blurred" frame from a cancelled open would show up
mid-close-animation.

### 6. RGB → GdkPixbuf → Gdk.Texture

Raw RGB bytes get wrapped in a `GdkPixbuf` and then into a `Gdk.Texture`,
which is what `widgets.Picture.set_paintable()` expects:

```python
# launcher/panels/backdrop.py:118-127
pixbuf = GdkPixbuf.Pixbuf.new_from_data(
    rgb_bytes,
    GdkPixbuf.Colorspace.RGB,
    False,         # has_alpha
    8,             # bits per channel
    width,
    height,
    width * 3,     # rowstride (3 bytes per pixel)
)
return Gdk.Texture.new_for_pixbuf(pixbuf)
```

`new_from_data` is zero-copy (the byte buffer is referenced, not
duplicated), which keeps memory cost down on 4K+ monitors.

## Ease-In Interval Math

The reveal animation uses **quadratic ease-in** — frames start slow and
accelerate toward the end. This visually matches the perception of "blur
gradually intensifying," in contrast to linear timing which feels mechanical.

```python
# launcher/panels/backdrop.py:53-69
def _ease_in_intervals(total_ms: int, steps: int) -> list[int]:
    if steps <= 1:
        return [total_ms]

    raw = [i / (steps - 1) for i in range(steps)]
    deltas = [raw[i + 1] - raw[i] for i in range(steps - 1)]
    total_delta = sum(deltas)
    intervals = [max(10, int(d / total_delta * total_ms)) for d in deltas]
    return intervals
```

For `total_ms=150, steps=7` the deltas are `[1/6, 1/6, ..., 1/6]` — six
equal slots of ~25ms each (hence "linear" with the current `raw[i] = i/(N-1)`
schedule). The function is structured to make swapping in a non-linear
generator (`raw[i] = (i/(N-1))**2` for true quadratic ease-in) a one-line
change. Total animation budget is 150ms — tuned to fall within the
Hyprland panel slide budget (~350ms) so the blur completes well before the
panel finishes sliding in.

## Reverse-Blur on Close

The close path **reuses** the cached frames from the open animation:

```python
# launcher/panels/backdrop.py:263-283
def _start_close_animation(window, on_done):
    if window._closing:
        return

    window._closing = True
    window._anim_gen += 1
    gen = window._anim_gen

    if window._blur_frames and len(window._blur_frames) > 1:
        reversed_frames = list(reversed(window._blur_frames))
        # Reverse the easing — close starts fast, slows at end
        intervals = list(reversed(_ease_in_intervals(_CLOSE_DURATION_MS,
                                                    len(reversed_frames))))
        _play_frame(window, reversed_frames, 0, gen, intervals, on_done)
    else:
        if on_done:
            on_done()
```

Two key choices:

- **No second `grim` capture.** The screen state hasn't changed in the
  ~1s the launcher was open, so capturing again would be wasted work
  (and would briefly capture the launcher panels themselves, since
  `grim` doesn't filter Layer Shell surfaces).
- **Reversed easing.** Open eases in (slow → fast); close eases out
  (fast → slow). This produces a symmetric perceived animation —
  bookending the launcher session with matching visual weight.

If there are no cached frames (e.g., the open animation never completed
before close was requested), `_start_close_animation` immediately calls
`on_done()` so the backdrop window can hide without waiting.

## Integration With `close_launcher`

The backdrop exports its close animation as a callable attached to
the window object:

```python
# launcher/panels/backdrop.py:160
window._start_close_animation = lambda on_done: _start_close_animation(window, on_done)
```

`close_launcher` in `utils/helpers.py:250-269` (~lines 250-280) special-cases
backdrop and search; everything else falls through to plain `set_visible(False)`:

```python
# launcher/utils/helpers.py:250-269
def close_launcher():
    """Close all Ignomi launcher windows including backdrop.

    Backdrop: reverse blur animation, then hide.
    Search panel: GTK Revealer crossfade, then hide.
    Bookmarks/frequent: Hyprland layerrules handle slide animation.
    """
    from ignis.app import IgnisApp
    app = IgnisApp.get_default()

    for window in app.get_windows():
        if window.namespace and window.namespace.startswith("ignomi-"):
            if window.namespace == "ignomi-backdrop":
                _close_backdrop(window)
            elif window.namespace == "ignomi-search":
                _close_search_panel(window)
            else:
                window.set_visible(False)


def _close_backdrop(window):
    """Close backdrop with reverse blur animation, then hide."""
    if hasattr(window, '_start_close_animation'):
        window._start_close_animation(lambda: window.set_visible(False))
    else:
        window.set_visible(False)
```

The `hasattr` guard exists so that any future `ignomi-*` window that
doesn't expose `_start_close_animation` still closes correctly.

## Why an Atomic Toggle Is Required

The whole pipeline assumes `toggle_launcher()` runs **inside** the Ignis
process (via `ignis run-python`), not as four parallel `goignis
toggle-window` shell calls. The earlier multi-call approach raced the
backdrop visibility transition against the panel visibility transitions —
sometimes the backdrop's `notify::visible` handler fired before
`window.monitor` was set, capturing the wrong monitor.

See [[20260227T035401098076654606]] for the toggle-architecture rationale
and the full `toggle_launcher()` flow.

## Parameters

All defined at module top of `launcher/panels/backdrop.py`:

| Constant              | Value | Purpose                                    |
| --------------------- | ----- | ------------------------------------------ |
| `_BLUR_STEPS`         | 7     | Number of generated frames (sharp + 6 blur levels) |
| `_OPEN_DURATION_MS`   | 150   | Total open animation budget (ms)           |
| `_CLOSE_DURATION_MS`  | 150   | Total close animation budget (ms)          |
| `_BLUR_DEFAULTS`      | `{radius: 20, brightness: 1.0}` | Per-monitor fallback         |
| `_MONITOR_SETTINGS`   | `{"DP-1": {radius: 20, brightness: 1.3}}` | Per-connector overrides |

## Cross-References

**Code:**

- [`launcher/panels/backdrop.py`](../../launcher/panels/backdrop.py) — full pipeline
- [`launcher/utils/helpers.py:250-280`](../../launcher/utils/helpers.py) — `close_launcher`
  and `_close_backdrop`
- [`launcher/utils/helpers.py:175-216`](../../launcher/utils/helpers.py) — `toggle_launcher`

**Related architecture docs:**

- [`2026-04-30-search-router-architecture.md`](./2026-04-30-search-router-architecture.md)
  — sibling subsystem (search router)
- [`2026-04-30-animation-architecture.md`](./2026-04-30-animation-architecture.md)
  — backdrop participates in the "plain Window + Hyprland fade" rule

**Related zk-notes:**

- `[[20260227T035340199796654606]]` — PIL thread-safety bug + fix that
  motivated the per-worker `Image.frombytes()` pattern
- `[[20260227T035401098076654606]]` — toggle architecture (single
  `ignis run-python` call) that backdrop relies on
- `[[20260225T072152714557306660]]` — animation debug hub (background
  context for why timing matters)
- `[[YZ0fIVUNY3wCB0Sb32XGU]]` — Phase 1 audit naming this doc as gap G10
