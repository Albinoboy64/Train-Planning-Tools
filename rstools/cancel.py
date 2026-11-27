"""Stopping a long run from the window (Stop button or Esc).

Every task reports its progress and log lines to the window through a queue. StopQueue is that queue: once
stop() has been called, the next progress or log message a worker thread sends raises Cancelled there, so the
run ends between two steps. Outputs are written to a temporary file and only renamed when complete, so a
stopped run leaves nothing half-written. The window then receives a ('stopped',) message."""
from __future__ import annotations

import queue
import threading

REPORTS = ("log", "prog", "progress", "status", "phase", "step")     # messages a worker sends while it works


class Cancelled(SystemExit):
    """The run was stopped by the user. A SystemExit, so the workers' 'except Exception' error handlers let it
    through and the thread ends quietly."""

    def __init__(self):
        super().__init__("Stopped - nothing was saved.")


class StopQueue(queue.Queue):
    def __init__(self):
        super().__init__()
        self._stop = threading.Event()

    def stop(self):
        """Ask the running task to stop at its next step."""
        self._stop.set()

    def reset(self):
        """A new run starts: forget an earlier stop."""
        self._stop.clear()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def put(self, item, block=True, timeout=None):
        if (self._stop.is_set() and isinstance(item, tuple) and item and item[0] in REPORTS
                and threading.current_thread() is not threading.main_thread()):
            super().put(("stopped",), block, timeout)
            raise Cancelled()
        super().put(item, block, timeout)
