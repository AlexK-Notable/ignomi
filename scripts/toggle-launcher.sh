#!/usr/bin/env bash
# Toggle the Ignomi launcher (all three panels)

# Use ignis toggle-window which tracks visibility state internally
ignis toggle-window ignomi-bookmarks &
ignis toggle-window ignomi-search &
ignis toggle-window ignomi-frequent &
wait
