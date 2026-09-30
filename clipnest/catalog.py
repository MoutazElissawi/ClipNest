from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime
import os
from pathlib import Path
import re
import json
import psutil

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
    try:
        process = psutil.Process(pid.value)
        return {"pid": pid.value, "exe": process.exe(), "name": process.name()}
    except (psutil.Error, OSError):
        return None


def normalized_path(path):
    return str(path).replace("\\", "/").rstrip("/").casefold()


class Catalog:
    def __init__(self, custom):
        self.custom = custom
        self.roots = []
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

    def classify(self, path):
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
        if app and app["pid"] != os.getpid() and app["name"].lower() != "obs64.exe":
            self.last = {**app, "category": self.classify(app["exe"])}
        return self.last
