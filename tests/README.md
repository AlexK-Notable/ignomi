# Ignomi Test Suite

This directory contains the pytest-based test suite for the Ignomi launcher. Tests are designed to run **headless** — no Wayland session, Layer Shell, or GTK display are required, thanks to per-file import mocking that stands in for the Ignis/GTK runtime.

## Running the suite

From the project root:

```bash
pytest tests/ -v
```

You can run a single file or a single test:

```bash
pytest tests/test_frecency.py -v
pytest tests/test_router.py::TestQueryRouter::test_first_matching_handler_wins -v
```

There are no special environment variables, no `DISPLAY` or `WAYLAND_DISPLAY` needed, and no daemon to start — `tests/conftest.py` and per-test module fakes (see "Headless-test pattern" below) replace the real GTK/Ignis modules at import time.

### Optional dependencies

Some tests are skipped when their optional dependency is not installed:

- `tests/test_app_search.py::test_fuzzy_search_finds_close_match` — gated on `rapidfuzz` via `pytest.mark.skipif(not HAS_RAPIDFUZZ, ...)`.

Install with `pip install rapidfuzz` (or via `pipx inject ignis rapidfuzz`) to exercise fuzzy matching.

## Fixtures (`tests/conftest.py`)

All fixtures use **real file I/O** in pytest's per-test `tmp_path` directory. Nothing about the filesystem is mocked.

| Fixture | What it creates | Used by |
|---------|------------------|---------|
| `tmp_db` | A real SQLite database at `tmp_path/app_usage.db` with the FrecencyService schema (`app_stats` table + `idx_frecency` index) already created. | `test_frecency.py` |
| `tmp_bookmarks` | A real JSON file at `tmp_path/bookmarks.json` containing three seed entries (`firefox.desktop`, `code.desktop`, `nautilus.desktop`). | `test_bookmarks.py` |
| `tmp_settings` | A real `tmp_path/settings.toml` with all four sections populated (`[launcher]`, `[frecency]`, `[search]`, `[animation]`). | `test_settings.py` |
| `tmp_commands` | A real `tmp_path/commands.toml` with two entries (`lock` → `hyprlock`, `suspend` → `systemctl suspend`). | `test_commands.py` |

If you add a new test that needs a config file, **prefer extending these fixtures over rolling your own** — they keep the I/O contract honest while giving you a clean directory per test.

## What's covered

| File | Coverage |
|------|----------|
| `tests/test_frecency.py` | `FrecencyService`: `_calculate_frecency` (all five recency-weight tiers), `record_launch` (insert + increment), `get_top_apps` (ordering, `min_launches` filter). |
| `tests/test_router.py` | `QueryRouter`: priority dispatch (highest priority handler with a match wins), empty-query routing, no-match returns `"none"`. |
| `tests/test_calculator.py` | `CalculatorHandler`: `matches`/`get_results`, malicious-input rejection (e.g. `__import__`), `pi`/`e` constants, division-by-zero handling. |
| `tests/test_app_search.py` | `AppSearchHandler`: `matches`/`get_results`, empty-query default slice, `ResultItem` shape, optional `rapidfuzz`-gated fuzzy match. |
| `tests/test_commands.py` | `CustomCommandsHandler`: TOML loading, prefix matching, malformed-entry skipping. |
| `tests/test_web_search.py` | `WebSearchHandler`: `matches` + URL construction across Kagi / Google / Wikipedia / GitHub / YouTube and custom engines. |
| `tests/test_bookmarks.py` | `load_bookmarks` / `save_bookmarks`: file I/O, atomic write (temp-file + rename), cache invalidation, XDG-migration code path. |
| `tests/test_settings.py` | `_deep_merge` (flat override, key addition, nested merging) + `load_settings` defaults vs. user overrides. |

Approximate total: **~70-80 tests across 8 files** (consistent with the project memo "78 tests passing" from the remediation sprint).

## Coverage gaps

The current suite leaves several user-visible code paths untested. These are honest gaps, not "we test it elsewhere" — they are real test debt:

- **`SystemControlsHandler`** (`launcher/search/handlers/controls.py`) — **no tests**, even though it has the highest priority (50) of all handlers and contains graceful-degradation logic for missing audio/backlight services. The inline `widget_builder` pattern is also untested.
- **`backdrop.py`** — no tests for the PIL blur pipeline, the ease-in interval math, the generation counter that cancels stale frame jobs, the per-monitor settings lookup, or the PIL thread-safety guarantee documented in MEMORY.md.
- **Panel classes themselves** (`BookmarksPanel`, `SearchPanel`, `FrequentPanel`) — only their downstream services and handlers are exercised. Window construction, monitor binding, signal wiring, and lifecycle are all untested.
- **`toggle_launcher()` / `close_launcher()` / `_close_search_panel` / `_close_backdrop`** — Layer Shell monitor-binding logic is untested despite a documented history of bugs in this exact area.
- **`get_monitor_under_cursor()` / `hyprland_monitor_to_ignis_monitor()`** — both untested. These wrap HyprlandService IPC and a connector-name lookup; both have been bug sites in past sprints.

## Headless-test pattern

