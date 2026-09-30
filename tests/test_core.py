import base64
import copy
import hashlib
import json
from pathlib import Path
import time

import pytest

from clipnest.catalog import Catalog, archive_file, safe_folder
from clipnest.config import validate, ENCODERS
from clipnest.hotkeys import parse_hotkey
from clipnest.native_client import NativeError as ObsError
from clipnest import engine as engine_module
from clipnest.engine import Engine


@pytest.fixture
def settings(tmp_path):
    return dict(output=str(tmp_path / "clips"), replay_seconds=90, width=1920, height=1080,
                fps=60, bitrate=20000, encoder="NVIDIA H.264", mic_device="default",
                desktop_device="default", monitor_property="monitor_id", monitor_value=None,
                mic_mode="Always on", mic_volume=100, ptt_key="F8", replay_key="Ctrl+Shift+F10",
                record_key="Ctrl+Shift+F9", port=4457, password="test-password", games={})


@pytest.fixture
def engine(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(engine_module, "JOURNAL", tmp_path / "pending.json")
    monkeypatch.setattr(engine_module, "SETTINGS", tmp_path / "settings.json")
    instance = Engine(settings)
    instance.catalog.poll = lambda: {"category": "Game A"}
    return instance


class Recorder:
    def __init__(self):
        self.record = False
        self.replay = False
        self.calls = []
        self.output_path = None

    def call(self, request, **args):
        self.calls.append((request, args))
        if request == "GetRecordStatus":
            return {"outputActive": self.record, "outputTimecode": "00:00:10.000"}
        if request == "GetReplayBufferStatus":
            return {"outputActive": self.replay}
        if request == "StartReplayBuffer":
            self.replay = True
        if request == "StopReplayBuffer":
            self.replay = False
        if request == "StartRecord":
            self.record = True
        if request == "StopRecord":
            self.record = False
            return {"outputPath": self.output_path}
        return {}


def test_simultaneous_replay_and_recording_are_independent(engine, tmp_path):
    recorder = Recorder()
    engine.rpc = recorder
    engine.handle("toggle_replay", None)
    engine.handle("toggle_record", None)
    assert recorder.record and recorder.replay
    engine.handle("save_replay", None)
    assert recorder.record and recorder.replay
    assert engine.pending_replay["category"] == "Game A"
    source = Path(engine.settings["output"]) / "_Unsorted/record.mkv"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"stand-in recording bytes")
    recorder.output_path = str(source)
    engine.handle("toggle_record", None)
    assert not recorder.record and recorder.replay
    assert len(list((Path(engine.settings["output"]) / "Game A").glob("*.mkv"))) == 1
    assert engine.pending_replay is not None


def test_replay_uses_category_at_save_request_not_later_focus(engine):
    engine.rpc = Recorder()
    engine.handle("save_replay", None)
    engine.catalog.poll = lambda: {"category": "Desktop"}
    source = Path(engine.settings["output"]) / "_Unsorted/replay.mkv"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"replay")
    engine.on_event("ReplayBufferSaved", {"savedReplayPath": str(source)})
    assert (source.parents[1] / "Game A").exists()
    assert engine.pending_replay is None


def test_replay_failure_clears_pending_journal(engine):
    class Failed:
        def call(self, *_args, **_kwargs):
            raise ObsError("buffer not running")
    engine.rpc = Failed()
    with pytest.raises(ObsError):
        engine.handle("save_replay", None)
    assert engine.pending_replay is None
    assert json.loads(engine_module.JOURNAL.read_text())["replay"] is None


def test_duplicate_save_does_not_issue_second_rpc(engine):
    engine.rpc = Recorder()
    engine.handle("save_replay", None)
    engine.handle("save_replay", None)
    assert sum(name == "SaveReplayBuffer" for name, _ in engine.rpc.calls) == 1


def test_record_category_is_pinned_at_start(engine):
    engine.rpc = Recorder()
    engine.handle("toggle_record", None)
    engine.catalog.poll = lambda: {"category": "Game B"}
    source = Path(engine.settings["output"]) / "_Unsorted/record.mkv"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"recording")
    engine.rpc.output_path = str(source)
    engine.handle("toggle_record", None)
    assert (source.parents[1] / "Game A").exists()
    assert not (source.parents[1] / "Game B").exists()


def test_apply_rejected_while_output_active(engine):
    engine.rpc = Recorder()
    engine.rpc.replay = True
    with pytest.raises(ValueError, match="Stop recording"):
        engine.handle("apply", engine.settings)
    assert engine.rpc.replay


def test_ptt_and_mute_transitions(engine):
    engine.rpc = Recorder()
    for mode, pressed, expected in [("Push to talk", False, True), ("Push to talk", True, False),
                                     ("Push to talk", False, True), ("Muted", True, True),
                                     ("Always on", False, False)]:
        engine.handle("mic", (mode, 80, pressed))
        assert engine.muted == expected
    volumes = [args for name, args in engine.rpc.calls if name == "SetInputVolume"]
    assert all(v["inputVolumeMul"] == .8 for v in volumes)


@pytest.mark.parametrize("name,expected", [("CON", "Game_CON"), ("../Hi:Game", "_Hi_Game"),
    ("", "Desktop"), ("  Rocket League. ", "Rocket League"), ("NUL.txt", "Game_NUL.txt"),
    ("_Unsorted", "Game__Unsorted")])
