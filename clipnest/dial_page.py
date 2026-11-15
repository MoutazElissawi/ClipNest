"""The Dial capture page, used when the active theme asks for the "dial" layout."""
from __future__ import annotations
import shutil
import time
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QVariantAnimation, QEasingCurve, QSize, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QSlider,
    QProgressBar, QSizePolicy)

from .branding import app_icon
from .external_theme import DEFAULT_COLORS, active_palette


def theme_color(role):
    return QColor((active_palette() or {}).get('colors', DEFAULT_COLORS)[role])


class SlideSwitch(QWidget):
    """A segmented switch whose thumb slides between options. Click an option, drag the thumb or use the arrow keys."""
    changed = Signal(int)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.options = list(options)
        self.index = 0
        self.position = 0.0  # where the thumb is drawn, in options; fractional while it slides or is dragged
        self.press_x = None
        self.dragging = False
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(320)
        self.animation.setEasingCurve(QEasingCurve.Type.OutBack)
        self.animation.valueChanged.connect(self.slide_to)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(38)

    def sizeHint(self):
        widest = max(self.fontMetrics().horizontalAdvance(option) for option in self.options)
        return QSize((widest + 28) * len(self.options) + 6, 38)

    def slide_to(self, value):
        self.position = float(value)
        self.update()

    def set_index(self, index, animate=True):
        """Show an option without emitting changed. -1 shows no option, for a value the switch does not offer."""
        self.index = index
        if index < 0:
            self.animation.stop()
            self.update()
            return
        if animate and self.isVisible():
            self.animation.stop()
            self.animation.setStartValue(self.position)
            self.animation.setEndValue(float(index))
            self.animation.start()
        else:
            self.slide_to(index)

    def choose(self, index):
        index = max(0, min(len(self.options) - 1, index))
        changed = index != self.index
        self.set_index(index)
        if changed:
            self.changed.emit(index)

    def option_at(self, x):
        """The thumb position for a pointer x, centred on the pointer."""
        width = (self.width() - 6) / len(self.options)
        return max(0.0, min(len(self.options) - 1.0, (x - 3) / width - .5))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.press_x = event.position().x()
            self.dragging = False

    def mouseMoveEvent(self, event):
        if self.press_x is None:
            return
        if abs(event.position().x() - self.press_x) > 3:
            self.dragging = True
            self.animation.stop()
        if self.dragging:
            self.slide_to(self.option_at(event.position().x()))

    def mouseReleaseEvent(self, event):
        if self.press_x is None:
            return
        self.press_x = None
        self.dragging = False
        self.choose(round(self.option_at(event.position().x())))

    def keyPressEvent(self, event):
        step = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1}.get(event.key())
        if step and self.isEnabled():
            self.choose(max(0, self.index) + step)
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(.45)
        rect = QRectF(self.rect())
        radius = rect.height() / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme_color('raised'))
        painter.drawRoundedRect(rect, radius, radius)
        width = (rect.width() - 6) / len(self.options)
        if self.index >= 0:
            thumb = QRectF(3 + self.position * width, 3, width, rect.height() - 6)
            painter.setBrush(QColor(0, 0, 0, 70))
            painter.drawRoundedRect(thumb.translated(0, 1.5), radius - 3, radius - 3)
            painter.setBrush(theme_color('accent'))
            painter.drawRoundedRect(thumb, radius - 3, radius - 3)
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(theme_color('accent'), 1.5))
            painter.drawRoundedRect(rect.adjusted(.75, .75, -.75, -.75), radius, radius)
        font = QFont(self.font())
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        for i, option in enumerate(self.options):
            on = self.index >= 0 and round(self.position) == i
            painter.setPen(theme_color('accent_text' if on else 'muted'))
            painter.drawText(QRectF(3 + i * width, 0, width, rect.height()), Qt.AlignmentFlag.AlignCenter, option)


