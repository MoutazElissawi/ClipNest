"""Remember successful exports without moving files or changing originals."""
import json
from pathlib import Path
from .config import DATA, atomic_json


def export_paths():
    try:
        value = json.loads((DATA/'exports.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return [Path(p) for p in value if isinstance(p, str)] if isinstance(value, list) else []


def register_export(path):
    path = Path(path).resolve()
    paths = [p for p in export_paths() if p != path]
    atomic_json(DATA/'exports.json', [str(path), *map(str, paths)])


def export_folder(clips_root):
    try:
        prefs = json.loads((DATA/'editor.json').read_text(encoding='utf-8'))
        folder = prefs.get('export_folder') if isinstance(prefs, dict) else None
    except (OSError, ValueError):
        folder = None
    return Path(folder) if isinstance(folder, str) and folder else Path(clips_root)/'Exports'
