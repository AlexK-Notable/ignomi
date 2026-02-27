"""
Helper utilities for the Ignomi launcher.

Provides common functions used across multiple panels:
- App launching with frecency tracking
- Launcher window management
- Settings loading
- Monitor detection via HyprlandService IPC
- Shared UI operations (container clearing, bookmark management)
"""

import json
from pathlib import Path
from typing import Any

import toml
from gi.repository import Gdk, GLib
from ignis.services.applications import ApplicationsService
from ignis.services.hyprland import HyprlandService
from loguru import logger


def _hyprland_name_to_ignis_index(connector_name: str) -> int:
    """
    Convert a Hyprland monitor connector name to a GTK/Ignis monitor index.

    Args:
        connector_name: Monitor connector name (e.g., "DP-1", "HDMI-A-1")

    Returns:
        Corresponding GTK monitor index, or 0 if not found
    """
    display = Gdk.Display.get_default()
    if not display:
        return 0

    monitors = display.get_monitors()
    for i in range(monitors.get_n_items()):
        monitor = monitors.get_item(i)
        if monitor.get_connector() == connector_name:
            return i

    return 0


def hyprland_monitor_to_ignis_monitor(hyprland_id: int) -> int:
    """
    Convert Hyprland monitor ID to Ignis/GTK monitor ID.

    Uses HyprlandService IPC instead of subprocess calls.

    Args:
        hyprland_id: Monitor ID from Hyprland

    Returns:
        Corresponding Ignis/GTK monitor ID, or 0 if not found
    """
    try:
        hyprland = HyprlandService.get_default()
        for monitor in hyprland.monitors:
            if monitor.id == hyprland_id:
                return _hyprland_name_to_ignis_index(monitor.name)
        return 0
    except Exception:
        logger.debug(f"Failed to convert Hyprland monitor {hyprland_id}")
        return 0


def get_monitor_under_cursor() -> int:
    """
    Get the ID of the monitor where the cursor is currently located.

    Uses HyprlandService IPC for monitor data and cursor position.

    Returns:
        Monitor ID (int), defaults to 0 if detection fails
    """
    try:
        hyprland = HyprlandService.get_default()

        # Get cursor position via IPC (format: "x, y")
        cursor_raw = hyprland.send_command("cursorpos").strip()
        cursor_pos = cursor_raw.split(', ')
        if len(cursor_pos) != 2:
            return 0
        cursor_x = int(cursor_pos[0])
        cursor_y = int(cursor_pos[1])

        # Find which monitor contains the cursor using cached monitor data
        for monitor in hyprland.monitors:
            if (monitor.x <= cursor_x < monitor.x + monitor.width
                    and monitor.y <= cursor_y < monitor.y + monitor.height):
                return _hyprland_name_to_ignis_index(monitor.name)

    except Exception:
        logger.debug("Failed to detect monitor under cursor, defaulting to 0")

    return 0


# -- Shared UI utilities --

def clear_container(container) -> None:
    """
    Remove all children from a GTK4 container widget.

    Args:
        container: Any GTK4 widget that supports get_first_child/remove
    """
    child = container.get_first_child()
    while child:
        next_child = child.get_next_sibling()
        container.remove(child)
        child = next_child


def find_app_by_id(app_id: str):
    """
    Find an Application object by its desktop file ID.

    Args:
        app_id: Desktop file ID (e.g., "firefox.desktop")

    Returns:
        Application object, or None if not found
    """
    apps_service = ApplicationsService.get_default()
    for app in apps_service.apps:
        if app.id == app_id:
            return app
    return None


def add_bookmark_with_refresh(app_id: str, button=None) -> None:
    """
    Add an app to bookmarks with visual feedback and cross-panel refresh.

    Args:
        app_id: Desktop file ID to bookmark
        button: Optional button widget for CSS pulse feedback
    """
    if is_bookmarked(app_id):
        return

    add_bookmark(app_id)

    # Visual feedback on the triggering button
    if button:
        button.add_css_class("bookmark-added")
        GLib.timeout_add(300, lambda: button.remove_css_class("bookmark-added"))

    # Refresh bookmarks panel
    from ignis.app import IgnisApp
    app_instance = IgnisApp.get_default()
    bookmarks_window = app_instance.get_window("ignomi-bookmarks")
    if bookmarks_window and hasattr(bookmarks_window, 'panel'):
        bookmarks_window.panel.refresh_from_disk()


