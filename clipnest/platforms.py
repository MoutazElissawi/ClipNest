"""Which OS ClipNest runs on, and the Linux stand-ins for its Windows OBS pieces.

Windows ClipNest downloads a pinned OBS runtime. Linux ClipNest uses the
distribution's OBS Studio 30+ (libobs.so.0 and its plugins), loaded by the same
private host process. IDs below are from OBS 32 source:
plugins/linux-capture, linux-pipewire, linux-pulseaudio and obs-ffmpeg.
"""
import ctypes.util
import os
from pathlib import Path
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
PLUGIN_DIRS = ("/usr/lib/x86_64-linux-gnu/obs-plugins", "/usr/lib64/obs-plugins", "/usr/lib/obs-plugins",
               "/usr/local/lib/x86_64-linux-gnu/obs-plugins", "/usr/local/lib64/obs-plugins", "/usr/local/lib/obs-plugins")
DATA_DIRS = ("/usr/share/obs", "/usr/local/share/obs")
INSTALL_HINT = ("Install OBS Studio 30 or newer from your distribution (not the Flatpak), for example "
                "'sudo apt install obs-studio' or 'sudo dnf install obs-studio', then start ClipNest again.")


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


def obs_layout(env=None, exists=os.path.isdir):
    """Where the system libobs keeps its plugins and data. Raises with an install hint."""
    env = os.environ if env is None else env
    prefix = env.get("CLIPNEST_OBS_PREFIX")
    plugins = [str(Path(prefix) / sub / "obs-plugins") for sub in ("lib/x86_64-linux-gnu", "lib64", "lib")] if prefix else list(PLUGIN_DIRS)
    data = [str(Path(prefix) / "share/obs")] if prefix else list(DATA_DIRS)
    plugin_dir = next((p for p in plugins if exists(p)), None)
    data_dir = next((d for d in data if exists(str(Path(d) / "libobs"))), None)
    if not plugin_dir or not data_dir:
        raise RuntimeError("OBS Studio was not found. " + INSTALL_HINT)
    library = graphics = None
    if prefix:
        lib_dir = Path(plugin_dir).parent
        library = str(lib_dir / "libobs.so.0") if os.path.isfile(str(lib_dir / "libobs.so.0")) else None
        graphics = str(lib_dir / "libobs-opengl.so.1") if os.path.isfile(str(lib_dir / "libobs-opengl.so.1")) else None
    # libobs appends ".so" to a bare module name, and distributions only ship the versioned
    # file without -dev packages, so pass the soname (OBS itself passes its build-time DL_OPENGL).
    return {"library": library or ctypes.util.find_library("obs") or "libobs.so.0",
            "graphics": graphics or ctypes.util.find_library("obs-opengl") or "libobs-opengl.so.1",
            "plugins": Path(plugin_dir), "data": Path(data_dir)}


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
