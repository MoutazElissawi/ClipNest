from pathlib import Path
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QPushButton, QComboBox, QCheckBox, QProgressBar, QFileDialog, QMessageBox, QSpinBox)
from .editor import Job
from .media import probe, available_encoders, ExportETA
from .gallery import gallery_tools
from .join import copy_compatible, combine


class JoinDialog(QDialog):
    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Combine clips')
        self.resize(720, 580)
        self.paths, self.infos, self.job = list(paths), [], None
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        self.list.addItems([str(p) for p in paths])
        self.list.setCurrentRow(0)
        layout.addWidget(QLabel('Clips play in this order:'))
        layout.addWidget(self.list)
        row = QHBoxLayout()
        for label, step in [('Move up', -1), ('Move down', 1)]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, step=step: self.move(step))
            row.addWidget(button)
        layout.addLayout(row)
        self.details = QLabel('Inspecting clips…')
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        self.mode = QComboBox()
        self.mode.addItems(['Copy compatible streams (no quality loss)', 'Re-encode · first clip size · 60 FPS · stereo/48 kHz per track'])
        layout.addWidget(self.mode)
        row = QHBoxLayout()
        self.encoder = QComboBox()
        self.bitrate = QSpinBox()
        self.bitrate.setRange(1000, 200000)
        self.bitrate.setValue(20000)
        self.bitrate.setSuffix(' Kbps')
        row.addWidget(self.encoder)
        row.addWidget(self.bitrate)
        layout.addLayout(row)
        self.audio_order = QCheckBox('If titles differ, match audio tracks by position and use titles from the first clip')
        layout.addWidget(self.audio_order)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.eta = ExportETA()
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.save = QPushButton('Choose destination and combine…')
        self.save.setObjectName('primary')
        self.save.setEnabled(False)
        self.save.clicked.connect(self.start_join)
        self.cancel_button = QPushButton('Cancel')
        self.cancel_button.clicked.connect(self.cancel_or_close)
        row.addWidget(self.save)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)
        self.ffmpeg, self.ffprobe = gallery_tools()
        if not self.ffmpeg:
            self.details.setText('Set File → FFmpeg folder in the editor first.')
            return
        self.launch(lambda job: ([probe(p, self.ffprobe, job.cancel) for p in self.paths], available_encoders(self.ffmpeg, job.cancel)), self.inspected)

    def launch(self, action, callback):
        self.job = Job(action, self)
        self.job.result.connect(callback)
        self.job.failed.connect(lambda text: self.status.setText(text))
        self.job.progress.connect(self.progress_changed)
        self.job.finished.connect(self.finished_job)
        self.eta.reset()
        self.job.start()

    def inspected(self, result):
        self.infos, (encoders, _) = result
        self.encoder.addItems(encoders)
        self.describe()

    def describe(self):
        compatible = copy_compatible(self.infos)
        counts = [len(i['audio']) for i in self.infos]
        seconds = sum(i['duration'] for i in self.infos)
        self.details.setText(f'{len(self.infos)} clips · {seconds:.2f} seconds · audio tracks: {counts}\n' +
            ('Stream copy is compatible.' if compatible else 'Re-encoding is required.') +
            (' Track counts differ. Export matching tracks first; combining is blocked.' if len(set(counts)) > 1 else ''))
        self.mode.model().item(0).setEnabled(compatible)
        if not compatible:
            self.mode.setCurrentIndex(1)

    def move(self, step):
        if self.job:
            return
        index = self.list.currentRow()
        target = index+step
        if 0 <= index < len(self.paths) and 0 <= target < len(self.paths):
            self.paths[index], self.paths[target] = self.paths[target], self.paths[index]
            if self.infos:
                self.infos[index], self.infos[target] = self.infos[target], self.infos[index]
            item = self.list.takeItem(index)
            self.list.insertItem(target, item)
            self.list.setCurrentRow(target)
            self.describe()

    def start_join(self):
        if self.job or not self.infos:
            return
        reencode = self.mode.currentIndex() == 1
        if reencode and not self.encoder.currentText():
            self.status.setText('No supported re-encode encoder is available.')
            return
        target, _ = QFileDialog.getSaveFileName(self, 'Save combined clip (new filename)', str(Path(self.paths[0]).parent/'Combined.mkv'), 'MKV (*.mkv);;MP4 (*.mp4)')
        if not target:
            return
        if Path(target).exists():
            self.status.setText('Choose a new filename; existing files are protected.')
            return
        self.save.setEnabled(False)
        self.progress.setValue(0)
        self.status.setText('Combining… Time remaining: estimating…')
        # Snapshot controls on the GUI thread, before worker execution.
        paths, encoder, bitrate, order = list(self.paths), self.encoder.currentText(), self.bitrate.value(), self.audio_order.isChecked()
        self.launch(lambda job: combine(paths, self.ffmpeg, self.ffprobe, target, reencode, encoder, bitrate, job.cancel, job.progress.emit, order),
                    lambda path: self.status.setText('Saved: ' + path))

    def progress_changed(self, percent):
        self.progress.setValue(percent)
        seconds = self.eta.update(percent)
        self.status.setText('Finishing…' if percent >= 99 else 'Combining… Time remaining: estimating…' if seconds is None else f'Combining… About {max(1, round(seconds))} s remaining')

    def finished_job(self):
        job, self.job = self.job, None
        job.deleteLater()
        self.save.setEnabled(bool(self.infos) and len({len(i['audio']) for i in self.infos}) == 1)

    def cancel_or_close(self):
        if self.job:
            self.job.cancel.set()
            self.status.setText('Cancelling… Please wait for the current operation to finish.')
        else:
            self.reject()

    def reject(self):
        if self.job:
            self.cancel_or_close()
            return
        super().reject()

    def closeEvent(self, event):
        if self.job:
            self.cancel_or_close()
            event.ignore()
        else:
            event.accept()
