# v1.2.0 gallery verification

88 tests pass locally. New tests are in tests/test_gallery.py. The Qt first-frame test uses real decoded media but disconnects physical audio output because the headless Linux environment has no audio device. Windows audio/playback and DPI behavior require a user check. Offscreen gallery and player screenshots were inspected with synthetic video. Recorder/native host and media/export logic were not changed in this release.

# v1.1.0 testing notes

83 local tests pass. Added coverage for confirmed start/save/finish notifications, intentional stop suppression, unexpected record/replay stops, native connection loss, failed starts, recovery-file handling, notification deduplication and priority, silent non-focus overlay flags, configurable notification position/duration/disable state, and redesigned dashboard/settings navigation. The dashboard, Settings → Notifications page, editor theme and toast were visually inspected offscreen at 1180×800.

Focused Windows check:

1. Start the engine, start instant replay and start a recording. Confirm small silent notifications appear for **Instant replay started** and **Recording started**. Save a replay and confirm **Clip saved**. Stop the recording normally and confirm **Recording finished** without an error notice.
2. Use Settings → Notifications to move the corner, change display/duration, toggle notifications, and use Preview notification. Confirm the overlay does not take focus and keyboard input stays with the game.
3. Force or observe an encoder/output failure and confirm the error notice identifies the stopped capture. Check that an interrupted file is labeled **Interrupted recording saved** if recovery succeeds.
4. Check the Capture, Clips & games, Settings and editor layouts at the normal Windows scale. Confirm the overlay appears on the selected/active display and that the game remains responsive.

Limits: Linux verification cannot confirm Windows global overlays, WDA_EXCLUDEFROMCAPTURE support, exclusive-fullscreen visibility, physical audio, GPU capture, or Windows DPI scaling. The overlay intentionally uses a desktop window and can be hidden by exclusive fullscreen. Existing recorder and replay acceptance results remain valid.

No handoff was created or updated for this release.

# v1.0.2 shortcut capture

77 local tests pass. New checks exercise actual Qt Page Down and modifier key presses, cancellation with Esc, Tab focus navigation, Page Up/Down name aliases, mocked Windows registration codes, action suppression during assignment, and passing the captured key through Apply settings. Windows global shortcut activation still requires a user check.

Test: click Save replay shortcut, press Page Down, and Apply settings with recording/replay stopped. Start replay and confirm Page Down saves it. While a shortcut field has focus, pressing the key should assign it without triggering replay/recording. Existing duplicate-shortcut checks remain active.

# v1.0.1 launcher testing notes

Added Launch_ClipNest.vbs and Launch_ClipNest.pyw for console-free startup. Start_ClipNest.bat now launches pythonw and exits after setup. The Python entry point was checked with absent standard streams and a simulated startup failure. Windows Script Host/double-click behavior requires Windows acceptance here: double-click Launch_ClipNest.vbs, confirm no console remains, and verify normal recorder/editor operation. First-time setup remains visible. Recorder/editor behavior is unchanged from v1.0.0.

# v1.0.0 testing notes

74 local tests pass. Seven new tests cover actual local-video drop events and rejected payloads; live crop/color preview and source toggle; a real FFmpeg remix with measured independent tone gains and duplicate-Mix protection; waveform generation/cancellation; cached thumbnails; scanning that excludes replay/export cache files; browsing prior-session files with search/sorting; frame navigation and millisecond trim controls; and rendered export-preview duration/crop/remix plus temporary-file cleanup. The landscape editor has been visually inspected at 1360×760 with generated video and all three audio tracks.

Focused Windows checks:

1. Drag a completed clip onto the video area. Drop another after it loads. Confirm it opens and the waveform appears; Listen solo should change the waveform track.
2. Set a crop and change brightness/saturation in Filters. Confirm the preview updates and Show crop / colors live toggles the source. Cancel in the filter dialog should restore previous settings. Try ±1 frame and a waveform seek.
3. Enable Combine selected audio, adjust Desktop/Microphone gains, and use Preview export on a short selection. Confirm Mix becomes unchecked, both isolated tracks are audible, and a final export has one audio track. Turn Combine off to retain separate tracks.
4. Browse clips, search by game/folder, change sorting and double-click a previous-session clip. Restart and check the browser remembers its selected folder.
5. Keep checking saved export presets and confirmed overwrite behavior as needed; the previously confirmed recorder/audio behavior is not reopened troubleshooting.

Limits: Linux verification cannot confirm Windows Qt video decoding/GPU performance or physical audio-device playback. Live preview uses an approximate RGB adjustment at at most 960×540 / 30 updates per second; Preview export applies actual FFmpeg filters in a temporary CPU H.264 render at full output dimensions. It does not simulate the chosen final codec/bitrate. Frame stepping is based on average frame rate and Qt seeking, so variable-frame-rate frame accuracy is not guaranteed. Thumbnails are cached under the ClipNest data folder; missing/corrupt videos can remain listed with no thumbnail and report an error if opened. Browser scans cap at 10,000 clips and do not hide active manual recordings; finish recording before opening one. New Windows acceptance is pending.

