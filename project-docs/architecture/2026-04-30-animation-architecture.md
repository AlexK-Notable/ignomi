# Animation Architecture

**Date:** 2026-04-30
**Status:** Implemented (current as of commit `94b83cf`)
**Scope:** All four Ignomi `widgets.Window` surfaces — bookmarks, search,
frequent, and backdrop

> **Why this document exists:** the animation story has changed at least
> three times during Ignomi's development (RevealerWindow → plain Window →
> plain Window + Revealer for the search panel only). Both `MEMORY.md` and
> the original launcher design doc reflect older snapshots and are
> internally inconsistent with the current code. This document is the
> canonical reference for "which surface uses which animation system, and
> why."

## TL;DR

| Surface             | Anchor          | Open/close anim       | Compositor anim?  | GTK animation widget? |
| ------------------- | --------------- | --------------------- | ----------------- | --------------------- |
| `ignomi-bookmarks`  | left (edge)     | slide right→left      | **yes** (Hyprland) | no                    |
| `ignomi-frequent`   | right (edge)    | slide left→right      | **yes** (Hyprland) | no                    |
| `ignomi-backdrop`   | full-screen     | fade + blur ramp      | **yes** (Hyprland fade) | no — pixel pipeline (see backdrop blur pipeline doc) |
| `ignomi-search`     | top+bottom (centered) | crossfade (200ms) | **no** (`exclusivity="ignore"`) | **yes** (`widgets.Revealer`) |

**The default rule:** plain `widgets.Window` + Hyprland `layerrule`. The
search panel is the documented exception, for one specific reason: a
centered surface with no edge anchor drifts laterally as Hyprland
recomputes layout when sibling exclusive zones change.

## The Default Rule: Compositor-Driven Animation

Three of the four launcher surfaces — bookmarks, frequent, and backdrop —
follow the same pattern:

1. The Python code creates a plain `widgets.Window` with `visible=False`.
2. `toggle_launcher()` flips `window.set_visible(True/False)` (or, for
   backdrop close, runs the reverse-blur animation and *then* hides).
3. Hyprland's per-namespace `layerrule = animation slide …` (or
   `animation fade …`) handles the visual transition between hidden and
   visible.

There is **no GTK Revealer**, no manual fade, no `transition-property`
CSS on the panel container. The compositor owns the slide.

This is intentional — Hyprland's compositor animation is hardware-
accelerated, runs on the compositor's frame schedule (so it cooperates
with vsync), and can integrate with compositor-level features like
`layerrule = blur` if we ever want to re-enable that.

### Why Plain Window Won the Remediation Sprint

Earlier panel implementations used `RevealerWindow` (a thin Ignis wrapper
around `widgets.Window` with a built-in `widgets.Revealer`). That meant
**both** the GTK Revealer **and** the Hyprland layerrule were animating
the same surface simultaneously, with different durations and (for some
panels) different directions:

- **Bookmarks** worked by accident — both GTK and Hyprland slid left.
- **Frequent** failed visually — GTK `SLIDE_LEFT` (content disappears
  from the right edge first) conflicted with Hyprland `slide right`.
- **Search** lingered — GTK finished its 200ms crossfade while Hyprland
  was still running its ~500ms fade, leaving a visible tail.

The remediation sprint (commit `d22fecd`) removed `RevealerWindow` from
all three panels and rewrote `close_launcher()` as a simple
`set_visible(False)` loop. See [[20260225T072152714557306660]] for the
full debug history.

> **MEMORY.md note (as of 2026-02-26):** `MEMORY.md` says
> *"Panels use plain `widgets.Window`, NOT `RevealerWindow`. DO NOT use
> GTK Revealer with Hyprland layerrules — causes dual animation conflict."*
> That statement was true at the time of `d22fecd`. The Revealer was
> re-introduced **for the search panel only** in commit `94b83cf`, with
> explicit justification (next section). The dual-animation rule still
> applies — the search panel avoids it via `exclusivity="ignore"`.

## The Search Panel Exception

