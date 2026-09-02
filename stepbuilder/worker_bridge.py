"""The window's half of the build process: start it, drain what it says,
notice it die, kill it on request.

No tkinter here. The window hands in five callbacks and they are called on
whatever thread calls `drain_once` - the window's Tk `after` loop, so the
callbacks may touch widgets; the bridge itself touches none. Round 74,
plan C5: out of gui.py, behaviour for behaviour (test_gui [9], [9b]).
"""

from __future__ import annotations

import multiprocessing
import queue
from typing import Callable

from .worker import BuildSettings, run_jobs

# 0xC0000005: what a process ends with when OpenCASCADE reads memory it must
# not - measured on a real board, in the fuse that stitches the layer solids.
ACCESS_VIOLATION = -1073741819


def crash_advice(code: int | None) -> str:
    """What to tell the user about a build that stopped without a word."""
    detail = (f"The build stopped without finishing (exit code {code})."
              if code is not None else "The build stopped without finishing.")
    if code == ACCESS_VIOLATION:
        detail += ("\nThat is an access violation inside OpenCASCADE, not "
                   "something the export can catch.")
    detail += ("\n\nWhat usually gets a board through: set Body stitching "
               "to 'Not stitched' (it fuses nothing), or raise "
               "gui.foldSliceAngle - a bend that has to be faceted makes "
               "harder work for the fuse the finer it is sliced. The log "
               "above ends at whatever it was doing.")
    return detail


class WorkerBridge:
    """A build process and its queue. `process` is the live
    `multiprocessing.Process` or None; `finished` says the build reported its
    end (done or error) or was seen dead; `cancelled` marks a kill on purpose,
    so the exit code is not reported as a crash."""

    def __init__(self, *, on_log: Callable[[str], None],
                 on_progress: Callable[[int, int, str | None], None],
                 on_done: Callable[[str], None], on_error: Callable[[str], None],
                 on_crash: Callable[[str], None]) -> None:
        self._queue = multiprocessing.Queue()
        self.process: multiprocessing.Process | None = None
        self.finished = False
        self.cancelled = False
        self._on_log = on_log
        self._on_progress = on_progress
        self._on_done = on_done
        self._on_error = on_error
        self._on_crash = on_crash

    @property
    def alive(self) -> bool:
        return self.process is not None and self.process.is_alive()

    def start(self, settings: BuildSettings) -> bool:
        """Start a build; False if one is already running."""
        if self.alive:
            return False
        self.finished = False
        self.cancelled = False
        self.process = multiprocessing.Process(
            target=run_jobs, args=(settings, self._queue), daemon=True)
        self.process.start()
        return True

    def drain_once(self) -> None:
        """Hand everything queued to the callbacks, then look for a death."""
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "log":
                    self._on_log(payload)
                elif kind == "progress":
                    current, total, *rest = payload
                    self._on_progress(current, total, rest[0] if rest else None)
                elif kind == "done":
                    self.finished = True
                    self._on_done(payload)
                elif kind == "error":
                    self.finished = True
                    self._on_error(payload)
        except queue.Empty:
            pass
        self.check_alive()

    def check_alive(self) -> None:
        """A build that died without saying so still has to be reported.

        OpenCASCADE can take its process down with an access violation rather
        than an exception - measured on a real board, in the fuse that stitches
        the layer solids - and before the build moved into a child process that
        was this window disappearing. Now the exit code arrives here instead.
        """
        if self.process is None or self.process.is_alive() or self.finished:
            return
        if self.cancelled:
            # Killed on purpose: the exit code is whatever terminate() gives,
            # and reporting that as a crash would be a lie with a traceback
            # attached.
            self.cancelled = False
            self.process = None
            self.finished = True
            return
        code = self.process.exitcode
        self.process = None
        self.finished = True
        if code == 0:
            return                       # said its piece and exited cleanly
        self._on_crash(crash_advice(code))

    def cancel(self) -> bool:
        """Kill the running build; False if none is running.

        A real kill rather than a polite request - the only thing that works:
        OCCT spends minutes inside a single boolean and nothing checks a flag
        in there. The file being written at that moment can be left half
        finished; the window says so.
        """
        if not self.alive:
            return False
        self.cancelled = True
        process = self.process
        process.terminate()
        self.process = None
        self.finished = True
        return True

    def close(self) -> None:
        """The window is going: kill a live build, let the queue go."""
        if self.alive:
            self.process.terminate()
        try:
            self._queue.close()
            self._queue.cancel_join_thread()
        except Exception:
            pass
