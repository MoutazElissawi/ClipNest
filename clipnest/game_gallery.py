"""The Dial theme's Clips page and the game list in its left menu. The menu lists favourite game folders, then the
ten most recently clipped games, each with its game's icon. The clip plays while the rest of that game's clips stay
in view, as a strip under the player or a grid."""
from __future__ import annotations
from datetime import datetime
import json
import os
from pathlib import Path
import re
import threading

from PySide6.QtCore import Qt, QByteArray, QFileInfo, QRectF, QSize, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QIcon, QImage, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QApplication, QFileIconProvider,QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListView,
    QListWidget, QListWidgetItem, QMenu, QPushButton, QSlider, QVBoxLayout, QWidget)

from .config import DATA, atomic_json
from .desktop import ClipActions, DefaultAudioOutput, SeekSlider, SmoothList, reveal_file, same_file, smooth_wheel
from .dial_page import SlideSwitch, theme_color
from .gallery import ClipDeletion, GalleryScan, card_icon, clock
from .library import Annotations, SKIPPED_FOLDERS
from .preview import VideoCanvas

STATE_FILE = 'dial_gallery.json'  # {"favorite_games": [...], "view": "strip" | "grid"}
ICONS_FILE = 'game_icons.json'  # {"game folder": "path of the game's .exe" or "" when none was found}
RECENT_GAMES = 10
EXPORTS = '\0exports'  # the rail entry for exported clips, never a folder name
ALL = '\0all'  # the rail entry for every clip, newest first
PAGE = 60  # clips loaded at a time; scrolling to the end loads the next ones

LINE_ICONS = {  # 24 x 24 strokes, drawn in the theme's colours
    'edit': '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M8.6 7.6 20 18M8.6 16.4 20 6"/>',
    'folder': '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    'trash': '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
    'star': '<path d="M12 2l3 6.6 7.2.8-5.4 4.9 1.5 7.1L12 17.8 5.7 21.4l1.5-7.1L1.8 9.4 9 8.6z"/>',
    'combine': '<path d="M6 4v5a6 6 0 0 0 6 6 6 6 0 0 0 6-6V4"/><path d="M12 15v5"/>',
    'volume': '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12"/>',
    'muted': '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M17 9l5 6M22 9l-5 6"/>',
    'monitor': '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    'exports': '<path d="M12 3v12m0 0-4-4m4 4 4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
    'all': '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
}


def line_icon(name, color, size=18):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" '
           f'stroke-linecap="round" stroke-linejoin="round">{LINE_ICONS[name]}</svg>')
    picture = QPixmap(size * 2, size * 2)
    picture.fill(Qt.GlobalColor.transparent)
    painter = QPainter(picture)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    picture.setDevicePixelRatio(2)
    return QIcon(picture)


