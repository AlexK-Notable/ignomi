# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Launching Ignomi

### Prerequisites
- Ignis installed via `pipx install ./ignis`
- Config symlink: `ln -sf ~/repos/ignomi/launcher/config.py ~/.config/ignis/config.py`
- Optional Python deps for full functionality (inject into the Ignis venv):
  - `pipx inject ignis loguru toml Pillow simpleeval rapidfuzz`
  - `loguru` and `toml` are required; `Pillow` is required for the backdrop; `simpleeval` and `rapidfuzz` are optional (calculator handler / fuzzy search degrade gracefully if missing)

### Launch Process

1. **Initialize Ignis daemon** (if not already running):
   ```bash
   ignis init &
   ```

2. **Toggle the launcher** (preferred — handles multi-monitor placement atomically):
   ```bash
   ~/repos/ignomi/scripts/toggle-launcher.sh
   ```
   Bind this to a hotkey in your compositor config.

3. **Manually open all four surfaces** (debugging only):
   ```bash
   ignis open-window ignomi-backdrop && \
   ignis open-window ignomi-bookmarks && \
   ignis open-window ignomi-search && \
   ignis open-window ignomi-frequent
   ```

### Development Commands

| Command | Purpose |
|---------|---------|
| `ignis list-windows` | List all registered windows |
| `ignis reload` | Reload config after Python or CSS changes |
| `ignis quit` | Stop the Ignis daemon |
| `ignis run-python "<code>"` | Execute Python inside the running Ignis process |
| `ignis inspector` | Open GTK Inspector against the running daemon |
| `journalctl -f -t ignis` | Follow Ignis daemon logs |
| `tail -f ~/.local/share/ignomi/ignomi.log` | Follow Ignomi-specific logs (loguru) |

### Common Launch Issues

- **"Ignis is not running"** — run `ignis init &` first.
- **"No such window: ignomi"** — there is no aggregate window. Use `ignomi-backdrop`, `ignomi-bookmarks`, `ignomi-search`, `ignomi-frequent`.
- **Config not loading** — verify the symlink: `readlink ~/.config/ignis/config.py` should print `/home/komi/repos/ignomi/launcher/config.py` (not a worktree).
- **Wrong monitor on toggle** — `wlr-layer-shell` binds output at surface creation; `toggle_launcher()` sets `window.monitor` BEFORE showing. Always toggle via `scripts/toggle-launcher.sh` or call `toggle_launcher()` from inside the process — opening windows individually via `ignis open-window` skips the monitor-detection step.

## Architecture Overview

### Four Layer-Shell Surfaces

Ignomi is a Wayland launcher built on the Ignis framework (GTK4 + Layer Shell). It runs as a single process and exposes four independent surfaces:

| Surface | Module | Anchor | Layer | Exclusivity | Animation source |
|---------|--------|--------|-------|-------------|------------------|
| `ignomi-backdrop` | `launcher/panels/backdrop.py` | top+bottom+left+right (full-screen) | `top` | `ignore` | Custom blur frames (PIL → GdkPixbuf) |
| `ignomi-bookmarks` | `launcher/panels/bookmarks.py` | left+top+bottom | `overlay` | `ignore` | Hyprland layerrules |
| `ignomi-search` | `launcher/panels/search.py` | top+bottom (centered) | `overlay` | `ignore` | GTK Revealer crossfade |
| `ignomi-frequent` | `launcher/panels/frequent.py` | right+top+bottom | `overlay` | `ignore` | Hyprland layerrules |

All surfaces use `exclusivity="ignore"` so the centered search panel does not jump when the edge panels release their exclusive zones — see `project-docs/discoveries/` and zettelkasten note `[[20260226T022743651177993774]]` for the multi-hour debugging story.

### Animation Architecture (read this before touching panel open/close)

