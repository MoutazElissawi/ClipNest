import os
import json
import threading
import time
from pathlib import Path
from unittest.mock import Mock
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaPlayer
from clipnest import gallery as module
from test_editor import media


def app():
    return QApplication.instance() or QApplication([])


def wait_for(application, condition, seconds=10):
    end = time.monotonic()+seconds
    while not condition() and time.monotonic() < end:
        application.processEvents()
        time.sleep(.01)
    assert condition()


def test_recent_scan_is_global_newest_first_and_excludes_in_progress(tmp_path):
    for folder, name, timestamp in [('A','old.mkv',10), ('Z','new.mp4',90), ('B','middle.mkv',50),
                                    ('_Unsorted','active.mkv',100), ('_ReplayCache','seg.mkv',200),
                                    ('.clipnest-export-x','partial.mp4',300)]:
        target = tmp_path/folder/name
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(b'video')
        os.utime(target, (timestamp,timestamp))
    result, errors = module.recent_clips(tmp_path, threading.Event(), limit=2)
    assert [c['name'] for c in result] == ['new.mp4','middle.mkv']
    assert not errors
    cancel = threading.Event(); cancel.set()
    assert module.recent_clips(tmp_path, cancel)[0] == []


def test_gallery_loads_previous_session_and_real_thumbnail(media, tmp_path, monkeypatch):
    application = app()
    monkeypatch.setattr(module, 'DATA', tmp_path)
    monkeypatch.setattr(module, 'gallery_tools', lambda: ('ffmpeg','ffprobe'))
    view = module.RecentGallery(Path(media['path']).parent)
    view.refresh()
    wait_for(application, lambda: view.worker is None)
    assert view.list.count() == 1
    clip = view.clips[0]
    assert abs(clip['duration']-4) < .1
    assert clip['width'] == 320 and Path(clip['thumbnail']).is_file()
    opened = []
    view.opened.connect(lambda clips,index: opened.append((clips[index]['path'],index)))
    view.open_item(view.list.item(0))
    assert opened == [(media['path'],0)]
    view.stop()


def test_tools_reuse_editors_chosen_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'DATA', tmp_path)
    (tmp_path/'editor.json').write_text(json.dumps({'ffmpeg_folder':'custom/bin'}))
    resolve = Mock(return_value=('ffmpeg','ffprobe'))
    monkeypatch.setattr(module, 'tools_path', resolve)
    assert module.gallery_tools() == ('ffmpeg','ffprobe')
    resolve.assert_called_once_with('custom/bin')


def test_player_loads_frame_paused_navigation_mute_edit_and_close(media):
    application = app()
    player = module.QuickPlayer()
    # Headless Linux has no audio device; verify UI controls without an audio backend.
    player.player.setAudioOutput(None)
    frames = []
    player.video_sink.videoFrameChanged.connect(lambda f: frames.append(f.isValid()))
    clip = dict(path=media['path'],name='test.mkv',folder='Game',size=1234,duration=4,width=320,height=240)
    player.open_clips([clip, dict(clip, name='second.mkv')], 0)
    wait_for(application, lambda: player.player.duration() > 0 and any(frames) and not player.video.display.isNull())
    assert player.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
    assert not player.previous.isEnabled() and player.next.isEnabled()
    player.open_index(1)
    assert player.previous.isEnabled() and not player.next.isEnabled()
    player.toggle_mute(); assert player.audio.isMuted()
    player.volume.setValue(30); assert abs(player.audio.volume()-.3) < .01
    edits = []
    player.edit_requested.connect(edits.append)
    player.edit()
    assert edits == [media['path']]
    player.close()
    assert player.player.source().isEmpty()


def test_gallery_refresh_cancels_obsolete_scan(tmp_path, monkeypatch):
    application = app()
    view = module.RecentGallery(tmp_path)
    view.refresh()
    view.refresh()
    wait_for(application, lambda: view.worker is None)
    assert not view.pending
    view.stop()
    view.refresh()
    assert view.worker is None
