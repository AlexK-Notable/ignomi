# launcher/

Three-panel application launcher for Wayland, built on the Ignis framework (GTK4 + Layer Shell).

## Overview

The `launcher/` package implements a multi-panel application launcher with three independent windows that run in a single Ignis process. Unlike traditional launchers that grab the pointer globally, all three panels remain fully interactive because they share one process with proper Wayland Layer Shell support.

The panels are:
- **Bookmarks** (left) -- user-curated favorites with drag-and-drop reordering
- **Search** (center) -- real-time app filtering with keyboard navigation
- **Frequent** (right) -- apps ranked by a Firefox-style frecency algorithm

## Package Structure

```
launcher/
├── config.py              # Entry point -- creates panels, loads CSS
├── __init__.py            # Package metadata (__version__)
├── panels/                # Panel UI implementations
│   ├── __init__.py        # Exports: BookmarksPanel, SearchPanel, FrequentPanel
│   ├── bookmarks.py       # Left panel: bookmarks with drag-drop
│   ├── search.py          # Center panel: search + keyboard nav
│   └── frequent.py        # Right panel: frecency-ranked apps
├── services/              # Backend logic
│   ├── __init__.py        # Exports: FrecencyService
│   └── frecency.py        # SQLite-backed frecency tracking
├── utils/                 # Shared helpers
│   ├── __init__.py        # Exports: launch_app, close_launcher, load_settings
│   └── helpers.py         # App launch, bookmarks I/O, monitor detection
├── data/                  # Runtime configuration
│   ├── bookmarks.json     # Bookmarked app IDs (auto-saved on changes)
│   └── settings.toml      # Panel dimensions, close delay, frecency limits
└── styles/                # GTK4 CSS
    ├── main.css           # Layout, animations, component styles
    └── colors.css         # Symlink -> Wallust-generated color definitions
```

## Entry Point

**`config.py`** is symlinked to `~/.config/ignis/config.py` and is loaded by the Ignis daemon on startup. It:

1. Adds the launcher directory to `sys.path` (resolves symlinks for worktree support)
2. Loads CSS files (`colors.css` then `main.css`) at "user" priority (800) to override global GTK4 styles
3. Instantiates all three panel classes
4. Calls `create_window()` on each, producing three `widgets.Window` instances
5. Stores panel references on window objects for cross-panel communication

```python
from panels.bookmarks import BookmarksPanel
from panels.search import SearchPanel
from panels.frequent import FrequentPanel

bookmarks_panel = BookmarksPanel()
search_panel = SearchPanel()
frequent_panel = FrequentPanel()

bookmarks_window = bookmarks_panel.create_window()
search_window = search_panel.create_window()
frequent_window = frequent_panel.create_window()

# Cross-panel access: window.panel gives back the Panel instance
bookmarks_window.panel = bookmarks_panel
```

## Key Components

### BookmarksPanel (`panels/bookmarks.py`)

Left-anchored panel displaying user-curated favorite applications.

```python
from panels.bookmarks import BookmarksPanel

panel = BookmarksPanel()
window = panel.create_window()  # widgets.Window anchored left

# External refresh (called by SearchPanel after adding a bookmark)
panel.refresh_from_disk()
```

- Loads app IDs from `data/bookmarks.json` on init
- Right-click context menu to remove bookmarks
- GTK4 drag-and-drop reordering (`Gtk.DragSource` / `Gtk.DropTarget`)
- Auto-saves bookmark order changes to disk

### SearchPanel (`panels/search.py`)

Center-positioned panel with search entry and filtered results.

```python
from panels.search import SearchPanel

panel = SearchPanel()
window = panel.create_window()  # widgets.Window anchored top+bottom
```

- Uses `ApplicationsService.search()` for real-time filtering
- Keyboard navigation: Up/Down arrows, Enter to launch, Escape to close
- Arrow keys intercepted in CAPTURE phase to prevent GTK focus stealing
- Auto-focuses search entry by moving cursor via `hyprctl dispatch movecursor`
- First result auto-selected for fast keyboard launching
- Right-click to add apps to bookmarks (triggers bookmarks panel refresh)

### FrequentPanel (`panels/frequent.py`)

Right-anchored panel displaying apps ranked by usage frecency.

```python
from panels.frequent import FrequentPanel

panel = FrequentPanel()
window = panel.create_window()  # widgets.Window anchored right
```

- Connects to `FrecencyService.changed` signal for automatic refresh
- Shows launch count badge per app
- Right-click context menu: remove from frequents, add to bookmarks
- Empty state message when no usage data exists

### FrecencyService (`services/frecency.py`)

SQLite-backed service implementing Firefox's frecency algorithm.

```python
from services.frecency import get_frecency_service

service = get_frecency_service()  # Singleton

service.record_launch("firefox.desktop")
top_apps = service.get_top_apps(limit=12, min_launches=2)
# Returns: [(app_id, score, launch_count, last_launch), ...]
```

- Database at `~/.local/share/ignomi/app_usage.db`
- Frecency formula: `score = launch_count * recency_weight`
- Recency weights: 100x (<4 days), 70x (<14 days), 50x (<31 days), 30x (<90 days), 10x (90+ days)
- Emits GObject `changed` signal after `record_launch()` and `clear_stats()`
- Extends `ignis.base_service.BaseService`

### Utilities (`utils/helpers.py`)

Shared functions used across all panels.