- **Edge-anchored panels (`bookmarks`, `frequent`) and the `backdrop`** rely on Hyprland `layerrule animation slide ...` rules in `~/.config/hypr/config/windowrules.conf`. They use plain `widgets.Window`, NOT `RevealerWindow` — combining the two produces a dual-animation conflict.
- **The centered `search` panel uses a GTK Revealer** (`transition_type="crossfade"`) wrapped in a centering Box. Centered surfaces drift laterally under compositor slide animations, so we let GTK own the transition for the search panel only.
- `close_launcher()` in `launcher/utils/helpers.py` dispatches per-surface: backdrop runs its reverse blur, search runs the Revealer unreveal (then hides on `notify::child-revealed`), bookmarks/frequent just toggle `visible=False` and let Hyprland animate.

### Search Router Subsystem (`launcher/search/`)

The search panel does not run app filtering directly. Queries are routed through a priority-ordered handler pipeline:

```
launcher/search/
├── router.py              # QueryRouter, ResultItem dataclass, SearchHandler Protocol
└── handlers/
    ├── controls.py        # SystemControlsHandler   priority 50   (volume / brightness widgets)
    ├── calculator.py      # CalculatorHandler       priority 100  ("=" prefix, simpleeval)
    ├── web_search.py      # WebSearchHandler        priority 200  ("?", "g:", "w:", "gh:", "yt:" prefixes)
    ├── commands.py        # CustomCommandsHandler   priority 300  ("!" prefix, reads commands.toml)
    └── app_search.py      # AppSearchHandler        priority 1000 (fallback — always matches)
```

- **Handler protocol** (structural, no inheritance): `name: str`, `priority: int`, `matches(query) -> bool`, `get_results(query) -> list[ResultItem]`.
- **Routing rule**: `QueryRouter.route()` returns the first matching handler's results, sorted ascending by `priority` (lower = checked first). App search has priority 1000 and `matches` always returns True, so it is the fallback.
- **`ResultItem`** can carry an `on_activate` callback OR a `widget_builder` (used by `SystemControlsHandler` to render Scale/Switch widgets inline).
- **Empty queries** are routed straight to `app_search` to populate default results.
- Adding a new handler: implement the protocol, register in `SearchPanel.__init__` (`launcher/panels/search.py`) with a unique priority slot.

### Backdrop Pipeline (`launcher/panels/backdrop.py`)

- Capture: `grim -o <connector> -t ppm -` → `PIL.Image` (per-monitor `connector` resolved via `Gdk.Display`).
- Generate: 7 Gaussian-blur frames (sharp → full blur), produced concurrently in a `ThreadPoolExecutor`. **PIL `Image` objects are not thread-safe** — each worker calls `Image.frombytes()` on shared raw bytes to get its own copy. Do not share an `Image` across threads.
- Display: raw RGB bytes → `GdkPixbuf.Pixbuf.new_from_data` → `Gdk.Texture` → `widgets.Picture.set_paintable`. Frames are streamed to the main thread via `GLib.idle_add` as they finish, so the sharp screenshot appears immediately.
- Animation timing: open and close each take ~150ms with quadratic ease-in (`_ease_in_intervals`).
- Cancellation: `window._anim_gen` is incremented on every visibility change; in-flight callbacks compare `gen` and bail if stale.
- Per-monitor overrides: edit `_MONITOR_SETTINGS` (connector → `{radius, brightness}`) at the top of `backdrop.py`. There is currently NO `[backdrop]` section in `settings.toml`.

### Cross-Surface Communication

1. **GObject signals**: `FrecencyService` emits `changed` → `FrequentPanel._refresh_apps`.
2. **Direct panel access via IgnisApp**: `add_bookmark_with_refresh()` (`utils/helpers.py`) reaches the bookmarks window via `IgnisApp.get_default().get_window("ignomi-bookmarks")` and calls `panel.refresh_from_disk()`.
3. **Singletons**: `get_frecency_service()`, `ApplicationsService.get_default()`, `HyprlandService.get_default()` are shared across all panels.

### Key Services

**FrecencyService** (`launcher/services/frecency.py`):
- SQLite database at `~/.local/share/ignomi/app_usage.db`.
- Firefox-style frecency: `score = launch_count × recency_weight`.
- Weights: 100x (<4 days), 70x (<14 days), 50x (<31 days), 30x (<90 days), 10x (90+ days).
- Emits `changed` GObject signal when usage data updates.

