from __future__ import annotations

import copy
import ctypes
from ctypes import wintypes
import json
import logging
import os
from pathlib import Path
import queue
import subprocess
import time

import psutil
from PySide6.QtCore import QThread, Signal

from .catalog import Catalog, archive_file
from .config import DATA, ENGINE, SETTINGS, atomic_json, validate
from . import fullscreen
from .native_client import NativeClient, NativeError as ObsError

log = logging.getLogger("clipnest")
SCENE, SCREEN, DESKTOP, MIC = "Capture", "CN Screen", "CN Desktop", "CN Microphone"
APP_AUDIO = "CN App Audio"
GAME_LAYER = "CN Game Layer"
GAME_LAYER_SETTINGS = {"capture_mode": "any_fullscreen", "capture_cursor": True, "anti_cheat_hook": True,
                       "capture_audio": False, "allow_transparency": False}
JOURNAL = DATA / "pending.json"


class Engine(QThread):
    state = Signal(dict)
    devices = Signal(dict)
    message = Signal(str)
    error = Signal(str)
    saved = Signal(str)
    notification = Signal(dict)
    meters = Signal(dict)
    applied = Signal(dict)
    shutdown_done = Signal(bool)

    def __init__(self, settings):
        super().__init__()
        self.settings = copy.deepcopy(settings)
        self.commands = queue.Queue()
        self.rpc = None
        self.retiring_clients = []
        self.running = True
        self.shutting_down = False
        self.shutdown_started = None
        self.shutdown_failures = 0
        self.catalog = Catalog(self.settings["games"])
        self.recording = False
        self.replay = False
        self.announced_active = {'record': False, 'replay': False}
        self.expected_stops = set()
        self.failed_outputs = set()
        self.record_context = None
        self.pending_replay = None
        self.processed = set()
        self.muted = None
        self.meter_levels = {}
        self.last_meter = 0
        self.last_poll = 0
        self.continuous = None
        self.replay_started = None
        self.archive_retry = []
        self.next_retry = 0
        self.recovery_intent = None
        self.capture_missing_since = None
        self.last_health_recovery = 0.0
        self.system_suspended = False
        self.game_layer_on = None
        self.game_layer_device = None
        self.last_layer_check = 0.0
        self.last_layer_window = None
        self.last_layer_reset = 0.0
        self.stitch = None
        self.layer_rects = {}
        self.layer_placed = None
        if JOURNAL.exists():
            try:
                data = json.loads(JOURNAL.read_text())
                self.record_context = data.get("record")
                self.pending_replay = data.get("replay")
            except (OSError, ValueError):
                log.exception("Could not read pending-save journal")

    def submit(self, command, data=None):
        if command == "shutdown":
            self.begin_shutdown()
        if not self.shutting_down or command == "shutdown":
            self.commands.put((command, data))

    def begin_shutdown(self):
        self.shutting_down = True
        if self.shutdown_started is None:
            self.shutdown_started = time.monotonic()
        elapsed = time.monotonic()-self.shutdown_started
        for client in [self.rpc, *list(self.retiring_clients)]:
            if client is not None and hasattr(client, 'begin_shutdown'):
                client.begin_shutdown(timeout=max(.01, 20-elapsed))
        if self.continuous is not None and hasattr(self.continuous, 'begin_shutdown'):
            self.continuous.begin_shutdown(timeout=max(.01, 25-elapsed))

    def finish_shutdown(self):
        jobs, self.archive_retry = self.archive_retry, []
        for path, ctx, kind, _ in jobs:
            self.finish_file(path, ctx, kind, 10)
        self.recording = self.replay = False
        self.state.emit({"connected": False})
        self.running = False
        self.shutdown_done.emit(True)

    def abort_shutdown(self):
        """Last-resort cleanup after bounded retries; never resume capture."""
        for client in [self.rpc, *list(self.retiring_clients)]:
            if client is None:
                continue
            try:
                client.force_stop()
                client.disconnect()
            except Exception:
                log.exception('Could not complete native recorder cleanup')
        self.rpc = None
        self.retiring_clients.clear()
        if self.continuous is not None:
            try:
                self.continuous.abort()
                self.continuous.close()
                self.drain_continuous()
            except Exception:
                log.exception('Replay cache retained after interrupted cleanup')
            self.continuous = None
        self.message.emit('Closing after a recorder timeout. Unfinished files remain in _Unsorted; check recorder logs.')
        self.finish_shutdown()

    def shutdown_failed(self, exc):
        log.exception('Shutdown still finishing')
        self.shutdown_failures += 1
        if self.shutdown_failures >= 3 or time.monotonic()-self.shutdown_started >= 28:
            self.abort_shutdown()
        else:
            self.message.emit(f'Still closing the recorder: {exc}')
            self.msleep(250)

    def journal(self):
        atomic_json(JOURNAL, {"record": self.record_context, "replay": self.pending_replay})

    def run(self):
        try:
            self.catalog.discover()
        except Exception:
            log.exception("Game discovery failed")
        while self.running:
            if self.shutting_down:
                try:
                    self.handle("shutdown", None)
                except Exception as exc:
                    self.shutdown_failed(exc)
                continue
            try:
                command, data = self.commands.get(timeout=.025)
            except queue.Empty:
                command = None
            if command:
                try:
                    self.handle(command, data)
                except Exception as exc:
                    log.exception("Command failed: %s", command)
                    if command == "shutdown":
                        self.shutdown_failed(exc)
                        continue
                    self.expected_stops.clear()
                    self.error.emit(str(exc))
            if self.shutting_down:
                continue
            self.drain_continuous()
            if self.rpc:
                try:
                    self.rpc.pump()
                    now = time.monotonic()
                    if now - self.last_poll > .8:
                        self.poll()
                        self.last_poll = now
                    if now - self.last_layer_check > .2:
                        self.last_layer_check = now
                        self.update_game_layer()
                    if self.archive_retry and now > self.next_retry:
                        jobs, self.archive_retry = self.archive_retry, []
                        for path, ctx, kind, attempts in jobs:
                            self.finish_file(path, ctx, kind, attempts)
                        self.next_retry = now + 1
                except Exception as exc:
                    log.exception("Recorder connection failed")
                    active = [name for name, active in (('record', self.recording), ('replay', self.replay))
                              if active or self.announced_active[name]]
                    if active:
                        self.notify('Capture stopped unexpectedly', 'Recorder connection lost. Check recorder logs.', 'error')
                        self.failed_outputs.update(active)
                        self.announced_active = {'record': False, 'replay': False}
                    else:
                        self.notify('Recorder disconnected', 'The recorder connection was lost. Check recorder logs.', 'error')
                    old = self.rpc
                    self.rpc = None
                    try:
                        old.disconnect()
                    except Exception as cleanup_error:
                        self.retiring_clients.append(old)
                        self.error.emit(str(cleanup_error))
                    self.state.emit({"connected": False})
                    self.error.emit(f"Native recorder connection lost: {exc}. Check _Unsorted for completed files and native-engine.log for details.")

    def drain_continuous(self):
        if self.continuous is None:
            return
        while True:
            try:
                kind, value, context, expired = self.continuous.results.get_nowait()
            except queue.Empty:
                return
            if kind == "saved":
                self.finish_file(value, context, "Replay")
                if expired:
                    self.message.emit("Replay footage expired or a segment failed before this save; continuity across that missing interval is not available.")
            else:
                self.error.emit("Continuous replay: " + value + ". Cache segments are retained under _Unsorted/_ReplayCache.")
                if context and kind != 'aborted' and not self.shutting_down:
                    self.pending_replay = None
                    self.journal()

    def prepare_continuous(self):
        if self.continuous is not None:
            self.continuous.close()
        from .media import tools_path
        from .replay import ContinuousReplay
        try:
            prefs = json.loads((DATA / "editor.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prefs = {}
        ffmpeg, ffprobe = tools_path(prefs.get("ffmpeg_folder", ""))
        self.continuous = ContinuousReplay(ffmpeg, ffprobe, Path(self.settings["output"])/"_Unsorted", self.settings["replay_seconds"])

    def call(self, method, **args):
        if not self.rpc:
            raise RuntimeError("Click Start engine first.")
        return self.rpc.call(method, **args)

    def capture_app(self):
        if self.settings.get("capture_target") in ("window", "game"):
            return self.catalog.window_app(self.settings.get("window_value", ""))
        return self.catalog.poll()

    def context(self, replay=False):
        app = self.capture_app()
        if replay and self.settings.get('capture_target', 'display') in ('display', 'displays') and hasattr(self.catalog, 'replay_app'):
            seconds = self.settings.get('replay_seconds', 90)
            if self.replay_started is not None:
                seconds = min(seconds, max(0, time.monotonic() - self.replay_started))
            app = self.catalog.replay_app(seconds)
        context = {"output": self.settings["output"], "category": app["category"], "requested": time.time()}
        log.info("Save context pid=%s name=%r exe=%r category=%r requested=%s", app.get("pid"),
                 app.get("name"), app.get("exe"), context["category"], context["requested"])
        log.info("Save capture target=%s display=%r configured_method=%s window=%r title=%r replay=%s",
                 self.settings.get('capture_target', 'display'), self.settings.get('monitor_value'),
                 self.settings.get('window_method' if self.settings.get('capture_target') == 'window' else 'capture_method'),
                 self.settings.get('window_value'), app.get('title'), replay)
        if self.game_layer_on is not None:
            window, hook = self.last_layer_window or {}, self.game_layer_state() or {}
            log.info("Save game layer drawn=%s hooked=%s hooked_exe=%r hooked_size=%s foreground_fullscreen=%s foreground_monitor=%r capture_monitor=%r display_affinity=%s",
                     self.game_layer_on, hook.get('hooked'), hook.get('executable'), hook.get('size'), window.get('fullscreen'),
                     window.get('device'), self.game_layer_device, window.get('affinity'))
        return context

    def game_layer_state(self):
        try:
            return self.call("GetGameLayerState", inputName=GAME_LAYER)
        except ObsError:
            return None

    def update_game_layer(self):
        """Draw the hooked game only while that game is the focused fullscreen window on the captured monitor.

        The hook stays attached while the layer is not drawn, so returning from Alt-Tab is immediate.
        """
        if self.game_layer_on is None:
            return
        window = fullscreen.foreground_window()
        self.last_layer_window = window
        draw = False
        if fullscreen.layer_wanted(window, self.game_layer_device):
            hook = self.game_layer_state() or {}
            if hook.get('hooked') and not fullscreen.same_window_app(window, hook):
                # OBS keeps its first hook in "any fullscreen" mode; re-hook the focused game.
                if time.monotonic() - self.last_layer_reset > 3:
                    self.last_layer_reset = time.monotonic()
                    log.info("Game layer re-hooking: hooked %r, focused class=%r", hook.get('executable'), window.get('class'))
                    self.call("SetSceneItemEnabled", sceneName=SCENE, sceneItemId=GAME_LAYER, sceneItemEnabled=False)
                    self.call("SetSceneItemEnabled", sceneName=SCENE, sceneItemId=GAME_LAYER, sceneItemEnabled=True)
            else:
                draw = bool(hook.get('hooked')) and (hook.get('size') or [0])[0] > 0
        if draw and self.layer_rects:
            device = (window.get('device') or '').casefold()
            if device in self.layer_rects and device != self.layer_placed:
                x, y, w, h = self.layer_rects[device]
                self.call("SetSceneItemTransform", sceneName=SCENE, sceneItemId=GAME_LAYER,
                          sceneItemTransform={"positionX": x, "positionY": y, "alignment": 5,
                                              "boundsType": "OBS_BOUNDS_SCALE_INNER", "boundsAlignment": 0,
                                              "boundsWidth": w, "boundsHeight": h})
                self.layer_placed = device
        if draw == self.game_layer_on:
            return
        self.call("SetInputEnabled", inputName=GAME_LAYER, inputEnabled=draw)
        self.game_layer_on = draw
        log.info("Game layer %s (foreground class=%r monitor=%r affinity=%s)", "drawn" if draw else "not drawn",
                 (window or {}).get('class'), (window or {}).get('device'), (window or {}).get('affinity'))

    def connect_engine(self):
        if self.rpc:
            return
        self.retiring_clients = [c for c in self.retiring_clients if c.process.poll() is None]
        if self.retiring_clients:
            raise RuntimeError("The previous native engine is still finishing. Wait before starting another session.")
        if not (ENGINE / "bin/64bit/obs.dll").exists():
            raise RuntimeError("Recorder libraries are missing. Close ClipNest and run Start_ClipNest.bat.")
        self.message.emit("Starting ClipNest's native recording engine...")
        self.stitch = self.stitch_layout()
        self.rpc = NativeClient(self.host_settings(), self.on_event)
        try:
            self.recording = self.replay = False
            self.setup_sources()
            self.read_devices()
            self.muted = None
            self.set_mic(self.settings["mic_mode"] != "Always on")
            self.call("SetInputVolume", inputName=MIC, inputVolumeMul=self.settings["mic_volume"] / 100)
            if self.pending_replay or self.record_context:
                self.message.emit("An earlier session ended before sorting completed. Check _Unsorted for its files.")
            self.pending_replay = self.record_context = None
            self.journal()
            self.message.emit(f"Native engine ready with {self.settings['encoder']}. Start replay when you want to begin buffering.")
            self.poll()
        except Exception:
            old = self.rpc
            self.rpc = None
            try:
                old.disconnect()
            except Exception as cleanup_error:
                self.retiring_clients.append(old)
                self.error.emit(str(cleanup_error))
            self.state.emit({"connected": False})
            raise

    def setup_sources(self):
        scenes = self.call("GetSceneList")["scenes"]
        if not any(s["sceneName"] == SCENE for s in scenes):
            self.call("CreateScene", sceneName=SCENE)
        kinds = self.call("GetInputKindList", unversioned=False)["inputKinds"]
        inputs = {i["inputName"] for i in self.call("GetInputList")["inputs"]}
        self.call("SetCurrentProgramScene", sceneName=SCENE)
        window_capture = self.settings.get("capture_target") in ("window", "game")
        video_kind = "game_capture" if self.settings.get("capture_target") == "game" else "window_capture" if window_capture else "monitor_capture"
        video_settings = ({"window": self.settings.get("window_value", ""), "method": self.settings.get("window_method", 2),
                           "priority": 2, "cursor": True, "client_area": True, "capture_audio": False, "force_sdr": True}
                          if window_capture else {"capture_cursor": True, "method": self.settings.get("capture_method", 2)})
        if self.settings.get("capture_target") == "game":
            video_settings = {"capture_mode": "window", "window": self.settings.get("window_value", ""),
                              "priority": 2, "capture_cursor": True, "anti_cheat_hook": True, "capture_audio": False}
        for name, prefix, settings in [(SCREEN, video_kind, video_settings),
                                       (DESKTOP, "wasapi_output_capture", {"device_id": self.settings["desktop_device"], "use_device_timing": False}),
                                       (MIC, "wasapi_input_capture", {"device_id": self.settings["mic_device"], "use_device_timing": False})]:
            if name not in inputs:
                kind = next((k for k in reversed(kinds) if k == prefix or k.startswith(prefix + "_v")), None)
                if not kind:
                    raise RuntimeError(f"The native engine is missing its Windows capture component: {prefix}")
                self.call("CreateInput", sceneName=SCENE, inputName=name, inputKind=kind,
                          inputSettings=settings, sceneItemEnabled=True)
            elif name != SCREEN:
                self.call("SetInputSettings", inputName=name, inputSettings=settings)
        if not window_capture:
            monitor_property = self.settings["monitor_property"]
            monitors = self.call("GetInputPropertiesListPropertyItems", inputName=SCREEN,
                                 propertyName=monitor_property)["propertyItems"]
            monitors = [m for m in monitors if m.get("itemEnabled", True)]
            if not monitors:
                raise RuntimeError("OBS could not find a capture monitor. Check its display-capture source.")
            selected = self.settings["monitor_value"]
            if selected is None:
                selected = monitors[0]["itemValue"]
            elif selected not in [m["itemValue"] for m in monitors]:
                selected = monitors[0]["itemValue"]
                self.message.emit("The saved monitor is disconnected. Using the first available monitor; check Settings before capturing.")
            self.capture_monitor = (monitor_property, selected)
            self.call("SetInputSettings", inputName=SCREEN,
                      inputSettings={monitor_property: selected, "force_sdr": True, "method": self.settings.get("capture_method", 2)})
        # Silence default global sources to prevent duplicated desktop/mic audio.
        for name in self.call("GetSpecialInputs").values():
            if name and name not in (MIC, DESKTOP):
                self.call("SetInputMute", inputName=name, inputMuted=True)
                self.call("SetInputAudioTracks", inputName=name, inputAudioTracks={str(i): False for i in range(1, 7)})
        for name, tracks in [(DESKTOP, (1, 2)), (MIC, (1, 3))]:
            self.call("SetInputAudioTracks", inputName=name, inputAudioTracks={str(i): i in tracks for i in range(1, 7)})
            self.call("SetInputAudioMonitorType", inputName=name, monitorType="OBS_MONITORING_TYPE_NONE")
        self.call("SetInputMute", inputName=DESKTOP, inputMuted=False)
        self.call("SetInputVolume", inputName=DESKTOP, inputVolumeMul=1.0)
        self.setup_app_audio(kinds)
        self.muted = None
        self.set_mic(self.settings["mic_mode"] != "Always on")
        item = self.call("GetSceneItemId", sceneName=SCENE, sourceName=SCREEN)["sceneItemId"]
        self.call("SetSceneItemTransform", sceneName=SCENE, sceneItemId=item,
                  sceneItemTransform={"positionX": 0, "positionY": 0, "alignment": 5,
                                      "boundsType": "OBS_BOUNDS_SCALE_INNER", "boundsAlignment": 0,
                                      "boundsWidth": self.settings["width"], "boundsHeight": self.settings["height"]})
        if self.stitch:
            self.setup_stitched_screens(kinds)
        self.setup_game_layer(kinds)

    def stitch_layout(self):
        """Monitor placement for 'All displays', read before the host sizes its canvas."""
        if self.settings.get("capture_target") != "displays":
            return None
        monitors = [m for m in fullscreen.monitor_layout() if m["id"]]
        if not monitors:
            raise RuntimeError("No displays were found for stitched capture. Check Windows display settings.")
        monitors.sort(key=lambda m: (m["rect"][0], m["rect"][1]))
        base, output, places = fullscreen.stitched_canvas([m["rect"] for m in monitors], self.settings["height"])
        log.info("Stitched capture: %s monitors, canvas %sx%s, output %sx%s", len(monitors), *base, *output)
        return {"base": base, "output": output, "monitors": [dict(m, place=p) for m, p in zip(monitors, places)]}

    def host_settings(self):
        settings = copy.deepcopy(self.settings)
        if self.stitch:
            settings.update(base_width=self.stitch["base"][0], base_height=self.stitch["base"][1],
                            width=self.stitch["output"][0], height=self.stitch["output"][1])
        return settings

    def setup_stitched_screens(self, kinds):
        """One display source per monitor, placed at its desktop position on the canvas."""
        available = {m["itemValue"] for m in self.call("GetInputPropertiesListPropertyItems", inputName=SCREEN,
                                                         propertyName="monitor_id")["propertyItems"]}
        monitors = [m for m in self.stitch["monitors"] if m["id"] in available]
        if not monitors:
            raise RuntimeError("OBS could not match any display for stitched capture. Use Refresh displays, then Apply.")
        self.stitch["monitors"] = monitors
        kind = self.inputs_kind(kinds, "monitor_capture")
        for i, monitor in enumerate(monitors):
            name = SCREEN if i == 0 else f"{SCREEN} {i + 1}"
            settings = {"monitor_id": monitor["id"], "force_sdr": True, "capture_cursor": True,
                        "method": self.settings.get("capture_method", 2)}
            if i == 0:
                self.call("SetInputSettings", inputName=name, inputSettings=settings)
            else:
                self.call("CreateInput", sceneName=SCENE, inputName=name, inputKind=kind,
                          inputSettings=settings, sceneItemEnabled=True)
            x, y, w, h = monitor["place"]
            self.call("SetSceneItemTransform", sceneName=SCENE, sceneItemId=name,
                      sceneItemTransform={"positionX": x, "positionY": y, "alignment": 5,
                                          "boundsType": "OBS_BOUNDS_SCALE_INNER", "boundsAlignment": 0,
                                          "boundsWidth": w, "boundsHeight": h})

    @staticmethod
    def inputs_kind(kinds, prefix):
        return next((k for k in reversed(kinds) if k == prefix or k.startswith(prefix + "_v")), prefix)

    def setup_app_audio(self, kinds):
        """Optional fourth track with one application's audio (Windows 10 2004+).

        The Desktop and Mix tracks still contain that application, because system
        output capture cannot exclude a process.
        """
        if not self.settings.get("app_audio"):
            return
        kind = next((k for k in reversed(kinds) if k == "wasapi_process_output_capture" or k.startswith("wasapi_process_output_capture_v")), None)
        if not kind:
            self.message.emit("Application audio capture needs Windows 10 version 2004 or newer. Recording continues with three tracks.")
            self.settings["app_audio"] = ""
            return
        self.call("CreateInput", sceneName=SCENE, inputName=APP_AUDIO, inputKind=kind,
                  inputSettings={"window": self.settings["app_audio"], "priority": 2}, sceneItemEnabled=True)
        self.call("SetInputAudioTracks", inputName=APP_AUDIO, inputAudioTracks={str(i): i == 4 for i in range(1, 7)})
        self.call("SetInputAudioMonitorType", inputName=APP_AUDIO, monitorType="OBS_MONITORING_TYPE_NONE")
        self.call("SetInputMute", inputName=APP_AUDIO, inputMuted=False)
        self.call("SetInputVolume", inputName=APP_AUDIO, inputVolumeMul=1.0)

    def setup_game_layer(self, kinds):
        """Hook fullscreen games above display capture; the display source stays as configured."""
        self.game_layer_on = None
        if self.settings.get("capture_target", "display") not in ("display", "displays") or not self.settings.get("game_layer", True):
            return
        kind = next((k for k in reversed(kinds) if k == "game_capture" or k.startswith("game_capture_v")), None)
        if not kind:
            log.warning("Game layer unavailable: the native engine has no game_capture source")
            return
        self.call("CreateInput", sceneName=SCENE, inputName=GAME_LAYER, inputKind=kind,
                  inputSettings=dict(GAME_LAYER_SETTINGS), sceneItemEnabled=True)
        self.call("SetInputEnabled", inputName=GAME_LAYER, inputEnabled=False)
        self.call("SetSceneItemTransform", sceneName=SCENE, sceneItemId=GAME_LAYER,
                  sceneItemTransform={"positionX": 0, "positionY": 0, "alignment": 5,
                                      "boundsType": "OBS_BOUNDS_SCALE_INNER", "boundsAlignment": 0,
                                      "boundsWidth": self.settings["width"], "boundsHeight": self.settings["height"]})
        prop, monitor = getattr(self, "capture_monitor", (self.settings.get("monitor_property"), self.settings.get("monitor_value")))
        self.game_layer_device = fullscreen.monitor_device(monitor) if prop == "monitor_id" else None
        if self.stitch:
            # Every display is recorded; the layer moves to the monitor the game is on.
            self.game_layer_device = None
            self.layer_rects = {m["device"].casefold(): m["place"] for m in self.stitch["monitors"]}
            self.layer_placed = None
        self.game_layer_on = False
        log.info("Game layer ready for display %r", self.game_layer_device or "any monitor")

    def read_devices(self):
        result = {}
        for key, name in [("microphones", MIC), ("outputs", DESKTOP)]:
            result[key] = self.call("GetInputPropertiesListPropertyItems", inputName=name, propertyName="device_id")["propertyItems"]
        kinds = self.call("GetInputKindList", unversioned=False)["inputKinds"]
        def capture_kind(prefix):
            return next((k for k in reversed(kinds) if k == prefix or k.startswith(prefix + "_v")), prefix)
        result["monitors"] = []
        for prop in ("monitor_id", "monitor"):
            try:
                items = self.call("GetInputPropertiesListPropertyItems", inputKind=capture_kind("monitor_capture"), propertyName=prop)["propertyItems"]
                if items:
                    result["monitors"] = items
                    result["monitor_property"] = prop
                    break
            except ObsError:
                continue
        result["windows"] = self.call("GetInputPropertiesListPropertyItems", inputKind=capture_kind("window_capture"), propertyName="window")["propertyItems"]
        try:
            result["audio_apps"] = self.call("GetInputPropertiesListPropertyItems", inputKind=capture_kind("wasapi_process_output_capture"), propertyName="window")["propertyItems"]
        except RuntimeError:
            result["audio_apps"] = []
        # Game capture includes minimized game windows omitted by Window capture.
        try:
            extra = self.call("GetInputPropertiesListPropertyItems", inputKind=capture_kind("game_capture"), propertyName="window")["propertyItems"]
            known = {item['itemValue'] for item in result['windows']}
            result['windows'].extend(item for item in extra if item['itemValue'] not in known)
        except RuntimeError:
            pass
        self.devices.emit(result)

    def set_mic(self, muted):
        if self.muted != muted:
            self.call("SetInputMute", inputName=MIC, inputMuted=bool(muted))
            self.muted = muted

    def poll(self):
        rec = self.call("GetRecordStatus")
        self.recording = rec["outputActive"]
        self.replay = self.call("GetReplayBufferStatus")["outputActive"]
        for kind, active in (('record', self.recording), ('replay', self.replay)):
            previous = self.announced_active[kind]
            if active and not previous:
                self.failed_outputs.discard(kind)
                self.notify('Recording started' if kind == 'record' else 'Instant replay started',
                            'Capturing your screen' if kind == 'record' else f"Keeping up to {self.settings['replay_seconds']} seconds")
            elif previous and not active and kind not in self.expected_stops:
                self.output_failed(kind, 'The output stopped unexpectedly. Check recorder logs.')
            if not active:
                self.expected_stops.discard(kind)
            self.announced_active[kind] = active
        if self.pending_replay and self.settings.get("replay_mode") != "continuous" and time.time() - self.pending_replay["requested"] > 45:
            self.message.emit("Replay save is taking longer than expected. Check _Unsorted and the recorder log.")
            self.pending_replay = None
            self.journal()
        size = rec.get('sourceSize')
        now = time.monotonic()
        if (self.recording or self.replay) and size is not None and (size[0] <= 0 or size[1] <= 0):
            if self.capture_missing_since is None:
                self.capture_missing_since = now
            elif now-self.capture_missing_since >= 4 and now-self.last_health_recovery > 60 and not self.shutting_down:
                self.capture_missing_since = None
                self.last_health_recovery = now
                self.notify('Capture source lost', 'Reconnecting the selected capture source; a fresh replay buffer will start.', 'error')
                self.handle('recover_capture', 'The selected capture source stopped supplying capture dimensions')
                return
        else:
            self.capture_missing_since = None
        elapsed = time.monotonic() - self.replay_started if self.replay_started else None
        self.state.emit({"connected": True, "recording": self.recording, "replay": self.replay,
                         "timecode": rec["outputTimecode"], "app": self.capture_app(),
                         "replay_seconds": self.settings["replay_seconds"], "buffered": elapsed,
                         "capture_target": self.settings.get("capture_target", "display"),
                         "capture_attached": rec.get("captureAttached", False), "capture_method": rec.get("captureMethod", self.settings.get("capture_method", 2)),
                         "saving": self.pending_replay is not None, "muted": self.muted, "stats": rec.get("stats", {}),
                         "game_layer": bool(self.game_layer_on)})

    def on_event(self, kind, data):
        if kind == "NativeNotice":
            self.message.emit(data.get("message", ""))
        elif kind == "NativeWarning":
            if data.get('stopped') and data.get('output') in ('record', 'replay'):
                self.output_failed(data['output'], data.get('message', 'Output stopped.'))
            self.error.emit(data.get("message", "Native recorder warning"))
        elif kind == "InputVolumeMeters":
            for entry in data.get("inputs", []):
                channels = entry.get("inputLevelsMul", [])
                if entry.get("inputName") in (MIC, DESKTOP):
                    self.meter_levels[entry["inputName"]] = max((c[1] for c in channels if len(c) > 1), default=0)
            now = time.monotonic()
            if now - self.last_meter >= .08:
                self.last_meter = now
                self.meters.emit(dict(self.meter_levels))
        elif kind == "ReplaySaveFailed":
            if not self.shutting_down:
                self.pending_replay = None
                self.journal()
            self.error.emit(data.get("message", "Replay save failed."))
        elif kind == "ReplaySegmentClosed":
            if self.continuous is not None:
                self.continuous.add(data["path"], data.get("next"), self.pending_replay if data.get("save") else None)
        elif kind == "ReplayBufferSaved":
            if self.pending_replay:
                self.finish_file(data["savedReplayPath"], self.pending_replay, "Replay")
            else:
                self.message.emit("An externally triggered replay was saved in _Unsorted.")
        elif kind == "RecordStateChanged" and data.get("outputState") == "STOPPED":
            if data.get('code') or (self.announced_active['record'] and 'record' not in self.expected_stops):
                self.output_failed('record', f"Recording interrupted (code {data.get('code', 0)}). Check recorder logs.")
            self.recording = False
            if data.get("outputPath") and self.record_context:
                self.finish_file(data["outputPath"], self.record_context, "Recording")

    def notify(self, title, detail='', tone='success'):
        self.notification.emit(dict(title=title, detail=detail, tone=tone))

    def output_failed(self, kind, detail):
        if kind == 'record' and self.record_context:
            self.record_context['interrupted'] = True
        if kind not in self.failed_outputs:
            self.failed_outputs.add(kind)
            self.notify('Recording stopped unexpectedly' if kind == 'record' else 'Instant replay stopped unexpectedly', detail, 'error')

    def finish_file(self, path, context, kind, attempts=0):
        if path in self.processed:
            return
        try:
            destination = archive_file(path, context["output"], context["category"], kind)
        except OSError as exc:
            if attempts < 10:
                self.archive_retry.append((path, context, kind, attempts + 1))
                return
            self.error.emit(f"Clip saved but could not be moved. It is still at {path}. {exc}")
        except ValueError as exc:
            self.error.emit(str(exc))
        else:
            self.saved.emit(str(destination))
            title = 'Recording finished' if kind == 'Recording' else 'Clip saved'
            if kind == 'Recording' and context.get('interrupted'):
                title = 'Interrupted recording saved'
            self.notify(title, Path(destination).name)
        self.processed.add(path)
        if kind == "Replay":
            self.pending_replay = None
        else:
            self.record_context = None
        self.journal()

    def stop_record(self):
        ctx = self.record_context or self.context()
        self.expected_stops.add('record')
        try:
            result = self.call("StopRecord")
        except Exception:
            self.expected_stops.discard('record')
            raise
        self.recording = False
        if result.get("outputPath"):
            self.finish_file(result["outputPath"], ctx, "Recording")

    def retire_for_recovery(self, reason):
        """Finalize old files before rebuilding the D3D/WASAPI host after resume."""
        if self.recovery_intent is None:
            if not self.rpc:
                return
            self.recovery_intent = dict(record=self.recording, replay=self.replay)
        if self.record_context:
            self.record_context['interrupted'] = True
            self.journal()
        self.expected_stops.update(('record', 'replay'))
        self.message.emit(reason + '. Finalizing the previous capture session...')
        if self.rpc:
            client = self.rpc
            for kind, method in (('record', 'StopRecord'), ('replay', 'StopReplayBuffer')):
                try:
                    if self.call('GetRecordStatus' if kind == 'record' else 'GetReplayBufferStatus')['outputActive']:
                        if kind == 'record':
                            self.stop_record()
                        else:
                            self.call(method)
                except Exception:
                    log.exception('Output stop during recovery: %s', kind)
            try:
                client.close()
            except Exception:
                if client.process.poll() is None:
                    # Never create a second recorder while the old process still owns files.
                    raise
                if getattr(client, 'finalized', False):
                    log.warning('Old recorder stalled in teardown after closing its files; replaced it')
                else:
                    log.exception('Old recorder exited during recovery')
            self.rpc = None
        self.recording = self.replay = False
        self.replay_started = None
        self.announced_active = {'record': False, 'replay': False}
        self.state.emit({'connected': False})
        if self.continuous is not None:
            self.continuous.close()
            self.drain_continuous()
            self.continuous = None
        if self.pending_replay:
            self.error.emit('A replay save was interrupted by the display/session change. Check _Unsorted and _ReplayCache for recoverable files.')
        self.expected_stops.clear()

    def recover_capture(self, reason):
        self.retire_for_recovery(reason)
        if self.recovery_intent is None or self.shutting_down:
            return
        intent = self.recovery_intent
        # One attempt per Windows event. A failure stays stopped instead of retrying forever.
        self.recovery_intent = None
        self.connect_engine()
        if self.shutting_down:
            return
        if intent['replay']:
            self.handle('toggle_replay', None)
        if intent['record'] and not self.shutting_down:
            self.handle('toggle_record', None)
        self.notify('Capture recovered', 'A fresh session started. Footage across sleep/lock/display changes is not continuous.' if any(intent.values()) else 'Recorder devices reconnected.')

    def apply_audio_devices(self, data=None, only=('desktop_device', 'mic_device')):
        proposed = {key: (data or self.settings).get(key, self.settings[key])
                    for key in ('desktop_device', 'mic_device')}
        if not all(isinstance(value, str) and value for value in proposed.values()):
            raise ValueError('Choose valid audio devices.')
        if self.rpc:
            sources = []
            unavailable = []
            for key, name, mask in (('desktop_device', DESKTOP, 3), ('mic_device', MIC, 5)):
                if key not in only:
                    continue
                device = proposed[key]
                devices = self.call('GetInputPropertiesListPropertyItems', inputName=name,
                                    propertyName='device_id')['propertyItems']
                if device != 'default' and not any(d['itemValue'] == device and d.get('itemEnabled', True) for d in devices):
                    detail = f'{name}: the selected device is disconnected. Reconnect it or choose System default in Audio settings.'
                    if data is not None:
                        raise ValueError(detail)
                    unavailable.append(detail)
                    continue
                sources.append(dict(inputName=name, device_id=device, mixers=mask,
                                    volume=self.settings['mic_volume']/100 if name == MIC else 1.0,
                                    muted=bool(self.muted) if name == MIC else False))
            if sources:
                self.call('ReconnectAudioSources', sources=sources)
            self.meter_levels.clear()
            self.meters.emit({})
            for detail in unavailable:
                self.notify('Audio device unavailable', detail, 'error')
                self.message.emit(detail)
        self.settings.update(proposed)
        atomic_json(SETTINGS, self.settings)
        if data is not None:
            self.applied.emit(copy.deepcopy(self.settings))
        if self.rpc:
            self.read_devices()
            self.message.emit('Available audio devices reconnected. Video capture continues; a brief audio gap during endpoint switching is expected.')
        else:
            self.message.emit('Audio device choices saved for the next capture session.')

    def handle(self, command, data):
        if self.shutting_down and command != "shutdown":
            return
        if command == 'suspend_capture':
            self.system_suspended = True
            self.retire_for_recovery(str(data))
            if self.recovery_intent and any(self.recovery_intent.values()):
                self.notify('Capture paused', str(data) + '. Capture will restart in a fresh session after unlock/resume.', 'error')
            return
        if command == 'recover_capture':
            self.system_suspended = False
            try:
                self.recover_capture(str(data or 'Display resumed'))
            except Exception:
                self.notify('Capture recovery failed', 'Capture needs attention. Check the log and restart the engine.', 'error')
                raise
            return
        if self.system_suspended and command in ('connect', 'toggle_replay', 'toggle_record', 'save_replay'):
            self.message.emit('Capture is paused until Windows resumes and the session is unlocked.')
            return
        if command == "connect":
            self.connect_engine()
        elif command == 'apply_audio':
            self.apply_audio_devices(data)
        elif command == 'audio_devices_changed':
            if self.rpc and not self.system_suspended:
                changed = data or {'inputs': True, 'outputs': True}
                # OBS's WASAPI sources already follow the Windows default endpoint;
                # rebuilding them only adds audio gaps. Pinned devices need a new client.
                keys = tuple(key for key, side in (('desktop_device', 'outputs'), ('mic_device', 'inputs'))
                             if changed.get(side) and self.settings[key] != 'default')
                if keys:
                    self.apply_audio_devices(only=keys)
                else:
                    log.info('Audio endpoints changed (%s); default-device sources follow Windows without a rebuild',
                             ', '.join(side for side in ('inputs', 'outputs') if changed.get(side)) or 'defaults')
        elif command == "toggle_replay":
            self.replay = self.call("GetReplayBufferStatus")["outputActive"]
            if self.replay and self.pending_replay:
                raise ValueError("Wait for the replay save to finish before stopping its buffer.")
            if not self.replay and self.settings.get("replay_mode") == "continuous":
                self.prepare_continuous()
            if self.replay:
                self.expected_stops.add('replay')
            try:
                self.call("StopReplayBuffer" if self.replay else "StartReplayBuffer")
            except Exception:
                self.expected_stops.discard('replay')
                raise
            self.replay_started = None if self.replay else time.monotonic()
            self.replay = not self.replay
            self.poll()
        elif command == "save_replay":
            if self.pending_replay:
                self.message.emit("A replay is already saving. Wait for its confirmation.")
                return
            self.pending_replay = self.context(replay=True)
            self.journal()
            try:
                self.call("SaveReplayBuffer")
            except Exception:
                self.pending_replay = None
                self.journal()
                raise
            self.message.emit("Saving replay...")
        elif command == "toggle_record":
            self.recording = self.call("GetRecordStatus")["outputActive"]
            if self.recording:
                self.stop_record()
            else:
                self.record_context = self.context()
                self.journal()
                try:
                    self.call("StartRecord")
                except Exception:
                    self.record_context = None
                    self.journal()
                    raise
                self.recording = True
            self.poll()
        elif command == "mic":
            mode, volume, pressed = data
            changed = mode != self.settings["mic_mode"] or volume != self.settings["mic_volume"]
            self.settings.update(mic_mode=mode, mic_volume=volume)
            if self.rpc:
                self.set_mic(mode == "Muted" or (mode == "Push to talk" and not pressed))
                if changed:
                    self.call("SetInputVolume", inputName=MIC, inputVolumeMul=volume / 100)
            if changed:
                atomic_json(SETTINGS, self.settings)
        elif command == "ui_theme":
            theme = str(data.get("theme", "dark") if isinstance(data, dict) else data or "dark")
            tint = int(data.get("tint", 46) if isinstance(data, dict) else self.settings.get("glass_tint", 46))
            if not 25 <= tint <= 85:
                raise ValueError("Glass tint must be between 25 and 85 percent.")
            if theme not in ("dark", "glass"):
                raise ValueError("Choose a supported appearance.")
            self.settings.update(ui_theme=theme, glass_tint=tint)
            atomic_json(SETTINGS, self.settings)
            self.message.emit("Appearance saved as " + ("Frosted glass." if theme == "glass" else "Classic dark."))
        elif command == "apply":
            validate(data)
            if self.rpc:
                if self.call("GetRecordStatus")["outputActive"] or self.call("GetReplayBufferStatus")["outputActive"]:
                    raise ValueError("Stop recording and replay before applying capture settings.")
            if self.pending_replay or self.archive_retry:
                raise ValueError("Wait for the pending clip save before applying settings.")
            atomic_json(SETTINGS, data)
            self.settings = copy.deepcopy(data)
            self.catalog.custom = self.settings["games"]
            self.applied.emit(copy.deepcopy(self.settings))
            if self.rpc:
                old = self.rpc
                self.rpc = None
                self.state.emit({"connected": False})
                try:
                    old.close()
                except Exception:
                    if old.process.poll() is None:
                        self.retiring_clients.append(old)
                        raise
                    self.message.emit("Settings saved. The inactive old engine exited unexpectedly; starting a fresh engine.")
            self.message.emit("Settings saved. Reconnecting the recorder...")
            self.connect_engine()
        elif command == "map_game":
            path, name = data
            self.settings["games"][path.casefold()] = name
            self.catalog.custom = self.settings["games"]
            atomic_json(SETTINGS, self.settings)
            self.message.emit(f"Future clips from this application will use {name}.")
        elif command == "refresh_devices":
            self.read_devices()
        elif command == "shutdown":
            self.begin_shutdown()
            self.expected_stops.update(("record", "replay"))
            if self.rpc:
                client = self.rpc
                if not client.closed:
                    # A failed stop must not skip the other output or host cleanup.
                    try:
                        if self.call("GetRecordStatus")["outputActive"]:
                            self.stop_record()
                    except Exception:
                        log.exception("Recording stop failed; continuing native shutdown")
                    deadline = min(time.monotonic() + 12, self.shutdown_started + 12)
                    while self.pending_replay and time.monotonic() < deadline:
                        try:
                            client.pump()
                        except Exception:
                            break
                        self.drain_continuous()
                        self.msleep(30)
                    try:
                        if self.call("GetReplayBufferStatus")["outputActive"]:
                            self.call("StopReplayBuffer")
                    except Exception:
                        log.exception("Replay stop failed; continuing native shutdown")
                try:
                    client.close()
                except Exception:
                    if client.process.poll() is None:
                        raise
                    log.exception("Native host exited without a clean shutdown reply")
                if getattr(client, 'forced', False) and self.continuous is not None:
                    self.continuous.abort()
                    self.message.emit('The recorder stalled while closing. Unfinished files and replay cache have been retained in _Unsorted.')
                self.rpc = None
            # Clients retired after a connection failure also belong to this app.
            for client in list(self.retiring_clients):
                client.disconnect()
                self.retiring_clients.remove(client)
            if self.continuous is not None:
                self.continuous.close()
                self.drain_continuous()
                self.continuous = None
            # Retry sorting only after native file handles and replay jobs finish.
            self.finish_shutdown()
