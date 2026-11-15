"""Glass chrome using ordinary Qt widgets; no masks or native hit-test callbacks.

Configure the alpha surface before first show. Defer DWM calls until the visible
QWindow already exists. menuBar() owns a stable QMenuBar inside the chrome: the
base accessor would otherwise replace our title bar when editor jobs disable it.
"""
import logging
from PySide6.QtCore import Qt, QTimer, QEvent, QRect, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QLinearGradient
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QMenuBar, QSizePolicy)


class TitleBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.owner = window
        self.setObjectName('windowTitleBar')
        self.setFixedHeight(48)
        row = QHBoxLayout(self)
        row.setContentsMargins(18, 12, 24, 4)
        row.setSpacing(10)
        self.emblem = QLabel()
        self.emblem.setFixedSize(24, 24)
        self.emblem.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(self.emblem)
        window.windowIconChanged.connect(self.update_icon)
        self.update_icon(window.windowIcon())
        self.caption = QLabel(window.windowTitle())
        self.caption.setObjectName('windowCaption')
        self.caption.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        window.windowTitleChanged.connect(self.caption.setText)
        row.addWidget(self.caption, 1)
        self.controls = {}
        for text, name, callback in [('−', 'Minimize', window.showMinimized),
                                      ('□', 'Maximize or restore', self.toggle_maximized),
                                      ('×', 'Close window', window.close)]:
            button = QPushButton(text)
            button.setObjectName('windowClose' if name == 'Close window' else 'windowControl')
            button.setAccessibleName(name)
            button.setToolTip(name)
            button.setFixedSize(44, 32)
            button.clicked.connect(callback)
            row.addWidget(button)
            self.controls[name] = button

    def update_icon(self, icon):
        self.emblem.setPixmap(icon.pixmap(24, 24))

    def toggle_maximized(self):
        if self.owner.isMaximized() or self.owner.isFullScreen():
            self.owner.showNormal()
        else:
            self.owner.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.owner.windowHandle()
            if handle is not None and handle.startSystemMove():
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class ResizeHandle(QWidget):
    """Generous Qt edge/corner target, with a fallback if the platform cannot drag."""
    def __init__(self, window, edges):
        super().__init__(window)
        self.owner, self.edges = window, edges
        self.drag_origin = self.drag_rect = None
        self.setObjectName('resizeHandle')
        self.setToolTip('Drag to resize')
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        left, right, top, bottom = (bool(edges & edge) for edge in (
            Qt.Edge.LeftEdge, Qt.Edge.RightEdge, Qt.Edge.TopEdge, Qt.Edge.BottomEdge))
        cursor = (Qt.CursorShape.SizeFDiagCursor if left == top else Qt.CursorShape.SizeBDiagCursor) if (left or right) and (top or bottom) else Qt.CursorShape.SizeHorCursor if left or right else Qt.CursorShape.SizeVerCursor
        self.setCursor(cursor)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.owner.isMaximized():
            return super().mousePressEvent(event)
        handle = self.owner.windowHandle()
        if handle is None or not handle.startSystemResize(self.edges):
            self.drag_origin = event.globalPosition().toPoint()
            self.drag_rect = self.owner.geometry()
        event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_origin is None:
            return super().mouseMoveEvent(event)
        delta = event.globalPosition().toPoint()-self.drag_origin
        rect = QRect(self.drag_rect)
        minimum = self.owner.minimumSize().expandedTo(self.owner.minimumSizeHint())
        if self.edges & Qt.Edge.LeftEdge:
            rect.setLeft(min(rect.right()-minimum.width()+1, rect.left()+delta.x()))
        if self.edges & Qt.Edge.RightEdge:
            rect.setRight(max(rect.left()+minimum.width()-1, rect.right()+delta.x()))
        if self.edges & Qt.Edge.TopEdge:
            rect.setTop(min(rect.bottom()-minimum.height()+1, rect.top()+delta.y()))
        if self.edges & Qt.Edge.BottomEdge:
            rect.setBottom(max(rect.top()+minimum.height()-1, rect.bottom()+delta.y()))
        self.owner.setGeometry(rect)
        event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_origin = self.drag_rect = None
        event.accept()


