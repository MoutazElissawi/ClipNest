"""Editor-only FFmpeg pipeline. Never touches recorder processes or originals."""
from __future__ import annotations
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
from fractions import Fraction

ENCODERS = {'NVIDIA H.264': 'h264_nvenc', 'NVIDIA AV1': 'av1_nvenc',
            'AMD H.264': 'h264_amf', 'AMD HEVC': 'hevc_amf', 'AMD AV1': 'av1_amf',
            'CPU H.264': 'libx264'}
# Stream copy: video packets pass through untouched; audio is copied unless edited.
COPY = 'Copy (no re-encode)'


def run(args, **kwargs):
    return subprocess.run(args, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                          capture_output=True, text=True, encoding='utf-8', errors='replace', **kwargs)


def tools_path(folder=''):
    folders = [Path(folder)] if folder else []
    folders += [Path(__file__).resolve().parents[1] / 'tools/ffmpeg']
    suffix = '.exe' if os.name == 'nt' else ''
    for base in folders:
        paths = [base / (name + suffix) for name in ('ffmpeg', 'ffprobe')]
        if all(p.is_file() for p in paths):
            return tuple(str(p.resolve()) for p in paths)
    if not folder and all(shutil.which(n) for n in ('ffmpeg', 'ffprobe')):
        return shutil.which('ffmpeg'), shutil.which('ffprobe')
    raise ValueError('Choose a folder containing both ffmpeg.exe and ffprobe.exe using File → FFmpeg folder. Recording does not require these editor tools.')


def probe(path, ffprobe, cancel=None):
    args = [ffprobe, '-v', 'error', '-show_streams', '-show_data', '-show_format', '-of', 'json', str(path)]
    if cancel is None:
        result = run(args, timeout=30)
        if result.returncode:
            raise ValueError(result.stderr[-2000:] or 'Cannot inspect this clip.')
        info = json.loads(result.stdout)
    else:
        from .editor_assets import captured_file
        with tempfile.TemporaryFile() as data:
            captured_file(args, data, cancel, 30)
            data.seek(0)
            info = json.load(data)
    video = next((s for s in info.get('streams', []) if s['codec_type'] == 'video' and not s.get('disposition', {}).get('attached_pic')), None)
    if not video:
        raise ValueError('This file has no video stream.')
    duration = float(info.get('format', {}).get('duration', video.get('duration', 0)))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('This clip has no finite duration. Finish recording before opening it.')
    return dict(path=str(Path(path).resolve()), duration=duration, video=video,
                audio=[s for s in info['streams'] if s['codec_type'] == 'audio'])


def available_encoders(ffmpeg, cancel=None):
    """Actually encode two frames: listing an encoder does not prove GPU support."""
    available, failures = [], {}
    for label, encoder in ENCODERS.items():
        try:
            args = [ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'color=s=1280x720:r=30',
                    '-frames:v', '2', '-c:v', encoder, '-pix_fmt', 'yuv420p', '-f', 'null', '-']
            if cancel is not None:
                if cancel.is_set():
                    raise ValueError('Encoder inspection cancelled.')
                from .editor_assets import captured_file
                with tempfile.TemporaryFile() as output:
                    captured_file(args, output, cancel, 20)
                available.append(label)
                continue
            result = run(args, timeout=20)
            if result.returncode == 0:
                available.append(label)
            else:
                failures[label] = result.stderr[-1200:]
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            if cancel is not None and cancel.is_set():
                raise ValueError('Encoder inspection cancelled.') from exc
            failures[label] = str(exc)
    return available, failures


class EncoderProbeCache:
    """Short-lived editor capability checks; manual recheck always bypasses."""
    def __init__(self, inspect):
        self.inspect = inspect
        self.entry = None
        self.lock = threading.Lock()

    def get(self, ffmpeg, force=False):
        path = Path(ffmpeg).resolve()
        try:
            stat = path.stat()
            key = (str(path), stat.st_size, stat.st_mtime_ns)
        except OSError:
            key = (str(path),)
        with self.lock:
            now = time.monotonic()
            if not force and self.entry and self.entry[0] == key and now < self.entry[1]:
                labels, errors = self.entry[2]
                return list(labels), dict(errors)
            labels, errors = self.inspect(ffmpeg)
            # A busy/unavailable GPU can recover quickly; don't pin failures.
            self.entry = (key, time.monotonic()+(30 if errors else 300), (list(labels), dict(errors)))
            return list(labels), dict(errors)


