import ctypes
import logging
from .winapi import wintypes
import os
from . import platforms

MODIFIERS = {"ALT": 1, "CTRL": 2, "SHIFT": 4, "WIN": 8}
KEYS = {**{f"F{i}": 0x6F + i for i in range(1, 25)}, "SPACE": 0x20,
        "INSERT": 0x2D, "HOME": 0x24, "END": 0x23, "PAUSE": 0x13,
        "PAGEUP": 0x21, "PGUP": 0x21, "PAGEDOWN": 0x22, "PGDOWN": 0x22, "PGDN": 0x22,
        "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28, "DELETE": 0x2E}


def parse_hotkey(text):
    parts = text.upper().replace(" ", "").split("+")
    mods = 0
    for part in parts[:-1]:
        if part not in MODIFIERS:
            raise ValueError(f"Unknown hotkey modifier: {part}")
        mods |= MODIFIERS[part]
    key = parts[-1]
    vk = KEYS.get(key)
    if vk is None and len(key) == 1 and key.isascii() and key.isalnum():
        vk = ord(key)
    if vk is None:
        raise ValueError("Use a letter, number, F1-F24, Space, Insert, Delete, Home, End, Page Up, Page Down, arrow key, or Pause.")
    return mods, vk


_x11 = None


def x11():
    """ClipNest's X11 shortcut connection, or None without an X server (pure Wayland)."""
    global _x11
    if _x11 is None and platforms.LINUX and os.environ.get("DISPLAY"):
        try:
            from .x11_hotkeys import X11Hotkeys
            _x11 = X11Hotkeys()
        except (OSError, RuntimeError) as exc:
            logging.getLogger("clipnest").warning("X11 shortcuts unavailable: %s", exc)
            _x11 = False
    return _x11 or None


def held(text):
    if platforms.LINUX:
        backend = x11()
        return bool(backend) and backend.held(parse_hotkey(text))
    if os.name != "nt":
        return False
    mods, vk = parse_hotkey(text)
    get = ctypes.windll.user32.GetAsyncKeyState
    if not (get(vk) & 0x8000):
        return False
    for bit, key in [(1, 0x12), (2, 0x11), (4, 0x10)]:
        if mods & bit and not (get(key) & 0x8000):
            return False
    if mods & 8 and not ((get(0x5B) | get(0x5C)) & 0x8000):
        return False
    return True


class Hotkeys:
    """Thread-bound Win32 hotkeys, or X11 key grabs on Linux, polled from the GUI's Qt timer."""
    def __init__(self):
        self.registered = []

    def configure(self, replay, record):
        combinations = [parse_hotkey(replay), parse_hotkey(record)]
        if combinations[0] == combinations[1]:
            raise ValueError("Replay and record shortcuts must be different.")
        self.close()
        if platforms.LINUX:
            backend = x11()
            if backend:
                backend.configure(list(zip(combinations, ("save_replay", "toggle_record"))))
                self.registered.append("x11")
            return
        if os.name != "nt":
            return
        user = ctypes.windll.user32
        for ident, (mods, vk) in zip((101, 102), combinations):
            if not user.RegisterHotKey(None, ident, mods | 0x4000, vk):
                self.close()
                raise ValueError("A shortcut is already in use. Choose another in Settings and apply it.")
            self.registered.append(ident)

    def poll(self):
        if platforms.LINUX:
            return x11().poll() if self.registered else []
        if os.name != "nt":
            return []
        msg = wintypes.MSG()
        result = []
        while ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), None, 0x0312, 0x0312, 1):
            result.append("save_replay" if msg.wParam == 101 else "toggle_record")
        return result

    def close(self):
        if platforms.LINUX and self.registered:
            x11().close()
        elif os.name == "nt":
            for ident in self.registered:
                ctypes.windll.user32.UnregisterHotKey(None, ident)
        self.registered.clear()
