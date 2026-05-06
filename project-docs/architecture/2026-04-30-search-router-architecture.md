# Search Router Architecture

**Date:** 2026-04-30
**Status:** Implemented (commit `94b83cf`)
**Scope:** `launcher/search/` subpackage and its integration with `launcher/panels/search.py`

> **Read alongside:** the original launcher design doc
> [`2025-11-02-ignomi-launcher-design.md`](./2025-11-02-ignomi-launcher-design.md)
> documents the older "single in-process app filter" model. This document
> supersedes the search-related portions of that design.

## Overview

The Ignomi search panel dispatches every keystroke through a **priority-ordered
query router**. Each search modality — installed-app fuzzy search, calculator,
web search, custom shell commands, and inline system controls — is implemented
as a small, independent **handler**. The panel itself owns no search business
logic; it only owns the input field, results list, keyboard navigation, and the
debounce timer.

The router design replaces what would otherwise be a growing if/elif chain
inside `SearchPanel._on_search`. Each handler is roughly 80–180 lines, lives in
its own file, and can be unit-tested in isolation without instantiating the
panel, GTK, or Ignis.

## Why a Router (vs. a Giant if/elif in SearchPanel)

A monolithic search method would conflate five concerns:

1. **Trigger detection** (`?` prefix? `=` prefix? volume keyword? always?)
2. **Result production** (URL construction, math eval, app filtering)
3. **Result rendering** (icon, title, description, inline widget)
4. **Activation handler** (launch app, copy to clipboard, xdg-open URL, run shell)
5. **Optional dependencies** (rapidfuzz, simpleeval, ignis-gvc)

Each concern has different testing needs and different failure modes. A router
gives every handler a clear contract and lets each one fail or be missing
independently — a missing `simpleeval` simply removes the `=` calculator
without affecting anything else.

Other practical wins:

- **Test isolation** — `tests/test_calculator.py`, `tests/test_app_search.py`,
  `tests/test_commands.py`, `tests/test_web_search.py`, and `tests/test_router.py`
  exercise handlers without launching GTK.
- **Discoverability** — `launcher/search/handlers/` is a single directory of
  handler classes; new contributors see the full extension surface at a glance.
- **Priority is data, not control flow** — adding a handler is a one-line
  registration, not a new branch in `_on_search`.
- **The fallback is just another handler** — `AppSearchHandler` is registered
  with `priority = 1000` and `matches() -> True`, so the no-special-prefix
  case requires no special-case code.

## The `SearchHandler` Protocol

