"""Shared desktop interactions, using Qt logical coordinates throughout."""
import ctypes
import os
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QPropertyAnimation, QEasingCurve, QAbstractAnimation, QObject, QEvent
from PySide6.QtGui import QDesktopServices, QCursor, QPen
from PySide6.QtWidgets import (QApplication, QListWidget, QAbstractItemView, QAbstractScrollArea, QScrollBar,
                               QStyledItemDelegate, QStyle, QStyleOptionViewItem, QSlider, QStyleOptionSlider,
                               QWidget, QAbstractSpinBox, QComboBox, QAbstractSlider, QPlainTextEdit, QHeaderView,
                               QInputDialog, QMessageBox)
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices


class SeekSlider(QSlider):
    """A left click on the track seeks immediately; dragging and keys still work."""
    def seek_to_mouse(self, event):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        handle = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, option,
                                             QStyle.SubControl.SC_SliderHandle, self)
        span = max(1, self.width() - handle.width())
        position = round(event.position().x() - handle.width()/2)
        value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(),
                                               max(0, min(span, position)), span, option.upsideDown)
        self.setValue(value)
        self.sliderMoved.emit(value)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.setSliderDown(True)
            self.seek_to_mouse(event)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.isSliderDown() and event.buttons() & Qt.MouseButton.LeftButton:
            self.seek_to_mouse(event)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isSliderDown():
            self.seek_to_mouse(event)
            self.setSliderDown(False)
            event.accept()
        else:
            super().mouseReleaseEvent(event)


def show_centered(window, anchor=None):
    """Restore, fit and center on the invoking window's monitor, including taskbar."""
    screen = anchor.screen() if anchor is not None else QApplication.screenAt(QCursor.pos())
    screen = screen or QApplication.primaryScreen()
    window.showNormal()
    if screen is not None:
        area = screen.availableGeometry()
        # Qt sizes and availableGeometry already account for Windows display scaling.
        margins = window.windowHandle().frameMargins() if window.windowHandle() else None
        extra_w = margins.left() + margins.right() if margins else 0
        extra_h = margins.top() + margins.bottom() if margins else 0
        width, height = max(1, area.width()-extra_w-24), max(1, area.height()-extra_h-24)
        window.setMinimumSize(min(window.minimumWidth(), width), min(window.minimumHeight(), height))
        preferred = window.preferred_open_size() if hasattr(window, 'preferred_open_size') else window.size()
        window.resize(min(preferred.width(), width), min(preferred.height(), height))
        frame = window.frameGeometry()
        frame.moveCenter(area.center())
        window.move(frame.topLeft())
    window.raise_()
    window.activateWindow()


def reveal_file(path):
    """Select a file in Explorer via its PIDL; no shell parsing or quoting hazards."""
    path = Path(path).resolve()
    if not path.is_file():
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
    if os.name == 'nt':
        from ctypes import wintypes as W
        shell = ctypes.WinDLL('shell32', use_last_error=True)
        ole = ctypes.WinDLL('ole32')
        shell.SHParseDisplayName.argtypes = [W.LPCWSTR, ctypes.c_void_p,
                                            ctypes.POINTER(ctypes.c_void_p), W.DWORD, ctypes.c_void_p]
        shell.SHParseDisplayName.restype = ctypes.c_long
        shell.SHOpenFolderAndSelectItems.argtypes = [ctypes.c_void_p, W.UINT, ctypes.c_void_p, W.DWORD]
        shell.SHOpenFolderAndSelectItems.restype = ctypes.c_long
        ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        pidl = ctypes.c_void_p()
        result = shell.SHParseDisplayName(str(path), None, ctypes.byref(pidl), 0, None)
        if result == 0 and pidl:
            try:
                if shell.SHOpenFolderAndSelectItems(pidl, 0, None, 0) == 0:
                    return True
            finally:
                ole.CoTaskMemFree(pidl)
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))


class DefaultAudioOutput(QAudioOutput):
    """Follow Windows' playback endpoint even when a player was opened earlier."""
    def __init__(self, parent=None):
        super().__init__(QMediaDevices.defaultAudioOutput(), parent)
        self.devices = QMediaDevices(self)
        self.devices.audioOutputsChanged.connect(self.refresh_device)

    def refresh_device(self):
        self.setDevice(QMediaDevices.defaultAudioOutput())


