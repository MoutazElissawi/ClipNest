"""Export progress with contrasting text on both sides of the fill edge."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QProgressBar


class ExportProgressBar(QProgressBar):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        outline = QPainterPath()
        outline.addRoundedRect(rect, 4, 4)
        painter.setClipPath(outline)
        painter.fillRect(rect, QColor(255, 255, 255, 24))
        span = self.maximum() - self.minimum()
        fraction = max(0.0, min(1.0, (self.value() - self.minimum()) / span)) if span else 0.0
        fill = QRectF(rect)
        fill.setWidth(rect.width() * fraction)
        if self.invertedAppearance() != (self.layoutDirection() == Qt.LayoutDirection.RightToLeft):
            fill.moveRight(rect.right())
        from .external_theme import active_palette
        palette = active_palette()
        colors = palette['colors'] if palette else {}
        painter.fillRect(fill, QColor(colors.get('accent', '#9cf236')))
        if self.isTextVisible():
            painter.setPen(QColor(colors.get('text', 'white')))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())
            painter.setClipRect(fill, Qt.ClipOperation.IntersectClip)
            painter.setPen(QColor(colors.get('accent_text', 'black')))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())
        painter.end()