Native host/client, libobs bindings, capture engine and continuous replay are unchanged from v0.4.2. No handoff was created or updated for this release.

The following sections are historical test notes; current results and scope above take precedence.

# v0.4.2 testing update

67 tests pass locally. Three new tests cover named presets and last-used codec/bitrate across editor restarts; manual changes and preset reselection; unavailable encoders blocking export and recovery after recheck; replacement/deletion confirmation; and preservation of old editor preferences. Preset controls visually inspected offscreen in the landscape layout. Recorder/replay and export-engine code are unchanged from v0.4.1.

Focused Windows check:

1. Set AV1 and your desired bitrate, Save preset…, then open another clip and restart ClipNest. Confirm the same preset, codec and bitrate return.
2. Change bitrate: Custom / last used should appear; select the saved preset to restore its values. Confirm replacement and deletion prompts.
3. Verify the v0.4.1 wider editor, grey shading outside the crop box, and confirmed export overwrites. Failure/cancellation should preserve the previous export.

Windows/GPU behavior for these new controls is pending user acceptance. The earlier user confirmations below remain valid; no sample clip is needed for these checks.

# v0.4.1 testing update

64 local tests pass. Added real overwrite success, failure/cancellation preservation, source/hard-link protection and destination-change checks. Landscape layout and grey crop shading visually inspected offscreen.

User confirmed v0.4.0 continuous joins with no delay, AV1 export, drag crop, names, A/B jumps, minimized restoration and export folder. Only the wider layout, shading and confirmed overwrite flow await Windows testing in this patch. Recorder/replay code unchanged from v0.4.0.

The following is historical v0.4.0 test detail; its pending checks are superseded by the confirmations above.

# v0.4.0 testing notes

## Latest user confirmation (v0.3.0)

Audio isolation, Listen solo, sync, editor operation and per-track volume work. Game detection creates correctly named game folders. DXGI without a border and concurrent manual recording/replay were confirmed previously. These are retained as confirmed baselines, not reopened troubleshooting.

## Local evidence

62 tests pass on Linux. All earlier regression tests remain; new checks cover application-prefixed filenames, 720p encoder probes, continuous segment consumption, expiry and error retention, cache path safety, crop coordinate conversion/actual corner dragging, marker seeking, default folders, minimized editor restoration, and native split requests leaving both outputs active.

Real generated media is encoded to four sequential two-second H.264/AAC segments with three audio tracks. Two saves are assembled from disjoint segment sets. Decoded frame hashes prove that all 240 source frames occur in order exactly once across the two clips. All three audio streams remain; video starts at zero and each four-second file is within 25 ms of target duration. Timestamp normalization handles encoder reorder offsets and prevents leading video delay from being added to every saved clip. Negative AAC preroll timestamps can be present.

Earlier actual CPU-export tests still cover non-keyframe cuts, crop dimensions, tone isolation/gain, first-frame content, cancellation, new-file protection and publication races. Qt UI and crop overlay rendered offscreen and visually checked. Pinned OBS 32.2.2 muxer source was inspected for split_file settings, file_changed signal semantics, keyframe boundaries and continuous packet delivery. Native behavior here is still mocked, not a Windows recording test.

## Please test these changes

1. **Continuous replay:** Set 20 seconds and Continuous in Settings, Apply, then start replay. Save after ~8 seconds; wait for the save confirmation; save again ~6 seconds later. Join the two files in your editor and check moving video and a continuous sound at the join. The second clip should contain only new footage. A save ends on a following keyframe, not exactly at the keypress. Try with manual recording active too.
2. **Expiry:** Wait longer than 20 seconds between saves; the older interval intentionally expires. Expect a notice and no promise that those clips can join without missing history. If the new mode fails, switch to Classic; report the message without changing DXGI.
3. **Editor:** Confirm headers/export toggles are readable, Go to A/B seeks to your selected points, minimized launch restores the window, and dragging crop corners changes the exported image.
4. **Folders/names:** A new clip should be `Game name_timestamp.mkv` or `Desktop_timestamp.mkv`. Set File → Default export folder and verify the next save dialog starts there. Open should start at the recorder's clip-root folder.
5. **GPU:** File → Check encoders again now tests 720p. If H.264 NVENC/AV1 still fail, send the text under **File → Encoder diagnostics → Show Details**. The screenshots supplied showed availability status but not the underlying error; the true driver/build failure cannot be inferred from that alone.

No sample needed now. Only request one later if a reproducible content/sync/join issue cannot be diagnosed from logs and exact timing.

## Remaining limits

Continuous replay uses disk, FFmpeg and hard-link-capable local storage. Real NVENC/AV1 support, native Windows split timing/audio seams, long runs and disk performance remain unverified here. Failed saves retain cache segments for recovery. Segments finishing during abrupt disconnect may remain in cache. No live crop-filter preview, combined audio remix or persistent thumbnail library yet.