def load_state():
    try:
        value = json.loads((DATA/STATE_FILE).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    favorites = [name for name in value.get('favorite_games', []) if isinstance(name, str)]
    return dict(favorite_games=favorites, view='grid' if value.get('view') == 'grid' else 'strip')


def save_state(**changes):
    atomic_json(DATA/STATE_FILE, dict(load_state(), **changes))


def game_folders(root, favorites, export_folder=None, limit=RECENT_GAMES):
    """(favourites, recent): favourite game folders that exist, then the most recently clipped other folders.
    A folder's time changes when ClipNest moves a clip into it, so no clip has to be read."""
    root = Path(root)
    found = {}
    try:
        with os.scandir(root) as listing:
            for entry in listing:
                name = entry.name
                if name.startswith(('_', '.')) or name in SKIPPED_FOLDERS or entry.is_symlink() or not entry.is_dir():
                    continue
                if export_folder is not None and same_file(entry.path, export_folder):
                    continue
                found[name] = entry.stat().st_mtime
    except OSError:
        return [], []
    newest = sorted(found, key=lambda name: found[name], reverse=True)
    favorites = [name for name in newest if name in favorites]
    return favorites, [name for name in newest if name not in favorites][:limit]


def known_icons():
    try:
        value = json.loads((DATA/ICONS_FILE).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in value.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(value, dict) else {}


def remember_icons(found):
    atomic_json(DATA/ICONS_FILE, dict(known_icons(), **found))


def compact(text):
    return re.sub(r'[^a-z0-9]', '', text.casefold())


def game_install_folders():
    """Folders games are installed in: Steam libraries, Epic installs and Riot games."""
    folders = []
    steam = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'))/'Steam'/'steamapps'/'libraryfolders.vdf'
    try:
        for library in re.findall(r'"path"\s+"([^"]+)"', steam.read_text(encoding='utf-8', errors='ignore')):
            common = Path(library.replace('\\\\', '\\'))/'steamapps'/'common'
            folders += [p for p in common.iterdir() if p.is_dir()] if common.is_dir() else []
    except OSError:
        pass
    manifests = Path(os.environ.get('ProgramData', r'C:\ProgramData'))/'Epic'/'EpicGamesLauncher'/'Data'/'Manifests'
    for item in manifests.glob('*.item') if manifests.is_dir() else []:
        try:
            location = json.loads(item.read_text(encoding='utf-8')).get('InstallLocation')
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(location, str) and Path(location).is_dir():
            folders.append(Path(location))
    for drive in 'CDEFGH':
        riot = Path(f'{drive}:\\Riot Games')
        if riot.is_dir():
            folders += [p for p in riot.iterdir() if p.is_dir()]
    return folders


def find_game_exe(name, folders, cancel=None):
    """The .exe of the installed game named like the folder, or '' when none is found."""
    from .catalog import KNOWN_GAMES
    wanted = compact(name)
    if len(wanted) < 3:
        return ''
    known = {exe for exe, game in KNOWN_GAMES.items() if game == name}
    for folder in folders:
        here = compact(folder.name)
        if not (here == wanted or (len(here) >= 4 and (wanted in here or here in wanted))):
            continue
        candidates, seen = [], 0
        for current, directories, files in os.walk(folder):
            depth = len(Path(current).relative_to(folder).parts)
            if depth >= 6:
                directories[:] = []
            for file in files:
                seen += 1
                lower = file.casefold()
                if not lower.endswith('.exe') or any(word in lower for word in ('crash', 'unins', 'setup', 'redist', 'launcher', 'helper')):
                    continue
                stem = compact(Path(file).stem)
                if lower in known or stem == wanted or stem.startswith(wanted[:8]):
                    candidates.append((lower not in known, stem != wanted, 'shipping' not in lower, depth, os.path.join(current, file)))
            if seen > 20000 or (cancel is not None and cancel.is_set()):
                break
        if candidates:
            return min(candidates)[-1]
    return ''


class IconSearch(QThread):
    """Look for the installed games of folders whose icon is not known yet."""
    found = Signal(object)

    def __init__(self, names, parent):
        super().__init__(parent)
        self.names, self.cancel = list(names), threading.Event()

    def run(self):
        folders = game_install_folders()
        result = {}
        for name in self.names:
            if self.cancel.is_set():
                return
            result[name] = find_game_exe(name, folders, self.cancel)
        self.found.emit(result)


def play_icon(color, size=26):
    picture = QPixmap(size * 2, size * 2)
    picture.fill(Qt.GlobalColor.transparent)
    painter = QPainter(picture)
    QSvgRenderer(QByteArray(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M8 5l12 7-12 7z" fill="{color}"/></svg>'.encode())).render(painter)
    painter.end()
    picture.setDevicePixelRatio(2)
    return QIcon(picture)


def monogram(name, size=22):
    picture = QPixmap(size * 2, size * 2)
    picture.fill(Qt.GlobalColor.transparent)
    painter = QPainter(picture)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(theme_color('raised'))
    painter.drawRoundedRect(QRectF(0, 0, size * 2, size * 2), 10, 10)
    font = painter.font()
    font.setPixelSize(size)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(theme_color('accent'))
    painter.drawText(QRectF(0, 0, size * 2, size * 2), Qt.AlignmentFlag.AlignCenter, (name.strip() or '?')[0].upper())
    painter.end()
    picture.setDevicePixelRatio(2)
    return QIcon(picture)


def game_icon(name, icons):
    if name in (EXPORTS, ALL):
        return line_icon('exports' if name == EXPORTS else 'all', theme_color('muted').name())
    if name.casefold() == 'desktop':
        return line_icon('monitor', theme_color('muted').name())
    exe = icons.get(name, '')
    if exe and Path(exe).is_file():
        icon = QFileIconProvider().icon(QFileInfo(exe))
        if not icon.isNull():
            return icon
    return monogram(name)


class GameRow(QPushButton):
    def __init__(self, name, label, icon, favorite):
        super().__init__(label)
        self.name = name
        self.setObjectName('gameRow')
        self.setCheckable(True)
        self.setIcon(icon)
        self.setIconSize(QSize(22, 22))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 10, 0)
        row.addStretch()
        self.star = None
        if favorite:
            self.star = QLabel()
            self.star.setPixmap(line_icon('star', theme_color('accent').name(), 13).pixmap(13, 13))
            self.star.setToolTip('Favourite')
            row.addWidget(self.star)


RAIL_STYLE = """
QPushButton#gameRow { text-align: left; padding: 0 8px; min-height: 36px; max-height: 36px; border: 0; border-radius: 10px;
    background: transparent; color: #aaaaaa; font-size: 11pt; font-weight: 500; }
QPushButton#gameRow:hover { background: #272727; }
QPushButton#gameRow:checked { background: #272727; color: #eeeeee; font-weight: 700; border-left: 3px solid #76b900; }
QWidget#gameRule { background: #3b3b3b; }
"""


class GameRail(QWidget):
    """The game list in the left menu. Right-click a game to add it to or remove it from the favourites."""
    chosen = Signal(str)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self.current = None
        self.rows = []
        self.searched = set()  # folders looked for this session, found or not
        self.search = None
        self.setStyleSheet(RAIL_STYLE)
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(2)

    def games(self):
        from .exports import export_folder
        return game_folders(self.root, load_state()['favorite_games'], export_folder(self.root))

    def refresh(self):
        """Rebuild the list. Returns the games shown, favourites first."""
        favorites, recent = self.games()
        icons = known_icons()
        while self.box.count():
            widget = self.box.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        self.rows = []
        groups = [group for group in ([(name, True) for name in favorites], [(name, False) for name in recent]) if group]
        for n, group in enumerate([[(ALL, False)]] + groups + [[(EXPORTS, False)]]):
            if n:
                rule = QWidget()
                rule.setObjectName('gameRule')
                rule.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                rule.setFixedHeight(1)
                self.box.addWidget(rule)
            for name, favorite in group:
                label = {EXPORTS: 'Exported clips', ALL: 'All clips'}.get(name, name)
                row = GameRow(name, label, game_icon(name, icons), favorite)
                row.setChecked(name == self.current)
                row.clicked.connect(lambda checked=False, name=name: self.choose(name))
                if name not in (EXPORTS, ALL):
                    row.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                    row.customContextMenuRequested.connect(lambda pos, row=row: self.row_menu(row, pos))
                self.box.addWidget(row)
                self.rows.append(row)
        missing = [name for name in favorites + recent if name not in icons and name not in self.searched and name.casefold() != 'desktop']
        if missing and self.search is None:
            self.searched.update(missing)
            self.search = IconSearch(missing, self)
            self.search.found.connect(self.icons_found)
            self.search.finished.connect(self.search_done)
            self.search.start()
        return favorites + recent

    def icons_found(self, found):
        try:
            remember_icons(found)
        except OSError:
            return
        self.refresh()

    def search_done(self):
        old, self.search = self.search, None
        if old is not None:
            old.deleteLater()

    def choose_none(self):
        self.current = None
        for row in self.rows:
            row.setChecked(False)

    def choose(self, name):
        self.current = name
        for row in self.rows:
            row.setChecked(row.name == name)
        self.chosen.emit(name)

    def row_menu(self, row, pos):
        favorite = row.name in load_state()['favorite_games']
        menu = QMenu(self)
        menu.addAction('Remove from favourites' if favorite else 'Add to favourites',
                       lambda: self.set_favorite(row.name, not favorite))
        menu.exec(row.mapToGlobal(pos))

    def set_favorite(self, name, on):
        favorites = [n for n in load_state()['favorite_games'] if n != name] + ([name] if on else [])
        save_state(favorite_games=favorites)
        self.refresh()

    def stop(self):
        if self.search is not None:
            self.search.cancel.set()
            self.search.wait()


class StageVideo(VideoCanvas):
    """The picture: a click plays or pauses, like the play button."""
    clicked = Signal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class ClipStage(QWidget):
    """The clip being watched: picture, a play button over it, and a seek bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.clip = None
        self.player = QMediaPlayer(self)
        self.audio = DefaultAudioOutput(self)
        self.audio.setVolume(.75)
        self.player.setAudioOutput(self.audio)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        self.video = StageVideo()
        self.video.clicked.connect(self.toggle)
        self.video.setAcceptDrops(False)
        self.video.show_edits = False
        self.video.setMinimumSize(320, 180)
        self.sink = QVideoSink(self)
        self.sink.videoFrameChanged.connect(self.video.frame_changed)
        self.player.setVideoSink(self.sink)
        from .playback_lifecycle import PlaybackLifecycle
        from .frame_step import FrameStepper
        self.lifecycle = PlaybackLifecycle(self, self.player, self.video)
        self.stepper = FrameStepper(self.player, self.sink)
        grid.addWidget(self.video, 0, 0)
        self.play_button = QPushButton()
        self.play_button.setObjectName('stagePlay')
        self.play_button.setFixedSize(68, 68)
        self.play_button.setIcon(play_icon(theme_color('accent_text').name()))
        self.play_button.setIconSize(QSize(26, 26))
        self.play_button.clicked.connect(self.toggle)
        grid.addWidget(self.play_button, 0, 0, Qt.AlignmentFlag.AlignCenter)
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 8, 0, 0)
        self.seek = SeekSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderMoved.connect(self.player.setPosition)
        self.seek.sliderPressed.connect(self.begin_seek)
        self.seek.sliderReleased.connect(self.end_seek)
        self.resume = False
        self.time = QLabel('00:00 / 00:00')
        self.time.setObjectName('stageTime')
        self.mute = QPushButton()
        self.mute.setObjectName('stageMute')
        self.mute.setFlat(True)
        self.mute.setToolTip('Mute')
        self.mute.setIconSize(QSize(20, 20))
        self.mute.clicked.connect(lambda: self.audio.setMuted(not self.audio.isMuted()))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setObjectName('stageVolume')
        self.volume.setRange(0, 100)
        self.volume.setValue(75)
        self.volume.setFixedWidth(110)
        self.volume.setToolTip('Volume')
        self.volume.valueChanged.connect(lambda value: (self.audio.setVolume(value / 100), self.audio.setMuted(False)))
        self.audio.mutedChanged.connect(self.show_volume)
        self.audio.volumeChanged.connect(self.show_volume)
        self.show_volume()
        bar.addWidget(self.seek, 1)
        bar.addWidget(self.time)
        bar.addSpacing(12)
        bar.addWidget(self.mute)
        bar.addWidget(self.volume)
        grid.addLayout(bar, 1, 0)
        grid.setRowStretch(0, 1)
        self.player.durationChanged.connect(self.duration_changed)
        self.player.positionChanged.connect(self.position_changed)
        self.player.playbackStateChanged.connect(
            lambda state: self.play_button.setVisible(state != QMediaPlayer.PlaybackState.PlayingState))

    def open(self, clip):
        self.player.stop()
        self.video.clear()
        self.clip = clip
        self.seek.setValue(0)
        self.time.setText('00:00 / ' + clock(clip.get('duration', 0)))
        if clip.get('thumbnail'):
            self.video.set_image(QImage(clip['thumbnail']))
        self.player.setSource(QUrl.fromLocalFile(clip['path']))
        self.player.pause()
        self.play_button.show()

    def toggle(self):
        if self.clip is None:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            if self.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia:
                self.player.setPosition(0)
            self.player.play()

    def begin_seek(self):
        self.resume = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.player.pause()

    def end_seek(self):
        self.player.setPosition(self.seek.value())
        if self.resume:
            self.player.play()

    def show_volume(self, *_):
        silent = self.audio.isMuted() or self.volume.value() == 0
        self.mute.setIcon(line_icon('muted' if silent else 'volume', theme_color('text').name()))

    def duration_changed(self, duration):
        self.seek.setRange(0, duration)
        self.position_changed(self.player.position())

    def position_changed(self, position):
        if not self.seek.isSliderDown():
            self.seek.setValue(position)
        self.time.setText(f'{clock(position / 1000)} / {clock(self.player.duration() / 1000)}')

    def release(self):
        self.player.stop()
        self.player.setSource(QUrl())
        self.video.clear()
        self.clip = None
        self.play_button.show()

    def release_file(self, path):
        if self.clip is not None and same_file(self.clip['path'], path):
            self.release()


class GameList(SmoothList):
    """Clip cards. In a strip the wheel scrolls sideways."""
    def wheelEvent(self, event):
        if not self.isWrapping() and event.modifiers() == Qt.KeyboardModifier.NoModifier and smooth_wheel(self.horizontalScrollBar(), event):
            event.accept()
        else:
            super().wheelEvent(event)


GALLERY_STYLE = """
QLabel#galleryTitle { font-size: 17pt; font-weight: 700; }
QLabel#clipTitle { font-size: 19pt; font-weight: 700; }
QLabel#clipTitleBig { font-size: 28pt; font-weight: 700; }
QLabel#clipGame { color: #76b900; font-weight: 600; }
QLabel#clipFacts, QLabel#stageTime, QLabel#galleryEmpty { color: #aaaaaa; }
QLineEdit#gallerySearch { min-height: 36px; border-radius: 18px; padding: 0 14px; background: #101010; border: 1px solid #3b3b3b; }
QPushButton#clipAction, QPushButton#clipEdit, QPushButton#clipDelete, QPushButton#pickAction, QPushButton#pickCombine {
    min-height: 38px; border-radius: 19px; padding: 0 16px; font-weight: 600; }
QPushButton#clipEdit, QPushButton#pickCombine { background: #76b900; color: #101500; border: 1px solid #76b900; }
QPushButton#clipDelete { color: #ff5c5c; border: 1px solid #6a2e2e; background: transparent; }
QPushButton#clipDelete:hover { background: #3a1d1f; }
QPushButton#clipEdit:disabled, QPushButton#clipDelete:disabled, QPushButton#clipAction:disabled,
QPushButton#pickCombine:disabled, QPushButton#pickAction:disabled { color: #aaaaaa; background: transparent; border-color: #3b3b3b; }
QPushButton#stagePlay { background: #76b900; color: #101500; border: 0; border-radius: 34px; font-size: 22px; }
QPushButton#stageMute { background: transparent; border: 0; padding: 4px; min-height: 0; min-width: 0; }
QWidget#pickBar { background: #101010; border: 1px solid #3b3b3b; border-radius: 28px; }
QListWidget#gameCards { border: 0; background: transparent; }
QListWidget#gameCards::item { background: transparent; border: 2px solid transparent; border-radius: 8px; padding: 4px; color: #aaaaaa; }
QListWidget#gameCards::item:hover { background: #272727; }
QListWidget#gameCards::item:selected { border: 2px solid #76b900; background: #253018; color: #eeeeee; }
"""


def saved_day(clip):
    saved = datetime.fromtimestamp(clip['modified'])
    return ('Today' if saved.date() == datetime.now().date() else f'{saved:%a} {saved.day} {saved:%b}'), f'{saved:%H:%M}'


class GameGallery(ClipDeletion, ClipActions, QWidget):
    """One game's clips (or the exported clips) with the selected clip playing above or beside them.
    Space plays and pauses; Left and Right step one frame."""
    edit_requested = Signal(str)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self.game, self.exported = None, False
        self.clips, self.items = [], {}
        self.pending_deletes = set()
        self.worker, self.pending, self.stopped = None, False, False
        self.limit, self.has_more = PAGE, False
        self.annotations = Annotations()
        self.setStyleSheet(GALLERY_STYLE)
        self.mode = load_state()['view']
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        head = QHBoxLayout()
        head.setSpacing(12)
        self.head_icon = QLabel()
        self.title = QLabel('Clips')
        self.title.setObjectName('galleryTitle')
        self.search = QLineEdit()
        self.search.setObjectName('gallerySearch')
        self.search.setPlaceholderText('Search')
        self.search.setFixedWidth(220)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(350)
        self.search_timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(self.search_timer.start)
        self.views = SlideSwitch(['Strip', 'Grid'])
        self.views.setFixedWidth(180)
        self.views.set_index(1 if self.mode == 'grid' else 0, animate=False)
        self.views.changed.connect(lambda i: self.set_mode('grid' if i else 'strip'))
        head.addWidget(self.head_icon)
        head.addWidget(self.title, 1)
        head.addWidget(self.search)
        head.addWidget(self.views)
        outer.addLayout(head)

        self.stage = ClipStage()
        self.game_label = QLabel()
        self.game_label.setObjectName('clipGame')
        self.clip_title = QLabel()
        self.facts = QLabel()
        self.facts.setObjectName('clipFacts')
        self.edit_button = self.action('Edit clip', 'edit', 'clipEdit', theme_color('accent_text').name(), self.edit_current)
        self.folder_button = self.action('Show in folder', 'folder', 'clipAction', theme_color('text').name(), self.show_current)
        self.delete_button = self.action('Delete', 'trash', 'clipDelete', '#ff5c5c', self.delete_selected)
        self.favorite_button = self.action('Favourite', 'star', 'clipAction', theme_color('text').name(), self.favorite_selected)
        self.actions = QWidget()
        self.actions_box = QHBoxLayout(self.actions)
        self.actions_box.setContentsMargins(0, 0, 0, 0)
        self.actions_box.setSpacing(8)
        for button in (self.edit_button, self.folder_button, self.delete_button, self.favorite_button):
            self.actions_box.addWidget(button)

        self.list = GameList()
        self.list.setObjectName('gameCards')
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setIconSize(QSize(176, 99))
        self.list.setGridSize(QSize(196, 140))
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.setUniformItemSizes(True)
        self.list.setWordWrap(False)
        self.list.itemSelectionChanged.connect(self.selection_changed)
        self.list.itemClicked.connect(self.card_clicked)
        self.opened_by_press = False
        for bar in (self.list.horizontalScrollBar(), self.list.verticalScrollBar()):
            bar.valueChanged.connect(self.load_more)

        self.body = QWidget()
        self.body_grid = QGridLayout(self.body)
        self.body_grid.setContentsMargins(0, 0, 0, 0)
        self.body_grid.setHorizontalSpacing(24)
        self.body_grid.setVerticalSpacing(12)
        self.info = QWidget()
        self.info_box = QVBoxLayout(self.info)
        self.info_box.setContentsMargins(0, 0, 0, 0)
        self.info_box.setSpacing(8)
        self.under = QWidget()
        self.under_box = QHBoxLayout(self.under)
        self.under_box.setContentsMargins(0, 0, 0, 0)
        self.under_box.setSpacing(8)
        outer.addWidget(self.body, 1)
        self.empty = QLabel('No clips here yet.')
        self.empty.setObjectName('galleryEmpty')
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.hide()
        outer.addWidget(self.empty, 1)

        self.picks = QWidget()
        self.picks.setObjectName('pickBar')
        self.picks.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.picks_box = QHBoxLayout(self.picks)
        self.picks_box.setContentsMargins(20, 8, 8, 8)
        self.pick_count = QLabel()
        self.picks_box.addWidget(self.pick_count, 1)
        self.combine_button = self.action('Combine', 'combine', 'pickCombine', theme_color('accent_text').name(), self.combine_selected)
        self.clear_button = QPushButton('Clear')
        self.clear_button.setObjectName('pickAction')
        self.clear_button.clicked.connect(self.clear_picks)
        self.picks.hide()
        outer.addWidget(self.picks)

        for key, action in (('Space', self.stage.toggle), ('Left', lambda: self.stage.stepper.step(-1)),
                            ('Right', lambda: self.stage.stepper.step(1))):
            shortcut = QShortcut(QKeySequence(key), self, activated=action)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.set_mode(self.mode, save=False)
        self.show_clip(None)

    def action(self, text, icon, name, color, callback):
        button = QPushButton(text)
        button.setObjectName(name)
        button.setIcon(line_icon(icon, color))
        button.setIconSize(QSize(18, 18))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(callback)
        return button

    def set_mode(self, mode, save=True):
        """Strip: the player across the top, the clip's title and actions under it, the cards in one row.
        Grid: the player with the clip's details beside it, the cards in rows underneath."""
        self.mode = mode
        grid = mode == 'grid'
        for widget in (self.stage, self.info, self.under, self.list):
            self.body_grid.removeWidget(widget)
        for box in (self.info_box, self.under_box):
            while box.count():
                box.takeAt(0)
        for row in range(3):
            self.body_grid.setRowStretch(row, 0)
        self.clip_title.setObjectName('clipTitleBig' if grid else 'clipTitle')
        self.clip_title.style().unpolish(self.clip_title)
        self.clip_title.style().polish(self.clip_title)
        self.actions_box.setDirection(QVBoxLayout.Direction.TopToBottom if grid else QHBoxLayout.Direction.LeftToRight)
        for button in (self.combine_button, self.clear_button):
            (self.actions_box if grid else self.picks_box).addWidget(button)
        self.list.setFlow(QListView.Flow.LeftToRight)
        if grid:
            for widget in (self.game_label, self.clip_title, self.facts, self.actions):
                self.info_box.addWidget(widget)
            self.info_box.addStretch()
            self.info.setFixedWidth(300)
            self.body_grid.addWidget(self.stage, 0, 0)
            self.body_grid.addWidget(self.info, 0, 1)
            self.body_grid.addWidget(self.list, 1, 0, 1, 2)
            self.body_grid.setRowStretch(0, 3)
            self.body_grid.setRowStretch(1, 2)
            self.list.setWrapping(True)
            self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.list.setMinimumHeight(150)
            self.list.setMaximumHeight(16777215)
        else:
            self.under_box.addWidget(self.clip_title, 1)
            self.under_box.addWidget(self.actions)
            self.body_grid.addWidget(self.stage, 0, 0, 1, 2)
            self.body_grid.addWidget(self.under, 1, 0, 1, 2)
            self.body_grid.addWidget(self.list, 2, 0, 1, 2)
            self.body_grid.setRowStretch(0, 1)
            self.list.setWrapping(False)
            self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.list.setFixedHeight(self.list.gridSize().height() + 16)
        self.info.setVisible(grid)
        self.under.setVisible(not grid)
        self.game_label.setVisible(grid)
        self.facts.setVisible(grid)
        self.selection_changed()
        if self.stage.clip is not None:
            self.show_clip(self.stage.clip, reopen=False)
        self.list.doItemsLayout()
        if save:
            try:
                save_state(view=mode)
            except OSError:
                pass

    def show_game(self, name):
        """Show one game folder's clips, every clip for ALL, or the exported clips for EXPORTS."""
        self.exported = name == EXPORTS
        self.game = None if self.exported else name
        self.limit = PAGE
        self.title.setText({EXPORTS: 'Exported clips', ALL: 'All clips'}.get(name, name))
        self.head_icon.setPixmap(game_icon(name, known_icons()).pixmap(28, 28))
        self.stage.release()
        self.clips = []
        self.list.clearSelection()
        self.render_clips()
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.stage.player.pause()
        self.pending = False
        if self.worker is not None:
            self.worker.cancel.set()

    def refresh(self, *, automatic=False):
        if self.stopped or (automatic and not self.isVisible()) or (self.game is None and not self.exported):
            return
        if self.worker is not None:
            self.pending = True
            self.worker.cancel.set()
            return
        game = '' if self.game == ALL else self.game or ''
        self.worker = GalleryScan(self.root, self, self.exported, self.limit, game, self.search.text(), False)
        self.worker.listed.connect(self.listed)
        self.worker.asset.connect(self.asset_ready)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def finished(self):
        old, self.worker = self.worker, None
        if old is not None:
            old.deleteLater()
        if self.pending and not self.stopped:
            self.pending = False
            self.refresh()

    def scan_worker(self):
        sender = self.sender()
        return sender if isinstance(sender, GalleryScan) else None

    def listed(self, clips, errors):
        worker = self.scan_worker()
        if self.stopped or (worker is not None and worker.cancel.is_set()):
            return
        self.clips = clips
        if worker is not None:
            self.has_more = worker.has_more
        self.render_clips()

    def load_more(self, *_):
        """Scrolled to the end of the cards: load the next clips, like the old gallery's View more."""
        bar = self.list.verticalScrollBar() if self.list.isWrapping() else self.list.horizontalScrollBar()
        if self.has_more and self.worker is None and bar.maximum() and bar.value() >= bar.maximum() - 40:
            self.limit += PAGE
            self.has_more = False
            self.refresh()

    def render_clips(self):
        current = self.stage.clip['path'] if self.stage.clip else None
        selected = set(self.selected_paths())
        self.list.blockSignals(True)
        self.list.clear()
        self.items = {}
        mixed = self.game == ALL or self.exported  # cards from several games also name their game
        self.list.setGridSize(QSize(196, 160 if mixed else 140))  # room for that second line
        if not self.list.isWrapping():
            self.list.setFixedHeight(self.list.gridSize().height() + 16)
        for clip in self.clips:
            item = QListWidgetItem(card_icon(clip), (clip['folder'] + '\n' if mixed else '') + ', '.join(saved_day(clip)))
            item.setData(Qt.ItemDataRole.UserRole, clip['path'])
            item.setToolTip(clip['name'])
            self.list.addItem(item)
            self.items[clip['path']] = item
            item.setSelected(clip['path'] in selected)
        if self.clips and not self.list.selectedItems():
            first = self.items[current] if current in self.items else self.list.item(0)
            first.setSelected(True)
            self.list.setCurrentItem(first)
        self.list.blockSignals(False)
        self.selection_changed()
        has_clips = bool(self.clips)
        self.body.setVisible(has_clips)
        self.empty.setVisible(not has_clips)
        if not has_clips:
            self.stage.release()
            self.show_clip(None)
            self.empty.setText('No clips match this search.' if self.search.text().strip() else 'No clips here yet.')

    def asset_ready(self, path, details):
        worker = self.scan_worker()
        if self.stopped or (worker is not None and worker.cancel.is_set()):
            return
        for clip in self.clips:
            if clip['path'] == path:
                clip.update(details)
                if path in self.items:
                    self.items[path].setIcon(card_icon(clip))
                if self.stage.clip is not None and same_file(self.stage.clip['path'], path):
                    self.stage.clip.update(details)
                    self.show_clip(clip, reopen=False)
                break

    def selection_changed(self):
        paths = self.selected_paths()
        self.picks.setVisible(len(paths) > 1 and self.mode == 'strip')
        self.pick_count.setText(f'{len(paths)} clips selected')
        self.combine_button.setText(f'Combine {len(paths)} clips' if len(paths) > 1 else 'Combine')
        self.combine_button.setEnabled(len(paths) > 1)
        self.clear_button.setEnabled(len(paths) > 1)
        chosen = self.selected_clips()
        self.favorite_button.setEnabled(bool(chosen))
        self.favorite_button.setText('Unfavourite' if chosen and all(c.get('favorite') for c in chosen) else 'Favourite')
        if len(paths) == 1:
            clip = next((c for c in self.clips if c['path'] == paths[0]), None)
            if clip is not None and (self.stage.clip is None or not same_file(self.stage.clip['path'], clip['path'])):
                self.show_clip(clip)
                # the click that chose this card only loads it
                self.opened_by_press = bool(QApplication.mouseButtons() & Qt.MouseButton.LeftButton)
        for button in (self.edit_button, self.folder_button, self.delete_button):
            button.setEnabled(len(paths) == 1)

    def card_clicked(self, item):
        """Clicking the card that is showing plays or pauses it; Ctrl/Shift-clicks only select."""
        opened, self.opened_by_press = self.opened_by_press, False
        if not opened and QApplication.keyboardModifiers() == Qt.KeyboardModifier.NoModifier and len(self.selected_paths()) == 1:
            self.stage.toggle()

    def clear_picks(self):
        """Keep only the clip that is playing selected. A redraw (after Favourite) leaves no current card."""
        playing = self.items.get(self.stage.clip['path']) if self.stage.clip else None
        current = playing or self.list.currentItem()
        self.list.clearSelection()
        if current is not None:
            current.setSelected(True)

    def show_clip(self, clip, reopen=True):
        if clip is None:
            for label in (self.clip_title, self.facts, self.game_label):
                label.setText('')
            return
        if reopen:
            self.stage.open(dict(clip))
        day, time = saved_day(clip)
        self.clip_title.setText(f'{day}\n{time}' if self.mode == 'grid' else f'{day}  {time}')
        self.game_label.setText(clip['folder'])
        dimensions = f" · {clip['width']} × {clip['height']}" if clip.get('width') else ''
        length = f"{clock(clip['duration'])} · " if clip.get('duration') else ''
        self.facts.setText(f"{length}{clip['size'] / 1048576:.0f} MB{dimensions}")

    def current_path(self):
        paths = self.selected_paths()
        return paths[0] if len(paths) == 1 else None

    def edit_current(self):
        path = self.current_path()
        if path:
            self.stage.player.pause()
            self.edit_requested.emit(path)

    def show_current(self):
        path = self.current_path()
        if path:
            try:
                reveal_file(path)
            except OSError as exc:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, 'Show in folder', str(exc))

    def release_file(self, path):
        """Let go of a clip being deleted, by this gallery or the classic one."""
        self.stage.release_file(path)

    def show_clips(self):
        self.render_clips()

    def reload_clips(self):
        self.refresh()

    def stop(self):
        self.stopped = True
        self.stage.release()
        if self.worker is not None:
            self.worker.cancel.set()
            self.worker.wait()
