"""One-chord key capture for the Win32 shortcut names accepted by ClipNest."""
from PySide6.QtCore import Qt, QEvent, Signal
from PySide6.QtWidgets import QLineEdit


class ShortcutField(QLineEdit):
    capturing = Signal(bool)

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setReadOnly(True)
        self.setToolTip('Click here, then press a key or combination. Esc cancels; Tab moves to the next field. Click Apply settings to save.')
        self.previous = text

    def focusInEvent(self, event):
        self.previous = self.text()
        self.capturing.emit(True)
        super().focusInEvent(event)
        self.selectAll()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.capturing.emit(False)

    def event(self, event):
        if event.type() == QEvent.Type.ShortcutOverride:
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.setText(self.previous)
            self.clearFocus()
            event.accept()
            return
        if event.isAutoRepeat():
            event.accept()
            return
        names = {Qt.Key.Key_PageDown: 'PageDown', Qt.Key.Key_PageUp: 'PageUp',
                 Qt.Key.Key_Home: 'Home', Qt.Key.Key_End: 'End', Qt.Key.Key_Insert: 'Insert',
                 Qt.Key.Key_Delete: 'Delete', Qt.Key.Key_Pause: 'Pause', Qt.Key.Key_Space: 'Space',
                 Qt.Key.Key_Left: 'Left', Qt.Key.Key_Right: 'Right', Qt.Key.Key_Up: 'Up', Qt.Key.Key_Down: 'Down'}
        name = names.get(key)
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
            name = f'F{key-Qt.Key.Key_F1+1}'
        elif Qt.Key.Key_A <= key <= Qt.Key.Key_Z or Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            name = chr(key)
        if name:
            modifiers = event.modifiers()
            prefix = [label for flag, label in ((Qt.KeyboardModifier.ControlModifier, 'Ctrl'),
                      (Qt.KeyboardModifier.AltModifier, 'Alt'), (Qt.KeyboardModifier.ShiftModifier, 'Shift'),
                      (Qt.KeyboardModifier.MetaModifier, 'Win')) if modifiers & flag]
            self.setText('+'.join(prefix+[name]))
            self.selectAll()
        # Modifier-only or unsupported keys retain the current binding.
        event.accept()
