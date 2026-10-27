# ClipNest for Linux

Instant replay and screen recording, using your distribution's OBS Studio as the recording engine.

## Requirements

- 64-bit x86 Linux with Python 3.10 or newer (and `python3-venv` on Debian/Ubuntu)
- **OBS Studio 30 or newer, including 33, from your distribution's packages**. A Flatpak or Snap OBS keeps its libraries in a sandbox where ClipNest cannot load them. It can stay installed next to the distribution package.
  - Debian/Ubuntu/Mint: `sudo apt install obs-studio python3-venv`
  - Fedora: `sudo dnf install obs-studio`
  - Arch: `sudo pacman -S obs-studio`
  - openSUSE: `sudo zypper install obs-studio`
  - Void: `sudo xbps-install obs`
- Wayland: `xdg-desktop-portal` with your desktop's backend (KDE, GNOME, wlr or Hyprland). Most desktops install it already.
- Optional: `ffmpeg`, for the clip editor's exports. Recording does not need it. The editor does not use OBS, so an editor that works says nothing about OBS.

## Install

```sh
tar xzf ClipNest-2.1.4-linux-x64.tar.gz
cd ClipNest-2.1.4-linux-x64
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

**Frosted glass.** On Linux, Glass makes the window see-through with a dark tint. Desktops that blur transparent windows, such as Hyprland, frost it; GNOME and KDE show your desktop clearly behind the tint. Raise **Glass tint** in Settings → Appearance for a darker window. On X11, Glass needs a compositor (built into GNOME, KDE and Xfce); without one it stays opaque.

## Troubleshooting

- **Check what ClipNest finds.** Run this in a terminal and share the output when asking for help:

  ```sh
  ~/.local/bin/clipnest --check-obs
  ```

  It shows where ClipNest looked for OBS, the OBS version, the plugins it needs and, on Wayland, whether the screen-sharing portal is there.
- **"OBS Studio … was not found"**: install the distribution package above. ClipNest looks next to the `obs` command, in the system library cache, and in `/usr`, `/usr/local` and `/opt/obs-studio`. In each place it looks for OBS's plugin folder: `obs-modules/core` for OBS 33 and newer, `obs-plugins` for OBS 30 to 32. If OBS is somewhere else, start ClipNest with `CLIPNEST_OBS_PREFIX=/that/prefix`.
- Logs are in `~/.local/share/ClipNest/clipnest.log` and `native-engine.log`.
