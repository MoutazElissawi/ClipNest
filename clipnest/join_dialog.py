"""Combine selected clips in the background: oldest first, saved next to the first clip and named after the clips."""
from pathlib import Path
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QMessageBox
from .catalog import parse_clip_name
from .editor import Job
from .media import probe, available_encoders
from .gallery import gallery_tools
from .join import copy_compatible, combine, oldest_first


def combined_name(paths):
    """The first clip's name followed by each later clip's number, in the first clip's folder:
    Helldivers 2_11-11-2026_00-50-41_423062 and ..._816355 give Helldivers 2_11-11-2026_00-50-41_423062_816355."""
    first = Path(paths[0])
    parts = [first.stem]
    for path in paths[1:]:
        parsed = parse_clip_name(Path(path).name)
        parts.append(parsed[2] if parsed and parsed[2] else Path(path).stem)
    suffix = first.suffix.lower() if first.suffix.lower() in ('.mkv', '.mp4') else '.mkv'
    target = first.with_name('_'.join(parts) + suffix)
    while target.exists():  # never replace a file
        target = target.with_stem(target.stem + '_copy')
    return target


def combine_work(paths, ffmpeg, ffprobe, encoder, bitrate):
    """A Job action that combines the clips and returns the new clip's path. Streams are copied when the clips
    match; otherwise they are re-encoded with the recorder's encoder when it works, else the first one that does."""
    def run(job):
        ordered = oldest_first(paths)
        infos = [probe(path, ffprobe, job.cancel) for path in ordered]
        if len({len(info['audio']) for info in infos}) > 1:
            raise ValueError('These clips have different numbers of audio tracks, so they cannot be combined.')
        chosen, reencode = encoder, not copy_compatible(infos)
        if reencode:
            available, _ = available_encoders(ffmpeg, job.cancel)
            if not available:
                raise ValueError('No working encoder was found to re-encode these clips.')
            chosen = encoder if encoder in available else available[0]
        target = combined_name(ordered)
        return str(combine(ordered, ffmpeg, ffprobe, target, reencode, chosen, bitrate, job.cancel, job.progress.emit))
    return run


class CombineResult(QObject):
    """Receives the job's result on the main thread: a child of the job, which lives there."""
    def __init__(self, job, host, notify):
        super().__init__(job)
        self.host, self.notify = host, notify
        job.result.connect(self.saved)
        job.failed.connect(self.failed)

    @Slot(object)
    def saved(self, path):
        self.notify(dict(title='Clips combined', detail=Path(path).name, sound=True))
        try:
            self.host.reload_clips()
        except RuntimeError:
            pass  # the clip browser was closed meanwhile

    @Slot(str)
    def failed(self, text):
        self.notify(dict(title='Clips not combined', detail=text, tone='error'))


def start_combine(paths, host):
    """Combine the clips selected in a gallery or the clip browser. The main window owns the work, so it carries on
    after the browser closes and is cancelled if ClipNest quits; the result arrives as a notification."""
    if len(paths) < 2:
        QMessageBox.information(host, 'Combine clips', 'Ctrl-click two or more clips first.')
        return None
    owner = host
    while owner is not None and not hasattr(owner, 'capture_notice'):
        owner = owner.parent()
    window = owner or host
    notify = owner.capture_notice if owner is not None else (lambda notice: None)
    if any(job.isRunning() for job in window.findChildren(Job, 'combine')):
        notify(dict(title='Already combining clips', detail='Wait for the current combine to finish.', tone='error'))
        return None
    ffmpeg, ffprobe = gallery_tools()
    if not ffmpeg:
        notify(dict(title='Clips not combined', detail='Set File → FFmpeg folder in the editor first.', tone='error'))
        return None
    settings = getattr(owner, 'settings', None) or {}
    job = Job(combine_work(paths, ffmpeg, ffprobe, settings.get('encoder', ''), settings.get('bitrate', 20000)), window)
    job.setObjectName('combine')
    CombineResult(job, host, notify)
    job.finished.connect(job.deleteLater)
    notify(dict(title=f'Combining {len(paths)} clips', detail='Oldest first, saved next to the first clip'))
    job.start()
    return job
