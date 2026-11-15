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
from collections import deque

from .fullscreen import user32

# A saved clip is named <game>_<day-month-year>_<hours-minutes-seconds>_<number>.
# Clips saved before 2.2.4 put the year first, and are read the same way.
CLIP_STAMP = "%d-%m-%Y_%H-%M-%S_%f"
CLIP_NAME = re.compile(r'(?P<game>.+?)_(?:(?P<year>\d{4})-(?P<month>\d\d)-(?P<day>\d\d)|(?P<day2>\d\d)-(?P<month2>\d\d)-(?P<year2>\d{4}))'
                       r'_(?P<hour>\d\d)-(?P<minute>\d\d)-(?P<second>\d\d)(?:_(?P<number>\d+))?')


def parse_clip_name(name):
    """(game, time saved, number) from a ClipNest clip name, or None for any other name. number may be ''."""
    match = CLIP_NAME.match(Path(name).stem)
    if not match:
        return None
    part = match.groupdict()
    try:
        saved = datetime(int(part['year'] or part['year2']), int(part['month'] or part['month2']), int(part['day'] or part['day2']),
                         int(part['hour']), int(part['minute']), int(part['second']))
    except ValueError:
        return None
    return part['game'], saved, part['number'] or ''


KNOWN_GAMES = {"valorant-win64-shipping.exe": "Valorant", "valorant.exe": "Valorant",
               "osu!.exe": "osu!", "helldivers2.exe": "Helldivers 2", "rocketleague.exe": "Rocket League",
               "marvel-win64-shipping.exe": "Marvel Rivals", "chivalry2-win64-shipping.exe": "Chivalry 2",
               "geometrydash.exe": "Geometry Dash"}
# Exact window titles for protected games that deny both process name and path.
KNOWN_TITLES = {'helldivers 2': 'Helldivers 2', 'valorant': 'Valorant',
                'rocket league': 'Rocket League', 'osu!': 'osu!'}
# Fullscreen windows that are never games: browsers, players, overlays and shell.
NOT_GAMES = {"chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "opera_gx.exe", "brave.exe", "vivaldi.exe",
             "arc.exe", "iexplore.exe", "vlc.exe", "mpc-hc64.exe", "mpc-be64.exe", "potplayermini64.exe", "mpv.exe",
             "wmplayer.exe", "video.ui.exe", "applicationframehost.exe", "discord.exe", "spotify.exe", "obs64.exe",
             "steamwebhelper.exe", "steam.exe", "epicgameslauncher.exe", "gameoverlayui.exe", "nvidia overlay.exe",
             "nvsphelper64.exe", "gamebar.exe", "gamebarftserver.exe", "explorer.exe", "searchhost.exe",
             "startmenuexperiencehost.exe", "shellexperiencehost.exe", "lockapp.exe", "textinputhost.exe",
             "powerpnt.exe", "teams.exe", "ms-teams.exe", "zoom.exe"}
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
    if not folder.exists():
        # Steam titles may add trademark marks; reuse a unique existing spelling
        # instead of creating a second folder for the same game.
        def comparable(value):
            return ' '.join(value.replace('™', '').replace('®', '').split()).casefold()
        aliases = [path for path in output.iterdir() if path.is_dir() and not path.is_symlink()
                   and comparable(path.name) == comparable(folder.name)]
        if len(aliases) == 1:
            folder = aliases[0]
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime(CLIP_STAMP)
    target = folder / f"{safe_folder(category)}_{stamp}{source.suffix}"
    # Same-volume move, never replace an existing clip.
    while target.exists():
        target = target.with_stem(target.stem + "_copy")
    source.rename(target)
    return target


_processes = {}  # (hwnd, pid) -> (name, exe): a window keeps its process, so focus polling skips the lookups


def foreground():
    if os.name != "nt":
        return None
    user = user32()
    hwnd = user.GetForegroundWindow()
    title = ctypes.create_unicode_buffer(min(4096, max(1, user.GetWindowTextLengthW(hwnd)+1)))
    user.GetWindowTextW(hwnd, title, len(title))
    pid = wintypes.DWORD()
    user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value and not title.value:
        return None
    result = {"pid": pid.value or None, "exe": "", "name": "", "title": title.value, "hwnd": int(hwnd or 0)}
    if not pid.value:
        return result
    key = (result["hwnd"], pid.value)
    if key not in _processes:
        if len(_processes) > 64:
            _processes.clear()
        _processes[key] = process_names(pid.value)
    result["name"], result["exe"] = _processes[key]
    return result


