"""Shared desktop interactions, using Qt logical coordinates throughout."""
import ctypes
import os
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QPropertyAnimation, QEasingCurve, QAbstractAnimation
from PySide6.QtGui import QDesktopServices, QCursor, QPen
from PySide6.QtWidgets import (QApplication, QListWidget, QAbstractItemView,
                               QStyledItemDelegate, QStyle, QStyleOptionViewItem)
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices


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
        window.resize(min(window.size().width(), width), min(window.size().height(), height))
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


class SmoothList(QListWidget):
    """Short eased mouse-wheel steps; preserve native trackpad pixel scrolling."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.keyboard_focus = False
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setItemDelegate(ItemDelegate(self))
        self.scroll_animation = QPropertyAnimation(self.verticalScrollBar(), b'value', self)
        self.scroll_animation.setDuration(160)
        self.scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.verticalScrollBar().sliderPressed.connect(self.scroll_animation.stop)
        self.verticalScrollBar().rangeChanged.connect(self.scroll_animation.stop)

    def wheelEvent(self, event):
        bar = self.verticalScrollBar()
        if event.pixelDelta().y():
            self.scroll_animation.stop()
            bar.setValue(bar.value()-event.pixelDelta().y())
        elif event.angleDelta().y():
            running = self.scroll_animation.state() == QAbstractAnimation.State.Running
            target = int(self.scroll_animation.endValue()) if running else bar.value()
            delta = round(event.angleDelta().y()/120 * 56)
            # Reversing direction should respond immediately, not finish the old queue.
            if running and (target-bar.value()) * delta > 0:
                target = bar.value()
            target = min(bar.maximum(), max(bar.minimum(), target-delta))
            self.scroll_animation.stop()
            self.scroll_animation.setStartValue(bar.value())
            self.scroll_animation.setEndValue(target)
            self.scroll_animation.start()
        else:
            super().wheelEvent(event)
            return
        event.accept()

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