def normalize_ranges(ranges, duration=None):
    """Sorted, merged (start, end) ranges; empty or reversed ranges are dropped."""
    cleaned = []
    for a, b in ranges:
        a, b = float(a), float(b)
        if duration is not None:
            a, b = max(0.0, a), min(float(duration), b)
        if math.isfinite(a) and math.isfinite(b) and b - a > 1e-6:
            cleaned.append((a, b))
    merged = []
    for a, b in sorted(cleaned):
        if merged and a <= merged[-1][1] + 1e-6:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def add_range(ranges, a, b, duration=None):
    return normalize_ranges(list(ranges) + [(a, b)], duration)


def remove_range(ranges, a, b):
    result = []
    for x, y in normalize_ranges(ranges):
        if y <= a or x >= b:
            result.append((x, y))
            continue
        if x < a:
            result.append((x, a))
        if y > b:
            result.append((b, y))
    return normalize_ranges(result)


def keep_only_range(a, b, duration):
    """Mute everything on a track except a..b ("trim" that track)."""
    return normalize_ranges([(0.0, a), (b, duration)], duration)


def mute_filter(ranges, start, end):
    """volume filter silencing source-time ranges inside an export that begins at start."""
    parts = []
    for a, b in normalize_ranges(ranges):
        a, b = max(a, start) - start, min(b, end) - start
        if b - a > 1e-6:
            parts.append(f'between(t,{a:.6f},{b:.6f})')
    return f"volume=0:enable='{'+'.join(parts)}'" if parts else ''


@dataclass
class Edit:
    start: float
    end: float
    encoder: str = 'CPU H.264'
    bitrate: int = 20000
    # stream index, title, gain: each remains a separate output track
    audio: list = field(default_factory=list)
    crop: tuple | None = None  # x, y, width, height
    brightness: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    remix: bool = False
    resolution: tuple | None = None
    fps: int = 0
    upscale: bool = False
    # stream index -> muted (start, end) ranges in source seconds; the track keeps its length
    mutes: dict = field(default_factory=dict)


