"""Windowed entry point with diagnostics even when Python has no console."""
import os
from pathlib import Path
import sys
import traceback


def launch():
    log_path = Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'.local/share')))/'ClipNest'/'launcher.log'
    try:
        os.chdir(Path(__file__).resolve().parent)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # pythonw can have None for the standard streams. Supply real handles
        # before importing Qt or other modules that may write diagnostics.
        if sys.stdin is None:
            sys.stdin = open(os.devnull, 'r')
        if sys.stdout is None or sys.stderr is None:
            if log_path.exists() and log_path.stat().st_size > 2_000_000:
                try:
                    log_path.replace(log_path.with_suffix('.previous.log'))
                except OSError:
                    pass
            log = log_path.open('a', encoding='utf-8', buffering=1)
            if sys.stdout is None:
                sys.stdout = log
            if sys.stderr is None:
                sys.stderr = log
        from main import main
        return main()
    except Exception as exc:
        details = traceback.format_exc()
        try:
            with log_path.open('a', encoding='utf-8') as log:
                log.write(details+'\n')
        except OSError:
            pass
        message = f'ClipNest could not start:\n\n{exc}\n\nSee launcher.log for details. For an installed copy, rerun the installer; for a source ZIP, run Start_ClipNest.bat.\nDetails: {log_path}'
        if os.name == 'nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, 'ClipNest startup error', 0x10)
        elif sys.stderr is not None:
            sys.stderr.write(message+'\n')
        return 1


if __name__ == '__main__':
    sys.exit(launch())
