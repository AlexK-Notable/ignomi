"""
Backdrop Panel - Full-screen blurred overlay behind launcher panels.

Creates a transparent full-screen layer surface that Hyprland applies
heavy blur to via layerrule. This blurs the entire screen, not just
the area behind individual panels.

HDR monitors need different blur settings (brightness/contrast) since
HDR changes the luminance curve. When the backdrop opens, we detect
the monitor and apply overrides via hyprctl keyword, restoring defaults
on close.
"""

import os
import sys

from gi.repository import Gdk
from ignis import widgets
from ignis.services.hyprland import HyprlandService
from loguru import logger

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.helpers import get_monitor_under_cursor, update_window_monitor

# Default blur settings (must match decorations.conf)
_BLUR_DEFAULTS = {
    "brightness": 1.2,
    "contrast": 0.98,
    "vibrancy": 0.16,
}

# Per-monitor blur overrides (connector name → settings)
# DP-1 is HDR — needs adjusted brightness/contrast to compensate
_MONITOR_BLUR_OVERRIDES = {
    "DP-1": {
        "brightness": 2.5,
        "contrast": 1.0,
        "vibrancy": 0.30,
    },
}

_blur_modified = False


def create_backdrop_window():
    """
    Create a full-screen transparent backdrop for blur.

    Anchored to all 4 edges so it covers the entire monitor.
    A layerrule in windowrules.conf applies blur to this namespace.

    Returns:
        widgets.Window covering the full monitor
    """
    # Child box must expand to fill the window for GTK to render pixels
    fill = widgets.Box(
        hexpand=True,
        vexpand=True,
        css_classes=["ignomi-backdrop-fill"],
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
        child=fill,
    )

    window.connect("notify::visible", _on_visibility_changed)

    return window


def _get_connector_for_monitor(monitor_idx: int) -> str:
    """Get the Wayland connector name for a GTK monitor index."""
    display = Gdk.Display.get_default()
    if display:
        monitors = display.get_monitors()
        if monitor_idx < monitors.get_n_items():
            return monitors.get_item(monitor_idx).get_connector()
    return ""


def _apply_blur_overrides(connector: str):
    """Apply monitor-specific blur settings via hyprctl."""
    global _blur_modified
    overrides = _MONITOR_BLUR_OVERRIDES.get(connector)
    if not overrides:
        return

    try:
        hyprland = HyprlandService.get_default()
        for key, value in overrides.items():
            hyprland.send_command(f"keyword decoration:blur:{key} {value}")
        _blur_modified = True
        logger.debug(f"Applied HDR blur overrides for {connector}: {overrides}")
    except Exception:
        logger.debug(f"Failed to apply blur overrides for {connector}")


def _restore_blur_defaults():
    """Restore default blur settings via hyprctl."""
    global _blur_modified
    if not _blur_modified:
        return

    try:
        hyprland = HyprlandService.get_default()
        for key, value in _BLUR_DEFAULTS.items():
            hyprland.send_command(f"keyword decoration:blur:{key} {value}")
        _blur_modified = False
        logger.debug("Restored default blur settings")
    except Exception:
        logger.debug("Failed to restore blur defaults")


def _on_visibility_changed(window, param):
    """Update monitor and apply blur overrides when backdrop opens/closes."""
    if window.get_visible():
        update_window_monitor(window)
        connector = _get_connector_for_monitor(window.monitor)
        _apply_blur_overrides(connector)
    else:
        _restore_blur_defaults()
