"""Debounced Windows lifecycle and audio endpoint events (GUI thread only)."""
import ctypes
from ctypes import wintypes
import os
import logging
from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaDevices


class SystemEvents(QObject):
    def __init__(self, window, submit):
        super().__init__(window)
        self.window, self.submit = window, submit
        self.locked = self.asleep = False
        self.reason = ''
        self.resume_timer = QTimer(window)
        self.resume_timer.setSingleShot(True)
        self.resume_timer.setInterval(1800)
        self.resume_timer.timeout.connect(self.resume)
        self.audio_timer = QTimer(window)
        self.audio_timer.setSingleShot(True)
        self.audio_timer.setInterval(1200)
        self.audio_timer.timeout.connect(lambda: self.submit('audio_devices_changed'))
        self.devices = QMediaDevices(window)
        self.devices.audioOutputsChanged.connect(self.audio_timer.start)
        self.devices.audioInputsChanged.connect(self.audio_timer.start)
        self.hwnd = None
        self.closed = False
        self.wts = None
        self.registration_timer = QTimer(window)
        self.registration_timer.setSingleShot(True)
        self.registration_timer.timeout.connect(self.start)
        self.registration_timer.start(0)

    def start(self):
        # Never force winId() during Window.__init__, or install a second Python
        # native filter. The existing hotkey filter forwards lifecycle messages.
        if self.closed or os.name != 'nt':
            return
        handle = self.window.windowHandle()
        if handle is None or not self.window.isVisible():
            self.registration_timer.start(100)
            return
        if self.hwnd is not None:
            return
        try:
            self.hwnd = int(handle.winId())
            self.wts = ctypes.WinDLL('wtsapi32', use_last_error=True)
            self.wts.WTSRegisterSessionNotification.argtypes = [wintypes.HWND, wintypes.DWORD]
            self.wts.WTSRegisterSessionNotification.restype = wintypes.BOOL
            self.wts.WTSUnRegisterSessionNotification.argtypes = [wintypes.HWND]
            self.wts.WTSUnRegisterSessionNotification.restype = wintypes.BOOL
            if not self.wts.WTSRegisterSessionNotification(wintypes.HWND(self.hwnd), 0):
                logging.getLogger('clipnest').warning('Session notification registration failed: %s', ctypes.get_last_error())
        except (OSError, AttributeError):
            logging.getLogger('clipnest').exception('Session notifications unavailable')

    def handle_message(self, hwnd, message, value):
        if not self.closed and self.hwnd is not None and hwnd == self.hwnd:
            self.dispatch(message, value)

    def queue_resume(self, reason):
        self.reason = reason
        if not self.locked and not self.asleep:
            self.resume_timer.start()

    def resume(self):
        if not self.locked and not self.asleep:
            self.submit('recover_capture', self.reason)

    def dispatch(self, message, value):
        if message == 0x0218:  # WM_POWERBROADCAST
            if value == 4:  # PBT_APMSUSPEND
                self.asleep = True
                self.resume_timer.stop()
                self.submit('suspend_capture', 'Windows is sleeping')
            elif value in (7, 18):  # RESUMESUSPEND / RESUMEAUTOMATIC
                self.asleep = False
                self.queue_resume('Windows resumed from sleep')
        elif message == 0x02B1:  # WM_WTSSESSION_CHANGE
            if value == 7:  # WTS_SESSION_LOCK
                self.locked = True
                self.resume_timer.stop()
                self.submit('suspend_capture', 'Windows session locked')
            elif value == 8:  # WTS_SESSION_UNLOCK
                self.locked = False
                self.queue_resume('Windows session unlocked')
        elif message == 0x007E:  # WM_DISPLAYCHANGE
            self.queue_resume('Display configuration changed')

    def close(self):
        self.closed = True
        self.registration_timer.stop()
        self.resume_timer.stop()
        self.audio_timer.stop()
        if self.hwnd and self.wts:
            self.wts.WTSUnRegisterSessionNotification(wintypes.HWND(self.hwnd))
        self.hwnd = None
