import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog
from clipnest import editor as module


def test_presets_and_last_settings_survive_restart(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(module, 'DATA', tmp_path)
    editor = module.Editor()
    editor.encoders_checked((['CPU H.264', 'NVIDIA AV1'], {}))
    editor.encoder.setCurrentIndex(editor.encoder.findData('NVIDIA AV1'))
    editor.bitrate.setValue(35000)
    monkeypatch.setattr(QInputDialog, 'getText', lambda *a, **k: ('AV1 sharing', True))
    editor.save_export_preset()
    assert editor.preset.currentData() == 'AV1 sharing'
    saved = json.loads((tmp_path/'editor.json').read_text())
    assert saved['export_presets']['AV1 sharing'] == {'encoder':'NVIDIA AV1', 'bitrate':35000}
    editor.close()
    restored = module.Editor()
    restored.encoders_checked((['CPU H.264', 'NVIDIA AV1'], {}))
    assert restored.encoder.currentData() == 'NVIDIA AV1'
    assert restored.bitrate.value() == 35000
    assert restored.preset.currentData() == 'AV1 sharing'
    restored.bitrate.setValue(42000)
    assert restored.preset.currentData() == ''
    assert restored.prefs['export_presets']['AV1 sharing']['bitrate'] == 35000
    restored.preset.setCurrentIndex(restored.preset.findData('AV1 sharing'))
    assert restored.bitrate.value() == 35000
    restored.encoders_checked((['CPU H.264', 'NVIDIA AV1'], {}))
    assert restored.encoder.currentData() == 'NVIDIA AV1' and restored.bitrate.value() == 35000
    restored.close()


def test_unavailable_saved_encoder_is_retained_and_export_blocked(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(module, 'DATA', tmp_path)
    choice = {'encoder':'NVIDIA AV1', 'bitrate':30000}
    (tmp_path/'editor.json').write_text(json.dumps({'last_export':choice, 'export_presets':{'AV1':choice}, 'active_export_preset':'AV1'}))
    editor = module.Editor()
    editor.info = {'path':'stand-in'}
    editor.encoders_checked((['CPU H.264'], {'NVIDIA AV1':'expected unavailable'}))
    assert editor.encoder.currentData() == 'NVIDIA AV1'
    assert not editor.export_ready()
    assert not editor.export_button.isEnabled()
    assert 'Selected encoder unavailable' in editor.status.text()
    editor.encoders_checked((['CPU H.264','NVIDIA AV1'], {}))
    assert editor.encoder.currentData() == 'NVIDIA AV1'
    assert editor.export_ready()
    editor.encoder.setCurrentIndex(editor.encoder.findData('CPU H.264'))
    assert editor.export_ready() and editor.preset.currentData() == ''
    assert editor.prefs['last_export']['encoder'] == 'CPU H.264'
    editor.close()


def test_preset_replace_delete_and_preference_migration(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(module, 'DATA', tmp_path)
    (tmp_path/'editor.json').write_text(json.dumps({'export_folder':'D:/Exports','recent':['keep.mkv'], 'export_presets':{'bad':{'encoder':[], 'bitrate':1}}}))
    editor = module.Editor()
    assert editor.prefs['export_folder']=='D:/Exports' and editor.prefs['recent']==['keep.mkv']
    assert editor.prefs['export_presets']=={}
    editor.encoders_checked((['CPU H.264'], {}))
    monkeypatch.setattr(QInputDialog, 'getText', lambda *a, **k: ('Test', True))
    editor.save_export_preset()
    editor.bitrate.setValue(28000)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.No)
    editor.save_export_preset()
    assert editor.prefs['export_presets']['Test']['bitrate']==20000
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.Yes)
    editor.save_export_preset()
    assert editor.prefs['export_presets']['Test']['bitrate']==28000
    editor.delete_export_preset()
    assert editor.prefs['export_presets']=={} and editor.bitrate.value()==28000
    assert editor.prefs['last_export']['bitrate']==28000
    assert editor.prefs['export_folder']=='D:/Exports' and editor.prefs['recent']==['keep.mkv']
    editor.close()
