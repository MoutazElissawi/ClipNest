"""Editor preview, local-file drops and a compact waveform timeline."""
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt, QRectF, Signal, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.mov', '.webm', '.avi', '.m4v', '.ts'}


def dropped_clip(mime):
    urls = mime.urls() if mime.hasUrls() else []
    if len(urls) != 1 or not urls[0].isLocalFile():
        return None
    path = Path(urls[0].toLocalFile())
    return str(path) if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS else None


def filtered_image(image, crop, colors, source_size=None):
    """Preserve source pixels; RGB preview is approximate, FFmpeg owns final colors."""
    if image.isNull():
        return image
    if crop:
        sw, sh = source_size or (image.width(), image.height())
        x, y, w, h = crop
        image = image.copy(round(x*image.width()/sw), round(y*image.height()/sh),
                           max(1, round(w*image.width()/sw)), max(1, round(h*image.height()/sh)))
    if colors == (0., 1., 1.):
        return image
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    pixels = np.frombuffer(image.constBits(), dtype=np.uint8).reshape(image.height(), image.bytesPerLine())
    rgb = pixels[:, :image.width()*4].reshape(image.height(), image.width(), 4)[:, :, :3].astype(np.float32)/255
    brightness, contrast, saturation = colors
    # Luma/chroma adjustment, retaining a neutral image when all controls are reset.
    luma = rgb[:, :, 0]*.299 + rgb[:, :, 1]*.587 + rgb[:, :, 2]*.114
    adjusted = (luma-.5)*contrast + .5 + brightness
    rgb = (rgb-luma[:, :, None])*saturation + adjusted[:, :, None]
    result = np.ascontiguousarray(np.clip(rgb*255, 0, 255).astype(np.uint8))
    return QImage(result.data, image.width(), image.height(), image.width()*3, QImage.Format.Format_RGB888).copy()


class VideoCanvas(QWidget):
    clipDropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumSize(360, 200)
        self.image = QImage()
        self.display = QImage()
        self.crop = None
        self.colors = (0., 1., 1.)
        self.source_size = None
        self.show_edits = True
        self.hover = False
        self.frames_suspended = False
        self.pending_frame = None
        self.frame_timer = QTimer(self)
        self.frame_timer.setSingleShot(True)
        self.frame_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.frame_timer.setInterval(16)
        self.frame_timer.timeout.connect(self.flush_frame)

    def frame_changed(self, frame):
        if frame.isValid():
            # Coalesce within a 16 ms budget for 60 fps playback; never queue old images.
            self.pending_frame = frame
            if not self.frames_suspended and not self.frame_timer.isActive():
                self.frame_timer.start()

    def suspend_frames(self):
        self.frames_suspended = True
        self.frame_timer.stop()

    def resume_frames(self):
        self.frames_suspended = False
        if self.pending_frame is not None and not self.frame_timer.isActive():
            self.frame_timer.start()

    def flush_frame(self):
        if self.frames_suspended:
            return
        frame, self.pending_frame = self.pending_frame, None
        if frame is not None:
            self.set_image(frame.toImage())

    def set_image(self, image):
        # One source image is retained for filter changes while paused.
        self.image = image
        self.refresh()

    def refresh(self):
        self.display = filtered_image(self.image, self.crop if self.show_edits else None,
                                      self.colors if self.show_edits else (0., 1., 1.), self.source_size)
        self.update()

    def dragEnterEvent(self, event):
        if dropped_clip(event.mimeData()):
            self.hover = True
            self.update()
            event.acceptProposedAction()
        else:
            event.ignore()

    dragMoveEvent = dragEnterEvent

    def dragLeaveEvent(self, event):
        self.hover = False
        self.update()
        event.accept()

    def dropEvent(self, event):
        self.hover = False
        self.update()
        path = dropped_clip(event.mimeData())
        if path:
            event.acceptProposedAction()
            self.clipDropped.emit(path)
        else:
            event.ignore()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor('#0e0e0e'))
        if not self.display.isNull():
            size = self.display.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            area = QRectF((self.width()-size.width())/2, (self.height()-size.height())/2, size.width(), size.height())
            p.drawImage(area, self.display)
        else:
            p.setPen(QColor('#cacaca'))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Drop a clip here\nor use Open / Browse clips')
        if self.hover:
            p.fillRect(self.rect(), QColor(118, 185, 0, 80))
            p.setPen(QPen(QColor('#c9c9c9'), 3))
            p.drawRect(self.rect().adjusted(2, 2, -3, -3))


