#!/usr/bin/env bash
# Toggle the Ignomi launcher (all three panels)
#
# Signal handlers in each panel automatically update monitor placement
# when windows become visible, so we just toggle visibility.
# Focus is handled by Python code that moves cursor to search entry.

# Toggle all three panels (visibility signal will handle monitor placement)
ignis toggle-window ignomi-bookmarks &
ignis toggle-window ignomi-search &
ignis toggle-window ignomi-frequent &
wait
