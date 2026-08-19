"""
Clipboard Screen - Clipboard history via elephant.

Reached from the home screen's nav bar; Escape returns there.

A screen rather than a search handler because clipboard history is
something you *browse* — you usually want the last few things you
copied, not the result of a query. It opens showing recent items with no
query at all, and the filter box is there for when you remember a word.

Ignis has no clipboard support whatsoever (a grep for `clipboard` and
`wl-copy` across the package returns nothing), so this is elephant's
`clipboard` provider.

Actions elephant exposes per item: copy, edit, pin, remove. Copy closes
the launcher, since the point of copying is to paste somewhere else.
Pin and remove keep the screen open so you can keep curating.
"""

import os
import sys

from gi.repository import Gdk
from loguru import logger

from ignis import widgets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.elephant import get_elephant_client

PROVIDER = "clipboard"
MAX_ITEMS = 50
PREVIEW_CHARS = 90


def summarize(item) -> str:
    """One-line preview of a clipboard entry.

    Newlines and runs of whitespace are collapsed, because a multi-line
    snippet would otherwise blow up the row height and push the rest of
    the history off screen.
    """
    if item.preview_type == "image":
        return "[image]"

    text = (item.text or "").strip()
    if not text:
        return "[empty]"

    collapsed = " ".join(text.split())
    if len(collapsed) > PREVIEW_CHARS:
        return collapsed[:PREVIEW_CHARS].rstrip() + "…"
    return collapsed


class ClipboardScreen:
    """Browse and act on clipboard history."""

    name = "clipboard"
    title = "Clipboard"
    icon = "edit-paste"
    show_in_nav = True
    description = "Browse clipboard history — copy, pin or remove entries"

    def __init__(self, client=None, max_items: int = MAX_ITEMS):
        self.client = client or get_elephant_client()
        self.max_items = max_items

        self._items = []
        self._filter_entry = None
        self._list_box = None
        self._status_label = None

    # --- Screen protocol ----------------------------------------------------

    def create_widget(self):
        """Build the clipboard screen. No elephant call happens here."""
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
                    label="Clipboard History",
                    css_classes=["systemd-title"],
                    hexpand=True,
                    xalign=0,
                ),
            ],
        )

        self._filter_entry = widgets.Entry(
            placeholder_text="Filter clipboard...",
            css_classes=["search-entry", "systemd-filter"],
            on_change=lambda _: self._refresh(),
        )

        self._list_box = widgets.ListBox(css_classes=["search-results"])

        self._status_label = widgets.Label(
            label="",
            css_classes=["systemd-status"],
            halign="center",
        )

        panel = widgets.Box(
            vertical=True,
            spacing=8,
            css_classes=["panel", "systemd-panel", "clipboard-panel"],
            child=[
                header,
                self._filter_entry,
                widgets.Scroll(
                    hexpand=True,
                    max_content_height=500,
                    propagate_natural_height=True,
                    child=self._list_box,
                ),
                self._status_label,
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

    def on_enter(self):
        """Always re-query — clipboard history changes constantly."""
        self._refresh()
        if self._filter_entry is not None:
            self._filter_entry.grab_focus()

    def on_leave(self):
        if self._filter_entry is not None:
            self._filter_entry.set_text("")

    def on_key_press(self, keyval, state) -> bool:
        """Up/Down move the selection, Enter copies the selected entry."""
        if self._list_box is None:
            return False

        rows = self._list_box.rows
        if not rows:
            return False

        selected = self._list_box.get_selected_row()
        current_idx = selected.get_index() if selected else -1

        if keyval == Gdk.KEY_Down:
            if current_idx < len(rows) - 1:
                self._list_box.select_row(rows[current_idx + 1])
            return True

        if keyval == Gdk.KEY_Up:
            if current_idx > 0:
                self._list_box.select_row(rows[current_idx - 1])
            return True

        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if selected is not None:
                identifier = getattr(selected, "_ignomi_id", None)
                if identifier:
                    self._act(identifier, "copy")
            return True

        return False

    # --- Data ---------------------------------------------------------------

    def _refresh(self):
        """Re-query elephant and redraw the list."""
        if self._list_box is None:
            return

        query = ""
        if self._filter_entry is not None:
            query = (self._filter_entry.text or "").strip()

        self._items = self.client.query(PROVIDER, query, self.max_items)

        self._list_box.remove_all()
        for item in self._items:
            self._list_box.append(self._create_row(item))

        rows = self._list_box.rows
        if rows:
            self._list_box.select_row(rows[0])

        self._set_status_for(query)

    def _set_status_for(self, query: str):
        if self._status_label is None:
            return

        if self._items:
            self._status_label.set_label("Enter copies · Esc goes back")
        elif not self.client.is_available():
            self._status_label.set_label(
                "Elephant daemon not running — start it with `elephant`"
            )
        elif query:
            self._status_label.set_label(f"Nothing in history matching '{query}'")
        else:
            self._status_label.set_label("Clipboard history is empty")

    # --- Rendering ----------------------------------------------------------

    def _create_row(self, item):
        """One history entry: preview, timestamp, and its actions."""
        text_block = widgets.Box(
            vertical=True,
            spacing=2,
            hexpand=True,
            child=[
                widgets.Label(
                    label=summarize(item),
                    css_classes=["app-name"],
                    xalign=0,
                    halign="start",
                    ellipsize="end",
                    max_width_chars=52,
                ),
                widgets.Label(
                    label=item.subtext or "",
                    css_classes=["app-description"],
                    xalign=0,
                    halign="start",
                    ellipsize="end",
                    max_width_chars=52,
                ),
            ],
        )

        actions = widgets.Box(
            spacing=4,
            halign="end",
            valign="center",
            child=[
                self._action_button("Copy", item, "copy"),
                self._action_button("Pin", item, "pin"),
                self._action_button("Remove", item, "remove"),
            ],
        )

        row = widgets.ListBoxRow(
            css_classes=["app-item", "result-item", "systemd-row"],
            child=widgets.Box(
                spacing=10,
                child=[
                    widgets.Icon(
                        image=(
                            "image-x-generic" if item.preview_type == "image"
                            else "edit-paste"
                        ),
                        pixel_size=20,
                    ),
                    text_block,
                    actions,
                ],
            ),
        )
        row._ignomi_id = item.identifier
        return row

    def _action_button(self, label: str, item, action: str):
        button = widgets.Button(
            css_classes=["systemd-action", f"clipboard-action-{action}"],
            on_click=lambda _, i=item.identifier, a=action: self._act(i, a),
            child=widgets.Label(label=label),
        )
        # Only offer what elephant says this item supports.
        if item.actions and action not in item.actions:
            button.set_sensitive(False)
        return button

    # --- Actions ------------------------------------------------------------

    def _act(self, identifier: str, action: str):
        """Run an elephant action on one entry.

        `copy` closes the launcher — you copied it to paste it somewhere.
        `pin` and `remove` are curation, so the screen stays open and
        refreshes to show the new state.
        """
        ok = self.client.activate(PROVIDER, identifier, action)

        if not ok:
            logger.warning(f"[clipboard] {action} failed for {identifier}")
            if self._status_label is not None:
                self._status_label.set_label(f"{action} failed")
            return

        if action == "copy":
            from utils.helpers import close_launcher

            close_launcher()
            return

        self._refresh()

    def _go_home(self):
        from panels.root import RootPanel

        root = RootPanel.get_default()
        if root is not None:
            root.screens.go_home()
