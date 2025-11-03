# Ignomi Launcher - Design Document
**Date:** 2025-11-02
**Status:** Implementation In Progress
**Version:** 1.0

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
- Multi-monitor independent launcher instances
- Custom desktop entry editing
- Application categories/folders
- Thumbnail previews
- Web search integration
- Plugin system

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
Widget.Window(
    namespace="ignomi-bookmarks",
    monitor=0,
    anchor=["left", "top", "bottom"],
    exclusive=True,  # Reserves screen space
    keyboard_mode="none",  # No keyboard focus
    layer="top"
)

# Search Panel (Center)
Widget.Window(
    namespace="ignomi-search",
    monitor=0,
    anchor=["top"],
    exclusive=False,  # Floating (doesn't reserve space)
    keyboard_mode="exclusive",  # Gets all keyboard input
    layer="top"
)

# Frequent Panel (Right)
Widget.Window(
    namespace="ignomi-frequent",
    monitor=0,
    anchor=["right", "top", "bottom"],
    exclusive=True,
    keyboard_mode="none",
    layer="top"
)
```

**Toggle Behavior:**
- Hyprland keybind: `Mod+Space → ignis open-window ignomi`
- All three windows share "ignomi" namespace prefix
- Ignis shows/hides all matching windows together
- Search panel automatically receives keyboard focus

### Data Flow

**Launch Sequence:**
1. User clicks app in any panel
2. `ApplicationsService.launch(app.id)` executes
3. `FrecencyService.record_launch(app.id)` increments counter
4. Visual feedback (brief highlight)
5. GLib.timeout_add(300ms) schedules auto-close
6. Launcher closes after delay

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
class FrecencyService(Service):
    # Signals
    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    # Methods
    def record_launch(self, app_id: str) -> None
    def get_top_apps(self, limit: int = 12) -> List[Tuple[str, float, int, int]]
    def _calculate_frecency(self, launch_count: int, last_launch: int) -> float
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
    "Alacritty.desktop",
    "code.desktop",
    "nemo.desktop",
    "discord.desktop",
    "spotify-launcher.desktop"
  ]
}
```

**Drag-Drop Implementation:**
```python
# Each app button gets:
drag_source = Gtk.DragSource()
drag_source.set_actions(Gdk.DragAction.MOVE)
drag_source.connect("prepare", on_drag_prepare)
button.add_controller(drag_source)

drop_target = Gtk.DropTarget()
drop_target.set_gtypes([GObject.TYPE_STRING])
drop_target.connect("drop", on_drop)
button.add_controller(drop_target)
```

### Search Panel (panels/search.py)

**Responsibility:** Filter and display all installed applications

**Features:**
- Search Entry widget for user input
- Real-time filtering via ApplicationsService.search()
- Display results with icons + labels
- Right-click to add to bookmarks
- Keyboard navigation (arrow keys, Enter to launch)

**Search Implementation:**
```python
self.entry = Widget.Entry(
    placeholder_text="Search applications...",
    on_change=lambda x: self._on_search()
)

def _on_search(self):
    query = self.entry.text
    if query:
        results = self.apps_service.search(
            self.apps_service.apps,
            query
        )
    else:
        results = self.apps_service.apps[:20]  # Default top 20

    self._update_results_display(results)
```

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
    """
    Launch app, record in frecency, close launcher after delay
    """
    # Launch the application
    app.launch()

    # Record in frecency
    frecency_service.record_launch(app.id)

    # Schedule auto-close
    GLib.timeout_add(close_delay_ms, lambda: close_launcher())