**HyprlandService IPC** (replaces `subprocess` + `hyprctl` calls):
- `helpers.get_monitor_under_cursor()` and `hyprland_monitor_to_ignis_monitor()` use `HyprlandService.get_default().monitors` and `.send_command("cursorpos")`.
- The `cursorpos` IPC reply is plain text (`"x, y"`), NOT JSON — split on `", "`.
- Mapping Hyprland `monitor.name` (connector, e.g. `DP-1`) → GTK monitor index is done via `Gdk.Display.get_default().get_monitors()`.

**`toggle_launcher()`** (`launcher/utils/helpers.py`):
- Single source of truth for opening/closing all surfaces atomically.
- Must run **inside** the Ignis process — `wlr-layer-shell` fixes the output at surface creation, so `window.monitor` must be set BEFORE `set_visible(True)`.
- `scripts/toggle-launcher.sh` is a one-line wrapper: `ignis run-python "from utils.helpers import toggle_launcher; toggle_launcher()"`. Using `ignis run-python` is critical — it is a single IPC call, atomic within the daemon's main loop, and avoids the racy "spawn N goignis processes in parallel" pattern.

### Configuration Files

| File | Purpose |
|------|---------|
| `launcher/data/settings.toml` | `[launcher]` (close_delay_ms), `[frecency]` (max_items, min_launches), `[search]` (max_results, fuzzy_threshold), `[animation]` (transition_duration). **No `[panels]` or `[backdrop]` section** — panel widths and per-monitor blur are hard-coded. |
| `launcher/data/bookmarks.json` | Seed bookmarks. Migrated to `~/.local/share/ignomi/bookmarks.json` on first run; the in-repo file is read once. |
| `launcher/data/commands.toml` | User-defined `!`-prefixed commands consumed by `CustomCommandsHandler`. |
| `launcher/styles/main.css` | Main GTK4 stylesheet. |
| `launcher/styles/colors.css` | Wallust-generated palette (symlinked from `~/.config/ignomi/colors.css`). |

### Entry Point

`launcher/config.py` is the Ignis configuration file (symlinked to `~/.config/ignis/config.py`). It instantiates the four panels, loads `colors.css` then `main.css`, and uses `os.path` for portable path resolution.

## Critical Implementation Details

### GTK4 Layer Shell Transparency

Required for transparency on Wayland Layer Shell windows:

```css
window,
window.background,
window.ignomi-window {
    background: transparent;
    background-color: transparent;
}
```

This must be set at the window level, not just on child widgets. See `project-docs/research/gtk4-layer-shell-transparency.md`.

### GTK4 CSS Variable Limitations

GTK4 CSS cannot use `alpha()` with `@define-color` variables — they resolve at parse time, not runtime:

```css
/* DOES NOT WORK */
@define-color bg #1a1a1a;
.panel { background: alpha(@bg, 0.9); }

/* WORKS — pre-compute alpha in the Wallust template */
@define-color bg_90 rgba(26, 26, 26, 0.9);
.panel { background: @bg_90; }
```

Naming convention: `@base_opacitypercent` (e.g. `@bg_65`, `@color4_30`). All variants must be declared in `~/.config/wallust/templates/ignomi.css`.

### Wallust Template Variables

Available in `~/.config/wallust/templates/ignomi.css`:
- `{{background}}`, `{{foreground}}` — main colors
- `{{color0}}` through `{{color15}}` — palette colors

Wallust does NOT provide `{{accent}}`, `{{success}}`, etc. — map them manually to color indices in the template.

### Logging (loguru)

The codebase uses `loguru` for all logging. Do not introduce `print()` for diagnostics.
- Default sink: `~/.local/share/ignomi/ignomi.log`.
- Use `logger.debug` for hot paths (search debounce, blur frame display), `logger.warning` for recoverable failures (grim missing, settings load failed), `logger.error` for unrecoverable.

### Auto-Close Behavior

