"""Persistent folder browser; scans and thumbnail decoding run off the UI thread."""
from pathlib import Path
import threading
from datetime import datetime
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QComboBox, QListWidget, QListWidgetItem, QFileDialog, QCheckBox, QInputDialog, QMessageBox)
from .editor_assets import scan_clips, thumbnail


from .desktop import SmoothList
from .library import Annotations, matches


class Scan(QThread):
    ready = Signal(object)
    def __init__(self, root, parent):
        super().__init__(parent)
        self.root = root
        self.cancel = threading.Event()
    def run(self):
        result = scan_clips(self.root, self.cancel)
        try:
            Annotations().annotate(result[0])
        except Exception as exc:
            result[2].append(str(exc))
        self.ready.emit(result)


class Thumbnails(QThread):
    ready = Signal(str, str)
    def __init__(self, paths, ffmpeg, cache, parent):
        super().__init__(parent)
        self.paths, self.ffmpeg, self.cache = paths, ffmpeg, cache
        self.cancel = threading.Event()
    def run(self):
        for path in self.paths:
            if self.cancel.is_set():
                return
            try:
                self.ready.emit(path, thumbnail(path, self.ffmpeg, self.cache, self.cancel))
            except (OSError, ValueError):
                continue


class ClipBrowser(QDialog):
    def __init__(self, root, ffmpeg, cache, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Browse clips')
        self.resize(1000, 660)
        self.root, self.ffmpeg, self.cache = Path(root), ffmpeg, cache
        self.selected_path = None
        self.clips, self.workers, self.items = [], [], {}
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.folder = QLabel(str(self.root))
        self.folder.setWordWrap(True)
        row.addWidget(self.folder, 1)
        choose = QPushButton('Folder…')
        choose.clicked.connect(self.choose_folder)
        row.addWidget(choose)
        refresh = QPushButton('Refresh')
        refresh.clicked.connect(self.scan)
        row.addWidget(refresh)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search game, name, YYYY-MM-DD or tag…')
        row.addWidget(self.search, 1)
        self.sort = QComboBox()
        self.sort.addItems(['Newest first', 'Oldest first', 'Name A–Z', 'Largest first'])
        row.addWidget(self.sort)
        layout.addLayout(row)
        controls = QHBoxLayout()
        self.favorites = QCheckBox('Favorites only')
        self.favorites.toggled.connect(self.filter_changed)
        controls.addWidget(self.favorites)
        for label, action in [('Favorite / unfavorite', self.favorite_selected), ('Tags…', self.tag_selected), ('Combine…', self.combine_selected)]:
            button = QPushButton(label)
            button.clicked.connect(action)
            controls.addWidget(button)
        layout.addLayout(controls)
        self.annotations = Annotations()
        self.list = SmoothList()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.setIconSize(QSize(160, 90))
        self.list.setUniformItemSizes(True)
        self.list.itemDoubleClicked.connect(self.open_selected)
        layout.addWidget(self.list, 1)
        self.status = QLabel('Scanning clips…')
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.more = QPushButton('Show more')
        self.more.clicked.connect(self.show_more)
        row.addWidget(self.more)
        row.addStretch()
        open_button = QPushButton('Open selected clip')
        open_button.setObjectName('primary')
        open_button.clicked.connect(self.open_selected)
        row.addWidget(open_button)
        layout.addLayout(row)
        self.shown = 100
        self.search.textChanged.connect(self.filter_changed)
        self.sort.currentIndexChanged.connect(self.filter_changed)
        self.scan()

    def stop_workers(self):
        for worker in self.workers:
            worker.cancel.set()
        for worker in self.workers:
            worker.wait()
            worker.deleteLater()
        self.workers.clear()

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Clips folder', str(self.root))
        if folder:
            self.root = Path(folder)
            self.folder.setText(folder)
            self.scan()

    def scan(self):
        self.stop_workers()
        self.status.setText('Scanning clips…')
        worker = Scan(self.root, self)
        worker.ready.connect(self.scanned)
        self.workers.append(worker)
        worker.start()

    def scanned(self, result):
        if self.sender() is not None and self.sender().cancel.is_set():
            return
        self.clips, self.limited, self.errors = result
        self.filter_changed()

    def filter_changed(self, *_):
        self.shown = 100
        self.populate()

    def show_more(self):
        self.shown += 100
        self.populate()

    def populate(self):
        # Cancellation takes at most one short polling interval in FFmpeg decoding.
        for worker in self.workers:
            if isinstance(worker, Thumbnails):
                worker.cancel.set()
        # Reap completed work instead of retaining a thread for every search edit.
        for worker in self.workers[:]:
            if worker.isFinished():
                self.workers.remove(worker)
                worker.deleteLater()
        query = self.search.text().casefold()
        filtered = [c for c in self.clips if matches(c, query, self.favorites.isChecked())]
        mode = self.sort.currentIndex()
        filtered.sort(key=lambda c: c['name'].casefold() if mode == 2 else c['size'] if mode == 3 else c['modified'], reverse=mode in (0, 3))
        self.list.clear()
        self.items.clear()
        for clip in filtered[:self.shown]:
            item = QListWidgetItem(f"{'★ ' if clip.get('favorite') else ''}{clip['name']}\n{clip['folder']} • {datetime.fromtimestamp(clip['modified']):%Y-%m-%d %H:%M} • {clip['size']/1048576:.1f} MB")
            item.setData(Qt.ItemDataRole.UserRole, clip['path'])
            item.setToolTip(clip['path'] + '\nTags: ' + ', '.join(clip.get('tags', [])))
            item.setSizeHint(QSize(350, 100))
            self.list.addItem(item)
            self.items[clip['path']] = item
        self.more.setEnabled(len(filtered) > self.shown)
        extra = ' • scan limited to 10,000 clips' if getattr(self, 'limited', False) else ''
        if getattr(self, 'errors', []):
            extra += ' • some folders could not be read'
        self.status.setText(f'{min(len(filtered), self.shown)} shown / {len(filtered)} matching clips{extra}')
        if self.ffmpeg:
            worker = Thumbnails(list(self.items), self.ffmpeg, self.cache, self)
            worker.ready.connect(self.thumbnail_ready)
            self.workers.append(worker)
            worker.start()

    def selected_paths(self):
        return [item.data(Qt.ItemDataRole.UserRole) for item in self.list.selectedItems()]

    def favorite_selected(self):
        self.edit_annotations(favorite=True)

    def tag_selected(self):
        self.edit_annotations(favorite=False)

    def edit_annotations(self, favorite):
        paths = self.selected_paths()
        selected = [c for c in self.clips if c['path'] in paths]
        if not selected:
            return
        if favorite:
            values = dict(favorite=not all(c.get('favorite', False) for c in selected))
        else:
            text, ok = QInputDialog.getText(self, 'Tags', 'Comma-separated tags (replaces selected tags):', text=', '.join(selected[0].get('tags', [])))
            if not ok:
                return
            values = dict(tags=[t.strip() for t in text.split(',') if t.strip()])
        try:
            for clip in selected:
                self.annotations.set(clip['path'], **values)
                clip.update(values)
            self.populate()
        except Exception as exc:
            QMessageBox.warning(self, 'Clip annotations', str(exc))

    def combine_selected(self):
        from .join_dialog import JoinDialog
        paths = self.selected_paths()
        if len(paths) < 2:
            QMessageBox.information(self, 'Combine clips', 'Ctrl-click two or more clips first.')
            return
        dialog = JoinDialog(paths, self)
        dialog.exec()
        dialog.deleteLater()
        self.scan()

    def thumbnail_ready(self, path, image):
        if path in self.items:
            self.items[path].setIcon(QIcon(image))

    def open_selected(self, *_):
        item = self.list.currentItem()
        if item:
            self.selected_path = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def done(self, result):
        self.stop_workers()
        super().done(result)
