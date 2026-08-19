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

3. **Manually open the launcher** (debugging only):
   ```bash
   ignis open-window ignomi-launcher
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
- **"No such window: ignomi"** — the registered namespace is `ignomi-launcher` (post-A1).
- **Config not loading** — verify the symlink: `readlink ~/.config/ignis/config.py` should print `/home/komi/repos/ignomi/launcher/config.py` (not a worktree).
- **Wrong monitor on toggle** — `wlr-layer-shell` binds output at surface creation; `toggle_launcher()` sets `window.monitor` BEFORE showing. Always toggle via `scripts/toggle-launcher.sh` or call `toggle_launcher()` from inside the process — opening windows individually via `ignis open-window` skips the monitor-detection step.

## Architecture Overview

### Single Layer Shell Surface (post-A1 refactor, 2026-05)

Ignomi is a Wayland launcher built on the Ignis framework (GTK4 + Layer Shell). It runs as a single process and exposes **one** Layer Shell surface — `ignomi-launcher` — that hosts all panels via a `widgets.Overlay`.

| Component | Module | Role |
|-----------|--------|------|
| `RootPanel` | `launcher/panels/root.py` | Owns the single window + backdrop; hosts the screen Stack; orchestrates open/close; owns global input policy (Escape, click-to-dismiss) |
| `ScreenManager` | `launcher/screens/manager.py` | Registry + `widgets.Stack` for screens; `register()` / `build()` / `switch_to()` / `go_home()` |
| `HomeScreen` | `launcher/screens/home.py` | Default screen: composes the three panels + the generated nav bar; owns the open/close reveal |
| `SystemdScreen` | `launcher/screens/systemd.py` | Start/stop/restart a curated unit list from `data/systemd.toml` |
| `ClipboardScreen` | `launcher/screens/clipboard.py` | Clipboard history via elephant — copy / pin / remove |
| `ShortcutsScreen` | `launcher/screens/shortcuts.py` | Cheat sheet **generated** from the router + screen registries |
| `ElephantClient` | `launcher/services/elephant.py` | Wraps the `elephant` CLI (query + activate) for the three integrations |
| `BookmarksPanel` | `launcher/panels/bookmarks.py` | `create_widget()` returns left-aligned content; revealed via `slide_right` Revealer |
| `SearchPanel` | `launcher/panels/search.py` | `create_widget()` returns centered content with internal `crossfade` Revealer |
| `FrequentPanel` | `launcher/panels/frequent.py` | `create_widget()` returns right-aligned content; revealed via `slide_left` Revealer |
| backdrop module | `launcher/panels/backdrop.py` | Functional API (`create_backdrop_widget`, `start_open_animation`, `start_close_animation`, `reset`); animates blur on a `widgets.Picture` placed at the base of the Overlay |

The single window: `namespace="ignomi-launcher"`, `anchor=["top","bottom","left","right"]`, `layer="overlay"`, `exclusivity="ignore"`, `kb_mode="on_demand"`. Why one surface:

- The compositor never sees siblings, so the search-panel-drift bug class is impossible by construction (see z-note `[[20260226T022743651177993774]]` for the historical issue).
- All animations are GTK Revealers; nothing in Hyprland's `windowrules.conf` needs Ignomi-specific rules anymore.
- `close_launcher()` becomes one method call (`RootPanel.close()`) instead of per-surface dispatch.

### Screen System (`launcher/screens/`)

The single window hosts a `widgets.Stack` of **screens**. Exactly one screen is visible; switching is a 200 ms crossfade. `HomeScreen` is the default and holds the classic bookmarks | search | frequent composition plus a nav bar; pressing a nav button switches to that screen, Escape returns home.

```
launcher/screens/
├── manager.py     # Screen Protocol + ScreenManager (registry, Stack, switching)
├── home.py        # HomeScreen — the three panels + generated nav bar
└── systemd.py     # SystemdScreen — curated unit controls
```

**Adding a screen** — three steps, no refactor:

1. Write a class with `name`, `title`, `icon`, and `create_widget()`.
2. `self.screens.register(MyScreen())` in `RootPanel.__init__`.
3. There is no step 3 — the nav button is generated from the registry.

Optional hooks, probed with `getattr` so you can omit them: `show_in_nav` (default True), `on_enter()`, `on_leave()`, `on_key_press(keyval, state) -> bool`.

**Rules that matter:**

- **Screen switching is the Stack crossfade and nothing else.** Panel Revealers are driven ONLY by launcher open/close (`HomeScreen.set_revealed()`). Animating both at once recreates the dual-animation conflict — see the iron rule below.
- **Mechanism vs policy**: `ScreenManager` switches; `RootPanel` decides what Escape means. The window-level CAPTURE key controller lives on `RootPanel`, applies Escape (back, or close when already home), then offers the event to the active screen via `ScreenManager.handle_key()`. It used to live on `SearchPanel` and closed the launcher unconditionally — wrong the moment a second screen exists.
- **Ignis quirk**: `widgets.Stack`'s `child` setter calls `add_titled(child, None, title)` — pages get NO name, so `set_visible_child_name()` can never work. `ScreenManager` keeps its own `name -> widget` map and uses `set_visible_child(widget)`.
- **Import cycle**: `panels/__init__.py` imports `root`, and `root` needs `HomeScreen`, which imports the panels. `RootPanel.__init__` therefore imports `HomeScreen`/`SystemdScreen` lazily. Do not hoist those to module level — it breaks depending on which package is imported first.

### Click-to-Dismiss

Clicking the blurred backdrop — anywhere that isn't launcher UI — closes the launcher and returns you to the desktop. Implemented in `RootPanel` alongside the Escape policy, since it is the same kind of global input decision.

The window covers the whole output, so "UI or backdrop?" cannot be answered by geometry — every point is inside the window. It is answered by `Gtk.Widget.pick()` (GTK's own event-targeting call) followed by an ancestor walk looking for a **content marker** CSS class: `SOLID_CSS_CLASSES = {"panel", "nav-bar"}` in `panels/root.py`.

- **Give any new screen's visible container the `panel` class.** All four existing panels already have it, so a screen following the convention gets click-to-dismiss for free. A screen styled only with a variant class (`.my-panel`, no `.panel`) would fall through and dismiss when clicked — there is a regression test for exactly that.
- **Press *and* release must both land on backdrop.** Otherwise dragging a bookmark out of its panel and releasing over the blur would close the launcher mid-reorder.
- **BUBBLE phase**, so buttons/rows/entries claim their own clicks first and this only sees what nothing else wanted.
- A screen can opt out with `dismiss_on_outside_click = False`.
- `pick()` returning `None` is treated as **content, not backdrop** — on a mapped full-screen window every click has a target, so `None` is an anomaly, and the conservative guess avoids a broken pick closing the launcher on every click. Note this also means `pick()` yields `None` for everything on a window that was never mapped, which is why the hit test cannot be exercised in the headless suite (the ancestor-walk half is covered by `tests/test_click_dismiss.py`).

### Elephant Integration (`launcher/services/elephant.py`)

Ignis has **no** clipboard, file-search or emoji support (grepping the package for `clipboard`, `wl-copy` and `emoji` returns nothing). Those three come from [elephant](https://github.com/abenz1267/elephant), Walker's provider daemon, which is already installed here. The other five elephant providers (`calc`, `desktopapplications`, `websearch`, `runner`, `providerlist`) duplicate existing Ignomi handlers and are deliberately **not** used.

**Transport is the `elephant` CLI, not the raw socket** — `elephant query` is documented and stable, the wire format is not. `ignis.utils.socket` is available if this ever needs to be faster; the measurements below say it doesn't.

Protocol (verified against elephant 2.22.0 — all semicolon-separated positional strings, *not* flags):

```bash
elephant query --json "<providers>;<query>;<limit>[;exactsearch]"   # NDJSON out, one item per line
elephant activate "<provider>;<identifier>;<action>;;"              # exactly FIVE fields
```

- **Output is NDJSON, not a JSON array.** Parse line by line.
- **`activate` needs five fields.** Fewer and the CLI *panics* with a Go index error instead of printing usage. `ElephantClient.activate` builds this; there is a test asserting the exact string.
- Actions: `symbols` → `run_cmd`; `clipboard` → `copy`/`edit`/`pin`/`remove`; `files` → `open`/`opendir`/`copyfile`/`copypath`.

**The daemon is not a systemd unit.** It runs detached (PPID 1); `systemctl --user list-unit-files` has no elephant entry unless you run `elephant service enable`. `ElephantClient.is_available()` checks for the socket at `$XDG_RUNTIME_DIR/elephant/elephant.sock`, and every method degrades to empty/False with a log line rather than raising.

**Do not run a second `elephant` process to test.** A transient instance takes over the socket and *deletes it on exit*, leaving the already-running daemon alive but unreachable (this broke Walker mid-session once). Query the existing daemon instead.

Measured latency on this machine (median of 5): clipboard 6.5 ms, symbols 10.5 ms, files 66.2 ms. The search router is synchronous, so these block the GTK main thread — which is why **file search sits behind the explicit `f:` prefix**. Ordinary typing never reaches elephant.

### Shortcuts Screen (`launcher/screens/shortcuts.py`)

The in-launcher cheat sheet, and it is **generated, not written**: prefixes come from the live `QueryRouter` registry, panels from the live `ScreenManager` registry. A handler documents itself with three optional attributes, read via `getattr`:

```python
prefixes = [":"]                                  # omit for keyword/fallback handlers
description = "Emoji and unicode symbols"
example = ":smile"
```

Add a handler and it appears here automatically — there is a test (`test_a_newly_registered_handler_needs_no_edit_here`) pinning that property. The one hand-maintained part is `KEY_BINDINGS`, since key handling is spread across `RootPanel` and each screen's `on_key_press` with no registry to read.

### Systemd Screen (`launcher/screens/systemd.py`)

- Units come from `launcher/data/systemd.toml` (array-of-tables: `unit`, optional `description` / `bus` / `icon`). **Never** call `SystemdService.units` — it resolves every unit file on the bus via one synchronous `LoadUnit` D-Bus round-trip each (1000+ blocking calls; the launcher would freeze).
- Units resolve **lazily on first `on_enter()`**, never at construction, so launcher startup does no D-Bus work.
- Live state via `notify::is-active` connected once per unit at resolve time; rows are rebuilt on filter, units are not.
- `bus = "system"` units need polkit authorization to act on. Session units need none.
- **Gotcha (verified against the real bus):** `get_unit()` does NOT raise for a unit that doesn't exist — the manager returns a stub with `is_active = False`, so a typo in `systemd.toml` looks like a merely-stopped service. The `start()`/`stop()`/`restart()` call *does* raise (`org.freedesktop.systemd1.NoSuchUnit`), so the screen marks the unit unavailable on that first failed action.

### Animation Architecture

- **All panel animations are GTK Revealers**, internal to the single launcher window. Bookmarks → `slide_right` (200 ms), search → `crossfade` (200 ms), frequent → `slide_left` (200 ms). Backdrop runs its blur frame stream on the underlying `widgets.Picture`.
- **Iron rule still applies**: never apply Hyprland `layerrule animation` to the launcher namespace AND a GTK Revealer to a child — that produced the original dual-animation conflict (z-note `[[20260225T072152714557306660]]`). Today we don't, because we have one Layer Shell window with no layerrules.
- `close_launcher()` (`launcher/utils/helpers.py`) calls `RootPanel.close()`, which unreveals all three Revealers in parallel, runs the backdrop reverse blur, and hides the window when the backdrop's `on_done` callback fires.

### Search Router Subsystem (`launcher/search/`)

The search panel does not run app filtering directly. Queries are routed through a priority-ordered handler pipeline:

```
launcher/search/
├── router.py              # QueryRouter, ResultItem dataclass, SearchHandler Protocol
└── handlers/
    ├── controls.py        # SystemControlsHandler   priority 50   (volume / brightness widgets)
    ├── calculator.py      # CalculatorHandler       priority 100  ("=" prefix, simpleeval)
    ├── symbols.py         # SymbolsHandler          priority 150  (":" prefix, elephant symbols)
    ├── web_search.py      # WebSearchHandler        priority 200  ("?", "g:", "w:", "gh:", "yt:" prefixes)
    ├── files.py           # FilesHandler            priority 250  ("f:" prefix, elephant files)
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

