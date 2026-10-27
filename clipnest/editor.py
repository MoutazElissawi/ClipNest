from __future__ import annotations
import json
from pathlib import Path
import threading
import tempfile
from fractions import Fraction

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QSize
from PySide6.QtGui import QImage, QIcon
from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QDoubleSpinBox, QComboBox, QTableWidget, QTableWidgetItem, QCheckBox,
    QDialog, QFormLayout, QSpinBox, QDialogButtonBox, QSplitter, QInputDialog,
    QLayout, QSizePolicy, QGridLayout)

from .config import DATA, atomic_json
from .media import (tools_path, probe, available_encoders, Edit, export_clip, ENCODERS, COPY, estimated_size, ExportETA, EncoderProbeCache,
                    add_range, remove_range, keep_only_range)
from .preview import VideoCanvas, Waveform
from .editor_assets import waveform
from .export_progress import ExportProgressBar


AUDIO_FORMATS = ('mp3', 'm4a', 'wav', 'flac')


class Job(QThread):
    result = Signal(object)
    failed = Signal(str)
    progress = Signal(int)

    def __init__(self, action, parent):
        super().__init__(parent)
        self.action = action
        self.cancel = threading.Event()

    def run(self):
        try:
            self.result.emit(self.action(self))
        except Exception as exc:
            self.failed.emit(str(exc))


from .desktop import DefaultAudioOutput, show_centered, ItemDelegate, SeekSlider
from .window_frame import DesktopWindow
from .playback_lifecycle import PlaybackLifecycle


