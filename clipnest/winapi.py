"""ctypes.wintypes on Windows; placeholder types elsewhere so modules still import.

Some Linux Pythons raise ValueError importing ctypes.wintypes (VARIANT_BOOL).
Code that calls Win32 checks os.name first, so the placeholders are only used
to build Structure classes that never reach a Windows API.
"""
import ctypes

try:
    from ctypes import wintypes
except (ImportError, ValueError):
    class _Placeholders:
        def __getattr__(self, name):
            return ctypes.c_void_p

    wintypes = _Placeholders()
