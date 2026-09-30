import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from types import SimpleNamespace
from unittest.mock import Mock
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton
from clipnest.shortcut_field import ShortcutField
from clipnest.hotkeys import parse_hotkey


def test_capture_navigation_chords_cancel_and_tab():
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    layout = QVBoxLayout(host)
    field = ShortcutField('F8')
    other = QPushButton('Apply')
    layout.addWidget(field)
    layout.addWidget(other)
    state = []
    field.capturing.connect(state.append)
    host.show()
    field.setFocus()
    app.processEvents()
    QTest.keyClick(field, Qt.Key.Key_PageDown)
    assert field.text() == 'PageDown' and parse_hotkey(field.text()) == (0, 0x22)
    QTest.keyClick(field, Qt.Key.Key_PageUp, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert field.text() == 'Ctrl+Shift+PageUp'
    QTest.keyClick(field, Qt.Key.Key_Shift)
    assert field.text() == 'Ctrl+Shift+PageUp'
    QTest.keyClick(field, Qt.Key.Key_Escape)
    assert field.text() == 'F8' and state[-1] is False
    field.setFocus()
    QTest.keyClick(field, Qt.Key.Key_PageDown)
    QTest.keyClick(field, Qt.Key.Key_Tab)
    assert other.hasFocus() and field.text() == 'PageDown'
    host.close()


def test_page_key_aliases_reach_windows_registration(monkeypatch):
    import clipnest.hotkeys as module
    assert parse_hotkey('Page Down') == parse_hotkey('PgDn') == parse_hotkey('PgDown') == (0, 0x22)
    assert parse_hotkey('Ctrl+Page Up') == (2, 0x21)
    api = Mock()
    api.RegisterHotKey.return_value = 1
    monkeypatch.setattr(module, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(module, 'ctypes', SimpleNamespace(windll=SimpleNamespace(user32=api)))
    keys = module.Hotkeys()
    keys.configure('PageDown', 'Ctrl+PageUp')
    assert api.RegisterHotKey.call_args_list[0].args == (None, 101, 0x4000, 0x22)
    assert api.RegisterHotKey.call_args_list[1].args == (None, 102, 0x4002, 0x21)
    keys.close()


def test_settings_capture_suspends_actions_and_applies_pressed_key(monkeypatch):
    app = QApplication.instance() or QApplication([])
    from clipnest.ui import Window
    from clipnest.config import load_settings
    window = Window(load_settings(), preview=True)
    window.hotkeys = Mock()
    window.register_hotkeys = Mock()
    window.preview = False
    window.shortcut_capture(True)
    window.hotkeys.close.assert_called_once()
    submit = Mock()
    monkeypatch.setattr(window.engine, 'submit', submit)
    window.submit('save_replay')
    window.submit('toggle_record')
    submit.assert_not_called()
    window.shortcut_capture(False)
    window.register_hotkeys.assert_called_once()
    QTest.keyClick(window.replay_key, Qt.Key.Key_PageDown)
    window.apply_settings()
    command, data = submit.call_args.args
    assert command == 'apply' and data['replay_key'] == 'PageDown'
    assert data['record_key'] == window.settings['record_key']
    window.preview = True
    window.close()
