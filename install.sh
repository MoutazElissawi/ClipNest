#!/bin/sh
# Install ClipNest for the current user: no root, nothing outside your home folder.
# App: ~/.local/share/clipnest-app   Command: ~/.local/bin/clipnest
# Settings and clips are kept by reinstalling and by uninstall.sh.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
PREFIX="$DATA_HOME/clipnest-app"
BIN="$HOME/.local/bin"
PYTHON=${PYTHON:-python3}

say() { printf '%s\n' "$*"; }
fail() { printf 'ClipNest install: %s\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = Linux ] || fail "this installer is for Linux."
[ "$(uname -m)" = x86_64 ] || fail "ClipNest needs a 64-bit x86 (x86_64) PC."

command -v "$PYTHON" >/dev/null 2>&1 || fail "Python 3.10 or newer is required (install python3)."
"$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 10))' || fail "Python 3.10 or newer is required; found $("$PYTHON" -V 2>&1)."
"$PYTHON" -c 'import venv, ensurepip' 2>/dev/null || fail "Python's venv module is missing. Debian/Ubuntu: sudo apt install python3-venv"

# Recording uses your distribution's OBS Studio 30+ (a Flatpak or Snap OBS keeps its libraries in
# its sandbox). This is the same search ClipNest runs when it starts.
(cd "$HERE" && "$PYTHON" -c '
from clipnest import platforms
try:
    platforms.obs_layout()
except RuntimeError as error:
    print("WARNING: ClipNest installs, but recording needs OBS Studio 30 or newer.\n" + str(error) + "\n")
') || true
command -v ffmpeg >/dev/null 2>&1 || say "Note: install ffmpeg to use the clip editor's exports (recording does not need it)."

say "Installing ClipNest into $PREFIX ..."
mkdir -p "$PREFIX"
rm -rf "$PREFIX/app.new"
mkdir -p "$PREFIX/app.new"
cp -R "$HERE/clipnest" "$HERE/main.py" "$HERE/requirements.txt" "$HERE/LICENSE.txt" "$HERE/THIRD_PARTY.md" "$PREFIX/app.new/"
find "$PREFIX/app.new" -name '__pycache__' -type d -prune -exec rm -rf {} +

if [ ! -x "$PREFIX/venv/bin/python" ]; then
    "$PYTHON" -m venv "$PREFIX/venv"
fi
"$PREFIX/venv/bin/python" -m pip install --disable-pip-version-check --quiet --upgrade pip
"$PREFIX/venv/bin/python" -m pip install --disable-pip-version-check --quiet -r "$PREFIX/app.new/requirements.txt"
"$PREFIX/venv/bin/python" -c 'import PySide6.QtWidgets, PySide6.QtMultimedia, psutil, numpy' \
    || fail "the Python packages did not import. Check the messages above."

rm -rf "$PREFIX/app.old"
[ -d "$PREFIX/app" ] && mv "$PREFIX/app" "$PREFIX/app.old"
mv "$PREFIX/app.new" "$PREFIX/app"
rm -rf "$PREFIX/app.old"

mkdir -p "$BIN"
cat > "$BIN/clipnest" <<EOF
#!/bin/sh
# ClipNest launcher. Bind "clipnest --save-replay" to a system shortcut on Wayland.
cd "$PREFIX/app" && exec "$PREFIX/venv/bin/python" "$PREFIX/app/main.py" "\$@"
EOF
chmod 755 "$BIN/clipnest"

ICONS="$DATA_HOME/icons/hicolor/512x512/apps"
mkdir -p "$ICONS" "$DATA_HOME/applications"
cp "$PREFIX/app/clipnest/assets/clipnest.png" "$ICONS/clipnest.png"
cat > "$DATA_HOME/applications/clipnest.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=ClipNest
GenericName=Instant replay recorder
Comment=Instant replay and screen recording with a clip editor
Exec=$BIN/clipnest
Icon=clipnest
Terminal=false
Categories=AudioVideo;Video;Recorder;
Keywords=clip;replay;record;obs;game;
StartupWMClass=ClipNest
Actions=SaveReplay;ToggleRecord;

[Desktop Action SaveReplay]
Name=Save instant replay
Exec=$BIN/clipnest --save-replay

[Desktop Action ToggleRecord]
Name=Start or stop recording
Exec=$BIN/clipnest --toggle-record
EOF
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true

say ""
say "ClipNest is installed. Open it from your applications menu, or run: $BIN/clipnest"
case ":$PATH:" in *":$BIN:"*) ;; *) say "($BIN is not on your PATH; use the full path above or add it.)";; esac
say "Wayland: add a system keyboard shortcut for '$BIN/clipnest --save-replay' to save replays from any app."
