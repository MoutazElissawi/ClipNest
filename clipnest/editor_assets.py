"""Cancellable editor analysis; bounded memory and no recorder interaction."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import time
import numpy as np


def captured_file(args, output, cancel, timeout=120):
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(args, stdout=output, stderr=errors,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        deadline = time.monotonic()+timeout
        try:
            while process.poll() is None:
                if cancel.wait(.05):
                    raise ValueError('Analysis cancelled.')
                if time.monotonic() > deadline:
                    raise ValueError('Analysis timed out.')
            if process.returncode:
                errors.seek(0)
                raise ValueError(errors.read()[-1500:].decode('utf-8', 'replace') or 'Cannot analyse this clip.')
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()


def waveform(info, index, ffmpeg, cancel, bins=1600):
    with tempfile.TemporaryFile() as data:
        captured_file([ffmpeg, '-v', 'error', '-nostdin', '-i', info['path'], '-map', f'0:{index}',
            '-vn', '-ac', '1', '-ar', '8000', '-f', 'f32le', '-'], data, cancel)
        count = data.tell()//4
        if not count:
            return []
        data.seek(0)
        peaks = np.zeros(bins, dtype=np.float32)
        offset = 0
        while chunk := data.read(65536):
            if cancel.is_set():
                raise ValueError('Analysis cancelled.')
            values = np.abs(np.frombuffer(chunk, dtype='<f4'))
            positions = np.minimum(bins-1, (np.arange(len(values))+offset)*bins//count)
            np.maximum.at(peaks, positions, values)
            offset += len(values)
        maximum = float(peaks.max())
        return (peaks/max(.001, maximum)).tolist()


def thumbnail(path, ffmpeg, cache, cancel):
    path = Path(path)
    stat = path.stat()
    key = hashlib.sha256(f'fullhd-v2:{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}'.encode()).hexdigest()
    cache.mkdir(parents=True, exist_ok=True)
    target = cache/(key+'.jpg')
    if target.exists():
        return str(target)
    with tempfile.TemporaryFile() as data:
        captured_file([ffmpeg, '-v', 'error', '-nostdin', '-i', str(path), '-frames:v', '1',
            '-vf', "scale=w='min(1920,iw)':h='min(1080,ih)':force_original_aspect_ratio=decrease", '-q:v', '2', '-an', '-f', 'image2pipe', '-vcodec', 'mjpeg', '-'], data, cancel, 10)
        data.seek(0)
        image = data.read()
    if image:
        # No partial thumbnails are visible to another browser instance.
        with tempfile.NamedTemporaryFile(dir=cache, suffix='.tmp', delete=False) as temp:
            temp.write(image)
            name = temp.name
        os.replace(name, target)
    return str(target)


def scan_clips(root, cancel, limit=10000):
    from .preview import VIDEO_EXTENSIONS
    clips = []
    errors = []
    for directory, folders, files in os.walk(root, onerror=lambda exc: errors.append(str(exc))):
        from .library import linked
        folders[:] = [f for f in folders if not f.startswith('.') and f not in ('_ReplayCache', '_Unsorted') and not linked(Path(directory)/f)]
        for filename in files:
            if cancel.is_set():
                return [], False, errors
            path = Path(directory)/filename
            if path.suffix.lower() not in VIDEO_EXTENSIONS or path.is_symlink():
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            clips.append(dict(path=str(path), name=path.name, folder=str(path.parent.relative_to(root)),
                              modified=stat.st_mtime, size=stat.st_size))
            if len(clips) >= limit:
                return clips, True, errors
    return clips, False, errors
