"""Recent completed clips and a lightweight player, independent of the recorder."""
from datetime import datetime
import heapq
import json
import math
import os
from pathlib import Path
import tempfile
import threading

from PySide6.QtCore import Qt, QThread, Signal, QSize, QUrl, QTimer
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QDesktopServices, QShortcut, QKeySequence, QImage
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QMediaMetaData, QVideoSink
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QListView, QMainWindow, QSlider)
from .config import DATA
from .editor_assets import thumbnail, captured_file
from .media import tools_path
from .preview import VIDEO_EXTENSIONS, VideoCanvas
from .theme import STYLE


def clock(seconds):
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f'{hours}:{minutes:02}:{seconds:02}' if hours else f'{minutes:02}:{seconds:02}'


def recent_clips(root, cancel, limit=24):
    """Scan every directory but retain only the newest completed files in memory."""
    root = Path(root)
    found, errors = [], []
    for directory, folders, files in os.walk(root, onerror=lambda e: errors.append(str(e)), followlinks=False):
        if cancel.is_set():
            return [], errors
        folders[:] = [f for f in folders if not f.startswith('.') and f not in ('_Unsorted', '_ReplayCache')
                      and not (Path(directory)/f).is_symlink()]
        for name in files:
            if cancel.is_set():
                return [], errors
            path = Path(directory)/name
            if name.startswith('.') or path.suffix.lower() not in VIDEO_EXTENSIONS or path.is_symlink():
                continue
            try:
                stat = path.stat()
                if not stat.st_size:
                    continue
                clip = dict(path=str(path.resolve()), name=name, folder=path.parent.name,
                            size=stat.st_size, modified=stat.st_mtime, stamp=stat.st_mtime_ns)
                entry = (stat.st_mtime_ns, str(path), clip)
                if len(found) < limit:
                    heapq.heappush(found, entry)
                elif entry[:2] > found[0][:2]:
                    heapq.heapreplace(found, entry)
            except OSError:
                continue
    return [c for _, _, c in sorted(found, reverse=True)], errors


