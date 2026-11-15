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
SKIPPED_FOLDERS = ('_Unsorted', '_ReplayCache')  # staging and replay cache, never finished clips


def media_files(root, cancel, extensions=MEDIA, onerror=None, skip=()):
    """(path, stat) of each non-empty media file under root; skips hidden, staging and linked folders and files.
    Windows lists sizes and times with the folder, so no file is opened or stat'ed. Those stats have no file id;
    os.stat the path when one is needed. `skip` holds os.path.normcase paths of files and folders to leave out."""
    folders = [str(root)]
    while folders:
        try:
            with os.scandir(folders.pop()) as listing:
                entries = list(listing)
        except OSError as exc:
            if onerror is not None:
                onerror(exc)
            continue
        for entry in entries:
            if cancel.is_set():
                return
            if entry.name.startswith('.'):
                continue
            try:
                stat = entry.stat(follow_symlinks=False)
                if entry.is_symlink() or getattr(stat, 'st_file_attributes', 0) & 0x400:  # links and junctions
                    continue
                if os.path.normcase(entry.path) in skip:
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name not in SKIPPED_FOLDERS:
                        folders.append(entry.path)
                elif stat.st_size and os.path.splitext(entry.name)[1].lower() in extensions:
                    yield entry.path, stat
            except OSError as exc:
                if onerror is not None:
                    onerror(exc)


def linked(path):
    try:
        return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()) or bool(
            getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)
    except OSError:
        return True


def clip_key(path, st=None):
    path = Path(path)
    st = st or path.stat()
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

    def load_all(self):
        """identity -> (tags, favorite), read once so a library scan can filter every file."""
        with self.connect() as db:
            rows = db.execute('SELECT identity, tags, favorite FROM clips').fetchall()
        result = {}
        for identity, tags, favorite in rows:
            try:
                result[identity] = (json.loads(tags), bool(favorite))
            except ValueError:
                result[identity] = ([], bool(favorite))
        return result

    def set(self, path, tags=None, favorite=None):
        key = clip_key(path)
        with self.connect() as db:
            old = db.execute('SELECT tags, favorite FROM clips WHERE identity=?', (key,)).fetchone() or ('[]', 0)
            tags = json.dumps(list(dict.fromkeys(t.strip()[:80] for t in tags if t.strip()))[:30]) if tags is not None else old[0]
            db.execute('INSERT OR REPLACE INTO clips VALUES (?, ?, ?)', (key, tags, int(favorite) if favorite is not None else old[1]))


def library_filter(query, favorites, annotations):
    """Predicate for a full-library scan; None when nothing is filtered."""
    if not query.strip() and not favorites:
        return None
    def accept(path, stat, clip):
        try:
            tags, favorite = annotations.get(clip_key(path, stat), ([], False))
        except OSError:
            tags, favorite = [], False
        clip.update(tags=tags, favorite=favorite)
        return matches(clip, query, favorites)
    return accept


def matches(clip, query='', favorites=False):
    words = (clip['name'] + ' ' + clip['folder'] + ' ' + datetime.fromtimestamp(clip['modified']).strftime('%Y-%m-%d')
             + ' ' + ' '.join(clip.get('tags', []))).casefold()
    return (not favorites or clip.get('favorite', False)) and all(word in words for word in query.casefold().split())


def storage_usage(root, cancel):
    root = Path(root)
    total = count = 0
    errors = []
    for _, stat in media_files(root, cancel, onerror=lambda e: errors.append(str(e)) if not isinstance(e, FileNotFoundError) else None):
        total += stat.st_size
        count += 1
    if cancel.is_set():
        return None
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
