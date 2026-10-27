"""Explicit C ABI bindings for OBS Studio 32.2.2, Windows x64."""
import ctypes as C
import json
import os
from pathlib import Path
from contextlib import contextmanager

P, S, U, I, B, Z, F = C.c_void_p, C.c_char_p, C.c_uint32, C.c_int, C.c_bool, C.c_size_t, C.c_float

class VideoInfo(C.Structure):
    _fields_ = [("graphics_module", S), ("fps_num", U), ("fps_den", U),
                ("base_width", U), ("base_height", U), ("output_width", U),
                ("output_height", U), ("output_format", I), ("adapter", U),
                ("gpu_conversion", B), ("colorspace", I), ("range", I), ("scale_type", I)]

class AudioInfo(C.Structure):
    _fields_ = [("samples_per_sec", U), ("speakers", I)]

class Vec2(C.Structure):
    _fields_ = [("x", F), ("y", F)]

class CallData(C.Structure):
    _fields_ = [("stack", P), ("size", Z), ("capacity", Z), ("fixed", B)]

SIGNAL = C.CFUNCTYPE(None, P, P)
METER = C.CFUNCTYPE(None, P, C.POINTER(F), C.POINTER(F), C.POINTER(F))
from .native_tasks import UI_HANDLER

SIGNATURES = {
    "obs_set_ui_task_handler": (None, UI_HANDLER),
    "obs_wait_for_destroy_queue": (B,), "obs_get_version_string": (S,), "obs_startup": (B, S, S, P), "obs_shutdown": (None,),
    "obs_add_data_path": (None, S), "obs_reset_video": (I, C.POINTER(VideoInfo)),
    "obs_reset_audio": (B, C.POINTER(AudioInfo)),
    "obs_open_module": (I, C.POINTER(P), S, S), "obs_init_module": (B, P),
    "obs_post_load_modules": (None,), "obs_get_video": (P,), "obs_get_audio": (P,),
    "obs_enum_input_types": (B, Z, C.POINTER(S)), "obs_enum_encoder_types": (B, Z, C.POINTER(S)),
    "obs_data_create_from_json": (P, S), "obs_data_release": (None, P),
    "obs_scene_create": (P, S), "obs_scene_release": (None, P), "obs_scene_get_source": (P, P),
    "obs_scene_add": (P, P, P), "obs_set_output_source": (None, U, P),
    "obs_sceneitem_remove": (None, P), "obs_source_set_name": (None, P, S),
    "obs_source_create": (P, S, S, P, P), "obs_source_release": (None, P),
    "obs_source_update": (None, P, P), "obs_source_set_muted": (None, P, B),
    "obs_source_get_width": (U, P), "obs_source_get_height": (U, P),
    "obs_source_set_volume": (None, P, F), "obs_source_set_audio_mixers": (None, P, U),
    "obs_source_set_monitoring_type": (None, P, I),
    "obs_get_source_properties": (P, S),
    "obs_source_properties": (P, P), "obs_properties_destroy": (None, P),
    "obs_properties_get": (P, P, S), "obs_property_list_format": (I, P),
    "obs_property_list_item_count": (Z, P), "obs_property_list_item_name": (S, P, Z),
    "obs_property_list_item_string": (S, P, Z), "obs_property_list_item_int": (C.c_longlong, P, Z),
    "obs_property_list_item_disabled": (B, P, Z),
    "obs_sceneitem_set_pos": (None, P, C.POINTER(Vec2)), "obs_sceneitem_set_alignment": (None, P, U),
    "obs_sceneitem_set_bounds_type": (None, P, I), "obs_sceneitem_set_bounds_alignment": (None, P, U),
    "obs_sceneitem_set_bounds": (None, P, C.POINTER(Vec2)), "obs_sceneitem_set_visible": (None, P, B), "obs_sceneitem_set_order": (None, P, I),
    "obs_source_set_enabled": (None, P, B), "obs_source_get_proc_handler": (P, P),
    "obs_video_encoder_create": (P, S, S, P, P), "obs_audio_encoder_create": (P, S, S, P, Z, P),
    "obs_encoder_release": (None, P), "obs_encoder_set_video": (None, P, P),
    "obs_encoder_set_audio": (None, P, P),
    "obs_output_create": (P, S, S, P, P), "obs_output_release": (None, P),
    "obs_output_update": (None, P, P), "obs_output_start": (B, P), "obs_output_stop": (None, P), "obs_output_force_stop": (None, P),
    "obs_output_active": (B, P), "obs_output_get_last_error": (S, P),
    "obs_output_get_total_frames": (I, P), "obs_output_get_frames_dropped": (I, P),
    "obs_get_active_fps": (C.c_double,), "obs_get_average_frame_time_ns": (C.c_uint64,),
    "obs_get_total_frames": (U,), "obs_get_lagged_frames": (U,),
    "obs_output_set_video_encoder": (None, P, P), "obs_output_set_audio_encoder": (None, P, P, Z),
    "obs_output_get_signal_handler": (P, P), "obs_output_get_proc_handler": (P, P),
    "signal_handler_connect": (None, P, S, SIGNAL, P),
    "signal_handler_disconnect": (None, P, S, SIGNAL, P),
    "proc_handler_call": (B, P, S, C.POINTER(CallData)),
    "calldata_get_string": (B, P, S, C.POINTER(S)),
    "calldata_get_data": (B, P, S, P, Z), "bfree": (None, P),
    "obs_volmeter_create": (P, I), "obs_volmeter_destroy": (None, P),
    "obs_volmeter_attach_source": (B, P, P),
    "obs_volmeter_add_callback": (None, P, METER, P),
    "obs_volmeter_remove_callback": (None, P, METER, P),
}
# libobs/obs-nix-platform.h, plus reading the PipeWire portal's restore token back.
LINUX_SIGNATURES = {
    "obs_set_nix_platform": (None, I), "obs_set_nix_platform_display": (None, P),
    "obs_source_save": (None, P), "obs_source_get_settings": (P, P), "obs_data_get_json": (S, P),
}

