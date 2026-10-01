# ClipNest 1.4.1

Windows screen recording, instant replay, and clip editing, powered by OBS/libobs.

## Requirements

- Windows 10/11 x64 and 64-bit Python 3.11+.
- Internet for first setup. Python dependencies and a private OBS runtime download automatically; an existing OBS installation is not required.
- Separate FFmpeg and ffprobe executables for continuous replay, editing, and thumbnails. Select their folder in the editor under File → FFmpeg folder.
- Compatible NVIDIA hardware/drivers for NVENC and AV1. CPU H.264 is also available.
- Local NTFS storage for continuous replay and exports.


## Screenshots
<img width="1477" height="1039" alt="image" src="https://github.com/user-attachments/assets/b8735c63-1e02-4f9f-852e-2bd133064f11" />
<img width="1477" height="1039" alt="image" src="https://github.com/user-attachments/assets/07f97bea-a0b0-4f7a-b8ed-030f42c9880f" />
<img width="1702" height="989" alt="image" src="https://github.com/user-attachments/assets/253f4025-c638-4a65-bb76-a3451c62043e" />


## Launch

Extract the ZIP and run Start_ClipNest.bat for first setup. Afterwards, use Launch_ClipNest.vbs. To update, finish recording, close the old app, and extract this release into a new folder. Existing settings and clips are retained.

## Features

- Configurable instant replay and simultaneous manual recording.
- Classic RAM replay or continuous disk replay, with consecutive saves within the retained time window.
- Automatic game folders and Desktop categorization, plus manual game registration.
- Separate desktop, microphone, and combined audio tracks.
- Microphone selection, gain, mute, and push-to-talk.
- Configurable shortcuts, recording resolution, frame rate, bitrate, and encoder.
- Recent clip gallery, searchable clip browser, and quick playback.
- Editor with trimming, cropping, color adjustments, audio gains/remixing, and export presets.
- H.264 and AV1 hardware exports where supported, plus CPU H.264.
- Compact animated notifications.

## New in 1.4.1

A quieter desktop interface: neutral surfaces, section dividers instead of boxed cards, smaller headings and controls, consistent spacing, clearer focus outlines, and more room for clips and video. Promotional subtitles and the editor advertisement have been removed. The capture engine and notification animation are unchanged.

Per-application audio isolation, an installer, and automatic device reconnection remain future work. Hardware compatibility varies; see TESTING.md for validation limits.

Source license: GPL-2.0-or-later. See LICENSE.txt and THIRD_PARTY.md.

Version 1.4.1 adds a black/charcoal/green palette and reorganizes editor playback and trim controls. Large green play/pause, marker icons and paired frame buttons sit above the timeline. Open/browse and compact A/B/crop controls sit beside the trim timestamps. ClipNest is an independent application, not an NVIDIA product.

Version 1.4.1 restores normal-size frame controls and labels the trim buttons Start and End. A/B timeline markers are retained.
