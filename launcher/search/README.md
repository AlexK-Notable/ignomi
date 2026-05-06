# launcher/search/

Pluggable query routing layer between the `SearchPanel` UI and a set of
priority-ordered handlers.

## Overview

The `search/` subpackage decouples *what is being searched* from *how the
search panel renders results*. `SearchPanel` does not know about apps,
calculators, or web URLs — it talks only to a `QueryRouter`, which in
turn dispatches each keystroke to the first matching `SearchHandler`.

A handler decides whether it can handle a query (`matches()`), and if so
returns a list of typed `ResultItem` rows (`get_results()`). Lower
priority numbers win — handler 50 (system controls) is checked before
handler 1000 (app search fallback).

## Package Structure

```
launcher/search/
├── __init__.py          # Re-exports QueryRouter, ResultItem, SearchHandler
├── router.py            # Router, dataclass, and Protocol definitions
└── handlers/
    ├── __init__.py      # Re-exports all 5 built-in handlers
    ├── controls.py      # SystemControlsHandler   (priority 50)
    ├── calculator.py    # CalculatorHandler       (priority 100)
    ├── web_search.py    # WebSearchHandler        (priority 200)
    ├── commands.py      # CustomCommandsHandler   (priority 300)
    └── app_search.py    # AppSearchHandler        (priority 1000, fallback)
```

## Quick Start

```python
from search.router import QueryRouter
from search.handlers import (
    AppSearchHandler,
    CalculatorHandler,
    CustomCommandsHandler,
    SystemControlsHandler,
    WebSearchHandler,
)

router = QueryRouter()
router.register(SystemControlsHandler())   # 50
router.register(CalculatorHandler())       # 100
router.register(WebSearchHandler())        # 200
router.register(CustomCommandsHandler())   # 300
router.register(AppSearchHandler())        # 1000

handler_name, results = router.route("= 2 + 2")
# handler_name == "calculator"
# results[0].title == "4"
```

The actual registration site lives in `launcher/panels/search.py`
(`SearchPanel.__init__`, lines 55-64).

## QueryRouter API (`router.py`)

```python
class QueryRouter:
    def __init__(self) -> None: ...
    def register(self, handler: SearchHandler) -> None: ...
    def route(self, query: str) -> tuple[str, list[ResultItem]]: ...
```

### `register(handler)`

Adds a handler and re-sorts the internal list by `handler.priority`
(ascending — lower numbers run first). Idempotent registration is *not*
enforced; registering the same handler twice will produce duplicate
results.

### `route(query)` → `(handler_name, results)`

Dispatch rules:

1. If `query` is empty or whitespace-only, the router falls through to
   the handler whose `name` is exactly `"app_search"` and returns its
   default result set (used to render the initial app list when the
   panel opens).
2. Otherwise, the router iterates handlers in priority order and
   returns the first whose `matches(query)` is `True`.
3. If no handler matches, returns `("none", [])`.

### Priority semantics

Lower number = higher priority. Pick a number that leaves room on either
side for future handlers. The shipped handlers occupy 50, 100, 200, 300,
1000 — gaps are intentional. There is no upper bound; `app_search` uses
1000 as a sentinel "always last" value.

## SearchHandler Protocol (`router.py`)

`SearchHandler` is a `typing.Protocol` — a *structural* type. Handlers
do **not** subclass it; they merely need to provide the right attributes
and methods. This keeps each handler file independent and easy to test
in isolation.

```python
from typing import Protocol

class SearchHandler(Protocol):
    name: str
    priority: int

    def matches(self, query: str) -> bool: ...
    def get_results(self, query: str) -> list[ResultItem]: ...
```

| Member | Required | Notes |
|--------|----------|-------|
| `name` | yes | Identifier returned by `route()`; `"app_search"` is treated specially as the empty-query fallback |
| `priority` | yes | Int; lower runs first |
| `matches(query)` | yes | Cheap predicate. Should *not* do expensive work — that belongs in `get_results` |
| `get_results(query)` | yes | Returns `list[ResultItem]`. May return `[]` |

## ResultItem Dataclass (`router.py`)

