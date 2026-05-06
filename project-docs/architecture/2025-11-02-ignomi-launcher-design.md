# Ignomi Launcher - Design Document
**Date:** 2025-11-02
**Status:** Implemented (all success criteria met)
**Version:** 2.1

> **Document History:** This document was originally written as a pre-implementation
> specification on 2025-11-02. Updated 2026-02-23 to match the implemented codebase.
> All code examples, API signatures, CSS patterns, and known limitations have been
> verified against the actual source files. Where the original spec diverged from
> implementation decisions made during development, the document now reflects reality.

> **As-of 2025-11-02 with addenda for:**
> - **Search router** (commit `94b83cf`) — see
>   [`2026-04-30-search-router-architecture.md`](./2026-04-30-search-router-architecture.md)
> - **Backdrop blur pipeline** (commit `b460826`) — see
>   [`2026-04-30-backdrop-blur-pipeline.md`](./2026-04-30-backdrop-blur-pipeline.md)
> - **Multi-monitor backdrop fix** (commit `857767e`) — covered in the
>   backdrop pipeline doc (PIL thread safety section)
> - **Animation architecture reconciliation** (search-panel exception) —
>   see [`2026-04-30-animation-architecture.md`](./2026-04-30-animation-architecture.md)
>
> Where this doc and the addenda disagree, **the addenda are correct**.
> Sections in this doc that are now obsolete are marked inline with
> "Updated YYYY-MM-DD" callouts.

## Executive Summary

Ignomi is a three-panel application launcher built with the Ignis framework (Python + GTK4) for Wayland compositors. It replaces a previous GTK4 + Rofi implementation that suffered from fundamental pointer grab incompatibilities.

**Problem Solved:** Rofi's global pointer grab prevents side GTK4 panels from receiving click events, making a three-panel layout impossible with Rofi at the center.

**Solution:** Use Ignis to build all three panels as coordinated windows under a single process, eliminating external pointer grab issues.

## Design Goals

### Primary Objectives
1. **Working Three-Panel Layout** - Bookmarks (left), search (center), frequent apps (right) all simultaneously interactive
2. **No Input Grabbing** - All panels clickable at the same time without pointer/keyboard conflicts
3. **Frecency Tracking** - Learn which apps users launch most frequently over time
4. **Dynamic Bookmarks** - Right-click to add/remove, drag-and-drop to reorder
5. **Wallust Integration** - Dynamic colors from current wallpaper

### Non-Goals (YAGNI)
- Custom desktop entry editing
- Application categories/folders
- Thumbnail previews
- Plugin system

> **Update 2026-04-30:** "Web search integration" was removed from the
> non-goals list — it is now implemented. The `WebSearchHandler`
> (`launcher/search/handlers/web_search.py`, priority 200, registered in
> `SearchPanel.__init__`) supports `?` (default engine), `g:` (Google),
> `w:` (Wikipedia), `gh:` (GitHub), and `yt:` (YouTube) prefixes, opening
> via `xdg-open`. See the
> [search router architecture doc](./2026-04-30-search-router-architecture.md)
> for the full handler registry.

## User Experience Flow

1. **Launch:** Press Mod+Space → Three panels appear instantly
2. **Search:** Type in center panel → Results filter in real-time
3. **Select:** Click app from any panel → App launches
4. **Auto-Close:** After 0.3s delay → Panels disappear
5. **Learn:** Frequent panel updates based on usage patterns

### Bookmark Management
- **Add:** Right-click app in search/frequent → Instantly added to bookmarks
- **Remove:** Right-click app in bookmarks → Instantly removed
- **Reorder:** Drag-and-drop apps in bookmarks panel
- **Visual Feedback:** Brief highlight/pulse animation on actions

### Keyboard Navigation
- **Focus:** Search panel gets exclusive keyboard focus
- **Typing:** Filters search results
- **Arrow Keys:** Navigate within search results
- **Enter:** Launch selected app
- **Escape:** Close launcher
- **Bookmarks/Frequent:** Mouse-only (design decision for simplicity)

## Architecture

### Technology Stack
- **Framework:** Ignis 0.5+ (Python + GTK4 + Layer Shell)
- **Language:** Python 3.13+
- **GUI:** GTK4 via Ignis Widget API
- **Positioning:** Wayland Layer Shell Protocol
- **Database:** SQLite for frecency tracking
- **Configuration:** TOML + JSON
- **Styling:** GTK4 CSS with Wallust integration

