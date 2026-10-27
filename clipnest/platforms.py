"""Which OS ClipNest runs on, and the Linux stand-ins for its Windows OBS pieces.

Windows ClipNest downloads a pinned OBS runtime. Linux ClipNest uses the
distribution's OBS Studio 30+ (libobs.so.0 and its plugins), loaded by the same
private host process. IDs below are from OBS 32 source:
plugins/linux-capture, linux-pipewire, linux-pulseaudio and obs-ffmpeg.
"""
import ctypes.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

WINDOWS = os.name == "nt"
LINUX = sys.platform.startswith("linux")

# enum obs_nix_platform_type (libobs/obs-nix-platform.h)
OBS_NIX_PLATFORM_X11_EGL, OBS_NIX_PLATFORM_WAYLAND = 1, 2
MIN_OBS_MAJOR = 30

LINUX_ENCODERS = {"NVIDIA H.264": "obs_nvenc_h264_tex", "NVIDIA AV1": "obs_nvenc_av1_tex",
                  "AMD/Intel H.264 (VAAPI)": "ffmpeg_vaapi_tex", "AMD/Intel HEVC (VAAPI)": "hevc_ffmpeg_vaapi_tex",
                  "AMD/Intel AV1 (VAAPI)": "av1_ffmpeg_vaapi_tex", "CPU H.264 (fallback)": "obs_x264"}
# OBS 30 (Ubuntu 24.04, Debian 13) has no obs-nvenc module; NVENC lives in obs-ffmpeg under older ids.
ENCODER_FALLBACKS = {"obs_nvenc_h264_tex": ("jim_nvenc", "ffmpeg_nvenc"),
                     "obs_nvenc_av1_tex": ("jim_av1_nvenc", "ffmpeg_av1_nvenc")}
# Capture targets that work on Linux. Games only, window and game capture need
# Windows hooks; X11 window capture and Wayland window picking are later work.
LINUX_TARGETS = ("display",)
LINUX_AUDIO = {"wasapi_output_capture": "pulse_output_capture", "wasapi_input_capture": "pulse_input_capture"}
LINUX_MODULES = ("linux-capture", "linux-pipewire", "linux-pulseaudio", "obs-ffmpeg", "obs-x264", "obs-nvenc")
# OBS installs libobs.so.0 and obs-plugins/ in one library folder of its prefix, and its data in share/obs.
LIB_SUBDIRS = ("lib/x86_64-linux-gnu", "lib64", "lib")
OBS_PREFIXES = ("/usr", "/usr/local", "/opt/obs-studio")
FLATPAK_OBS = ("/var/lib/flatpak/app/com.obsproject.Studio", "~/.local/share/flatpak/app/com.obsproject.Studio")
SNAP_OBS = "/snap/obs-studio"
INSTALL_HINT = ("Install OBS Studio 30 or newer from your distribution's packages: Debian, Ubuntu or Mint "
                "'sudo apt install obs-studio', Fedora 'sudo dnf install obs-studio', Arch 'sudo pacman -S obs-studio', "
                "openSUSE 'sudo zypper install obs-studio', Void 'sudo xbps-install obs'. Then start ClipNest again.")
CHECK_HINT = "For details, run 'clipnest --check-obs' in a terminal."


def wayland(env=None):
    env = os.environ if env is None else env
    return bool(env.get("WAYLAND_DISPLAY")) or env.get("XDG_SESSION_TYPE") == "wayland"


def source_kind(kind, env=None):
    """The OBS source id that does a Windows source's job on this OS."""
    if not LINUX:
        return kind
    if kind == "monitor_capture":
        return "pipewire-screen-capture-source" if wayland(env) else "xshm_input"
    return LINUX_AUDIO.get(kind, kind)


def audio_kind(kind):
    return kind.startswith(("wasapi_", "pulse_"))


def monitor_property(env=None):
    """Display picker property: xshm lists screens; the Wayland portal picks in its own dialog."""
    if not LINUX:
        return None
    return None if wayland(env) else "screen"


def screen_settings(settings, env=None):
    """Display-capture settings in the Linux source's own keys."""
    if wayland(env):
        return {"ShowCursor": True, "RestoreToken": settings.get("pipewire_restore_token", "")}
    return {"show_cursor": True}


def encoder_id(wanted, available):
    """The encoder this OBS has for a ClipNest choice, or None."""
    for candidate in (wanted, *(ENCODER_FALLBACKS.get(wanted, ()) if LINUX else ())):
        if candidate in available:
            return candidate
    return None


def module_optional(name, env=None):
    """Modules that may be missing or refuse to load without stopping the recorder."""
    if name == "obs-nvenc":
        return True
    return name == ("linux-capture" if wayland(env) else "linux-pipewire")


