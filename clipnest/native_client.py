"""Request/reply transport to our own libobs process over anonymous pipes."""
import json
import logging
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid
from .config import DATA, ENGINE


def host_command(env):
    if os.name != "nt":
        return [sys.executable, "-u", "-m", "clipnest.native_host"]
    # OBS resolves its helper EXEs beside GetModuleFileNameW(NULL), not cwd/PATH.
    # Use the real base interpreter, not the venv redirector, in our private runtime.
    base = Path(sys.base_prefix)
    binary = base / "ClipNestRecorder.exe"
    if not binary.is_file():
        binary = base / "python.exe"
    target = ENGINE / "bin/64bit"
    if not binary.is_file():
        raise RuntimeError(f"Cannot locate the base Python interpreter: {binary}")
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, target / "clipnest-host.exe")
    for pattern in ("python3*.dll", "vcruntime*.dll"):
        for dll in base.glob(pattern):
            if pattern.startswith("vcruntime") and (target / dll.name).exists():
                continue
            shutil.copy2(dll, target / dll.name)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONHOME"] = str(base)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    env["PATH"] = str(base) + os.pathsep + env.get("PATH", "")
    return [str(target / "clipnest-host.exe"), "-u", "-m", "clipnest.native_host"]

class NativeError(RuntimeError): pass

class NativeClient:
    def __init__(self, settings, event_callback=lambda *_: None, command=None):
        self.event_callback = event_callback
        self.messages = queue.Queue()
        self.closed = False
        self.shutdown_deadline = None
        self.shutdown_timer = None
        self.forced = False
        self._shutdown_lock = threading.Lock()
        self._stop_lock = threading.Lock()
        DATA.mkdir(parents=True, exist_ok=True)
        log_path = DATA / "native-engine.log"
        if log_path.exists() and log_path.stat().st_size > 5_000_000:
            log_path.replace(DATA / "native-engine.previous.log")
        self.log = log_path.open("ab", buffering=0)
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        self.process = subprocess.Popen(command or host_command(env),
            cwd=str(Path(__file__).resolve().parents[1]), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.log, text=True, encoding="utf-8", bufsize=1, env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            self.info = self.call("Initialize", settings=settings)
        except Exception:
            # EOF tells a partly initialized host to release its native resources.
            self.disconnect()
            raise

    def _read(self):
        try:
            for line in self.process.stdout:
                try: self.messages.put(json.loads(line))
                except ValueError: self.log.write(line.encode("utf-8", errors="replace"))
        finally:
            self.messages.put({"disconnected": True})

    def dispatch(self, message):
        if message.get("disconnected"):
            try: code = self.process.wait(timeout=2)
            except subprocess.TimeoutExpired: code = "stdout closed while process is still running"
            raise ConnectionError(f"Native engine exited (code {code}). Open File → Open recorder logs.")
        if "event" in message:
            self.event_callback(message["event"], message.get("data", {}))

    def call(self, method, **args):
        if self.closed or self.process.poll() is not None:
            raise ConnectionError("Native recorder is not running. Start the engine again.")
        ident = uuid.uuid4().hex
        self.process.stdin.write(json.dumps({"id": ident, "method": method, "args": args}) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + (75 if method == "Shutdown" else 45 if method == "Initialize" else 30)
        while time.monotonic() < deadline:
            if self.shutdown_deadline is not None and time.monotonic() >= self.shutdown_deadline:
                raise TimeoutError(f'Native recorder shutdown deadline reached during {method}.')
            try: msg = self.messages.get(timeout=min(.2, max(.01, deadline - time.monotonic())))
            except queue.Empty: continue
            if msg.get("id") == ident:
                if "error" in msg: raise NativeError(msg["error"])
                return msg.get("result", {})
            self.dispatch(msg)
        raise TimeoutError(f"Native engine timed out during {method}. Check native-engine.log.")

    def pump(self):
        for _ in range(30):
            try: self.dispatch(self.messages.get_nowait())
            except queue.Empty: return

    def begin_shutdown(self, timeout=20):
        """Arm once, even while the controller is blocked in an earlier call.

        Only our Popen child can be terminated. A retry never extends its grace
        period, and the timer never dispatches events or touches Qt objects.
        """
        with self._shutdown_lock:
            if self.shutdown_deadline is not None:
                return
            self.shutdown_deadline = time.monotonic() + timeout
            self.shutdown_timer = threading.Timer(timeout, self.force_stop)
            self.shutdown_timer.daemon = True
            self.shutdown_timer.start()

    def force_stop(self):
        with self._stop_lock:
            if self.process.poll() is not None:
                return
            self.forced = True
            logging.error('Native recorder did not finish in time; terminating owned child PID %s. Staging files are retained.', self.process.pid)
            try:
                self.process.terminate()
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
            except ProcessLookupError:
                pass

    def disconnect(self):
        self.closed = True
        if self.process.stdin and not self.process.stdin.closed:
            try: self.process.stdin.close()
            except (BrokenPipeError, OSError): pass
        remaining = 25 if self.shutdown_deadline is None else max(.01, self.shutdown_deadline-time.monotonic())
        try: self.process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            self.force_stop()
        finally:
            if self.process.poll() is not None:
                if self.shutdown_timer is not None:
                    self.shutdown_timer.cancel()
                self.reader.join(timeout=2)
                # EOF cleanup can emit final recording/replay paths after the
                # Shutdown reply was lost. Deliver these before archiving ends.
                while True:
                    try:
                        message = self.messages.get_nowait()
                    except queue.Empty:
                        break
                    if "event" in message:
                        self.dispatch(message)
                self.log.close()

    def close(self):
        self.begin_shutdown()
        if self.closed:
            self.disconnect()
            return
        try:
            if self.process.poll() is None:
                self.call("Shutdown")
        finally:
            self.disconnect()