class DesktopWindow(QMainWindow):
    backdropChanged = Signal(str)

    def __init__(self, parent=None, flags=Qt.WindowType.Window, theme=None):
        theme = theme or getattr(parent, '_surface_theme', 'dark')
        self._surface_theme = theme
        glass = theme == 'glass'
        super().__init__(parent, flags | (Qt.WindowType.FramelessWindowHint if glass else Qt.WindowType.Widget))
        self._theme = theme
        self._backdrop = False
        self._native_backdrop_allowed = glass
        self._glass_tint = getattr(parent, '_glass_tint', 46)
        self._chrome = self._glass_menu = self.title_bar = None
        self._resize_handles = []
        self._backdrop_timer = QTimer(self)
        self._backdrop_timer.setSingleShot(True)
        self._backdrop_timer.timeout.connect(self.refresh_backdrop)
        if glass:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAutoFillBackground(False)
            self.setContentsMargins(1, 1, 1, 1)
            self._chrome = QWidget(self)
            self._chrome.setObjectName('windowChrome')
            stack = QVBoxLayout(self._chrome)
            stack.setContentsMargins(0, 0, 0, 0)
            stack.setSpacing(0)
            self.title_bar = TitleBar(self)
            stack.addWidget(self.title_bar)
            self._glass_menu = QMenuBar(self._chrome)
            self._glass_menu.setNativeMenuBar(False)
            stack.addWidget(self._glass_menu)
            self._glass_menu.hide()
            self.setMenuWidget(self._chrome)
            L, R, T, B = Qt.Edge.LeftEdge, Qt.Edge.RightEdge, Qt.Edge.TopEdge, Qt.Edge.BottomEdge
            self._resize_handles = [ResizeHandle(self, edges) for edges in (L, R, T, B, L|T, R|T, L|B, R|B)]

    def menuBar(self):
        if self._glass_menu is not None:
            self._glass_menu.show()
            return self._glass_menu
        return super().menuBar()

    def showEvent(self, event):
        super().showEvent(event)
        self.layout_resize_handles()
        self.schedule_backdrop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.layout_resize_handles()

    def changeEvent(self, event):
        super().changeEvent(event)
        # Recheck Windows preferences on return from Settings. Reuse the same
        # native surface: no HWND recreation, extra native filter, or mask.
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            if hasattr(self, '_backdrop_timer'):
                self.schedule_backdrop()
        if event.type() == QEvent.Type.WindowStateChange:
            self.layout_resize_handles()
            self.update()

    def layout_resize_handles(self):
        handles = getattr(self, '_resize_handles', [])
        if not handles:
            return
        w, h = self.size().width(), self.size().height()
        edge, corner = 9, 20  # logical pixels, so targets grow with Windows scaling
        positions = ((0, corner, edge, max(1, h-2*corner)),
                     (w-edge, corner, edge, max(1, h-2*corner)),
                     (corner, 0, max(1, w-2*corner), edge),
                     (corner, h-edge, max(1, w-2*corner), edge),
                     (0, 0, corner, corner), (w-corner, 0, corner, corner),
                     (0, h-corner, corner, corner), (w-corner, h-corner, corner, corner))
        enabled = not (self.isMaximized() or self.isFullScreen())
        for handle, geometry in zip(handles, positions):
            handle.setGeometry(*geometry)
            handle.setVisible(enabled)
            handle.raise_()

    def set_glass_tint(self, value):
        self._glass_tint = max(25, min(85, int(value)))
        self.update()  # Changing tint is paint-only; never recreate a native surface.

    def schedule_backdrop(self):
        if self._native_backdrop_allowed:
            self._backdrop_timer.start(0)
        else:
            status = 'Classic window — restart ClipNest to enable the saved Glass theme' if self._theme == 'glass' else 'Classic dark'
            self.setProperty('backdropMode', status)
            self.backdropChanged.emit(status)

    def refresh_backdrop(self):
        if not self.isVisible() or self.windowHandle() is None:
            return
        from .theme import apply_native_backdrop
        try:
            self._backdrop = apply_native_backdrop(self, self._theme)
        except (OSError, AttributeError) as error:
            logging.warning('Native backdrop unavailable: %s', error)
            self._backdrop = False
            self.setProperty('backdropMode', 'Opaque fallback — native backdrop unavailable')
        status = str(self.property('backdropMode') or 'Opaque fallback')
        logging.info('Window appearance [%s]: %s', self.windowTitle(), status)
        self.backdropChanged.emit(status)
        self.update()

    def paintEvent(self, event):
        if not self._native_backdrop_allowed:
            return super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        if self._theme == 'glass' and self._backdrop:
            alpha = round(255*self._glass_tint/100)
            tint = QLinearGradient(0, 0, self.size().width(), self.size().height())
            tint.setColorAt(0, QColor(29, 38, 35, max(30, alpha-16)))
            tint.setColorAt(.48, QColor(14, 23, 20, alpha))
            tint.setColorAt(1, QColor(32, 42, 43, min(235, alpha+12)))
            painter.fillRect(self.rect(), tint)
            rim = QLinearGradient(0, 0, 0, self.size().height())
            rim.setColorAt(0, QColor(240, 255, 246, 150))
            rim.setColorAt(.5, QColor(212, 235, 223, 45))
            rim.setColorAt(1, QColor(222, 240, 245, 100))
            painter.setPen(QPen(rim, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            # Windows 11 applies native corner rounding; Windows 10 stays rectangular.
            # Never use a native region/mask to force rounded compositor geometry.
            painter.drawRect(area)
        else:
            painter.fillRect(self.rect(), QColor(16, 19, 18))
        if not self.isMaximized():
            painter.setPen(QPen(QColor(205, 225, 211, 120), 1))
            w, h = self.size().width()-4, self.size().height()-4
            for offset in (4, 8, 12):
                painter.drawLine(w-offset, h, w, h-offset)