class ReplayDial(QWidget):
    """The ClipNest mark inside a ring that is lit while Instant Replay holds the last seconds."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.on = False
        self.seconds = 90
        self.logo = app_icon().pixmap(256, 256)
        self.setMinimumSize(260, 260)
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)  # square, so the buttons sit right under the ring
        self.setSizePolicy(policy)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return min(width, 460)

    def sizeHint(self):
        return QSize(400, 400)

    def show_replay(self, on, seconds):
        if (on, seconds) != (self.on, self.seconds):
            self.on, self.seconds = on, seconds
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        side = min(self.width(), self.height()) - 4
        ring = max(10, side * .045)
        box = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side).adjusted(ring / 2, ring / 2, -ring / 2, -ring / 2)
        painter.setPen(QPen(theme_color('accent' if self.on else 'raised'), ring))
        painter.drawEllipse(box)
        logo = side * .3
        centre = box.center()
        painter.drawPixmap(QRectF(centre.x() - logo / 2, centre.y() - logo * .78, logo, logo).toRect(), self.logo)
        font = QFont(self.font())
        font.setPointSizeF(max(12, side * .052))
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(theme_color('accent' if self.on else 'muted'))
        line = side * .09
        painter.drawText(QRectF(box.left(), centre.y() + logo * .32, box.width(), line), Qt.AlignmentFlag.AlignCenter,
                         'Replay on' if self.on else 'Replay off')
        font.setPointSizeF(max(9, side * .032))
        font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)
        painter.setPen(theme_color('muted'))
        painter.drawText(QRectF(box.left(), centre.y() + logo * .32 + line, box.width(), line * .7), Qt.AlignmentFlag.AlignCenter,
                         f'Last {self.seconds} s')


CARD_STYLE = """
QWidget#dialCard { background: #101010; border: 1px solid #3b3b3b; border-radius: 16px; }
QWidget#dialCard QLabel { background: transparent; }
QLabel#dialHeading { color: #aaaaaa; font-weight: 600; }
QLabel#dialTimer { font-size: 26pt; font-weight: 700; }
QLabel#dialValue { font-size: 18pt; font-weight: 700; }
QLabel#dialFact { color: #aaaaaa; }
QLabel#dialFactValue { font-weight: 600; }
QLabel#dialTitle { font-size: 16pt; font-weight: 700; }
QPushButton#dialRound { border-radius: 22px; min-height: 44px; padding: 0 22px; font-size: 11pt; font-weight: 600; }
QPushButton#dialSave { border-radius: 22px; min-height: 44px; padding: 0 22px; font-size: 11pt; font-weight: 700;
    background: #76b900; color: #101500; border: 1px solid #76b900; }
