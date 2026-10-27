"""Global shortcuts on X11 through XGrabKey on ClipNest's own display connection.

Polled from the GUI's Qt timer, like the Windows hotkeys. On Wayland the grabs
only fire while an XWayland window (most Proton games) has focus; the
`--save-replay` command covers native Wayland windows.
"""
import ctypes
import ctypes.util

KEY_PRESS, GRAB_MODE_ASYNC = 2, 1
SHIFT, LOCK, CONTROL, MOD1, MOD2, MOD4 = 1, 2, 4, 8, 16, 64
# hotkeys.MODIFIERS bits -> X11 modifier masks
MODIFIER_MASKS = {1: MOD1, 2: CONTROL, 4: SHIFT, 8: MOD4}
# Windows virtual-key codes from hotkeys.parse_hotkey -> X11 keysyms (X11/keysymdef.h)
VK_KEYSYMS = {0x20: 0x20, 0x2D: 0xFF63, 0x24: 0xFF50, 0x23: 0xFF57, 0x13: 0xFF13, 0x21: 0xFF55, 0x22: 0xFF56,
              0x25: 0xFF51, 0x26: 0xFF52, 0x27: 0xFF53, 0x28: 0xFF54, 0x2E: 0xFFFF}
# Grab every Caps Lock / Num Lock combination, or the shortcut dies while either is on.
LOCK_VARIANTS = (0, LOCK, MOD2, LOCK | MOD2)


class XKeyEvent(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong), ("send_event", ctypes.c_int),
                ("display", ctypes.c_void_p), ("window", ctypes.c_ulong), ("root", ctypes.c_ulong),
                ("subwindow", ctypes.c_ulong), ("time", ctypes.c_ulong), ("x", ctypes.c_int), ("y", ctypes.c_int),
                ("x_root", ctypes.c_int), ("y_root", ctypes.c_int), ("state", ctypes.c_uint),
                ("keycode", ctypes.c_uint), ("same_screen", ctypes.c_int)]


class XEvent(ctypes.Union):
    _fields_ = [("type", ctypes.c_int), ("xkey", XKeyEvent), ("pad", ctypes.c_long * 24)]


ERROR_HANDLER = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)


def keysym(mods_vk):
    """X11 (modifier mask, keysym) for a parsed Windows (modifiers, virtual key) pair."""
    mods, vk = mods_vk
    mask = 0
    for bit, x_mask in MODIFIER_MASKS.items():
        if mods & bit:
            mask |= x_mask
    if 0x70 <= vk <= 0x87:                       # F1-F24
        sym = 0xFFBE + vk - 0x70
    elif 0x41 <= vk <= 0x5A:                     # letters: X11 uses the lowercase keysym
        sym = vk + 0x20
    elif 0x30 <= vk <= 0x39:
        sym = vk
    else:
        sym = VK_KEYSYMS[vk]
    return mask, sym


class X11Hotkeys:
    def __init__(self):
        name = ctypes.util.find_library("X11") or "libX11.so.6"
        self.x = x = ctypes.CDLL(name)
        x.XOpenDisplay.restype = ctypes.c_void_p
        x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x.XDefaultRootWindow.restype = ctypes.c_ulong
        x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        x.XKeysymToKeycode.restype = ctypes.c_ubyte
        x.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        for fn in (x.XGrabKey, x.XUngrabKey):
            fn.restype = ctypes.c_int
        x.XGrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        x.XUngrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong]
        x.XPending.argtypes = [ctypes.c_void_p]
        x.XPending.restype = ctypes.c_int
        x.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.POINTER(XEvent)]
        x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XQueryKeymap.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ubyte)]
        x.XSetErrorHandler.restype = ctypes.c_void_p
        x.XSetErrorHandler.argtypes = [ctypes.c_void_p]
        self.display = x.XOpenDisplay(None)
        if not self.display:
            raise RuntimeError("No X11 display for global shortcuts.")
        self.root = x.XDefaultRootWindow(self.display)
        self.grabs = {}       # (keycode, mask) -> command
        self.failed = False
        self.on_error = ERROR_HANDLER(self._error)

    def _error(self, _display, _event):
        # BadAccess: another program already grabbed this combination.
        self.failed = True
        return 0

    def configure(self, bindings):
        """bindings: [((mods, vk), command)] from hotkeys.parse_hotkey."""
        self.close()
        previous = self.x.XSetErrorHandler(ctypes.cast(self.on_error, ctypes.c_void_p))
        try:
            for parsed, command in bindings:
                mask, sym = keysym(parsed)
                code = self.x.XKeysymToKeycode(self.display, sym)
                if not code:
                    raise ValueError("This keyboard layout has no key for that shortcut. Choose another in Settings.")
                self.failed = False
                for lock in LOCK_VARIANTS:
                    self.x.XGrabKey(self.display, code, mask | lock, self.root, 0, GRAB_MODE_ASYNC, GRAB_MODE_ASYNC)
                self.x.XSync(self.display, 0)
                self.grabs[(code, mask)] = command
                if self.failed:
                    self.close()
                    raise ValueError("A shortcut is already in use. Choose another in Settings and apply it.")
        finally:
            self.x.XSetErrorHandler(previous)

    def poll(self):
        result = []
        event = XEvent()
        while self.x.XPending(self.display):
            self.x.XNextEvent(self.display, ctypes.byref(event))
            if event.type == KEY_PRESS:
                state = event.xkey.state & ~(LOCK | MOD2)
                command = self.grabs.get((event.xkey.keycode, state))
                if command:
                    result.append(command)
        return result

    def held(self, parsed):
        """Whether a parsed shortcut's key and modifiers are down now (push to talk)."""
        mask, sym = keysym(parsed)
        keys = (ctypes.c_ubyte * 32)()
        self.x.XQueryKeymap(self.display, keys)
        def down(symbol):
            code = self.x.XKeysymToKeycode(self.display, symbol)
            return bool(code) and bool(keys[code // 8] & (1 << (code % 8)))
        if not down(sym):
            return False
        for x_mask, symbols in ((SHIFT, (0xFFE1, 0xFFE2)), (CONTROL, (0xFFE3, 0xFFE4)),
                                (MOD1, (0xFFE9, 0xFFEA)), (MOD4, (0xFFEB, 0xFFEC))):
            if mask & x_mask and not any(down(s) for s in symbols):
                return False
        return True

    def close(self):
        for code, mask in self.grabs:
            for lock in LOCK_VARIANTS:
                self.x.XUngrabKey(self.display, code, mask | lock, self.root)
        if self.grabs:
            self.x.XSync(self.display, 0)
        self.grabs.clear()
