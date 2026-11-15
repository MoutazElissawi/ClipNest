"""Step a paused player one frame at a time, from the frame on screen."""
from PySide6.QtCore import QObject
from PySide6.QtMultimedia import QMediaMetaData


class FrameStepper(QObject):
    """The player's clock can be a few frames behind the picture after a pause, so a step starts from the
    shown frame's own timestamp and seeks to the middle of its neighbour."""
    def __init__(self, player, sink):
        super().__init__(player)
        self.player, self.sink = player, sink
        self.target = None  # microseconds; the frame a step is still seeking to, so held keys keep counting
        sink.videoFrameChanged.connect(self.arrived)

    def arrived(self, _frame):
        self.target = None

    def step(self, direction):
        """Pause and show the previous (-1) or next (+1) frame. False if the frame timing is not known."""
        frame = self.sink.videoFrame()
        fps = self.player.metaData().value(QMediaMetaData.Key.VideoFrameRate)
        if not frame.isValid() or frame.startTime() < 0 or not isinstance(fps, (int, float)) or not 0 < fps <= 1000:
            return False
        length = 1e6/fps
        shown = frame.startTime()+length/2 if self.target is None else self.target
        self.player.pause()
        target = max(0, min((self.player.duration()-1)*1000, shown+direction*length))
        self.player.setPosition(round(target/1000))
        self.target = target  # after the seek: a frame delivered by pause() must not clear it
        return True
