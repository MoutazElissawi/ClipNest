import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from unittest.mock import Mock
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from test_core import engine, settings, Recorder


def test_confirmed_start_save_finish_and_intentional_replay_stop(engine):
    engine.rpc = Recorder()
    notices = []
    engine.notification.connect(notices.append)
    engine.handle('toggle_replay', None)
    engine.handle('toggle_record', None)
    engine.poll()
    assert [n['title'] for n in notices] == ['Instant replay started', 'Recording started']
    root = Path(engine.settings['output'])/'_Unsorted'
    root.mkdir(parents=True)
    replay = root/'replay.mkv'
    replay.write_bytes(b'clip')
    engine.handle('save_replay', None)
    engine.on_event('ReplayBufferSaved', {'savedReplayPath':str(replay)})
    assert notices[-1]['title'] == 'Clip saved'
    recording = root/'recording.mkv'
    recording.write_bytes(b'recording')
    engine.rpc.output_path = str(recording)
    engine.handle('toggle_record', None)
    assert notices[-1]['title'] == 'Recording finished'
    count = len(notices)
    engine.on_event('RecordStateChanged', {'outputState':'STOPPED','outputPath':str(recording),'code':0})
    engine.handle('toggle_replay', None)
    engine.poll()
    assert len(notices) == count
    assert not any(n['tone']=='error' for n in notices)


def test_output_failure_is_reported_once_and_recovered_file_is_not_normal_finish(engine):
    engine.rpc = Recorder()
    notices = []
    engine.notification.connect(notices.append)
    engine.handle('toggle_record', None)
    root = Path(engine.settings['output'])/'_Unsorted'
    root.mkdir(parents=True)
    recording = root/'failed.mkv'
    recording.write_bytes(b'partial but recoverable')
    engine.rpc.record = False
    engine.on_event('RecordStateChanged', {'outputState':'STOPPED','outputPath':str(recording),'code':-5})
    engine.on_event('NativeWarning', {'output':'record','stopped':True,'code':-5,'message':'Record stopped with error -5'})
    engine.poll()
    assert [n['title'] for n in notices] == ['Recording started','Recording stopped unexpectedly','Interrupted recording saved']
    engine.handle('toggle_replay', None)
    engine.rpc.replay = False
    engine.on_event('NativeWarning', {'output':'replay','stopped':True,'code':-1,'message':'Replay stopped with error -1'})
    engine.poll()
    assert [n['title'] for n in notices].count('Instant replay stopped unexpectedly') == 1


def test_unexpected_inactive_state_and_connection_loss_notify(engine):
    recorder = Recorder()
    engine.rpc = recorder
    notices = []
    engine.notification.connect(notices.append)
    engine.handle('toggle_replay', None)
    recorder.replay = False
    engine.poll()
    engine.poll()
    assert [n['title'] for n in notices].count('Instant replay stopped unexpectedly') == 1
    engine.handle('toggle_record', None)
    engine.catalog.discover = lambda: None
    def fail():
        engine.running = False
        raise ConnectionError('test host exited')
    recorder.pump = fail
    recorder.disconnect = lambda: None
    engine.run()
    assert notices[-1]['title'] == 'Capture stopped unexpectedly'


def test_failed_start_and_pending_archive_do_not_claim_success(engine, monkeypatch):
    recorder = Recorder()
    engine.rpc = recorder
    original = recorder.call
    def fail(request, **kwargs):
        if request == 'StartRecord':
            raise RuntimeError('encoder failed')
        return original(request, **kwargs)
    recorder.call = fail
    notices = []
    engine.notification.connect(notices.append)
    with pytest.raises(RuntimeError):
        engine.handle('toggle_record', None)
    assert notices == []
    import clipnest.engine as module
    monkeypatch.setattr(module, 'archive_file', Mock(side_effect=OSError('file still locked')))
    engine.finish_file('not-ready.mkv',engine.context(),'Recording')
    assert engine.archive_retry and notices == []


def test_silent_overlay_flags_queue_priority_and_disable():
    app = QApplication.instance() or QApplication([])
    from clipnest.notifications import Notifications
    notices = Notifications({'notification_corner':'Bottom left','notification_seconds':2})
    toast = notices.toast
    assert toast.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert toast.windowFlags() & Qt.WindowType.WindowTransparentForInput
    assert toast.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    notices.push('Clip saved','one.mkv')
    assert toast.isVisible() and toast.title == 'Clip saved'
    area = notices.screen().availableGeometry()
    assert toast.x() == area.left()+20 and toast.y() == area.bottom()-toast.height()-19
    notices.push('Recording started','Recording')
    assert len(notices.queue) == 1
    notices.push('Recording stopped unexpectedly','Disk error','error')
    assert toast.title == 'Recording stopped unexpectedly' and not notices.queue
    assert notices.timer.interval() == 6000
    notices.push('Recording stopped unexpectedly','Disk error','error')
    assert not notices.queue
    notices.close()
    notices.settings['notifications_enabled'] = False
    notices.push('Clip saved','two.mkv')
    assert not toast.isVisible()
    notices.push('Preview','Example',force=True)
    assert toast.isVisible()
    notices.close()


def test_redesigned_navigation_and_notification_preferences():
    app = QApplication.instance() or QApplication([])
    from clipnest.ui import Window
    from clipnest.config import load_settings
    window = Window(load_settings(),preview=True)
    window.tabs.setCurrentIndex(1)
    assert window.page_title.text() == 'Settings' and window.nav_buttons[1].isChecked()
    assert window.settings_pages.count() == 5
    window.notification_corner.setCurrentText('Bottom left')
    window.notification_seconds.setValue(4)
    window.submit = Mock()
    window.apply_settings()
    assert window.submit.call_args.args[1]['notification_corner'] == 'Bottom left'
    window.tray.showMessage = Mock()
    window.capture_notice(dict(title='Recording started', detail='Capturing your screen'))
    window.clip_saved('/clips/Game/test.mkv')
    assert window.clips.count() == 1
    window.tray.showMessage.assert_not_called()
    window.close()
