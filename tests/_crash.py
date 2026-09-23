"""A child process that dies of a REAL access violation, for the suites that
check how a crash is reported (round 92).

Why a real one. `worker_bridge.crash_advice` compared the exit code with a
constant, and the only test of it handed a stand-in process that very
constant - so the test could not see that a real crash arrives as a
different integer (3221225477, not -1073741819), and for two months the
window never said "access violation". A test built on its own copy of the
value proves the copy.

Why a module of its own. On Windows multiprocessing SPAWNS the child, and
the child's first act is to re-run the parent's main module - for a suite,
the whole suite file, which in test_gui.py would open windows and run every
check again inside the child (the reason [9] used a stand-in in the first
place). `spawn_crash` starts the child with THIS module as the one it
re-runs, so all the child executes before it dies is these few lines.
"""
from __future__ import annotations

import faulthandler
import importlib.util
import multiprocessing
import sys


def read_null() -> None:
    """Read through a NULL pointer in plain C and die of it.

    STATUS_ACCESS_VIOLATION (0xC0000005), exactly the way OpenCASCADE ends a
    process when it reads memory it must not. Not `ctypes.string_at(0)`:
    ctypes catches that exception itself and raises OSError, and the child
    exits with 1. faulthandler's test hook first switches Windows Error
    Reporting off for the process (SEM_NOGPFAULTERRORBOX), so the crash
    opens no dialog and leaves no report on C: - checked 2026-09-23: none
    in ProgramData/Microsoft/Windows/WER, where the real crashes of July
    left theirs.
    """
    faulthandler._read_null()


def spawn_crash() -> multiprocessing.Process:
    """Start a spawned child that dies at once of an access violation.

    What a spawned child re-runs is decided when start() gathers what to
    send it: the main module's `__spec__` if it has one, its file if not.
    A suite run as a script has no spec, so for the length of start() the
    main module is given this module's spec, and has its own put back
    straight after, whatever happens.
    """
    main = sys.modules["__main__"]
    saved = main.__spec__
    main.__spec__ = importlib.util.find_spec(__name__)
    try:
        child = multiprocessing.get_context("spawn").Process(target=read_null, daemon=True)
        child.start()
    finally:
        main.__spec__ = saved
    return child