### System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Ignis Process                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  Bookmarks   │  │    Search    │  │   Frequent   │ │
│  │    Panel     │  │    Panel     │  │    Panel     │ │
│  │  (Widget.    │  │  (Widget.    │  │  (Widget.    │ │
│  │   Window)    │  │   Window)    │  │   Window)    │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│         │                 │                  │         │
│         └─────────────────┴──────────────────┘         │
│                           │                            │
│              ┌────────────┴────────────┐               │
│              │                         │               │
│        ┌─────▼─────┐           ┌──────▼──────┐        │
│        │ Applications│         │  Frecency   │        │
│        │   Service   │         │   Service   │        │
│        │  (Ignis)    │         │  (Custom)   │        │
│        └─────────────┘         └─────────────┘        │
│              │                        │                │
│              │                        ▼                │
│              │                  ┌──────────┐           │
│              │                  │ SQLite   │           │
│              │                  │ Database │           │
│              │                  └──────────┘           │
│              ▼                                         │
│        ┌──────────────┐                                │
│        │ Desktop      │                                │
│        │ Entries      │                                │
│        │ (/usr/share/ │                                │
│        │ applications)│                                │
│        └──────────────┘                                │
└─────────────────────────────────────────────────────────┘
```

### Window Management

**Three Independent Windows (Coordinated Show/Hide):**

```python
# Bookmarks Panel (Left)
# Updated 2026-04-30 — exclusivity changed from "exclusive" to "ignore",
# layer changed from "top" to "overlay". This was part of the search-panel
# drift fix (the centered search panel was destabilized by sibling exclusive
# zones). See 2026-04-30-animation-architecture.md.
# Citation: launcher/panels/bookmarks.py:108-110.
widgets.Window(
    namespace="ignomi-bookmarks",
    monitor=get_monitor_under_cursor(),
    anchor=["left", "top", "bottom"],
    exclusivity="ignore",     # All surfaces "ignore" — no exclusive zones
    kb_mode="on_demand",      # Allow mouse interaction
    layer="overlay",          # Above the backdrop layer
    default_width=320,
    visible=False,
    margin_top=8, margin_bottom=8, margin_left=8
)

# Search Panel (Center)
# Updated 2026-04-30 — exclusivity changed from "normal" to "ignore",
# layer changed from "top" to "overlay". See animation architecture doc
# for the full rationale (centered surfaces drift laterally when
# sibling exclusive zones change). Citation: launcher/panels/search.py:140-153.
widgets.Window(
    namespace="ignomi-search",
    monitor=get_monitor_under_cursor(),
    anchor=["top", "bottom"],
    exclusivity="ignore",     # Ignore other surfaces' exclusive zones (drift fix)
    kb_mode="on_demand",
    layer="overlay",          # Above edge panels' "top" layer
    default_width=600,
    visible=False,
    margin_top=8, margin_bottom=8,
    child=centered,           # GTK Revealer wrapped in centering Box (see anim doc)
)

