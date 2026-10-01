# ClipNest 1.5.1

Windows screen recording, instant replay, and clip editing, powered by OBS/libobs.

## Install and launch

**Windows installer:** run `ClipNest-Setup-1.5.1-x64.exe`, then open ClipNest from the Start menu or optional desktop shortcut. Python and a separate OBS installation are not required. Internet is needed on first launch to download the private OBS runtime.

**Source ZIP:** install 64-bit Python 3.11–3.13, extract the ZIP, and run `Start_ClipNest.bat` once. Afterwards, use `Launch_ClipNest.vbs` to launch without a console window. The source ZIP does not include a prebuilt installer or Python runtime.

## Requirements

- Windows 10/11 x64.
- FFmpeg and ffprobe for continuous replay, editing, and thumbnails, unless included in your installer. Select their folder under the editor's **File → FFmpeg folder**. The default installer build does not bundle these tools.
- Compatible NVIDIA hardware/drivers for NVENC and AV1. CPU H.264 is also available.
- Local NTFS storage for continuous replay and exports.

### FFmpeg setup

Select the folder containing the actual `ffmpeg.exe` and `ffprobe.exe` files, usually named `bin`. If you installed FFmpeg with WinGet, look under `%LOCALAPPDATA%\Microsoft\WinGet\Packages` for the FFmpeg package and its `bin` folder. Selecting the aliases in `WinGet\Links` can cause Windows error 448 (untrusted mount point).

## Features

- Configurable instant replay and simultaneous manual recording.
- Classic RAM replay or continuous disk replay, with consecutive saves within the retained time window.
- Automatic game folders and application filenames, plus manual game registration.
- Separate desktop, microphone, and combined audio tracks.
- Microphone selection, gain, mute, and push-to-talk.
- Configurable shortcuts, recording resolution, frame rate, bitrate, and encoder.
- Recent clip gallery with Recycle Bin deletion, searchable clip browser, and quick playback.
- Editor with trimming, visual cropping, color adjustments, audio gains/remixing, and export presets.
- H.264 and AV1 hardware exports where supported, plus CPU H.264.
- Compact, silent visual notifications.

## Screenshots

<img width="1477" height="1039" alt="image" src="https://github.com/user-attachments/assets/b8735c63-1e02-4f9f-852e-2bd133064f11" />
<img width="1477" height="1039" alt="image" src="https://github.com/user-attachments/assets/07f97bea-a0b0-4f7a-b8ed-030f42c9880f" />
<img width="1702" height="989" alt="image" src="https://github.com/user-attachments/assets/253f4025-c638-4a65-bb76-a3451c62043e" />

## Updates and settings

Finish recording and fully quit ClipNest, including its tray instance, before updating. Run the newer installer over the existing installation, or extract a newer source ZIP into a fresh folder.

Settings and the private recorder runtime remain in `%LOCALAPPDATA%\ClipNest`. Recordings and exports stay in your selected folders. Uninstall retains these user files.

## New in 1.5.1

ClipNest branding now appears on installed shortcuts, the installer, app windows, and tray. The installer build launcher explicitly selects a supported Python version. Installer packaging includes a private Python runtime and a graphical first-run OBS setup.

To build the installer yourself, see [packaging/BUILD.md](packaging/BUILD.md).

Per-application audio isolation and automatic device reconnection remain future work. Capture, playback, and encoding performance depend on your hardware and drivers.

Source license: GPL-2.0-or-later. See [LICENSE.txt](LICENSE.txt) and [THIRD_PARTY.md](THIRD_PARTY.md). ClipNest is independent of OBS and NVIDIA.
