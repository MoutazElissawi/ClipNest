# ClipNest 1.2.0 — recent gallery and quick player

## New gallery

Open **Clips & games** to see the latest 24 completed clips from your configured clips folder, including previous sessions. Each card shows a thumbnail, duration, game/folder, date and filename. Click once to watch. The gallery refreshes when opened, after a new clip is saved, or with Refresh. Browse all clips opens the existing searchable folder browser and then the same quick player.

The gallery skips `_Unsorted`, `_ReplayCache`, hidden temporary folders, empty files and symlinks. Scanning runs in the background and retains only the newest 24 entries; thumbnail decoding and metadata inspection also run in a cancellable background worker. Existing editor FFmpeg/ffprobe preferences are reused. If tools are missing, placeholder cards still open the player; choose the tools folder in the full editor to enable thumbnails and durations. Thumbnails/details are cached under `%LOCALAPPDATA%\ClipNest\thumbnails` by file path, size and modification time.

## Quick player

A clip opens paused on its first decoded frame, with a large play button, play/pause, seek bar, elapsed/total time, previous/next clip, mute, volume, Open folder and Edit clip. Space toggles playback; Esc closes the player. The default audio track is used (normally the recording's Mix track). Use the full editor for solo tracks, trimming and export. Closing the player stops playback and releases its media source. Files are never modified by this player.

The viewer uses the editor's existing video canvas and Qt decoder. Display refresh is capped at 30 updates/sec as in the editor; original recording frame rates are unchanged. Windows device audio and hardware playback still need a local check.

## Upgrade

Finish recording, close the old app, extract this ZIP into a new folder, then run **Launch_ClipNest.vbs**. Settings, recordings, the OBS runtime and editor tool preferences are reused. Capture/replay, audio routing, exports, presets and notifications are unchanged.

## Validation

88 local tests passed, including real FFmpeg thumbnail/metadata extraction, Qt decoding of a paused first frame, newest-first scanning, exclusion of unfinished files, navigation/edit handoff, mute/volume controls without a physical audio backend, cancellation, and the original 83 regression tests. Gallery and player visually inspected offscreen. Test on Windows: open Clips & games, play an older clip, seek and adjust sound, use previous/next and Edit clip, then save a new replay and confirm its card appears.

---

# ClipNest 1.2.0 — native recorder + clip editor

## Assign keyboard shortcuts

In Settings, click the Save replay, Record or Push-to-talk field and press the desired key or combination, such as **Page Down** or **Ctrl+Page Down**, then click **Apply settings**. Esc restores the previous value; Tab moves to the next control. Shortcuts and push-to-talk activation are suspended while a shortcut field has focus. Page Up/Down, arrows and Delete are supported alongside letters, numbers, F1–F24, Space, Insert, Home, End and Pause. Stop recording/replay before applying settings as usual.

## Launch without a Command Prompt

Double-click **Launch_ClipNest.vbs** for normal use. It launches the private Python windowed interpreter, so there is no Command Prompt window to keep open. You can right-click that file and choose Send to → Desktop (create shortcut). Keep the original file in the extracted ClipNest folder.

First-time setup opens Start_ClipNest.bat visibly so downloads and any errors are readable. The setup window now closes after starting ClipNest. Start_ClipNest.bat also remains available to repair missing dependencies. Startup failures in the windowed launcher show an error dialog and write `%LOCALAPPDATA%\ClipNest\launcher.log`; normal recorder logs are unchanged. This launcher still uses the existing Python environment; this is not a bundled executable installer.

## New in 1.1.0

The recorder dashboard now uses a sidebar for Capture, Clips & games, Settings and the editor. The Capture page puts replay and recording controls, buffer length, elapsed recording time, audio meters, shortcuts and recent activity in one view. Settings are grouped into Capture, Video, Audio, Shortcuts and Notifications pages. The editor uses the same dark theme and clearer hierarchy.

ClipNest shows small, silent visual notifications in a non-focus overlay. They appear after the recorder confirms an event: **Clip saved**, **Recording started**, **Instant replay started**, **Recording finished**, and error notifications when recording/replay stops unexpectedly or the recorder connection fails. Notifications can be enabled, placed in a screen corner, assigned to a display and timed from 2–10 seconds. Errors stay visible for at least six seconds. The overlay is excluded from Windows capture when the OS supports `WDA_EXCLUDEFROMCAPTURE`; exclusive fullscreen games can still hide desktop overlays. The overlay never plays audio, takes keyboard focus or uses Windows toast sounds. Use Settings → Notifications → Preview notification to check the position.

Normal recorder stop requests are recognized as intentional, so they show **Recording finished** without an error notice. If a partial recording can be recovered after an output error, ClipNest labels it **Interrupted recording saved**.

**Confirmed by the user in v0.2.2:** DXGI video works without a yellow border; manual recording works while instant replay runs. This release preserves direct libobs, DXGI capture setup and independent manual recording. It adds a continuous replay output mode using the existing native muxer. No OBS Studio frontend or WebSockets are used.

## New in 1.0.0

- **Drag and drop:** drop one local video onto the preview to open it automatically. Unsupported files, folders and web links are ignored. An ongoing export must finish or be cancelled before loading another clip.
- **Live crop/color preview:** Show crop / colors live toggles between the source and current edits, including during playback. Color controls update the paused/playing preview while their dialog is open; Cancel restores the previous settings. The preview is capped at 960×540 and 30 updates/second to limit processing overhead. It uses an approximate RGB color adjustment, so use Preview export for the final FFmpeg filter result.
- **Preview export:** render the selected A–B range to a temporary CPU H.264 file, with final crop, color and audio settings. Watch it and select its audio tracks without choosing a permanent output filename. Cancel export also cancels preview generation. This preview checks edits, not the final codec/bitrate quality; full-resolution long selections can take time.
- **Timeline:** normalized waveform for the listened-to audio track, click/drag seeking, highlighted A–B selection, millisecond trim fields, ±1 frame controls and playback speeds from 0.25× to 2×. Frame buttons use the clip's average frame rate; variable-frame-rate clips and Qt seeking are not guaranteed exact frame stepping.
- **Audio remix:** Combine selected audio into one track applies each selected track's gain and exports one AAC track. The existing track named Mix is unchecked automatically when isolated tracks exist; manually reselecting it alongside others blocks the remix to avoid doubled audio. A limiter catches peaks without automatic loudness normalization. Leave Combine off to preserve separate tracks. Preview export auditions the actual remix and gains above 100%.
- **Browse clips:** persistent folder selection, prior-session recordings, cached thumbnails, filename/game-folder search, date/name/size sorting and batches of 100 results. Refresh rescans the folder; replay caches and partial export folders are excluded. Scans are limited to 10,000 clips and report unreadable folders. Scanning/thumbnail generation runs in background threads.

Existing DXGI/direct-libobs recorder and continuous replay code are unchanged. v1.1.0 updates the recorder dashboard and adds silent visual capture notifications. NumPy is installed automatically by Start_ClipNest.bat for preview/waveform processing. Handoffs are intentionally not updated or included in this release.

## New in 0.4.2

Named export presets remember codec and bitrate. Choose your values and click **Save preset…**; select that preset to reuse them across clips and restarts. Manual changes automatically persist as **Custom / last used**, without altering the named preset. Replacing or deleting a preset asks for confirmation. An unavailable saved encoder remains selected and blocks export until you choose an available codec or a recheck succeeds.

## New in 0.4.1

Landscape editor with preview/trim left and audio/export right; grey shading outside the crop box; confirmed export replacement. The save dialog asks once before replacing a destination. The previous export stays intact until encoding succeeds; cancellation/failure keeps it. The current source clip remains protected, including aliases. The last export filename is suggested again for the current clip.

Latest user tests confirm continuous joins without delay and AV1 export, cropping, filenames, A/B jumps, minimized restoration and default export folder. v0.4.1 UI/overwrite changes are locally tested only. v0.4.2 presets are also locally tested and await Windows acceptance.

## New in 0.4.0

- Readable dark table headers, larger audio-export toggles and a highlighted export button.
- **Go to A / Go to B** jumps to the selected trim start/end, without changing either marker.
- **Drag crop corners** opens a decoded frame with draggable corners and a movable crop box; crops snap to valid even source pixels. The box is restored when reopened. Pixel controls/color filters remain available.
- Restores and activates a minimized editor when launched or when a clip is double-clicked.
- Editor **Open** starts in your configured recording folder. **File → Default export folder** remembers your export destination separately.
- Saved files now use `Game name_date_time.mkv` or `Desktop_date_time.mkv`; Replay/Recording prefixes are removed. Existing files are untouched.
- Encoder checks use 1280×720 instead of 128×128. The old test resolution could reject hardware that supports normal recording sizes. **File → Encoder diagnostics** exposes full failures if NVENC/AV1 remain unavailable; AV1 export was subsequently confirmed working by the user.

## Continuous replay

**Settings → Replay behavior → Continuous** is the new default when no mode was previously saved. Apply with both outputs stopped. Existing monitor/DXGI, audio and encoding preferences remain intact. Classic retains the original overlapping RAM replay buffer.

Continuous uses libobs's native muxer to write roughly two-second segments in a bounded **disk cache**, sharing encoders with manual recording. Save requests a split at the next keyframe, joins only unsaved segments with FFmpeg packet copy, and keeps capture running. No encoder/capture stop or restart is issued. The next saved clip starts at the previous clip's boundary. Saving may include up to roughly one keyframe interval after the keypress (normally around two seconds); this is a delayed boundary, not intentionally missing footage.

The first save contains the available recent history. Subsequent saves contain new footage since the prior successful save, **up to your replay-duration limit**. If you wait longer, expired history cannot be recovered or stitched continuously. Whole keyframe segments can make the retained window slightly longer than the requested duration. A notice reports expiration or segment failure. Wait for each save confirmation before requesting another.

Continuous requires the same FFmpeg/ffprobe setup as the editor and local storage supporting hard links (such as NTFS). It writes disk data continuously while active; it does not add a second video encode. Cache location: your clips folder's `_Unsorted/_ReplayCache`. Successfully saved/expired segments are removed; failed saves and abrupt exits can retain recovery files. Normal stopping discards remaining unsaved history when the worker closes/restarts. Never delete cache files while replay is running. Disk use includes the retained window, in-flight save and queued segments during disk/tool delays; failed recovery files are retained beyond that limit.

Local generated-video tests found no missing/duplicated frames, video starts at zero and four-second joins within 25 ms of target duration. The user confirmed gapless joins on their Windows setup. Local tests do not establish behavior on other hardware or under sustained disk/GPU load. Classic remains selectable if continuous mode has a regression.

## Upgrade

1. Finish recordings and close the old ClipNest.
2. Extract this ZIP into a new writable folder and run **Start_ClipNest.bat**.
3. Existing settings, selected DXGI method, clips, and downloaded OBS runtime are retained. Requires Windows 10/11 x64 and 64-bit Python 3.11+.
4. Open **File → Open clip editor**, or double-click a session clip in Clips & games.

## One-time editor setup

The recorder still uses its existing OBS runtime. The editor additionally needs the standalone **ffmpeg.exe and ffprobe.exe** programs; OBS's DLLs are not replacements for these programs. They are not bundled or automatically downloaded by this release.

- Get a Windows build through https://ffmpeg.org/download.html (Windows EXE Files). Choose a build with libx264, h264_nvenc and av1_nvenc support. Keep its license notices and any accompanying DLLs.
- In the editor, choose **File → FFmpeg folder**, selecting the extracted `bin` folder containing both executables.
- Alternatively put them in `ClipNest\tools\ffmpeg`, or make both available on PATH before starting ClipNest.
- ClipNest tests encoders with a short real encode. Available encoders appear, and a saved unavailable selection is retained with an unavailable label. CPU H.264 is the fallback; GPU failure never silently changes the selected encoder. Hover over the encoder selector for failure details; use File → Check encoders again after changing drivers or freeing GPU resources.

## Editor

- **File:** open a completed MKV/MP4/MOV/WebM clip, export, select FFmpeg, recheck encoders.
- **Recent:** last ten opened files, retained across launches.
- **Edit:** set start/end from the current position, reset trim.
- **Filters:** crop using even pixel coordinates; brightness, contrast, saturation; reset filters.
- Play/pause, waveform and seek slider, ±1-frame buttons, millisecond start/end fields, and Play selection.
- Every detected audio stream is listed with its stored title, codec and channel count. **Listen solo** selects exactly one playback track. Use this to check Mix, Desktop and Microphone separately.
- Checked tracks are exported as separate AAC tracks. Each has independent 0–200% export volume. Source playback auditions one track at a time and caps volume at 100%; Preview export auditions the rendered remix and final track gains.
- **Mix is already desktop + microphone.** Changing the isolated tracks does not rebuild Mix. Uncheck Mix if you want only adjusted isolated tracks. Uncheck every track for a silent export.
- Export to an **MKV or MP4** using NVIDIA H.264, NVIDIA AV1 (when runtime checks pass), or CPU H.264. Progress and Cancel export are provided.

Exports decode and re-encode, including non-keyframe starts. Cuts follow source frame timing; millisecond controls do not imply arbitrary subframe accuracy. Frame stepping uses the average source frame interval and Qt seeking. Live preview shows crop/color changes; Preview export checks final FFmpeg processing without creating a permanent export.

The current source clip is protected. Export writes in a private temporary folder. New destinations publish without overwriting; explicitly confirmed replacements atomically replace the old export only after successful encoding. Use a local NTFS drive for export: publication requires hard-link support. A failed/cancelled export removes its temporary files in normal operation. Abrupt process or PC termination can leave a `.clipnest-export-*` temporary folder; it never replaces the original. Close is blocked while inspection/export is running; cancel export and wait before exiting.

## Audio and game folders

Recorder routing remains:

| Track | Content |
|---|---|
| 1 — Mix | Desktop + microphone |
| 2 — Desktop | Desktop only |
| 3 — Microphone | Microphone only |

This routing is verified in mocked controller/native tests. Real microphone/desktop isolation and sync still require listening to your Windows recordings. Device mixers such as VoiceMeeter can route microphone audio into the selected desktop device upstream of ClipNest.

Replay category is pinned when Save replay is requested. Manual recording category is pinned at recording start. Focusing ClipNest retains the last external app. Recognized games use named folders; other applications use Desktop. Steam/Epic manifests, known executables and manual registration remain supported. This release normalizes slash direction/case for matching and chooses the most specific matching installation folder. Game recognition affects sorting, not what monitor is captured. A replay spanning a game switch is not split.

Completed clips move from `_Unsorted` into their category. Existing retries and pending-save journal remain intact. Never delete `_Unsorted` as routine troubleshooting. Use **Clips & games → Register last application as a game** for missing recognition.

## Recording controls

Defaults: replay Ctrl+Shift+F10, recording Ctrl+Shift+F9, push-to-talk F8; 90-second replay; H.264 NVENC 1080p60 at 20 Mbps. Settings persist under `%LOCALAPPDATA%\ClipNest\settings.json`. Editor preferences are separate in `editor.json`.

Minimize to tray is explicit; closing attempts to finish recordings and exit. Screen capture attaches only when an output starts and stays attached while either output is active. PTT still relies on UI polling. Exports may compete with recording for GPU resources; simultaneous editor export/recording performance has not been measured.

## Testing and limits

See **TESTING.md** for results and the short Windows acceptance checklist. **83 tests passed locally**, including actual FFmpeg CPU exports and offscreen Qt checks. No Windows/GPU capture or physical-device audio was tested in this environment. AV1/NVENC options are implemented and checked on the user's machine at runtime, not hardware-verified here.

Per-app audio (including Spotify isolation), an installer, device reconnect handling, recording health monitoring, and safer stalled-UI PTT remain future work. The v1.1.0 dashboard and notification overlay are locally tested; Windows overlay placement and capture behavior still need acceptance. HDR, game-only capture, multiple-monitor simultaneous recording, and broad fullscreen/anti-cheat compatibility remain unverified or incomplete.

Diagnostics: File → Open app diagnostics / Open recorder logs. `%LOCALAPPDATA%\ClipNest\clipnest.log` and `native-engine.log`. Do not modify OBS Studio profiles: ClipNest does not use them.

Development: `python -m pip install -r requirements.txt pytest`, then `python -m pytest -q`. FFmpeg and ffprobe must be on PATH for real media tests; those tests explicitly skip otherwise. `python main.py --preview` opens the interface without loading the recorder.

Source is GPL-2.0-or-later. See LICENSE.txt and THIRD_PARTY.md.