# Frequent Panel (Right)
# Updated 2026-04-30 — same migration as bookmarks above:
# exclusivity "exclusive" → "ignore", layer "top" → "overlay".
# Citation: launcher/panels/frequent.py:131-133.
widgets.Window(
    namespace="ignomi-frequent",
    monitor=get_monitor_under_cursor(),
    anchor=["right", "top", "bottom"],
    exclusivity="ignore",
    kb_mode="on_demand",
    layer="overlay",
    default_width=320,
    visible=False,
    margin_top=8, margin_bottom=8, margin_right=8
)
```

**Toggle Behavior:**

> **Update 2026-04-30:** the parallel-toggle approach below was replaced
> by a single atomic `ignis run-python` call in commit `b460826`. The
> current `scripts/toggle-launcher.sh` is one line:
>
> ```bash
> ignis run-python "from utils.helpers import toggle_launcher; toggle_launcher()"
> ```
>
> `toggle_launcher()` (in `launcher/utils/helpers.py:175-216`) runs inside
> the Ignis process: detects the cursor monitor while windows are still
> hidden, sets `.monitor` on every `ignomi-*` window, then flips
> visibility. wlr-layer-shell binds the surface's monitor at *creation*,
> so setting `.monitor` after `set_visible(True)` is too late — the
> per-panel `update_window_monitor()` approach below was the bug this
> change fixed. See zk-note `[[20260227T035401098076654606]]` for the
> full rationale.

- Hyprland keybind: `Mod+Space` runs `scripts/toggle-launcher.sh`
- Script issues a single `ignis run-python` call invoking `toggle_launcher()`
- `toggle_launcher()` sets `.monitor` on all panels **before** flipping
  visibility (atomic w.r.t. the GTK main loop)
- Search panel moves cursor to search entry after animation completes (300ms delay)

### Data Flow

**Launch Sequence:**
1. User clicks app in any panel
2. `launch_app(app, frecency_service, close_delay_ms)` in helpers.py orchestrates:
   a. `app.launch()` executes the application
   b. `frecency_service.record_launch(app.id)` increments counter
   c. `GLib.timeout_add(close_delay_ms, ...)` schedules auto-close
3. After delay, `close_launcher()` hides all `ignomi-*` windows

**Search Sequence:**
1. User types in search Entry widget
2. `on_change` callback fires
3. `ApplicationsService.search(apps, query)` filters results
4. Results box updated with filtered apps
5. Re-renders in real-time (no debouncing needed)

**Frecency Update:**
1. App launch triggers `FrecencyService.record_launch()`
2. SQLite UPDATE increments count, updates timestamp
3. Service emits GObject "changed" signal
4. Frequent panel listens to signal
5. Panel re-queries top apps
6. UI updates with new ranking

## Component Design

### FrecencyService (services/frecency.py)

**Responsibility:** Track app usage and calculate frecency scores

**Interface:**
```python
class FrecencyService(BaseService):  # ignis.base_service.BaseService
    __gtype_name__ = "FrecencyService"

    # Signals
    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    # Methods
    def record_launch(self, app_id: str) -> None
    def get_top_apps(self, limit: int = 12, min_launches: int = 1) -> List[Tuple[str, float, int, int]]
    def get_app_stats(self, app_id: str) -> Optional[Tuple[int, int, int]]
    def get_total_launches(self) -> int
    def clear_stats(self, app_id: Optional[str] = None) -> None
    def _calculate_frecency(self, launch_count: int, last_launch: int) -> float

# Singleton accessor (used by all panels and scripts)
def get_frecency_service() -> FrecencyService
```

**Frecency Algorithm (Firefox-Style):**
```python
age_days = (now - last_launch) / (24 * 3600)

if age_days < 4:    recency_weight = 100
elif age_days < 14: recency_weight = 70
elif age_days < 31: recency_weight = 50
elif age_days < 90: recency_weight = 30
else:               recency_weight = 10

frecency_score = launch_count * recency_weight
```

**Database Schema:**
```sql
CREATE TABLE app_stats (
    app_id TEXT PRIMARY KEY,
    launch_count INTEGER DEFAULT 0,
    last_launch INTEGER,  -- Unix timestamp
    created_at INTEGER
);

CREATE INDEX idx_frecency
ON app_stats(last_launch DESC, launch_count DESC);
```

**Location:** `~/.local/share/ignomi/app_usage.db` (XDG standard)

### Bookmarks Panel (panels/bookmarks.py)

**Responsibility:** Display and manage user-curated app list

**Features:**
- Load apps from `data/bookmarks.json`
- Display with icons + labels
- Right-click to remove from bookmarks
- Drag-and-drop reordering (GTK4 DragSource/DropTarget)
- Save changes back to JSON on modification

**Data Format (data/bookmarks.json):**
```json
{
  "bookmarks": [
    "firefox.desktop",
    "nemo.desktop",
    "spotify-launcher.desktop",
    "com.mitchellh.ghostty.desktop"
  ]
}
```

**Drag-Drop Implementation:**
```python
# Each app button gets DragSource + DropTarget controllers
drag_source = Gtk.DragSource()
drag_source.set_actions(Gdk.DragAction.MOVE)
drag_source.connect("prepare", lambda src, x, y, idx=index: self._on_drag_prepare(idx))
drag_source.connect("drag-begin", lambda src, drag: self._on_drag_begin())
button.add_controller(drag_source)

