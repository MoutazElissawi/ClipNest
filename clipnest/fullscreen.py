"""Foreground fullscreen detection for the display-capture game layer.

Some games are invisible to desktop composition capture (DXGI duplication and
Windows Graphics Capture). VALORANT recorded by ClipNest 2.0.0-beta.6 showed the
live desktop behind the game. The game layer hooks the game's own swap chain,
but OBS keeps a hook attached after Alt-Tab, so ClipNest draws the layer only
while the hooked game is the focused fullscreen window on the captured monitor.
"""
import ctypes
import os
from ctypes import wintypes

SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
WS_MAXIMIZE, WS_BORDER = 0x01000000, 0x00800000
EDD_GET_DEVICE_INTERFACE_NAME = 1
MONITOR_DEFAULTTONEAREST = 2


def covers_monitor(rect, monitor_rect, style):
    """The rule OBS game capture uses for "any fullscreen application"."""
    if style & WS_MAXIMIZE and style & WS_BORDER:
        return False
    return tuple(rect) == tuple(monitor_rect)


def layer_wanted(window, target_device):
    """Show the game layer only for a fullscreen app on the captured monitor."""
    if not window or not window.get("fullscreen"):
        return False
    if window.get("pid") == os.getpid() or window.get("class") in SHELL_CLASSES:
        return False
    if target_device is None:
        return True
    return window.get("device", "").casefold() == target_device.casefold()


def same_window_app(window, hook):
    """Is the focused window the one OBS hooked? Window class needs no process access."""
    if window.get("class") and hook.get("class"):
        return window["class"] == hook["class"]
    exe = (window.get("exe") or "").replace("\\", "/").rsplit("/", 1)[-1]
    return bool(exe) and exe.casefold() == (hook.get("executable") or "").casefold()


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32),
                ("DeviceString", wintypes.WCHAR * 128), ("StateFlags", wintypes.DWORD),
                ("DeviceID", wintypes.WCHAR * 128), ("DeviceKey", wintypes.WCHAR * 128)]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32)]


_user32 = None


def user32():
    global _user32
    if _user32 is None:
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        u.MonitorFromRect.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD]
        u.MonitorFromRect.restype = wintypes.HMONITOR
        u.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
        u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowDisplayAffinity.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.EnumDisplayDevicesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DISPLAY_DEVICEW), wintypes.DWORD]
        _user32 = u
    return _user32


def monitor_device(monitor_id):
    r"""Map OBS's monitor_id (\\?\DISPLAY#...) to a GDI name (\\.\DISPLAY1)."""
    if os.name != "nt" or not monitor_id:
        return None
    u = user32()
    adapter = DISPLAY_DEVICEW(cb=ctypes.sizeof(DISPLAY_DEVICEW))
    i = 0
    while u.EnumDisplayDevicesW(None, i, ctypes.byref(adapter), 0):
        monitor = DISPLAY_DEVICEW(cb=ctypes.sizeof(DISPLAY_DEVICEW))
        j = 0
        while u.EnumDisplayDevicesW(adapter.DeviceName, j, ctypes.byref(monitor), EDD_GET_DEVICE_INTERFACE_NAME):
            if monitor.DeviceID.casefold() == monitor_id.casefold():
                return adapter.DeviceName
            j += 1
        i += 1
    return None


def even(value):
    return max(2, int(value) // 2 * 2)


def stitched_canvas(rects, height, max_dim=4096):
    """Canvas for monitors recorded side by side at their desktop positions.

    rects are (left, top, right, bottom) in physical pixels. Returns the full-size
    base canvas, the encoded output size (at most `height` tall and max_dim on either
    side; NVIDIA H.264 cannot encode wider than 4096) and each monitor's (x, y, w, h).
    """
    left, top = min(r[0] for r in rects), min(r[1] for r in rects)
    right, bottom = max(r[2] for r in rects), max(r[3] for r in rects)
    base = (even(right - left), even(bottom - top))
    scale = min(1.0, height / base[1], max_dim / base[0], max_dim / base[1])
    output = (even(base[0] * scale), even(base[1] * scale))
    places = [(r[0] - left, r[1] - top, r[2] - r[0], r[3] - r[1]) for r in rects]
    return base, output, places


def monitor_layout():
    """Connected monitors: GDI device name, OBS monitor_id and desktop rectangle."""
    if os.name != "nt":
        return []
    u = user32()
    found = []
    PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def visit(monitor, _dc, _rect, _data):
        info = MONITORINFOEXW(cbSize=ctypes.sizeof(MONITORINFOEXW))
        if u.GetMonitorInfoW(monitor, ctypes.byref(info)):
            device = DISPLAY_DEVICEW(cb=ctypes.sizeof(DISPLAY_DEVICEW))
            ident = device.DeviceID if u.EnumDisplayDevicesW(info.szDevice, 0, ctypes.byref(device), EDD_GET_DEVICE_INTERFACE_NAME) else ""
            m = info.rcMonitor
            found.append({"device": info.szDevice, "id": ident, "rect": (m.left, m.top, m.right, m.bottom)})
        return True

    # Physical pixels regardless of the caller's DPI awareness (OBS captures physical pixels).
    u.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    u.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    previous = u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    try:
        u.EnumDisplayMonitors(None, None, PROC(visit), 0)
    finally:
        if previous:
            u.SetThreadDpiAwarenessContext(ctypes.c_void_p(previous))
    return found


def foreground_window():
    """Foreground window geometry, monitor and capture affinity, or None."""
    if os.name != "nt":
        return None
    u = user32()
    hwnd = u.GetForegroundWindow()
    if not hwnd:
        return None
    rect = wintypes.RECT()
    if not u.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    info = MONITORINFOEXW(cbSize=ctypes.sizeof(MONITORINFOEXW))
    monitor = u.MonitorFromRect(ctypes.byref(rect), MONITOR_DEFAULTTONEAREST)
    if not monitor or not u.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    name = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(hwnd, name, len(name))
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    affinity = wintypes.DWORD()
    if not u.GetWindowDisplayAffinity(hwnd, ctypes.byref(affinity)):
        affinity.value = 0xFFFFFFFF
    style = u.GetWindowLongPtrW(hwnd, -16) & 0xFFFFFFFF
    m = info.rcMonitor
    return {"hwnd": int(hwnd), "pid": pid.value, "class": name.value, "device": info.szDevice,
            "fullscreen": covers_monitor((rect.left, rect.top, rect.right, rect.bottom),
                                         (m.left, m.top, m.right, m.bottom), style),
            "affinity": affinity.value}
