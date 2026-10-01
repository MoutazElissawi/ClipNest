"""Aspect-correct crop editor using a decoded source frame."""
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import QWidget, QDialog, QVBoxLayout, QLabel, QDialogButtonBox, QPushButton


class CropCanvas(QWidget):
    def __init__(self, image, width, height, crop=None):
        super().__init__()
        self.image, self.source_width, self.source_height = image, width, height
        self.rect = QRectF(*(crop or (0, 0, width-width%2, height-height%2)))
        self.drag = None
        self.setMinimumSize(480, 270)
        self.setMouseTracking(True)

    def picture_rect(self):
        scale = min(self.width()/self.source_width, self.height()/self.source_height)
        w, h = self.source_width*scale, self.source_height*scale
        return QRectF((self.width()-w)/2, (self.height()-h)/2, w, h)

    def to_source(self, point):
        area = self.picture_rect()
        return QPointF(max(0, min(self.source_width, (point.x()-area.x())*self.source_width/area.width())),
                       max(0, min(self.source_height, (point.y()-area.y())*self.source_height/area.height())))

    def selection(self):
        r = self.rect.normalized()
        x, y = int(r.left())//2*2, int(r.top())//2*2
        right = min(self.source_width//2*2, max(x+2, int(r.right())//2*2))
        bottom = min(self.source_height//2*2, max(y+2, int(r.bottom())//2*2))
        return x, y, right-x, bottom-y

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect_or_widget(), QColor('#0f0f0f'))
        area = self.picture_rect()
        p.drawImage(area, self.image)
        scale = area.width()/self.source_width
        r = QRectF(area.x()+self.rect.x()*scale, area.y()+self.rect.y()*scale,
                   self.rect.width()*scale, self.rect.height()*scale)
        outside = QPainterPath()
        outside.addRect(area)
        inside = QPainterPath()
        inside.addRect(r)
        p.fillPath(outside.subtracted(inside), QColor(65, 68, 74, 115))
        p.setPen(QPen(QColor('#a4d65e'), 3))
        p.drawRect(r)
        p.setBrush(QColor('#ffffff'))
        for point in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
            p.drawRect(QRectF(point.x()-6, point.y()-6, 12, 12))
        p.setPen(QColor('white'))
        p.drawText(12, 24, 'Crop: ' + ' × '.join(map(str, self.selection()[2:])))

    def rect_or_widget(self):
        return QRectF(0, 0, self.width(), self.height())

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.picture_rect().contains(event.position()):
            return
        point = self.to_source(event.position())
        corners = [self.rect.topLeft(), self.rect.topRight(), self.rect.bottomLeft(), self.rect.bottomRight()]
        tolerance = 18*self.source_width/self.picture_rect().width()
        nearest = min(range(4), key=lambda i: (corners[i]-point).manhattanLength())
        if (corners[nearest]-point).manhattanLength() <= tolerance:
            self.drag = ('corner', corners[3-nearest])
        elif self.rect.contains(point):
            self.drag = ('move', point, QRectF(self.rect))
        else:
            self.drag = ('corner', point)
        self.grabMouse()

    def mouseMoveEvent(self, event):
        if not self.drag:
            return
        point = self.to_source(event.position())
        if self.drag[0] == 'corner':
            candidate = QRectF(self.drag[1], point).normalized()
            if candidate.width() >= 2 and candidate.height() >= 2:
                self.rect = candidate
        else:
            delta = point-self.drag[1]
            old = self.drag[2]
            self.rect.moveTo(max(0, min(self.source_width-old.width(), old.x()+delta.x())),
                             max(0, min(self.source_height-old.height(), old.y()+delta.y())))
        self.update()

    def mouseReleaseEvent(self, event):
        if self.drag:
            self.drag = None
            self.releaseMouse()
            self.rect = QRectF(*self.selection())
            self.update()


class CropDialog(QDialog):
    def __init__(self, image, width, height, crop, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Drag crop corners')
        self.resize(900, 650)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Drag any white corner; drag inside the box to move it. The blue box is the exported area.'))
        self.canvas = CropCanvas(image, width, height, crop)
        layout.addWidget(self.canvas, 1)
        reset = QPushButton('Use full image')
        reset.clicked.connect(lambda: self.reset_crop(width, height))
        layout.addWidget(reset)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def reset_crop(self, width, height):
        self.canvas.rect = QRectF(0, 0, width-width%2, height-height%2)
        self.canvas.update()