drop_target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
drop_target.connect("drop", lambda tgt, val, x, y, idx=index: self._on_drop(idx))
drop_target.connect("enter", lambda tgt, x, y: self._on_drop_enter(button))
drop_target.connect("leave", lambda tgt: self._on_drop_leave(button))
button.add_controller(drop_target)
```

### Search Panel (panels/search.py)

**Responsibility:** Dispatch user queries to a priority-ordered router of typed
search handlers and render the results.

> **Update 2026-04-30:** the panel no longer drives `ApplicationsService.search()`
> directly. It owns only the input field, results list, keyboard navigation,
> a 120ms debounce, and a close-guard. All search logic — calculator, web
> search, custom commands, system controls, and app filtering — lives in
> `launcher/search/`. See the
> [search router architecture doc](./2026-04-30-search-router-architecture.md)
> for the full design.

**Features:**
- Query router dispatches to typed handlers (priority-ordered)
- 120ms debounce on every keystroke
- Display results with icons + labels (or inline widgets for handlers like
  system controls)
- First row auto-selected after every search
- Right-click on app results to add to bookmarks
- Keyboard navigation (arrow keys, Enter to launch, Escape to close)

**Search Implementation (current shape — see `launcher/panels/search.py:92-99`):**

```python
self.search_entry = widgets.Entry(
    placeholder_text="Search applications...",
    css_classes=["search-entry"],
    on_change=lambda x: self._on_search_changed(),
)
self.search_entry.connect("activate", lambda entry: self._on_entry_activate())

def _on_search_changed(self):
    """Debounced search — waits 120ms after last keystroke."""
    if self._closing:
        return
    if self._debounce_timer is not None:
        GLib.source_remove(self._debounce_timer)
    self._debounce_timer = GLib.timeout_add(120, self._do_search)

def _do_search(self):
    """Execute the actual search query (called after debounce)."""
    self._debounce_timer = None
    query = self.search_entry.text if self.search_entry else ""
    self.current_handler, self.current_results = self.router.route(query)
    self._update_results()
    return False  # Don't repeat GLib timeout
```

The `widgets.Entry` `on_change`/`activate` pair replaces the older
`Widget.Entry` + ad-hoc `_on_search` shown in earlier revisions of this
document.

### Frequent Panel (panels/frequent.py)

**Responsibility:** Display apps ranked by frecency score

**Features:**
- Load top N apps from FrecencyService
- Connect to "changed" signal for auto-updates
- Display with icons + labels + usage count
- Right-click to add to bookmarks

**Auto-Update:**
```python
self.frecency.connect("changed",
                     lambda x: self._refresh_apps())

def _refresh_apps(self):
    top_app_data = self.frecency.get_top_apps(limit=12)
    # top_app_data = [(app_id, score, count, last_launch), ...]

    self.top_apps = []
    for app_id, score, count, _ in top_app_data:
        app = self._find_app_by_id(app_id)
        if app:
            self.top_apps.append((app, score, count))

    self._update_display()
```

### Shared Utilities (utils/helpers.py)

**App Launch Wrapper:**
```python
from gi.repository import GLib

def launch_app(app, frecency_service, close_delay_ms=300):
    """Launch app, record in frecency, close launcher after delay."""
    app.launch()
    frecency_service.record_launch(app.id)
    GLib.timeout_add(close_delay_ms, lambda: _close_launcher_callback())

def _close_launcher_callback() -> bool:
    """Callback for GLib.timeout_add."""
    close_launcher()
    return False  # Don't repeat
```

**Close Launcher (current — `launcher/utils/helpers.py:250-293`, ~lines 250-280):**

> **Update 2026-04-30:** `close_launcher()` is no longer a simple
> `set_visible(False)` loop over all `ignomi-*` windows. It now special-cases
> two namespaces:
>
> - **`ignomi-backdrop`** — runs the reverse-blur animation
>   (`window._start_close_animation`, exported by `panels/backdrop.py`)
>   before hiding. See
>   [backdrop blur pipeline doc](./2026-04-30-backdrop-blur-pipeline.md).
> - **`ignomi-search`** — calls `revealer.set_reveal_child(False)` to
>   trigger the GTK Revealer crossfade. The Revealer's
>   `notify::child-revealed` signal hides the window when the animation
>   completes. See
>   [animation architecture doc](./2026-04-30-animation-architecture.md).
> - **Bookmarks / frequent** — fall through to `set_visible(False)`;
>   Hyprland layerrules handle their slide animations.

```python
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


def _close_search_panel(window):
    """Close the search panel with GTK Revealer animation."""
    centering_box = window.get_child()
    if centering_box:
        revealer = centering_box.get_first_child()
        if revealer and hasattr(revealer, 'set_reveal_child'):
            revealer.set_reveal_child(False)
            return
    window.set_visible(False)
