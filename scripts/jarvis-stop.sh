#!/usr/bin/env bash
# Kill switch: a running JARVIS agent stops before its next action.
touch "${XDG_RUNTIME_DIR:-/tmp}/jarvis.stop"
notify-send -a JARVIS -i process-stop "JARVIS" "Agent stopped" 2>/dev/null || true
