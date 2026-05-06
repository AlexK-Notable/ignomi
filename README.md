# Ignomi

**Finally, a launcher where you can actually click all the panels.**

You wanted a multi-panel launcher. Bookmarks on the left, search in the middle, frecent apps on the right. Simple, right? Except Rofi grabs the pointer globally, so the moment your search panel opens, your side panels become furniture. Click all you want—nothing happens.

Ignomi fixes this. Built on Ignis, all three panels run in one process with proper Wayland Layer Shell support. No pointer grab conflicts. Click anywhere. It just works.

## Why This Exists

| Problem | How We Solve It |
|---------|-----------------|
| "Rofi grabs the pointer, side panels are dead" | **Single process** - Ignis handles all panels, no grab conflicts |
| "I keep launching the same 5 apps" | **Smart frecency** - Firefox-style algorithm learns your patterns |
| "I want quick access to favorites" | **Bookmarks panel** - Right-click to add, drag to reorder |
| "My launcher looks wrong after wallpaper change" | **Wallust integration** - Colors update automatically |
| "Launchers are slow to open" | **Sub-100ms launch** - Python + GTK4, minimal footprint |

## What Makes It Different

- **Actually multi-panel**: Three independent panels that all respond to clicks
- **Learns your habits**: Frecency ranking means your most-used apps float to the top
- **Keyboard and mouse**: Full keyboard nav in search, click-friendly everywhere
- **Wayland-native**: Built for Hyprland/Sway/Niri, not ported from X11

---