| Function | Purpose |
|----------|---------|
| `launch_app(app, frecency_service, close_delay_ms)` | Launch app, record frecency, schedule auto-close |
| `close_launcher()` | Hide all `ignomi-*` windows |
| `load_settings()` | Load `data/settings.toml` with defaults |
| `get_monitor_under_cursor()` | Detect monitor at cursor position (Hyprland + GTK) |
| `load_bookmarks()` / `save_bookmarks(ids)` | Read/write `data/bookmarks.json` |
| `add_bookmark(app_id)` / `remove_bookmark(app_id)` | Modify bookmarks list |
| `is_bookmarked(app_id)` | Check if app is bookmarked |
| `hyprland_monitor_to_ignis_monitor(id)` | Translate Hyprland monitor ID to GTK monitor index |

## Cross-Panel Communication

Panels communicate through three mechanisms:

### 1. GObject Signals
`FrecencyService` emits a `changed` signal whenever usage data is updated. The `FrequentPanel` connects to this signal in its constructor and rebuilds its app list automatically.

```python
# In FrequentPanel.__init__()
self.frecency.connect("changed", lambda x: self._refresh_apps())
```

### 2. Direct Panel Access
When the search panel adds a bookmark, it reaches into the bookmarks panel to trigger a refresh:

```python
# In SearchPanel._on_right_click()
app_instance = IgnisApp.get_default()
bookmarks_window = app_instance.get_window("ignomi-bookmarks")
if bookmarks_window and hasattr(bookmarks_window, 'panel'):
    bookmarks_window.panel.refresh_from_disk()
```

This works because `config.py` stores panel references as `window.panel` attributes.

### 3. Shared Singletons
All panels share the same service instances:
- `ApplicationsService.get_default()` -- Ignis built-in, lists installed apps
- `get_frecency_service()` -- module-level singleton in `services/frecency.py`

## Configuration

### `data/settings.toml`

| Section | Key | Type | Default | Description |
|---------|-----|------|---------|-------------|
| `launcher` | `close_delay_ms` | int | 300 | Delay before auto-closing after app launch |
| `panels` | `bookmark_width` | int | 300 | Bookmarks panel width (px) |
| `panels` | `frequent_width` | int | 300 | Frequent panel width (px) |
| `panels` | `search_width` | int | 500 | Search panel width (px) |
| `panels` | `search_height` | int | 600 | Search panel height (px) |
| `frecency` | `max_items` | int | 12 | Max apps shown in frequent panel |
| `frecency` | `min_launches` | int | 2 | Minimum launches before appearing |

### `data/bookmarks.json`

Simple JSON array of desktop file IDs. Auto-saved when bookmarks change:

```json
{
  "bookmarks": [
    "firefox.desktop",
    "com.mitchellh.ghostty.desktop"
  ]
}
```

### `styles/colors.css`

Symlink to Wallust-generated color definitions. Expected to define `@define-color` variables used in `main.css`. The CSS variable naming convention uses a `@base_opacitypercent` pattern:

| Variable | Meaning |
|----------|---------|
| `@bg_65` | Background color at 65% opacity |
| `@fg_70` | Foreground color at 70% opacity |
| `@color4_30` | Palette color 4 at 30% opacity |
| `@color6_40` | Palette color 6 at 40% opacity |

This pattern exists because GTK4's CSS parser cannot apply `alpha()` to `@define-color` variables at runtime. All alpha variants must be pre-computed in the Wallust template as separate `@define-color` declarations with RGBA values.

## Dependencies

- **ignis** -- Framework providing `widgets`, `IgnisApp`, `ApplicationsService`, `BaseService`
- **gi.repository (GTK4)** -- `Gtk`, `Gdk`, `GLib`, `GObject` for widget system and event handling
- **toml** -- Parse `settings.toml`
- **sqlite3** -- Frecency database (stdlib)
- **subprocess** -- Shell out to `hyprctl` for monitor/cursor detection

## How to Add a New Panel

1. Create `panels/your_panel.py` with a class following this pattern:

```python
from ignis import widgets
from utils.helpers import get_monitor_under_cursor

class YourPanel:
    def __init__(self):
        # Initialize services and state
        pass

    def create_window(self):
        # Build widget tree, return widgets.Window
        window = widgets.Window(
            namespace="ignomi-yourpanel",
            monitor=get_monitor_under_cursor(),
            anchor=["top", "bottom"],  # Choose anchoring
            layer="top",
            visible=False,
            child=widgets.Box(...)
        )
        # Add visibility handler for monitor detection
        window.connect("notify::visible", self._on_visibility_changed)
        return window

    def _on_visibility_changed(self, window, param):
        if window.get_visible():
            cursor_monitor = get_monitor_under_cursor()
            if window.monitor != cursor_monitor:
                window.monitor = cursor_monitor
```

2. Export from `panels/__init__.py`:
```python
from .your_panel import YourPanel
__all__ = [..., "YourPanel"]
```

3. Instantiate in `config.py`:
```python
from panels.your_panel import YourPanel
your_panel = YourPanel()
your_window = your_panel.create_window()
your_window.panel = your_panel
```

4. Add the window name to `scripts/toggle-launcher.sh`:
```bash
ignis toggle-window ignomi-yourpanel &
```

5. Update `utils/helpers.py` `close_launcher()` -- no change needed since it already closes all windows matching `ignomi-*`.

## See Also

- [Project README](../README.md) -- Installation, keybinds, usage
- [Architecture Diagrams](../docs/diagrams/) -- Visual system overview
- [Design Documents](../project-docs/architecture/) -- Architectural decisions and rationale
- [CLAUDE.md](../CLAUDE.md) -- Developer reference for working with this codebase
