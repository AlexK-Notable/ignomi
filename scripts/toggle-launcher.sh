#!/usr/bin/env bash
# Toggle the Ignomi launcher (all panels) with correct multi-monitor placement.
#
# Uses `ignis run-python` to execute toggle logic inside the running Ignis
# process. This is required because wlr-layer-shell fixes the output (monitor)
# at surface creation time — we must set window.monitor BEFORE toggling
# visibility, which can only be done from within the process.

ignis run-python "from utils.helpers import toggle_launcher; toggle_launcher()"
