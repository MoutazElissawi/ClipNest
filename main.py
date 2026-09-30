import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox

from clipnest.config import DATA, SETTINGS, load_settings, atomic_json
from clipnest.ui import Window


def main():
    preview = "--preview" in sys.argv
    app = QApplication(sys.argv)
    app.setApplicationName("ClipNest")
    app.setQuitOnLastWindowClosed(False)
    DATA.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(DATA / "clipnest.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s")
    lock = QLockFile(str(DATA / "app.lock"))
    if not preview and not lock.tryLock(100):
        QMessageBox.information(None, "ClipNest", "ClipNest is already running. Check its tray icon.")
        return 0
    if os.name != "nt" and not preview:
        QMessageBox.warning(None, "Windows required", "Recording requires Windows 10/11 x64. Use --preview to inspect the interface here.")
        return 1
    try:
        settings = load_settings()
        if not preview:
            atomic_json(SETTINGS, settings)
        window = Window(settings, preview=preview)
    except Exception as exc:
        logging.exception("Startup failed")
        QMessageBox.critical(None, "Startup error", str(exc))
        return 1
    window.show()
    result = app.exec()
    lock.unlock()
    return result


if __name__ == "__main__":
    sys.exit(main())
