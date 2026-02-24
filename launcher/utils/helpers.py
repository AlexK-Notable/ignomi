"""
Helper utilities for the Ignomi launcher.

Provides common functions used across multiple panels:
- App launching with frecency tracking
- Launcher window management
- Settings loading
- Monitor detection via HyprlandService IPC
- Shared UI operations (container clearing, bookmark management)
"""

from gi.repository import GLib, Gdk
from pathlib import Path
import toml
import json
from typing import Dict, Any, Optional

from ignis.services.applications import ApplicationsService
from ignis.services.hyprland import HyprlandService


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
        pass

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


def launch_app(app, frecency_service, close_delay_ms: int = 300):
    """
    Launch an application, record in frecency, and auto-close launcher.

    Args:
        app: Application object from ApplicationsService
        frecency_service: FrecencyService instance for tracking
        close_delay_ms: Delay in milliseconds before closing launcher

    Example:
        from utils.helpers import launch_app
        launch_app(app, frecency_service, 300)
    """
    # Launch the application
    app.launch()

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
    Close all Ignomi launcher windows.

    Hides all windows with namespace starting with "ignomi-".
    This effectively closes the entire launcher.
    """
    from ignis.app import IgnisApp

    app = IgnisApp.get_default()

    # Hide all ignomi windows
    for window in app.get_windows():
        if window.namespace and window.namespace.startswith("ignomi-"):
            window.set_visible(False)


def load_settings() -> Dict[str, Any]:
    """
    Load launcher settings from TOML file.

    Returns:
        Dictionary containing settings with defaults applied

    Example settings structure:
        {
            "launcher": {
                "close_delay_ms": 300
            },
            "frecency": {
                "max_items": 12,
                "min_launches": 2
            }
        }
    """
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
            return settings
        except Exception as e:
            print(f"Warning: Could not load settings from {settings_path}: {e}")
            print("Using default settings")
            return defaults
    else:
        print(f"Info: Settings file not found at {settings_path}, using defaults")
        return defaults


def _deep_merge(base: Dict, override: Dict) -> Dict:
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


def load_bookmarks() -> list:
    """
    Load bookmark app IDs from JSON file.

    Returns:
        List of desktop file IDs (e.g., ["firefox.desktop", ...])

    If file doesn't exist or is invalid, returns empty list.
    """
    import json

    bookmarks_path = Path(__file__).parent.parent / "data" / "bookmarks.json"

    if bookmarks_path.exists():
        try:
            with open(bookmarks_path) as f:
                data = json.load(f)
                return data.get("bookmarks", [])
        except Exception as e:
            print(f"Warning: Could not load bookmarks from {bookmarks_path}: {e}")
            return []
    else:
        print(f"Info: Bookmarks file not found at {bookmarks_path}, using empty list")
        return []


def save_bookmarks(bookmark_ids: list):
    """
    Save bookmark app IDs to JSON file.

    Args:
        bookmark_ids: List of desktop file IDs to save

    Example:
        save_bookmarks(["firefox.desktop", "code.desktop"])
    """
    import json

    bookmarks_path = Path(__file__).parent.parent / "data" / "bookmarks.json"

    # Ensure data directory exists
    bookmarks_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(bookmarks_path, "w") as f:
            json.dump({"bookmarks": bookmark_ids}, f, indent=2)
    except Exception as e:
        print(f"Error: Could not save bookmarks to {bookmarks_path}: {e}")


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


