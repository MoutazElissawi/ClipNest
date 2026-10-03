from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime
import os
from pathlib import Path
import re
import json
import psutil
import time

KNOWN_GAMES = {"helldivers2.exe": "Helldivers 2", "rocketleague.exe": "Rocket League",
               "marvel-win64-shipping.exe": "Marvel Rivals", "chivalry2-win64-shipping.exe": "Chivalry 2",
               "geometrydash.exe": "Geometry Dash"}
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_folder(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")[:100]
    if not name:
        return "Desktop"
    if name.split(".")[0].upper() in RESERVED or name.casefold() == "_unsorted":
        name = "Game_" + name
    return name


def archive_file(source, output, category, kind):
    source, output = Path(source), Path(output)
    # Only move files generated in this application's staging directory.
    staging = (output / "_Unsorted").resolve()
    if source.resolve().parent != staging:
        raise ValueError(f"File is outside ClipNest's staging folder; left untouched: {source}")
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError(f"Recording is missing or empty: {source}")
    folder = output / safe_folder(category)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    target = folder / f"{safe_folder(category)}_{stamp}{source.suffix}"
    # Same-volume move, never replace an existing clip.
    while target.exists():
        target = target.with_stem(target.stem + "_copy")
    source.rename(target)
    return target


def foreground():
    if os.name != "nt":
        return None
    user = ctypes.windll.user32
    user.GetForegroundWindow.restype = wintypes.HWND
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    hwnd = user.GetForegroundWindow()
    pid = wintypes.DWORD()
    user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return None
    result = {"pid": pid.value, "exe": "", "name": ""}
    try:
        process = psutil.Process(pid.value)
        # Elevated/protected games may expose their name but deny the full path.
        for key, getter in (("name", process.name), ("exe", process.exe)):
            try:
                result[key] = getter()
            except (psutil.Error, OSError):
                pass
    except (psutil.Error, OSError):
        pass
    if not result['exe']:
        result['exe'] = limited_process_path(pid.value)
    if not result['name'] and result['exe']:
        result['name'] = result['exe'].replace('\\', '/').rsplit('/', 1)[-1]
    return result


def limited_process_path(pid):
    """Windows limited-query fallback, without elevating ClipNest."""
    if os.name != 'nt':
        return ''
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return ''
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        return buffer.value if kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)) else ''
    finally:
        kernel.CloseHandle(handle)


def normalized_path(path):
    return str(path).replace("\\", "/").rstrip("/").casefold()


class Catalog:
    def __init__(self, custom):
        self.custom = custom
        self.roots = []
        self.last_seen = 0.0
        self.last = {"category": "Desktop", "exe": "", "name": "Desktop"}

    def discover(self):
        if os.name != "nt":
            return
        import winreg
        self.roots = []
        roots = set()
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                roots.add(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
        except OSError:
            pass
        for root in list(roots):
            vdf = root / "steamapps/libraryfolders.vdf"
            if vdf.exists():
                for path in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(errors="replace")):
                    roots.add(Path(path.replace("\\\\", "\\")))
        for root in roots:
            for manifest in (root / "steamapps").glob("appmanifest_*.acf"):
                try:
                    fields = dict(re.findall(r'"([^"\n]+)"\s+"([^"\n]+)"', manifest.read_text(errors="replace")))
                    self.roots.append((str(root / "steamapps/common" / fields["installdir"]).casefold(), fields["name"]))
                except (OSError, KeyError):
                    continue
        epic = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "Epic/EpicGamesLauncher/Data/Manifests"
        for manifest in epic.glob("*.item"):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                if data.get("InstallLocation") and data.get("DisplayName"):
                    self.roots.append((str(Path(data["InstallLocation"])).casefold(), data["DisplayName"]))
            except (OSError, ValueError):
                continue

    def classify(self, path, name=""):
        if not path:
            path = name
        path = normalized_path(path)
        basename = path.replace("\\", "/").rsplit("/", 1)[-1]
        custom = {normalized_path(key): value for key, value in self.custom.items()}
        if path in custom:
            return custom[path]
        if basename in KNOWN_GAMES:
            return KNOWN_GAMES[basename]
        for root, name in sorted(self.roots, key=lambda item: len(item[0]), reverse=True):
            if path.startswith(normalized_path(root) + "/"):
                return name
        return "Desktop"

    def poll(self):
        app = foreground()
        now = time.monotonic()
        # Clicking ClipNest must preserve the last observed external app. Known
        # game overlays are transient; Explorer/browser focus is genuine Desktop.
        own = app and app["pid"] == os.getpid()
        overlay = app and app.get("name", "").casefold() in {
            "gameoverlayui.exe", "nvidia overlay.exe", "nvsphelper64.exe", "obs64.exe"}
        if own:
            return dict(self.last)
        if app and (app.get("exe") or app.get("name")) and not overlay:
            self.last = {**app, "category": self.classify(app.get("exe", ""), app.get("name", ""))}
            self.last_seen = now
        elif now - self.last_seen > 3:
            self.last = {"pid": (app or {}).get("pid"), "exe": "", "name": "Desktop", "category": "Desktop"}
        return dict(self.last)
