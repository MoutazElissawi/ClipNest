import ctypes
import os
import threading

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


def held_modifiers(get):
    mods = 0
    for bit, keys in [(1, (0x12,)), (2, (0x11,)), (4, (0x10,)), (8, (0x5B, 0x5C))]:
        if any(get(key) & 0x8000 for key in keys):
            mods |= bit
    return mods


def combo_held(get, mods, vk):
    """vk is down with at least the modifiers in mods (push to talk keeps working while running with Shift)."""
    return bool(get(vk) & 0x8000) and held_modifiers(get) & mods == mods


def extra_modifier_match(combos, vk, held):
    """The command for vk pressed while `held` modifiers are down that Windows will not deliver itself, or None.
    Windows only sends a registered hotkey when exactly its modifiers are held, so PageDown did nothing while
    Shift was held to run. The most specific shortcut wins: with PageDown and Shift+PageDown both set, Shift
    belongs to the second one, which Windows delivers."""
    matches = [(mods, command) for command, mods, key in combos if key == vk and mods & held == mods]
    if not matches:
        return None
    mods, command = max(matches, key=lambda match: bin(match[0]).count("1"))
    return None if mods == held else command


class ExtraModifierWatch(threading.Thread):
    """Watches the shortcut keys and the push-to-talk key only; it never blocks them from games or other apps."""
    def __init__(self, combos, deliver, interval=.01, ptt=None, ptt_changed=None):
        super().__init__(name="ClipNest shortcut watch", daemon=True)
        self.combos, self.deliver, self.interval = combos, deliver, interval
        self.ptt = ptt  # (mods, vk) while the microphone is push to talk; replaced from the GUI thread
        self.ptt_changed = ptt_changed or (lambda pressed: None)
        self.talking = False
        self.stopped = threading.Event()

    def run(self):
        get = ctypes.windll.user32.GetAsyncKeyState
        keys = {vk for _, _, vk in self.combos}
        down = {vk for vk in keys if get(vk) & 0x8000}  # a key already held is not a new press
        while not self.stopped.wait(self.interval):
            for vk in keys:
                pressed = bool(get(vk) & 0x8000)
                if pressed and vk not in down:
                    command = extra_modifier_match(self.combos, vk, held_modifiers(get))
                    if command:
                        self.deliver(command)
                (down.add if pressed else down.discard)(vk)
            ptt = self.ptt
            talking = ptt is not None and combo_held(get, *ptt)
            if talking != self.talking:
                self.talking = talking
                self.ptt_changed(talking)


class Hotkeys:
    """Thread-bound Win32 hotkeys, plus one watch for presses with extra modifiers held and for push to talk."""
    def __init__(self, deliver=None, ptt_changed=None):
        self.registered = []
        self.deliver, self.ptt_changed = deliver, ptt_changed
        self.watch = None
        self.ptt = None

    def configure(self, replay, record, ptt=None):
        combinations = [parse_hotkey(replay), parse_hotkey(record)]
        if combinations[0] == combinations[1]:
            raise ValueError("Replay and record shortcuts must be different.")
        self.close()
        if os.name != "nt":
            return
        user = ctypes.windll.user32
        taken = False
        for ident, (mods, vk) in zip((101, 102), combinations):
            if not user.RegisterHotKey(None, ident, mods | 0x4000, vk):
                taken = True
                break
            self.registered.append(ident)
        if taken:
            self.unregister()
        if self.deliver is not None:
            # Push to talk keeps working even when another app owns a shortcut.
            combos = [] if taken else [(command, mods, vk) for command, (mods, vk) in zip(("save_replay", "toggle_record"), combinations)]
            self.watch = ExtraModifierWatch(combos, self.deliver, ptt_changed=self.ptt_changed)
            self.set_ptt(ptt)
            self.watch.start()
        if taken:
            raise ValueError("A shortcut is already in use. Choose another in Settings and apply it.")

    def set_ptt(self, text):
        """Watch the push-to-talk key, or stop watching it with None."""
        try:
            self.ptt = parse_hotkey(text) if text else None
        except ValueError:
            self.ptt = None
        if self.watch is not None:
            self.watch.ptt = self.ptt

    def unregister(self):
        if os.name == "nt":
            for ident in self.registered:
                ctypes.windll.user32.UnregisterHotKey(None, ident)
        self.registered.clear()

    def close(self):
        if self.watch is not None:
            self.watch.stopped.set()
            self.watch.join(1)
            if self.watch.talking and self.ptt_changed is not None:
                self.ptt_changed(False)  # a stopped watch never reports the release
            self.watch = None
        self.unregister()