After launching an app, panels auto-close after `close_delay_ms` (default 300ms) via `GLib.timeout_add` → `close_launcher()`. Configure in `settings.toml [launcher]`.

## Testing

Run the suite from the repo root:

```bash
pytest tests/ -v
```

- ~70-80 tests across 8 files: `test_app_search.py`, `test_calculator.py`, `test_commands.py`, `test_web_search.py`, `test_router.py`, `test_bookmarks.py`, `test_settings.py`, `test_frecency.py`.
- Fixtures in `tests/conftest.py`: `tmp_db`, `tmp_bookmarks`, `tmp_settings`, `tmp_commands` — each creates a real file in `tmp_path`, no filesystem mocking.
- **Headless-import-mock pattern**: `test_app_search.py`, `test_bookmarks.py`, and `test_frecency.py` install `MagicMock` modules into `sys.modules` for `gi`, `gi.repository`, `ignis`, `ignis.widgets`, and `ignis.services.*` BEFORE importing the modules under test. This lets the suite run on a headless box (CI, remote shell) with no display server.
- Only mock these specific surfaces: `time.time()`, `GObject.emit`, `BaseService.__init__`, `ApplicationsService.apps`. Real file I/O exercises real bugs.

**Coverage gaps (uncovered, be honest with reviewers):**
- `SystemControlsHandler` (`launcher/search/handlers/controls.py`)
- `backdrop.py` (PIL pipeline, ease-in math, generation counter, monitor lookup)
- `BookmarksPanel` / `SearchPanel` / `FrequentPanel` classes themselves
- `toggle_launcher()`, `close_launcher()`, `_close_search_panel`, `_close_backdrop`
- `get_monitor_under_cursor()`, `hyprland_monitor_to_ignis_monitor()`

## Debugging

### Frecency Tracking

```bash
~/repos/ignomi/scripts/track-launch.sh firefox.desktop
sqlite3 ~/.local/share/ignomi/app_usage.db "SELECT * FROM app_stats ORDER BY last_launch DESC;"
```

### Styling Issues

1. Check CSS load errors: `journalctl -t ignis | grep -i css`
2. Verify symlinks:
   ```bash
   ls -la ~/repos/ignomi/launcher/styles/colors.css   # → ~/.config/ignomi/colors.css
   ls -la ~/.config/ignis/config.py                   # → ~/repos/ignomi/launcher/config.py
   ```
3. Diagnostic isolation: replace `@define-color` vars with literal hex values to confirm CSS is loading.
4. Live inspect: `ignis inspector`.

### Common Pitfalls

- **Touching multiple things at once** — change one variable at a time and `ignis reload` between attempts.
- **Forgetting to reload** — Python and CSS edits both require `ignis reload`.
- **Using `print()`** — output goes nowhere useful; use `logger.debug` and tail `ignomi.log`.
- **Calling `subprocess.run("hyprctl ...")` for monitor data** — use `HyprlandService.get_default()` instead. There should be no `hyprctl` calls in `launcher/` Python code.
- **Opening windows with `ignis open-window` then expecting correct multi-monitor placement** — that path skips `toggle_launcher()`, so the window opens on whichever monitor was last set.

See `project-docs/discoveries/systematic-debugging-phase1-theming.md` for the systematic-debugging methodology used during Phase 1.

## Project Documentation

| Directory | Contents |
|-----------|----------|
| `project-docs/architecture/` | Design documents, component structure, architectural decisions |
| `project-docs/research/` | Technical investigations (GTK4 transparency, CSS limitations, Wallust) |
| `project-docs/discoveries/` | Debugging walkthroughs, lessons learned |
| `project-docs/status/` | Milestone completions |
| `docs/diagrams/` | PNG diagrams (system architecture, panel structure, dataflow) |
| `tests/` | Pytest suite with fixtures |

**Most critical references:**
- `project-docs/research/gtk4-layer-shell-transparency.md` — GTK4 transparency patterns (essential for any Layer Shell work).
- `project-docs/architecture/2025-11-02-ignomi-launcher-design.md` — Original design rationale.
