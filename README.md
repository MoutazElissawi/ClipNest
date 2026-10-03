# ClipNest v1.8.0

Windows screen recording, instant replay and clip editing with a private direct-libobs recorder.

## New in 1.8.0

- Game sorting now keeps process names when executable access fails, adds a limited-access Windows lookup, and expires failed foreground reads. Replay category is captured when Save is requested.
- Gallery storage bar shows completed clip usage and actual drive free space. Settings → Capture has an optional **warning-only** library limit; 0 means unlimited. Clips are never automatically deleted and recording stays enabled. A separate warning appears below 10 GB free.
- Search recent clips or **Browse all clips** by game, filename, date (`YYYY-MM-DD`) and tags. Ctrl-click to select several clips, set favorites, or replace their tags. Favorites and tags are saved locally without editing video files.
- Export presets now include resolution/FPS. Quick choices offer 1080p60, smaller 720p30 and vertical 1080p60 with padding. Estimates include the selected audio tracks; progress shows approximate time remaining.
- Select two or more clips and choose **Combine…**. Reorder them, review duration and audio tracks, then select a new destination. Compatible streams can be copied; otherwise choose re-encoding. Re-encoding uses the first clip's size, 60 FPS and stereo/48 kHz for each audio track. Different track counts are blocked; different titles require explicit matching by position. Original clips are protected.

Storage totals exclude `_Unsorted`, replay caches, hidden temporary folders and linked folders. Usage refreshes after gallery actions and every 30 seconds. GB uses decimal units. Favorites/tags follow same-volume renames and moves on filesystems with stable IDs; cross-volume copies are treated as new clips. The gallery searches its latest 24 clips; Browse all clips searches up to 10,000.

The existing glass appearance, recorder architecture and shutdown safeguards are retained. This source release still needs Windows hardware checks for Helldivers detection, capture, glass and NVENC. It does not include a compiled installer.

## Enable frosted glass

Open **Settings → Appearance** and choose **Frosted glass**. The choice saves automatically. Fully quit ClipNest and reopen it using the normal shortcut once to activate its translucent window frame.

If **Current effect** reports disabled transparency, click **Open Windows transparency settings** and turn on **Transparency effects** in **Personalization → Colors**. Return to ClipNest or click **Refresh glass effect**; this does not require restarting. If the status reports High Contrast, Windows must leave that mode before glass can activate. ClipNest does not change either Windows preference automatically.

Adjust **Glass tint** to reveal more or less of the desktop; it previews and saves immediately. Drag the title bar to move, double-click to maximize/restore, and drag any edge or corner to resize. Classic dark restores the standard Windows frame after restart. Windows 10 uses compatibility blur and may retain square outer corners; Windows 11 22H2+ uses desktop acrylic when available. This is a Windows implementation inspired by the reference, not Apple's Liquid Glass framework.

If glass prevents startup, fully close ClipNest and run **Launch_Classic_Mode.bat** inside the installation folder. This temporarily uses Classic mode without erasing the saved appearance. Choose Classic in Appearance to keep it for normal launches.

## Closing with active capture

The recorder gets up to 20 seconds to finalize normally. A replay file job gets up to 25 seconds; repeated cleanup errors can end the wait sooner. Capture cannot restart after Quit. If native cleanup stalls, ClipNest terminates its own recorder process and retains unfinished files in `_Unsorted` and `_Unsorted/_ReplayCache`. A forced stop can lose queued tail frames; retained files are not guaranteed to be complete exports. Completed clips are kept. Check **File → Open recorder logs** if a timeout occurs.

Windows native blur, capture shutdown, and installer launch still require hardware validation. Automated checks use simulated libobs calls, real child processes, offscreen Qt and real FFmpeg files.

## Install and launch

**Windows installer:** run `ClipNest-Setup-1.8.0-x64.exe`, then open ClipNest from the Start menu or optional desktop shortcut. Python and a separate OBS installation are not required. Internet is needed on first launch to download the private OBS runtime.

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
- Microphone selection, gain, mute, and push-to-talk. Live audio-device reconnect and playback following the Windows default output.
- Configurable shortcuts, recording resolution, frame rate, bitrate, and encoder.
- Recent clip gallery with Recycle Bin deletion, searchable clip browser, and quick playback.
- Editor with trimming, visual cropping, color adjustments, audio gains/remixing, and export presets.
- H.264 and AV1 hardware exports where supported, plus CPU H.264.
- Compact, silent visual notifications.
- Optional **Frosted glass** under **Settings → Appearance**: a transparent window with native desktop blur, rounded cards, and a custom draggable title bar. Windows 11 uses desktop acrylic; Windows 10 uses a compatibility blur. Unsupported/disabled transparency falls back to an opaque surface.

