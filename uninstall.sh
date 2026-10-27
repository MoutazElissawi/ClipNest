#!/bin/sh
# Remove ClipNest for the current user. Your settings (~/.local/share/ClipNest) and clips are kept.
set -eu
DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
if pgrep -f "clipnest-app/app/main.py" >/dev/null 2>&1; then
    echo "ClipNest is running. Quit it from its tray icon first, so no recording is cut off." >&2
    exit 1
fi
rm -rf "$DATA_HOME/clipnest-app"
rm -f "$HOME/.local/bin/clipnest" "$DATA_HOME/applications/clipnest.desktop" "$DATA_HOME/icons/hicolor/512x512/apps/clipnest.png"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
echo "ClipNest was removed. Settings remain in $DATA_HOME/ClipNest; delete that folder to remove them too."