```

## Styling & Theming

### CSS Architecture

**File Structure:**
```
launcher/styles/
├── main.css         # Core styling
└── colors.css       # Wallust-generated (symlink)
```

**Main CSS (styles/main.css):**

> **Critical GTK4 limitation:** `alpha()` cannot be used with `@define-color`
> variables at runtime (e.g., `alpha(@bg, 0.65)` does NOT work). All alpha
> variants must be pre-computed in the Wallust template as literal hex values
> wrapped in `alpha()` (e.g., `@define-color bg_65 alpha(#292420, 0.65);`).

```css
/* Window must be transparent for RGBA backgrounds to work */
window, window.background, .background {
    background: transparent;
    background-color: transparent;
}

/* Panel backgrounds -- uses pre-computed @bg_65 (65% opacity) */
.panel {
    background-color: @bg_65;
    color: @fg;
    border-radius: 12px;
    border: none;
    box-shadow: none;
    padding: 16px;
}

/* App list items */
.app-item {
    background-color: transparent;
    border-radius: 8px;
    padding: 12px;
    margin: 2px 0;
    transition: all 0.15s ease;
}

.app-item:hover {
    background-color: @color4_30;  /* Pre-computed: alpha(#BE8F53, 0.30) */
    transform: translateX(2px);
}

.app-item:active {
    background-color: @color6_50;  /* Pre-computed: alpha(#BFAB70, 0.50) */
    transform: scale(0.98);
}

/* Search entry */
.search-entry {
    font-size: 16px;
    padding: 14px 18px;
    margin-bottom: 12px;
    border-radius: 8px;
    background-color: @bg_60;
    border: 1px solid @color4_40;
    transition: all 0.2s ease;
}

.search-entry:focus {
    border-color: @color6;
    background-color: @bg_80;
    box-shadow: 0 0 8px @color6_30;
}

/* Keyboard navigation highlight */
.keyboard-selected {
    background-color: @color6_40;
    border-left: 3px solid @color6;
}

/* Frecency badges */
.frecency-count {
    font-size: 10px;
    color: @fg_50;  /* Pre-computed: alpha(foreground, 0.50) */
    font-style: italic;
    margin-top: 4px;
}
```

### Wallust Integration

**Template Location:** `~/.config/wallust/templates/ignomi.css`

**Template Content (abridged -- 16 alpha variants in actual file):**
```css
/* Generated by Wallust from current wallpaper */
/* Base semantic colors */
@define-color bg {{background}};
@define-color fg {{foreground}};
@define-color accent {{color3}};
@define-color success {{color2}};
@define-color warning {{color1}};
@define-color error {{color5}};

/* Extended palette */
@define-color color0 {{color0}};
/* ... @color1 through @color8 ... */

/* Pre-computed alpha variants (GTK4 cannot use alpha() with @define-color vars) */
@define-color bg_65 alpha({{background}}, 0.65);
@define-color bg_75 alpha({{background}}, 0.75);
@define-color bg_60 alpha({{background}}, 0.60);
@define-color bg_80 alpha({{background}}, 0.80);
@define-color fg_70 alpha({{foreground}}, 0.70);
@define-color fg_50 alpha({{foreground}}, 0.50);
@define-color accent_30 alpha({{color3}}, 0.30);
@define-color color4_30 alpha({{color4}}, 0.30);
/* ... 16 total pre-computed variants ... */
```

**Loading in Ignis (config.py):**
```python
from ignis.app import IgnisApp
import os

app = IgnisApp.get_default()
# "user" priority (800) overrides global GTK4 CSS
styles_dir = os.path.join(config_dir, "styles")
app.apply_css(os.path.join(styles_dir, "colors.css"), style_priority="user")
app.apply_css(os.path.join(styles_dir, "main.css"), style_priority="user")
```

## Configuration

### Settings File (data/settings.toml)

```toml
[launcher]
close_delay_ms = 300  # Time before auto-close after launch

[panels]
bookmark_width = 300
frequent_width = 300
search_width = 500
search_height = 600

[frecency]
max_items = 12          # Number shown in frequent panel
min_launches = 2        # Minimum launches before appearing
```

### Hyprland Integration

**Keybinding (hypr/config/keybinds.conf):**
```conf
# Toggle launcher (runs toggle-launcher.sh which issues 3 toggle-window commands)
bindd = $mainMod, SPACE, Launch Ignomi three-panel launcher, exec, ~/repos/ignomi/scripts/toggle-launcher.sh
```

**Optional Window Rules:**
```conf
# Ensure launcher appears on all workspaces
windowrulev2 = pin, class:(ignis), title:(ignomi-.*)

# Blur background
layerrule = blur, ignomi-.*
layerrule = ignorealpha 0.3, ignomi-.*
```

## Manual Frecency Tracking

**CLI Tool (scripts/track-launch.sh):**
```bash
#!/usr/bin/env bash
# Track app launches for frecency outside the launcher
# Usage: track-launch.sh firefox.desktop

set -euo pipefail

if [ $# -eq 0 ]; then
    echo "Usage: $0 <app-id>"
    echo "Example: $0 firefox.desktop"
    exit 1
fi

APP_ID="$1"

python3 <<EOF
import sys
sys.path.insert(0, '/home/komi/repos/ignomi/launcher')

from services.frecency import get_frecency_service

service = get_frecency_service()
service.record_launch("$APP_ID")
print(f"Recorded launch: $APP_ID")
EOF
```

**Usage:**
```bash
~/repos/ignomi/scripts/track-launch.sh firefox.desktop
```

## Testing Strategy

### Manual Testing Checklist

**Phase 1: Basic Functionality**
- [ ] Mod+Space opens all three panels
- [ ] Search panel has keyboard focus
- [ ] Typing filters search results in real-time
- [ ] Clicking app in any panel launches it
- [ ] Launcher auto-closes after 0.3s

**Phase 2: Bookmarks Management**
- [ ] Right-click in search adds to bookmarks
- [ ] Right-click in frequent adds to bookmarks
- [ ] Right-click in bookmarks removes from bookmarks
- [ ] Bookmark pulse animation shows on add/remove
- [ ] Changes persist across launcher restarts

**Phase 3: Drag-and-Drop**
- [ ] Can drag bookmark app item
- [ ] Drop target shows visual indicator
- [ ] Dropping reorders bookmarks
- [ ] Order persists across restarts

**Phase 4: Frecency Tracking**
- [ ] Launching app updates frecency database
- [ ] Frequent panel shows most-used apps
- [ ] Recently launched apps rank higher
- [ ] Old apps decay in ranking (time-based)

**Phase 5: Styling**
- [ ] Wallust colors apply correctly
- [ ] Changing wallpaper updates launcher colors
- [ ] Hover states work on all buttons
- [ ] Animations smooth (no janky transitions)

## Known Limitations

1. **No Categories:** All apps in flat list (sorted by search relevance)
2. **No Thumbnails:** Icon-only, no window previews
3. **No History:** Frecency only, no launch history view
4. **Manual Tracking:** External launches not auto-tracked (use CLI tool)
5. **Hardcoded Path in bookmarks.py:** `sys.path.insert(0, '/home/komi/repos/ignomi/launcher')` -- other panels resolve dynamically

## Future Enhancements (Post-MVP)

### Potential Features
- Keyboard shortcuts (Tab to switch panels)
- Category filters (Dev, Media, Utils, etc.)
- Custom icons per bookmark
- Usage statistics view
- Export/import bookmarks
- Window previews for running apps
- System-wide launch tracking via D-Bus
- Fuzzy search algorithm tuning

### Already Implemented (Originally Planned as Future)
- **Multi-monitor support** -- `get_monitor_under_cursor()` in helpers.py positions panels on the monitor where the cursor is located when the launcher opens. Uses `hyprctl cursorpos` + `hyprctl monitors -j` with Hyprland-to-GTK monitor ID translation.
- **Right-click context menus** -- Bookmarks panel: "Remove from bookmarks". Frequent panel: "Remove from frequents", "Add to bookmarks". Search panel: direct bookmark add with pulse animation.

## Success Criteria

Project is considered successful when:

1. ✅ All three panels show simultaneously without input conflicts
2. ✅ Search filters apps in real-time
3. ✅ Apps launch from all three panels
4. ✅ Bookmarks can be managed via right-click
5. ✅ Bookmarks can be reordered via drag-drop
6. ✅ Frecency panel updates based on usage
7. ✅ Wallust colors integrate correctly
8. ✅ No crashes during normal usage
9. ✅ Performance acceptable (<100ms to show launcher)
10. ✅ Code is maintainable and documented

## References

- [Ignis Documentation](https://ignis-sh.github.io/ignis/stable/)
- [Ignis GitHub](https://github.com/linkfrg/ignis)
- [IgnisNiriShell Example](https://github.com/lost-melody/IgnisNiriShell)
- [Exo Desktop Shell](https://github.com/debuggyo/Exo)
- [GTK4 Documentation](https://docs.gtk.org/gtk4/)
- [Wayland Layer Shell Protocol](https://wayland.app/protocols/wlr-layer-shell-unstable-v1)

---

**Document Version:** 2.0
**Last Updated:** 2026-02-23
**Author:** Claude Code (with user collaboration)
**Status:** Reflects implemented codebase as of 2026-02-23
