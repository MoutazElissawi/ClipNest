from pathlib import Path
import threading
from PySide6.QtCore import QThread, Signal, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar
from .library import storage_usage, GB


class StorageScan(QThread):
    ready = Signal(object)
    def __init__(self, root, parent):
        super().__init__(parent)
        self.root, self.cancel = root, threading.Event()
    def run(self):
        result = storage_usage(self.root, self.cancel)
        if result is not None:
            self.ready.emit(result)


class StorageWidget(QWidget):
    def __init__(self, root, quota=0, parent=None):
        super().__init__(parent)
        self.root, self.quota, self.worker = Path(root), quota, None
        self.stopped = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel('Checking clip storage…')
        self.label.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.setStyleSheet('QProgressBar { background:#303030; border:0; border-radius:3px; } QProgressBar::chunk { background:#76b900; border-radius:3px; }')
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.label)
        layout.addWidget(self.bar)
        layout.addWidget(self.note)
        self.setToolTip('Completed media in the clip folder. Excludes replay cache, staging files and linked folders. GB = 1,000,000,000 bytes. Limit is advisory; clips are never deleted automatically.')
        self.timer = QTimer(self)
        self.timer.setInterval(30000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def refresh(self):
        if self.stopped or self.worker:
            return
        worker = self.worker = StorageScan(self.root, self)
        worker.ready.connect(lambda result: self.loaded(result) if worker.root == self.root else None)
        worker.finished.connect(self.finished)
        worker.start()

    def finished(self):
        worker, self.worker = self.worker, None
        worker.deleteLater()
        if worker.root != self.root:
            self.refresh()

    def loaded(self, result):
        used, free = result['bytes']/GB, result['free']
        limit = f' / {self.quota:g} GB limit' if self.quota else ' GB · no library limit'
        self.label.setText(f'{used:.2f}{limit} · {result["count"]} clips' + (f' · {free/GB:.1f} GB free on drive' if free is not None else ''))
        denominator = self.quota*GB if self.quota else result['capacity']
        self.bar.setValue(min(1000, round(result['bytes']/denominator*1000)) if denominator else 0)
        notes = []
        if free is not None and free < 10*GB:
            notes.append('Low disk space: less than 10 GB free.')
        if self.quota and result['bytes'] >= self.quota*GB:
            notes.append('Library limit reached. Move or delete clips to free space; recording remains enabled.')
        if result['errors']:
            notes.append('Some folders could not be read; usage may be incomplete.')
        self.note.setText(' '.join(notes))
        self.note.setVisible(bool(notes))

    def stop(self):
        self.stopped = True
        self.timer.stop()
        if self.worker:
            self.worker.cancel.set()
            return self.worker.wait(5000)
        return True