class Waveform(QWidget):
    seek = Signal(int)
    region_changed = Signal(object)  # (start, end) seconds, or None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(66)
        self.setMaximumHeight(80)
        self.peaks = []
        self.duration = 0
        self.position = 0
        self.start = self.end = 0
        self.muted = []      # muted (start, end) ranges of the shown track, seconds
        self.region = None   # selected (start, end) range, seconds
        self.region_anchor = None
        self.label = 'Waveform appears when a clip is loaded'
        self.setToolTip('Click or drag to seek. Shift+drag selects an audio range to mute, cut or keep. '
                        'Gray marks the A–B export range; red marks muted audio on this track.')

    def seconds_at(self, x):
        return max(0., min(1., x/max(1, self.width()-1)))*self.duration

    def set_region(self, region):
        self.region = region if region and region[1] - region[0] > 1e-3 else None
        self.region_changed.emit(self.region)
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.duration:
            return
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.region_anchor = self.seconds_at(event.position().x())
            self.set_region(None)
            return
        self.region_anchor = None
        self.seek.emit(round(self.seconds_at(event.position().x())*1000))

    def mouseMoveEvent(self, event):
        if not event.buttons() & Qt.MouseButton.LeftButton:
            return
        if self.region_anchor is not None:
            here = self.seconds_at(event.position().x())
            self.set_region((min(here, self.region_anchor), max(here, self.region_anchor)))
            return
        self.mousePressEventProxy(event)

    def mouseReleaseEvent(self, event):
        self.region_anchor = None

    def mousePressEventProxy(self, event):
        if self.duration:
            self.seek.emit(round(max(0., min(1., event.position().x()/max(1, self.width()-1)))*self.duration*1000))

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#191919'))
        w, h = self.width(), self.height()
        if self.duration:
            a, b = self.start/self.duration*w, self.end/self.duration*w
            p.fillRect(QRectF(a, 0, max(0, b-a), h), QColor('#404040'))
            p.setPen(QColor('#c9c9c9'))
            p.drawText(int(a)+3, 13, 'A')
            p.drawText(max(0, min(w-13, int(b)-13)), 13, 'B')
            for ma, mb in self.muted:
                p.fillRect(QRectF(ma/self.duration*w, 0, max(1, (mb-ma)/self.duration*w), h), QColor(170, 30, 30, 150))
        p.setPen(QPen(QColor('#76b900'), 1))
        for i, peak in enumerate(self.peaks):
            x = round(i*w/max(1, len(self.peaks)-1))
            amp = float(peak)*(h/2-16)
            p.drawLine(x, round(h/2-amp), x, round(h/2+amp))
        if self.duration and self.region:
            ra, rb = self.region
            p.fillRect(QRectF(ra/self.duration*w, 0, max(1, (rb-ra)/self.duration*w), h), QColor(255, 220, 69, 70))
            p.setPen(QPen(QColor('#ffdc45'), 1))
            p.drawLine(round(ra/self.duration*w), 0, round(ra/self.duration*w), h)
            p.drawLine(round(rb/self.duration*w), 0, round(rb/self.duration*w), h)
        if self.duration:
            p.setPen(QPen(QColor('#ffffff'), 2))
            x = round(self.position/self.duration/1000*w)
            p.drawLine(x, 0, x, h)
        p.setPen(QColor('#dfdfdf'))
        p.drawText(6, h-4, self.label)
