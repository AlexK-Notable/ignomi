# launcher/

Three-panel application launcher for Wayland, built on the Ignis framework (GTK4 + Layer Shell).

## Overview

The `launcher/` package implements a multi-panel application launcher with three independent windows that run in a single Ignis process. Unlike traditional launchers that grab the pointer globally, all three panels remain fully interactive because they share one process with proper Wayland Layer Shell support.

The panels are:
- **Bookmarks** (left) -- user-curated favorites with drag-and-drop reordering
- **Search** (center) -- pluggable query router (apps, calculator, web, custom commands, system controls)
- **Frequent** (right) -- apps ranked by a Firefox-style frecency algorithm

A fourth, non-interactive overlay -- the **backdrop** -- sits behind the panels and renders an animated screenshot-based blur of the desktop while the launcher is open.

## Package Structure

```
launcher/
├── config.py              # Entry point — creates backdrop + panels, loads CSS
├── __init__.py            # Package metadata (__version__)
├── panels/                # Panel UI implementations
│   ├── __init__.py        # Exports: BookmarksPanel, SearchPanel, FrequentPanel
│   ├── backdrop.py        # Full-screen animated-blur overlay (PIL pipeline)
│   ├── bookmarks.py       # Left panel: bookmarks with drag-drop
│   ├── search.py          # Center panel: search entry + query router
│   └── frequent.py        # Right panel: frecency-ranked apps
├── search/                # Query routing layer (see search/README.md)
│   ├── __init__.py        # Exports: QueryRouter, ResultItem, SearchHandler
│   ├── router.py          # Router + dataclass + Protocol
│   └── handlers/          # Five built-in handlers
│       ├── __init__.py
│       ├── app_search.py        # priority 1000 — fallback
│       ├── calculator.py        # priority 100  — "=" prefix
│       ├── commands.py          # priority 300  — "!" prefix
│       ├── controls.py          # priority 50   — vol/brightness keywords
│       └── web_search.py        # priority 200  — "?" / "g:" / "w:" / "gh:" / "yt:"
├── services/              # Backend logic
│   ├── __init__.py        # Exports: FrecencyService
│   └── frecency.py        # SQLite-backed frecency tracking
├── utils/                 # Shared helpers
│   ├── __init__.py        # Re-exports helpers (see Utility table below)
│   └── helpers.py         # App launch, bookmarks I/O, monitor detection, toggle
├── data/                  # Runtime configuration
│   ├── bookmarks.json     # Seed bookmarks (copied to XDG path on first run)
│   ├── commands.toml      # User-defined "!" commands
│   └── settings.toml      # [launcher] [frecency] [search] [animation] sections
└── styles/                # GTK4 CSS
    ├── main.css           # Layout, animations, component styles
    └── colors.css         # Symlink → Wallust-generated color definitions
```

## Entry Point

**`config.py`** is symlinked to `~/.config/ignis/config.py` and is loaded by the Ignis daemon on startup. It:

1. Configures `loguru` to log warnings to stderr and debug-level lines to `~/.local/share/ignomi/ignomi.log` (rotated at 1 MB, 3 retained)
2. Adds the launcher directory to `sys.path` (resolves symlinks for worktree support)
3. Loads CSS files (`colors.css` then `main.css`) at "user" priority (800) to override global GTK4 styles
4. Constructs `RootPanel`, which composes bookmarks/search/frequent + backdrop into a single Layer Shell window (`ignomi-launcher`)
5. Calls `RootPanel.create_window()` to build that window
6. Re-raises any panel-construction failures so `ignis init` exits non-zero rather than running a half-broken daemon (M9 failure-to-start handling)

