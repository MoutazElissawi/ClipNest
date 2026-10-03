"""Local clip annotations and cancellable storage accounting. Never edits media."""
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sqlite3
from contextlib import contextmanager
from .config import DATA

MEDIA = {'.mkv', '.mp4', '.mov', '.avi', '.webm', '.m4v'}
GB = 1_000_000_000


def linked(path):
    try:
        return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()) or bool(
            getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)
    except OSError:
        return True


def clip_key(path):
    path = Path(path)
    st = path.stat()
    # Filesystem identity survives same-volume rename/move. Size/mtime guard
    # against reused file IDs. Cross-volume copies are intentionally new clips.
    if st.st_ino:
        return f'{st.st_dev}:{st.st_ino}:{st.st_size}:{st.st_mtime_ns}'
    return f'{path.resolve()}:{st.st_size}:{st.st_mtime_ns}'


class Annotations:
    def __init__(self, database=None):
        self.database = Path(database or DATA / 'clips.sqlite3')

    @contextmanager
    def connect(self):
        self.database.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.database, timeout=5)
        db.execute('CREATE TABLE IF NOT EXISTS clips (identity TEXT PRIMARY KEY, tags TEXT NOT NULL, favorite INTEGER NOT NULL)')
        try:
            with db:
                yield db
        finally:
            db.close()

    def annotate(self, clips):
        with self.connect() as db:
            for clip in clips:
                try:
                    key = clip_key(clip['path'])
                    row = db.execute('SELECT tags, favorite FROM clips WHERE identity=?', (key,)).fetchone()
                    clip.update(tags=json.loads(row[0]) if row else [], favorite=bool(row and row[1]))
                except (OSError, ValueError):
                    clip.update(tags=[], favorite=False)
        return clips

    def set(self, path, tags=None, favorite=None):
        key = clip_key(path)
        with self.connect() as db:
            old = db.execute('SELECT tags, favorite FROM clips WHERE identity=?', (key,)).fetchone() or ('[]', 0)
            tags = json.dumps(list(dict.fromkeys(t.strip()[:80] for t in tags if t.strip()))[:30]) if tags is not None else old[0]
            db.execute('INSERT OR REPLACE INTO clips VALUES (?, ?, ?)', (key, tags, int(favorite) if favorite is not None else old[1]))


def matches(clip, query='', favorites=False):
    words = (clip['name'] + ' ' + clip['folder'] + ' ' + datetime.fromtimestamp(clip['modified']).strftime('%Y-%m-%d')
             + ' ' + ' '.join(clip.get('tags', []))).casefold()
    return (not favorites or clip.get('favorite', False)) and all(word in words for word in query.casefold().split())


def storage_usage(root, cancel):
    root = Path(root)
    total = count = 0
    errors = []
    for base, dirs, files in os.walk(root, followlinks=False, onerror=lambda e: errors.append(str(e)) if not isinstance(e, FileNotFoundError) else None):
        if cancel.is_set():
            return None
        kept = []
        for name in dirs:
            try:
                if not name.startswith('.') and name not in ('_Unsorted', '_ReplayCache') and not linked(Path(base)/name):
                    kept.append(name)
            except OSError as exc:
                errors.append(str(exc))
        dirs[:] = kept
        for name in files:
            if cancel.is_set():
                return None
            path = Path(base)/name
            try:
                if path.suffix.lower() in MEDIA and not name.startswith('.') and not linked(path):
                    size = path.stat().st_size
                    if size:
                        total += size
                        count += 1
            except OSError as exc:
                errors.append(str(exc))
    volume = root
    while not volume.exists() and volume != volume.parent:
        volume = volume.parent
    try:
        disk = shutil.disk_usage(volume)
        free, capacity = disk.free, disk.total
    except OSError as exc:
        errors.append(str(exc))
        free = capacity = None
    return dict(bytes=total, count=count, free=free, capacity=capacity, errors=errors)