![Status](https://img.shields.io/badge/status-in%20development-yellow)
![Platform](https://img.shields.io/badge/platform-Wayland-blue)
![Framework](https://img.shields.io/badge/framework-Ignis-purple)

## Features

- **Three Interactive Panels**
  - Left: Bookmarked apps (customizable favorites)
  - Center: Search panel (filter all installed apps)
  - Right: Frequent apps (auto-ranked by usage)

- **Dynamic Bookmarks**
  - Right-click to add/remove apps
  - Drag-and-drop to reorder
  - Persists across sessions

- **Smart Frecency**
  - Firefox-style algorithm (frequency × recency)
  - Learns your usage patterns over time
  - Time-weighted rankings (recent apps rank higher)

- **Wallust Integration**
  - Colors automatically match your wallpaper
  - Dynamic theme updates when wallpaper changes
  - GTK4 CSS styling

- **Fast & Lightweight**
  - Python + GTK4 + Wayland Layer Shell
  - Sub-100ms launch time
  - Minimal memory footprint

## Installation

### Prerequisites

```bash
# Arch Linux / CachyOS
sudo pacman -S python python-gobject gtk4 python-pipx

# Wallust for dynamic colors (optional but recommended)
# Install from AUR or https://github.com/devora-garb/wallust
```

### Install Ignis

```bash
# Clone this repository
git clone <your-repo-url> ~/repos/ignomi
cd ~/repos/ignomi

# Install Ignis framework
pipx install ./ignis

# Verify installation
ignis --version
```

### Setup Launcher

```bash
# Create Ignis config symlink
mkdir -p ~/.config/ignis
ln -s ~/repos/ignomi/launcher/config.py ~/.config/ignis/config.py

# Create colors symlink (after Wallust setup)
mkdir -p ~/.config/ignomi/styles
ln -s ~/.config/ignomi/colors.css ~/repos/ignomi/launcher/styles/colors.css
```

### Hyprland Keybinding

Add to `~/.config/hypr/config/keybinds.conf`:

```conf
bindd = $mainMod, SPACE, Launch Ignomi three-panel launcher, exec, ~/repos/ignomi/scripts/toggle-launcher.sh
```

## Usage

### Basic Operations

- **Open Launcher:** Press `Mod+Space` (or your configured keybind)
- **Search Apps:** Start typing in the center panel
- **Launch App:** Click any app from any panel
- **Close:** Press `Escape` or wait for auto-close (0.3s after launch)

### Search Prefixes

The center panel routes your query to one of several handlers based on a
short prefix or keyword:

| Type | Trigger | Example | What it does |
|------|---------|---------|--------------|
| App search | (none) | `firefox` | Filter installed applications (fuzzy when `rapidfuzz` is installed) |
| Calculator | `=` | `= sqrt(16) * 2` | Evaluate the expression and copy the result to the clipboard on Enter |
| Web search | `?`, `g:`, `w:`, `gh:`, `yt:` | `? wayland layer shell` | Open the result in your default browser via `xdg-open` |
| Custom command | `!` | `!lock` | Run a user-defined shell command from `launcher/data/commands.toml` |
| System controls | `vol`, `volume`, `bright`, `brightness`, `mute` | `vol` | Render an inline volume / brightness slider |

See [`launcher/search/README.md`](launcher/search/README.md) for the full
handler reference and `launcher/data/commands.toml` for the custom-command
schema.

### Managing Bookmarks

- **Add to Bookmarks:** Right-click app in search/frequent panels
- **Remove from Bookmarks:** Right-click app in bookmarks panel
- **Reorder Bookmarks:** Drag-and-drop apps in bookmarks panel

### Toggle Script

The primary way to open and close all three panels is the toggle script, which is
what the Hyprland keybind calls:

```bash
# Toggle all panels on/off
~/repos/ignomi/scripts/toggle-launcher.sh
```

The toggle script detects the cursor's monitor and assigns it to every
panel before showing them, so the launcher always appears where your
cursor is.

### Manual Frecency Tracking

Track apps launched outside the launcher:

```bash
~/repos/ignomi/scripts/track-launch.sh firefox.desktop
```

## Configuration

### Panel Settings

Edit `launcher/data/settings.toml`:

```toml
[launcher]
close_delay_ms = 300       # Auto-close delay after launch (ms)

[frecency]
max_items = 12             # Apps shown in frequent panel
min_launches = 2           # Minimum launches before appearing

[search]
max_results = 30           # Max results for app search
fuzzy_threshold = 50       # rapidfuzz score cutoff (0-100, higher = stricter)

[animation]
transition_duration = 200  # Search-panel reveal/crossfade duration (ms)
```

Panel widths are hard-coded in the panel modules (no `[panels]` section).
For per-monitor backdrop blur tuning, edit `_MONITOR_SETTINGS` near the
top of `launcher/panels/backdrop.py`.

### Initial Bookmarks

Edit `launcher/data/bookmarks.json`:

```json
{
  "bookmarks": [
    "firefox.desktop",
    "Alacritty.desktop",
    "code.desktop"
  ]
}
```

### Wallust Color Theme

Create template at `~/.config/wallust/templates/ignomi.css`:

```css
@define-color bg {{background}};
@define-color fg {{foreground}};
@define-color accent {{color3}};
@define-color success {{color2}};
@define-color warning {{color1}};
@define-color error {{color5}};
```

Update `~/.config/wallust/wallust.toml`:

```toml
[templates]
ignomi_colors = {
    template = "ignomi.css",
    target = "/home/<your-username>/.config/ignomi/colors.css"
}
```

## Project Structure

```
ignomi/
├── ignis/                   # Ignis framework (git submodule)
├── launcher/                # Launcher implementation
│   ├── config.py            # Main Ignis entry point
│   ├── panels/              # Panel implementations
│   │   ├── backdrop.py      # Animated screenshot-based blur overlay
│   │   ├── bookmarks.py     # Bookmarks panel (left)
│   │   ├── search.py        # Search panel (center)
│   │   └── frequent.py      # Frequent apps panel (right)
│   ├── search/              # Pluggable query routing layer
│   │   ├── router.py        # QueryRouter, ResultItem, SearchHandler
│   │   └── handlers/        # 5 built-in handlers (apps, calc, web, cmd, ctrls)
│   ├── services/            # Backend services
│   │   └── frecency.py      # Frecency tracking + SQLite
│   ├── utils/               # Helper functions
│   │   └── helpers.py       # App launching, bookmarks, monitor detection, toggle
│   ├── data/                # Configuration files
│   │   ├── bookmarks.json   # Seed bookmarks (copied to XDG path on first run)
│   │   ├── commands.toml    # User-defined `!` commands
│   │   └── settings.toml    # [launcher] [frecency] [search] [animation] sections
│   └── styles/              # CSS styling
│       ├── main.css         # Layout, colors, animations
│       └── colors.css       # Symlink to Wallust-generated colors
├── scripts/                 # Utility scripts
│   ├── toggle-launcher.sh   # Toggle all three panels (used by keybind)
│   └── track-launch.sh      # Manual frecency tracking
├── tests/                   # pytest suite (handlers, frecency, settings, bookmarks)
├── docs/                    # Architecture diagrams
├── project-docs/            # Design docs, research, discoveries
└── README.md
```

## Development

### Running in Dev Mode

```bash
# Start Ignis daemon (if not running)
ignis init &

# Open the launcher (one window hosts all panels)
ignis open-window ignomi-launcher

# Or toggle the launcher (same as the keybind)
./scripts/toggle-launcher.sh

# Reload after code/CSS changes
ignis reload

# View logs
journalctl -f | grep ignis

# List registered windows
ignis list-windows
```

## Troubleshooting

### Launcher doesn't appear

```bash
# Check if Ignis is running
ps aux | grep ignis

# Check Ignis logs
journalctl --user -u ignis

# Verify keybinding
hyprctl binds | grep ignomi
```

### Panels overlap incorrectly

Monitor selection is automatic. The toggle script calls `toggle_launcher()`
in `launcher/utils/helpers.py`, which uses `get_monitor_under_cursor()` to
detect the cursor's monitor and assigns `window.monitor` on every panel
*before* showing them (required by `wlr-layer-shell`, which binds the
surface to its monitor at creation time).

At runtime, monitor and cursor data is fetched via Ignis IPC:

```python
# launcher/utils/helpers.py
hyprland = HyprlandService.get_default()
cursor_raw = hyprland.send_command("cursorpos").strip()  # "x, y"
for monitor in hyprland.monitors:
    ...
```

The same information is available from the command line for debugging:

```bash
# Verify Hyprland sees your monitors
hyprctl monitors -j

# Check cursor position detection
hyprctl cursorpos
```

If the CLI commands return correct values but the panels still land on
the wrong monitor, restart Ignis (`ignis quit && ignis init &`) — stale
monitor data after a hotplug event is the most common cause.

### Frecency not updating

```bash
# Check database exists
ls -la ~/.local/share/ignomi/app_usage.db

# Manually test tracking
~/repos/ignomi/scripts/track-launch.sh firefox.desktop
```

### Colors not updating

```bash
# Regenerate Wallust colors
wallust run ~/.config/wallust/wallpapers/current.png

# Check symlink
ls -la ~/repos/ignomi/launcher/styles/colors.css
```

## License

[MIT License](LICENSE)

## Credits

- [Ignis Framework](https://github.com/linkfrg/ignis) - Widget system and Wayland integration
- [Wallust](https://github.com/devora-garb/wallust) - Dynamic color generation
- Firefox Frecency Algorithm - Usage ranking approach
