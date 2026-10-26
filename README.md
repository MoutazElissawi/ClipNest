# ClipNest

Windows screen recorder with instant replay, automatic game folders, a clip gallery and a lightweight editor.

## How to launch

**Installer (recommended)**
1. Download `ClipNest-Setup-<version>-x64.exe` from the [Releases](../../releases) page and run it. No administrator rights are needed.
2. Open **ClipNest** from the Start menu. The first launch downloads its recording engine, so it needs internet.
3. To use instant replay, editing and thumbnails, install [FFmpeg](https://ffmpeg.org/download.html). In ClipNest's editor, choose **File → FFmpeg folder** and select the folder that contains `ffmpeg.exe` and `ffprobe.exe` (usually `bin`).

**From source**
1. Install 64-bit [Python 3.11–3.13](https://www.python.org/downloads/windows/) with the Python launcher.
2. Download this repository and double-click `Start_ClipNest.bat`. The first run installs what it needs; later runs start ClipNest directly.

**If ClipNest won't open** after you turn on frosted glass, run `Launch_Classic_Mode.bat` (it's also in the installation folder at `%LOCALAPPDATA%\Programs\ClipNest`).

## Requirements
- Windows 10 version 2004 or newer, or Windows 11 (64-bit).
- FFmpeg and ffprobe (not included).
- An NVIDIA or AMD GPU for hardware encoding; CPU encoding always works.

## Features
- Instant replay with a hotkey, plus manual recording at the same time.
- Games only (the default): records just the game you are playing, never the desktop or other apps. Alt-Tab keeps the game in the clip, a minimized game records black, and the replay never restarts. Games that hide from screen capture, such as VALORANT, are recorded too.
- Or record one display, all displays stitched into one video, or a single window.
- Separate Mix, Desktop and Microphone audio tracks, plus an optional track for one app (e.g. Spotify). Optionally record only the game's audio. Push-to-talk and mic controls.
- Clips are sorted into folders by game automatically.
- Gallery with search, favorites, tags, a game filter and quick playback.
- Editor: trim, crop, colors, per-track volume and muting, export to MKV, MP4, MP3, M4A, WAV or FLAC, or Copy (no re-encode) for instant lossless trims.
- Black-and-green theme, optional frosted glass, and custom color themes (Settings → Appearance → Save theme template, edit the JSON, then Load theme).

## Updating and your files
Quit ClipNest (including the tray icon) and run the newer installer. Settings live in `%LOCALAPPDATA%\ClipNest`; recordings stay in the folder you chose. Uninstalling keeps both.

## Building the installer
Run `packaging\Build_Installer.bat` (needs Python 3.11–3.13 and Inno Setup 6.3+). Details: [packaging/BUILD.md](packaging/BUILD.md).

## License
GPL-2.0-or-later. See [LICENSE.txt](LICENSE.txt) and [THIRD_PARTY.md](THIRD_PARTY.md). ClipNest uses the OBS recording engine (libobs) and is not affiliated with OBS, NVIDIA, AMD or Riot Games.
