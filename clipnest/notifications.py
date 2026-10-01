"""Silent, non-activating desktop overlay; no Windows balloon or audio API."""
from collections import deque
import ctypes
from ctypes import wintypes
import logging
import os
import time
from PySide6.QtCore import Qt, QTimer, QRectF, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import QApplication, QWidget


class Toast(QWidget):
    def __init__(self):
        flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                 Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.WindowTransparentForInput)
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle('ClipNest notification')
        self.resize(320, 76)
        self.reveal = 1.0
        self.slide_direction = 1
        self.title = self.detail = ''
        self.tone = 'success'
        self.capture_excluded = False

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self.reveal)
        p.translate(self.slide_direction * (1.0-self.reveal) * self.width(), 0)
        accent = QColor('#ff8e9f' if self.tone == 'error' else '#a4d65e')
        p.setBrush(QColor(20, 20, 20, 247))
        p.setPen(QPen(QColor('#4a4a4a'), 1))
        p.drawRoundedRect(QRectF(1, 1, self.width()-2, self.height()-2), 12, 12)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        p.drawRoundedRect(QRectF(1, 17, 4, self.height()-34), 2, 2)
        p.setPen(accent)
        p.setFont(QFont('Segoe UI', 8, QFont.Weight.DemiBold))
        p.drawText(16, 17, 'CLIPNEST')
        p.setPen(QColor('#f7f7f7'))
        p.setFont(QFont('Segoe UI', 11, QFont.Weight.DemiBold))
        p.drawText(16, 38, p.fontMetrics().elidedText(self.title, Qt.TextElideMode.ElideRight, self.width()-32))
        p.setPen(QColor('#c0c0c0'))
        p.setFont(QFont('Segoe UI', 9))
        text = p.fontMetrics().elidedText(self.detail.replace('\n', ' '), Qt.TextElideMode.ElideRight, self.width()-32)
        p.drawText(16, 59, text)

    def exclude_from_capture(self):
        if os.name != 'nt':
            return
        try:
            function = ctypes.windll.user32.SetWindowDisplayAffinity
            function.argtypes = [wintypes.HWND, wintypes.DWORD]
            function.restype = wintypes.BOOL
            self.capture_excluded = bool(function(int(self.winId()), 0x11))
        except (AttributeError, OSError):
            self.capture_excluded = False
        if not self.capture_excluded:
            logging.getLogger('clipnest').warning('Notification capture exclusion unavailable on this Windows configuration.')


class Notifications:
    def __init__(self, settings):
        self.settings = settings
        self.toast = Toast()
        self.queue = deque(maxlen=8)
        self.recent = {}
        self.timer = QTimer(self.toast)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.next)
        self.active = False
        self.exiting = False
        self.animation = QVariantAnimation(self.toast)
        self.animation.valueChanged.connect(self.animate_frame)
        self.animation.finished.connect(self.animation_finished)

    def animate_frame(self, value):
        self.toast.reveal = float(value)
        self.toast.update()

    def animate(self, end, duration, curve):
        self.animation.stop()
        self.animation.setStartValue(self.toast.reveal)
        self.animation.setEndValue(end)
        self.animation.setDuration(duration)
        self.animation.setEasingCurve(curve)
        self.animation.start()

    def animation_finished(self):
        if self.exiting:
            self.toast.hide()
            self.active = False
            self.exiting = False
            if self.queue:
                self.display(self.queue.popleft())

    def push(self, title, detail='', tone='success', force=False):
        if not force and not self.settings.get('notifications_enabled', True):
            return
        now = time.monotonic()
        self.recent = {key: stamp for key, stamp in self.recent.items() if now-stamp < 3}
        key = (title, detail)
        if key in self.recent:
            return
        self.recent[key] = now
        item = (title, detail, tone)
        if tone == 'error':
            # Failures take priority; a start confirmation must not follow a stop error.
            self.queue.clear()
            self.display(item)
        elif self.active:
            self.queue.append(item)
        else:
            self.display(item)

    def screen(self):
        screens = QApplication.screens()
        name = self.settings.get('notification_screen', '')
        chosen = next((screen for screen in screens if screen.name() == name), None)
        if chosen:
            return chosen
        if os.name == 'nt':
            try:
                api = ctypes.windll.user32
                api.GetForegroundWindow.restype = wintypes.HWND
                api.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
                api.MonitorFromWindow.restype = wintypes.HANDLE
                class MonitorInfo(ctypes.Structure):
                    _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT),
                                ('work', wintypes.RECT), ('flags', wintypes.DWORD), ('device', wintypes.WCHAR*32)]
                info = MonitorInfo()
                info.size = ctypes.sizeof(info)
                api.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
                handle = api.MonitorFromWindow(api.GetForegroundWindow(), 2)
                if api.GetMonitorInfoW(handle, ctypes.byref(info)):
                    chosen = next((screen for screen in screens if screen.name().casefold() == info.device.casefold()), None)
            except (AttributeError, OSError):
                pass
        return chosen or QApplication.primaryScreen()

    def display(self, item):
        self.timer.stop()
        self.animation.stop()
        self.exiting = False
        self.active = True
        self.toast.reveal = 0.0
        self.toast.resize(320, 76 if item[1] else 54)
        corner = self.settings.get('notification_corner', 'Top right')
        self.toast.slide_direction = -1 if 'left' in corner else 1
        self.toast.title, self.toast.detail, self.toast.tone = item
        screen = self.screen()
        if screen:
            area = screen.availableGeometry()
            corner = self.settings.get('notification_corner', 'Top right')
            x = area.left()+20 if 'left' in corner else area.right()-self.toast.width()-19
            y = area.top()+20 if 'Top' in corner else area.bottom()-self.toast.height()-19
            self.toast.move(x, y)
        # Request exclusion before making the first frame visible.
        self.toast.exclude_from_capture()
        self.toast.update()
        self.toast.show()
        self.animate(1.0, 240, QEasingCurve.Type.OutCubic)
        duration = max(2, min(10, int(self.settings.get('notification_seconds', 3))))
        self.timer.start((max(6, duration) if item[2] == 'error' else duration)*1000)

    def next(self):
        self.timer.stop()
        if not self.active or self.exiting:
            return
        self.exiting = True
        self.animate(0.0, 180, QEasingCurve.Type.InCubic)

    def close(self):
        self.animation.stop()
        self.active = False
        self.exiting = False
        self.timer.stop()
        self.queue.clear()
        self.toast.close()