```python
from panels.root import RootPanel

root_panel = RootPanel()
root_window = root_panel.create_window()
# root_window is a single widgets.Window (namespace="ignomi-launcher")
# containing all three panels + backdrop in a widgets.Overlay.

# Cross-panel access: window.panel gives back the Panel instance
bookmarks_window.panel = bookmarks_panel
search_window.panel = search_panel
frequent_window.panel = frequent_panel
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

- Loads app IDs from the XDG bookmarks file (see [`data/bookmarks.json`](#databookmarksjson) below)
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

- Owns a `QueryRouter` with five registered handlers (see [`search/README.md`](search/README.md))
- 120 ms debounced input
- Keyboard navigation: Up/Down arrows, Enter to launch, Escape to close
- Arrow keys intercepted in `Gtk.PropagationPhase.CAPTURE` to prevent GTK focus stealing
- Auto-focuses the entry by issuing a Hyprland `dispatch movecursor X Y` IPC command via `HyprlandService.send_command(...)`
- First result auto-selected for fast keyboard launching
- Right-click on app rows adds to bookmarks (triggers bookmarks panel refresh)
- Uses a GTK `Revealer` for open/close crossfade — the centered surface drifts laterally with Hyprland slide animations, so the panel handles its own transition

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

### Backdrop (`panels/backdrop.py`)

Full-screen non-interactive layer that renders an animated blur of the desktop behind the launcher panels.

```python
```python
from panels import backdrop

picture = backdrop.create_backdrop_widget()  # widgets.Picture, no Window
backdrop.start_open_animation(picture, monitor_idx=0)
backdrop.start_close_animation(picture, on_done=lambda: ...)
backdrop.reset(picture)
```

- Functional API — no class, no Window. The single launcher window owns the `Picture` and places it at the base of a `widgets.Overlay`.
- Captures the current monitor with `grim` (PPM format) on every open
- Generates 7 progressively-blurred frames in a `ThreadPoolExecutor` using PIL `GaussianBlur`
- Streams frames into a `GdkPixbuf` → `Gdk.Texture` and swaps them on the GTK main loop
- Open animation: sharp → full blur with quadratic ease-in (~150 ms)
- Close animation: full blur → sharp (cached frames, reverse playback)
- Per-monitor settings (radius, brightness) via the `_MONITOR_SETTINGS` dict at the top of `backdrop.py`
- Re-entrancy: rapid double-close chains the new `on_done` instead of dropping it (the `_pending_on_done` attribute on the picture)
- **PIL is not thread-safe** — each worker receives its own `Image.frombytes()` copy

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
| `close_launcher()` | Hide all `ignomi-*` windows; backdrop reverses its blur, search runs the Revealer crossfade, others snap closed |
| `toggle_launcher()` | **Canonical entry point** for the keybind. Single Ignis-process function: detect cursor monitor, set `window.monitor` on every panel, then toggle visibility. Required because wlr-layer-shell binds the surface to the monitor at creation time |
| `load_settings()` | Load `data/settings.toml` (cached) and deep-merge with built-in defaults |
| `load_bookmarks()` / `save_bookmarks(ids)` | Read/write bookmarks JSON (atomic via tmp + rename) |
| `add_bookmark(app_id)` / `remove_bookmark(app_id)` | Modify bookmarks list |
| `is_bookmarked(app_id)` | Check if app is bookmarked |
| `add_bookmark_with_refresh(app_id, button=None)` | Add bookmark, pulse the triggering button, then call `refresh_from_disk()` on the bookmarks panel |
| `get_monitor_under_cursor()` | Detect the GTK monitor index where the cursor currently sits, via `HyprlandService` IPC |
| `hyprland_monitor_to_ignis_monitor(id)` | Translate a Hyprland monitor ID into a GTK monitor index |
| `clear_container(container)` | GTK4 helper: remove every child of a widget that exposes `get_first_child` / `remove` |
| `find_app_by_id(app_id)` | Look up an `Application` object by desktop-file ID via `ApplicationsService` |

#### Monitor detection — `HyprlandService`, not subprocess

Both `get_monitor_under_cursor()` and `hyprland_monitor_to_ignis_monitor()` route through `HyprlandService.send_command(...)` rather than `subprocess.run(["hyprctl", ...])`:

```python
# helpers.py — inside get_monitor_under_cursor
from ignis.services.hyprland import HyprlandService

hyprland = HyprlandService.get_default()
cursor_raw = hyprland.send_command("cursorpos").strip()  # "x, y"
for monitor in hyprland.monitors:                          # cached list
    if (monitor.x <= cursor_x < monitor.x + monitor.width
            and monitor.y <= cursor_y < monitor.y + monitor.height):
        return _hyprland_name_to_ignis_index(monitor.name)
```

