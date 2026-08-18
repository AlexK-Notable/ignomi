"""
Home Screen - The launcher's default screen.

This is the composition that used to live inline in
`RootPanel.create_window()`: bookmarks on the left, search in the
centre, frequent on the right. It moved here when screens were
introduced so that RootPanel owns *the window* and each screen owns
*its own content*.

Two things were added in the move:

  * a **nav bar** under the search panel, generated from the
    ScreenManager registry — every registered non-home screen gets a
    button automatically, so adding a screen never means editing this
    file; and
  * ownership of the **open/close reveal orchestration**
    (`set_revealed`), which RootPanel now delegates here.

Reveal vs. screen switching
---------------------------
`set_revealed()` is driven ONLY by the launcher window opening and
closing. Switching to another screen does NOT unreveal these panels —
the Stack crossfade in ScreenManager is the entire switch animation.
Running both would recreate the dual-animation conflict documented in
project-docs/architecture/2026-04-30-animation-architecture.md.
"""

import os
import sys

from ignis import widgets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panels.bookmarks import BookmarksPanel
from panels.frequent import FrequentPanel
from panels.search import SearchPanel


class HomeScreen:
    """Default screen: bookmarks | search + nav | frequent."""

    name = "home"
    title = "Home"
    icon = "go-home"
    show_in_nav = False  # you don't navigate to where the buttons live

    def __init__(self, manager, transition_duration: int = 200):
        """
        Args:
            manager: the ScreenManager, read at `create_widget()` time to
                build the nav bar. Held rather than passed per-call so
                the screen satisfies the no-arg `create_widget()`
                convention shared with the panels.
            transition_duration: reveal animation length in ms.
        """
        self._manager = manager
        self._duration = transition_duration

        self.bookmarks_panel = BookmarksPanel()
        self.search_panel = SearchPanel()
        self.frequent_panel = FrequentPanel()

        self._left_revealer = None
        self._right_revealer = None
        self._nav_revealer = None

    # --- Screen protocol ----------------------------------------------------

    def create_widget(self):
        """Build the home composition.

        Returns:
            widgets.Box — full-width HBox: left | centre (+nav) | right.
        """
        bookmarks_content = self.bookmarks_panel.create_widget()
        search_content = self.search_panel.create_widget()
        frequent_content = self.frequent_panel.create_widget()

        self._left_revealer = widgets.Revealer(
            transition_type="slide_right",
            transition_duration=self._duration,
            reveal_child=False,
            child=bookmarks_content,
            halign="start",
            valign="fill",
        )

        self._right_revealer = widgets.Revealer(
            transition_type="slide_left",
            transition_duration=self._duration,
            reveal_child=False,
            child=frequent_content,
            halign="end",
            valign="fill",
        )

        self._nav_revealer = widgets.Revealer(
            transition_type="crossfade",
            transition_duration=self._duration,
            reveal_child=False,
            child=self._create_nav_bar(),
            halign="center",
            valign="end",
        )

        # Centre column: search (expands, self-centres) with the nav bar
        # pinned beneath it.
        centre = widgets.Box(
            vertical=True,
            hexpand=True,
            vexpand=True,
            halign="center",
            valign="fill",
            child=[search_content, self._nav_revealer],
        )

        return widgets.Box(
            hexpand=True,
            vexpand=True,
            css_classes=["home-screen"],
            child=[self._left_revealer, centre, self._right_revealer],
        )

    def on_enter(self):
        """Returning from another screen — put the cursor back in search."""
        self.search_panel.focus_entry()

    def on_key_press(self, keyval, state) -> bool:
        """Delegate to the search panel's navigation handling.

        Escape is deliberately NOT handled here: RootPanel applies it as
        global policy before screens are consulted.
        """
        return self.search_panel.handle_key(keyval, state)

    # --- Open / close reveal ------------------------------------------------

    def set_revealed(self, revealed: bool):
        """Reveal or unreveal every home panel in parallel.

        Called by RootPanel on launcher open/close — never on screen
        switch.
        """
        self._left_revealer.set_reveal_child(revealed)
        self._right_revealer.set_reveal_child(revealed)
        self._nav_revealer.set_reveal_child(revealed)
        self.search_panel.set_revealed(revealed)

    # --- Nav bar ------------------------------------------------------------

    def _create_nav_bar(self):
        """Build one button per registered non-home screen.

        Reads `ScreenManager.nav_screens()`, so registering a new screen
        is the only step needed to get a button for it.
        """
        buttons = [
            self._create_nav_button(screen)
            for screen in self._manager.nav_screens()
        ]

        return widgets.Box(
            spacing=8,
            halign="center",
            css_classes=["nav-bar"],
            margin_bottom=24,
            margin_top=12,
            child=buttons,
        )

    def _create_nav_button(self, screen):
        """One nav button: icon + label, switches to `screen` on click."""
        return widgets.Button(
            css_classes=["nav-button"],
            on_click=lambda _, name=screen.name: self._manager.switch_to(name),
            child=widgets.Box(
                spacing=8,
                halign="center",
                valign="center",
                child=[
                    widgets.Icon(
                        image=getattr(screen, "icon", "application-x-executable"),
                        pixel_size=16,
                        css_classes=["nav-icon"],
                    ),
                    widgets.Label(
                        label=getattr(screen, "title", screen.name),
                        css_classes=["nav-label"],
                    ),
                ],
            ),
        )
