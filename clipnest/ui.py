from __future__ import annotations

import copy
import ctypes
from ctypes import wintypes
import math
import os
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QAbstractNativeEventFilter, QUrl
from PySide6.QtGui import QDesktopServices, QAction
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTabWidget, QGroupBox, QFormLayout, QLineEdit, QSpinBox,
    QComboBox, QSlider, QProgressBar, QPlainTextEdit, QFileDialog, QMessageBox,
    QListWidget, QListWidgetItem, QInputDialog, QSystemTrayIcon, QMenu, QScrollArea, QCheckBox)

from .config import DATA, ENCODERS
from .engine import Engine, MIC, DESKTOP
from .hotkeys import Hotkeys, held, parse_hotkey
from .shortcut_field import ShortcutField

from .theme import STYLE
from .notifications import Notifications


from .branding import app_icon as icon


class NativeHotkeys(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        if os.name == "nt" and bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam in (101, 102):
                self.callback("save_replay" if msg.wParam == 101 else "toggle_record")
                return True, 0
        return False, 0


class Window(QMainWindow):
    def __init__(self, settings, preview=False):
        super().__init__()
        self.settings = copy.deepcopy(settings)
        self.preview = preview
        self.connected = self.recording = self.replay = False
        self.closing = False
        self.allow_close = False
        self.last_app = {}
        self.last_mic = None
        self.device_data = {}
        self.setWindowTitle("ClipNest 1.5.1 • Native recorder + editor")
        self.setWindowIcon(icon())
        self.resize(1180, 800)
        self.setMinimumSize(1000, 720)
        self.setStyleSheet(STYLE)
        self.engine = Engine(settings)
        self.hotkeys = Hotkeys()
        self.capturing_shortcut = False
        self.notifications = Notifications(self.settings)
        self.native_filter = NativeHotkeys(self.submit)
        QApplication.instance().installNativeEventFilter(self.native_filter)

        shell = QWidget()
        outer = QHBoxLayout(shell)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        rail = QWidget()
        rail.setObjectName('rail')
        rail.setFixedWidth(176)
        navigation = QVBoxLayout(rail)
        navigation.setContentsMargins(16, 24, 16, 16)
        brand = QLabel('ClipNest')
        brand.setObjectName('brand')
        navigation.addWidget(brand)
        navigation.addSpacing(24)
        self.nav_buttons = {}
        for index, label in ((0, 'Capture'), (2, 'Clips && games'), (1, 'Settings')):
            button = self.button(label, lambda checked=False, i=index: self.tabs.setCurrentIndex(i), 'nav')
            button.setCheckable(True)
            self.nav_buttons[index] = button
            navigation.addWidget(button)
        navigation.addSpacing(24)
        navigation.addWidget(self.button('Open clip editor', self.open_editor, 'quiet'))
        navigation.addStretch()
        self.connection_badge = QLabel('ENGINE OFFLINE')
        self.connection_badge.setObjectName('chip')
        navigation.addWidget(self.connection_badge)
        navigation.addSpacing(12)
        navigation.addWidget(self.button('Minimize to tray', self.hide_to_tray, 'quiet'))
        version = QLabel('v1.5.1')
        version.setObjectName('muted')
        navigation.addWidget(version)
        outer.addWidget(rail)
        content = QWidget()
        content.setObjectName('content')
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        header = QHBoxLayout()
        headings = QVBoxLayout()
        self.page_title = QLabel('Capture dashboard')
        self.page_title.setObjectName('pageTitle')
        headings.addWidget(self.page_title)
        self.page_description = QLabel('Your next highlight starts here.')
        self.page_description.setObjectName('muted')
        self.page_description.hide()
        header.addLayout(headings, 1)
        header.addWidget(self.button('Open clips folder', self.open_folder, 'quiet'))
        layout.addLayout(header)
        self.status = QLabel('Ready to connect  •  Start the engine to enable capture')
        self.status.setObjectName('status')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        self.tabs.setDocumentMode(True)
        layout.addWidget(self.tabs, 1)
        self.build_capture()
        self.build_settings()
        self.build_clips()
        self.tabs.currentChanged.connect(self.page_changed)
        self.page_changed(0)
        self.editor = None
        outer.addWidget(content, 1)
        self.setCentralWidget(shell)
        menu = self.menuBar().addMenu("File")
        menu.addAction("Open clip editor…", self.open_editor)
        menu.addAction("Open clips folder", self.open_folder)
        menu.addAction("Open app diagnostics", lambda: self.open_path(DATA))
        menu.addAction("Open recorder logs", lambda: self.open_path(DATA / "native-engine.log"))
        menu.addSeparator()
        menu.addAction("Exit", self.close)
        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction("Read setup and limitations", lambda: self.open_path(Path(__file__).resolve().parents[1] / "README.md"))
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("ClipNest")
        tray_menu = QMenu()
        tray_menu.addAction("Show ClipNest", self.show_normal)
        tray_menu.addAction("Save replay", lambda: self.submit("save_replay"))
        tray_menu.addAction("Start / stop recording", lambda: self.submit("toggle_record"))
        tray_menu.addAction("Exit", self.close)
        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(lambda reason: self.show_normal() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        if not preview:
            self.tray.show()
            self.engine.state.connect(self.update_state)
            self.engine.devices.connect(self.update_devices)
            self.engine.message.connect(self.log)
            self.engine.error.connect(self.show_error)
            self.engine.saved.connect(self.clip_saved)
            self.engine.notification.connect(self.capture_notice)
            self.engine.meters.connect(self.update_meters)
            self.engine.applied.connect(self.settings_applied)
            self.engine.shutdown_done.connect(self.shutdown_complete)
            self.engine.start()
            self.register_hotkeys()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(40)

    def button(self, text, callback, name=None):
        result = QPushButton(text)
        result.clicked.connect(callback)
        if name:
            result.setObjectName(name)
        return result

    def page_changed(self, index):
        titles = {0: ('Capture', ''),
                  1: ('Settings', ''),
                  2: ('Clips & games', '')}
        title, description = titles[index]
        self.page_title.setText(title)
        self.page_description.setText(description)
        for i, button in self.nav_buttons.items():
            button.setChecked(i == index)

    def build_capture(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        row = QHBoxLayout()
        self.category = QLabel('Saving to  /  Desktop')
        self.category.setObjectName('chip')
        row.addWidget(self.category)
        row.addStretch()
        self.connect_btn = self.button('Start engine', lambda: self.submit('connect'), 'primary')
        row.addWidget(self.connect_btn)
        layout.addLayout(row)
        cards = QHBoxLayout()
        cards.setSpacing(16)
        replay = QGroupBox('Instant replay')
        body = QVBoxLayout(replay)
        self.replay_metric = QLabel(f"{self.settings['replay_seconds']} sec")
        self.replay_metric.setObjectName('metric')
        body.addWidget(self.replay_metric)
        self.buffer_label = QLabel('Replay duration')
        self.buffer_label.setObjectName('muted')
        self.buffer_label.setWordWrap(True)
        body.addWidget(self.buffer_label)
        body.addSpacing(12)
        buttons = QHBoxLayout()
        self.replay_btn = self.button('Start replay', lambda: self.submit('toggle_replay'))
        self.save_btn = self.button('Save replay', lambda: self.submit('save_replay'), 'primary')
        buttons.addWidget(self.replay_btn)
        buttons.addWidget(self.save_btn)
        body.addLayout(buttons)
        cards.addWidget(replay, 1)
        recording = QGroupBox('Recording')
        body = QVBoxLayout(recording)
        self.record_metric = QLabel('00:00:00')
        self.record_metric.setObjectName('metric')
        body.addWidget(self.record_metric)
        self.record_hint = QLabel('Elapsed time')
        self.record_hint.setObjectName('muted')
        body.addWidget(self.record_hint)
        body.addSpacing(12)
        self.record_btn = self.button('Start recording', lambda: self.submit('toggle_record'), 'record')
        body.addWidget(self.record_btn)
        cards.addWidget(recording, 1)
        layout.addLayout(cards)
        for button in (self.replay_btn, self.save_btn, self.record_btn):
            button.setEnabled(False)
        self.shortcut_label = QLabel()
        self.shortcut_label.setObjectName('muted')
        layout.addWidget(self.shortcut_label)
        self.update_shortcut_label()
        lower = QHBoxLayout()
        lower.setSpacing(16)
        audio = QGroupBox('Audio')
        form = QFormLayout(audio)
        form.setVerticalSpacing(16)
        form.setHorizontalSpacing(24)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.mode = QComboBox()
        self.mode.addItems(['Always on', 'Push to talk', 'Muted'])
        self.mode.setCurrentText(self.settings['mic_mode'])
        form.addRow('Microphone', self.mode)
        volume_row = QHBoxLayout()
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 200)
        self.volume.setValue(self.settings['mic_volume'])
        self.volume_label = QLabel(f'{self.volume.value()}%')
        self.volume.valueChanged.connect(lambda n: self.volume_label.setText(f'{n}%'))
        volume_row.addWidget(self.volume)
        volume_row.addWidget(self.volume_label)
        form.addRow('Gain', volume_row)
        self.mic_meter, self.desktop_meter = QProgressBar(), QProgressBar()
        for meter in (self.mic_meter, self.desktop_meter):
            meter.setRange(0, 100)
            meter.setValue(0)
            meter.setTextVisible(False)
        form.addRow('Microphone', self.mic_meter)
        form.addRow('Desktop', self.desktop_meter)
        self.mic_label = QLabel('Separate Mix, Desktop and Microphone tracks')
        self.mic_label.setObjectName('muted')
        self.mic_label.setWordWrap(True)
        form.addRow(self.mic_label)
        lower.addWidget(audio, 1)
        activity = QGroupBox('Recent activity')
        activity_layout = QVBoxLayout(activity)
        self.messages = QPlainTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setMaximumBlockCount(250)
        self.messages.setPlaceholderText('Saves, status updates and errors appear here.')
        self.messages.setMaximumHeight(160)
        activity_layout.addWidget(self.messages)
        lower.addWidget(activity, 1)
        layout.addLayout(lower)
        layout.addStretch(1)
        self.tabs.addTab(page, 'Capture')

    def spin(self, low, high, value, suffix=""):
        control = QSpinBox()
        control.setRange(low, high)
        control.setValue(value)
        control.setSuffix(suffix)
        return control

    def build_settings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.settings_pages = QTabWidget()
        layout.addWidget(self.settings_pages, 1)
        def section(name, title, description):
            root = QWidget()
            body = QVBoxLayout(root)
            body.setContentsMargins(0, 16, 0, 0)
            group = QGroupBox(title)
            form = QFormLayout(group)
            form.setVerticalSpacing(16)
            form.setHorizontalSpacing(24)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            note = QLabel(description)
            note.setWordWrap(True)
            note.setObjectName('muted')
            form.addRow(note)
            body.addWidget(group)
            body.addStretch()
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(root)
            self.settings_pages.addTab(scroll, name)
            return form
        form = section('Capture', 'CAPTURE / STORAGE', 'Choose your display, recording folder and replay behavior.')
        self.output = QLineEdit(self.settings['output'])
        output_row = QHBoxLayout()
        output_row.addWidget(self.output)
        output_row.addWidget(self.button('Browse', self.choose_output))
        form.addRow('Save clips to', output_row)
        self.seconds = self.spin(5, 1800, self.settings['replay_seconds'], ' sec')
        form.addRow('Replay duration', self.seconds)
        self.replay_mode = QComboBox()
        self.replay_mode.addItem('Continuous · consecutive clips', 'continuous')
        self.replay_mode.addItem('Classic · last X seconds', 'classic')
        self.replay_mode.setCurrentIndex(self.replay_mode.findData(self.settings.get('replay_mode', 'continuous')))
        form.addRow('Replay behavior', self.replay_mode)
        self.monitor = QComboBox()
        self.monitor.addItem('Start engine to list monitors', None)
        form.addRow('Display', self.monitor)
        self.capture_method = QComboBox()
        for label, value in (('Windows Graphics Capture', 2), ('Automatic', 0), ('DXGI Desktop Duplication', 1)):
            self.capture_method.addItem(label, value)
        self.capture_method.setCurrentIndex(self.capture_method.findData(self.settings.get('capture_method', 2)))
        form.addRow('Capture method', self.capture_method)
        note = QLabel('Continuous replay saves consecutive footage within the buffer duration. Older footage expires. Windows Graphics Capture can show a capture border; DXGI avoids it when supported.')
        note.setWordWrap(True)
        note.setObjectName('muted')
        form.addRow(note)
        form = section('Video', 'VIDEO QUALITY', 'Recorder quality is separate from your editor export presets.')
        self.encoder = QComboBox()
        self.encoder.addItems(ENCODERS)
        self.encoder.setCurrentText(self.settings['encoder'])
        form.addRow('Encoder', self.encoder)
        resolution = QHBoxLayout()
        self.width = self.spin(64, 4096, self.settings['width'])
        self.height = self.spin(64, 4096, self.settings['height'])
        resolution.addWidget(self.width)
        resolution.addWidget(QLabel('×'))
        resolution.addWidget(self.height)
        form.addRow('Resolution', resolution)
        self.fps = QComboBox()
        self.fps.addItems(['24', '30', '60', '90', '120'])
        self.fps.setCurrentText(str(self.settings['fps']))
        form.addRow('Frame rate', self.fps)
        self.bitrate = self.spin(1000, 200000, self.settings['bitrate'], ' Kbps')
        self.bitrate.setSingleStep(1000)
        form.addRow('Bitrate', self.bitrate)
        form = section('Audio', 'AUDIO DEVICES', 'Mix, Desktop and Microphone are saved as separate tracks. Live microphone controls are on the dashboard.')
        self.mic, self.output_device = QComboBox(), QComboBox()
        for control, key in ((self.mic, 'mic_device'), (self.output_device, 'desktop_device')):
            control.addItem('System default', 'default')
            if self.settings[key] != 'default':
                control.addItem('Saved device', self.settings[key])
                control.setCurrentIndex(1)
        form.addRow('Microphone', self.mic)
        form.addRow('Desktop output', self.output_device)
        form.addRow(self.button('Refresh devices', lambda: self.submit('refresh_devices')))
        form = section('Shortcuts', 'KEYBOARD SHORTCUTS', 'Click a field and press your key or combination. Esc cancels. Apply settings to save.')
        self.replay_key = ShortcutField(self.settings['replay_key'])
        self.record_key = ShortcutField(self.settings['record_key'])
        self.ptt_key = ShortcutField(self.settings['ptt_key'])
        for field in (self.replay_key, self.record_key, self.ptt_key):
            field.capturing.connect(self.shortcut_capture)
        form.addRow('Save replay', self.replay_key)
        form.addRow('Start / stop recording', self.record_key)
        form.addRow('Push to talk', self.ptt_key)
        form = section('Notifications', 'SILENT ON-SCREEN NOTIFICATIONS', 'Small visual confirmations that disappear automatically. No sounds and no keyboard-focus changes.')
        self.notification_enabled = QCheckBox('Show capture notifications')
        self.notification_enabled.setChecked(self.settings.get('notifications_enabled', True))
        form.addRow(self.notification_enabled)
        self.notification_corner = QComboBox()
        self.notification_corner.addItems(['Top right', 'Top left', 'Bottom right', 'Bottom left'])
        self.notification_corner.setCurrentText(self.settings.get('notification_corner', 'Top right'))
        form.addRow('Corner', self.notification_corner)
        self.notification_screen = QComboBox()
        self.notification_screen.addItem('Display with the active app', '')
        for screen in QApplication.screens():
            self.notification_screen.addItem(screen.name(), screen.name())
        self.notification_screen.setCurrentIndex(max(0, self.notification_screen.findData(self.settings.get('notification_screen', ''))))
        form.addRow('Display', self.notification_screen)
        self.notification_seconds = self.spin(2, 10, self.settings.get('notification_seconds', 3), ' sec')
        form.addRow('Duration', self.notification_seconds)
        form.addRow(self.button('Preview notification', self.test_notification))
        note = QLabel('Errors stay visible for at least six seconds. Borderless games are recommended; exclusive fullscreen may hide desktop overlays.')
        note.setWordWrap(True)
        note.setObjectName('muted')
        form.addRow(note)
        row = QHBoxLayout()
        note = QLabel('Stop replay and recording before applying settings.')
        note.setObjectName('muted')
        row.addWidget(note, 1)
        row.addWidget(self.button('Apply settings', self.apply_settings, 'primary'))
        layout.addLayout(row)
        self.tabs.addTab(page, 'Settings')

    def build_clips(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        from .gallery import RecentGallery
        row = QHBoxLayout()
        row.addWidget(self.button('Browse all clips', self.browse_library, 'quiet'))
        row.addWidget(self.button('Open editor', self.open_editor, 'quiet'))
        row.addStretch()
        row.addWidget(self.button('Register game folder', self.map_game, 'quiet'))
        layout.addLayout(row)
        self.gallery = RecentGallery(self.settings['output'], self)
        self.gallery.opened.connect(self.watch_clips)
        self.quick_player = None
        self.clips = self.gallery.list
        layout.addWidget(self.gallery, 1)
        self.session_saves = 0
        self.clip_count = QLabel('SAVED THIS SESSION  /  0')
        self.clip_count.setObjectName('muted')
        layout.addWidget(self.clip_count)
        self.tabs.addTab(page, 'Clips & games')

    def watch_clips(self, clips, index):
        if self.quick_player is None:
            from .gallery import QuickPlayer
            self.quick_player = QuickPlayer(self)
            self.quick_player.edit_requested.connect(self.open_editor)
        self.quick_player.open_clips(clips, index)

    def browse_library(self):
        from .clip_browser import ClipBrowser
        from .gallery import gallery_tools
        ffmpeg, _ = gallery_tools()
        browser = ClipBrowser(Path(self.settings['output']), ffmpeg, DATA/'thumbnails', self)
        if browser.exec() and browser.selected_path:
            clips = sorted(browser.clips, key=lambda c: c['modified'], reverse=True)
            index = next((i for i,c in enumerate(clips) if c['path'] == browser.selected_path), 0)
            self.watch_clips(clips, index)
        browser.deleteLater()

    def notification_options(self):
        return dict(notifications_enabled=self.notification_enabled.isChecked(),
                    notification_corner=self.notification_corner.currentText(),
                    notification_screen=self.notification_screen.currentData() or '',
                    notification_seconds=self.notification_seconds.value())

    def test_notification(self):
        previous = self.notifications.settings
        self.notifications.settings = dict(self.settings, **self.notification_options())
        self.notifications.timer.stop()
        self.notifications.queue.clear()
        self.notifications.push('Clip saved', 'Your highlight is ready to edit', force=True)
        self.notifications.settings = previous

    def capture_notice(self, notice):
        if not self.closing:
            self.notifications.push(notice['title'], notice.get('detail', ''), notice.get('tone', 'success'))

    def open_editor(self, path=None):
        if self.editor is None:
            from .editor import Editor
            self.editor = Editor(self)
        self.editor.clips_folder = Path(self.settings["output"])
        self.editor.showNormal()
        self.editor.raise_()
        self.editor.activateWindow()
        if isinstance(path, str):
            self.editor.open_clip(path)

    def submit(self, command, data=None):
        if self.capturing_shortcut and command in ('save_replay', 'toggle_record'):
            return
        if self.preview:
            self.log("UI preview only. Run on Windows to capture.")
            return
        if not self.closing:
            self.engine.submit(command, data)
        if command == "connect":
            self.connect_btn.setEnabled(False)
            self.status.setText("Connecting recorder...")

    def tick(self):
        if self.preview or self.closing:
            return
        mode, volume = self.mode.currentText(), self.volume.value()
        try:
            pressed = held(self.settings["ptt_key"]) if mode == "Push to talk" and not self.capturing_shortcut else False
        except ValueError:
            pressed = False
        value = (mode, volume, pressed)
        if value != self.last_mic:
            self.engine.submit("mic", value)
            self.last_mic = value
            self.settings.update(mic_mode=mode, mic_volume=volume)

    def update_state(self, data):
        if data["connected"] and not self.connected:
            self.last_mic = None
        self.connected = data["connected"]
        self.connection_badge.setText("ENGINE READY" if self.connected else "ENGINE OFFLINE")
        self.connect_btn.setEnabled(not self.connected)
        self.connect_btn.setText("Engine running" if self.connected else "Start engine")
        self.replay_btn.setEnabled(self.connected)
        self.record_btn.setEnabled(self.connected)
        if not self.connected:
            self.status.setText("Recorder offline  •  Start the engine to reconnect")
            self.recording = self.replay = False
            self.record_hint.setText("Capture stopped")
            self.record_metric.setText('00:00:00')
            self.replay_btn.setText('Start replay')
            self.record_btn.setText('Start recording')
            self.record_btn.setProperty('active', False)
            self.record_btn.style().unpolish(self.record_btn)
            self.record_btn.style().polish(self.record_btn)
            self.save_btn.setEnabled(False)
            return
        self.recording, self.replay = data["recording"], data["replay"]
        self.last_app = data["app"]
        self.category.setText(f"Saving to  /  {self.last_app['category']}")
        self.replay_btn.setText("Stop replay" if self.replay else "Start replay")
        self.save_btn.setEnabled(self.replay and not data.get("saving"))
        self.record_btn.setText("Stop recording" if self.recording else "Start recording")
        self.record_metric.setText(data["timecode"] if self.recording else "00:00:00")
        self.record_hint.setText("Recording in progress" if self.recording else "Capture from start to finish")
        self.replay_metric.setText(f"{data['replay_seconds']} sec")
        self.record_btn.setProperty("active", self.recording)
        self.record_btn.style().unpolish(self.record_btn)
        self.record_btn.style().polish(self.record_btn)
        recording = f"Recording {data['timecode']}" if self.recording else "Manual recording off"
        capture = {0: "Automatic capture", 1: "DXGI capture", 2: "Windows Graphics Capture"}.get(data.get("capture_method"), "Screen capture") if data.get("capture_attached") else "Screen capture idle"
        self.status.setText(f"{'Replay ON' if self.replay else 'Replay off'}  •  {recording}  •  {capture}")
        seconds, buffered = data["replay_seconds"], data.get("buffered")
        warmup = f" • Buffer warming up: {min(int(buffered), seconds)} / {seconds}s" if self.replay and buffered is not None and buffered < seconds else ""
        self.buffer_label.setText(f"Replay length: {seconds} seconds{warmup}")
        self.mic_label.setText(("Mic muted" if data.get("muted") else "Mic live") + f" • Push-to-talk key: {self.settings['ptt_key']}")

    def update_devices(self, data):
        self.device_data = data
        for control, items, selected in [(self.mic, data["microphones"], self.settings["mic_device"]),
                                         (self.output_device, data["outputs"], self.settings["desktop_device"]),
                                         (self.monitor, data["monitors"], self.settings["monitor_value"])]:
            control.clear()
            for item in items:
                if item.get("itemEnabled", True):
                    control.addItem(item["itemName"], item["itemValue"])
            index = control.findData(selected)
            if index >= 0:
                control.setCurrentIndex(index)

    def update_meters(self, levels):
        for name, meter in [(MIC, self.mic_meter), (DESKTOP, self.desktop_meter)]:
            db = 20 * math.log10(max(float(levels.get(name, 0)), .001))
            meter.setValue(round(max(0, min(100, (db + 60) / 60 * 100))))

    def log(self, text):
        self.messages.appendPlainText(text)

    def show_error(self, text):
        self.log("ERROR: " + text)
        self.connect_btn.setEnabled(not self.connected)
        self.status.setText("Action failed • See the message below")
        # Output-stop events already have a specific error notification.
        if 'stopped with error' not in text.lower() and 'native recorder connection lost' not in text.lower():
            self.notifications.push('ClipNest needs attention', text, 'error')

    def clip_saved(self, path):
        self.log("Saved: " + path)
        self.session_saves += 1
        self.clip_count.setText(f"SAVED THIS SESSION  /  {self.session_saves}")
        import time
        source = Path(path)
        try:
            stat = source.stat()
            size, modified = stat.st_size, stat.st_mtime
        except OSError:
            size, modified = 0, time.time()
        clip = dict(path=path, name=source.name, folder=source.parent.name, size=size, modified=modified)
        self.gallery.listed([clip]+[c for c in self.gallery.clips if c['path'] != path][:23], [])
        QTimer.singleShot(150, self.gallery.refresh)

    def update_shortcut_label(self):
        self.shortcut_label.setText(f"Save replay: {self.settings['replay_key']}     Record: {self.settings['record_key']}")

    def register_hotkeys(self):
        if self.capturing_shortcut or self.closing:
            return
        try:
            self.hotkeys.configure(self.settings["replay_key"], self.settings["record_key"])
        except ValueError as exc:
            self.show_error(str(exc))

    def shortcut_capture(self, active):
        self.capturing_shortcut = active
        if active:
            self.hotkeys.close()
        elif not self.preview:
            self.register_hotkeys()

    def apply_settings(self):
        try:
            replay_key, record_key, ptt_key = [field.text().strip() for field in (self.replay_key, self.record_key, self.ptt_key)]
            parsed = []
            for label, value in (("Save replay shortcut", replay_key), ("Record shortcut", record_key), ("Push-to-talk key", ptt_key)):
                try:
                    parsed.append(parse_hotkey(value))
                except ValueError as exc:
                    raise ValueError(f"Settings not applied: {label}: {exc}") from exc
            if len(set(parsed)) != 3:
                raise ValueError("Use different keys for replay, recording, and push to talk.")
            data = copy.deepcopy(self.settings)
            data.update(output=self.output.text().strip(), replay_seconds=self.seconds.value(), replay_mode=self.replay_mode.currentData(),
                        encoder=self.encoder.currentText(), capture_method=self.capture_method.currentData(), width=self.width.value(), height=self.height.value(),
                        fps=int(self.fps.currentText()), bitrate=self.bitrate.value(),
                        mic_device=self.mic.currentData() or self.settings["mic_device"],
                        desktop_device=self.output_device.currentData() or self.settings["desktop_device"],
                        replay_key=replay_key, record_key=record_key, ptt_key=ptt_key)
            data.update(self.notification_options())
            if self.monitor.currentData() is not None:
                data.update(monitor_value=self.monitor.currentData(), monitor_property=self.device_data.get("monitor_property", "monitor_id"))
            self.submit("apply", data)
        except ValueError as exc:
            self.show_error(str(exc))

    def settings_applied(self, data):
        self.settings = copy.deepcopy(data)
        self.notifications.settings = self.settings
        self.gallery.root = Path(data["output"])
        self.gallery.refresh()
        if self.editor is not None:
            self.editor.clips_folder = Path(data["output"])
        self.update_shortcut_label()
        self.register_hotkeys()
        self.last_mic = None

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "Choose clips folder", self.output.text())
        if path:
            self.output.setText(path)

    def map_game(self):
        path = self.last_app.get("exe")
        if not path:
            self.show_error("Start the engine, focus the game, then return here.")
            return
        name, ok = QInputDialog.getText(self, "Register a game", f"Folder name for {Path(path).name}:")
        if ok and name.strip():
            self.settings["games"][path.casefold()] = name.strip()
            self.submit("map_game", (path, name.strip()))

    def open_path(self, path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_folder(self):
        path = Path(self.settings["output"])
        path.mkdir(parents=True, exist_ok=True)
        self.open_path(path)

    def show_normal(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def hide_to_tray(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
        else:
            self.showMinimized()

    def closeEvent(self, event):
        if self.editor is not None and not self.editor.can_close():
            event.ignore()
            return
        if self.editor is not None:
            self.editor.hide()
        if self.allow_close or self.preview:
            self.gallery.stop()
            if self.quick_player is not None:
                self.quick_player.close()
            self.hotkeys.close()
            self.notifications.close()
            event.accept()
            return
        event.ignore()
        if not self.closing:
            self.closing = True
            self.status.setText("Finishing recordings and closing the recorder...")
            self.engine.submit("shutdown")

    def shutdown_complete(self, success):
        if success:
            self.engine.wait(3000)
            self.allow_close = True
            self.tray.hide()
            self.close()
            QApplication.instance().quit()
        else:
            self.closing = False
            self.show_normal()
