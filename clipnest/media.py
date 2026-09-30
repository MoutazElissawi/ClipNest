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

ENCODERS = {'NVIDIA H.264': 'h264_nvenc', 'NVIDIA AV1': 'av1_nvenc', 'CPU H.264': 'libx264'}


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


def probe(path, ffprobe):
    result = run([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], timeout=30)
    if result.returncode:
        raise ValueError(result.stderr[-2000:] or 'Cannot inspect this clip.')
    info = json.loads(result.stdout)
    video = next((s for s in info.get('streams', []) if s['codec_type'] == 'video' and not s.get('disposition', {}).get('attached_pic')), None)
    if not video:
        raise ValueError('This file has no video stream.')
    duration = float(info.get('format', {}).get('duration', video.get('duration', 0)))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('This clip has no finite duration. Finish recording before opening it.')
    return dict(path=str(Path(path).resolve()), duration=duration, video=video,
                audio=[s for s in info['streams'] if s['codec_type'] == 'audio'])


def available_encoders(ffmpeg):
    """Actually encode two frames: listing an encoder does not prove GPU support."""
    available, failures = [], {}
    for label, encoder in ENCODERS.items():
        try:
            result = run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'color=s=1280x720:r=30',
                          '-frames:v', '2', '-c:v', encoder, '-pix_fmt', 'yuv420p', '-f', 'null', '-'], timeout=20)
            if result.returncode == 0:
                available.append(label)
            else:
                failures[label] = result.stderr[-1200:]
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures[label] = str(exc)
    return available, failures


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


def export_args(info, edit, ffmpeg, destination):
    if not (math.isfinite(edit.start) and math.isfinite(edit.end) and 0 <= edit.start < edit.end <= info['duration'] + .001):
        raise ValueError('Choose a start before the end, inside the clip.')
    if edit.encoder not in ENCODERS or not 1000 <= edit.bitrate <= 200000:
        raise ValueError('Choose an available encoder and valid bitrate.')
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
    filters += [f'eq=brightness={edit.brightness}:contrast={edit.contrast}:saturation={edit.saturation}', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', 'format=yuv420p']
    args = [ffmpeg, '-hide_banner', '-v', 'error', '-nostdin', '-n', '-ss', f'{edit.start:.6f}', '-i', info['path'],
            '-t', f'{edit.end-edit.start:.6f}', '-map', f"0:{info['video']['index']}", '-vf', ','.join(filters),
            '-c:v', ENCODERS[edit.encoder], '-b:v', f'{edit.bitrate}k']
    indexes = {s['index'] for s in info['audio']}
    seen = set()
    if edit.remix and len(edit.audio) > 1 and any(title.strip().casefold() == 'mix' for _, title, _ in edit.audio):
        raise ValueError('Uncheck the existing Mix track before combining isolated tracks; otherwise audio is doubled.')
    mix_filters = []
    for i, (index, title, gain) in enumerate(edit.audio):
        if index not in indexes or index in seen or not math.isfinite(gain) or not 0 <= gain <= 2:
            raise ValueError('Invalid audio track or volume.')
        seen.add(index)
        if edit.remix:
            mix_filters.append(f'[0:{index}]volume={gain}[audio{i}]')
        else:
            args += ['-map', f'0:{index}', f'-filter:a:{i}', f'volume={gain}', f'-metadata:s:a:{i}', f'title={title}',
                     f'-disposition:a:{i}', 'default' if i == 0 else '0']
    if edit.remix and edit.audio:
        inputs = ''.join(f'[audio{i}]' for i in range(len(edit.audio)))
        mix_filters.append(f'{inputs}amix=inputs={len(edit.audio)}:normalize=0:dropout_transition=0,alimiter=limit=0.98:level=false:latency=true[remix]')
        args += ['-filter_complex', ';'.join(mix_filters), '-map', '[remix]', '-metadata:s:a:0', 'title=Remix', '-disposition:a:0', 'default']
    args += ['-c:a', 'aac', '-b:a', '192k', '-map_metadata', '-1', '-map_chapters', '-1', '-progress', 'pipe:1', '-nostats']
    if Path(destination).suffix.lower() == '.mp4':
        args += ['-movflags', '+faststart']
    return args + [str(destination)]


def file_identity(path):
    stat = Path(path).stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def export_clip(info, edit, ffmpeg, target, cancel=None, progress=None, *, overwrite=False, expected_target=None):
    target = Path(target).resolve()
    if target.suffix.lower() not in ('.mkv', '.mp4'):
        raise ValueError('Choose an MKV or MP4 filename.')
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
