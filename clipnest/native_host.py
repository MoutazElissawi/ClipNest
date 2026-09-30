"""Private libobs host, using inherited pipes. No socket or OBS frontend."""
from __future__ import annotations
import ctypes as C
import faulthandler
from datetime import datetime
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
import traceback
from .config import DATA, ENGINE, ENCODERS, validate
from .libobs import LibObs, VideoInfo, AudioInfo, Vec2, SIGNAL, METER, P, utf8, obs_path, decode


class NativeEngine:
    def __init__(self, emit):
        self.emit = emit
        self.lib = None
        self.started = False
        self.scene = None
        self.inputs, self.items, self.outputs = {}, {}, {}
        self.encoders, self.callbacks, self.meters = [], [], []
        self.stop_events, self.stop_codes = {}, {}
        self.record_path = self.last_replay = ""
        self.record_start = 0
        self.settings = {}
        self.com_initialized = False
        self.capture_attached = False
        self.capture_method = 2
        self.segment_path = ""
        self.segment_save_requested = False

    def initialize(self, settings):
        validate(settings)
        self.settings = settings
        self.capture_method = settings.get("capture_method", 2)
        if os.name == "nt":
            user32 = C.WinDLL("user32", use_last_error=True)
            user32.SetProcessDpiAwarenessContext.argtypes = [P]
            user32.SetProcessDpiAwarenessContext.restype = C.c_bool
            if not user32.SetProcessDpiAwarenessContext(P(-4)):
                print(f"DPI awareness request returned {C.get_last_error()}", file=sys.stderr, flush=True)
            result = C.windll.ole32.CoInitializeEx(None, 2)
            if result not in (0, 1):
                raise RuntimeError(f"Windows COM initialization failed: {result}")
            self.com_initialized = True
        self.staging = Path(settings["output"]) / "_Unsorted"
        self.staging.mkdir(parents=True, exist_ok=True)
        config_dir = DATA / "native-config"
        config_dir.mkdir(parents=True, exist_ok=True)
        self.lib = l = LibObs(ENGINE)
        print(f"ClipNest 0.2.2 host: {sys.executable}; encoder: {settings['encoder']}", file=sys.stderr, flush=True)
        if not l.obs_startup(b"en-US", obs_path(config_dir), None):
            raise RuntimeError("libobs initialization failed. See native-engine.log.")
        self.started = True
        l.obs_add_data_path(obs_path(ENGINE / "data/libobs"))
        graphics = obs_path(ENGINE / "bin/64bit/libobs-d3d11.dll")
        video = VideoInfo(graphics, settings["fps"], 1, settings["width"], settings["height"],
                          settings["width"], settings["height"], 2, 0, True, 2, 1, 2)
        result = l.obs_reset_video(C.byref(video))
        if result != 0:
            raise RuntimeError(f"Direct3D initialization failed (libobs code {result}). Check graphics drivers and native-engine.log.")
        if not l.obs_reset_audio(C.byref(AudioInfo(48000, 2))):
            raise RuntimeError("Could not initialize 48 kHz stereo audio.")
        for name in ("win-capture", "win-wasapi", "obs-ffmpeg", "obs-x264", "obs-nvenc"):
            module = P()
            result = l.obs_open_module(C.byref(module), obs_path(ENGINE / "obs-plugins/64bit" / (name + ".dll")),
                                       obs_path(ENGINE / "data/obs-plugins" / name))
            if result != 0 or not l.obs_init_module(module):
                if name == "obs-nvenc":
                    self.emit("NativeWarning", {"message": "NVIDIA encoder initialization failed. See native-engine.log for the helper or driver error."})
                    continue
                raise RuntimeError(f"Could not load {name} (code {result}). See native-engine.log.")
        l.obs_post_load_modules()
        return {"version": decode(l.obs_get_version_string()), "encoders": l.enumerate(l.obs_enum_encoder_types)}

    def active(self, kind):
        return bool(self.outputs.get(kind) and self.lib.obs_output_active(self.outputs[kind]))

    def release_idle_capture(self):
        if self.capture_attached and not self.active("record") and not self.active("replay"):
            self.lib.obs_set_output_source(0, None)
            self.capture_attached = False

    def capture_ready(self, timeout=4):
        screen = self.inputs.get("CN Screen")
        if not screen:
            raise RuntimeError("Screen source is missing. Reconnect the engine.")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.lib.obs_source_get_width(screen[0]) > 0 and self.lib.obs_source_get_height(screen[0]) > 0:
                return True
            time.sleep(.05)
        return False

    def prepare_capture(self):
        if self.capture_attached:
            return
        if not self.scene:
            raise RuntimeError("Capture scene is missing. Reconnect the engine.")
        self.lib.obs_set_output_source(0, self.lib.obs_scene_get_source(self.scene))
        self.capture_attached = True
        # Let the graphics thread activate the source before checking its size.
        time.sleep(.1)
        if self.capture_ready():
            return
        if self.capture_method != 2:
            self.emit("NativeNotice", {"message": "Desktop Duplication did not initialize. Trying Windows Graphics Capture; Windows 10 may show a yellow border."})
            with self.lib.data({"method": 2}) as data:
                self.lib.obs_source_update(self.inputs["CN Screen"][0], data)
            self.capture_method = 2
            time.sleep(.1)
            if self.capture_ready():
                return
        raise RuntimeError("Screen capture did not initialize. Recording was not started. Check the selected monitor and native-engine.log.")

    def make_outputs(self):
        if len(self.outputs) == 2:
            return
        if self.encoders or self.outputs:
            raise RuntimeError("Output initialization was incomplete. Stop and reconnect the engine before retrying.")
        l, s = self.lib, self.settings
        encoder_id = ENCODERS[s["encoder"]]
        available = l.enumerate(l.obs_enum_encoder_types)
        if encoder_id not in available:
            raise RuntimeError(f"{s['encoder']} is unavailable. Stop replay and select another encoder in Settings.")
        with l.data({"rate_control": "CBR", "bitrate": s["bitrate"], "keyint_sec": 2,
                     "preset": "veryfast" if s["encoder"].startswith("CPU") else "p4",
                     "preset2": "p4", "tune": "hq", "multipass": "disabled", "bf": 2,
                     "profile": "main" if s["encoder"] == "NVIDIA AV1" else "high",
                     "lookahead": False, "psycho_aq": False}) as data:
            video = l.obs_video_encoder_create(utf8(encoder_id), b"ClipNest Video", data, None)
        if not video: raise RuntimeError("Video encoder creation failed.")
        self.encoders.append(video)
        l.obs_encoder_set_video(video, l.obs_get_video())
        audio = []
        for index, name in enumerate(("Mix", "Desktop", "Microphone")):
            with l.data({"bitrate": 192}) as data:
                enc = l.obs_audio_encoder_create(b"ffmpeg_aac", utf8(name), data, index, None)
            if not enc: raise RuntimeError(f"Could not create AAC encoder for {name}.")
            self.encoders.append(enc)
            audio.append(enc)
            l.obs_encoder_set_audio(enc, l.obs_get_audio())
        continuous = s.get("replay_mode") == "continuous"
        for kind, output_id in (("record", "ffmpeg_muxer"), ("replay", "ffmpeg_muxer" if continuous else "replay_buffer")):
            with l.data({"directory": str(self.staging), "format": "Replay_%CCYY-%MM-%DD_%hh-%mm-%ss",
                         "extension": "mkv", "allow_spaces": False, "max_time_sec": s["replay_seconds"],
                         "max_size_mb": max(512, int(s["bitrate"] * s["replay_seconds"] / 8000 * 1.5))}) as data:
                output = l.obs_output_create(utf8(output_id), utf8("ClipNest " + kind), data, None)
            if not output: raise RuntimeError(f"Could not create {kind} output.")
            self.outputs[kind] = output
            l.obs_output_set_video_encoder(output, video)
            for index, enc in enumerate(audio): l.obs_output_set_audio_encoder(output, enc, index)
            self.stop_events[kind] = threading.Event()
            def stopped(_param, calldata, kind=kind):
                code = C.c_longlong()
                l.calldata_get_data(calldata, b"code", C.byref(code), C.sizeof(code))
                self.stop_codes[kind] = code.value
                if kind == "record":
                    self.emit("RecordStateChanged", {"outputState": "STOPPED", "outputPath": self.record_path,
                              "outputActive": False, "code": code.value})
                if kind == "replay" and self.segment_save_requested:
                    self.segment_save_requested = False
                    self.emit("ReplaySaveFailed", {"message": "Replay stopped before the requested split completed. Cached segments remain available."})
                if code.value:
                    self.emit("NativeWarning", {"message": f"{kind.capitalize()} stopped with error {code.value}: {decode(l.obs_output_get_last_error(self.outputs[kind]))}",
                              "output": kind, "code": code.value, "stopped": True})
                self.stop_events[kind].set()
            callback = SIGNAL(stopped)
            handler = l.obs_output_get_signal_handler(output)
            l.signal_handler_connect(handler, b"stop", callback, None)
            self.callbacks.append((handler, b"stop", callback))
        if continuous:
            def changed(_param, calldata):
                next_file = C.c_char_p()
                l.calldata_get_string(calldata, b"next_file", C.byref(next_file))
                previous, self.segment_path = self.segment_path, decode(next_file.value)
                requested, self.segment_save_requested = self.segment_save_requested, False
                if previous:
                    self.emit("ReplaySegmentClosed", {"path": previous, "next": self.segment_path, "save": requested})
            callback = SIGNAL(changed)
            handler = l.obs_output_get_signal_handler(self.outputs["replay"])
            l.signal_handler_connect(handler, b"file_changed", callback, None)
            self.callbacks.append((handler, b"file_changed", callback))
            return
        def saved(_param, _data):
            try:
                self.last_replay = l.procedure(self.outputs["replay"], "get_last_replay", "path")
                self.emit("ReplayBufferSaved", {"savedReplayPath": self.last_replay})
            except Exception as exc:
                self.emit("NativeWarning", {"message": str(exc)})
        callback = SIGNAL(saved)
        handler = l.obs_output_get_signal_handler(self.outputs["replay"])
        l.signal_handler_connect(handler, b"saved", callback, None)
        self.callbacks.append((handler, b"saved", callback))

    def stop(self, kind):
        if not self.active(kind):
            self.release_idle_capture()
            return
        event = self.stop_events[kind]
        event.clear()
        self.lib.obs_output_stop(self.outputs[kind])
        if not event.wait(20):
            raise RuntimeError(f"{kind.capitalize()} has not finished closing. Check native-engine.log.")
        if kind == "replay" and self.settings.get("replay_mode") == "continuous" and self.segment_path:
            self.emit("ReplaySegmentClosed", {"path": self.segment_path, "next": None, "save": False})
            self.segment_path = ""
        self.release_idle_capture()

    def start(self, kind):
        self.make_outputs()
        if self.active(kind): raise RuntimeError(f"{kind.capitalize()} is already active.")
        if kind == "record":
            self.record_path = str(self.staging / ("Recording_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f") + ".mkv"))
            with self.lib.data({"path": self.record_path}) as data:
                self.lib.obs_output_update(self.outputs[kind], data)
        if kind == "replay" and self.settings.get("replay_mode") == "continuous":
            folder = self.staging / "_ReplayCache" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            folder.mkdir(parents=True, exist_ok=False)
            self.segment_path = str(folder / "Segment_initial.mkv")
            self.segment_save_requested = False
            with self.lib.data({"path": self.segment_path, "directory": str(folder), "format": "Segment_%CCYY-%MM-%DD_%hh-%mm-%ss",
                                "extension": "mkv", "split_file": True, "allow_overwrite": False,
                                "max_time_sec": 2, "max_size_mb": 0}) as data:
                self.lib.obs_output_update(self.outputs[kind], data)
        self.stop_events[kind].clear()
        try:
            self.prepare_capture()
            if not self.lib.obs_output_start(self.outputs[kind]):
                reason = decode(self.lib.obs_output_get_last_error(self.outputs[kind]))
                raise RuntimeError(f"Could not start {kind}: {reason or 'check native-engine.log for the encoder error'}")
        except Exception:
            self.release_idle_capture()
            raise
        if kind == "record": self.record_start = time.monotonic()

    def properties(self, name, prop_name):
        l = self.lib
        properties = l.obs_source_properties(self.inputs[name][0])
        if not properties: raise RuntimeError(f"No properties for {name}.")
        try:
            prop = l.obs_properties_get(properties, utf8(prop_name))
            if not prop: raise RuntimeError(f"No property {prop_name} on {name}.")
            fmt = l.obs_property_list_format(prop)
            if fmt not in (1, 3): raise RuntimeError("Unsupported device-list value format.")
            values = []
            for i in range(l.obs_property_list_item_count(prop)):
                value = decode(l.obs_property_list_item_string(prop, i)) if fmt == 3 else l.obs_property_list_item_int(prop, i)
                values.append({"itemName": decode(l.obs_property_list_item_name(prop, i)), "itemValue": value,
                               "itemEnabled": not l.obs_property_list_item_disabled(prop, i)})
            return {"propertyItems": values}
        finally: l.obs_properties_destroy(properties)

    def attach_meter(self, source, name):
        l = self.lib
        meter = l.obs_volmeter_create(0)
        if not meter: return
        last = [0.0]
        def update(_param, magnitude, peak, input_peak):
            now = time.monotonic()
            if now - last[0] < .1: return
            last[0] = now
            channels = []
            for i in range(2):
                db = float(peak[i])
                channels.append([0, 10 ** (db / 20) if math.isfinite(db) else 0.0, 0])
            self.emit("InputVolumeMeters", {"inputs": [{"inputName": name, "inputLevelsMul": channels}]})
        callback = METER(update)
        l.obs_volmeter_add_callback(meter, callback, None)
        l.obs_volmeter_attach_source(meter, source)
        self.meters.append((meter, callback))

    def call(self, method, a):
        if method == "Initialize": return self.initialize(a["settings"])
        if not self.started: raise RuntimeError("Native recorder is not initialized.")
        l = self.lib
        if method == "GetSceneList": return {"scenes": [{"sceneName": "Capture"}] if self.scene else []}
        if method == "CreateScene":
            self.scene = l.obs_scene_create(b"Capture")
            if not self.scene: raise RuntimeError("Could not create capture scene.")
        elif method == "SetCurrentProgramScene": pass  # Attach only when an output starts.
        elif method == "GetInputKindList": return {"inputKinds": l.enumerate(l.obs_enum_input_types)}
        elif method == "GetInputList": return {"inputs": [{"inputName": n} for n in self.inputs]}
        elif method == "GetSpecialInputs": return {}
        elif method == "CreateInput":
            with l.data(a["inputSettings"]) as data:
                source = l.obs_source_create(utf8(a["inputKind"]), utf8(a["inputName"]), data, None)
            if not source: raise RuntimeError(f"Could not create {a['inputName']}.")
            self.inputs[a["inputName"]] = (source, a["inputKind"])
            item = l.obs_scene_add(self.scene, source)
            if not item: raise RuntimeError("Could not add input to scene.")
            self.items[a["inputName"]] = item
            if a["inputKind"].startswith("wasapi"):
                l.obs_source_set_muted(source, True)
                self.attach_meter(source, a["inputName"])
        elif method == "GetInputPropertiesListPropertyItems": return self.properties(a["inputName"], a["propertyName"])
        elif method == "SetInputSettings":
            with l.data(a["inputSettings"]) as data: l.obs_source_update(self.inputs[a["inputName"]][0], data)
        elif method == "SetInputMute": l.obs_source_set_muted(self.inputs[a["inputName"]][0], a["inputMuted"])
        elif method == "SetInputVolume": l.obs_source_set_volume(self.inputs[a["inputName"]][0], a["inputVolumeMul"])
        elif method == "SetInputAudioTracks":
            mask = sum(1 << (int(track) - 1) for track, enabled in a["inputAudioTracks"].items() if enabled)
            l.obs_source_set_audio_mixers(self.inputs[a["inputName"]][0], mask)
        elif method == "SetInputAudioMonitorType": l.obs_source_set_monitoring_type(self.inputs[a["inputName"]][0], 0)
        elif method == "GetSceneItemId": return {"sceneItemId": a["sourceName"]}
        elif method == "SetSceneItemTransform":
            item, t = self.items[a["sceneItemId"]], a["sceneItemTransform"]
            l.obs_sceneitem_set_pos(item, C.byref(Vec2(t["positionX"], t["positionY"])))
            l.obs_sceneitem_set_alignment(item, t["alignment"])
            l.obs_sceneitem_set_bounds_type(item, 2)
            l.obs_sceneitem_set_bounds_alignment(item, t["boundsAlignment"])
            l.obs_sceneitem_set_bounds(item, C.byref(Vec2(t["boundsWidth"], t["boundsHeight"])))
        elif method == "GetRecordStatus":
            self.release_idle_capture()
            elapsed = max(0, time.monotonic() - self.record_start) if self.active("record") else 0
            hours, rem = divmod(int(elapsed), 3600)
            minutes, seconds = divmod(rem, 60)
            return {"outputActive": self.active("record"), "outputTimecode": f"{hours:02}:{minutes:02}:{seconds:02}",
                    "captureAttached": self.capture_attached, "captureMethod": self.capture_method}
        elif method == "GetReplayBufferStatus": return {"outputActive": self.active("replay")}
        elif method == "StartRecord": self.start("record")
        elif method == "StartReplayBuffer": self.start("replay")
        elif method == "StopRecord":
            self.stop("record")
            return {"outputPath": self.record_path}
        elif method == "StopReplayBuffer": self.stop("replay")
        elif method == "SaveReplayBuffer":
            if not self.active("replay"): raise RuntimeError("Start replay before saving a clip.")
            if self.settings.get("replay_mode") == "continuous":
                self.segment_save_requested = True
                l.procedure(self.outputs["replay"], "split_file")
                return {}
            # Archiving removes the previous staging filename. Supply a fresh name
            # even for two saves within the same second so duplicate guards stay valid.
            with l.data({"format": "Replay_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")}) as data:
                l.obs_output_update(self.outputs["replay"], data)
            l.procedure(self.outputs["replay"], "save")
        elif method == "GetLastReplayBufferReplay": return {"savedReplayPath": self.last_replay}
        else: raise RuntimeError(f"Unknown native-engine method: {method}")
        return {}

    def shutdown(self):
        if not self.started:
            if self.com_initialized:
                C.windll.ole32.CoUninitialize()
                self.com_initialized = False
            return
        l = self.lib
        self.stop("record")
        self.stop("replay")
        for handler, name, callback in self.callbacks: l.signal_handler_disconnect(handler, name, callback, None)
        for output in self.outputs.values(): l.obs_output_release(output)
        for enc in self.encoders: l.obs_encoder_release(enc)
        for meter, callback in self.meters:
            l.obs_volmeter_remove_callback(meter, callback, None)
            l.obs_volmeter_destroy(meter)
        l.obs_set_output_source(0, None)
        if self.scene: l.obs_scene_release(self.scene)
        for source, _ in self.inputs.values(): l.obs_source_release(source)
        l.obs_shutdown()
        self.started = False
        if self.com_initialized:
            C.windll.ole32.CoUninitialize()
            self.com_initialized = False


def main():
    faulthandler.enable(file=sys.stderr, all_threads=True)
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    lock = threading.Lock()
    def send(value):
        try:
            with lock:
                protocol.write(json.dumps(value, allow_nan=False) + "\n")
                protocol.flush()
        except (BrokenPipeError, OSError): pass
    engine = NativeEngine(lambda name, data: send({"event": name, "data": data}))
    try:
        for line in sys.stdin:
            request = {}
            try:
                request = json.loads(line)
                if request["method"] == "Shutdown":
                    engine.shutdown()
                    send({"id": request["id"], "result": {}})
                    break
                result = engine.call(request["method"], request.get("args", {}))
                send({"id": request["id"], "result": result})
            except Exception as exc:
                traceback.print_exc(file=sys.stderr)
                send({"id": request.get("id"), "error": str(exc)})
    finally:
        engine.shutdown()

if __name__ == "__main__": main()