```python
@dataclass
class ResultItem:
    title: str
    description: str = ""
    icon: str = "image-missing"          # GTK icon name
    result_type: str = "app"             # app | calculator | control | web | command
    on_activate: Callable | None = None  # Called when the user clicks/Enters
    widget_builder: Callable | None = None  # Returns a custom GTK widget
    app: object = None                   # Application object (app results only)
```

### Field reference

| Field | Used by |
|-------|---------|
| `title` | All handlers — the bold first line of the row |
| `description` | All handlers — the secondary line |
| `icon` | All handlers — GTK icon name resolved via the icon theme |
| `result_type` | Used by `SearchPanel` to choose the row template |
| `on_activate` | Called by `SearchPanel` on Enter / row click. App rows leave this `None` and let the panel call `launch_app(result.app, ...)` directly so frecency tracking is uniform |
| `widget_builder` | If set, `SearchPanel` calls it to build a custom inline widget instead of rendering the standard title/description row |
| `app` | The Ignis `Application` object for `result_type="app"` rows |

### `widget_builder` callback pattern

`widget_builder` is what makes inline controls possible. When the row is
rendered, `SearchPanel` calls `result.widget_builder()` (no arguments)
and inserts the returned GTK widget in place of the default row layout.

`SystemControlsHandler` is the only built-in user of this pattern. Its
`_build_volume_control()` and `_build_brightness_control()` methods
return `widgets.Box` instances containing live `widgets.Scale` and
`widgets.Switch` widgets bound directly to `AudioService` / `BacklightService`:

```python
# Excerpt from controls.py
ResultItem(
    title="Volume",
    icon="audio-volume-high",
    result_type="control",
    widget_builder=self._build_volume_control,  # Called by SearchPanel
)
```

The widget's lifetime is the lifetime of the result row — when the user
types another character and the result list is rebuilt, the inline
widget is destroyed and a new one is built.

## Built-in Handlers

| Priority | Handler | Trigger | Optional Dependencies |
|---------:|---------|---------|-----------------------|
| 50  | `SystemControlsHandler` | `vol`, `volume`, `sound`, `audio`, `speaker`, `mute`, `unmute`, `bright`, `brightness`, `backlight`, `screen` keywords (exact match, lowercase) | Uses Ignis `AudioService` and `BacklightService` if present; gracefully degrades when unavailable |
| 100 | `CalculatorHandler` | `=` prefix | `pipx inject ignis simpleeval` (handler is dormant without it) |
| 200 | `WebSearchHandler` | `?`, `g:`, `w:`, `gh:`, `yt:` prefixes (configurable) | None — uses `xdg-open` (always present on Wayland desktops) |
| 300 | `CustomCommandsHandler` | `!` prefix | None — reads `data/commands.toml`; missing file means no commands |
| 1000 | `AppSearchHandler` | Always matches (fallback) | `pipx inject ignis rapidfuzz` for typo-tolerant fuzzy matching; falls back to `ApplicationsService.search()` |

### Notes on each handler

- **SystemControlsHandler** uses `widget_builder` to render live Scale +
  Switch widgets bound to `AudioService.speaker.volume` and
  `BacklightService.brightness`. Activation is the slider drag itself,
  so `on_activate` is unused.
- **CalculatorHandler** uses `simpleeval` with an explicit whitelist of
  math functions (`sqrt`, `sin`, `cos`, `tan`, `log`, `log10`, `pow`,
  `min`, `max`, `abs`, `round`) and constants (`pi`, `e`). On activation,
  it copies the result to the clipboard via `wl-copy` and closes the
  launcher.
- **WebSearchHandler** stores its prefix → engine map as an instance
  attribute (`self.engines`) populated from the `engines=` constructor
  kwarg or `DEFAULT_ENGINES`. URL-encodes the search term and shells out
  to `xdg-open`. See the module docstring for the customization story.
- **CustomCommandsHandler** loads `data/commands.toml` once at
  construction time. Each command is a TOML table named
  `[commands.<id>]` with `description`, `exec`, and optional `icon`
  fields. **`shell=True`** is used to execute the command, so commands
  inherit the user's shell environment — keep the file in user-private
  storage.
