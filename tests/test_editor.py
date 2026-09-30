import array
import math
from pathlib import Path
import shutil
import subprocess
import threading

import pytest
from clipnest.catalog import Catalog
from clipnest.media import Edit, export_args, export_clip, probe, available_encoders


def test_catalog_separator_normalization_and_specific_roots():
    catalog = Catalog({r'C:\Games\Manual\play.exe': 'Manual override'})
    catalog.roots = [('C:/Steam/common', 'Broad'), (r'c:\steam\common\A Game', 'A Game')]
    assert catalog.classify('c:/games/manual/play.exe') == 'Manual override'
    assert catalog.classify(r'C:\Steam\common\A Game\bin/game.exe') == 'A Game'
    assert catalog.classify('c:/steam/common-other/game.exe') == 'Desktop'
    assert catalog.classify('c:/steam/common/A Game 2/game.exe') == 'Broad'


@pytest.fixture(scope='module')
def media(tmp_path_factory):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('Real media tests require ffmpeg and ffprobe')
    path = tmp_path_factory.mktemp('media') / 'three tracks.mkv'
    result = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=320x240:r=30:d=4',
        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=4',
        '-f', 'lavfi', '-i', 'sine=frequency=880:sample_rate=48000:duration=4',
        '-filter_complex', '[1:a][2:a]amix=inputs=2:normalize=0[m]',
        '-map', '0:v', '-map', '[m]', '-map', '1:a', '-map', '2:a',
        '-c:v', 'libx264', '-g', '120', '-c:a', 'pcm_s16le',
        '-metadata:s:a:0', 'title=Mix', '-metadata:s:a:1', 'title=Desktop',
        '-metadata:s:a:2', 'title=Microphone', str(path)], capture_output=True)
    assert result.returncode == 0, result.stderr
    return probe(path, 'ffprobe')


def test_probe_three_tracks_and_runtime_encoder_probe(media):
    assert [s['tags']['title'] for s in media['audio']] == ['Mix', 'Desktop', 'Microphone']
    labels, failures = available_encoders('ffmpeg')
    assert 'CPU H.264' in labels
    assert set(labels) | set(failures) == {'NVIDIA H.264', 'NVIDIA AV1', 'CPU H.264'}


def audio_samples(path, index):
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-map', f'0:a:{index}',
        '-t', '1', '-f', 'f32le', '-ac', '1', '-ar', '48000', '-'], capture_output=True, check=True)
    a = array.array('f')
    a.frombytes(r.stdout)
    return a


def amplitude(samples, frequency):
    samples = samples[4800:38400]
    return 2*abs(sum(v*complex(math.cos(2*math.pi*frequency*i/48000), math.sin(2*math.pi*frequency*i/48000)) for i, v in enumerate(samples)))/len(samples)


def test_real_nonkeyframe_trim_crop_tracks_and_gain(media, tmp_path):
    original = Path(media['path']).read_bytes()
    dest = tmp_path / 'edited.mkv'
    edit = Edit(.7, 2.3, audio=[(2, 'Desktop', .5), (3, 'Microphone', .25)], crop=(20, 10, 200, 180))
    progress = []
    export_clip(media, edit, 'ffmpeg', dest, progress=progress.append)
    result = probe(dest, 'ffprobe')
    assert result['video']['width'] == 200 and result['video']['height'] == 180
    assert abs(result['duration']-1.6) < .06
    assert [s['tags']['title'] for s in result['audio']] == ['Desktop', 'Microphone']
    frames = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames',
        '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0', str(dest)], capture_output=True, text=True, check=True)
    assert int(frames.stdout.strip()) == 48
    desktop, mic = audio_samples(dest, 0), audio_samples(dest, 1)
    assert .05 < amplitude(desktop, 440) < .075
    assert amplitude(desktop, 880) < .002
    assert .022 < amplitude(mic, 880) < .04
    assert amplitude(mic, 440) < .002
    assert Path(media['path']).read_bytes() == original
    assert progress[-1] == 100
    assert not list(tmp_path.glob('.clipnest-export-*'))


def test_export_refuses_original_existing_and_invalid_trim(media, tmp_path):
    with pytest.raises(ValueError, match='exists'):
        export_clip(media, Edit(0, 1), 'ffmpeg', media['path'])
    target = tmp_path / 'keep.mkv'
    target.write_bytes(b'keep')
    with pytest.raises(ValueError, match='exists'):
        export_clip(media, Edit(0, 1), 'ffmpeg', target)
    assert target.read_bytes() == b'keep'
    for start, end in [(1, 1), (-1, 2), (0, 10), (float('nan'), 1)]:
        with pytest.raises(ValueError):
            export_args(media, Edit(start, end), 'ffmpeg', tmp_path/'new.mkv')


