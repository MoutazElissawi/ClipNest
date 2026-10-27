# ClipNest for Linux

Instant replay and screen recording, using your distribution's OBS Studio as the recording engine.

## Requirements

- 64-bit x86 Linux with Python 3.10 or newer (and `python3-venv` on Debian/Ubuntu)
- **OBS Studio 30 or newer from your distribution's packages**. The Flatpak keeps its libraries in a sandbox where ClipNest cannot load them.
  - Debian/Ubuntu: `sudo apt install obs-studio python3-venv`
  - Fedora: `sudo dnf install obs-studio`
  - Arch: `sudo pacman -S obs-studio`
- Optional: `ffmpeg`, for the clip editor's exports. Recording does not need it.

## Install

```sh
tar xzf ClipNest-2.1.1-linux-x64.tar.gz
cd ClipNest-2.1.1-linux-x64
./install.sh
```

The installer needs no root and writes only to your home folder:

- the app goes in `~/.local/share/clipnest-app`
- the command is `~/.local/bin/clipnest`
- it adds an entry to your applications menu

Run it again to update. `./uninstall.sh` removes the app and keeps your settings and clips.

## What works on Linux

- **Entire display** capture:
  - X11 captures the screen you choose in Settings.
  - Wayland asks once through the system's screen-share dialog, and ClipNest remembers your choice for later sessions.
- System audio and microphone (PipeWire or PulseAudio), each on its own track as on Windows.
- Encoders:
  - NVIDIA (NVENC)
  - AMD/Intel (VAAPI)
  - CPU x264, the default. Pick a hardware encoder in Settings → Encoder if your OBS supports it.
- Instant replay, recording, the clip library and the editor.

**Shortcuts.** On X11, global shortcuts and push-to-talk work as on Windows. Wayland does not let apps grab keys everywhere:

- ClipNest's shortcuts work while an XWayland window is focused, which covers most Steam/Proton games.
- To save from any app, add a system keyboard shortcut in your desktop's settings that runs:

  ```sh
  ~/.local/bin/clipnest --save-replay
  ```

  `clipnest --toggle-record` starts or stops recording the same way. Both also appear when you right-click ClipNest in the applications menu.

## Not available on Linux yet

- **Games only**, window capture and game capture: these use Windows game hooks. On Linux, record the display.
- Game-only audio and the per-application audio track.

## Troubleshooting

- **"OBS Studio was not found"**: install the distribution package above. If OBS is installed under a custom prefix, start ClipNest with `CLIPNEST_OBS_PREFIX=/that/prefix`.
- Logs are in `~/.local/share/ClipNest/clipnest.log` and `native-engine.log`.
