#!/usr/bin/env bash
# Track app launches for frecency outside the launcher
# Usage: track-launch.sh firefox.desktop

set -euo pipefail

if [ $# -eq 0 ]; then
    echo "Usage: $0 <app-id>"
    echo "Example: $0 firefox.desktop"
    echo ""
    echo "This manually tracks app launches for frecency scoring."
    echo "Use this when launching apps outside the Ignomi launcher."
    exit 1
fi

APP_ID="$1"

# Run Python code to record launch
python3 <<EOF
import sys
sys.path.insert(0, '/home/komi/repos/ignomi/launcher')

from services.frecency import get_frecency_service

try:
    service = get_frecency_service()
    service.record_launch("$APP_ID")
    print(f"✓ Recorded launch: $APP_ID")
except Exception as e:
    print(f"✗ Error recording launch: {e}", file=sys.stderr)
    sys.exit(1)
EOF
