"""Bounded disk replay segments. Native libobs owns capture and keyframe splitting.

All disk work runs off the controller/native threads. Successful saves consume
closed segments; capture keeps writing the next one. Failed saves retain sources.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import math
import mmap
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time
from fractions import Fraction
from .config import MAX_TRACKS
from .media import run


class ReplayCancelled(RuntimeError):
    pass


def replay_run(args, *, timeout, cancel=None):
    if cancel is None:
        return run(args, timeout=timeout)
    if cancel.is_set():
        raise ReplayCancelled('Closing ClipNest; unfinished replay sources were retained')
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, encoding='utf-8', errors='replace',
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0) as process:
        deadline = time.monotonic()+timeout
        try:
            while True:
                if cancel.is_set():
                    raise ReplayCancelled('Closing ClipNest; unfinished replay sources were retained')
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(args, timeout)
                try:
                    out, err = process.communicate(timeout=min(.2, remaining))
                    return subprocess.CompletedProcess(args, process.returncode, out, err)
                except subprocess.TimeoutExpired:
                    pass
        except BaseException:
            process.kill()
            process.communicate()
            raise


@dataclass
class Segment:
    path: Path
    duration: float
    start: float = 0.0


class Unreadable(Exception):
    """The segment uses a Matroska layout this reader leaves to ffprobe."""


# Matroska element IDs, marker bits included.
SEGMENT, INFO, TIMESTAMP_SCALE = 0x18538067, 0x1549A966, 0x2AD7B1
TRACKS, TRACK_ENTRY, TRACK_NUMBER, TRACK_TYPE, DEFAULT_DURATION = 0x1654AE6B, 0xAE, 0xD7, 0x83, 0x23E383
CLUSTER, CLUSTER_TIMESTAMP, SIMPLE_BLOCK, BLOCK_GROUP, BLOCK, REFERENCE_BLOCK = 0x1F43B675, 0xE7, 0xA3, 0xA0, 0xA1, 0xFB
REORDER_WINDOW = 16  # B-frames reorder a few frames; a frame older than this many packets is a timestamp reversal


def ebml_elements(data, start, end):
    """(id, body start, body end) of each EBML element in data[start:end]."""
    pos = start
    while pos < end:
        id_length = 9 - data[pos].bit_length()
        size_length = 9 - data[pos + id_length].bit_length() if 1 <= id_length <= 4 else 0
        if not 1 <= size_length <= 8:
            raise Unreadable('Invalid element header')
        ident = int.from_bytes(data[pos:pos + id_length], 'big')
        size = int.from_bytes(data[pos + id_length:pos + id_length + size_length], 'big') & ((1 << 7 * size_length) - 1)
        body = pos + id_length + size_length
        if size == (1 << 7 * size_length) - 1:  # unknown size, only written by unseekable muxing
            if ident != SEGMENT:
                raise Unreadable('Element of unknown size')
            size = end - body
        if body + size > end:
            raise Unreadable('Truncated element')
        yield ident, body, body + size
        pos = body + size


def frame_rate(default_duration):
    """FFmpeg's average frame rate for a Matroska DefaultDuration in ns: av_reduce(1e9, duration, 30000)."""
    num, den, limit = 1_000_000_000, default_duration, 30000
    common = math.gcd(num, den)
    num, den = num // common, den // common
    if num <= limit and den <= limit:
        return Fraction(num, den)
    a0, a1 = (0, 1), (1, 0)
    while den:
        x, next_den = divmod(num, den)
        a2 = (x * a1[0] + a0[0], x * a1[1] + a0[1])
        if a2[0] > limit or a2[1] > limit:
            x = min((limit - a0[0]) // a1[0] if a1[0] else x, (limit - a0[1]) // a1[1] if a1[1] else x)
            if den * (2 * x * a1[1] + a0[1]) > num * a1[1]:
                a1 = (x * a1[0] + a0[0], x * a1[1] + a0[1])
            break
        a0, a1, num, den = a1, a2, den, next_den
    return Fraction(*a1)


def matroska_timing(path):
    """Streams and packets of a closed Matroska segment without starting ffprobe.
    Returns (video index, video rate, audio indexes, packets as (index, pts, dts or None, keyframe)) in file order.
    The video DTS is FFmpeg's guess, so this checks the video's reorder window itself. Audio keeps the codec
    delay FFmpeg subtracts, which leaves its order, the only thing checked, unchanged."""
    with open(path, 'rb') as file:
        if not os.fstat(file.fileno()).st_size:
            raise Unreadable('Empty segment')
        # Only block headers are read; mapping skips copying the video payload.
        with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as data:
            return matroska_packets(data)


def matroska_packets(data):
    scale, tracks, packets = 1_000_000, [], []
    segment = next((body, end) for ident, body, end in ebml_elements(data, 0, len(data)) if ident == SEGMENT)
    for ident, body, end in ebml_elements(data, *segment):
        if ident == INFO:
            scale = next((int.from_bytes(data[b:e], 'big') for i, b, e in ebml_elements(data, body, end) if i == TIMESTAMP_SCALE), scale)
        elif ident == TRACKS:
            for entry, b, e in ebml_elements(data, body, end):
                if entry == TRACK_ENTRY:
                    fields = {i: int.from_bytes(data[fb:fe], 'big') for i, fb, fe in ebml_elements(data, b, e)
                              if i in (TRACK_NUMBER, TRACK_TYPE, DEFAULT_DURATION)}
                    tracks.append(fields)
        elif ident == CLUSTER:
            cluster = 0
            for child, b, e in ebml_elements(data, body, end):
                if child == CLUSTER_TIMESTAMP:
                    cluster = int.from_bytes(data[b:e], 'big')
                elif child in (SIMPLE_BLOCK, BLOCK_GROUP):
                    keyframe = None
                    if child == BLOCK_GROUP:
                        group = list(ebml_elements(data, b, e))
                        b, e = next(((gb, ge) for i, gb, ge in group if i == BLOCK), (b, b))
                        keyframe = not any(i == REFERENCE_BLOCK for i, _, _ in group)
                    length = 9 - data[b].bit_length()
                    if not 1 <= length <= 8 or b + length + 3 > e or data[b + length + 2] & 0x06:
                        raise Unreadable('Laced or empty block')  # FFmpeg never laces; leave it to ffprobe
                    track = int.from_bytes(data[b:b + length], 'big') & ((1 << 7 * length) - 1)
                    offset = int.from_bytes(data[b + length:b + length + 2], 'big', signed=True)
                    if keyframe is None:
                        keyframe = bool(data[b + length + 2] & 0x80)
                    packets.append((track, (cluster + offset) * scale / 1e9, keyframe))
    video = next((t for t in tracks if t.get(TRACK_TYPE) == 1), None)
    audio = [t[TRACK_NUMBER] for t in tracks if t.get(TRACK_TYPE) == 2 and TRACK_NUMBER in t]
    if video is None or TRACK_NUMBER not in video or not video.get(DEFAULT_DURATION):
        raise Unreadable('No video frame duration')
    index, rate = video[TRACK_NUMBER], frame_rate(video[DEFAULT_DURATION])
    stamps = [pts for track, pts, _ in packets if track == index]
    newest = float('-inf')
    for i in range(REORDER_WINDOW, len(stamps)):
        newest = max(newest, stamps[i - REORDER_WINDOW])
        if stamps[i] < newest:
            raise ValueError('Replay segment has invalid media timestamps. Cache retained.')
    return index, rate, audio, [(track, pts, None if track == index else pts, keyframe) for track, pts, keyframe in packets]


def ffprobe_timing(path, ffprobe, cancel=None):
    """The same streams and packets as matroska_timing, read by ffprobe."""
    r = replay_run([ffprobe, '-v', 'error', '-show_packets',
             '-show_entries', 'packet=stream_index,pts_time,dts_time,duration_time,flags:stream=index,codec_type,avg_frame_rate', '-show_streams', '-of', 'json', str(path)], timeout=20, cancel=cancel)
    if r.returncode:
        raise ValueError(r.stderr[-1000:] or 'Segment is not ready')
    data = json.loads(r.stdout)
    streams = data.get('streams', [])
    video = next((s for s in streams if s.get('codec_type') == 'video'), None)
    audio = [s['index'] for s in streams if s.get('codec_type') == 'audio']
    packets = [(p.get('stream_index'), float(p['pts_time']) if 'pts_time' in p else None,
                float(p['dts_time']) if 'dts_time' in p else None, 'K' in p.get('flags', ''))
               for p in data.get('packets', [])]
    return (video['index'] if video else None), (video or {}).get('avg_frame_rate', '30/1'), audio, packets


def segment_timing(path, ffprobe, cancel=None):
    """(duration, start) of a closed replay segment: its video span, for joining segments without gaps or overlap.
    A segment closes every two seconds, so it is read directly; ffprobe reads anything else."""
    if cancel is not None and cancel.is_set():
        raise ReplayCancelled('Closing ClipNest; unfinished replay sources were retained')
    try:
        video, rate, audio, packets = matroska_timing(path)
    except (Unreadable, OSError, IndexError, StopIteration):
        video, rate, audio, packets = ffprobe_timing(path, ffprobe, cancel)
    # Standard: Mix, Desktop, Microphone (+ application, + game). One track per app: 1-6 chosen sources.
    if video is None or not 1 <= len(audio) <= MAX_TRACKS:
        raise ValueError('Replay segment is missing video or one of its audio tracks. Cache retained.')
    indexes = {index for index, *_ in packets}
    if any(index not in indexes for index in [video, *audio]):
        raise ValueError('Replay segment contains an empty media track. Cache retained.')
    frames = [p for p in packets if p[0] == video]
    if frames and not frames[0][3]:
        raise ValueError('Replay segment does not begin with a keyframe. Cache retained.')
    for stream in [video, *audio]:
        times = [dts for index, _, dts, _ in packets if index == stream and dts is not None]
        if any(not math.isfinite(t) for t in times) or any(b < a for a, b in zip(times, times[1:])):
            raise ValueError('Replay segment has invalid media timestamps. Cache retained.')
    stamps = [pts for _, pts, _, _ in frames if pts is not None]
    if not stamps:
        raise ValueError('Segment has no video packets')
    rate = float(Fraction(rate))
    if not math.isfinite(rate) or rate <= 0 or any(not math.isfinite(t) for t in stamps):
        raise ValueError('Replay segment has invalid video timing. Cache retained.')
    return max(stamps)-min(stamps)+1/rate, min(stamps)


def concat_segments(segments, ffmpeg, destination, cancel=None):
    """Copy encoded packets, preserving all audio tracks and explicit video spans."""
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Replay destination already exists')
    with tempfile.TemporaryDirectory(prefix='.replay-save-', dir=destination.parent) as temp:
        listing = Path(temp)/'segments.ffconcat'
        lines = ['ffconcat version 1.0']
        for seg in segments:
            path = str(seg.path.resolve()).replace('\\', '/')
            if '\n' in path or '\r' in path:
                raise ValueError('Invalid replay cache path')
            lines += ["file '" + path.replace("'", "'\\''") + "'", f'inpoint {seg.start:.9f}', f'duration {seg.duration:.9f}']
        listing.write_text('\n'.join(lines)+'\n', encoding='utf-8')
        partial = Path(temp)/'saved.mkv'
        r = replay_run([ffmpeg, '-v', 'error', '-nostdin', '-n', '-copyts', '-f', 'concat', '-safe', '0', '-i', str(listing),
                 '-map', '0', '-c', 'copy', '-avoid_negative_ts', 'disabled', '-t', f'{sum(s.duration for s in segments):.9f}', str(partial)], timeout=180, cancel=cancel)
        if r.returncode or not partial.exists() or not partial.stat().st_size:
            raise ValueError(r.stderr[-2000:] or 'Could not join replay segments')
        os.link(partial, destination)
    return str(destination)


class ContinuousReplay(threading.Thread):
    def __init__(self, ffmpeg, ffprobe, staging, seconds, wake=None):
        super().__init__(name='ClipNest replay files', daemon=True)
        self.ffmpeg, self.ffprobe = ffmpeg, ffprobe
        self.staging = Path(staging).resolve()
        self.seconds = seconds
        self.wake = wake or (lambda: None)  # tells the engine a result is waiting
        self.commands, self.results = queue.Queue(), queue.Queue()
        self.segments = []
        self.expired = False
        self.failed = False
        self.close_requested = False
        self.cancel = threading.Event()
        self.shutdown_timer = None
        self._shutdown_lock = threading.Lock()
        self.start()

    def add(self, path, next_path=None, context=None):
        self.commands.put(('segment', path, next_path, context))

    def report(self, *result):
        self.results.put(result)
        self.wake()

    def close(self):
        if not self.close_requested:
            self.close_requested = True
            self.commands.put(('close',))
        self.join(5)
        if self.is_alive():
            raise RuntimeError('Replay files are still finishing. Wait before closing.')

    def begin_shutdown(self, timeout=25):
        with self._shutdown_lock:
            if self.shutdown_timer is not None:
                return
            self.shutdown_timer = threading.Timer(timeout, self.abort)
            self.shutdown_timer.daemon = True
            self.shutdown_timer.start()

    def abort(self):
        # Wake an idle worker or cancel its owned ffmpeg/ffprobe child. Cache
        # files and pending contexts stay available for recovery.
        self.cancel.set()
        self.commands.put(('close',))

    def discard(self, segments):
        for seg in segments:
            if self.cancel.is_set():
                return
            try:
                seg.path.unlink(missing_ok=True)
            except OSError:
                # An antivirus/reader may hold a file; never fail capture or touch unrelated files.
                pass

    def validate_path(self, value):
        path = Path(value).resolve()
        if self.staging / '_ReplayCache' not in path.parents:
            raise ValueError('Replay segment is outside the private cache')
        return path

    def run(self):
        while True:
            command = self.commands.get()
            if command[0] == 'close':
                if not self.failed:
                    self.discard(self.segments)
                if self.shutdown_timer is not None:
                    self.shutdown_timer.cancel()
                return
            _, raw, next_path, context = command
            validated = False
            try:
                if self.cancel.is_set():
                    raise ReplayCancelled('Closing ClipNest; unfinished replay sources were retained')
                path = self.validate_path(raw)
                # file_changed is signalled before the helper consumes the change.
                # Its new-file creation follows closing the old segment.
                if next_path:
                    following = self.validate_path(next_path)
                    deadline = time.monotonic()+10
                    while not following.exists():
                        if time.monotonic() > deadline:
                            raise ValueError('Replay segment close timed out')
                        if self.cancel.wait(.05):
                            raise ReplayCancelled('Closing ClipNest; unfinished replay sources were retained')
                duration, start = segment_timing(path, self.ffprobe, cancel=self.cancel)
                validated = True
                self.segments.append(Segment(path, duration, start))
                total = sum(s.duration for s in self.segments)
                while len(self.segments) > 1 and total-self.segments[0].duration >= self.seconds:
                    old = self.segments.pop(0)
                    total -= old.duration
                    if not self.failed:
                        self.discard([old])
                    self.expired = True
                if context:
                    destination = self.staging / ('Saved_' + str(time.time_ns()) + '.mkv')
                    saved = concat_segments(self.segments, self.ffmpeg, destination, cancel=self.cancel)
                    self.report('saved', saved, context, self.expired or self.failed)
                    self.discard(self.segments)
                    self.segments = []
                    self.expired = self.failed = False
            except Exception as exc:
                if not validated:
                    self.segments = []  # keep cache files, exclude the broken interval from future saves
                self.failed = True
                self.report('aborted' if isinstance(exc, ReplayCancelled) else 'error', str(exc), context, False)
