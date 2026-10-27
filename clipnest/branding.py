"""Shared application branding for Qt windows and Windows shortcuts."""
import logging
import os
from pathlib import Path
from PySide6.QtGui import QIcon

APP_ID = 'ClipNest.Desktop'
ASSETS = Path(__file__).resolve().parent / 'assets'


def app_icon():
    return QIcon(str(ASSETS / 'clipnest.ico'))


def set_windows_app_id():
    if os.name != 'nt':
        return
    import ctypes
    from ctypes import wintypes
    try:
        function = ctypes.WinDLL('shell32').SetCurrentProcessExplicitAppUserModelID
        function.argtypes = [wintypes.LPCWSTR]
        function.restype = ctypes.c_long
        result = function(APP_ID)
        if result < 0:
            logging.warning('Windows application identity could not be set: 0x%08x', result & 0xffffffff)
    except OSError:
        logging.exception('Windows application identity could not be set')