QPushButton#dialSave:disabled { background: #272727; color: #aaaaaa; border-color: #3b3b3b; }
QProgressBar { background: #272727; border: 0; border-radius: 4px; max-height: 8px; }
QProgressBar::chunk { background: #76b900; border-radius: 4px; }
"""

CAPTURE_TARGETS = ('display', 'games')
MIC_MODES = ('Always on', 'Push to talk', 'Muted')


class DialPage(QWidget):
    """Capture controls around the replay dial. It drives the main window's existing controls, so both layouts
    stay in step and use the same engine commands."""

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.held_target = None  # a capture target the user picked, kept on screen until the engine reports it
        self.held_until = 0.0
        self.space_checked = 0.0
        self.setStyleSheet(CARD_STYLE)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 10, 6)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(14)
        grid.setColumnStretch(1, 1)
        self.title = QLabel('Capture')
        self.title.setObjectName('dialTitle')
        grid.addWidget(self.title, 0, 0, 1, 3)

        left = QVBoxLayout()
        left.setSpacing(14)
        card, body = self.card('Recording')
        self.timer = QLabel('00:00:00')
        self.timer.setObjectName('dialTimer')
        body.addWidget(self.timer)
        self.record = QPushButton('Start recording')
        self.record.setObjectName('record')
        self.record.clicked.connect(lambda: window.submit('toggle_record'))
        body.addWidget(self.record)
        left.addWidget(card)
        card, body = self.card('Capture')
        self.capture = SlideSwitch(['Screen', 'Game only'])
        self.capture.changed.connect(self.capture_chosen)
        body.addWidget(self.capture)
        self.facts = {}
        for name in ('Resolution', 'Frame rate', 'Bitrate', 'Encoder'):
            row = QHBoxLayout()
            label = QLabel(name)
            label.setObjectName('dialFact')
            value = QLabel()
            value.setObjectName('dialFactValue')
            row.addWidget(label)
            row.addStretch()
            row.addWidget(value)
            body.addLayout(row)
            self.facts[name] = value
        left.addWidget(card)
        left.addStretch()
        grid.addLayout(left, 1, 0)

        middle = QVBoxLayout()
        middle.setSpacing(18)
        middle.addStretch(1)
        self.dial = ReplayDial()
        middle.addWidget(self.dial)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.replay = QPushButton('Start replay')
        self.replay.setObjectName('dialRound')
        self.replay.clicked.connect(lambda: window.submit('toggle_replay'))
        self.save = QPushButton('Save clip')
        self.save.setObjectName('dialSave')
        self.save.clicked.connect(lambda: window.submit('save_replay'))
        buttons.addWidget(self.replay)
        buttons.addWidget(self.save)
        buttons.addStretch()
        middle.addLayout(buttons)
        middle.addStretch(1)
        grid.addLayout(middle, 1, 1)

        right = QVBoxLayout()
        right.setSpacing(14)
        card, body = self.card('Microphone')
        self.mic = SlideSwitch(MIC_MODES)
        self.mic.changed.connect(lambda i: window.mode.setCurrentText(MIC_MODES[i]))
        body.addWidget(self.mic)
        gain = QHBoxLayout()
        label = QLabel('Gain')
        label.setObjectName('dialFact')
        self.gain = QSlider(Qt.Orientation.Horizontal)
        self.gain.setRange(0, 200)
        self.gain_label = QLabel()
        gain.addWidget(label)
        gain.addWidget(self.gain, 1)
        gain.addWidget(self.gain_label)
        body.addLayout(gain)
        right.addWidget(card)
        card, body = self.card('Free space')
        self.space = QLabel('–')
        self.space.setObjectName('dialValue')
        self.space_bar = QProgressBar()
        self.space_bar.setTextVisible(False)
        body.addWidget(self.space)
        body.addWidget(self.space_bar)
        right.addWidget(card)
        card, body = self.card('Audio')
        self.meters = {}
        for name in ('Microphone', 'Desktop'):
            row = QHBoxLayout()
            label = QLabel(name)
            label.setObjectName('dialFact')
            label.setMinimumWidth(84)
            meter = QProgressBar()
            meter.setTextVisible(False)
            meter.setRange(0, 100)
            row.addWidget(label)
            row.addWidget(meter, 1)
            body.addLayout(row)
            self.meters[name] = meter
        right.addWidget(card)
        right.addStretch()
        grid.addLayout(right, 1, 2)
        for column in (0, 2):
            grid.setColumnMinimumWidth(column, 280)

        window.mode.currentTextChanged.connect(self.mic_mode_shown)
        self.mic_mode_shown(window.mode.currentText(), animate=False)
        self.gain.setValue(window.volume.value())
        self.gain_label.setText(f'{window.volume.value()}%')
        self.gain.valueChanged.connect(window.volume.setValue)
        window.volume.valueChanged.connect(self.gain_shown)
        self.show_settings(window.settings)
        self.show_state(None)

    def card(self, heading):
        card = QWidget()
        card.setObjectName('dialCard')
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        body = QVBoxLayout(card)
        body.setContentsMargins(16, 14, 16, 16)
        body.setSpacing(10)
        label = QLabel(heading)
        label.setObjectName('dialHeading')
        body.addWidget(label)
        return card, body

    def mic_mode_shown(self, mode, animate=True):
        self.mic.set_index(MIC_MODES.index(mode) if mode in MIC_MODES else -1, animate)

    def gain_shown(self, value):
        self.gain.blockSignals(True)
        self.gain.setValue(value)
        self.gain.blockSignals(False)
        self.gain_label.setText(f'{value}%')

    def capture_chosen(self, index):
        target = CAPTURE_TARGETS[index]
        self.held_target, self.held_until = target, time.monotonic() + 15
        if not self.window.switch_capture(target):
            self.held_target = None
            self.show_target(self.window.settings.get('capture_target', 'display'))

    def show_target(self, target):
        self.capture.set_index(CAPTURE_TARGETS.index(target) if target in CAPTURE_TARGETS else -1)

    def show_settings(self, settings):
        self.facts['Resolution'].setText(f"{settings['width']} × {settings['height']}")
        self.facts['Frame rate'].setText(f"{settings['fps']} fps")
        self.facts['Bitrate'].setText(f"{settings['bitrate']:,} kbps")
        self.facts['Encoder'].setText(settings['encoder'])
        self.check_space(settings, force=True)

    def check_space(self, settings, force=False):
        if not force and time.monotonic() - self.space_checked < 10:
            return
        self.space_checked = time.monotonic()
        try:
            usage = shutil.disk_usage(Path(settings['output']).anchor or settings['output'])
        except OSError:
            self.space.setText('Unavailable')
            self.space_bar.setValue(0)
            return
        self.space.setText(f'{usage.free / 1024**3:,.0f} GB')
        self.space_bar.setValue(round(usage.used / usage.total * 100))

    def show_meter(self, name, value):
        self.meters[name].setValue(value)

    def show_state(self, data):
        """Mirror the recorder state the window received. None means the recorder is offline."""
        connected = bool(data and data.get('connected'))
        replay = connected and data['replay']
        recording = connected and data['recording']
        seconds = (data or {}).get('replay_seconds') or self.window.settings['replay_seconds']
        self.dial.show_replay(replay, seconds)
        self.replay.setText('Stop replay' if replay else 'Start replay')
        self.replay.setEnabled(connected)
        self.save.setEnabled(replay and not data.get('saving'))
        self.record.setEnabled(connected)
        self.record.setText('Stop recording' if recording else 'Start recording')
        if self.record.property('active') != recording:
            self.record.setProperty('active', recording)
            self.record.style().unpolish(self.record)
            self.record.style().polish(self.record)
        self.timer.setText(data['timecode'] if recording else '00:00:00')
        app = (data or {}).get('app') or {}
        self.title.setText(f"Saving to {app['category']}" if app.get('category') else 'Capture')
        target = (data or {}).get('capture_target') or self.window.settings.get('capture_target', 'display')
        if self.held_target and (target == self.held_target or time.monotonic() > self.held_until):
            self.held_target = None
        if not self.held_target and not self.capture.dragging:
            self.show_target(target)
        self.check_space(self.window.settings)