### Cross-Panel Communication

1. **GObject signals**: `FrecencyService` emits `changed` → `FrequentPanel._refresh_apps`.
2. **RootPanel singleton**: `add_bookmark_with_refresh()` (`utils/helpers.py`) reaches the bookmarks panel via `RootPanel.get_default().bookmarks_panel.refresh_from_disk()`. No more `IgnisApp.get_window(...)` reach-throughs.
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
- Toggles the single `ignomi-launcher` window via `RootPanel.get_default()`.
- Must run **inside** the Ignis process — `wlr-layer-shell` fixes the output at surface creation, so `window.monitor` must be set BEFORE `set_visible(True)`.
- Open path: rebind monitor, then `window.set_visible(True)`. Close path: `RootPanel.close()`, which orchestrates the parallel unreveal + backdrop reverse-blur + final `set_visible(False)`.
- `scripts/toggle-launcher.sh` is a one-line wrapper: `ignis run-python "from utils import toggle_launcher; toggle_launcher()"`.

### Configuration Files

| File | Purpose |
|------|---------|
| `launcher/data/settings.toml` | `[launcher]` (close_delay_ms), `[frecency]` (max_items, min_launches), `[search]` (max_results, fuzzy_threshold), `[animation]` (transition_duration). **No `[panels]` or `[backdrop]` section** — panel widths and per-monitor blur are hard-coded. |
| `launcher/data/bookmarks.json` | Seed bookmarks. Migrated to `~/.local/share/ignomi/bookmarks.json` on first run; the in-repo file is read once. |
| `launcher/data/commands.toml` | User-defined `!`-prefixed commands consumed by `CustomCommandsHandler`. |
| `launcher/data/systemd.toml` | Curated unit list for `SystemdScreen` (array-of-tables: `unit`, `description`, `bus`, `icon`). |
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

