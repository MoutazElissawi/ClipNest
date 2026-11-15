"""Start ClipNest when the user signs in to Windows (per-user Run key, no admin rights)."""
import logging
import os
from pathlib import Path
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "ClipNest"
STARTUP_FLAG = "--startup"  # opens in the tray instead of showing the window

log = logging.getLogger(__name__)


def command():
    """The command Windows runs at sign-in, for the installed app or a source checkout."""
    exe = Path(sys.executable)
    if exe.name.casefold() == "clipnest.exe":
        return f'"{exe}" {STARTUP_FLAG}'
    windowed = exe.with_name("pythonw.exe")
    launcher = Path(__file__).resolve().parents[1] / "Launch_ClipNest.pyw"
    return f'"{windowed if windowed.is_file() else exe}" "{launcher}" {STARTUP_FLAG}'


def registered():
    if os.name != "nt":
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return winreg.QueryValueEx(key, VALUE)[0]
    except OSError:
        return None


def sync(enabled):
    """Add or remove the sign-in entry. Re-adding refreshes a path that moved after a reinstall."""
    if os.name != "nt":
        return
    import winreg
    if enabled:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, VALUE, 0, winreg.REG_SZ, command())
    elif registered() is not None:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE)
