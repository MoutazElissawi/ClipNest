import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox

from clipnest.config import DATA, SETTINGS, load_settings, atomic_json
from clipnest.ui import Window
from clipnest.branding import app_icon, set_windows_app_id
from clipnest import __version__


def main():
    preview = "--preview" in sys.argv
    if not preview:
        from clipnest.install_support import hold_install_mutex
        hold_install_mutex()
    set_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName("ClipNest")
    app.setWindowIcon(app_icon())
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
        if not preview and (Path(__file__).parent / "runtime/pythonw.exe").is_file():
            from clipnest.first_setup import ensure_runtime
            if not ensure_runtime():
                return 1
        settings = load_settings()
        if not preview:
            atomic_json(SETTINGS, settings)
        if '--safe-ui' in sys.argv:
            settings['ui_theme'] = 'dark'
        logging.info('ClipNest %s; source=%s; executable=%s; theme=%s; tint=%s; safe_ui=%s',
                     __version__, Path(__file__).resolve(), sys.executable, settings['ui_theme'],
                     settings['glass_tint'], '--safe-ui' in sys.argv)
        window = Window(settings, preview=preview)
    except Exception as exc:
        logging.exception("Startup failed")
        QMessageBox.critical(None, "Startup error", str(exc))
        return 1
    from clipnest.desktop import show_centered
    show_centered(window)
    result = app.exec()
    lock.unlock()
    return result


if __name__ == "__main__":
    sys.exit(main())