class ItemDelegate(QStyledItemDelegate):
    """Replace native dotted text rectangles with a subtle keyboard-only border."""
    def paint(self, painter, option, index):
        option = QStyleOptionViewItem(option)
        focused = bool(option.state & QStyle.StateFlag.State_HasFocus)
        option.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, option, index)
        if focused and getattr(self.parent(), 'keyboard_focus', False):
            painter.save()
            painter.setPen(QPen(Qt.GlobalColor.lightGray, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(option.rect.adjusted(2, 2, -2, -2), 5, 5)
            painter.restore()


def scroll_animation(bar):
    """The eased wheel animation for a scroll bar, created on first use and owned by the bar."""
    animation = bar.findChild(QPropertyAnimation, 'smoothWheel')
    if animation is None:
        animation = QPropertyAnimation(bar, b'value', bar)
        animation.setObjectName('smoothWheel')
        animation.setDuration(160)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        bar.sliderPressed.connect(animation.stop)
        bar.rangeChanged.connect(animation.stop)
    return animation


def smooth_wheel(bar, event):
    """Scroll `bar` in short eased steps (trackpads keep their native pixels). False when it cannot move
    that way, so the wheel goes on to an outer scroll area."""
    animation = scroll_animation(bar)
    if event.pixelDelta().y():
        animation.stop()
        value = bar.value()
        bar.setValue(value-event.pixelDelta().y())
        return bar.value() != value
    if not event.angleDelta().y():
        return False
    running = animation.state() == QAbstractAnimation.State.Running
    target = int(animation.endValue()) if running else bar.value()
    delta = round(event.angleDelta().y()/120 * 56)
    # Reversing direction should respond immediately, not finish the old queue.
    if running and (target-bar.value()) * delta > 0:
        target = bar.value()
    target = min(bar.maximum(), max(bar.minimum(), target-delta))
    if target == bar.value():
        animation.stop()
        return running
    animation.stop()
    animation.setStartValue(bar.value())
    animation.setEndValue(target)
    animation.start()
    return True


class SmoothWheel(QObject):
    """Application-wide mouse-wheel smoothing for every list, table and scrolling page.
    Wheeling over an unfocused spin box, combo box or slider inside a scrolling area scrolls the
    area instead of changing the value; click the control first to use the wheel on it."""
    VALUE_WIDGETS = (QAbstractSpinBox, QComboBox, QAbstractSlider)

    def eventFilter(self, receiver, event):
        if event.type() == QEvent.Type.Polish and isinstance(receiver, QAbstractItemView) and not isinstance(
                receiver, QHeaderView):
            # Lists and tables move by whole rows by default; pixels let the eased steps land anywhere.
            receiver.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            return False
        if event.type() != QEvent.Type.Wheel or not isinstance(receiver, QWidget):
            return False
        if event.modifiers() != Qt.KeyboardModifier.NoModifier or not (event.angleDelta().y() or event.pixelDelta().y()):
            return False  # Shift scrolls sideways and Ctrl zooms; both stay native
        guarded = False
        widget = receiver
        while widget is not None:
            if isinstance(widget, QScrollBar):
                if widget.orientation() == Qt.Orientation.Vertical and smooth_wheel(widget, event):
                    return True
            elif isinstance(widget, self.VALUE_WIDGETS):
                if widget.hasFocus():
                    return False
                guarded = True
            elif isinstance(widget, QAbstractScrollArea) and not isinstance(widget, QHeaderView) and (
                    widget.viewport() is receiver or widget.viewport().isAncestorOf(receiver)):
                if isinstance(widget, QPlainTextEdit):
                    return False  # scrolls by whole lines; leave it native
                if smooth_wheel(widget.verticalScrollBar(), event):
                    return True
            widget = widget.parentWidget()
        # An unfocused control inside a page that cannot scroll further still keeps its value.
        return guarded and self.in_scroll_area(receiver)

    @staticmethod
    def in_scroll_area(widget):
        while widget is not None:
            if isinstance(widget, QAbstractScrollArea):
                return True
            widget = widget.parentWidget()
        return False


def install_smooth_scrolling(app):
    if app.findChild(SmoothWheel) is None:
        app.installEventFilter(SmoothWheel(app))


class SmoothList(QListWidget):
    """Short eased mouse-wheel steps; preserve native trackpad pixel scrolling."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.keyboard_focus = False
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setItemDelegate(ItemDelegate(self))

    @property
    def scroll_animation(self):
        return scroll_animation(self.verticalScrollBar())

    def wheelEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.NoModifier and smooth_wheel(self.verticalScrollBar(), event):
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        self.keyboard_focus = False
        super().mousePressEvent(event)
        self.viewport().update()

    def keyPressEvent(self, event):
        self.keyboard_focus = True
        self.scroll_animation.stop()
        super().keyPressEvent(event)
        self.viewport().update()

    def focusInEvent(self, event):
        self.keyboard_focus = event.reason() in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason)
        super().focusInEvent(event)


def same_file(a, b):
    """Same path on Windows, ignoring case and relative parts."""
    return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))


class ClipActions:
    """Favorites, tags and Combine for the selected clips, shared by the gallery and the clip browser.
    The host keeps clip dicts in self.clips, its list in self.list and Annotations in self.annotations, and
    provides show_clips() to redraw the list and reload_clips() to rescan after a new file appears."""
    def selected_paths(self):
        return [item.data(Qt.ItemDataRole.UserRole) for item in self.list.selectedItems()]

    def selected_clips(self):
        paths = set(self.selected_paths())
        return [clip for clip in self.clips if clip['path'] in paths]

    def favorite_selected(self):
        selected = self.selected_clips()
        if selected:
            self.annotate(selected, favorite=not all(clip.get('favorite', False) for clip in selected))

    def tag_selected(self):
        selected = self.selected_clips()
        if not selected:
            return
        text, ok = QInputDialog.getText(self, 'Clip tags', 'Comma-separated tags (replaces tags on selected clips):',
                                        text=', '.join(selected[0].get('tags', [])))
        if ok:
            self.annotate(selected, tags=[tag.strip() for tag in text.split(',') if tag.strip()])

    def annotate(self, clips, **values):
        try:
            for clip in clips:
                self.annotations.set(clip['path'], **values)
                clip.update(values)
        except Exception as exc:
            QMessageBox.warning(self, 'Clip annotations', str(exc))
        self.show_clips()

    def combine_selected(self):
        from .join_dialog import start_combine
        start_combine(self.selected_paths(), self)
