"""`ClipNest --save-replay` / `--toggle-record` for desktop shortcuts on Wayland.

Wayland lets no app grab global keys, so users bind a system shortcut to one of
these commands. A second ClipNest process hands the command to the running one
over a per-user local socket and exits.
"""
import getpass
from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket

COMMANDS = {"--save-replay": "save_replay", "--toggle-record": "toggle_record"}


def server_name():
    return f"clipnest-commands-{getpass.getuser()}"


def requested(argv):
    return next((COMMANDS[a] for a in argv if a in COMMANDS), None)


def send(command, timeout=1500):
    """Deliver a command to the running ClipNest. False when none is listening."""
    socket = QLocalSocket()
    socket.connectToServer(server_name())
    if not socket.waitForConnected(timeout):
        return False
    socket.write(command.encode("ascii") + b"\n")
    # waitForBytesWritten is False when the bytes already left, so check what is still queued.
    socket.flush()
    if socket.bytesToWrite():
        socket.waitForBytesWritten(timeout)
    sent = socket.bytesToWrite() == 0
    socket.disconnectFromServer()
    if socket.state() != QLocalSocket.UnconnectedState:
        socket.waitForDisconnected(timeout)
    return sent


class CommandServer(QObject):
    def __init__(self, parent, submit):
        super().__init__(parent)
        self.submit = submit
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        QLocalServer.removeServer(server_name())  # A crashed run leaves its socket file behind.
        self.server.newConnection.connect(self.accept)
        self.listening = self.server.listen(server_name())

    def accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.readyRead.connect(lambda s=socket: self.read(s))
            socket.disconnected.connect(socket.deleteLater)
            self.read(socket)

    def read(self, socket):
        while socket.canReadLine():
            command = bytes(socket.readLine()).decode("ascii", errors="ignore").strip()
            if command in COMMANDS.values():
                self.submit(command)

    def close(self):
        self.server.close()
