"""
Shortcuts Screen - What can I actually type in here?

A cheat sheet for the launcher: every search-bar prefix, every screen,
and the keys that work.

Generated, not written
----------------------
The prefix list is built by reading the **live** `QueryRouter` registry
and the **live** `ScreenManager` registry at render time. Nothing here
is a hand-maintained list of what the launcher supports, because a
hand-maintained list is wrong the first time someone adds a handler and
forgets to update it — which is exactly the failure this screen exists
to prevent.

A handler documents itself with three optional attributes:

    prefixes    list[str]  e.g. [":"] — omit for keyword/fallback handlers
    description str        one line, what it does
    example     str        something the user can literally type

They are read with `getattr`, so a handler that declares none of them
still appears (by name) rather than breaking the screen.

The one hand-maintained part is `KEY_BINDINGS` below — key handling
lives across RootPanel and the individual screens' `on_key_press`, and
there is no registry to read it from. Keep it in sync by hand; it is
short.
"""

import os
import sys

from ignis import widgets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Hand-maintained: there is no registry of key handlers to generate from.
# Sources: RootPanel._on_key_press (global), SearchPanel.handle_key,
# SystemdScreen/ClipboardScreen.on_key_press.
KEY_BINDINGS = [
    ("Enter", "Activate the selected result"),
    ("Up / Down", "Move through results"),
    ("Escape", "Back to home — or close, if already home"),
    ("Click outside", "Close the launcher"),
]


class ShortcutsScreen:
    """Self-documenting reference for the launcher's capabilities."""

    name = "shortcuts"
    title = "Shortcuts"
    icon = "help-about"
    show_in_nav = True

    def __init__(self, router=None, manager=None):
        """
        Args:
            router: the QueryRouter whose handlers get documented.
            manager: the ScreenManager whose screens get documented.

        Both are optional so the screen degrades to whatever it can see
        rather than failing to build.
        """
        self._router = router
        self._manager = manager

    # --- Screen protocol ----------------------------------------------------

    def create_widget(self):
        back_button = widgets.Button(
            css_classes=["systemd-back"],
            on_click=lambda _: self._go_home(),
            child=widgets.Box(
                spacing=6,
                child=[
                    widgets.Icon(image="go-previous", pixel_size=16),
                    widgets.Label(label="Back"),
                ],
            ),
        )

        header = widgets.Box(
            spacing=12,
            css_classes=["systemd-header"],
            child=[
                back_button,
                widgets.Label(
                    label="Shortcuts",
                    css_classes=["systemd-title"],
                    hexpand=True,
                    xalign=0,
                ),
            ],
        )

        body = widgets.Box(vertical=True, spacing=4, child=self._build_sections())

        panel = widgets.Box(
            vertical=True,
            spacing=8,
            css_classes=["panel", "systemd-panel", "shortcuts-panel"],
            child=[
                header,
                widgets.Scroll(
                    hexpand=True,
                    max_content_height=520,
                    propagate_natural_height=True,
                    child=body,
                ),
            ],
        )

        return widgets.Box(
            vertical=True,
            hexpand=True,
            vexpand=True,
            halign="center",
            valign="center",
            child=[panel],
        )

    # --- Section assembly ---------------------------------------------------

    def _build_sections(self) -> list:
        sections = []

        prefixed, unprefixed = self._split_handlers()

        if prefixed:
            sections.append(self._section("Type in the search bar", prefixed))
        if unprefixed:
            sections.append(self._section("Also in the search bar", unprefixed))

        screens = self._screen_rows()
        if screens:
            sections.append(self._section("Panels", screens))

        sections.append(self._section(
            "Keys",
            [(key, desc) for key, desc in KEY_BINDINGS],
        ))

        return sections

    def _split_handlers(self):
        """Turn the router registry into (prefixed, unprefixed) row lists.

        Rows are `(left, right)` — left is what you type, right is what
        it does.
        """
        prefixed, unprefixed = [], []

        if self._router is None:
            return prefixed, unprefixed

        for handler in self._router.handlers:
            description = getattr(handler, "description", "") or handler.name
            example = getattr(handler, "example", "")
            prefixes = getattr(handler, "prefixes", None)
            # Optional per-prefix labels. Web search declares five
            # prefixes; without these each row said "Search the web",
            # which answers nothing — the actual question is *which*
            # engine `gh:` is.
            prefix_help = getattr(handler, "prefix_help", None) or {}

            if prefixes:
                # One row per prefix so every trigger is discoverable.
                for prefix in prefixes:
                    right = prefix_help.get(prefix) or description
                    if (
                        prefix not in prefix_help
                        and example
                        and example.startswith(prefix)
                    ):
                        right = f"{description}  (e.g. {example})"
                    prefixed.append((f"{prefix}…", right))
            else:
                # `trigger_label` describes what to type. Falling back to
                # `example` would print "firefox" in the key column and
                # read as though firefox were a special command, rather
                # than an example of the any-text fallback.
                left = getattr(handler, "trigger_label", "") or example or handler.name
                unprefixed.append((left, description))

        return prefixed, unprefixed

    def _screen_rows(self) -> list:
        """Document the nav-bar screens from the live registry."""
        if self._manager is None:
            return []

        rows = []
        for screen in self._manager.nav_screens():
            if screen.name == self.name:
                continue  # don't document the shortcuts screen in itself
            rows.append((
                getattr(screen, "title", screen.name),
                getattr(screen, "description", "Open the panel"),
            ))
        return rows

    # --- Rendering ----------------------------------------------------------

    def _section(self, heading: str, rows: list):
        children = [
            widgets.Label(
                label=heading,
                css_classes=["shortcuts-heading"],
                xalign=0,
                halign="start",
            )
        ]
        children.extend(self._row(left, right) for left, right in rows)

        return widgets.Box(
            vertical=True,
            spacing=2,
            css_classes=["shortcuts-section"],
            child=children,
        )

    @staticmethod
    def _row(left: str, right: str):
        """One reference row: what to type, and what it does.

        The description **wraps** rather than ellipsizing. This is a
        reference screen — a description cut off at the panel edge fails
        at the one job the screen has. Wrapping costs a little height and
        the panel scrolls; truncating loses the information entirely.
        """
        return widgets.Box(
            spacing=12,
            valign="start",
            css_classes=["shortcuts-row"],
            child=[
                widgets.Label(
                    label=left,
                    css_classes=["shortcuts-key"],
                    xalign=0,
                    halign="start",
                    valign="start",
                    width_chars=12,
                ),
                widgets.Label(
                    label=right,
                    css_classes=["shortcuts-desc"],
                    xalign=0,
                    halign="start",
                    valign="start",
                    hexpand=True,
                    wrap=True,
                    wrap_mode="word",
                    max_width_chars=48,
                ),
            ],
        )

    def _go_home(self):
        from panels.root import RootPanel

        root = RootPanel.get_default()
        if root is not None:
            root.screens.go_home()
