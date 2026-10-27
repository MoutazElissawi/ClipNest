"""Installer coordination. Never stop a recorder to permit an update."""
import os

_mutex = None


def hold_install_mutex():
    global _mutex
    if os.name != 'nt' or _mutex:
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    _mutex = kernel.CreateMutexW(None, False, 'Local\\ClipNest.Running')
    if not _mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    # Keep the handle until process termination, including recorder shutdown.
