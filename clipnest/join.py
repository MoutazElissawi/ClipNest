"""Join completed clips with explicit compatibility checks and safe publication."""
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from .media import probe, Edit, export_args, file_identity


def copy_compatible(infos):
    def signature(info):
        video = info['video']
        video_fields = ('codec_name', 'profile', 'level', 'width', 'height', 'pix_fmt', 'sample_aspect_ratio',
                        'field_order', 'r_frame_rate', 'avg_frame_rate', 'time_base', 'extradata',
                        'color_range', 'color_space', 'color_transfer', 'color_primaries')
        audio_fields = ('codec_name', 'profile', 'sample_rate', 'channels', 'channel_layout', 'time_base', 'extradata')
        return (tuple(video.get(k) for k in video_fields),
                tuple((tuple(a.get(k) for k in audio_fields), a.get('tags', {}).get('title', '')) for a in info['audio']))
    return len(infos) >= 2 and all(signature(info) == signature(infos[0]) for info in infos[1:])


def execute(args, duration, cancel, progress):
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        def read():
            for line in process.stdout:
                if line.startswith('out_time_us='):
                    try:
                        progress(min(99, max(0, float(line.split('=')[1])/duration/10000)))
                    except ValueError:
                        pass
        reader = threading.Thread(target=read, daemon=True)
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
            reader.join(3)
            if cancel.is_set():
                raise ValueError('Combine cancelled. Source clips are unchanged.')
            if process.returncode:
                errors.seek(0)
                raise ValueError(errors.read()[-3000:].decode('utf-8', 'replace') or 'Combine failed.')
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            reader.join(3)
            process.stdout.close()


def combine(paths, ffmpeg, ffprobe, target, reencode=False, encoder='CPU H.264', bitrate=20000,
            cancel=None, progress=None, confirm_audio_order=False):
    cancel = cancel or threading.Event()
    progress = progress or (lambda value: None)
    target = Path(target).resolve()
    paths = [Path(path).resolve() for path in paths]
    if len(paths) < 2 or len(set(paths)) != len(paths):
        raise ValueError('Select at least two different clips.')
    if target in paths or target.exists():
        raise ValueError('Choose a new destination filename. Existing files and source clips are protected.')
    if target.suffix.lower() not in ('.mkv', '.mp4'):
        raise ValueError('Choose MKV or MP4.')
    identities, infos = [], []
    for path in paths:
        if cancel.is_set():
            raise ValueError('Combine cancelled.')
        identities.append(file_identity(path))
        infos.append(probe(path, ffprobe, cancel))
    if not reencode and not copy_compatible(infos):
        raise ValueError('These clips need re-encoding. Choose the re-encode option.')
    count = len(infos[0]['audio'])
    if any(len(info['audio']) != count for info in infos):
        raise ValueError('Audio track counts differ. Export clips with the same intended tracks before combining; no tracks were dropped.')
    titles = lambda info: [a.get('tags', {}).get('title', '') for a in info['audio']]
    if reencode and any(titles(info) != titles(infos[0]) for info in infos) and not confirm_audio_order:
        raise ValueError('Audio titles differ. Confirm that tracks should match by their position.')
    total = sum(info['duration'] for info in infos)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.clipnest-join-', dir=target.parent) as tmp:
        tmp = Path(tmp)
        inputs = paths
        if reencode:
            inputs = []
            first = infos[0]
            resolution = tuple(int(first['video'][k])//2*2 for k in ('width', 'height'))
            elapsed = 0
            for n, info in enumerate(infos):
                partial = tmp/f'part-{n}.mkv'
                tracks = [(a['index'], first['audio'][i].get('tags', {}).get('title', f'Audio {i+1}'), 1.) for i,a in enumerate(info['audio'])]
                edit = Edit(0, info['duration'], encoder, bitrate, tracks, resolution=resolution, fps=60)
                args = export_args(info, edit, ffmpeg, partial)
                # Normalize every audio track to stereo/48kHz and equal duration.
                for i in range(count):
                    index = args.index(f'-filter:a:{i}')+1
                    args[index] += f",aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration={info['duration']:.6f}"
                execute(args, info['duration'], cancel, lambda value, done=elapsed, duration=info['duration']: progress(int(90*(done+duration*value/100)/total)))
                inputs.append(partial)
                elapsed += info['duration']
        manifest = tmp/'inputs.txt'
        lines = []
        for path in inputs:
            name = path.as_posix()
            if '\n' in name or '\r' in name:
                raise ValueError('A clip path contains a newline; rename it before combining.')
            escaped = name.replace("'", "'\\''")
            lines.append("file '" + escaped + "'\n")
        manifest.write_text(''.join(lines), encoding='utf-8')
        output = tmp/('combined'+target.suffix)
        args = [ffmpeg, '-hide_banner', '-v', 'error', '-nostdin', '-n', '-f', 'concat', '-safe', '0', '-i', str(manifest),
                '-map', '0:v:0', '-map', '0:a?', '-c', 'copy', '-map_chapters', '-1', '-progress', 'pipe:1', '-nostats']
        if target.suffix.lower() == '.mp4':
            args += ['-movflags', '+faststart']
        execute(args+[str(output)], total, cancel, lambda value: progress(int(90+value*.09) if reencode else int(value)))
        if cancel.is_set():
            raise ValueError('Combine cancelled.')
        if not output.exists() or not output.stat().st_size:
            raise ValueError('No output was produced.')
        result = probe(output, ffprobe, cancel)
        if len(result['audio']) != count:
            raise ValueError('Output audio verification failed. No file was published.')
        if any(file_identity(path) != identity for path, identity in zip(paths, identities)):
            raise ValueError('A source changed during combining. No file was published.')
        # Hard-link publication is exclusive and on the destination filesystem.
        if cancel.is_set():
            raise ValueError('Combine cancelled.')
        os.link(output, target)
    progress(100)
    return str(target)