def test_safe_folders(name, expected):
    assert safe_folder(name) == expected


def test_archive_never_moves_unrelated_file(tmp_path):
    source = tmp_path / "personal.mkv"
    source.write_bytes(b"keep")
    with pytest.raises(ValueError, match="outside"):
        archive_file(source, tmp_path / "clips", "Desktop", "Replay")
    assert source.read_bytes() == b"keep"


def test_archive_preserves_bytes_and_is_idempotent_at_controller(engine):
    source = Path(engine.settings["output"]) / "_Unsorted/replay.mkv"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"original audio and video data")
    ctx = engine.context()
    engine.finish_file(str(source), ctx, "Replay")
    engine.finish_file(str(source), ctx, "Replay")
    clips = list(source.parents[1].glob("Game A/*.mkv"))
    assert len(clips) == 1
    assert clips[0].read_bytes() == b"original audio and video data"


def test_locked_file_retries_without_deleting(engine, monkeypatch):
    source = Path(engine.settings["output"]) / "_Unsorted/replay.mkv"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"safe")
    actual = engine_module.archive_file
    def locked(*args):
        raise PermissionError("busy")
    monkeypatch.setattr(engine_module, "archive_file", locked)
    engine.finish_file(str(source), engine.context(), "Replay")
    assert source.exists() and len(engine.archive_retry) == 1
    monkeypatch.setattr(engine_module, "archive_file", actual)
    path, ctx, kind, attempt = engine.archive_retry.pop()
    engine.finish_file(path, ctx, kind, attempt)
    assert not source.exists()


def test_game_recognition_respects_path_boundaries():
    catalog = Catalog({"c:\\custom\\play.exe": "Custom"})
    catalog.roots = [("c:\\steam\\common\\mygame", "My Game")]
    assert catalog.classify(r"C:\Steam\common\MyGame\bin\game.exe") == "My Game"
    assert catalog.classify(r"C:\Steam\common\MyGame2\game.exe") == "Desktop"
    assert catalog.classify(r"C:\Games\helldivers2.exe") == "Helldivers 2"
    assert catalog.classify(r"C:\custom\play.exe") == "Custom"


def test_bad_resolution_rejected(settings):
    settings["width"] = 1919
    with pytest.raises(ValueError):
        validate(settings)


def test_hotkey_parsing():
    assert parse_hotkey("Ctrl+Shift+F10") == (6, 0x79)
    assert parse_hotkey("F8") == (0, 0x77)
    with pytest.raises(ValueError):
        parse_hotkey("Ctrl+NotAKey")


def test_source_routing_and_monitor_are_explicit(engine):
    calls = []
    def call(request, **args):
        calls.append((request, args))
        replies = {
            "GetSceneList": {"scenes": [{"sceneName": "Capture"}]},
            "GetInputKindList": {"inputKinds": ["monitor_capture", "wasapi_output_capture", "wasapi_input_capture"]},
            "GetInputList": {"inputs": []},
            "GetSpecialInputs": {"desktop1": "Desktop Audio", "mic1": "Mic/Aux"},
            "GetSceneItemId": {"sceneItemId": 1},
            "GetInputPropertiesListPropertyItems": {"propertyItems": [
                {"itemName": "Select display", "itemValue": "invalid", "itemEnabled": False},
                {"itemName": "Monitor 1", "itemValue": "DISPLAY1", "itemEnabled": True}]}}
        return replies.get(request, {})
    engine.call = call
    engine.setup_sources()
    routes = {args["inputName"]: args["inputAudioTracks"] for name, args in calls if name == "SetInputAudioTracks"}
    assert routes["CN Desktop"] == {str(i): i in (1, 2) for i in range(1, 7)}
    assert routes["CN Microphone"] == {str(i): i in (1, 3) for i in range(1, 7)}
    assert not any(routes["Desktop Audio"].values())
    screen = [args for name, args in calls if name == "SetInputSettings" and args["inputName"] == "CN Screen"]
    assert screen[0]["inputSettings"]["monitor_id"] == "DISPLAY1"


def test_apply_keeps_new_encoder_when_inactive_host_crashes(engine, settings):
    class Crashed(Recorder):
        class process:
            @staticmethod
            def poll(): return 1
        def close(self): raise ConnectionError('host crashed during shutdown')
    engine.rpc = Crashed()
    new = dict(settings, encoder='CPU H.264 (fallback)')
    connections = []
    engine.connect_engine = lambda: connections.append(engine.settings['encoder'])
    engine.handle('apply', new)
    assert connections == ['CPU H.264 (fallback)']
    assert json.loads(engine_module.SETTINGS.read_text())['encoder'] == new['encoder']


def test_apply_does_not_launch_over_a_still_running_host(engine, settings):
    class Hung(Recorder):
        class process:
            @staticmethod
            def poll(): return None
        def close(self): raise RuntimeError('host still running')
    old = engine.rpc = Hung()
    connections = []
    engine.connect_engine = lambda: connections.append(True)
    with pytest.raises(RuntimeError, match='still running'):
        engine.handle('apply', dict(settings, encoder='CPU H.264 (fallback)'))
    assert connections == []
    assert engine.retiring_clients == [old]