The search panel is the **only** Ignomi surface that uses GTK
`widgets.Revealer` for its open/close animation. It does so because of a
specific compositor behavior that affects centered Layer Shell surfaces.

### The Drift Bug

When all three panels closed simultaneously, the search panel — which is
horizontally centered (anchored only to top+bottom) — would visibly jump
**170 pixels to the left** mid-animation, then fade out from that
displaced position.

Direct measurement via `hyprctl layers` polling pinpointed the cause: the
moment the bookmarks panel hid (releasing its 340-pixel exclusive zone on
the left edge), Hyprland recomputed available width and re-centered the
search panel in the now-wider area. 170 = 340 ÷ 2 = exactly half of the
released exclusive zone, matching the observed shift to the pixel. See
[[20260226T022743651177993774]] for the smoking-gun position-polling
trace.

This is correct compositor behavior per the wlr-layer-shell protocol
(centered surfaces get re-centered when other surfaces' exclusive zones
change). It is also visually unacceptable for an animated close.

### The Fix: Two Things Together

The search panel's `widgets.Window` declaration uses **both** of:

```python
# launcher/panels/search.py:140-153
window = widgets.Window(
    namespace="ignomi-search",
    css_classes=["ignomi-window"],
    monitor=get_monitor_under_cursor(),
    anchor=["top", "bottom"],
    default_width=600,
    exclusivity="ignore",       # ← key change #1
    kb_mode="on_demand",
    layer="overlay",            # ← (overlay, not "top")
    visible=False,
    margin_top=8,
    margin_bottom=8,
    child=centered,
)
```

```python
# launcher/panels/search.py:125-130
self._revealer = widgets.Revealer(
    transition_type="crossfade",
    transition_duration=200,
    reveal_child=False,
    child=panel_content,
)
```

**Why both?** Each addresses one half of the problem:

- **`exclusivity="ignore"`** tells the compositor to ignore *all* other
  surfaces' exclusive zones when computing this surface's position. The
  search panel now occupies the same x-coordinate regardless of whether
  bookmarks/frequent are visible. This eliminates the layout
  recomputation that caused the drift.
- **`widgets.Revealer` (crossfade, 200ms)** then handles the close
  animation entirely in GTK. Because there is no longer a Hyprland
  layerrule slide on this namespace (the search panel's Hyprland
  layerrule is `animation []` — effectively a no-op), there is **no
  dual-animation conflict**. Revealer owns the animation outright.

### Wiring Detail: Hide-on-Animation-End

A `widgets.Revealer` with `reveal_child=False` only *visually* hides its
child — the surface itself remains mapped. To actually drop the layer
surface (so `kb_mode="on_demand"` releases keyboard focus and so the next
open re-creates a fresh surface on the correct monitor), the panel
listens for `notify::child-revealed`:

```python
# launcher/panels/search.py:168-173
def _on_child_revealed(self, revealer, param):
    """Hide window immediately when unreveal animation finishes."""
    if not revealer.get_child_revealed():
        window = revealer.get_root()
        if window:
            window.set_visible(False)
```

`close_launcher()` triggers the unreveal via a small helper that walks
the centering wrapper:

```python
# launcher/utils/helpers.py:280-293
def _close_search_panel(window):
    """Close the search panel with GTK Revealer animation.

    Traverses centering Box → Revealer. The notify::child-revealed
    signal on the Revealer hides the window when animation finishes.
    """
    # Window child is the centering Box; Revealer is its first child
    centering_box = window.get_child()
    if centering_box:
        revealer = centering_box.get_first_child()
        if revealer and hasattr(revealer, 'set_reveal_child'):
            revealer.set_reveal_child(False)
            return
    window.set_visible(False)
```

The fallback `window.set_visible(False)` at the end exists so a future
refactor that changes the widget tree doesn't accidentally leave the
search panel un-closeable.

## The Dual-Animation Rule

The lesson from the remediation sprint stands and remains current:

> **Never apply both a Hyprland `layerrule = animation …` and a GTK
> `widgets.Revealer` to the same Layer Shell surface.**