Several handler modules import `ignis.services.applications`, `ignis.services.audio`, `ignis.services.backlight`, `ignis.widgets`, `gi.repository.Gdk`, etc. at module-load time. Without intervention, simply `import`ing a handler in a test environment that has no Wayland session would raise `ImportError` (or worse, hang trying to connect to a display).

The suite handles this in two related ways. Both work; pick whichever fits your test.

### Pattern 1 — Top-level module replacement (used by `test_app_search.py`, `test_bookmarks.py`, `test_frecency.py`)

Before importing the system-under-test, the test file builds fake module objects with `types.ModuleType(...)` and `unittest.mock.MagicMock()`, installs them in `sys.modules`, imports the SUT, then restores any modules that were originally present.

Skeleton:

```python
import sys
import types
from unittest.mock import MagicMock

_saved_modules = {}
_modules_to_fake = [
    "gi", "gi.repository",
    "ignis", "ignis.widgets",
    "ignis.services", "ignis.services.applications",
]
for _mod in _modules_to_fake:
    if _mod in sys.modules:
        _saved_modules[_mod] = sys.modules[_mod]

# Build fake modules
_fake_gi = types.ModuleType("gi")
_fake_ignis = types.ModuleType("ignis")
_fake_ignis.widgets = MagicMock()
# ... wire up children ...

sys.modules["gi"] = _fake_gi
sys.modules["ignis"] = _fake_ignis
# ... install all entries ...

# Now safe to import the SUT
from search.handlers.app_search import AppSearchHandler

# Restore originals so other test files aren't affected
for _mod in _modules_to_fake:
    if _mod in _saved_modules:
        sys.modules[_mod] = _saved_modules[_mod]
    elif _mod in sys.modules:
        del sys.modules[_mod]
```

### Pattern 2 — Per-test fixture (used by `test_router.py`)

For tests that don't need a fully-shaped fake module — just enough that an `import` succeeds — an autouse fixture with `patch.dict("sys.modules", ...)` is shorter and self-contained:

```python
@pytest.fixture(autouse=True)
def _mock_ignis():
    with patch.dict("sys.modules", {
        "ignis": MagicMock(),
        "ignis.services": MagicMock(),
        "ignis.services.applications": MagicMock(),
    }):
        yield
```

### Why this matters

Ignis services normally require a running Wayland session, a Hyprland (or compatible) compositor, and the Layer Shell protocol. Without these mocks, **every test would `ImportError` at module load**, making the suite impossible to run in CI, on a non-Wayland machine, or in a fresh dev container. The mock surfaces are intentionally minimal — the real behavior lives in the SUT, not in the fakes.

If you add a test that imports a new Ignis or `gi` symbol, extend the appropriate `_modules_to_fake` list (Pattern 1) or the `patch.dict` mapping (Pattern 2).

## Recommended test additions (prioritized)

### HIGH

- **`test_controls.py`** — `SystemControlsHandler` is priority 50 (the highest of all handlers) and contains graceful-degradation logic in `_audio_available` / `_backlight_available`. Both branches of each guard need verification, plus the inline `widget_builder` pattern. Mocks needed: `ignis.services.audio.AudioService.get_default()` and `ignis.services.backlight.BacklightService.get_default()` — extend `test_app_search.py`'s Pattern 1 fakes to return `MagicMock` instances with the relevant attributes.
- **`test_helpers.py`** — `_close_search_panel`, `_close_backdrop`, and `toggle_launcher` have a documented bug history (Layer Shell monitor binding fired too late from per-panel handlers). At minimum: a state-machine test that exercises `IgnisApp` window discovery + `window.monitor` rebinding + `window.visible` toggle, with all of these mocked. Use Pattern 2 to keep the test self-contained.

### MED

- **`test_backdrop.py`** — at minimum, test:
  - the **generation counter** (a stale frame job from generation N-1 must not overwrite a fresh capture from generation N),
  - the **ease-in interval math** (frame durations should accelerate, not be uniform),
  - the **per-monitor settings lookup** (the `_MONITOR_SETTINGS` dict literal — the only `DP-1` override matters here).
  The PIL pipeline itself can be tested with small fixed in-memory `Image` objects; no need to invoke `grim`.
- **`test_monitor_helpers.py`** — `get_monitor_under_cursor` (mock `HyprlandService.send_command` to return canned cursor-position and monitor-list responses) and `hyprland_monitor_to_ignis_monitor` (pure logic test of the connector-name → GTK index mapping).

### LOW

- Panel-class tests (`BookmarksPanel`, `SearchPanel`, `FrequentPanel`) are the hardest — they require mocking GTK widget construction, Revealer state, signal connections, and Layer Shell window lifecycle. Defer until the higher-priority gaps are filled and there is a clear story for shared GTK widget mocks. If undertaken, share helpers via `conftest.py` rather than per-file boilerplate.

## See also

- `~/.claude/projects/-home-komi-repos-ignomi/memory/MEMORY.md` — "Testing" section: lists the canonical mock surfaces (`time.time()`, `GObject.emit`, `BaseService.__init__`, `ApplicationsService.apps`).
- Phase 1 audit z-note `YZ0fIVUNY3wCB0Sb32XGU` — original gap-finding for this README.