def update_window_monitor(window) -> None:
    """
    Update a window's monitor to match the cursor's current position.

    Call this in visibility-changed handlers to ensure panels
    appear on the correct monitor.

    Args:
        window: An Ignis Window widget
    """
    cursor_monitor = get_monitor_under_cursor()
    if window.monitor != cursor_monitor:
        window.monitor = cursor_monitor


def toggle_launcher():
    """
    Toggle all Ignomi launcher panels with correct multi-monitor placement.

    Must run inside the Ignis process (via ``ignis run-python`` or direct call).

    wlr-layer-shell fixes the output (monitor) at surface creation time.
    Setting ``window.monitor`` only takes effect on the NEXT show, so we must:
    1. Detect cursor monitor while windows are still hidden
    2. Set ``.monitor`` on every window
    3. Then toggle visibility

    This replaces per-panel ``update_window_monitor()`` calls in visibility
    handlers, which fire too late (after the surface is already created).
    """
    from ignis.app import IgnisApp

    app = IgnisApp.get_default()
    target_monitor = get_monitor_under_cursor()

    # Collect all ignomi windows
    ignomi_windows = [
        w for w in app.get_windows()
        if w.namespace and w.namespace.startswith("ignomi-")
    ]

    if not ignomi_windows:
        return

    # Determine current state from any panel (they toggle together)
    currently_visible = any(w.get_visible() for w in ignomi_windows)

    if currently_visible:
        # Closing — use close_launcher() for proper animation sequencing
        close_launcher()
    else:
        # Opening — set monitors BEFORE showing (Layer Shell requirement)
        for w in ignomi_windows:
            w.monitor = target_monitor

        for w in ignomi_windows:
            w.set_visible(True)


def launch_app(app, frecency_service, close_delay_ms: int = 300):
    """
    Launch an application, record in frecency, and auto-close launcher.

    Args:
        app: Application object from ApplicationsService
        frecency_service: FrecencyService instance for tracking
        close_delay_ms: Delay in milliseconds before closing launcher
    """
    # Launch the application
    app.launch()
    logger.debug(f"Launched {app.id}")

    # Record in frecency for usage tracking
    frecency_service.record_launch(app.id)

    # Schedule auto-close after delay
    GLib.timeout_add(close_delay_ms, lambda: _close_launcher_callback())


def _close_launcher_callback() -> bool:
    """
    Callback for GLib.timeout_add to close launcher.

    Returns:
        False to prevent timeout from repeating
    """
    close_launcher()
    return False  # Don't repeat