def close_launcher():
    """Close all ignomi windows"""
    from ignis.app import IgnisApp
    app = IgnisApp.get_default()

    # Close all ignomi-* windows
    for window in app.get_windows():
        if window.namespace.startswith("ignomi-"):
            window.hide()

    return False  # Don't repeat timeout
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
```css
/* Panel backgrounds */
.panel {
    background-color: alpha(@bg, 0.95);
    color: @fg;
    border-radius: 12px;
    padding: 16px;
}

/* App list items */
.app-item {
    background-color: transparent;
    border-radius: 6px;
    padding: 12px;
    margin: 4px 0;
    transition: all 0.1s ease;
}

.app-item:hover {
    background-color: alpha(@accent, 0.3);
}

.app-item:active {
    background-color: alpha(@accent, 0.5);
    transform: scale(0.98);
}

/* Drag-drop feedback */
.app-item.drag-hover {
    border-top: 2px solid @accent;
}

/* Right-click confirmation */
@keyframes bookmark-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; background-color: alpha(@success, 0.5); }
}

.bookmark-added {
    animation: bookmark-pulse 0.3s ease;
}

/* Search panel specific */
.search-panel .entry {
    font-size: 16px;
    padding: 12px 16px;
    margin-bottom: 8px;
}

.search-results {
    max-height: 600px;
}

/* Frecency badges */
.frecency-count {
    font-size: 10px;
    color: alpha(@fg, 0.6);
    margin-top: 4px;
}
```

### Wallust Integration

**Template Location:** `~/.config/wallust/templates/ignomi.css`

**Template Content:**
```css
/* Generated by Wallust from current wallpaper */
@define-color bg {{background}};
@define-color fg {{foreground}};
@define-color accent {{color3}};
@define-color success {{color2}};
@define-color warning {{color1}};
@define-color error {{color5}};
```

**Wallust Configuration (wallust.toml):**
```toml
[templates]
ignomi_colors = {
    template = "ignomi.css",
    target = "/home/komi/.config/ignomi/colors.css"
}
```

**Loading in Ignis:**
```python
from ignis.app import IgnisApp

app = IgnisApp.get_default()
app.apply_css("/home/komi/.config/ignomi/styles/colors.css")
app.apply_css("/home/komi/repos/ignomi/launcher/styles/main.css")
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
decay_enabled = false   # Future: time-based score decay
```

### Hyprland Integration

**Keybinding (hypr/config/keybinds.conf):**
```conf
# Replace old launcher
bindd = $mainMod, SPACE, Launch Ignomi three-panel launcher, exec, ignis open-window ignomi
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
# Usage: track-launch.sh firefox.desktop

if [ $# -eq 0 ]; then
    echo "Usage: $0 <app-id>"
    echo "Example: $0 firefox.desktop"
    exit 1
fi

APP_ID="$1"

python3 <<EOF
import sys
sys.path.insert(0, '/home/komi/repos/ignomi/launcher')

from services.frecency import FrecencyService

service = FrecencyService()
service.record_launch("$APP_ID")
print(f"Recorded launch: $APP_ID")
EOF
```

**Make executable:**
```bash
chmod +x ~/repos/ignomi/scripts/track-launch.sh
```

**Usage:**
```bash
# Track app launched outside launcher
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

1. **Single Monitor:** Launcher shows on primary monitor only
2. **No Categories:** All apps in flat list (sorted by search relevance)
3. **No Thumbnails:** Icon-only, no window previews
4. **No History:** Frecency only, no launch history view
5. **Manual Tracking:** External launches not auto-tracked (use CLI tool)

## Future Enhancements (Post-MVP)

### Phase 2 Features
- Keyboard shortcuts (Tab to switch panels)
- Category filters (Dev, Media, Utils, etc.)
- Custom icons per bookmark
- Usage statistics view
- Export/import bookmarks

### Phase 3 Features
- Multi-monitor support
- Window previews for running apps
- Quick actions (right-click menu)
- System-wide launch tracking via D-Bus
- Fuzzy search algorithm tuning

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

**Document Version:** 1.0
**Last Updated:** 2025-11-02
**Author:** Claude Code (with user collaboration)
**Status:** Living document - will be updated during implementation
