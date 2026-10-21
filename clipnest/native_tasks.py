"""Serial executor for libobs tasks that normally run on OBS's UI thread."""
import ctypes as C
import logging
import os
import queue
import threading

TASK = C.CFUNCTYPE(None, C.c_void_p)
UI_HANDLER = C.CFUNCTYPE(None, TASK, C.c_void_p, C.c_bool)


class NativeTasks:
    def __init__(self):
        self.queue = queue.Queue()
        self.callback = UI_HANDLER(self.submit)
        self.thread = threading.Thread(target=self.run, name='ClipNest OBS tasks', daemon=True)
        self.thread.start()

    def submit(self, task, param, wait):
        if threading.current_thread() is self.thread:
            task(param)
            return
        done = threading.Event()
        self.queue.put((task, param, done))
        if wait:
            done.wait()

    def run(self):
        ole = None
        if os.name == 'nt':
            ole = C.WinDLL('ole32')
            initialized = ole.CoInitializeEx(None, 2) in (0, 1)
        try:
            while True:
                entry = self.queue.get()
                if entry is None:
                    return
                task, param, done = entry
                try:
                    task(param)
                except Exception:
                    logging.getLogger('clipnest').exception('OBS UI task failed')
                finally:
                    done.set()
        finally:
            if ole is not None and initialized:
                ole.CoUninitialize()

    def flush(self):
        # A barrier keeps source-destruction tasks ahead of plugin unloading.
        self.submit(TASK(lambda _: None), None, True)

    def close(self):
        self.queue.put(None)
        self.thread.join(5)