def utf8(value): return str(value).encode("utf-8")
def obs_path(value): return str(value).replace("\\", "/").encode("utf-8")
def decode(value): return value.decode("utf-8", errors="replace") if value else ""

class LibObs:
    def __init__(self, root):
        from . import platforms
        if C.sizeof(P) != 8 or not (platforms.WINDOWS or platforms.LINUX):
            raise RuntimeError("The native engine requires 64-bit Python on Windows or Linux.")
        if platforms.LINUX:
            # root is platforms.obs_layout(): the distribution's OBS Studio.
            self.dll = C.CDLL(root["library"])
            signatures = {**SIGNATURES, **LINUX_SIGNATURES}
        else:
            root = Path(root).resolve()
            bins = [root / "bin/64bit", root / "obs-plugins/64bit"]
            self.dll_dirs = [os.add_dll_directory(str(p)) for p in bins]
            os.environ["PATH"] = os.pathsep.join(map(str, bins)) + os.pathsep + os.environ.get("PATH", "")
            os.chdir(bins[0])
            self.dll = C.CDLL(str(bins[0] / "obs.dll"))
            signatures = SIGNATURES
        for name, spec in signatures.items():
            try: fn = getattr(self.dll, name)
            except AttributeError as exc: raise RuntimeError(f"Missing libobs export: {name}") from exc
            fn.restype, fn.argtypes = spec[0], list(spec[1:])
            setattr(self, name, fn)
        version = decode(self.obs_get_version_string())
        if platforms.LINUX:
            if not platforms.version_supported(version):
                raise RuntimeError(f"ClipNest needs OBS Studio {platforms.MIN_OBS_MAJOR} or newer, found {version}. " + platforms.INSTALL_HINT)
        elif not version.startswith("32.2.2"):
            raise RuntimeError(f"Expected OBS libraries 32.2.2, found {version}. Repair the runtime.")

    def source_settings(self, source):
        """A source's settings after its save callback (Linux only: the portal's RestoreToken)."""
        self.obs_source_save(source)
        data = self.obs_source_get_settings(source)
        try:
            return json.loads(decode(self.obs_data_get_json(data)) or "{}")
        finally:
            self.obs_data_release(data)

    @contextmanager
    def data(self, value):
        pointer = self.obs_data_create_from_json(json.dumps(value).encode())
        if not pointer: raise RuntimeError("Could not allocate OBS settings.")
        try: yield pointer
        finally: self.obs_data_release(pointer)

    def enumerate(self, function):
        values, index, result = [], 0, S()
        while function(index, C.byref(result)):
            values.append(decode(result.value))
            index += 1
        return values

    def game_hook(self, source):
        """OBS game_capture's get_hooked procedure: hooked flag plus window identity."""
        data = CallData()
        try:
            if not self.proc_handler_call(self.obs_source_get_proc_handler(source), b"get_hooked", C.byref(data)):
                return {"hooked": False, "title": "", "class": "", "executable": ""}
            hooked = C.c_bool()
            self.calldata_get_data(C.byref(data), b"hooked", C.byref(hooked), C.sizeof(hooked))
            result = {"hooked": bool(hooked.value)}
            for key in ("title", "class", "executable"):
                value = S()
                self.calldata_get_string(C.byref(data), utf8(key), C.byref(value))
                result[key] = decode(value.value)
            return result
        finally:
            self.bfree(data.stack)

    def procedure(self, output, name, result_key=None):
        data = CallData()
        try:
            if not self.proc_handler_call(self.obs_output_get_proc_handler(output), utf8(name), C.byref(data)):
                raise RuntimeError(f"Output does not support procedure {name}.")
            if result_key:
                result = S()
                self.calldata_get_string(C.byref(data), utf8(result_key), C.byref(result))
                return decode(result.value)
        finally:
            self.bfree(data.stack)