### Ignis enum properties round-trip as strings, not enums

`BaseWidget.override_enum` makes `set_property` accept a lowercase string (`transition_type="crossfade"` → `Gtk.StackTransitionType.CROSSFADE` via `getattr(enum, value.upper())`). The **getter** is asymmetric: it returns `value_nick`, i.e. the *string*. So:

```python
label.get_ellipsize() == Pango.EllipsizeMode.NONE   # always False!
label.get_ellipsize() == "none"                     # correct
```

This bit a verification probe, which reported 14 correctly-configured labels as broken. Compare against the string (or accept both) for any overridden enum: `ellipsize`, `wrap_mode`, `justify`, `transition_type`, `valign`/`halign`.

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

- 273 tests, 1 skipped (the cage smoke test) as of the elephant sprint.
- Fixtures in `tests/conftest.py`: `tmp_db`, `tmp_bookmarks`, `tmp_settings`, `tmp_commands`, `tmp_systemd_config` — each creates a real file in `tmp_path`, no filesystem mocking.
- **The system `python3` cannot run the suite** — it has no `toml`. Use the Ignis venv: `~/.local/share/pipx/venvs/ignis/bin/python -m pytest tests/ -v`.
- `ruff` is not installed locally; `uvx ruff check launcher/` works. Two pre-existing `I001` import-order errors in `panels/backdrop.py` and `panels/search.py:278` are known and untouched.
- **Headless-import-mock pattern**: `test_app_search.py`, `test_bookmarks.py`, and `test_frecency.py` install `MagicMock` modules into `sys.modules` for `gi`, `gi.repository`, `ignis`, `ignis.widgets`, and `ignis.services.*` BEFORE importing the modules under test. This lets the suite run on a headless box (CI, remote shell) with no display server.
- Only mock these specific surfaces: `time.time()`, `GObject.emit`, `BaseService.__init__`, `ApplicationsService.apps`. Real file I/O exercises real bugs.

