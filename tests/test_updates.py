import json
import subprocess
import time
from pathlib import Path
from unittest.mock import Mock
import pytest
from clipnest.replay import Segment, ContinuousReplay, concat_segments, segment_duration, segment_timing
from clipnest.catalog import archive_file
from clipnest.media import available_encoders


def test_application_names_replace_recording_kinds(tmp_path):
    for kind in ('Recording', 'Replay'):
        source = tmp_path/'_Unsorted'/f'{kind}.mkv'
        source.parent.mkdir(exist_ok=True)
        source.write_bytes(b'original')
        path = archive_file(source, tmp_path, 'Geometry Dash', kind)
        assert path.name.startswith('Geometry Dash_')
        assert path.read_bytes() == b'original'


def test_encoder_probe_uses_conventional_resolution(monkeypatch):
    import clipnest.media as media
    calls=[]
    def run(args, **kwargs):
        calls.append(args)
        return Mock(returncode=0, stderr='')
    monkeypatch.setattr(media, 'run', run)
    assert len(available_encoders('ffmpeg')[0]) == 3
    assert all('color=s=1280x720:r=30' in cmd for cmd in calls)


@pytest.fixture
def segments(tmp_path):
    cache=tmp_path/'_ReplayCache'/'session'
    cache.mkdir(parents=True)
    r=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=320x240:r=30:d=8',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=8',
        '-map','0:v','-map','1:a','-map','1:a','-map','1:a','-c:v','libx264','-g','60','-sc_threshold','0',
        '-c:a','aac','-f','segment','-segment_time','2','-reset_timestamps','1',str(cache/'part%02d.mkv')],capture_output=True)
    assert r.returncode==0,r.stderr
    return [Segment(p,*segment_timing(p,'ffprobe')) for p in sorted(cache.glob('*.mkv'))]


def frames(path):
    r=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-map','0:v:0','-f','framemd5','-'],capture_output=True,text=True,check=True)
    return [line.rsplit(',',1)[1].strip() for line in r.stdout.splitlines() if not line.startswith('#')]


def test_joined_replays_preserve_every_video_frame_without_overlap(segments,tmp_path):
    assert len(segments)==4
    a=concat_segments(segments[:2],'ffmpeg',tmp_path/'first.mkv')
    b=concat_segments(segments[2:],'ffmpeg',tmp_path/'second.mkv')
    expected=sum((frames(s.path) for s in segments),[])
    assert frames(a)+frames(b)==expected
    assert len(expected)==240
    for path in (a,b):
        info=json.loads(subprocess.run(['ffprobe','-v','error','-show_streams','-of','json',path],capture_output=True,text=True,check=True).stdout)
        assert sum(s['codec_type']=='audio' for s in info['streams'])==3
        video=next(s for s in info['streams'] if s['codec_type']=='video')
        assert abs(float(video['start_time'])) < .002
        timing=json.loads(subprocess.run(['ffprobe','-v','error','-show_format','-of','json',path],capture_output=True,text=True,check=True).stdout)
        assert abs(float(timing['format']['duration'])-4) < .025


def test_worker_consumes_only_successfully_saved_segments(segments,tmp_path):
    worker=ContinuousReplay('ffmpeg','ffprobe',tmp_path,90)
    context={'category':'Desktop','output':str(tmp_path),'requested':time.time()}
    worker.add(str(segments[0].path))
    worker.add(str(segments[1].path),context=context)
    first=worker.results.get(timeout=15)
    assert first[0]=='saved'
    worker.add(str(segments[2].path))
    worker.add(str(segments[3].path),context=context)
    second=worker.results.get(timeout=15)
    assert second[0]=='saved'
    assert len(frames(first[1]))==120 and len(frames(second[1]))==120
    worker.close()
    assert not worker.is_alive()


def test_replay_file_safety_and_error_retention(segments,tmp_path):
    worker=ContinuousReplay('missing-ffmpeg','ffprobe',tmp_path,90)
    worker.add(str(segments[0].path),context={'category':'Desktop'})
    error=worker.results.get(timeout=15)
    assert error[0]=='error'
    worker.close()
    assert segments[0].path.exists()
    with pytest.raises(ValueError,match='outside'):
        worker.validate_path(tmp_path/'personal.mkv')


def test_expiry_marks_the_gap_and_limits_cache(segments,tmp_path):
    worker=ContinuousReplay('ffmpeg','ffprobe',tmp_path,3)
    for seg in segments[:-1]:
        worker.add(str(seg.path))
    worker.add(str(segments[-1].path),context={'category':'Desktop'})
    result=worker.results.get(timeout=15)
    assert result[0]=='saved' and result[3]
    assert len(frames(result[1]))==120
    worker.close()


def test_crop_drag_coordinate_mapping_and_even_bounds(monkeypatch):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QImage
    from clipnest.crop import CropCanvas
    app=QApplication.instance() or QApplication([])
    canvas=CropCanvas(QImage(1920,1080,QImage.Format.Format_RGB32),1920,1080)
    canvas.resize(800,600)
    area=canvas.picture_rect()
    assert area.height()==450 and area.top()==75
    p=canvas.to_source(QPointF(400,300))
    assert p.x()==960 and p.y()==540
    canvas.rect=QRectF(13,19,1001,777)
    assert canvas.selection()==(12,18,1002,778)
    canvas.close()


def test_editor_markers_folders_and_restore(tmp_path, monkeypatch):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication, QFileDialog
    import clipnest.editor as module
    from clipnest.ui import Window
    from clipnest.config import load_settings
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr(module,'DATA',tmp_path)
    settings=load_settings()
    settings['output']=str(tmp_path/'Clips')
    window=Window(settings,preview=True)
    window.open_editor()
    editor=window.editor
    editor.showMinimized()
    app.processEvents()
    window.open_editor()
    app.processEvents()
    assert not editor.isMinimized()
    def open_dialog(parent,title,directory,filters):
        assert directory==settings['output']
        return '', ''
    monkeypatch.setattr(QFileDialog,'getOpenFileName',open_dialog)
    editor.choose_clip()
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *a: str(tmp_path/'Exports'))
    editor.choose_export_folder()
    assert json.loads((tmp_path/'editor.json').read_text())['export_folder']==str(tmp_path/'Exports')
    player=editor.player
    editor.player=Mock()
    editor.jump_marker(1.3)
    editor.player.setPosition.assert_called_once_with(1300)
    editor.player=player
    editor.close()
    window.close()


def test_drag_corner_changes_crop_in_source_pixels():
    import os
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtGui import QImage
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from clipnest.crop import CropCanvas
    app=QApplication.instance() or QApplication([])
    canvas=CropCanvas(QImage(1920,1080,QImage.Format.Format_RGB32),1920,1080,(100,100,1000,600))
    canvas.resize(960,540)
    canvas.show()
    app.processEvents()
    QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=QPoint(50,50))
    QTest.mouseMove(canvas,QPoint(100,100))
    QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=QPoint(100,100))
    assert canvas.selection()==(200,200,900,500)
    canvas.close()