def export_args(info, edit, ffmpeg, destination):
    audio_codec = {'.mp3': 'libmp3lame', '.wav': 'pcm_s16le', '.flac': 'flac', '.m4a': 'aac'}.get(Path(destination).suffix.lower())
    if not (math.isfinite(edit.start) and math.isfinite(edit.end) and 0 <= edit.start < edit.end <= info['duration'] + .001):
        raise ValueError('Choose a start before the end, inside the clip.')
    copy = edit.encoder == COPY and not audio_codec
    if not audio_codec and not copy and (edit.encoder not in ENCODERS or not 1000 <= edit.bitrate <= 200000):
        raise ValueError('Choose an available encoder and valid bitrate.')
    blocking = [name for name, active in (
        ('crop (Filters → Reset filters)', edit.crop),
        ('color changes (Filters → Reset filters)', (edit.brightness, edit.contrast, edit.saturation) != (0.0, 1.0, 1.0)),
        ('resolution', edit.resolution), ('FPS', edit.fps), ('upscaling', edit.upscale)) if active]
    if copy and blocking:
        raise ValueError('Copy keeps the original video untouched, so it cannot apply your '
                         + ' and '.join(blocking) + '. Reset that, or choose an encoder to re-encode.')
    dest, source = Path(destination), Path(info['path'])
    if dest.resolve() == source.resolve() or (dest.exists() and source.exists() and dest.samefile(source)):
        raise ValueError('Export must use a new filename; the original is protected.')
    filters = []
    if edit.crop:
        x, y, w, h = edit.crop
        video = info['video']
        if any(type(v) is not int or v < 0 or v % 2 for v in edit.crop) or min(w, h) < 2 or x+w > video['width'] or y+h > video['height']:
            raise ValueError('Crop must use even pixels and stay inside the source image.')
        filters.append(f'crop={w}:{h}:{x}:{y}')
    if not (-1 <= edit.brightness <= 1 and 0 <= edit.contrast <= 2 and 0 <= edit.saturation <= 2):
        raise ValueError('Invalid color filter values.')
    if edit.resolution:
        if len(edit.resolution) != 2 or any(type(v) is not int or v < 2 or v > 4096 or v % 2 for v in edit.resolution):
            raise ValueError('Export resolution must use even dimensions from 2 to 4096.')
        w, h = edit.resolution
        # Always preserve the selected canvas/aspect ratio. Without explicit
        # opt-in, fit inside BOTH the canvas and original cropped dimensions.
        sw, sh = edit.crop[2:] if edit.crop else (info['video']['width'], info['video']['height'])
        try:
            sar = float(Fraction(info['video'].get('sample_aspect_ratio', '1:1').replace(':', '/')))
            sw *= sar if math.isfinite(sar) and sar > 0 else 1
        except (ValueError, ZeroDivisionError, AttributeError):
            pass
        scale = min(w/sw, h/sh)
        if not edit.upscale:
            scale = min(1.0, scale)
        fw, fh = max(2, int(sw*scale)//2*2), max(2, int(sh*scale)//2*2)
        filters += [f'scale={fw}:{fh}:flags=lanczos', 'setsar=1', f'pad={w}:{h}:(ow-iw)/2:(oh-ih)/2']
    if edit.fps not in (0, 24, 30, 60):
        raise ValueError('Choose source FPS, 24, 30 or 60.')
    if edit.fps:
        filters.append(f'fps={edit.fps}')
    filters += [f'eq=brightness={edit.brightness}:contrast={edit.contrast}:saturation={edit.saturation}', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', 'format=yuv420p']
    args = [ffmpeg, '-hide_banner', '-v', 'error', '-nostdin', '-n', '-ss', f'{edit.start:.6f}', '-i', info['path'],
            '-t', f'{edit.end-edit.start:.6f}', '-map', f"0:{info['video']['index']}"]
    if copy:
        # Copied video must start on a keyframe, so it begins at the keyframe before Start.
        # Shifting every stream by the same offset keeps re-encoded audio in sync.
        args += ['-c:v', 'copy', '-avoid_negative_ts', 'make_zero']
    else:
        args += ['-vf', ','.join(filters), '-c:v', ENCODERS.get(edit.encoder, 'libx264'), '-b:v', f'{edit.bitrate}k']
    indexes = {s['index'] for s in info['audio']}
    if audio_codec:
        if not edit.audio:
            raise ValueError('Select an audio track to export.')
        if len(edit.audio) > 1 and not edit.remix:
            raise ValueError('Audio exports need one track. Select one track or enable combining audio tracks.')
        args = [ffmpeg, '-hide_banner', '-v', 'error', '-nostdin', '-n', '-ss', f'{edit.start:.6f}', '-i', info['path'],
                '-t', f'{edit.end-edit.start:.6f}', '-vn']
    if not audio_codec and not copy and ENCODERS[edit.encoder].endswith('_amf'):
        args += ['-rc', 'cbr']
    seen = set()
    if edit.remix and len(edit.audio) > 1 and any(title.strip().casefold() == 'mix' for _, title, _ in edit.audio):
        raise ValueError('Uncheck the existing Mix track before combining isolated tracks; otherwise audio is doubled.')
    mix_filters = []
    for ranges in (edit.mutes or {}).values():
        if any(not (math.isfinite(a) and math.isfinite(b) and 0 <= a < b <= info['duration'] + .001) for a, b in ranges):
            raise ValueError('Muted audio ranges must lie inside the clip.')
    for i, (index, title, gain) in enumerate(edit.audio):
        if index not in indexes or index in seen or not math.isfinite(gain) or not 0 <= gain <= 2:
            raise ValueError('Invalid audio track or volume.')
        seen.add(index)
        mutes = mute_filter((edit.mutes or {}).get(index, ()), edit.start, edit.end)
        chain = ','.join(f for f in (f'volume={gain}', mutes) if f)
        if edit.remix:
            mix_filters.append(f'[0:{index}]{chain}[audio{i}]')
        else:
            args += ['-map', f'0:{index}']
            if copy and gain == 1 and not mutes:
                args += [f'-c:a:{i}', 'copy']
            else:
                args += [f'-filter:a:{i}', chain]
                if copy:
                    args += [f'-c:a:{i}', 'aac', f'-b:a:{i}', '192k']
            args += [f'-metadata:s:a:{i}', f'title={title}', f'-disposition:a:{i}', 'default' if i == 0 else '0']
    if edit.remix and edit.audio:
        inputs = ''.join(f'[audio{i}]' for i in range(len(edit.audio)))
        mix_filters.append(f'{inputs}amix=inputs={len(edit.audio)}:normalize=0:dropout_transition=0,alimiter=limit=0.98:level=false:latency=true[remix]')
        args += ['-filter_complex', ';'.join(mix_filters), '-map', '[remix]', '-metadata:s:a:0', 'title=Remix', '-disposition:a:0', 'default']
    if not copy:
        args += ['-c:a', audio_codec or 'aac']
        if audio_codec not in ('pcm_s16le', 'flac'):
            args += ['-b:a', '192k']
    elif edit.remix and edit.audio:
        args += ['-c:a:0', 'aac', '-b:a:0', '192k']
    args += ['-map_metadata', '-1', '-map_chapters', '-1', '-progress', 'pipe:1', '-nostats']
    if Path(destination).suffix.lower() == '.mp4':
        args += ['-movflags', '+faststart']
    return args + [str(destination)]


def file_identity(path):
    stat = Path(path).stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def export_clip(info, edit, ffmpeg, target, cancel=None, progress=None, *, overwrite=False, expected_target=None):
    target = Path(target).resolve()
    if target.suffix.lower() not in ('.mkv', '.mp4', '.mp3', '.wav', '.flac', '.m4a'):
        raise ValueError('Choose an MKV, MP4, MP3, WAV, FLAC or M4A filename.')
    if target.exists() and not overwrite:
        raise ValueError('That file already exists. Confirm replacement or choose a new filename.')
    approved = expected_target
    if overwrite:
        current = file_identity(target) if target.exists() else None
        if approved is None:
            approved = current
        if current is None or current != approved:
            raise ValueError('The destination changed since confirmation. Export again to confirm the current file.')
    export_args(info, edit, ffmpeg, target)  # validate before allocating files
    cancel = cancel or threading.Event()
    target.parent.mkdir(parents=True, exist_ok=True)
    # Private sibling directory keeps promotion on the same filesystem.
    with tempfile.TemporaryDirectory(prefix='.clipnest-export-', dir=target.parent) as temp:
        partial = Path(temp) / target.name
        args = export_args(info, edit, ffmpeg, partial)
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors, text=True,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            def read_progress():
                for line in process.stdout:
                    if line.startswith('out_time_us=') and progress:
                        try:
                            progress(min(99, max(0, int(float(line.split('=')[1]) / ((edit.end-edit.start)*10000)))))
                        except ValueError:
                            pass
            reader = threading.Thread(target=read_progress, daemon=True)
            reader.start()
            try:
                while process.poll() is None:
                    if cancel.wait(.1):
                        process.terminate()
                        try:
                            process.wait(3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                        break
                process.wait()
                reader.join()
                if cancel.is_set():
                    raise ValueError('Export cancelled. Original unchanged.')
                if process.returncode or not partial.exists() or partial.stat().st_size == 0:
                    errors.seek(0)
                    raise ValueError(errors.read().decode('utf-8', 'replace')[-3000:] or 'Export failed.')
                # A confirmed replacement is published only after successful encoding.
                # Unconfirmed new destinations retain exclusive no-overwrite publication.
                try:
                    if overwrite:
                        export_args(info, edit, ffmpeg, target)  # recheck source identity before replacement
                        if not target.exists() or file_identity(target) != approved:
                            raise ValueError('The destination changed during export. It was not replaced.')
                        os.replace(partial, target)
                    else:
                        os.link(partial, target)
                except OSError as exc:
                    raise ValueError(f'Cannot publish export safely. Choose a new name on an NTFS/local drive. {exc}') from exc
                if progress:
                    progress(100)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                reader.join(timeout=3)
                process.stdout.close()
    return str(target)


def estimated_size(edit, info=None):
    if edit.encoder == COPY and info:
        # Copy keeps the source bitrate; the keyframe pre-roll adds a little.
        try:
            return os.path.getsize(info['path']) * max(0, edit.end-edit.start) / info['duration']
        except (OSError, KeyError, ZeroDivisionError):
            return 0
    tracks = 1 if edit.remix and edit.audio else len(edit.audio)
    return max(0, edit.end-edit.start) * (edit.bitrate + 192*tracks) * 1000/8


class ExportETA:
    """Smoothed throughput from FFmpeg's encoded media progress."""
    def __init__(self):
        import time
        self.clock = time.monotonic
        self.reset()

    def reset(self):
        self.started = self.previous = self.clock()
        self.percent = 0
        self.rate = None

    def update(self, percent):
        now = self.clock()
        elapsed = now-self.previous
        if percent > self.percent and elapsed > 0:
            rate = (percent-self.percent)/elapsed
            self.rate = rate if self.rate is None else .25*rate + .75*self.rate
            self.percent, self.previous = percent, now
        if now-self.started < 2 or not self.rate or percent <= 0:
            return None
        return max(0, (100-percent)/self.rate)