def process_names(pid):
    """(name, exe) of a process. Elevated/protected games may expose their name but deny the full path."""
    name = exe = ''
    try:
        process = psutil.Process(pid)
        try:
            name = process.name()
        except (psutil.Error, OSError):
            pass
        try:
            exe = process.exe()
        except (psutil.Error, OSError):
            pass
    except (psutil.Error, OSError):
        pass
    exe = exe or limited_process_path(pid)
    return name or exe.replace('\\', '/').rsplit('/', 1)[-1], exe


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
        self.history = deque(maxlen=20000)

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
                for path in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8-sig", errors="replace")):
                    roots.add(Path(path.replace("\\\\", "\\")))
        for root in roots:
            for manifest in (root / "steamapps").glob("appmanifest_*.acf"):
                try:
                    fields = dict(re.findall(r'"([^"\n]+)"\s+"([^"\n]+)"', manifest.read_text(encoding="utf-8-sig", errors="replace")))
                    title = fields["name"]
                    plain = title.replace('™', '').replace('®', '').strip().casefold()
                    title = next((name for name in KNOWN_GAMES.values() if name.casefold() == plain), title)
                    self.roots.append((str(root / "steamapps/common" / fields["installdir"]).casefold(), title))
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
        if '/' not in path:
            aliases = {value for key, value in custom.items() if key.rsplit('/', 1)[-1] == basename}
            if len(aliases) == 1:
                return next(iter(aliases))
        if basename in KNOWN_GAMES:
            return KNOWN_GAMES[basename]
        for root, name in sorted(self.roots, key=lambda item: len(item[0]), reverse=True):
            if path.startswith(normalized_path(root) + "/"):
                return name
        return "Desktop"

    def window_app(self, value):
        """Name clips for the selected source even when another app has focus."""
        parts = str(value).split(':')
        if len(parts) != 3:
            return dict(category='Window', exe='', name='Window')
        title, _, name = [part.replace('#3A', ':').replace('#22', '#') for part in parts]
        current = self.poll()
        key = str(value)
        if current.get('name', '').casefold() == name.casefold():
            app = current
        else:
            app = dict(getattr(self, '_window_apps', {}).get(key, {}))
        app.setdefault('name', name)
        app.setdefault('exe', '')
        category = self.classify(app.get('exe', ''), name)
        if category == 'Desktop':
            aliases = {v for k, v in self.custom.items() if normalized_path(k).rsplit('/', 1)[-1] == name.casefold()}
            category = next(iter(aliases)) if len(aliases) == 1 else Path(name).stem or title or 'Window'
        app['category'] = category
        self._window_apps = {key: dict(app)}
        return app

    def poll(self):
        app = foreground()
        now = time.monotonic()
        # Clicking ClipNest must preserve the last observed external app. Known
        # game overlays are transient; Explorer/browser focus is genuine Desktop.
        own = app and app["pid"] == os.getpid()
        overlay = app and app.get("name", "").casefold() in {
            "gameoverlayui.exe", "nvidia overlay.exe", "nvsphelper64.exe", "obs64.exe"}
        if own:
            pass
        elif app and (app.get("exe") or app.get("name") or app.get('title')) and not overlay:
            category = self.classify(app.get("exe", ""), app.get("name", ""))
            # Protected processes can deny both path and name. Only accept exact
            # game titles then, never browser/document titles containing game names.
            if category == 'Desktop' and not app.get('name') and not app.get('exe'):
                title = app.get('title', '').casefold().replace('™', '').strip()
                category = KNOWN_TITLES.get(title, 'Desktop')
            self.last = {**app, "category": category}
            self.last_seen = now
        elif now - self.last_seen > 3:
            self.last = {"pid": (app or {}).get("pid"), "exe": "", "name": "Desktop", "category": "Desktop"}
        self.history.append((now, dict(self.last)))
        while len(self.history) > 1 and self.history[1][0] < now - 3600:
            self.history.popleft()
        return dict(self.last)

    def game_category(self, app, window):
        """Game name for the focused window, or None for the desktop and other apps.

        Known, mapped and Steam/Epic games always count. An unknown program counts
        only while it covers its monitor and is not a browser, player or overlay.
        """
        if not app or (window or {}).get('pid') == os.getpid():
            return None
        exe, name = app.get('exe', ''), app.get('name', '')
        category = self.classify(exe, name)
        if category == 'Desktop' and not name and not exe:
            category = KNOWN_TITLES.get(app.get('title', '').casefold().replace('™', '').strip(), 'Desktop')
        if category != 'Desktop':
            return category
        basename = name or exe.replace('\\', '/').rsplit('/', 1)[-1]
        if basename and (window or {}).get('fullscreen') and basename.casefold() not in NOT_GAMES:
            return Path(basename).stem
        return None

    def replay_app(self, seconds):
        """Use foreground time within the requested footage, not just save-time focus."""
        current = self.poll()
        if current['category'] != 'Desktop':
            return current
        now = time.monotonic()
        start = now - max(0, seconds)
        scores, apps = {}, {}
        samples = list(self.history)
        for i, (stamp, app) in enumerate(samples):
            end = samples[i+1][0] if i+1 < len(samples) else now
            # Do not attribute sleep or a stalled polling thread to one application.
            duration = max(0, min(end, stamp + 3, now) - max(stamp, start))
            category = app['category']
            scores[category] = scores.get(category, 0) + duration
            apps[category] = app
        if not scores or max(scores.values()) <= 0:
            return current
        winner = max(scores, key=lambda category: (scores[category], category == current['category']))
        return dict(apps[winner])