class Editor(DesktopWindow):
    exportCompleted = Signal(str)
    exportFolderChanged = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('ClipNest • Clip editor')
        from .theme import apply_theme
        theme = getattr(parent, 'current_theme', parent.settings.get('ui_theme', 'dark')) if parent is not None and hasattr(parent, 'settings') else 'dark'
        apply_theme(self, theme, '\nQPushButton { padding: 6px 9px; }')
        self.resize(1560, 1000)
        self.setMinimumSize(1000, 600)
        self.clips_folder = Path(parent.settings["output"]) if parent is not None and hasattr(parent, "settings") else Path.home()/"Videos/ClipNest"
        self.encoder_errors = {}
        self.encoder_probe = EncoderProbeCache(lambda path: available_encoders(path))
        self.last_export_path = None
        self.info = None
        self.job = None
        self.analysis_jobs = []
        self.wave_token = 0
        self.mutes = {}  # audio stream index -> muted (start, end) ranges, source seconds
        self.preview_temp = None
        self.crop = None
        self.colors = (0.0, 1.0, 1.0)
        self.preferences = DATA / 'editor.json'
        try:
            self.prefs = json.loads(self.preferences.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.prefs = {}
        if not isinstance(self.prefs, dict):
            self.prefs = {}
        raw_presets = self.prefs.get('export_presets', {})
        self.prefs['export_presets'] = {name: choice for name, choice in raw_presets.items()
            if isinstance(name, str) and name.strip() and self.valid_choice(choice)} if isinstance(raw_presets, dict) else {}
        self.quick_presets = {
            'Quick: 1080p60': dict(encoder='CPU H.264', bitrate=16000, resolution=[1920,1080], fps=60),
            'Quick: Smaller 720p30': dict(encoder='CPU H.264', bitrate=5000, resolution=[1280,720], fps=30),
            'Quick: Vertical fit 1080p60': dict(encoder='CPU H.264', bitrate=12000, resolution=[1080,1920], fps=60),
        }
        self.export_choice = self.prefs.get('last_export')
        if not self.valid_choice(self.export_choice):
            self.export_choice = None
        active = self.prefs.get('active_export_preset', '')
        if not isinstance(active, str) or (active not in self.quick_presets and self.prefs['export_presets'].get(active) != self.export_choice):
            self.prefs['active_export_preset'] = ''
        self.available_export_encoders = []
        self.player = QMediaPlayer(self)
        self.audio_output = DefaultAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 12, 16, 12)
        top = QHBoxLayout()
        heading = QLabel('Clip editor')
        heading.setObjectName('pageTitle')
        top.addWidget(heading)
        top.addStretch()
        subtitle = QLabel('TRIM  /  CROP  /  EXPORT')
        subtitle.setObjectName('eyebrow')
        top.addWidget(subtitle)
        layout.addLayout(top)
        self.caption = QLabel('Drop a completed clip onto the preview, or use Open / Browse clips.')
        self.caption.setObjectName('muted')
        self.caption.setWordWrap(True)
        root_layout = layout
        split = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(split, 1)
        preview = QWidget()
        layout = QVBoxLayout(preview)
        layout.setContentsMargins(0, 0, 10, 0)
        split.addWidget(preview)
        file_row = QHBoxLayout()
        self.caption.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        file_row.addWidget(self.caption, 5)
        self.open_clip_button = QPushButton('Open clip')
        self.open_clip_button.clicked.connect(self.choose_clip)
        self.browse_clips_button = QPushButton('Browse clips')
        self.browse_clips_button.clicked.connect(self.browse_clips)
        for button in (self.open_clip_button, self.browse_clips_button):
            button.setMinimumWidth(140)
            file_row.addWidget(button, 2)
        file_row.addStretch(1)
        layout.addLayout(file_row)
        sidebar = QWidget()
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(10, 0, 0, 0)
        side.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        sidebar.setMinimumWidth(490)
        split.addWidget(sidebar)
        split.setStretchFactor(0, 7)
        split.setStretchFactor(1, 3)
        split.setSizes([1020, 460])
        self.video = VideoCanvas()
        self.video.setMinimumHeight(180)
        self.video_sink = QVideoSink(self)
        self.video_sink.videoFrameChanged.connect(self.video.frame_changed)
        self.player.setVideoSink(self.video_sink)
        self.playback_lifecycle = PlaybackLifecycle(self, self.player, self.video)
        self.video.clipDropped.connect(self.open_clip)
        layout.addWidget(self.video, 1)
        def icon_button(name, tooltip, callback, large=False):
            button = QPushButton()
            button.setIcon(QIcon(str(Path(__file__).parent/'assets'/f'{name}.svg')))
            button.setIconSize(QSize(30, 30) if large else QSize(20, 20))
            button.setFixedSize(64, 40) if large else button.setFixedSize(40, 32)
            button.setObjectName('transport' if large else 'compact')
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
            button.clicked.connect(callback)
            return button
        transport = QHBoxLayout()
        transport.setSpacing(8)
        self.play_button = icon_button('play', 'Play / pause', self.play_pause, True)
        transport.addWidget(self.play_button)
        def playback_icon(state):
            name = 'pause' if state == QMediaPlayer.PlaybackState.PlayingState else 'play'
            self.play_button.setIcon(QIcon(str(Path(__file__).parent/'assets'/f'{name}.svg')))
        self.player.playbackStateChanged.connect(playback_icon)
        for label, tooltip, callback in [('Start', 'Set start here (A)', self.mark_start), ('End', 'Set end here (B)', self.mark_end)]:
            button = QPushButton(label)
            button.setFixedSize(80, 32)
            button.setToolTip(tooltip)
            button.clicked.connect(callback)
            transport.addWidget(button)
        transport.addWidget(icon_button('jump-a', 'Go to A (selected start)', lambda: self.jump_marker(self.start.value())))
        transport.addWidget(icon_button('jump-b', 'Go to B (selected end)', lambda: self.jump_marker(self.end.value())))
        transport.addWidget(icon_button('crop', 'Drag crop corners', self.visual_crop))
        steps = QHBoxLayout()
        steps.setSpacing(8)
        for text, direction in [('−1 frame', -1), ('+1 frame', 1)]:
            button = QPushButton(text)
            button.setObjectName('compact')
            button.setFixedSize(80, 32)
            button.setToolTip('Previous frame' if direction < 0 else 'Next frame')
            button.setAccessibleName(button.toolTip())
            button.clicked.connect(lambda checked=False, d=direction: self.step_frame(d))
            steps.addWidget(button)
        transport.addLayout(steps)
        selection = QPushButton('Play selection')
        selection.clicked.connect(self.play_selection)
        transport.addWidget(selection)
        transport.addStretch()
        self.clock = QLabel('0.0 / 0.0 s')
        preview_options_clock = self.clock
        preview_options = QHBoxLayout()
        self.show_edits = QCheckBox('Show crop / colors live')
        self.show_edits.setChecked(True)
        self.show_edits.toggled.connect(self.update_preview)
        preview_options.addWidget(self.show_edits)
        preview_options.addStretch()
        preview_options.addWidget(preview_options_clock)
        self.speed = QComboBox()
        self.speed.addItems(['0.25×', '0.5×', '1×', '1.5×', '2×'])
        self.speed.setCurrentIndex(2)
        self.speed.currentIndexChanged.connect(lambda i: self.player.setPlaybackRate((.25, .5, 1., 1.5, 2.)[i]))
        preview_options.addWidget(QLabel('Speed'))
        preview_options.addWidget(self.speed)
        layout.addLayout(preview_options)
        layout.addLayout(transport)
        self.wave = Waveform()
        self.wave.seek.connect(lambda ms: self.jump_marker(ms/1000))
        self.wave.region_changed.connect(self.region_changed)
        layout.addWidget(self.wave)
        # Per-track audio edits: silence parts of the track shown in the waveform.
        region_row = QHBoxLayout()
        self.region_label = QLabel('Track audio: Shift+drag the waveform to select a range')
        self.region_label.setObjectName('muted')
        self.region_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        region_row.addWidget(self.region_label, 1)
        self.region_buttons = []
        for text, tip, callback, needs_region in (
                ('Use A–B', 'Select the Start–End export range on the waveform', self.region_from_markers, False),
                ('Mute', 'Silence the selected range on this track (cut it out of this track only)', self.mute_region, True),
                ('Keep only', 'Trim this track: silence everything outside the selected range', self.keep_region, True),
                ('Unmute', 'Restore audio in the selected range on this track', self.unmute_region, True),
                ('Clear', 'Remove all muted ranges from this track', self.clear_track_mutes, False)):
            button = QPushButton(text)
            button.setToolTip(tip)
            button.clicked.connect(callback)
            region_row.addWidget(button)
            self.region_buttons.append((button, needs_region))
        layout.addLayout(region_row)
        self.scrub = SeekSlider(Qt.Orientation.Horizontal)
        self.scrub.setRange(0, 0)
        self.scrub.sliderMoved.connect(self.player.setPosition)
        layout.addWidget(self.scrub)
        row = QHBoxLayout()
        self.start, self.end = self.seconds(), self.seconds()
        self.start.valueChanged.connect(self.update_timeline)
        self.end.valueChanged.connect(self.update_timeline)
        row.addWidget(QLabel('Start'))
        row.addWidget(self.start)
        row.addWidget(QLabel('End'))
        row.addWidget(self.end)
        self.start.setFixedWidth(125)
        self.end.setFixedWidth(125)
        row.addStretch()
        layout.addLayout(row)
        self.selection_playing = False
        audio_heading = QLabel('AUDIO • Select tracks and adjust volume')
        side.addWidget(audio_heading)
        self.tracks = QTableWidget(0, 4)
        self.tracks.setHorizontalHeaderLabels(['Keep', 'Audio track', 'Gain %', 'Listen'])
        self.tracks.horizontalHeader().setStretchLastSection(True)
        self.tracks.setColumnWidth(0, 55)
        self.tracks.setColumnWidth(1, 175)
        self.tracks.setColumnWidth(2, 80)
        self.tracks.verticalHeader().setDefaultSectionSize(46)
        self.tracks.verticalHeader().setVisible(False)
        self.tracks.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.tracks.setItemDelegate(ItemDelegate(self.tracks))
        self.tracks.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tracks.setMinimumHeight(205)
        self.tracks.setMaximumHeight(210)
        side.addWidget(self.tracks)
        self.remix = QCheckBox('Combine selected audio into one track')
        self.remix.toggled.connect(self.remix_changed)
        side.addWidget(self.remix)
        note = QLabel('Listen solo selects the waveform track. Combining excludes the existing Mix to avoid doubling.\nLive colors are approximate; Preview export checks final filters and audio. Solo volume is capped at 100%; export supports 200%.')
        note.setToolTip(note.text())
        note.setText('Listen solo previews a track and shows it on the waveform; Shift+drag there to mute or keep parts of it.')
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 11px; color: #bfbfbf;")
        side.addWidget(note)
        self.preview_export_button = QPushButton('Preview export…')
        self.preview_export_button.clicked.connect(self.preview_export)
        side.addWidget(self.preview_export_button)
        side.addSpacing(4)
        side.addWidget(QLabel("EXPORT"))
        form = QFormLayout()
        self.encoder = QComboBox()
        self.export_format = QComboBox()
        for label, extension in [('MKV · video', 'mkv'), ('MP4 · video', 'mp4'), ('MP3 · audio', 'mp3'), ('M4A · audio', 'm4a'), ('WAV · uncompressed audio', 'wav'), ('FLAC · lossless audio', 'flac')]:
            self.export_format.addItem(label, extension)
        self.export_format.setCurrentIndex(max(0, self.export_format.findData(self.prefs.get('export_format', 'mkv'))))
        form.addRow('Export format', self.export_format)
        self.export_format.setToolTip('MP4 with H.264 is widely compatible for sharing. Audio formats export one selected track or a combined mix.')
        self.export_format.currentIndexChanged.connect(self.export_format_changed)
        self.bitrate = QSpinBox()
        self.bitrate.setRange(1000, 200000)
        self.bitrate.setValue(self.export_choice['bitrate'] if self.export_choice else 20000)
        self.bitrate.setSuffix(' Kbps')
        self.preset = QComboBox()
        form.addRow('Preset', self.preset)
        preset_buttons = QHBoxLayout()
        save_preset = QPushButton('Save preset…')
        save_preset.clicked.connect(self.save_export_preset)
        preset_buttons.addWidget(save_preset)
        self.delete_preset = QPushButton('Delete preset')
        self.delete_preset.clicked.connect(self.delete_export_preset)
        preset_buttons.addWidget(self.delete_preset)
        form.addRow(preset_buttons)
        compact = QGridLayout()
        compact.setHorizontalSpacing(8)
        compact.addWidget(QLabel('Encoder'), 0, 0)
        compact.addWidget(self.encoder, 0, 1)
        compact.addWidget(QLabel('Bitrate'), 0, 2)
        compact.addWidget(self.bitrate, 0, 3)
        self.encoder.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.encoder.setMinimumContentsLength(10)
        compact.setColumnStretch(1, 1)
        compact.setColumnStretch(3, 1)
        self.resolution = QComboBox()
        for label, value in [('Source / crop size', None), ('3840 × 2160 (4K fit)', [3840,2160]), ('2560 × 1440 (1440p fit)', [2560,1440]), ('1920 × 1080 (fit)', [1920,1080]), ('1280 × 720 (fit)', [1280,720]), ('1080 × 1920 (vertical fit)', [1080,1920])]:
            self.resolution.addItem(label, value)
        self.export_fps = QComboBox()
        for label, value in [('Source FPS', 0), ('24 FPS', 24), ('30 FPS', 30), ('60 FPS', 60)]:
            self.export_fps.addItem(label, value)
        self.upscale = QCheckBox('Allow upscaling smaller footage (Lanczos)')
        self.upscale.setChecked(False)
        self.upscale.setToolTip('Off by default. When off, smaller footage is padded without enlarging it. Upscaling enlarges pixels; it does not recover missing detail.')
        self.set_output_choice(self.export_choice or {})
        compact.addWidget(QLabel('Resolution'), 1, 0)
        compact.addWidget(self.resolution, 1, 1)
        compact.addWidget(QLabel('FPS'), 1, 2)
        compact.addWidget(self.export_fps, 1, 3)
        self.resolution.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.resolution.setMinimumContentsLength(14)
        form.addRow(compact)
        form.addRow(self.upscale)
        self.size_estimate = QLabel('Estimated size: open a clip')
        self.size_estimate.setWordWrap(True)
        form.addRow(self.size_estimate)
        side.addLayout(form)
        self.export_button = QPushButton('Export…')
        self.export_button.setObjectName('primary')
        self.export_button.setMinimumWidth(140)
        self.export_button.clicked.connect(self.export)
        export_actions = QHBoxLayout()
        export_actions.addWidget(self.export_button, 1)
        self.cancel_button = QPushButton('Cancel export')
        self.cancel_button.setMinimumWidth(140)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_export)
        export_actions.addWidget(self.cancel_button, 1)
        side.addLayout(export_actions)
        footer = QVBoxLayout()
        self.progress = ExportProgressBar()
        self.progress.setObjectName('exportProgress')
        self.progress.setStyleSheet("QProgressBar#exportProgress { min-height: 30px; max-height: 30px; }")
        self.progress.setFixedHeight(30)
        self.progress.setFormat('%p%')
        side.addWidget(self.progress)
        self.eta = ExportETA()
        self.eta_label = QLabel()
        self.eta_label.setWordWrap(True)
        side.addWidget(self.eta_label)
        self.status = QLabel('FFmpeg tools are required for inspection and export. File → FFmpeg folder to configure.')
        self.status.setWordWrap(True)
        footer.addWidget(self.status)
        side.addStretch()
        root_layout.addLayout(footer)
        self.setCentralWidget(root)
        file_menu = self.menuBar().addMenu('File')
        file_menu.addAction('Open clip', self.choose_clip)
        file_menu.addAction('Browse clips', self.browse_clips)
        file_menu.addAction('Export…', self.export)
        file_menu.addAction('FFmpeg folder…', self.choose_tools)
        file_menu.addAction('Check encoders again', self.check_encoders)
        file_menu.addAction('Encoder diagnostics…', self.encoder_diagnostics)
        file_menu.addAction('Default export folder…', self.choose_export_folder)
        self.recent = self.menuBar().addMenu('Recent')
        self.refresh_recent()
        edit_menu = self.menuBar().addMenu('Edit')
        edit_menu.addAction('Set start here', self.mark_start)
        edit_menu.addAction('Set end here', self.mark_end)
        edit_menu.addAction('Reset trim', self.reset_trim)
        filters = self.menuBar().addMenu('Filters')
        filters.addAction('Drag crop corners…', self.visual_crop)
        filters.addAction('Crop / brightness / contrast / saturation…', self.filter_dialog)
        filters.addAction('Reset filters', self.reset_filters)
        self.player.positionChanged.connect(self.position_changed)
        self.player.tracksChanged.connect(self.tracks_ready)
        self.player.errorOccurred.connect(lambda *_: self.status.setText('Playback: ' + self.player.errorString()))
        self.track_rows = []
        self.listen_row = 0
        self.wave_row = None
        self.export_button.setEnabled(False)
        self.refresh_presets()
        self.preset.currentIndexChanged.connect(self.apply_export_preset)
        self.encoder.currentIndexChanged.connect(self.export_controls_changed)
        self.bitrate.valueChanged.connect(self.export_controls_changed)
        self.resolution.currentIndexChanged.connect(self.export_controls_changed)
        self.export_fps.currentIndexChanged.connect(self.export_controls_changed)
        self.remix.toggled.connect(self.update_size_estimate)
        self.upscale.toggled.connect(self.update_size_estimate)
        self.export_format_changed()
        self.update_region_controls()

    def preferred_open_size(self):
        # Include the real theme/font/titlebar layout rather than a fixed height.
        self.ensurePolished()
        self.layout().activate()
        return self.size().expandedTo(self.sizeHint()).expandedTo(QSize(1560, 1000))

    def set_output_choice(self, choice):
        for widget, key, default in ((self.resolution, 'resolution', None), (self.export_fps, 'fps', 0)):
            widget.blockSignals(True)
            widget.setCurrentIndex(max(0, widget.findData(choice.get(key, default))))
            widget.blockSignals(False)

    def output_choice(self, label):
        choice = dict(encoder=label, bitrate=self.bitrate.value())
        if self.resolution.currentData():
            choice['resolution'] = self.resolution.currentData()
        if self.export_fps.currentData():
            choice['fps'] = self.export_fps.currentData()
        return choice

    def update_size_estimate(self, *_):
        if hasattr(self, 'size_estimate') and self.audio_export():
            self.size_estimate.setText('Audio only · select one track or combine isolated tracks. MP3/M4A: 192 kb/s.')
            return
        if hasattr(self, 'size_estimate') and self.info and hasattr(self, 'track_rows'):
            estimate = estimated_size(self.current_edit(), self.info) / 1_000_000
            note = ' · copy: starts at the keyframe before Start' if self.copy_selected() else ''
            self.size_estimate.setText(f'Estimated size: {estimate:.1f} MB (approximate){note}')

    def export_progress(self, percent):
        self.progress.setValue(percent)
        seconds = self.eta.update(percent)
        self.eta_label.setText('Finishing…' if percent >= 99 else 'Time remaining: estimating…' if seconds is None else f'About {max(1, round(seconds))} s remaining')

    def browse_clips(self):
        if self.busy():
            return
        from .clip_browser import ClipBrowser
        try:
            ffmpeg, _ = tools_path(self.prefs.get('ffmpeg_folder', ''))
        except ValueError:
            ffmpeg = None
        dialog = ClipBrowser(self.prefs.get('library_folder') or self.clips_folder, ffmpeg, DATA/'thumbnails', self)
        dialog.exec()
        self.prefs['library_folder'] = str(dialog.root)
        self.save_prefs()
        if dialog.selected_path:
            self.open_clip(dialog.selected_path)

    def update_preview(self, *_):
        self.video.crop, self.video.colors = self.crop, self.colors
        self.video.show_edits = self.show_edits.isChecked()
        self.video.refresh()

    def update_timeline(self, *_):
        self.wave.start, self.wave.end = self.start.value(), self.end.value()
        self.wave.update()
        self.update_size_estimate()

    def step_frame(self, direction):
        if not self.info:
            return
        try:
            fps = float(Fraction(self.info['video'].get('avg_frame_rate', '0/1')))
            if not 0 < fps <= 1000:
                return
        except (ValueError, ZeroDivisionError):
            return
        frame = round(self.player.position()*fps/1000)+direction
        self.jump_marker(max(0, min(self.info['duration']-1/fps, frame/fps)))

    def remix_changed(self, checked):
        if checked and len(self.track_rows) > 1:
            for _, title, check, _, _ in self.track_rows:
                if title.strip().casefold() == 'mix':
                    check.setChecked(False)

    def start_waveform(self, row=0):
        self.wave_token += 1
        token = self.wave_token
        for job in self.analysis_jobs:
            job.cancel.set()
        self.wave.peaks = []
        if not self.info or not self.track_rows:
            self.wave.label = 'No audio track'
            self.wave.update()
            return
        self.wave_row = row
        info, index, title = self.info, self.track_rows[row][0], self.track_rows[row][1]
        self.wave.muted = self.mutes.get(index, [])
        self.update_region_controls()
        self.wave.label = 'Loading waveform: ' + title
        self.wave.update()
        try:
            ffmpeg, _ = tools_path(self.prefs.get('ffmpeg_folder', ''))
        except ValueError:
            return
        job = Job(lambda job: waveform(info, index, ffmpeg, job.cancel), self)
        def ready(peaks):
            if token == self.wave_token:
                self.wave.peaks, self.wave.label = peaks, title + ' • normalized waveform'
                self.wave.update()
        def failed(text):
            if token == self.wave_token:
                self.wave.label = 'Waveform unavailable'
                self.wave.setToolTip(text)
                self.wave.update()
        def finished():
            if job in self.analysis_jobs:
                self.analysis_jobs.remove(job)
                job.deleteLater()
        job.result.connect(ready)
        job.failed.connect(failed)
        job.finished.connect(finished)
        self.analysis_jobs.append(job)
        job.start()

    def current_edit(self):
        audio = [(index, title, volume.value()/100) for index, title, check, volume, _ in self.track_rows if check.isChecked()]
        # Copy greys out resolution/FPS/upscale; their leftover values must not block the export.
        copy = self.copy_selected()
        return Edit(self.start.value(), self.end.value(), self.encoder.currentData(), self.bitrate.value(),
                    audio, self.crop, *self.colors, remix=self.remix.isChecked(),
                    resolution=None if copy else self.resolution.currentData(),
                    fps=0 if copy else self.export_fps.currentData(),
                    upscale=False if copy else self.upscale.isChecked(),
                    mutes={index: list(ranges) for index, ranges in self.mutes.items() if ranges})

    def region_changed(self, region):
        self.update_region_controls()

    def wave_track(self):
        if self.wave_row is None or not self.info or self.wave_row >= len(self.track_rows):
            return None
        return self.track_rows[self.wave_row]

    def update_region_controls(self):
        track, region = self.wave_track(), self.wave.region
        for button, needs_region in self.region_buttons:
            button.setEnabled(track is not None and (region is not None or not needs_region))
        if track is None:
            self.region_label.setText('Track audio: open a clip to edit individual tracks')
            return
        muted = self.mutes.get(track[0], [])
        summary = f' • {len(muted)} muted part{"s" if len(muted) != 1 else ""}' if muted else ''
        if region:
            self.region_label.setText(f'{track[1]}: {region[0]:.3f}–{region[1]:.3f} s selected{summary}')
        else:
            self.region_label.setText(f'{track[1]}: Shift+drag the waveform to select a range{summary}')

    def set_track_mutes(self, ranges):
        track = self.wave_track()
        if track is None:
            return
        index = track[0]
        if ranges:
            self.mutes[index] = ranges
        else:
            self.mutes.pop(index, None)
        self.wave.muted = self.mutes.get(index, [])
        row = self.wave_row
        item = self.tracks.item(row, 1)
        if item is not None:
            base = item.text().split(' • muted ', 1)[0]
            count = len(self.mutes.get(index, []))
            item.setText(base + (f' • muted {count}×' if count else ''))
        self.update_region_controls()
        self.wave.update()
        self.apply_listen_mutes(self.player.position())

    def region_from_markers(self):
        self.wave.set_region((self.start.value(), self.end.value()))

    def mute_region(self):
        track, region = self.wave_track(), self.wave.region
        if track and region:
            self.set_track_mutes(add_range(self.mutes.get(track[0], []), *region, self.info['duration']))

    def keep_region(self):
        track, region = self.wave_track(), self.wave.region
        if track and region:
            self.set_track_mutes(keep_only_range(*region, self.info['duration']))

    def unmute_region(self):
        track, region = self.wave_track(), self.wave.region
        if track and region:
            self.set_track_mutes(remove_range(self.mutes.get(track[0], []), *region))

    def clear_track_mutes(self):
        self.set_track_mutes([])

    def apply_listen_mutes(self, position):
        """Solo listening follows the muted ranges of the track being heard."""
        if not self.info or self.listen_row >= len(self.track_rows):
            return
        seconds = position / 1000
        ranges = self.mutes.get(self.track_rows[self.listen_row][0], [])
        self.audio_output.setMuted(any(a <= seconds < b for a, b in ranges))

    def preview_export(self):
        if self.busy() or not self.info:
            return
        try:
            ffmpeg, _ = tools_path(self.prefs.get('ffmpeg_folder', ''))
            edit = self.current_edit()
            edit.encoder, edit.bitrate = 'CPU H.264', 8000
            if self.preview_temp:
                self.preview_temp.cleanup()
            self.preview_temp = tempfile.TemporaryDirectory(prefix='clipnest-preview-')
            target = str(Path(self.preview_temp.name)/'preview.mkv')
        except (ValueError, OSError) as exc:
            self.error(str(exc))
            return
        self.player.pause()
        self.progress.setValue(0)
        self.status.setText('Preparing selected-range preview with final filters and audio… Cancel export stops this too.')
        info = self.info
        self.launch(lambda job: export_clip(info, edit, ffmpeg, target, job.cancel, job.progress.emit), self.show_export_preview, exporting=True)

    def show_export_preview(self, path):
        dialog = QDialog(self)
        dialog.setWindowTitle('Export preview • selected A–B range')
        dialog.resize(960, 620)
        layout = QVBoxLayout(dialog)
        video = QVideoWidget()
        layout.addWidget(video, 1)
        player = QMediaPlayer(dialog)
        output = DefaultAudioOutput(dialog)
        player.setAudioOutput(output)
        player.setVideoOutput(video)
        dialog.playback_lifecycle = PlaybackLifecycle(dialog, player)
        player.setSource(QUrl.fromLocalFile(path))
        audio = QComboBox()
        audio.currentIndexChanged.connect(player.setActiveAudioTrack)
        def tracks():
            audio.clear()
            from PySide6.QtMultimedia import QMediaMetaData
            for i, track in enumerate(player.audioTracks()):
                audio.addItem(str(track.value(QMediaMetaData.Key.Title) or f'Audio {i+1}'))
        player.tracksChanged.connect(tracks)
        layout.addWidget(audio)
        slider = SeekSlider(Qt.Orientation.Horizontal)
        player.durationChanged.connect(lambda duration: slider.setRange(0, duration))
        player.positionChanged.connect(lambda position: slider.setValue(position) if not slider.isSliderDown() else None)
        slider.sliderMoved.connect(player.setPosition)
        layout.addWidget(slider)
        button = QPushButton('Play / pause')
        button.clicked.connect(lambda: player.pause() if player.playbackState() == QMediaPlayer.PlaybackState.PlayingState else player.play())
        layout.addWidget(button)
        player.play()
        dialog.exec()
        player.stop()
        player.setSource(QUrl())
        dialog.deleteLater()
        self.status.setText('Preview closed. Export when ready.')

    @staticmethod
    def valid_choice(choice):
        return (isinstance(choice, dict) and isinstance(choice.get('encoder'), str) and choice.get('encoder') in (*ENCODERS, COPY)
                and type(choice.get('bitrate')) is int and 1000 <= choice['bitrate'] <= 200000
                and choice.get('resolution') in (None, [1920,1080], [1280,720], [1080,1920], [2560,1440], [3840,2160])
                and choice.get('fps', 0) in (0,24,30,60))

    def refresh_presets(self):
        active = self.prefs.get('active_export_preset', '')
        self.preset.blockSignals(True)
        self.preset.clear()
        self.preset.addItem('Custom / last used', '')
        for name in self.quick_presets:
            self.preset.addItem(name, name)
        for name in sorted(self.prefs['export_presets'], key=str.casefold):
            self.preset.addItem(name, name)
        index = self.preset.findData(active)
        self.preset.setCurrentIndex(max(0, index))
        self.preset.blockSignals(False)
        self.delete_preset.setEnabled(self.preset.currentData() in self.prefs['export_presets'])

    def export_ready(self):
        audio = self.audio_export()
        return self.info is not None and (audio or self.encoder.currentData() in self.available_export_encoders) and not self.busy()

    def export_format_changed(self, *_):
        self.prefs['export_format'] = self.export_format.currentData()
        self.save_prefs()
        audio = self.audio_export()
        for control in (self.encoder, self.bitrate, self.resolution, self.export_fps, self.upscale):
            control.setEnabled(not audio)
        self.update_copy_controls()
        self.export_button.setEnabled(self.export_ready())
        self.update_size_estimate()

    def audio_export(self):
        return self.export_format.currentData() in AUDIO_FORMATS

    def copy_selected(self):
        audio = self.audio_export()
        return not audio and self.encoder.currentData() == COPY

    def update_copy_controls(self):
        """Copy passes video through untouched, so video-processing options do not apply."""
        if not hasattr(self, 'upscale'):
            return
        audio = self.audio_export()
        copy = self.copy_selected()
        for control in (self.bitrate, self.resolution, self.export_fps, self.upscale):
            control.setEnabled(not audio and not copy)
        if copy:
            self.encoder.setToolTip('Copy: no re-encoding. Video is passed through unchanged and starts at the keyframe '
                                    'before Start. Audio tracks are copied unless you changed their volume, muted parts '
                                    'or combined them; those are re-encoded as AAC. Crop, colors, resolution and FPS '
                                    'cannot be applied.')

    def populate_export_encoders(self):
        desired = self.export_choice['encoder'] if self.export_choice else None
        if desired is None and self.available_export_encoders:
            desired = self.available_export_encoders[0]
            self.export_choice = {'encoder': desired, 'bitrate': self.bitrate.value()}
            self.prefs['last_export'] = dict(self.export_choice)
            self.save_prefs()
        self.encoder.blockSignals(True)
        self.encoder.clear()
        for label in self.available_export_encoders:
            self.encoder.addItem(label, label)
        if desired and desired not in self.available_export_encoders:
            self.encoder.addItem(desired + ' (unavailable)', desired)
            self.encoder.model().item(self.encoder.count()-1).setEnabled(False)
        if desired:
            self.encoder.setCurrentIndex(self.encoder.findData(desired))
        self.encoder.blockSignals(False)
        self.export_button.setEnabled(self.export_ready())

    def export_controls_changed(self, *_):
        label = self.encoder.currentData()
        if label not in ENCODERS and label != COPY:
            return
        self.update_copy_controls()
        self.export_choice = self.output_choice(label)
        self.update_size_estimate()
        self.prefs['last_export'] = dict(self.export_choice)
        self.prefs['active_export_preset'] = ''
        self.refresh_presets()
        self.save_prefs()
        self.export_button.setEnabled(self.export_ready())

    def apply_export_preset(self, *_):
        name = self.preset.currentData()
        self.delete_preset.setEnabled(name in self.prefs['export_presets'])
        if not name:
            self.prefs['active_export_preset'] = ''
            self.save_prefs()
            return
        choice = dict(self.quick_presets[name] if name in self.quick_presets else self.prefs['export_presets'][name])
        if name in self.quick_presets and self.encoder.currentData() in self.available_export_encoders:
            choice['encoder'] = self.encoder.currentData()
        self.set_output_choice(choice)
        self.export_choice = choice
        self.prefs['last_export'] = dict(choice)
        self.prefs['active_export_preset'] = name
        self.bitrate.blockSignals(True)
        self.bitrate.setValue(choice['bitrate'])
        self.bitrate.blockSignals(False)
        self.populate_export_encoders()
        self.update_size_estimate()
        self.save_prefs()
        self.status.setText('Preset: ' + name + ('. Encoder unavailable; select an available encoder or recheck.'
            if choice['encoder'] not in self.available_export_encoders else '.'))

    def save_export_preset(self):
        label = self.encoder.currentData()
        if label not in ENCODERS and label != COPY:
            self.error('Load a clip or check encoders before saving a preset.')
            return
        name, ok = QInputDialog.getText(self, 'Save export preset', 'Preset name:', text=self.preset.currentData() or '')
        name = name.strip()
        if not ok or not name:
            return
        if name in self.quick_presets:
            self.error('Choose a different name from the built-in quick choices.')
            return
        if name in self.prefs['export_presets']:
            answer = QMessageBox.question(self, 'Replace preset?', f'Replace the settings saved in “{name}”?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        choice = self.output_choice(label)
        self.prefs['export_presets'][name] = choice
        self.prefs['active_export_preset'] = name
        self.prefs['last_export'] = dict(choice)
        self.export_choice = dict(choice)
        self.refresh_presets()
        self.save_prefs()
        self.status.setText('Export preset saved: ' + name)

    def delete_export_preset(self):
        name = self.preset.currentData()
        if not name:
            return
        answer = QMessageBox.question(self, 'Delete preset?', f'Delete “{name}”? Current export settings will be kept.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.prefs['export_presets'].pop(name, None)
        self.prefs['active_export_preset'] = ''
        self.refresh_presets()
        self.save_prefs()

    def jump_marker(self, seconds):
        self.selection_playing = False
        self.player.pause()
        self.player.setPosition(round(seconds*1000))

    def choose_export_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Default export folder', str(self.prefs.get('export_folder') or self.clips_folder))
        if folder:
            self.last_export_path = None
            self.prefs['export_folder'] = folder
            self.save_prefs()
            self.status.setText('Default export folder: ' + folder)
            self.exportFolderChanged.emit()

    def encoder_diagnostics(self):
        try:
            ffmpeg, _ = tools_path(self.prefs.get('ffmpeg_folder', ''))
        except Exception as exc:
            ffmpeg = str(exc)
        text = 'FFmpeg: ' + ffmpeg + '\n\n' + ('\n\n'.join(f'{name}:\n{error}' for name, error in self.encoder_errors.items()) or 'No encoder errors recorded. Run Check encoders again.')
        box = QMessageBox(self)
        box.setWindowTitle('Encoder diagnostics')
        box.setText('If NVIDIA encoders are unavailable, copy the details below. This is the editor FFmpeg check, separate from the working recorder.')
        box.setDetailedText(text)
        box.exec()

    def visual_crop(self):
        if not self.info or self.busy():
            return
        self.player.pause()
        info = self.info
        position = self.player.position()/1000
        try:
            ffmpeg, _ = tools_path(self.prefs.get('ffmpeg_folder', ''))
        except Exception as exc:
            self.error(str(exc))
            return
        def get_frame(job):
            import subprocess
            import os
            result = subprocess.run([ffmpeg, '-v', 'error', '-ss', str(min(position, max(0, info['duration']-.1))), '-i', info['path'],
                '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-'],
                capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if result.returncode or not result.stdout:
                raise ValueError(result.stderr.decode('utf-8', 'replace')[-1500:] or 'Could not decode crop preview frame.')
            return result.stdout
        self.status.setText('Loading crop preview…')
        self.launch(get_frame, self.show_crop)

    def show_crop(self, data):
        from .crop import CropDialog
        image = QImage.fromData(data)
        if image.isNull():
            self.error('Could not display crop preview.')
            return
        dialog = CropDialog(image, self.info['video']['width'], self.info['video']['height'], self.crop, self)
        if dialog.exec():
            self.crop = dialog.canvas.selection()
            self.update_preview()
            self.status.setText(f'Export crop: {self.crop}. Reopen Drag crop corners to adjust.')

    def seconds(self):
        s = QDoubleSpinBox()
        s.setDecimals(3)
        s.setSingleStep(.1)
        s.setRange(0, 1000000)
        s.setSuffix(' s')
        return s

    def save_prefs(self):
        try:
            atomic_json(self.preferences, self.prefs)
        except OSError as exc:
            self.status.setText(f'Editor preferences could not be saved: {exc}')

    def refresh_recent(self):
        self.recent.clear()
        for path in self.prefs.get('recent', [])[:10]:
            self.recent.addAction(path, lambda checked=False, p=path: self.open_clip(p))

    def busy(self):
        return self.job is not None

    def launch(self, action, on_result, exporting=False):
        if self.busy():
            return
        self.export_button.setEnabled(False)
        self.menuBar().setEnabled(False)
        self.cancel_button.setEnabled(exporting)
        self.job = Job(action, self)
        self.job.result.connect(on_result)
        self.job.failed.connect(self.error)
        self.eta.reset()
        self.eta_label.setText('Time remaining: estimating…' if exporting else '')
        self.job.progress.connect(self.export_progress)
        self.job.finished.connect(self.job_finished)
        self.job.start()

    def job_finished(self):
        self.eta_label.clear()
        job, self.job = self.job, None
        job.deleteLater()
        self.menuBar().setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.export_button.setEnabled(self.export_ready())

    def error(self, text):
        self.status.setText(text)
        QMessageBox.warning(self, 'Clip editor', text)

    def choose_tools(self, checked=False, *, dialog_parent=None):
        if self.busy():
            return
        folder = QFileDialog.getExistingDirectory(dialog_parent or self, 'Folder containing ffmpeg.exe and ffprobe.exe')
        if folder:
            try:
                tools_path(folder)
                self.prefs['ffmpeg_folder'] = folder
                self.save_prefs()
                self.check_encoders()
            except Exception as exc:
                self.error(str(exc))

    def check_encoders(self):
        if self.busy():
            return
        try:
            ffmpeg, _ = tools_path(self.prefs.get('ffmpeg_folder', ''))
        except Exception as exc:
            self.error(str(exc))
            return
        self.status.setText('Testing encoders with two frames each…')
        self.launch(lambda job: self.encoder_probe.get(ffmpeg, force=True), self.encoders_checked)

    def encoders_checked(self, result):
        labels, errors = result
        self.encoder_errors = errors
        # Copy needs no encoder, so it is always available.
        self.available_export_encoders = list(labels) + [COPY]
        self.populate_export_encoders()
        self.update_copy_controls()
        self.encoder.setToolTip('\n\n'.join(f'{k}: {v}' for k, v in errors.items()))
        message = 'Available: ' + (', '.join(labels) or 'none') + ('. Unavailable: ' + ', '.join(errors) + '. File → Encoder diagnostics for details.' if errors else '')
        if self.export_choice and self.export_choice['encoder'] not in labels:
            message += ' Selected encoder unavailable; export disabled until you choose an available encoder.'
        self.status.setText(message)

    def choose_clip(self):
        if self.busy():
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Open completed clip', str(self.clips_folder), 'Video (*.mkv *.mp4 *.mov *.webm);;All files (*)')
        if path:
            self.open_clip(path)

    def open_clip(self, path):
        show_centered(self, self.parentWidget())
        if self.busy():
            self.status.setText('Wait for the current operation, or cancel the export, before opening another clip.')
            return
        try:
            ffmpeg, ffprobe = tools_path(self.prefs.get('ffmpeg_folder', ''))
        except Exception as exc:
            self.error(str(exc))
            return
        self.player.pause()
        self.status.setText('Inspecting clip and checking encoders…')
        self.launch(lambda job: (probe(path, ffprobe), self.encoder_probe.get(ffmpeg)), self.loaded)

    def loaded(self, result):
        self.last_export_path = None
        self.preview_export_button.setEnabled(True)
        # A finished bar belongs to the previous clip; 100% here looked like this clip was exported.
        self.progress.setValue(0)
        self.eta.reset()
        self.eta_label.clear()
        self.info, encoders = result
        self.encoders_checked(encoders)
        self.crop, self.colors = None, (0., 1., 1.)
        self.video.source_size = (self.info['video']['width'], self.info['video']['height'])
        self.video.frame_timer.stop()
        self.video.pending_frame = None
        self.video.set_image(QImage())
        self.update_preview()
        self.wave.duration = self.info['duration']
        self.reset_trim()
        self.caption.setText(f"{self.info['path']}\n{self.info['video']['width']} × {self.info['video']['height']} • {self.info['duration']:.3f} s • {len(self.info['audio'])} audio tracks")
        self.scrub.setRange(0, round(self.info['duration'] * 1000))
        self.position_changed(0)
        self.track_rows = []
        self.mutes = {}
        self.wave.muted = []
        self.wave.set_region(None)
        self.tracks.setRowCount(len(self.info['audio']))
        for i, stream in enumerate(self.info['audio']):
            title = stream.get('tags', {}).get('title', f'Audio {i+1}')
            check = QCheckBox()
            check.setChecked(True)
            check.toggled.connect(self.update_size_estimate)
            volume = QSpinBox()
            volume.setRange(0, 200)
            volume.setValue(100)
            volume.valueChanged.connect(self.update_listen_volume)
            listen = QPushButton('Listen solo')
            listen.clicked.connect(lambda checked=False, row=i: self.listen(row))
            self.tracks.setCellWidget(i, 0, check)
            self.tracks.setItem(i, 1, QTableWidgetItem(f"{i+1}: {title} • {stream.get('codec_name', '?')} • {stream.get('channels', '?')} ch"))
            self.tracks.setCellWidget(i, 2, volume)
            self.tracks.setCellWidget(i, 3, listen)
            self.track_rows.append((stream['index'], title, check, volume, listen))
        self.listen_row = 0
        self.wave_row = None
        self.remix_changed(self.remix.isChecked())
        self.update_size_estimate()
        self.selection_playing = False
        self.player.setSource(QUrl.fromLocalFile(self.info['path']))
        self.player.pause()
        self.prefs['recent'] = [self.info['path']] + [p for p in self.prefs.get('recent', []) if p != self.info['path']][:9]
        self.save_prefs()
        self.refresh_recent()
        self.start_waveform()

    def tracks_ready(self):
        if self.track_rows and self.player.audioTracks():
            self.listen(min(self.listen_row, len(self.player.audioTracks()) - 1))

    def listen(self, row):
        if row >= len(self.player.audioTracks()):
            self.status.setText('Playback backend has not loaded this track yet, or cannot decode it.')
            return
        self.listen_row = row
        self.player.setActiveAudioTrack(row)
        self.apply_listen_mutes(self.player.position())
        for i, (_, _, _, _, button) in enumerate(self.track_rows):
            button.setText('Listening' if i == row else 'Listen solo')
        self.update_listen_volume()
        if self.wave_row != row:
            self.start_waveform(row)

    def update_listen_volume(self):
        if self.listen_row < len(self.track_rows):
            self.audio_output.setVolume(min(1.0, self.track_rows[self.listen_row][3].value() / 100))

    def position_changed(self, position):
        self.apply_listen_mutes(position)
        self.wave.position = position
        self.wave.update()
        if not self.scrub.isSliderDown():
            self.scrub.setValue(position)
        self.clock.setText(f'{position/1000:.3f} / {self.scrub.maximum()/1000:.3f} s')
        if self.selection_playing and position >= self.end.value()*1000:
            self.player.pause()
            self.selection_playing = False

    def play_pause(self):
        self.selection_playing = False
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()


    def mark_start(self):
        self.start.setValue(self.player.position()/1000)

    def mark_end(self):
        self.end.setValue(self.player.position()/1000)

    def reset_trim(self):
        if self.info:
            # Never round the trim boundary past the source duration.
            end = int(self.info['duration']*1000)/1000
            self.start.setMaximum(end)
            self.end.setMaximum(end)
            self.start.setValue(0)
            self.end.setValue(end)

    def play_selection(self):
        if self.start.value() >= self.end.value():
            self.error('Start must be before end.')
            return
        self.selection_playing = True
        self.player.setPosition(round(self.start.value()*1000))
        self.player.play()

    def reset_filters(self):
        self.crop, self.colors = None, (0., 1., 1.)
        self.update_preview()
        self.status.setText('Crop and color filters reset.')

    def filter_dialog(self):
        if not self.info:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Crop / colors • live preview')
        form = QFormLayout(dialog)
        enabled = QCheckBox('Enable crop')
        enabled.setChecked(self.crop is not None)
        form.addRow(enabled)
        w, h = self.info['video']['width'], self.info['video']['height']
        controls = []
        for label, value in zip(('Left / x', 'Top / y', 'Width', 'Height'), self.crop or (0, 0, w-w%2, h-h%2)):
            control = QSpinBox()
            control.setRange(0, max(w, h))
            control.setSingleStep(2)
            control.setValue(value)
            form.addRow(label + ' (even pixels)', control)
            controls.append(control)
        colors = []
        for label, value, low in zip(('Brightness', 'Contrast', 'Saturation'), self.colors, (-1, 0, 0)):
            control = QDoubleSpinBox()
            control.setRange(low, 1 if low == -1 else 2)
            control.setSingleStep(.05)
            control.setValue(value)
            form.addRow(label, control)
            colors.append(control)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        def draft_preview():
            crop = tuple(c.value() for c in controls) if enabled.isChecked() else None
            if crop:
                x, y, cw, ch = crop
                if any(v % 2 for v in crop) or min(cw, ch) < 2 or x+cw > w or y+ch > h:
                    return
            self.video.crop = crop
            self.video.colors = tuple(c.value() for c in colors)
            self.video.refresh()
        for control in controls+colors:
            control.valueChanged.connect(draft_preview)
        enabled.toggled.connect(draft_preview)
        if dialog.exec():
            crop = tuple(c.value() for c in controls) if enabled.isChecked() else None
            if crop:
                x, y, cw, ch = crop
                if any(v % 2 for v in crop) or min(cw, ch) < 2 or x+cw > w or y+ch > h:
                    self.error('Crop must have even coordinates/dimensions and fit inside the source. Previous filters retained.')
                    self.update_preview()
                    return
            self.crop = crop
            self.colors = tuple(c.value() for c in colors)
            self.status.setText(f'Export filters: crop {self.crop or "off"}; brightness / contrast / saturation {self.colors}')
        self.update_preview()

    def export(self):
        if self.busy() or not self.info:
            return
        if not self.export_ready():
            self.error('The selected export encoder is unavailable. Choose an available encoder or use File → Check encoders again.')
            return
        edit = self.current_edit()
        source = Path(self.info['path'])
        extension = self.export_format.currentData()
        suggested = str(Path(self.last_export_path or str(Path(self.prefs.get('export_folder') or self.clips_folder/'Exports') / (source.stem + '_edited.mkv'))).with_suffix('.' + extension))
        path, _ = QFileDialog.getSaveFileName(self, 'Export clip', suggested, f'{extension.upper()} (*.{extension})',
                                             options=QFileDialog.Option.DontConfirmOverwrite)
        if not path:
            return
        path = str(Path(path).with_suffix('.' + extension))
        try:
            ffmpeg, _ = tools_path(self.prefs.get('ffmpeg_folder', ''))
            from .media import export_args, file_identity
            export_args(self.info, edit, ffmpeg, path)
            existing = file_identity(path) if Path(path).exists() else None
            if existing is not None:
                answer = QMessageBox.question(self, 'Replace existing export?',
                    f'{Path(path).name} already exists. Replace it with this export?\n\nThe existing file is kept until the new export finishes successfully.',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return
        except Exception as exc:
            self.error(str(exc))
            return
        self.player.pause()
        self.progress.setValue(0)
        self.status.setText('Exporting… The existing file is kept until completion.' if existing else 'Exporting a new copy…')
        info = self.info
        self.launch(lambda job: export_clip(info, edit, ffmpeg, path, job.cancel, job.progress.emit, overwrite=existing is not None, expected_target=existing),
                    self.export_saved, exporting=True)

    def export_saved(self, path):
        self.last_export_path = path
        self.status.setText('Export saved: ' + path)
        from .exports import register_export
        try:
            register_export(path)
        except OSError:
            self.status.setText('Export saved, but its gallery entry could not be stored: ' + path)
        self.exportCompleted.emit(path)
        parent = self.parent()
        if parent is not None and hasattr(parent, 'capture_notice'):
            parent.capture_notice(dict(title='Export complete', detail=Path(path).name, sound=True))
        else:
            from .notifications import export_beep
            export_beep()
            QMessageBox.information(self, 'Export complete', 'Saved: ' + path)

    def cancel_export(self):
        if self.job:
            self.job.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status.setText('Cancelling export…')

    def can_close(self):
        if self.busy():
            self.error('Wait for clip inspection, or cancel the export and wait for it to finish, before closing.')
            return False
        self.wave_token += 1
        for job in self.analysis_jobs:
            job.cancel.set()
        for job in self.analysis_jobs:
            if not job.wait(5000):
                self.status.setText('Stopping waveform analysis; close again in a moment.')
                return False
        self.release_media()
        if self.preview_temp:
            try:
                self.preview_temp.cleanup()
                self.preview_temp = None
            except OSError:
                pass
        return True

    def closeEvent(self, event):
        if self.can_close():
            event.accept()
        else:
            event.ignore()

    def release_media(self):
        """Let go of the clip file. A stopped player still holds it open, which blocked Recycle Bin moves."""
        self.player.stop()
        self.player.setSource(QUrl())
        self.video.frame_timer.stop()
        self.video.pending_frame = None

    def release_file(self, path):
        """The gallery is deleting this clip; release it if it is the one loaded here."""
        from .desktop import same_file
        if self.info and same_file(self.info['path'], path):
            self.release_media()
            self.status.setText('This clip was moved to the Recycle Bin. Open another clip to continue.')
            self.export_button.setEnabled(False)
            self.preview_export_button.setEnabled(False)

    def showEvent(self, event):
        super().showEvent(event)
        # Reopening the editor restores the clip released when it was closed.
        if self.info and self.player.source().isEmpty() and Path(self.info['path']).is_file():
            self.player.setSource(QUrl.fromLocalFile(self.info['path']))
            self.player.pause()