def test_cancel_failure_and_no_audio_leave_original_safe(media, tmp_path):
    target = tmp_path / 'cancelled.mkv'
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ValueError, match='cancelled'):
        export_clip(media, Edit(0, 3), 'ffmpeg', target, cancel)
    assert not target.exists()
    assert not list(tmp_path.glob('.clipnest-export-*'))
    bad = dict(media, path=str(tmp_path/'missing.mkv'))
    with pytest.raises(ValueError):
        export_clip(bad, Edit(0, 1), 'ffmpeg', target)
    assert not target.exists()
    export_clip(media, Edit(.1, .6), 'ffmpeg', tmp_path/'silent.mp4')
    assert probe(tmp_path/'silent.mp4', 'ffprobe')['audio'] == []


def test_invalid_crop_and_tracks(media, tmp_path):
    for crop in [(1, 0, 200, 200), (0, 0, 322, 240), (0, 0, 0, 0)]:
        with pytest.raises(ValueError, match='Crop'):
            export_args(media, Edit(0, 1, crop=crop), 'ffmpeg', tmp_path/'new.mkv')
    with pytest.raises(ValueError, match='audio'):
        export_args(media, Edit(0, 1, audio=[(8, 'missing', 1)]), 'ffmpeg', tmp_path/'new.mkv')


def test_first_exported_frame_is_at_requested_cut(media, tmp_path):
    target = tmp_path/'cut.mkv'
    export_clip(media, Edit(.7, 1.2, bitrate=20000), 'ffmpeg', target)
    def frame(path, start):
        r = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(start), '-i', str(path),
            '-frames:v', '1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'], capture_output=True, check=True)
        return r.stdout
    source_frame, result_frame = frame(media['path'], .7), frame(target, 0)
    assert len(source_frame) == len(result_frame) == 320*240*3
    assert sum(abs(a-b) for a,b in zip(source_frame, result_frame))/len(source_frame) < 5


def test_publish_race_never_overwrites_file(media, tmp_path, monkeypatch):
    import clipnest.media as module
    actual_link = module.os.link
    target = tmp_path/'race.mkv'
    def competing_link(source, destination):
        Path(destination).write_bytes(b'another process created this')
        actual_link(source, destination)
    monkeypatch.setattr(module.os, 'link', competing_link)
    with pytest.raises(ValueError, match='publish'):
        export_clip(media, Edit(.1, .3), 'ffmpeg', target)
    assert target.read_bytes() == b'another process created this'
    assert not list(tmp_path.glob('.clipnest-export-*'))


def test_editor_async_load_and_solo_controls(media, tmp_path, monkeypatch):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QEventLoop, QTimer
    import clipnest.editor as module
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(module, 'DATA', tmp_path)
    monkeypatch.setattr(module, 'available_encoders', lambda _: (['CPU H.264'], {}))
    editor = module.Editor()
    errors = []
    editor.error = errors.append
    editor.open_clip(media['path'])
    assert editor.busy() and not editor.export_button.isEnabled()
    assert not editor.can_close()
    assert errors.pop().startswith('Wait for')
    loop = QEventLoop()
    editor.job.finished.connect(loop.quit)
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    app.processEvents()
    assert not editor.busy()
    assert not errors
    assert editor.tracks.rowCount() == 3
    assert editor.encoder.currentText() == 'CPU H.264'
    assert editor.export_button.isEnabled()
    assert editor.start.value() == 0 and editor.end.value() == 4
    editor.track_rows[0][3].setValue(50)
    assert abs(editor.audio_output.volume()-.5) < .001
    editor.start.setValue(.7)
    editor.end.setValue(2.3)
    assert editor.start.singleStep() == .1
    assert editor.can_close()
    editor.close()


def test_confirmed_export_replaces_only_after_success(media, tmp_path):
    from clipnest.media import file_identity
    target = tmp_path/'replace.mkv'
    target.write_bytes(b'previous export')
    identity = file_identity(target)
    export_clip(media, Edit(.3, .8), 'ffmpeg', target, overwrite=True, expected_target=identity)
    assert probe(target, 'ffprobe')['video']['codec_name'] == 'h264'
    target.write_bytes(b'keep on cancellation')
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ValueError, match='cancelled'):
        export_clip(media, Edit(0, 1), 'ffmpeg', target, cancel, overwrite=True)
    assert target.read_bytes() == b'keep on cancellation'
    with pytest.raises(ValueError):
        export_clip(dict(media,path=str(tmp_path/'missing.mkv')), Edit(0, 1), 'ffmpeg', target, overwrite=True)
    assert target.read_bytes() == b'keep on cancellation'


def test_overwrite_protects_source_aliases_and_changed_destination(media, tmp_path):
    import os
    from clipnest.media import file_identity
    with pytest.raises(ValueError, match='original'):
        export_clip(media, Edit(0, 1), 'ffmpeg', media['path'], overwrite=True)
    alias = tmp_path/'alias.mkv'
    os.link(media['path'], alias)
    with pytest.raises(ValueError, match='original'):
        export_clip(media, Edit(0, 1), 'ffmpeg', alias, overwrite=True)
    target=tmp_path/'changed.mkv'
    target.write_bytes(b'approved')
    identity=file_identity(target)
    target.write_bytes(b'newer file')
    with pytest.raises(ValueError, match='changed'):
        export_clip(media, Edit(0,1), 'ffmpeg', target, overwrite=True, expected_target=identity)
    assert target.read_bytes()==b'newer file'
