"""Pause off-screen players without changing capture or automatically restarting audio."""
from PySide6.QtCore import QObject, QEvent
from PySide6.QtMultimedia import QMediaPlayer


class PlaybackLifecycle(QObject):
    def __init__(self, window, player, canvas=None):
        super().__init__(window)
        self.window, self.player, self.canvas = window, player, canvas
        window.installEventFilter(self)

    def eventFilter(self, watched, event):
        hidden = event.type() == QEvent.Type.Hide
        minimized = event.type() == QEvent.Type.WindowStateChange and self.window.isMinimized()
        if hidden or minimized:
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.player.pause()
            if self.canvas is not None:
                self.canvas.suspend_frames()
        elif event.type() in (QEvent.Type.Show, QEvent.Type.WindowStateChange) and not self.window.isMinimized():
            if self.canvas is not None:
                self.canvas.resume_frames()
        return False