If two animation systems touch the same surface, they will fight — with
different durations, possibly different directions, and no shared concept
of "the animation is done." The visible result is either a dual-tail
(GTK finishes early, compositor lingers) or a misaligned slide (different
directions). Neither is a debuggable user-facing artifact; both consume
hours of investigation.

The current architecture obeys this rule by giving each surface exactly
one animation owner:

- **bookmarks, frequent, backdrop** — Hyprland owns the animation;
  GTK side is pure visibility flip.
- **search** — GTK Revealer owns the animation; Hyprland side is
  `animation []` no-op (and `exclusivity="ignore"` prevents layout
  recomputation as a side effect).

If you find yourself adding a `widgets.Revealer` to bookmarks, frequent,
or backdrop — **stop** and re-read [[20260225T072152714557306660]] first.

## Decision Tree for Future Surfaces

When adding a new Ignomi Layer Shell surface, choose its animation
strategy from this tree:

```
Does the surface have a hard edge anchor (left, right, top, bottom)?
├── YES → use plain widgets.Window
│         add a Hyprland layerrule for slide/fade animation
│         (do NOT add a Revealer)
│
└── NO (centered or overlay) →
    Does the surface coexist with any "exclusive" surfaces?
    ├── YES → set exclusivity="ignore"
    │         use widgets.Revealer for animation
    │         set the Hyprland layerrule animation to []
    │         (or to fade with matching duration if you must)
    │
    └── NO → either approach works; prefer plain Window + Hyprland
            for consistency with the existing 3 surfaces
```

## Cross-References

**Code:**

- [`launcher/panels/search.py`](../../launcher/panels/search.py) — the
  Revealer-based exception
- [`launcher/panels/bookmarks.py`](../../launcher/panels/bookmarks.py) —
  default rule
- [`launcher/panels/frequent.py`](../../launcher/panels/frequent.py) —
  default rule
- [`launcher/panels/backdrop.py`](../../launcher/panels/backdrop.py) —
  default rule + custom pixel-level animation (separate concern)
- [`launcher/utils/helpers.py:250-293`](../../launcher/utils/helpers.py)
  — `close_launcher`, `_close_backdrop`, `_close_search_panel`
- `~/.config/hypr/config/windowrules.conf` — Hyprland layerrules

**Related architecture docs:**

- [`2025-11-02-ignomi-launcher-design.md`](./2025-11-02-ignomi-launcher-design.md)
  — original design (animation section is now superseded)
- [`2026-04-30-backdrop-blur-pipeline.md`](./2026-04-30-backdrop-blur-pipeline.md)
  — describes backdrop's pixel-level animation, which is separate from
  the open/close visibility animation
- [`2026-04-30-search-router-architecture.md`](./2026-04-30-search-router-architecture.md)
  — search panel design (does not touch animation)

**Related zk-notes:**

- `[[20260225T072152714557306660]]` — animation debug hub: the original
  dual-animation conflict that motivated removing RevealerWindow
- `[[20260226T022743651177993774]]` — search panel drift root cause:
  the bug that motivated re-introducing Revealer for the search panel,
  combined with `exclusivity="ignore"`
- `[[20260227T035401098076654606]]` — toggle architecture: how
  `toggle_launcher()` sequences visibility changes atomically

## Outstanding Items

- **`MEMORY.md` is out of date.** The "Panels use plain `widgets.Window`,
  NOT `RevealerWindow`. DO NOT use GTK Revealer" line was true at
  `d22fecd` but does not reflect the current search panel design. Update
  recommended in next memory-maintenance pass; this is gap **G15** in
  the Phase 1 audit ([[YZ0fIVUNY3wCB0Sb32XGU]]).
- **`launcher/panels/backdrop.py`'s `layer="top"`** — backdrop currently
  uses `layer="top"` while the search panel uses `layer="overlay"`. The
  backdrop is *behind* the panels in z-order, which works because GTK
  picks z-order from window-creation order within the same layer. If a
  future refactor changes the creation order of `config.py`, the
  backdrop should explicitly move to `layer="background"` or the panels
  to `layer="overlay"`. Tracked informally; not currently broken.
