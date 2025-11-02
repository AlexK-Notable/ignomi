"""
Helper utilities for the Ignomi launcher.

Provides common functions used across multiple panels:
- App launching with frecency tracking
- Launcher window management
- Settings loading
"""

from gi.repository import GLib
from pathlib import Path
import toml
import subprocess
import json
from typing import Dict, Any, Optional


def get_focused_monitor() -> int:
    """
    Get the ID of the currently focused monitor in Hyprland.

    Returns:
        Monitor ID (int), defaults to 0 if detection fails
    """
    try:
        result = subprocess.run(
            ['hyprctl', 'monitors', '-j'],
            capture_output=True,
            text=True,
            timeout=1
        )
        if result.returncode == 0:
            monitors = json.loads(result.stdout)
            for monitor in monitors:
                if monitor.get('focused', False):
                    return monitor['id']
    except Exception:
        pass

    # Fallback to monitor 0
    return 0


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
            "panels": {
                "bookmark_width": 300,
                "frequent_width": 300,
                "search_width": 500,
                "search_height": 600
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
        "panels": {
            "bookmark_width": 300,
            "frequent_width": 300,
            "search_width": 500,
            "search_height": 600,
        },
        "frecency": {
            "max_items": 12,
            "min_launches": 2,
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


def reorder_bookmarks(app_id: str, new_index: int):
    """
    Move a bookmark to a new position.

    Args:
        app_id: Desktop file ID to move
        new_index: New position (0-indexed)

    If app_id not found, does nothing.
    """
    bookmarks = load_bookmarks()

    if app_id in bookmarks:
        # Remove from current position
        bookmarks.remove(app_id)

        # Insert at new position
        new_index = max(0, min(new_index, len(bookmarks)))
        bookmarks.insert(new_index, app_id)

        save_bookmarks(bookmarks)
