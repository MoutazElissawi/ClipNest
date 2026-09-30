from __future__ import annotations

import json
import os
from pathlib import Path

DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share"))) / "ClipNest"
ENGINE = DATA / "engine"
SETTINGS = DATA / "settings.json"
ENCODERS = {"NVIDIA H.264": "obs_nvenc_h264_tex", "NVIDIA AV1": "obs_nvenc_av1_tex", "CPU H.264 (fallback)": "obs_x264"}


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temp.replace(path)


def load_settings():
    defaults = dict(output=str(Path.home() / "Videos/ClipNest"), replay_seconds=90,
                    replay_mode="continuous", width=1920, height=1080, fps=60, bitrate=20000,
                    encoder="NVIDIA H.264", mic_device="default", desktop_device="default",
                    monitor_property="monitor_id", monitor_value=None, capture_method=2,
                    mic_mode="Always on", mic_volume=100, ptt_key="F8",
                    replay_key="Ctrl+Shift+F10", record_key="Ctrl+Shift+F9",
                    games={}, notifications_enabled=True, notification_corner='Top right',
                    notification_seconds=3, notification_screen='')
    if SETTINGS.exists():
        defaults.update(json.loads(SETTINGS.read_text(encoding="utf-8")))
    defaults.pop("password", None)
    defaults.pop("port", None)
    validate(defaults)
    return defaults


def validate(s):
    if s.get("replay_mode", "classic") not in ("classic", "continuous"):
        raise ValueError("Choose a supported replay mode.")
    if s.get("capture_method", 2) not in (0, 1, 2):
        raise ValueError("Choose a supported screen capture method.")
    if not 5 <= int(s["replay_seconds"]) <= 1800:
        raise ValueError("Replay length must be 5 to 1800 seconds.")
    if s["encoder"] not in ENCODERS:
        raise ValueError("Choose a supported encoder.")
    for key in ("width", "height"):
        if not 64 <= int(s[key]) <= 4096 or int(s[key]) % 2:
            raise ValueError("Resolution must use even dimensions between 64 and 4096.")
    if int(s["fps"]) not in (24, 30, 60, 90, 120):
        raise ValueError("Choose 24, 30, 60, 90, or 120 fps.")
    if not 1000 <= int(s["bitrate"]) <= 200000:
        raise ValueError("Bitrate must be 1,000 to 200,000 Kbps.")
    if not Path(s["output"]).is_absolute():
        raise ValueError("Choose an absolute output folder.")
