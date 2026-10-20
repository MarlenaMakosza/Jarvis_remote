#!/usr/bin/env bash
# Bind the JARVIS kill switch to a global KDE shortcut (default Meta+Esc).
# Usage: scripts/install-killswitch.sh [shortcut]
set -euo pipefail
SHORTCUT="${1:-Meta+Esc}"
HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/.local/share/applications/jarvis-stop.desktop"

chmod +x "$HERE/jarvis-stop.sh"
mkdir -p "$(dirname "$APP")"
cat > "$APP" <<DESKTOP
[Desktop Entry]
Type=Application
Name=JARVIS stop
Comment=Stop the JARVIS_REMOTE agent
Exec=$HERE/jarvis-stop.sh
Icon=process-stop
NoDisplay=true
X-KDE-GlobalAccel-CommandShortcut=true
DESKTOP

# Keep a copy of the shortcut config before the first change.
cp -n "$HOME/.config/kglobalshortcutsrc" "$HOME/.config/kglobalshortcutsrc.jarvis-backup" 2>/dev/null || true
kwriteconfig6 --file kglobalshortcutsrc --group services --group jarvis-stop.desktop --key _launch "$SHORTCUT"
kbuildsycoca6 >/dev/null 2>&1 || true
echo "Bound $SHORTCUT to $APP."
echo "If it does not fire, log out and back in, or set it in System Settings > Shortcuts."
