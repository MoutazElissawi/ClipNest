from __future__ import annotations

import json
import logging
import os
from pathlib import Path

DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share"))) / "ClipNest"
ENGINE = DATA / "engine"
SETTINGS = DATA / "settings.json"
ENCODERS = {"NVIDIA H.264": "obs_nvenc_h264_tex", "NVIDIA AV1": "obs_nvenc_av1_tex", "CPU H.264 (fallback)": "obs_x264"}
ENCODERS.update({"AMD H.264": "h264_texture_amf", "AMD HEVC": "h265_texture_amf", "AMD AV1": "av1_texture_amf"})


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temp.replace(path)


def load_settings():
    defaults = dict(output=str(Path.home() / "Videos/ClipNest"), replay_seconds=90,
                    storage_limit_gb=0, replay_mode="continuous", width=1920, height=1080, fps=60, bitrate=20000,
                    encoder="NVIDIA H.264", nvenc_preset="p4", mic_device="default", desktop_device="default",
                    audio_bitrate=192, mic_bitrate=192,
                    monitor_property="monitor_id", monitor_value=None, capture_method=2,
                    capture_target="games", window_value="", window_method=2, game_layer=True, game_audio_only=False, app_audio="", export_sound=True,
                    mic_mode="Always on", mic_volume=100, ptt_key="F8",
                    replay_key="Ctrl+Shift+F10", record_key="Ctrl+Shift+F9",
                    games={}, ui_theme='dark', theme_file='', glass_tint=46, notifications_enabled=True, notification_corner='Top right',
                    notification_seconds=3, notification_screen='')
    pristine = dict(defaults)
    if os.name != 'nt':
        pristine['encoder'] = defaults['encoder'] = 'CPU H.264 (fallback)'
    repaired = []
    if SETTINGS.exists():
        try:
            saved = json.loads(SETTINGS.read_text(encoding="utf-8-sig"))
            if not isinstance(saved, dict):
                raise ValueError('Settings must be a JSON object')
        except (ValueError, UnicodeError):
            saved = {}
            repaired.append('unreadable settings')
        for key, value in saved.items():
            if key not in pristine:
                continue
            if key == 'encoder':
                value = {'CPU H.264': 'CPU H.264 (fallback)',
                         'obs_x264': 'CPU H.264 (fallback)',
                         **{v: k for k, v in ENCODERS.items()}}.get(str(value), value)
            candidate = {**pristine, key: value}
            try:
                expected = pristine[key]
                if expected is not None and type(value) is not type(expected):
                    raise ValueError('Wrong setting type')
                validate(candidate)
                if key == 'games' and not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
                    raise ValueError('Invalid game mappings')
                defaults[key] = value
            except (ValueError, TypeError, KeyError, OverflowError):
                repaired.append(key)
                if key == "encoder":
                    defaults[key] = "CPU H.264 (fallback)"
        if repaired:
            from datetime import datetime
            import shutil
            backup = SETTINGS.with_name('settings.recovered-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json')
            shutil.copy2(SETTINGS, backup)
            logging.warning('Recovered settings %s; original saved to %s', ', '.join(repaired), backup)

    # Appearance belongs to the UI. Recorder settings may be written later by
    # an already queued command, so they must not overwrite a newer UI choice.
    try:
        appearance = json.loads(SETTINGS.with_name('appearance.json').read_text(encoding='utf-8'))
        if appearance.get('ui_theme') in ('dark', 'glass'):
            defaults['ui_theme'] = appearance['ui_theme']
        if isinstance(appearance.get('theme_file'), str):
            defaults['theme_file'] = appearance['theme_file']
        tint = int(appearance.get('glass_tint', defaults['glass_tint']))
        if 25 <= tint <= 85:
            defaults['glass_tint'] = tint
    except FileNotFoundError:
        pass
    except (OSError, ValueError, TypeError, AttributeError):
        logging.exception('Could not load appearance preferences; using saved recorder settings')
    defaults.pop("password", None)
    defaults.pop("port", None)
    validate(defaults)
    return defaults


def save_appearance(theme, tint, theme_file=None):
    tint = int(tint)
    if theme not in ('dark', 'glass') or not 25 <= tint <= 85:
        raise ValueError('Choose a supported appearance and tint from 25 to 85 percent.')
    path = SETTINGS.with_name('appearance.json')
    if theme_file is None:
        try:
            theme_file = json.loads(path.read_text(encoding='utf-8')).get('theme_file', '')
        except (OSError, ValueError, AttributeError):
            theme_file = ''
    atomic_json(path, {'ui_theme': theme, 'glass_tint': tint, 'theme_file': str(theme_file)})


def app_track_name(window_value):
    """Track title for the per-application audio track, e.g. 'Spotify'."""
    exe = (window_value or "").split(":")[-1].replace("#3A", ":")
    return Path(exe).stem[:40] if exe else ""


def validate(s):
    for key in ('audio_bitrate', 'mic_bitrate'):
        if type(s.get(key, 192)) is not int or s.get(key, 192) not in (64, 96, 128, 160, 192, 256, 320):
            raise ValueError('Audio bitrate must be 64, 96, 128, 160, 192, 256 or 320 kb/s.')
    if type(s.get("storage_limit_gb", 0)) not in (int, float) or not 0 <= s.get("storage_limit_gb", 0) <= 1000000:
        raise ValueError("Storage limit must be 0 (unlimited) to 1,000,000 GB.")
    if s.get('nvenc_preset', 'p4') not in ('p1', 'p3', 'p4', 'p5'):
        raise ValueError('Choose a supported NVIDIA quality preset.')
    if s.get('ui_theme', 'dark') not in ('dark', 'glass'):
        raise ValueError('Choose a supported appearance.')
    if not 25 <= int(s.get('glass_tint', 46)) <= 85:
        raise ValueError('Glass tint must be between 25 and 85 percent.')
    if s.get("replay_mode", "classic") not in ("classic", "continuous"):
        raise ValueError("Choose a supported replay mode.")
    if s.get("capture_target", "display") not in ("games", "display", "displays", "window", "game"):
        raise ValueError("Choose Games only, Display or Window capture.")
    if not isinstance(s.get("app_audio", ""), str) or (s.get("app_audio") and len(s["app_audio"].split(":")) != 3):
        raise ValueError("Choose a valid application for the extra audio track.")
    if type(s.get("export_sound", True)) is not bool:
        raise ValueError("Export sound must be on or off.")
    if type(s.get("game_layer", True)) is not bool:
        raise ValueError("Game layer must be on or off.")
    if type(s.get("game_audio_only", False)) is not bool:
        raise ValueError("Game-only audio must be on or off.")
    if s.get("window_method", 2) not in (0, 1, 2):
        raise ValueError("Choose a supported window capture method.")
    if not isinstance(s.get("window_value", ""), str):
        raise ValueError("Choose a valid capture window.")
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
