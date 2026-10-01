"""Request/reply transport to our own libobs process over anonymous pipes."""
import json
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
        deadline = time.monotonic() + (45 if method in ("Initialize", "Shutdown") else 30)
        while time.monotonic() < deadline:
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

    def disconnect(self):
        if self.closed: return
        self.closed = True
        if self.process.stdin:
            try: self.process.stdin.close()
            except (BrokenPipeError, OSError): pass
        try: self.process.wait(timeout=25)
        except subprocess.TimeoutExpired:
            raise NativeError("Native recorder is still finishing. Restart ClipNest only after its background process exits; do not delete _Unsorted files.")
        finally:
            if self.process.poll() is not None:
                self.reader.join(timeout=2)
                self.log.close()

    def close(self):
        if self.closed: return
        try:
            if self.process.poll() is None:
                self.call("Shutdown")
        finally:
            self.disconnect()