- **AppSearchHandler** has both rapidfuzz and non-rapidfuzz code paths.
  When rapidfuzz is present, it uses `process.extract` with
  `fuzz.WRatio` and a configurable `fuzzy_threshold` (default 50). The
  non-rapidfuzz path uses `ApplicationsService.search()`, which is
  substring-based.

## Authoring a New Handler

There is no base class to inherit from — implement the `SearchHandler`
Protocol directly.

### 1. Create the handler module

```python
# launcher/search/handlers/emoji.py
"""
Emoji Handler - Insert emoji by name.

Triggers on ":" prefix. ":heart" → ❤
"""

from search.router import ResultItem


_EMOJI = {
    "heart": "❤",
    "fire": "🔥",
    "rocket": "🚀",
    # ... or load from a data file
}


class EmojiHandler:
    """Pick an emoji by name with ':' prefix."""

    name = "emoji"
    priority = 250  # between web_search (200) and commands (300)

    def matches(self, query: str) -> bool:
        return query.strip().startswith(":")

    def get_results(self, query: str) -> list[ResultItem]:
        needle = query.strip().lstrip(":").lower()
        if not needle:
            return [ResultItem(title="Type an emoji name",
                               description="e.g. :heart, :fire",
                               icon="face-smile",
                               result_type="emoji")]

        results = []
        for name, char in _EMOJI.items():
            if needle in name:
                results.append(ResultItem(
                    title=char,
                    description=f":{name}",
                    icon="face-smile",
                    result_type="emoji",
                    on_activate=lambda c=char: self._copy(c),
                ))
        return results

    def _copy(self, char: str) -> None:
        import subprocess
        subprocess.Popen(["wl-copy", char],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        from utils.helpers import close_launcher
        close_launcher()
```

### 2. Re-export from `handlers/__init__.py`

```python
from .emoji import EmojiHandler

__all__ = [
    "AppSearchHandler",
    "CalculatorHandler",
    "EmojiHandler",
    "SystemControlsHandler",
    "WebSearchHandler",
    "CustomCommandsHandler",
]
```

### 3. Register in `SearchPanel.__init__`

In `launcher/panels/search.py`, add a `register()` call alongside the
existing five (preserving priority ordering for clarity):

```python
self.router.register(SystemControlsHandler())   # 50
self.router.register(CalculatorHandler())       # 100
self.router.register(WebSearchHandler())        # 200
self.router.register(EmojiHandler())            # 250  ← new
self.router.register(CustomCommandsHandler())   # 300
self.router.register(AppSearchHandler(...))     # 1000
```

### 4. (Optional) Style the new `result_type`

If you set `result_type="emoji"` (or any new value), `launcher/styles/main.css`
will continue to use the generic `.result-item` class. To give the row a
distinct look, add a CSS class in your handler's row construction or
extend `SearchPanel`'s row template.

### Testing

Add a `tests/test_emoji_handler.py` following the conventions in
`tests/test_calculator.py` / `tests/test_web_search.py`. Handlers are
trivial to unit-test because they have no GTK dependency:

```python
def test_emoji_matches():
    h = EmojiHandler()
    assert h.matches(":heart")
    assert not h.matches("heart")
```

Run with `pytest tests/ -v`.

## Reference Files

- `launcher/search/router.py` — `QueryRouter`, `ResultItem`,
  `SearchHandler`
- `launcher/search/handlers/*.py` — Five reference implementations
- `launcher/panels/search.py` lines 55-64 — Live registration site
- `tests/test_router.py` — Router-level tests (priority dispatch, empty
  query, no-match path)
- `tests/test_calculator.py`, `tests/test_web_search.py`,
  `tests/test_app_search.py`, `tests/test_commands.py` — Per-handler
  tests

## See Also

- [`launcher/README.md`](../README.md) — Package-level overview
- [`data/commands.toml`](../data/commands.toml) — Schema example for
  `CustomCommandsHandler`
- [`data/settings.toml`](../data/settings.toml) — `[search]` section
  for `max_results` and `fuzzy_threshold`
