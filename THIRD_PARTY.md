# Licensing and third-party software

ClipNest source in this package is licensed under GNU GPL version 2 or, at your option, any later version. See LICENSE.txt. It directly loads libobs, which is GPL-2.0-or-later.

The source ZIP does not bundle third-party binaries. The optional installer build adds a private Python runtime and Python dependencies; their included license and package metadata files must remain with the distribution. See packaging/BUILD.md for binary redistribution requirements. Setup downloads the official OBS Studio 32.2.2 Windows x64 distribution, whose license files remain in that runtime. Preserve those notices when redistributing it.

- OBS Studio/libobs: https://github.com/obsproject/obs-studio (GPL-2.0-or-later; includes dependencies with their own notices).
- PySide6/Qt for Python: https://doc.qt.io/qtforpython-6/licenses.html
- psutil: https://github.com/giampaolo/psutil (BSD-3-Clause).
- NumPy: https://numpy.org (BSD-3-Clause; installed for editor preview and waveform processing).

websocket-client is no longer required. ClipNest is not affiliated with OBS, NVIDIA, Valve, or Epic.

The editor invokes separately installed or optionally bundled FFmpeg/ffprobe executables. They are not bundled in this source ZIP. FFmpeg licensing depends on build options (LGPL/GPL and optional components); retain the chosen distribution's notices and source obligations when redistributing it: https://ffmpeg.org/legal.html and https://ffmpeg.org/download.html . Qt Multimedia may ship its own FFmpeg libraries through PySide6; those are distinct from the standalone command-line tools.

- CPython private runtime: https://www.python.org/ — retain its LICENSE.txt.
- Inno Setup installer builder: https://jrsoftware.org/ — separate tool; its use does not change ClipNest or dependency licenses.
