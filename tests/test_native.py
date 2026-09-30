import ctypes as C
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import threading
import pytest

from clipnest.libobs import VideoInfo, AudioInfo, CallData, Vec2
from clipnest.native_host import NativeEngine
from clipnest.native_client import NativeClient, NativeError


def test_native_structure_layout_matches_pinned_headers():
    # Checked with a compiled C probe using the actual 32.2.2 header declarations.
    assert C.sizeof(VideoInfo) == 56
    assert C.sizeof(AudioInfo) == 8
    assert C.sizeof(CallData) == 32
    assert C.sizeof(Vec2) == 8
    assert VideoInfo.gpu_conversion.offset == 40
    assert VideoInfo.colorspace.offset == 44


class FakeLib:
    def __init__(self):
        self.calls = []
        self.next_id = 100
        self.active_outputs = set()
    @contextmanager
    def data(self, value): yield value
    def enumerate(self, function): return ["obs_nvenc_h264_tex", "ffmpeg_aac"]
    def __getattr__(self, name):
        def call(*args):
            self.calls.append((name, args))
            if name == "obs_output_active": return args[0] in self.active_outputs
            if name == "obs_output_start":
                self.active_outputs.add(args[0])
                return True
            if name == "obs_output_get_last_error": return b""
            self.next_id += 1
            return self.next_id
        return call


def native(tmp_path):
    n = NativeEngine(lambda *_: None)
    n.lib = FakeLib()
    n.started = True
    n.settings = {"encoder": "NVIDIA H.264", "bitrate": 20000, "replay_seconds": 90}
    n.staging = tmp_path
    n.scene = 50
    n.inputs["CN Screen"] = (51, "monitor_capture")
    return n


def test_both_outputs_share_encoders_with_three_distinct_audio_mixers(tmp_path):
    n = native(tmp_path)
    n.make_outputs()
    calls = n.lib.calls
    video = [args for name, args in calls if name == "obs_output_set_video_encoder"]
    assert len(video) == 2 and video[0][1] == video[1][1]
    audio = [args for name, args in calls if name == "obs_audio_encoder_create"]
    assert [args[3] for args in audio] == [0, 1, 2]
    assert [args[1] for args in audio] == [b"Mix", b"Desktop", b"Microphone"]
    bindings = [args for name, args in calls if name == "obs_output_set_audio_encoder"]
    assert len(bindings) == 6
    assert [b[1:] for b in bindings[:3]] == [b[1:] for b in bindings[3:]]
    before = len(calls)
    n.make_outputs()
    assert len(calls) == before


def test_native_replay_and_record_start_independently(tmp_path):
    n = native(tmp_path)
    n.start("replay")
    n.start("record")
    assert n.active("record") and n.active("replay")
    assert Path(n.record_path).parent == tmp_path
    assert Path(n.record_path).suffix == ".mkv"


def test_saving_inactive_replay_rejected(tmp_path):
    n = native(tmp_path)
    with pytest.raises(RuntimeError, match="Start replay"):
        n.call("SaveReplayBuffer", {})


def test_unknown_encoder_does_not_silently_fallback(tmp_path):
    n = native(tmp_path)
    n.settings["encoder"] = "NVIDIA AV1"
    with pytest.raises(RuntimeError, match="unavailable"):
        n.make_outputs()
    assert n.encoders == []


def test_stop_uses_completion_signal(tmp_path):
    n = native(tmp_path)
    n.start("record")
    def stop(output):
        n.lib.active_outputs.discard(output)
        n.stop_events["record"].set()
    n.lib.obs_output_stop = stop
    result = n.call("StopRecord", {})
    assert result["outputPath"] == n.record_path
    assert not n.active("record")


@pytest.fixture
def pipe_client(tmp_path, monkeypatch):
    import clipnest.native_client as transport
    monkeypatch.setattr(transport, "DATA", tmp_path)
    script = tmp_path / "fake_host.py"
    script.write_text('''import json,sys
for line in sys.stdin:
 r=json.loads(line)
 if r['method']=='Fail': print(json.dumps({'id':r['id'],'error':'expected failure'}),flush=True);continue
 if r['method']=='Echo': print(json.dumps({'event':'TestEvent','data':{'saved':True}}),flush=True)
 print(json.dumps({'id':r['id'],'result':r.get('args',{})}),flush=True)
 if r['method']=='Shutdown': break
''')
    events = []
    client = NativeClient({}, lambda *e: events.append(e), command=[sys.executable, '-u', str(script)])
    yield client, events
    client.close()


def test_real_child_pipe_transport_and_interleaved_event(pipe_client):
    client, events = pipe_client
    assert client.call("Echo", text="مرحبا") == {"text": "مرحبا"}
    assert events == [("TestEvent", {"saved": True})]


def test_remote_error_does_not_break_next_command(pipe_client):
    client, _ = pipe_client
    with pytest.raises(NativeError, match="expected failure"):
        client.call("Fail")
    assert client.call("Echo", n=2) == {"n": 2}


def test_graceful_close_stops_child(pipe_client):
    client, _ = pipe_client
    client.close()
    assert client.process.poll() == 0
    assert not client.reader.is_alive()


def test_disconnect_eof_stops_child(pipe_client):
    client, _ = pipe_client
    client.disconnect()
    assert client.process.poll() == 0


def test_no_obs_frontend_or_network_dependency_in_native_route():
    root = Path(__file__).parents[1]
    assert "websocket-client" not in (root / 'requirements.txt').read_text()
    for name in ('engine.py','native_client.py','native_host.py'):
        text = (root / 'clipnest' / name).read_text()
        assert 'obs64.exe' not in text
        assert 'ws://' not in text