**Covered as of A1 sprint (2026-05):**
- `SystemControlsHandler` matches/get_results + audio/backlight availability gates → `tests/test_controls.py`
- `_ease_in_intervals` pure function (validates the quadratic curve fix) → `tests/test_backdrop_pure.py`
- `launch_app` happy + failure paths (validates the N17 fix) → `tests/test_helpers_lifecycle.py`
- `_bookmarks_path` XDG migration → `tests/test_helpers_xdg.py`
- `get_monitor_under_cursor` / `hyprland_monitor_to_ignis_monitor` → `tests/test_monitor_helpers.py`

**Covered as of the screens sprint (2026-08):**
- `ScreenManager` registry, nav-bar generation, switching, lifecycle-hook failure isolation, key routing → `tests/test_screens.py` (25 tests)
- `load_unit_configs` parsing + `SystemdScreen` actions, toggle, status dots, filtering, D-Bus error humanising → `tests/test_systemd_screen.py` (38 tests)
- `is_background_target` content-vs-backdrop hit testing for click-to-dismiss → `tests/test_click_dismiss.py` (14 tests)

**Covered as of the elephant sprint (2026-08):**
- `ElephantClient` NDJSON parsing, availability gating, command construction, every failure mode → `tests/test_elephant.py` (22 tests). Fixtures are verbatim captures from the live daemon.
- `SymbolsHandler` / `FilesHandler` match discipline, result mapping, activation → `tests/test_elephant_handlers.py` (28 tests)
- `ShortcutsScreen` registry-driven generation, including the anti-staleness property → `tests/test_shortcuts_screen.py` (15 tests)

**Still uncovered (real test debt):**
- `backdrop.py` everything except `_ease_in_intervals` (PIL pipeline, generation counter, frame streaming, threaded capture)
- `BookmarksPanel` / `SearchPanel` / `FrequentPanel` constructors and signal wiring
- `RootPanel` open/close orchestration
- `toggle_launcher()` / `close_launcher()` integration (the new RootPanel singleton path)
- `HomeScreen.create_widget()` end-to-end — it constructs `BookmarksPanel`, whose context menu calls `IgnisMenuItem`, which requires a fully initialized `IgnisApp`. It therefore cannot be built outside the running daemon, which is also why no test constructs a real `RootPanel`.

There's also an opt-in cage smoke test at `tests/test_cage_smoke.py` — only runs if `cage`, `ignis`, and `wayland-info` are on PATH.

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
