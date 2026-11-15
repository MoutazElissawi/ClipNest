"""Visible first-run download for installed builds, without a console window."""
import contextlib
import traceback
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QMessageBox
import bootstrap


class SetupWorker(QThread):
    message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.error = ''

    def write(self, text):
        if text.strip():
            self.message.emit(text.strip())
        return len(text)

    def flush(self):
        pass

    def run(self):
        try:
            with contextlib.redirect_stdout(self):
                bootstrap.setup()
        except Exception:
            self.error = traceback.format_exc()


class SetupDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('ClipNest — first-time setup')
        self.setMinimumWidth(470)
        layout = QVBoxLayout(self)
        label = QLabel('Preparing the private recorder runtime.\nInternet is needed once; existing OBS installations are unaffected.')
        label.setWordWrap(True)
        layout.addWidget(label)
        self.status = QLabel('Starting…')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        progress = QProgressBar()
        progress.setRange(0, 0)
        layout.addWidget(progress)
        self.worker = SetupWorker(self)
        self.worker.message.connect(self.status.setText)
        self.worker.finished.connect(self.accept)

    def reject(self):
        # Extraction must finish before its worker and this dialog are destroyed.
        if not self.worker.isRunning():
            super().reject()

    def closeEvent(self, event):
        if self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)


def ensure_runtime():
    if bootstrap.is_ready():
        return True
    dialog = SetupDialog()
    dialog.worker.start()
    dialog.exec()
    dialog.worker.wait()
    if dialog.worker.error:
        import logging
        logging.error('First setup failed: %s', dialog.worker.error)
        QMessageBox.critical(None, 'ClipNest setup failed',
            'The recorder runtime could not be prepared. Check your connection and launch ClipNest to retry.\n'
            'Details are in %LOCALAPPDATA%\\ClipNest\\clipnest.log.')
        return False
    return True
