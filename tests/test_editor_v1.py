import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import threading
from unittest.mock import Mock
import pytest
from PySide6.QtCore import Qt, QMimeData, QUrl, QPointF, QEventLoop, QTimer
from PySide6.QtGui import QImage, QColor, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication
from clipnest.preview import VideoCanvas, dropped_clip, filtered_image
from clipnest.editor_assets import waveform, scan_clips, thumbnail
from clipnest.media import Edit, export_clip, probe, export_args
from test_editor import media, audio_samples, amplitude


def app():
    return QApplication.instance() or QApplication([])


def test_local_single_video_drop_loads_editor_and_rejects_other_payloads(tmp_path, monkeypatch):
    application = app()
    from clipnest import editor as module
    monkeypatch.setattr(module, 'DATA', tmp_path)
    opened = []
    monkeypatch.setattr(module.Editor, 'open_clip', lambda self, path: opened.append(path))
    editor = module.Editor()
    video = tmp_path/'clip with spaces.MKV'
    video.write_bytes(b'placeholder')
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(video))])
    assert dropped_clip(mime) == str(video)
    enter = QDragEnterEvent(editor.video.rect().center(), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    editor.video.dragEnterEvent(enter)
    assert enter.isAccepted()
    drop = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    editor.video.dropEvent(drop)
    assert drop.isAccepted() and opened == [str(video)]
    for urls in ([QUrl('https://example.com/movie.mp4')], [QUrl.fromLocalFile(str(tmp_path))],
                 [QUrl.fromLocalFile(str(video))]*2, [QUrl.fromLocalFile(str(tmp_path/'missing.mp4'))]):
        mime.setUrls(urls)
        assert dropped_clip(mime) is None
    editor.close()


def test_live_crop_colors_reset_and_source_toggle():
    application = app()
    original = QImage(320, 240, QImage.Format.Format_RGB32)
    original.fill(QColor(180, 60, 20))
    canvas = VideoCanvas()
    canvas.set_image(original)
    canvas.source_size = (320, 240)
    canvas.crop = (20, 10, 200, 180)
    canvas.colors = (.1, 1., 0.)
    canvas.refresh()
    pixel = canvas.display.pixelColor(10, 10)
    assert pixel.red() == pixel.green() == pixel.blue()
    assert abs(canvas.display.width()/canvas.display.height()-200/180) < .01
    assert original.pixelColor(10, 10) == QColor(180, 60, 20)
    canvas.show_edits = False
    canvas.refresh()
    assert canvas.display.pixelColor(10, 10) == QColor(180, 60, 20)
    assert abs(canvas.display.width()/canvas.display.height()-4/3) < .01


def test_actual_remix_combines_isolated_tracks_without_doubling(media, tmp_path):
    target = tmp_path/'remixed.mkv'
    edit = Edit(.5, 2.5, audio=[(2, 'Desktop', .5), (3, 'Microphone', .25)], remix=True)
    export_clip(media, edit, 'ffmpeg', target)
    info = probe(target, 'ffprobe')
    assert len(info['audio']) == 1
    assert info['audio'][0]['tags']['title'] == 'Remix'
    samples = audio_samples(target, 0)
    assert .05 < amplitude(samples, 440) < .075
    assert .022 < amplitude(samples, 880) < .04
    edit.audio.insert(0, (1, 'Mix', 1))
    with pytest.raises(ValueError, match='doubled'):
        export_args(media, edit, 'ffmpeg', tmp_path/'bad.mkv')


def test_waveform_thumbnail_cache_and_scan(media, tmp_path):
    cancel = threading.Event()
    peaks = waveform(media, 2, 'ffmpeg', cancel, 80)
    assert len(peaks) == 80 and max(peaks) == 1 and min(peaks) > .8
    image = thumbnail(media['path'], 'ffmpeg', tmp_path/'thumbs', cancel)
    assert not QImage(image).isNull()
    assert thumbnail(media['path'], 'not-a-program', tmp_path/'thumbs', cancel) == image
    root = tmp_path/'clips'
    (root/'Game').mkdir(parents=True)
    (root/'Game'/'one.mp4').write_bytes(b'clip')
    (root/'_ReplayCache').mkdir()
    (root/'_ReplayCache'/'active.mkv').write_bytes(b'not a completed clip')
    (root/'.clipnest-export-partial').mkdir()
    (root/'.clipnest-export-partial'/'partial.mp4').write_bytes(b'partial')
    clips, limited, errors = scan_clips(root, cancel)
    assert len(clips) == 1 and clips[0]['folder'] == 'Game'
    assert not limited and not errors
    cancel.set()
    with pytest.raises(ValueError, match='cancelled'):
        waveform(media, 2, 'ffmpeg', cancel)


def test_browser_search_sort_and_prior_session_files(tmp_path):
    application = app()
    from clipnest.clip_browser import ClipBrowser
    folder = tmp_path/'A game'
    folder.mkdir()
    (folder/'older.mkv').write_bytes(b'longer')
    (folder/'newer.mp4').write_bytes(b'x')
    os.utime(folder/'older.mkv', (1000, 1000))
    browser = ClipBrowser(tmp_path, None, tmp_path/'cache')
    loop = QEventLoop()
    browser.workers[0].finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    application.processEvents()
    assert browser.list.count() == 2
    assert 'newer.mp4' in browser.list.item(0).text()
    browser.search.setText('older')
    assert browser.list.count() == 1
    browser.search.setText('A game')
    browser.sort.setCurrentIndex(3)
    assert 'older.mkv' in browser.list.item(0).text()
    browser.list.setCurrentRow(0)
    browser.open_selected()
    assert browser.selected_path == str(folder/'older.mkv')


def test_frame_controls_precise_trim_and_remix_ui(media, tmp_path, monkeypatch):
    application = app()
    from clipnest import editor as module
    monkeypatch.setattr(module, 'DATA', tmp_path)
    editor = module.Editor()
    editor.loaded((media, (['CPU H.264'], {})))
    original_player = editor.player
    editor.player = Mock()
    editor.player.position.return_value = 1000
    editor.step_frame(1)
    editor.player.setPosition.assert_called_with(1033)
    editor.remix.setChecked(True)
    assert not editor.track_rows[0][2].isChecked()
    editor.start.setValue(.733)
    assert editor.current_edit().start == .733
    assert editor.wave.start == .733
    assert editor.current_edit().remix
    assert len(editor.current_edit().audio) == 2
    editor.player = original_player
    editor.close()


def test_export_preview_renders_selection_filters_and_remix_without_changing_preset(media, tmp_path, monkeypatch):
    application = app()
    from clipnest import editor as module
    monkeypatch.setattr(module, 'DATA', tmp_path)
    editor = module.Editor()
    editor.loaded((media, (['CPU H.264'], {})))
    editor.crop = (20, 10, 200, 180)
    editor.start.setValue(.5)
    editor.end.setValue(1.5)
    editor.remix.setChecked(True)
    editor.bitrate.setValue(25000)
    results = []
    errors = []
    editor.show_export_preview = results.append
    editor.error = errors.append
    editor.preview_export()
    loop = QEventLoop()
    editor.job.finished.connect(loop.quit)
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    application.processEvents()
    assert not errors and len(results) == 1
    rendered = probe(results[0], 'ffprobe')
    assert rendered['video']['width'] == 200 and rendered['video']['height'] == 180
    assert len(rendered['audio']) == 1 and abs(rendered['duration']-1) < .06
    assert editor.bitrate.value() == 25000 and editor.prefs['last_export']['bitrate'] == 25000
    editor.close()
    assert not Path(results[0]).exists()