def ld_cache_libobs():
    """Paths of libobs.so.0 in the dynamic linker cache ('ldconfig -p'; /sbin is often off a user's PATH)."""
    for ldconfig in ("ldconfig", "/sbin/ldconfig", "/usr/sbin/ldconfig"):
        try:
            listing = subprocess.run([ldconfig, "-p"], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        return [line.split("=>", 1)[1].strip() for line in listing.splitlines()
                if line.strip().startswith("libobs.so.0 ") and "=>" in line]
    return []


def prefix_of(path, kind):
    """The install prefix above a 'bin/obs' command or a 'lib*/libobs.so.0' library."""
    parent = Path(path).parent
    if kind == "command":
        return parent.parent if parent.name == "bin" else None
    folder = parent.as_posix()
    for sub in LIB_SUBDIRS:
        if folder.endswith("/" + sub):
            return Path(folder[:-len(sub) - 1] or "/")
    return None


def obs_candidates(env, which=shutil.which, ld_cache=ld_cache_libobs, realpath=os.path.realpath):
    """Prefixes that may hold OBS, best first, each with where the guess came from.

    The 'obs' command finds self-built, /opt and NixOS installs; the linker cache finds
    any registered library folder; the usual prefixes cover distribution packages.
    """
    if env.get("CLIPNEST_OBS_PREFIX"):
        return [(Path(env["CLIPNEST_OBS_PREFIX"]), "CLIPNEST_OBS_PREFIX")]
    guesses = []
    command = which("obs", path=env.get("PATH"))
    if command:
        guesses.append((prefix_of(realpath(command), "command"), f"the obs command, {command}"))
    guesses += [(prefix_of(realpath(path), "library"), f"the library cache, {path}") for path in ld_cache()]
    guesses += [(Path(prefix), "a standard location") for prefix in OBS_PREFIXES]
    found, seen = [], set()
    for prefix, origin in guesses:
        if prefix is not None and prefix not in seen:
            seen.add(prefix)
            found.append((prefix, origin))
    return found


def layout_at(prefix, exists=os.path.exists):
    """OBS's library, plugins and data under one prefix: (layout, '') or (None, why not)."""
    data = prefix / "share/obs"
    for sub in LIB_SUBDIRS:
        lib_dir = prefix / sub
        if not exists(str(lib_dir / "obs-plugins")):
            continue
        if not exists(str(data / "libobs")):
            return None, f"{lib_dir / 'obs-plugins'} exists, but its data folder {data / 'libobs'} is missing."
        library, graphics = lib_dir / "libobs.so.0", lib_dir / "libobs-opengl.so.1"
        # Load the libobs that belongs to these plugins. libobs appends ".so" to a bare graphics
        # module name, and distributions ship only versioned files, so the fallbacks are sonames.
        return {"library": str(library) if exists(str(library)) else ctypes.util.find_library("obs") or "libobs.so.0",
                "graphics": str(graphics) if exists(str(graphics)) else ctypes.util.find_library("obs-opengl") or "libobs-opengl.so.1",
                "plugins": lib_dir / "obs-plugins", "data": data}, ""
    return None, ""


def sandboxed_obs(env, exists=os.path.exists):
    """'Flatpak' or 'Snap' when such an OBS is installed: its libraries stay inside its sandbox."""
    home = env.get("HOME") or os.path.expanduser("~")
    if any(exists(path.replace("~", home, 1)) for path in FLATPAK_OBS):
        return "Flatpak"
    return "Snap" if exists(SNAP_OBS) else ""


def obs_layout(env=None, exists=os.path.exists, which=shutil.which, ld_cache=ld_cache_libobs, realpath=os.path.realpath):
    """Where the system libobs keeps its library, plugins and data. Raises with install help."""
    env = os.environ if env is None else env
    candidates = obs_candidates(env, which, ld_cache, realpath)
    problems = []
    for prefix, _origin in candidates:
        layout, problem = layout_at(prefix, exists)
        if layout:
            return layout
        if problem:
            problems.append(problem)
    sandbox = sandboxed_obs(env, exists)
    if sandbox:
        message = (f"OBS Studio is installed as a {sandbox}, and ClipNest cannot load OBS from inside that sandbox. "
                   "Also install your distribution's OBS Studio package; both can stay installed. ")
    else:
        message = "OBS Studio 30 or newer was not found in " + ", ".join(str(prefix) for prefix, _ in candidates) + ". "
    elsewhere = " If OBS is installed in another folder, start ClipNest with CLIPNEST_OBS_PREFIX set to it."
    raise RuntimeError(message + " ".join(problems) + (" " if problems else "") + INSTALL_HINT + elsewhere + " " + CHECK_HINT)


def version_supported(version):
    try:
        return int(str(version).split(".")[0]) >= MIN_OBS_MAJOR
    except ValueError:
        return False


def choose_qt_audio_backend(env=None):
    """Use Qt's PulseAudio backend when no PipeWire server runs (call before QApplication).

    Qt 6.12's PipeWire device backend crashes in QMediaDevices.audioInputs() when
    libpipewire is installed but its server is not running, as on PulseAudio desktops.
    """
    env = os.environ if env is None else env
    if not LINUX or env.get("QT_AUDIO_BACKEND"):
        return
    runtime = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    remote = env.get("PIPEWIRE_REMOTE", "pipewire-0")
    if not os.path.exists(remote if remote.startswith("/") else os.path.join(runtime, remote)):
        env["QT_AUDIO_BACKEND"] = "pulseaudio"


def open_display(platform):
    """A native display connection for libobs, opened before obs_startup."""
    if platform == OBS_NIX_PLATFORM_WAYLAND:
        lib = ctypes.CDLL(ctypes.util.find_library("wayland-client") or "libwayland-client.so.0")
        lib.wl_display_connect.restype = ctypes.c_void_p
        lib.wl_display_connect.argtypes = [ctypes.c_char_p]
        display = lib.wl_display_connect(None)
    else:
        lib = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
        lib.XOpenDisplay.restype = ctypes.c_void_p
        lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        display = lib.XOpenDisplay(None)
    if not display:
        raise RuntimeError("Could not connect to the desktop session's display. Start ClipNest from your desktop, not a plain terminal or SSH.")
    return display


def x11_compositor_owner():
    """The X11 compositing manager's window (owner of _NET_WM_CM_S<screen>), or 0 when none runs."""
    x11 = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XDefaultScreen.argtypes = [ctypes.c_void_p]
    x11.XInternAtom.restype = ctypes.c_ulong
    x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    x11.XGetSelectionOwner.restype = ctypes.c_ulong
    x11.XGetSelectionOwner.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = x11.XOpenDisplay(None)
    if not display:
        return 0
    try:
        return x11.XGetSelectionOwner(display, x11.XInternAtom(display, b"_NET_WM_CM_S%d" % x11.XDefaultScreen(display), 0))
    finally:
        x11.XCloseDisplay(display)


def compositing(env=None, compositor_owner=x11_compositor_owner):
    """Whether the desktop blends transparent windows with what is behind them."""
    env = os.environ if env is None else env
    if wayland(env):
        return True  # Every Wayland compositor blends alpha, XWayland windows included.
    if not env.get("DISPLAY"):
        return False
    try:
        return bool(compositor_owner())
    except OSError:
        return False


def portal_status():
    """Whether xdg-desktop-portal offers ScreenCast, which Wayland screen capture goes through."""
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtDBus import QDBusConnection, QDBusInterface
    if QCoreApplication.instance() is None:
        portal_status.app = QCoreApplication([])  # QtDBus needs an application object; keep it alive
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return "unknown: no session D-Bus"
    reply = QDBusInterface("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                           "org.freedesktop.DBus.Introspectable", bus).call("Introspect")
    if any("org.freedesktop.portal.ScreenCast" in str(value) for value in reply.arguments()):
        return "available"
    return ("missing. Install xdg-desktop-portal and your desktop's backend, "
            "for example xdg-desktop-portal-kde, -gnome, -wlr or -hyprland")


def obs_report(env=None, portal=portal_status):
    """(ok, text): what `clipnest --check-obs` prints about recording on this PC."""
    env = os.environ if env is None else env
    session = "Wayland" if wayland(env) else "X11" if env.get("DISPLAY") else "none found"
    lines = [f"Desktop session: {session}",
             "Searched: " + "; ".join(f"{prefix} ({origin})" for prefix, origin in obs_candidates(env))]
    try:
        layout = obs_layout(env)
    except RuntimeError as error:
        return False, "\n".join(lines + ["", "Result: " + str(error).replace(" " + CHECK_HINT, "")])
    lines += [f"OBS library: {layout['library']}", f"OBS plugins: {layout['plugins']}", f"OBS data:    {layout['data']}"]
    try:
        library = ctypes.CDLL(layout["library"])
        library.obs_get_version_string.restype = ctypes.c_char_p
        version = (library.obs_get_version_string() or b"").decode("utf-8", "replace")
    except (OSError, AttributeError) as error:
        return False, "\n".join(lines + ["", f"Result: the OBS library could not be loaded: {error}"])
    ok = version_supported(version)
    lines.append(f"OBS version: {version}" + ("" if ok else f" (ClipNest needs {MIN_OBS_MAJOR} or newer)"))
    for name in LINUX_MODULES:
        present = os.path.exists(str(layout["plugins"] / (name + ".so")))
        required = not module_optional(name, env)
        ok = ok and (present or not required)
        lines.append(f"  {name}: " + ("found" if present else "missing (needed)" if required else "not installed (optional)"))
    sandbox = sandboxed_obs(env)
    if sandbox:
        lines.append(f"A {sandbox} OBS is installed too; ClipNest uses the one above.")
    if session == "Wayland":
        status = portal()
        ok = ok and not status.startswith("missing")
        lines.append("Screen sharing portal: " + status)
    lines += ["", "Result: " + ("ClipNest can record with this OBS." if ok else "ClipNest cannot record yet; see above.")]
    return ok, "\n".join(lines)