The `HyprlandService` import lives **inside** the function (not at module top) so that the helper module can be imported in test contexts without an active Hyprland socket. Earlier code shelled out to `hyprctl cursorpos` and `hyprctl monitors -j`; that path has been removed.

## Cross-Panel Communication

Panels communicate through three mechanisms:

### 1. GObject Signals
`FrecencyService` emits a `changed` signal whenever usage data is updated. The `FrequentPanel` connects to this signal in its constructor and rebuilds its app list automatically.

```python
# In FrequentPanel.__init__()
self.frecency.connect("changed", lambda x: self._refresh_apps())
```

### 2. RootPanel Singleton
When the search panel adds a bookmark, `add_bookmark_with_refresh()` reaches the bookmarks panel through `RootPanel.get_default()`:

```python
# In utils/helpers.py
from panels.root import RootPanel
root = RootPanel.get_default()
if root is not None:
    root.bookmarks_panel.refresh_from_disk()
```

`RootPanel` is the singleton constructed in `config.py`; it owns all sub-panels as attributes (`bookmarks_panel`, `search_panel`, `frequent_panel`).

### 3. Shared Singletons
All panels share the same service instances:
- `ApplicationsService.get_default()` — Ignis built-in, lists installed apps
- `get_frecency_service()` — module-level singleton in `services/frecency.py`
- `HyprlandService.get_default()` — Ignis built-in, used for monitor / cursor IPC

## Configuration

### `data/settings.toml`

Live sections (mirror the `defaults` dict in `helpers.load_settings`):

| Section | Key | Type | Default | Description |
|---------|-----|------|---------|-------------|
| `launcher` | `close_delay_ms` | int | 300 | Delay before auto-closing after app launch |
| `frecency` | `max_items` | int | 12 | Max apps shown in frequent panel |
| `frecency` | `min_launches` | int | 2 | Minimum launches before appearing |
| `search` | `max_results` | int | 30 | Maximum results returned by `AppSearchHandler` |
| `search` | `fuzzy_threshold` | int | 50 | rapidfuzz score cutoff (0-100, higher = stricter); only used when rapidfuzz is installed |
| `animation` | `transition_duration` | int | 200 | Transition duration in milliseconds for the search-panel `Revealer` |

Panel widths and heights are **hard-coded** in their respective panel modules (`search.py` `default_width=600`; bookmarks/frequent use `min_content_width=280` on their inner Scroll widgets). There is no `[panels]` section.

Per-monitor backdrop blur settings (radius, brightness) live in the `_MONITOR_SETTINGS` dict in `panels/backdrop.py` rather than `settings.toml`.

### `data/bookmarks.json`

> **Seed data.** This file is **copied once** to `~/.local/share/ignomi/bookmarks.json` on the first launch (see `_bookmarks_path()` in `helpers.py` at lines 376-391). After that copy, the in-repo file is unused — all reads and writes go through the XDG path.

JSON shape:

```json
{
  "bookmarks": [
    "firefox.desktop",
    "com.mitchellh.ghostty.desktop"
  ]
}
```

To distribute a different default set with the launcher, edit `data/bookmarks.json` *before* the first launch on a fresh machine. To change bookmarks at runtime, use the right-click menus or edit `~/.local/share/ignomi/bookmarks.json` directly and call `panel.refresh_from_disk()` (or restart Ignis).

### `data/commands.toml`

Schema for the `CustomCommandsHandler` (`!` prefix). Each command is a TOML table named `[commands.<id>]`. The handler reads this file once at construction time.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | string | recommended | Shown as the result row's secondary line |
| `exec` | string | **yes** | Shell command line; runs via `subprocess.Popen(exec_str, shell=True)` |
| `icon` | string | optional | GTK icon name (defaults to `utilities-terminal`) |

Entries missing the `exec` field are skipped with a warning at load time.

```toml
# data/commands.toml

[commands.lock]
description = "Lock screen"
exec = "hyprlock"
icon = "system-lock-screen"

[commands.suspend]
description = "Suspend system"
exec = "systemctl suspend"
icon = "system-suspend"

[commands.reload]
description = "Reload Ignis configuration"
exec = "goignis reload"
icon = "view-refresh"
```

