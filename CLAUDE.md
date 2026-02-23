# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Launching Ignomi

### Prerequisites
- Ensure Ignis is installed via `pipx install ./ignis`
- Config symlink should point to master branch: `ln -sf ~/repos/ignomi/launcher/config.py ~/.config/ignis/config.py`

### Launch Process

1. **Initialize Ignis daemon** (if not already running):
   ```bash
   ignis init &
   ```

2. **Open all three launcher panels**:
   ```bash
   ignis open-window ignomi-bookmarks && ignis open-window ignomi-search && ignis open-window ignomi-frequent
   ```

### Development Commands

- `ignis list-windows` - List all available windows
- `ignis reload` - Reload configuration after making code changes
- `ignis quit` - Stop the Ignis daemon
- `journalctl -f | grep ignis` - View live Ignis logs for debugging

### Common Launch Issues
- **"Ignis is not running"**: Run `ignis init &` first
- **"No such window: ignomi"**: Use the individual window names (ignomi-bookmarks, ignomi-search, ignomi-frequent), not "ignomi"
- **Config not loading**: Ensure symlink points to `/home/komi/repos/ignomi/launcher/config.py` (not a worktree)

## Architecture Overview

### Three-Panel Design

Ignomi is a Wayland application launcher built with the Ignis framework (GTK4 + Layer Shell). It consists of three independent panels that run in a single process:

1. **Bookmarks Panel** (`launcher/panels/bookmarks.py`) - Left panel
   - User-curated favorites loaded from `launcher/data/bookmarks.json`
   - Drag-and-drop reordering support
   - Right-click to remove from bookmarks

2. **Search Panel** (`launcher/panels/search.py`) - Center panel
   - Real-time application filtering using `ApplicationsService.search()`
   - Keyboard navigation (arrow keys, Enter to launch, Escape to close)
   - Auto-focus search entry with cursor positioning via `hyprctl dispatch movecursor`
   - Right-click to add apps to bookmarks
   - **Auto-selects first result by default** for faster keyboard launching

3. **Frequent Panel** (`launcher/panels/frequent.py`) - Right panel
   - Displays apps ranked by Firefox-style frecency algorithm
   - Updates reactively via GObject signals from FrecencyService

### Key Services

**FrecencyService** (`launcher/services/frecency.py`):
- Tracks app launches in SQLite database (`~/.local/share/ignomi/app_usage.db`)
- Implements Firefox frecency algorithm: `score = launch_count × recency_weight`
- Recency weights: 100x (<4 days), 70x (<14 days), 50x (<31 days), 30x (<90 days), 10x (90+ days)
- Emits `changed` signal when usage data updates, triggering UI refresh

### Cross-Panel Communication

Panels communicate via:
1. **GObject Signals**: FrecencyService emits `changed` signal → frequent panel refreshes
2. **Direct Panel Access**: Search panel can call `bookmarks_panel.refresh_from_disk()` after adding bookmarks
3. **Shared Services**: All panels use singleton instances (`get_frecency_service()`, `ApplicationsService.get_default()`)

### Configuration Files

- `launcher/data/settings.toml` - Panel dimensions, close delay, frecency settings
- `launcher/data/bookmarks.json` - Initial bookmarked apps (auto-saved on changes)
- `launcher/styles/main.css` - Main GTK4 styles
- `launcher/styles/colors.css` - Wallust-generated dynamic colors (symlinked from `~/.config/ignomi/colors.css`)

### Entry Point

**launcher/config.py**:
- Main Ignis configuration file (symlinked to `~/.config/ignis/config.py`)
- Creates all three panel instances
- Loads CSS styling (colors.css from Wallust, main.css for structure)
- Uses dynamic path resolution via `os.path.realpath(__file__)`
- **IMPORTANT**: `bookmarks.py` and `frequent.py` contain hardcoded `sys.path.insert` paths assuming project is at `/home/komi/repos/ignomi`

## Critical Implementation Details

### GTK4 Layer Shell Transparency

**REQUIRED for transparency on Wayland Layer Shell windows:**

```css
window {
    background: transparent;
}
```

This must be set at the window level, not just on child widgets. See `project-docs/research/gtk4-layer-shell-transparency.md` for full details.

### GTK4 CSS Variable Limitations

GTK4 CSS parser **cannot** use `alpha()` function with `@define-color` variables:

```css
/* DOES NOT WORK */
@define-color bg #1a1a1a;
.panel { background: alpha(@bg, 0.9); }

/* WORKS - pre-compute alpha in Wallust template */
@define-color bg_90 rgba(26, 26, 26, 0.9);
.panel { background: @bg_90; }
```

Variables resolve at parse time, not runtime. Alpha variants must be pre-computed in the Wallust template.

### Wallust Template Variables

Available in `~/.config/wallust/templates/ignomi.css`:
- `{{background}}`, `{{foreground}}` - Main colors
- `{{color0}}` through `{{color15}}` - Palette colors
- Does NOT provide: `{{accent}}`, `{{success}}`, etc. (must map to color indices manually)

### Monitor Detection

All panels use `get_monitor_under_cursor()` to position on the monitor where the cursor is located when the launcher opens. This uses:
1. `hyprctl cursorpos` to get cursor position (plain text "x, y" format, NOT JSON)
2. `hyprctl monitors -j` to find which monitor contains that position (JSON)
3. GTK monitor index mapping via connector name matching (`hyprland_monitor_to_ignis_monitor()`)

### Auto-Close Behavior

After launching an app, panels auto-close after `close_delay_ms` (default 300ms) via `GLib.timeout_add()`. Delay is configurable in `settings.toml`.

## Testing & Debugging

### Testing Frecency Tracking

```bash
# Manually track app launch
~/repos/ignomi/scripts/track-launch.sh firefox.desktop

# Inspect database
sqlite3 ~/.local/share/ignomi/app_usage.db "SELECT * FROM app_stats ORDER BY last_launch DESC;"
```

### Debugging Styling Issues

1. Check CSS files are loading: Look for warnings in `journalctl -f | grep ignis`
2. Verify symlinks exist:
   ```bash
   ls -la ~/repos/ignomi/launcher/styles/colors.css
   ls -la ~/.config/ignis/config.py
   ```
3. Test with known-good colors: Replace `@define-color` variables with hardcoded values
4. Use GTK Inspector: `ignis inspector` (while Ignis is running)

### Common Debugging Pitfalls

- **Changing multiple things at once**: Change one variable at a time
- **Forgetting to reload**: Run `ignis reload` after CSS/Python changes
- **Wrong monitor**: Verify monitor index in panel window definitions matches your setup
- **Path assumptions**: Check hardcoded `sys.path.insert` in `bookmarks.py` and `frequent.py` if cloned to non-standard location

See `project-docs/discoveries/systematic-debugging-phase1-theming.md` for systematic debugging methodology.

## Project Documentation

Comprehensive documentation in `project-docs/`:

- `architecture/` - Design documents, component structure, architectural decisions
- `research/` - Technical investigations (GTK4 transparency, CSS limitations, Wallust integration)
- `discoveries/` - Debugging processes, lessons learned, development insights
- `status/` - Milestone completions, progress tracking

**Most critical references:**
- `project-docs/research/gtk4-layer-shell-transparency.md` - GTK4 transparency patterns (essential for any GTK4 Layer Shell work)
- `project-docs/architecture/2025-11-02-ignomi-launcher-design.md` - Original design document with rationale for architectural choices