def gallery_tools():
    try:
        prefs = json.loads((DATA/'editor.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        prefs = {}
    try:
        return tools_path(prefs.get('ffmpeg_folder', ''))
    except ValueError:
        return None, None


class GalleryScan(QThread):
    listed = Signal(object, object)
    asset = Signal(str, object)
    def __init__(self, root, parent):
        super().__init__(parent)
        self.root = root
        self.cancel = threading.Event()

    def run(self):
        clips, errors = recent_clips(self.root, self.cancel)
        self.listed.emit(clips, errors)
        ffmpeg, ffprobe = gallery_tools()
        if not ffmpeg:
            return
        for clip in clips:
            if self.cancel.is_set():
                return
            try:
                picture = thumbnail(clip['path'], ffmpeg, DATA/'thumbnails', self.cancel)
                cache = Path(picture).with_suffix('.json')
                try:
                    info = json.loads(cache.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    with tempfile.TemporaryFile() as data:
                        captured_file([ffprobe, '-v', 'error', '-show_entries',
                            'format=duration:stream=codec_type,width,height', '-of', 'json', clip['path']],
                            data, self.cancel, 10)
                        data.seek(0)
                        raw = json.loads(data.read())
                    video = next(s for s in raw['streams'] if s.get('codec_type') == 'video')
                    duration = float(raw.get('format', {}).get('duration', 0))
                    info = dict(duration=duration if math.isfinite(duration) else 0,
                                width=video.get('width', 0), height=video.get('height', 0))
                    cache.write_text(json.dumps(info), encoding='utf-8')
                self.asset.emit(clip['path'], dict(info, thumbnail=picture))
            except (OSError, ValueError, KeyError, StopIteration):
                continue


def card_icon(clip):
    canvas = QPixmap(256, 144)
    canvas.fill(QColor('#182638'))
    painter = QPainter(canvas)
    picture = QPixmap(clip.get('thumbnail', ''))
    if not picture.isNull():
        picture = picture.scaled(256, 144, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        painter.drawPixmap((256-picture.width())//2, (144-picture.height())//2, picture)
    else:
        painter.setPen(QColor('#8195ac'))
        painter.drawText(canvas.rect(), Qt.AlignmentFlag.AlignCenter, '▶')
    label = clock(clip['duration']) if clip.get('duration') else 'VIDEO'
    painter.fillRect(8, 8, max(58, len(label)*9+14), 25, QColor(0, 0, 0, 190))
    painter.setPen(Qt.GlobalColor.white)
    painter.drawText(15, 26, label)
    painter.end()
    return QIcon(canvas)


class RecentGallery(QWidget):
    opened = Signal(object, int)
    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root, self.worker = Path(root), None
        self.clips, self.items = [], {}
        self.pending = self.stopped = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        title = QLabel('RECENT CLIPS')
        title.setObjectName('eyebrow')
        row.addWidget(title)
        row.addStretch()
        refresh = QPushButton('Refresh')
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        layout.addLayout(row)
        self.list = QListWidget()
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setIconSize(QSize(256, 144))
        self.list.setGridSize(QSize(282, 216))
        self.list.setSpacing(8)
        self.list.setWordWrap(False)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setUniformItemSizes(True)
        self.list.setStyleSheet('QListWidget {border:0; background:transparent;} QListWidget::item {background:#151e2a; border:1px solid #26364b; border-radius:10px; padding:8px;} QListWidget::item:hover {border:1px solid #69e5cb; background:#1b2b36;} QListWidget::item:selected {border:1px solid #69e5cb; background:#203b3b;}')
        self.list.itemClicked.connect(self.open_item)
        self.list.itemActivated.connect(self.open_item)
        layout.addWidget(self.list, 1)
        self.status = QLabel('Your latest 24 clips appear here, including previous sessions.')
        self.status.setObjectName('muted')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def refresh(self):
        if self.stopped:
            return
        if self.worker is not None:
            self.pending = True
            self.worker.cancel.set()
            return
        self.status.setText('Looking for recent clips…')
        self.worker = GalleryScan(self.root, self)
        self.worker.listed.connect(self.listed)
        self.worker.asset.connect(self.asset_ready)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def finished(self):
        old, self.worker = self.worker, None
        if old:
            old.deleteLater()
        if self.pending and not self.stopped:
            self.pending = False
            self.refresh()

    def listed(self, clips, errors):
        if self.stopped or (self.sender() and getattr(self.sender(), 'cancel', threading.Event()).is_set()):
            return
        self.clips, self.items = clips, {}
        self.list.clear()
        for clip in clips:
            item = QListWidgetItem(card_icon(clip), f"{clip['folder']}\n{datetime.fromtimestamp(clip['modified']):%b %d · %H:%M}\n{clip['name']}")
            item.setData(Qt.ItemDataRole.UserRole, clip['path'])
            item.setToolTip(clip['path'])
            self.list.addItem(item)
            self.items[clip['path']] = item
        text = f'{len(clips)} recent clips · Click to watch' if clips else 'No saved clips yet. Your next saved clip will appear here.'
        if errors:
            text += ' · Some folders could not be read'
        if not gallery_tools()[0]:
            text += ' · Set File → FFmpeg folder in the editor for thumbnails and clip details'
        self.status.setText(text)

    def asset_ready(self, path, details):
        if self.stopped or (self.sender() and getattr(self.sender(), 'cancel', threading.Event()).is_set()):
            return
        for clip in self.clips:
            if clip['path'] == path:
                clip.update(details)
                if path in self.items:
                    self.items[path].setIcon(card_icon(clip))
                break

    def open_item(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        index = next((i for i,c in enumerate(self.clips) if c['path'] == path), -1)
        if index >= 0:
            self.opened.emit(self.clips, index)

    def stop(self):
        self.stopped = True
        if self.worker:
            self.worker.cancel.set()
            self.worker.wait()


class QuickPlayer(QMainWindow):
    edit_requested = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle('ClipNest • Watch clip')
        self.setStyleSheet(STYLE)
        self.resize(1160, 760)
        self.clips, self.index = [], -1
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.75)
        self.player.setAudioOutput(self.audio)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 18, 22, 18)
        row = QHBoxLayout()
        self.title = QLabel('Clip')
        self.title.setObjectName('pageTitle')
        row.addWidget(self.title, 1)
        close = QPushButton('Close')
        close.clicked.connect(self.close)
        row.addWidget(close)
        layout.addLayout(row)
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setObjectName('muted')
        layout.addWidget(self.details)
        stage = QGridLayout()
        self.video = VideoCanvas()
        self.video.setAcceptDrops(False)
        self.video.show_edits = False
        self.video_sink = QVideoSink(self)
        self.video_sink.videoFrameChanged.connect(self.video.frame_changed)
        self.video.setMinimumSize(320, 180)
        self.player.setVideoSink(self.video_sink)
        stage.addWidget(self.video, 0, 0)
        self.center_play = QPushButton('▶')
        self.center_play.setFixedSize(76, 76)
        self.center_play.setStyleSheet('QPushButton {background:#131c27; color:white; border:1px solid #62778c; border-radius:38px; font-size:28px;}')
        self.center_play.clicked.connect(self.toggle)
        stage.addWidget(self.center_play, 0, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(stage, 1)
        row = QHBoxLayout()
        self.previous = QPushButton('‹ Previous')
        self.previous.clicked.connect(lambda: self.open_index(self.index-1))
        row.addWidget(self.previous)
        self.play = QPushButton('Play')
        self.play.clicked.connect(self.toggle)
        row.addWidget(self.play)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderMoved.connect(self.player.setPosition)
        self.seek.sliderPressed.connect(self.begin_seek)
        self.seek.sliderReleased.connect(self.end_seek)
        self.resume_after_seek = False
        row.addWidget(self.seek, 1)
        self.time = QLabel('00:00 / 00:00')
        row.addWidget(self.time)
        self.next = QPushButton('Next ›')
        self.next.clicked.connect(lambda: self.open_index(self.index+1))
        row.addWidget(self.next)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.mute = QPushButton('Mute')
        self.mute.clicked.connect(self.toggle_mute)
        row.addWidget(self.mute)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(75)
        self.volume.setMaximumWidth(180)
        self.volume.valueChanged.connect(lambda v: self.audio.setVolume(v/100))
        row.addWidget(self.volume)
        row.addStretch()
        folder = QPushButton('Open folder')
        folder.clicked.connect(self.open_folder)
        row.addWidget(folder)
        edit = QPushButton('Edit clip')
        edit.setObjectName('primary')
        edit.clicked.connect(self.edit)
        row.addWidget(edit)
        layout.addLayout(row)
        self.message = QLabel('')
        self.message.setWordWrap(True)
        self.message.setObjectName('muted')
        layout.addWidget(self.message)
        self.player.durationChanged.connect(self.duration_changed)
        self.player.metaDataChanged.connect(self.metadata_changed)
        self.player.positionChanged.connect(self.position_changed)
        self.player.playbackStateChanged.connect(self.state_changed)
        self.player.errorOccurred.connect(lambda *_: self.message.setText('Playback failed: '+self.player.errorString()))
        QShortcut(QKeySequence('Space'), self, activated=self.toggle)
        QShortcut(QKeySequence('Escape'), self, activated=self.close)

    def open_clips(self, clips, index):
        self.clips = [dict(c) for c in clips]
        self.open_index(index)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def open_index(self, index):
        if not 0 <= index < len(self.clips):
            return
        self.player.stop()
        self.video.frame_timer.stop()
        self.video.pending_frame = None
        self.video.set_image(QImage())
        self.index = index
        clip = self.clips[index]
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setText(clip['folder'])
        dimensions = f"{clip['width']} × {clip['height']} · " if clip.get('width') else ''
        self.details.setText(f"{clip['name']}\n{dimensions}{clip['size']/1048576:.1f} MB · {index+1} of {len(self.clips)}")
        self.previous.setEnabled(index > 0)
        self.next.setEnabled(index+1 < len(self.clips))
        self.seek.setValue(0)
        self.time.setText('00:00 / '+clock(clip.get('duration', 0)))
        self.message.setText('Space: play/pause · Esc: close · Edit clip opens the full editor')
        if clip.get('thumbnail'):
            self.video.set_image(QImage(clip['thumbnail']))
        self.player.setSource(QUrl.fromLocalFile(clip['path']))
        self.player.pause()
        self.center_play.show()
        if not Path(clip['path']).is_file():
            self.message.setText('This clip has been moved or deleted. Refresh the gallery.')

    def begin_seek(self):
        self.resume_after_seek = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.player.pause()

    def end_seek(self):
        self.player.setPosition(self.seek.value())
        if self.resume_after_seek:
            self.player.play()

    def duration_changed(self, duration):
        self.seek.setRange(0, duration)
        self.position_changed(self.player.position())

    def metadata_changed(self):
        if self.index < 0:
            return
        size = self.player.metaData().value(QMediaMetaData.Key.Resolution)
        if size and hasattr(size, 'width'):
            clip = self.clips[self.index]
            self.details.setText(f"{clip['name']}\n{size.width()} × {size.height()} · {clip['size']/1048576:.1f} MB · {self.index+1} of {len(self.clips)}")

    def toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            if self.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia:
                self.player.setPosition(0)
            self.player.play()

    def state_changed(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play.setText('Pause' if playing else 'Play')
        self.center_play.setVisible(not playing)

    def position_changed(self, position):
        if not self.seek.isSliderDown():
            self.seek.setValue(position)
        self.time.setText(f'{clock(position/1000)} / {clock(self.player.duration()/1000)}')

    def toggle_mute(self):
        self.audio.setMuted(not self.audio.isMuted())
        self.mute.setText('Unmute' if self.audio.isMuted() else 'Mute')

    def open_folder(self):
        if self.index >= 0:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.clips[self.index]['path']).parent)))

    def edit(self):
        if self.index >= 0:
            self.player.pause()
            self.edit_requested.emit(self.clips[self.index]['path'])

    def closeEvent(self, event):
        self.player.stop()
        self.player.setSource(QUrl())
        self.video.frame_timer.stop()
        self.video.pending_frame = None
        self.video.set_image(QImage())
        event.accept()