> **Security note.** Because `exec` runs through a user shell with `shell=True`, every command inherits the user's `PATH`, aliases, and environment. The file is local and user-owned — keep it that way; do not source it from untrusted locations.

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

### Required
- **ignis** — Framework providing `widgets`, `IgnisApp`, `ApplicationsService`, `BaseService`, `HyprlandService`, `AudioService`, `BacklightService`
- **gi.repository (GTK4)** — `Gtk`, `Gdk`, `GdkPixbuf`, `GLib`, `GObject` for widget system and event handling
- **toml** — Parse `settings.toml` and `commands.toml`
- **loguru** — Structured logging with file rotation (replaces ad-hoc `print()`)
- **Pillow (PIL)** — `Image`, `ImageEnhance`, `ImageFilter` for backdrop blur frame generation
- **sqlite3** — Frecency database (Python stdlib)
- **subprocess** — Used to invoke `grim` (backdrop screenshot), `xdg-open` (web search), `wl-copy` (calculator clipboard), and user-defined commands

### Optional
- **simpleeval** — Safe expression evaluator for the calculator handler. Without it, `CalculatorHandler.matches()` always returns `False` and `=` queries fall through. Install: `pipx inject ignis simpleeval`
- **rapidfuzz** — Typo-tolerant fuzzy app search. Without it, `AppSearchHandler` falls back to substring matching via `ApplicationsService.search()`. Install: `pipx inject ignis rapidfuzz`

### External CLI tools (runtime, not Python packages)
- **grim** — Wayland screenshot tool, used by `backdrop.py`
- **xdg-open** — URL opener for `WebSearchHandler`
- **wl-copy** (wl-clipboard) — Clipboard for `CalculatorHandler`

## Testing

Tests live in `tests/` at the project root and run with:

```bash
pytest tests/ -v
```

Conventions:
- Fixtures (`tmp_db`, `tmp_bookmarks`, `tmp_settings`, `tmp_commands`) live in `tests/conftest.py`
- Handler tests are GTK-free (`test_router.py`, `test_calculator.py`, `test_app_search.py`, `test_commands.py`, `test_web_search.py`)
- Service / utility tests use `tmp_path` + monkeypatching of `time.time()`, `BaseService.__init__`, and `ApplicationsService.apps`

When adding a new handler, mirror the structure of `tests/test_calculator.py` — instantiate the handler directly and assert on `matches()` / `get_results()`. No display server or Ignis daemon is needed.

## How to Add a New Panel

Since A1, panels are widget-tree producers that get composed inside `RootPanel`'s single Layer Shell window — they no longer return their own `widgets.Window`. Add a new panel like this:

1. Create `panels/your_panel.py`:

```python
from ignis import widgets

class YourPanel:
    def __init__(self):
        # Initialize services and state
        pass

    def create_widget(self):
        # Build a widget tree (no Window) and return it.
        # RootPanel wraps it in a Revealer + places it in the Overlay layout.
        return widgets.Box(
            vertical=True,
            vexpand=True,
            valign="center",
            child=[...],
        )
```

2. Export from `panels/__init__.py`:
```python
from .your_panel import YourPanel
__all__ = [..., "YourPanel"]
```

3. Wire into `RootPanel.create_window()` (`panels/root.py`): instantiate, create the widget, wrap in a Revealer, place in the layout HBox.

4. `toggle_launcher()` and `close_launcher()` work automatically — they only deal with the single launcher window.

5. If your panel needs a custom open/close animation independent of the surrounding launcher, give it its own internal Revealer (the search panel pattern). RootPanel already orchestrates parallel reveal/unreveal across panels.

## How to Add a New Search Handler

See [`search/README.md`](search/README.md) for the full handler authoring guide.

## See Also

- [`search/README.md`](search/README.md) — Query router, handler protocol, authoring guide
- [Project README](../README.md) — Installation, keybinds, usage
- [Architecture Diagrams](../docs/diagrams/) — Visual system overview
- [Design Documents](../project-docs/architecture/) — Architectural decisions and rationale
- [CLAUDE.md](../CLAUDE.md) — Developer reference for working with this codebase