`SearchHandler` is a [`typing.Protocol`](https://peps.python.org/pep-0544/) —
a **structural** type. Handlers do not subclass it; they merely need to provide
the right attributes and methods.

From `launcher/search/router.py:26-32`:

```python
class SearchHandler(Protocol):
    """Structural type for search handlers. No inheritance required."""
    name: str
    priority: int

    def matches(self, query: str) -> bool: ...
    def get_results(self, query: str) -> list[ResultItem]: ...
```

**Why structural typing?**

- **No artificial base class** — handlers stay independent. There is no
  shared state to protect, no template-method pattern to extend.
- **Tests don't need a fixture** — a hand-rolled stub (`class FakeHandler:
  name = "x"; priority = 1; def matches(...): ...`) is a valid
  `SearchHandler` to type-checkers and to the router at runtime.
- **Optional dependencies stay local** — `CalculatorHandler` can decide at
  module-import time whether `simpleeval` is available and degrade
  `matches()` accordingly without affecting `SearchHandler`'s definition.
- **Future plugin path is open** — third-party handlers are exactly what
  Protocols enable: any class meeting the contract can be registered.

## The `ResultItem` Dataclass

`ResultItem` is a frozen-shape result schema shared by every handler.

From `launcher/search/router.py:14-23`:

```python
@dataclass
class ResultItem:
    """A single search result from any handler."""
    title: str
    description: str = ""
    icon: str = "image-missing"
    result_type: str = "app"  # app, calculator, control, web, command
    on_activate: Callable | None = None
    widget_builder: Callable | None = None
    app: object = None  # Application object for app results
```

| Field            | Purpose                                                              |
| ---------------- | -------------------------------------------------------------------- |
| `title`          | Bold label rendered as the result heading                            |
| `description`    | Subtitle line under the title                                        |
| `icon`           | Icon name (XDG icon theme) — default `image-missing`                 |
| `result_type`    | CSS class hint and bookmark-eligibility flag (only `app` allows ⌥-add) |
| `on_activate`    | Custom handler invoked on Enter / row-activation                     |
| `widget_builder` | Inline widget renderer — overrides default row layout                |
| `app`            | Original `Application` object — preserved so `launch_app()` and the bookmark-add flow can use it |

### The `widget_builder` Callback Pattern

For four of the five handlers (apps, calculator, web, commands), a result is
just text + icon + activation. `SearchPanel._create_result_row` renders these
with a single shared layout.

`SystemControlsHandler` is the exception: it ships **interactive** controls
(volume slider, brightness slider, mute switch) that need live `ignis.widgets`
to function. Rather than special-case the panel renderer, the handler returns
a `ResultItem` with `widget_builder` set to a callable that produces the
inline `widgets.Box` with `widgets.Scale` / `widgets.Switch` children.

The renderer chooses path on a single `if`:

```python
# launcher/panels/search.py:195-202
for result in self.current_results:
    if result.widget_builder:
        widget = result.widget_builder()
        row = widgets.ListBoxRow(child=widget)
        self.results_box.append(row)
    else:
        row = self._create_result_row(result)
        self.results_box.append(row)
```

This keeps `SearchPanel` ignorant of which handlers do or do not need bespoke
widgets. Adding a new "interactive" handler (e.g., a future quick-toggle for
Wi-Fi or media playback) requires nothing more than returning a
`widget_builder` from `get_results()`.

## Priority Dispatch Semantics

**Lower number = higher priority. First matching handler wins.**

The router stores handlers in a list, re-sorted on every registration:

```python
# launcher/search/router.py:41-44
def register(self, handler: SearchHandler) -> None:
    """Register a handler and re-sort by priority."""
    self._handlers.append(handler)
    self._handlers.sort(key=lambda h: h.priority)
```

Routing iterates in priority order:

```python
# launcher/search/router.py:64-68
for handler in self._handlers:
    if handler.matches(query):
        return handler.name, handler.get_results(query)

return "none", []
```

### Currently Registered Handlers

Registration in `SearchPanel.__init__` (`launcher/panels/search.py:55-64`):

| Priority | Handler                  | Trigger                                        | Optional Dep | File |
| -------- | ------------------------ | ---------------------------------------------- | ------------ | ---- |
| **50**   | `SystemControlsHandler`  | `vol`, `volume`, `bright`, `brightness`, `mute` | ignis-gvc / ignis backlight | `handlers/controls.py` |
| **100**  | `CalculatorHandler`      | `=` prefix                                     | `simpleeval` | `handlers/calculator.py` |
| **200**  | `WebSearchHandler`       | `?`, `g:`, `w:`, `gh:`, `yt:` prefixes         | none         | `handlers/web_search.py` |
| **300**  | `CustomCommandsHandler`  | `!` prefix                                     | `toml` (required) | `handlers/commands.py` |
| **1000** | `AppSearchHandler`       | always — fallback                              | `rapidfuzz` (fuzzy match upgrade) | `handlers/app_search.py` |

The 50-100-200-300-1000 spacing is intentional — adding a future handler at
e.g. 150 (between calculator and web search) requires no renumbering of
existing handlers.

### Why the Order Matters

- **Controls beat calculator** — the literal query `vol` should not be
  parsed as a math expression. Even though `vol` doesn't start with `=`, the
  ordering documents the intent: "system controls always check first."
- **Web search beats commands** — a query like `?bash !bang` would match
  web search at the prefix `?`, never reaching the commands handler.
- **App search is last** — every prefix-driven handler gets a chance to
  claim the query before falling through to general application filtering.

### Empty-Query Behavior

An empty query short-circuits the priority loop and routes directly to
app search, which returns the first 20 installed apps:

```python
# launcher/search/router.py:57-62
if not query or not query.strip():
    # Empty query - let app search show defaults
    for handler in self._handlers:
        if handler.name == "app_search":
            return handler.name, handler.get_results("")
    return "none", []
```

This is why opening the launcher and immediately pressing Enter launches
the first installed app — there is always a populated, auto-selected list.

## Optional-Dependency Pattern

Handlers that wrap an optional library check at import time, set a flag,
and use the flag in `matches()`:

```python
# launcher/search/handlers/calculator.py:16-32
try:
    from simpleeval import InvalidExpression, simple_eval
    HAS_SIMPLEEVAL = True
except ImportError:
    HAS_SIMPLEEVAL = False


class CalculatorHandler:
    name = "calculator"
    priority = 100

    def matches(self, query: str) -> bool:
        if not HAS_SIMPLEEVAL:
            return False
        return query.strip().startswith("=")
```

If `simpleeval` is missing, `matches()` returns `False` and `=` queries fall
through to the next handler. The user sees only their `=2+2` echoed back (no
calculator result), but the launcher does not crash.

`AppSearchHandler` follows the same pattern with `rapidfuzz`, but degrades
to `ApplicationsService.search()` (a substring match) instead of
disappearing entirely — search is the fallback, so it must always work.

`SystemControlsHandler` extends the pattern at runtime: it not only
imports lazily but also calls `_audio_available()` / `_backlight_available()`
which touch `AudioService.get_default()` inside a `try` to confirm the
service is actually usable on this system.

## Lifecycle: Keystroke to Rendered Results

```
┌──────────────────────────────────────────────────────────────────┐
│                  SearchPanel keystroke pipeline                  │
└──────────────────────────────────────────────────────────────────┘

  user types "g"
        │
        ▼
  widgets.Entry.on_change → _on_search_changed()    (search.py:175)
        │
        │  _closing flag set?  ── yes ──► drop event (close-guard)
        │   no
        ▼
  GLib.timeout_add(120, _do_search)                  (search.py:181)
        │  ── new keystroke arrives within 120ms ──┐
        │                                          │
        │   (timer cancelled, restarted)           │
        ▼                                          │
  _do_search()                  ◄──────────────────┘
        │
        ▼
  router.route(query)                                (search.py:187)
        │
        │  empty query?  ── yes ──► AppSearchHandler.get_results("")
        │   no
        ▼
  for handler in priority-sorted list:
        │   handler.matches(query)?  ── no ──► next
        │       yes
        ▼
  handler.get_results(query) → list[ResultItem]
        │
        ▼
  _update_results()                                  (search.py:191)
        │
        │  for each result:
        │    ┌── result.widget_builder set? ──► widget = result.widget_builder()
        │    │                                  row    = widgets.ListBoxRow(child=widget)
        │    │
        │    └── otherwise ──► row = _create_result_row(result)
        │
        ▼
  results_box.append(row)
        │
        ▼
  results_box.select_row(rows[0])      ← first row auto-selected
        │
        ▼
  user presses Enter
        │
        ▼
  _on_entry_activate() / _on_key_press(Return)        (search.py:327, 341)
        │
        ▼
  results_box.activate_row(selected)
        │
        ▼
  _activate_result(result)                            (search.py:264)
        │
        │  result.on_activate set?  ── yes ──► result.on_activate()
        │      (calculator copies to clipboard,
        │       web opens URL, command runs shell,
        │       all then call close_launcher())
        │
        │  otherwise (app result) ──► launch_app(result.app, frecency, close_delay)
        │                              ├── app.launch()
        │                              ├── frecency.record_launch()
        │                              └── GLib.timeout_add(close_delay, close_launcher)
```

### Mermaid View

```mermaid
sequenceDiagram
    participant User
    participant Entry as widgets.Entry
    participant Panel as SearchPanel
    participant Router as QueryRouter
    participant Handler as SearchHandler
    participant Box as widgets.ListBox

    User->>Entry: keystroke
    Entry->>Panel: on_change
    Panel->>Panel: _on_search_changed()
    Note right of Panel: cancel pending timer<br/>schedule 120ms debounce
    Panel->>Panel: _do_search() (after 120ms)
    Panel->>Router: route(query)
    alt empty query
        Router->>Handler: AppSearchHandler.get_results("")
    else priority loop
        loop priority-sorted
            Router->>Handler: matches(query)?
            Handler-->>Router: True / False
        end
        Router->>Handler: get_results(query)
    end
    Handler-->>Panel: list[ResultItem]
    Panel->>Box: remove_all() + append rows
    Note right of Box: widget_builder() called<br/>for inline-widget results
    Panel->>Box: select_row(rows[0])
    User->>Entry: Enter
    Entry->>Panel: activate
    Panel->>Box: activate_row(selected)
    Box->>Panel: _activate_result(result)
    alt has on_activate
        Panel->>Handler: result.on_activate()
    else app result
        Panel->>Panel: launch_app(result.app, ...)
    end
```

## Integration With SearchPanel

The panel is now a thin shell around the router. Its `__init__`
(`launcher/panels/search.py:49-78`) consists almost entirely of:

1. Resolving services (`ApplicationsService`, `FrecencyService`, settings)
2. Constructing the router and registering five handlers
3. Initializing widget references to `None` (created later in `create_window`)
4. Setting `_debounce_timer = None` and `_closing = False`

The interesting code paths (`_on_search_changed`, `_do_search`,
`_update_results`, `_activate_result`) total well under 80 lines.

## Cross-References

**Code:**

- [`launcher/search/router.py`](../../launcher/search/router.py) — `QueryRouter`,
  `ResultItem`, `SearchHandler`
- [`launcher/search/handlers/app_search.py`](../../launcher/search/handlers/app_search.py)
- [`launcher/search/handlers/calculator.py`](../../launcher/search/handlers/calculator.py)
- [`launcher/search/handlers/web_search.py`](../../launcher/search/handlers/web_search.py)
- [`launcher/search/handlers/commands.py`](../../launcher/search/handlers/commands.py)
- [`launcher/search/handlers/controls.py`](../../launcher/search/handlers/controls.py)
- [`launcher/panels/search.py:55-65`](../../launcher/panels/search.py) — handler
  registration block

**Tests:**

- `tests/test_router.py` — priority dispatch, empty-query routing,
  no-match returns `"none"`
- `tests/test_app_search.py`, `tests/test_calculator.py`,
  `tests/test_web_search.py`, `tests/test_commands.py` — per-handler
  isolation tests

**Related architecture docs:**

- [`2025-11-02-ignomi-launcher-design.md`](./2025-11-02-ignomi-launcher-design.md)
  — original three-panel design (search section now superseded by this doc)
- [`2026-04-30-animation-architecture.md`](./2026-04-30-animation-architecture.md)
  — why the search panel uses a GTK Revealer where other panels do not
- [`2026-04-30-backdrop-blur-pipeline.md`](./2026-04-30-backdrop-blur-pipeline.md)
  — the parallel sibling subsystem the launcher now ships

**Related zk-notes:**

- `[[puAgRuJyp3fLROUs3EfwS]]` — Phase 0b deep exploration of the search
  panel surface area
- `[[YZ0fIVUNY3wCB0Sb32XGU]]` — Phase 1 audit naming this doc as gap G1