def test_obs_paths_use_forward_slashes_for_module_name_parsing():
    from clipnest.libobs import obs_path
    path = obs_path(r'C:\Users\Name\engine\obs-plugins\64bit\obs-nvenc.dll')
    assert path.rsplit(b'/', 1)[-1] == b'obs-nvenc.dll'
    assert b'\\' not in path


def test_host_executable_is_beside_obs_helpers(tmp_path, monkeypatch):
    import types
    import clipnest.native_client as transport
    base, runtime = tmp_path / 'python', tmp_path / 'engine'
    base.mkdir()
    (base / 'python.exe').write_bytes(b'real interpreter')
    (base / 'python312.dll').write_bytes(b'python runtime')
    (base / 'vcruntime140.dll').write_bytes(b'python vc runtime')
    bins = runtime / 'bin/64bit'
    bins.mkdir(parents=True)
    (bins / 'vcruntime140.dll').write_bytes(b'existing OBS runtime')
    monkeypatch.setattr(transport, 'os', types.SimpleNamespace(name='nt', pathsep=';'))
    monkeypatch.setattr(transport, 'sys', types.SimpleNamespace(base_prefix=str(base)))
    monkeypatch.setattr(transport, 'ENGINE', runtime)
    env = {'PATH': 'previous'}
    cmd = transport.host_command(env)
    assert Path(cmd[0]).parent == bins
    assert Path(cmd[0]).read_bytes() == b'real interpreter'
    assert (bins / 'python312.dll').read_bytes() == b'python runtime'
    assert (bins / 'vcruntime140.dll').read_bytes() == b'existing OBS runtime'
    assert env['PYTHONHOME'] == str(base)
    assert Path(env['PYTHONPATH']).joinpath('clipnest/native_host.py').is_file()


def test_close_cleans_up_even_if_shutdown_reply_is_lost(pipe_client, monkeypatch):
    client, _ = pipe_client
    def failed(*args, **kwargs):
        raise ConnectionError('lost shutdown response')
    monkeypatch.setattr(client, 'call', failed)
    with pytest.raises(ConnectionError):
        client.close()
    assert client.closed
    assert client.process.poll() == 0


def test_capture_stays_on_until_both_outputs_stop(tmp_path):
    n = native(tmp_path)
    n.start('replay')
    n.start('record')
    def stop(output):
        n.lib.active_outputs.discard(output)
        kind = next(k for k, v in n.outputs.items() if v == output)
        n.stop_events[kind].set()
    n.lib.obs_output_stop = stop
    n.stop('record')
    assert n.capture_attached
    n.stop('replay')
    assert not n.capture_attached
    assert n.lib.calls[-1] == ('obs_set_output_source', (0, None))


def test_dxgi_failure_falls_back_before_output_start(tmp_path):
    n = native(tmp_path)
    n.capture_method = 1
    checks = iter([False, True])
    n.capture_ready = lambda: next(checks)
    notices = []
    n.emit = lambda *args: notices.append(args)
    n.start('replay')
    assert n.capture_method == 2
    assert n.active('replay')
    names = [name for name, args in n.lib.calls]
    assert names.index('obs_source_update') < names.index('obs_output_start')
    assert notices[0][0] == 'NativeNotice'


def test_failed_capture_does_not_start_output_and_releases_screen(tmp_path):
    n = native(tmp_path)
    n.capture_ready = lambda: False
    with pytest.raises(RuntimeError, match='Screen capture did not initialize'):
        n.start('record')
    assert not n.capture_attached
    assert not any(name == 'obs_output_start' for name, args in n.lib.calls)


def test_failed_second_output_keeps_first_capturing(tmp_path):
    n = native(tmp_path)
    n.start('replay')
    n.lib.obs_output_start = lambda output: False
    with pytest.raises(RuntimeError, match='Could not start record'):
        n.start('record')
    assert n.active('replay') and n.capture_attached


def test_unexpected_output_stop_releases_capture_on_poll(tmp_path):
    n = native(tmp_path)
    n.start('replay')
    n.lib.active_outputs.clear()
    status = n.call('GetRecordStatus', {})
    assert not status['captureAttached']


def test_select_scene_does_not_activate_capture(tmp_path):
    n = native(tmp_path)
    n.call('SetCurrentProgramScene', {})
    assert not n.capture_attached
    assert not any(name == 'obs_set_output_source' for name, args in n.lib.calls)


def test_native_audio_track_masks_match_mix_desktop_and_microphone(tmp_path):
    n = native(tmp_path)
    n.inputs['CN Desktop'] = (61, 'wasapi_output_capture')
    n.inputs['CN Microphone'] = (62, 'wasapi_input_capture')
    for name, tracks in [('CN Desktop', (1, 2)), ('CN Microphone', (1, 3))]:
        n.call('SetInputAudioTracks', dict(inputName=name, inputAudioTracks={str(i): i in tracks for i in range(1, 7)}))
    calls = [args for name, args in n.lib.calls if name == 'obs_source_set_audio_mixers']
    assert calls == [(61, 0b011), (62, 0b101)]


def test_continuous_replay_splits_without_stopping_outputs(tmp_path):
    n = native(tmp_path)
    n.settings['replay_mode'] = 'continuous'
    n.start('replay')
    n.start('record')
    assert n.active('record') and n.active('replay')
    before = len(n.lib.calls)
    n.call('SaveReplayBuffer', {})
    calls=n.lib.calls[before:]
    assert any(name=='procedure' and args[1]=='split_file' for name,args in calls)
    assert not any(name in ('obs_output_stop','obs_output_start','obs_set_output_source') for name,args in calls)
    assert n.active('record') and n.active('replay')
    assert n.segment_save_requested
    updates=[args[1] for name,args in n.lib.calls if name=='obs_output_update']
    assert any(v.get('split_file') and v.get('max_time_sec')==2 for v in updates)
