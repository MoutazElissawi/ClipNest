"""Bounded disk replay segments. Native libobs owns capture and keyframe splitting.

All disk work runs off the controller/native threads. Successful saves consume
closed segments; capture keeps writing the next one. Failed saves retain sources.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time
from fractions import Fraction
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


def segment_timing(path, ffprobe, cancel=None):
    r = replay_run([ffprobe, '-v', 'error', '-show_packets',
             '-show_entries', 'packet=stream_index,pts_time,dts_time,duration_time,flags:stream=index,codec_type,avg_frame_rate', '-show_streams', '-of', 'json', str(path)], timeout=20, cancel=cancel)
    if r.returncode:
        raise ValueError(r.stderr[-1000:] or 'Segment is not ready')
    data = json.loads(r.stdout)
    streams, all_packets = data.get('streams', []), data.get('packets', [])
    video = next((s for s in streams if s.get('codec_type') == 'video'), None)
    audio = [s for s in streams if s.get('codec_type') == 'audio']
    # Mix, Desktop and Microphone, plus an optional application track.
    if video is None or len(audio) not in (3, 4):
        raise ValueError('Replay segment is missing video or one of its audio tracks. Cache retained.')
    indexes = {packet.get('stream_index') for packet in all_packets}
    if any(s['index'] not in indexes for s in [video, *audio]):
        raise ValueError('Replay segment contains an empty media track. Cache retained.')
    packets = [p for p in all_packets if p.get('stream_index') == video['index']]
    if packets and 'K' not in packets[0].get('flags', ''):
        raise ValueError('Replay segment does not begin with a keyframe. Cache retained.')
    for stream in [video, *audio]:
        times = [float(p['dts_time']) for p in all_packets if p.get('stream_index') == stream['index'] and 'dts_time' in p]
        if any(not math.isfinite(t) for t in times) or any(b < a for a,b in zip(times, times[1:])):
            raise ValueError('Replay segment has invalid media timestamps. Cache retained.')
    stamps = [float(p['pts_time']) for p in packets if 'pts_time' in p]
    if not stamps:
        raise ValueError('Segment has no video packets')
    rate = float(Fraction(video.get('avg_frame_rate', '30/1')))
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
    def __init__(self, ffmpeg, ffprobe, staging, seconds):
        super().__init__(name='ClipNest replay files', daemon=True)
        self.ffmpeg, self.ffprobe = ffmpeg, ffprobe
        self.staging = Path(staging).resolve()
        self.seconds = seconds
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

    def reset(self):
        self.commands.put(('reset',))

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
            if command[0] in ('reset', 'close'):
                if not self.failed:
                    self.discard(self.segments)
                self.segments = []
                self.expired = self.failed = False
                if command[0] == 'close':
                    if self.shutdown_timer is not None:
                        self.shutdown_timer.cancel()
                    return
                continue
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
                    self.results.put(('saved', saved, context, self.expired or self.failed))
                    self.discard(self.segments)
                    self.segments = []
                    self.expired = self.failed = False
            except Exception as exc:
                if not validated:
                    self.segments = []  # keep cache files, exclude the broken interval from future saves
                self.failed = True
                self.results.put(('aborted' if isinstance(exc, ReplayCancelled) else 'error', str(exc), context, False))