def close_launcher():
    """
    Close all Ignomi launcher windows including backdrop.

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


def _close_search_panel(window):
    """Close the search panel with GTK Revealer animation.

    Traverses centering Box → Revealer. The notify::child-revealed
    signal on the Revealer hides the window when animation finishes.
    """
    # Window child is the centering Box; Revealer is its first child
    centering_box = window.get_child()
    if centering_box:
        revealer = centering_box.get_first_child()
        if revealer and hasattr(revealer, 'set_reveal_child'):
            revealer.set_reveal_child(False)
            return
    window.set_visible(False)


# -- Settings cache --
_settings_cache = None


def load_settings() -> dict[str, Any]:
    """
    Load launcher settings from TOML file (cached after first load).

    Returns:
        Dictionary containing settings with defaults applied
    """
    global _settings_cache
    if _settings_cache is not None:
        return _settings_cache

    # Default settings
    defaults = {
        "launcher": {
            "close_delay_ms": 300,
        },
        "frecency": {
            "max_items": 12,
            "min_launches": 2,
        },
        "search": {
            "max_results": 30,
            "fuzzy_threshold": 50,
        },
        "animation": {
            "transition_duration": 200,
        },
    }

    # Settings file location
    settings_path = Path(__file__).parent.parent / "data" / "settings.toml"

    # Load from file if it exists
    if settings_path.exists():
        try:
            loaded = toml.load(settings_path)
            # Merge loaded settings with defaults
            settings = _deep_merge(defaults, loaded)
            _settings_cache = settings
            return settings
        except Exception as e:
            logger.warning(f"Could not load settings from {settings_path}: {e}, using defaults")
            _settings_cache = defaults
            return defaults
    else:
        logger.info(f"Settings file not found at {settings_path}, using defaults")
        _settings_cache = defaults
        return defaults


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Deep merge two dictionaries.

    Args:
        base: Base dictionary with defaults
        override: Dictionary with overrides

    Returns:
        Merged dictionary (override takes precedence)
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value

    return result


# -- Bookmarks --
_bookmarks_cache = None


def _bookmarks_path() -> Path:
    """Resolve bookmarks file path with XDG migration."""
    import shutil

    xdg_path = Path.home() / ".local" / "share" / "ignomi" / "bookmarks.json"
    if xdg_path.exists():
        return xdg_path

    old_path = Path(__file__).parent.parent / "data" / "bookmarks.json"
    if old_path.exists():
        xdg_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(old_path), str(xdg_path))
        logger.info(f"Migrated bookmarks from {old_path} to {xdg_path}")
        return xdg_path

    return xdg_path


def load_bookmarks() -> list:
    """
    Load bookmark app IDs from JSON file (cached after first load).

    Returns:
        List of desktop file IDs (e.g., ["firefox.desktop", ...])

    If file doesn't exist or is invalid, returns empty list.
    """
    global _bookmarks_cache
    if _bookmarks_cache is not None:
        return list(_bookmarks_cache)  # Return copy to prevent mutation

    bookmarks_path_val = _bookmarks_path()

    if bookmarks_path_val.exists():
        try:
            with open(bookmarks_path_val) as f:
                data = json.load(f)
                _bookmarks_cache = data.get("bookmarks", [])
                return list(_bookmarks_cache)
        except Exception as e:
            logger.warning(f"Could not load bookmarks from {bookmarks_path_val}: {e}")
            return []
    else:
        logger.info(f"Bookmarks file not found at {bookmarks_path_val}, using empty list")
        return []


def save_bookmarks(bookmark_ids: list):
    """
    Save bookmark app IDs to JSON file (atomic write via tmp + rename).

    Args:
        bookmark_ids: List of desktop file IDs to save
    """
    import os

    global _bookmarks_cache

    path = _bookmarks_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps({"bookmarks": bookmark_ids}, indent=2))
        os.replace(str(tmp_path), str(path))
        _bookmarks_cache = list(bookmark_ids)
        logger.debug(f"Saved {len(bookmark_ids)} bookmarks")
    except Exception as e:
        logger.error(f"Could not save bookmarks to {path}: {e}")


def add_bookmark(app_id: str):
    """
    Add an app to bookmarks.

    Args:
        app_id: Desktop file ID to add

    If already bookmarked, does nothing.
    """
    bookmarks = load_bookmarks()
    if app_id not in bookmarks:
        bookmarks.append(app_id)
        save_bookmarks(bookmarks)


def remove_bookmark(app_id: str):
    """
    Remove an app from bookmarks.

    Args:
        app_id: Desktop file ID to remove

    If not bookmarked, does nothing.
    """
    bookmarks = load_bookmarks()
    if app_id in bookmarks:
        bookmarks.remove(app_id)
        save_bookmarks(bookmarks)


def is_bookmarked(app_id: str) -> bool:
    """
    Check if an app is bookmarked.

    Args:
        app_id: Desktop file ID to check

    Returns:
        True if bookmarked, False otherwise
    """
    bookmarks = load_bookmarks()
    return app_id in bookmarks
