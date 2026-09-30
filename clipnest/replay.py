"""Bounded disk replay segments. Native libobs owns capture and keyframe splitting.

All disk work runs off the controller/native threads. Successful saves consume
closed segments; capture keeps writing the next one. Failed saves retain sources.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import os
from pathlib import Path
import queue
import tempfile
import threading
import time
from fractions import Fraction
from .media import run


@dataclass
class Segment:
    path: Path
    duration: float
    start: float = 0.0


def segment_timing(path, ffprobe):
    r = run([ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_packets',
             '-show_entries', 'packet=pts_time,duration_time:stream=avg_frame_rate', '-show_streams', '-of', 'json', str(path)], timeout=20)
    if r.returncode:
        raise ValueError(r.stderr[-1000:] or 'Segment is not ready')
    data = json.loads(r.stdout)
    packets = data.get('packets', [])
    stamps = [float(p['pts_time']) for p in packets if 'pts_time' in p]
    if not stamps:
        raise ValueError('Segment has no video packets')
    rate = float(Fraction(data['streams'][0].get('avg_frame_rate', '30/1')))
    return max(stamps)-min(stamps)+1/rate, min(stamps)


def segment_duration(path, ffprobe):
    return segment_timing(path, ffprobe)[0]


def concat_segments(segments, ffmpeg, destination):
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
        r = run([ffmpeg, '-v', 'error', '-nostdin', '-n', '-copyts', '-f', 'concat', '-safe', '0', '-i', str(listing),
                 '-map', '0', '-c', 'copy', '-avoid_negative_ts', 'disabled', '-t', f'{sum(s.duration for s in segments):.9f}', str(partial)], timeout=180)
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
        self.start()

    def add(self, path, next_path=None, context=None):
        self.commands.put(('segment', path, next_path, context))

    def reset(self):
        self.commands.put(('reset',))

    def close(self):
        self.commands.put(('close',))
        self.join(5)
        if self.is_alive():
            raise RuntimeError('Replay files are still finishing. Wait before closing.')

    def discard(self, segments):
        for seg in segments:
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
                    return
                continue
            _, raw, next_path, context = command
            try:
                path = self.validate_path(raw)
                # file_changed is signalled before the helper consumes the change.
                # Its new-file creation follows closing the old segment.
                if next_path:
                    following = self.validate_path(next_path)
                    deadline = time.monotonic()+10
                    while not following.exists():
                        if time.monotonic() > deadline:
                            raise ValueError('Replay segment close timed out')
                        time.sleep(.05)
                duration, start = segment_timing(path, self.ffprobe)
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
                    saved = concat_segments(self.segments, self.ffmpeg, destination)
                    self.results.put(('saved', saved, context, self.expired or self.failed))
                    self.discard(self.segments)
                    self.segments = []
                    self.expired = self.failed = False
            except Exception as exc:
                self.failed = True
                self.results.put(('error', str(exc), context, False))