## Screenshots

These screenshots show an earlier interface; v1.7.6 retains the updated window chrome and glass styling.

<img width="1477" height="1039" alt="image" src="https://github.com/user-attachments/assets/b8735c63-1e02-4f9f-852e-2bd133064f11" />
<img width="1477" height="1039" alt="image" src="https://github.com/user-attachments/assets/07f97bea-a0b0-4f7a-b8ed-030f42c9880f" />
<img width="1702" height="989" alt="image" src="https://github.com/user-attachments/assets/253f4025-c638-4a65-bb76-a3451c62043e" />

## Updates and settings

Finish recording and fully quit ClipNest, including its tray instance, before updating. Run the newer installer over the existing installation, or extract a newer source ZIP into a fresh folder.

Settings and the private recorder runtime remain in `%LOCALAPPDATA%\ClipNest`. Recordings and exports stay in your selected folders. Uninstall retains these user files.

## New in 1.7.0

- Recovery after Windows sleep, unlock, and display-mode changes rebuilds the private recorder and restarts previously active outputs. Recording is finalized and continued in a **new file**; replay starts a **fresh buffer**. These interruptions are not gapless. Consecutive replay saves during an uninterrupted session still use the existing gapless segment path.
- **Settings → Audio → Apply / reconnect audio** applies your selected devices while video continues. Automatic endpoint-change handling reconnects available audio sources. A named device stays pinned; **System default** follows Windows. A brief audio gap during endpoint switching is expected.
- Gallery and editor playback follow the Windows playback output when switching between speakers, monitor/IEM output, and Bluetooth devices. Capture choices and playback output are separate.
- Smaller, eased gallery/browser wheel steps; native pixel scrolling for trackpads.
- Quick player and editor restore centered on the invoking monitor and fit its available work area.
- **Open folder** in the quick player selects the actual clip in Explorer, including filenames with spaces or commas.
- Removed the green audio-table cell selection and dotted gallery text rectangles; keyboard gallery navigation retains a subtle focus border.
- Real alpha-backed glass windows with native blur, plus the approved dark-tile ClipNest icon.
- Corrected the OBS NVENC adaptive-quantization option. **Settings → Video → NVIDIA effort** offers P1/P3/P4/P5; P4 remains the default. Single-pass encoding and disabled lookahead are explicit. Recording and replay continue sharing one video encoder and three audio encoders.
- Dashboard capture FPS/render-time/lag counters help compare configurations. They are **not GPU-utilization measurements**.

For lower encoder load, try Efficient (P3) or Fastest (P1), accepting a quality tradeoff at the same bitrate. Resolution and FPS have a major effect. Compare against other recorders at matching codec, dimensions, FPS, bitrate and scene; no measured GPU-use reduction is claimed for this release.

Keep Windows **Transparency effects** enabled to see native glass. High contrast or disabled transparency produces an opaque fallback. Windows 10's blur compatibility API is undocumented and may differ by OS build/driver; Classic dark remains available. The appearance is inspired by the approved concept, not Apple's Liquid Glass framework.

This release was tested on Linux with offscreen Qt, real FFmpeg media tests, and simulated native recorder tests. Windows sleep/DXGI recovery, HDMI/Bluetooth endpoints, native backdrop appearance, native window interactions and GPU utilization require testing on Windows. A frozen picture can have causes other than sleep; recovery handles Windows lifecycle events and does not mistake a motionless desktop for a capture failure.

Installed builds use branded `ClipNest.exe` and `ClipNest Recorder` entry points. Unbuilt source launched through Python still appears as Python. Rebuild the installer for the updated code, icon and version metadata.

Normally closing finishes active recordings and exits automatically. If an output stalls for 20 seconds, ClipNest asks libobs to stop it immediately; this recovery may omit queued frames at the end. Pending clip work is completed where possible, and unresolved files remain in `_Unsorted` / `_ReplayCache`. A completely deadlocked native host can still prevent graceful exit; the app does not forcibly terminate it.

To build the installer yourself, see [packaging/BUILD.md](packaging/BUILD.md).

Per-application audio isolation remains future work. Capture, playback, and encoding performance depend on your hardware and drivers.

Source license: GPL-2.0-or-later. See [LICENSE.txt](LICENSE.txt) and [THIRD_PARTY.md](THIRD_PARTY.md). ClipNest is independent of OBS and NVIDIA.
