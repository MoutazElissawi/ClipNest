# Build the Windows installer

Use Windows 10/11 x64, a full python.org 64-bit Python 3.11–3.13 installation with pip, and Inno Setup 6.3 or newer. https://jrsoftware.org/isdl.php

The batch launcher automatically selects a supported 64-bit Python version, preferring 3.11.

1. Extract the developer ZIP. Finish recording and quit existing ClipNest instances.
2. Double-click `Build_Installer.bat`. Internet is needed to obtain Python packages.
3. Find `dist/ClipNest-Setup-1.5.1-x64.exe` and its SHA-256 file.
4. Run the acceptance checks in `TESTCASES.md` before sharing the installer.

To choose a Python version explicitly: `py -3.12 packaging/build_installer.py`.
To specify the compiler: `py -3.11 packaging/build_installer.py --iscc "C:\path\ISCC.exe"`.
To inspect the payload without Inno: `py -3.11 packaging/build_installer.py --stage-only`.

The builder copies a private full Python runtime and installs only the project's dependencies into it. It does not copy your existing site-packages, settings, recordings, caches or credentials. Runtime import checks run before compilation. Resolved package versions are recorded in BUILD-INFO.json; requirements currently use version ranges, so this is not a byte-reproducible build. Do not copy an existing venv into the installer.

The installer creates per-user shortcuts under `%LOCALAPPDATA%\Programs\ClipNest`; no administrator prompt is requested. It keeps the existing `%LOCALAPPDATA%\ClipNest` preferences/runtime location. Both app and recorder hold an installer mutex: setup/uninstall asks you to exit rather than killing a recording. Versions older than 1.5.1 do not hold this mutex: exit them manually before installing. The stable AppId must stay unchanged for later releases.

First launch downloads and verifies the existing pinned official OBS runtime in a visible progress dialog. No system Python or separate OBS installation is needed by installer users. This is not an offline installer. No automatic updater or signing certificate is included. The installer is unsigned; building it does not establish a verified publisher.

## Optional bundled FFmpeg

Default builds retain the existing separate FFmpeg requirement. To include it:

- Prepare a folder with `ffmpeg.exe`, `ffprobe.exe`, any required DLLs, and the selected distribution's license/notice files.
- Include a `REDISTRIBUTION.md` identifying the exact build, its origin, configuration and how recipients receive its corresponding source. Keep needed source archives with the folder or distribute corresponding source alongside the release as required by that build's license. A link or a file named REDISTRIBUTION.md alone is not a compliance guarantee.
- Run `Build_Installer.bat --ffmpeg-dir "C:\your\prepared-ffmpeg"`.

The whole supplied folder is copied, so include only redistributable files. Prefer an official-download-page-listed distribution with H.264/NVENC/AV1 support suitable for your users. ClipNest automatically discovers bundled tools; an existing valid custom FFmpeg path takes priority. This build recipe deliberately does not silently redistribute arbitrary tools from your PATH.

Keep LICENSE.txt, THIRD_PARTY.md and dependency notices. ClipNest's Python source and its build scripts are shipped in the installed payload. Before publishing bundled third-party binaries, meet each chosen distribution's source and notice requirements; retained wheel metadata is not by itself a complete corresponding-source package. Inno Setup itself does not remove those obligations.

No recording engine changes are required by this packaging. Validate on a clean Windows account/machine without Python, and with your existing preferences, before treating this as a release-ready installer.
