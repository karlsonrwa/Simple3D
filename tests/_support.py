"""What every test script shares: where the repository is, where a test may
write, the one check() that decides the exit code, the one way a STEP file is
measured, the one turn at the session's clipboard (SessionTurn, round 94) and
the one way text is put on it (put_clipboard_text, round 96).

The scripts are run one by one by tests/run_all.py, which reads only the
subprocess's exit code - a suite that prints FAIL and exits 0 passes. So a
suite ends with `sys.exit(0 if not fails else 1)` over THIS module's `fails`
list. A suite that rebinds `fails = []` of its own has cut that wire; round 70
found the C++ regression in that state (it printed MATCH or DRIFT and exited 0
either way, from the day it was written).

Import it as `from _support import ...`: the script's own folder is the first
entry on sys.path when Python runs it as a file, so nothing else is needed.
Importing puts the repository root on sys.path, so `stepbuilder` resolves as a
PACKAGE - core.py imports its siblings relatively inside the functions that
need them, and a bare `import core` fails there, not at the top of the file.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "test-output"        # gitignored
OUT.mkdir(parents=True, exist_ok=True)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

fails: list[str] = []


def check(name, cond, detail="") -> bool:
    """Print one PASS/FAIL line and remember the failures for the exit code."""
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + str(detail)}")
    if not cond:
        fails.append(name)
    return bool(cond)


def out_dir(name: str) -> Path:
    """build/test-output/<name>/, created."""
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def rect(x0, y0, x1, y1) -> list[dict]:
    """A closed rectangle as the four `segment` primitives the intermediate uses."""
    return [{"type": "segment", "start": [x0, y0], "end": [x1, y0]},
            {"type": "segment", "start": [x1, y0], "end": [x1, y1]},
            {"type": "segment", "start": [x1, y1], "end": [x0, y1]},
            {"type": "segment", "start": [x0, y1], "end": [x0, y0]}]


# ---- windows nobody has to watch ------------------------------------------ #

# Kept open for the life of the process: a desktop disappears with its last
# handle, and the windows on it with it.
_OWN_DESKTOP = None


def keep_windows_off_screen() -> str:
    """Put every window THIS thread creates from now on on a desktop of its
    own - "Simple3D-tests", in the same session - that nobody looks at.

    The GUI suites need windows that are really MAPPED: a withdrawn one
    reports the size it asked for rather than where it is, and drops a
    generated click (test_geom, test_gui [7i]). Mapped on the user's desktop
    they pop up while the suites run - a dozen per run, one maximized, and
    under tools/mutate.py four copies at once. On a desktop of their own
    they are the same windows, measured the same way: the screen, the
    virtual desktop and the DPI are the session's, and winplace reads
    nothing else - but they are not drawn where anyone looks, take no
    taskbar button and cannot take the focus from the user's work (round
    94). The clipboard stays the session's: SessionTurn is still needed.

    Must run before the thread creates its first window - Tk's, at the first
    Tk() - which is why a suite calls it right after importing this module.
    Returns "" once done, or why it could not be; the windows are then
    simply shown as before.
    """
    global _OWN_DESKTOP
    if sys.platform != "win32":
        return "not Windows"
    if _OWN_DESKTOP is not None:
        return ""
    import ctypes
    from ctypes import wintypes

    u32 = ctypes.windll.user32
    u32.CreateDesktopW.restype = wintypes.HANDLE
    u32.CreateDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p,
                                   wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    u32.SetThreadDesktop.restype = wintypes.BOOL
    u32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
    GENERIC_ALL = 0x10000000
    # Created by the first suite, opened by every later one: CreateDesktopW
    # hands back the existing desktop of that name.
    desktop = u32.CreateDesktopW("Simple3D-tests", None, None, 0, GENERIC_ALL, None)
    if not desktop:
        return f"CreateDesktopW failed with error {ctypes.GetLastError()}"
    if not u32.SetThreadDesktop(desktop):
        return f"SetThreadDesktop failed with error {ctypes.GetLastError()}"
    _OWN_DESKTOP = desktop
    return ""


# ---- a turn at the Windows session, for a suite that writes the clipboard -- #

class SessionTurn:
    """A turn at what a Windows SESSION has only one of - the clipboard -
    taken from every other process that asks by the same name (round 94).

    tools/mutate.py runs the suites on four copies of the tree at once, and a
    copy isolates files, not the session. test_gui [7g] and [7h] put a path on
    the real clipboard and paste it back; on 2026-09-23 one copy's text was
    replaced by another's in between, "[7g] and the STEP-folders box pastes
    too" failed, and a mutation that had nothing to do with pasting read as
    caught. A flaky check under a mutation can hide a survivor. So a section
    that writes the clipboard - from reading what the user had there to
    putting it back - runs in `with SessionTurn() as turn:` and goes ahead
    only `if turn.held`.

    A NAMED MUTEX, not a lock file: the copies live in trees that share
    nothing, so a file in one of them locks nothing for the others, while a
    kernel object belongs to the session. The name is step2html's
    (tests/test_editing.py, OneAtATime) on purpose: the clipboard is one per
    session whoever's suite writes it, and mutation runs of several projects
    have shared this machine. A copy killed while holding it leaves it
    ABANDONED, and the next one takes it.

    The wait is long - a turn here is well under a second - but bounded: a
    copy that cannot get one fails with the reason instead of hanging, and
    the reason names the mutex. Off Windows there is nothing to take and
    `held` is simply true.
    """

    NAME = "step2html-tests-one-window"
    OWNED, ABANDONED = 0x0, 0x80           # WAIT_OBJECT_0; the holder died

    def __init__(self, seconds: float = 120.0) -> None:
        self.seconds = seconds
        self.handle = None
        self.why = ""
        self.waited = 0.0
        self._k32 = None

    def __enter__(self) -> "SessionTurn":
        if sys.platform != "win32":
            return self
        import ctypes
        import time

        k32 = ctypes.windll.kernel32
        k32.CreateMutexW.restype = ctypes.c_void_p
        k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        k32.WaitForSingleObject.restype = ctypes.c_uint
        k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        k32.ReleaseMutex.argtypes = [ctypes.c_void_p]
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        self._k32 = k32
        handle = k32.CreateMutexW(None, 0, self.NAME)
        if not handle:
            self.why = f"CreateMutexW({self.NAME!r}) failed with error {ctypes.GetLastError()}"
            return self
        started = time.time()
        got = k32.WaitForSingleObject(handle, int(self.seconds * 1000))
        self.waited = time.time() - started
        if got in (self.OWNED, self.ABANDONED):
            self.handle = handle
        else:
            k32.CloseHandle(handle)
            self.why = (f"another process held {self.NAME!r} for {self.seconds:.0f} s "
                        f"(WaitForSingleObject returned 0x{got:X})")
        return self

    @property
    def held(self) -> bool:
        return self.handle is not None or sys.platform != "win32"

    def __exit__(self, *exc) -> None:
        if self.handle is not None:
            self._k32.ReleaseMutex(self.handle)
            self._k32.CloseHandle(self.handle)
            self.handle = None


# What another process answers when it asks for the turn: exit 0 it got the
# turn (and gave it straight back), 3 it did not within the wait. Anything
# else is the probe itself failing, and a check must not read that as either.
TURN_TAKEN, TURN_REFUSED = 0, 3
_TURN_PROBE = """\
import ctypes, sys
k = ctypes.windll.kernel32
k.CreateMutexW.restype = ctypes.c_void_p
k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
k.WaitForSingleObject.restype = ctypes.c_uint
k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
k.ReleaseMutex.argtypes = [ctypes.c_void_p]
h = k.CreateMutexW(None, 0, sys.argv[1])
got = k.WaitForSingleObject(h, int(sys.argv[2]))
if got in (0, 0x80):
    k.ReleaseMutex(h)
sys.exit(0 if got in (0, 0x80) else 3)
"""


def session_turn_elsewhere(wait_ms: int) -> int:
    """Ask for the session turn from ANOTHER process, waiting up to *wait_ms*:
    TURN_TAKEN, TURN_REFUSED, or the probe's own exit code when it broke.

    The proof that SessionTurn excludes anything at all: while this process
    holds the turn, another one must be refused. A second thread would not
    do - it proves a lock, not that the lock reaches past the process."""
    import subprocess

    done = subprocess.run([sys.executable, "-c", _TURN_PROBE, SessionTurn.NAME, str(wait_ms)],
                          capture_output=True, timeout=wait_ms / 1000.0 + 60)
    return done.returncode


# ---- text on the clipboard as real data, never as Tk's promise ----------- #

CF_UNICODETEXT = 13


class ClipboardBusy(Exception):
    """Another program kept the clipboard open past a wait, so whatever needed
    it can be judged neither way (round 98). A check that meets it says "not
    judged" and fails nothing: a FAIL the session caused, not the code, makes
    an unrelated mutation read as caught. On 23.10.2026 one of step2html's
    puts waited its 2 s and failed while the owner copied something in his
    RDP session (rdpclip.exe carries such a copy across)."""


def clipboard_owned_here() -> bool:
    """Whether the clipboard's owner is a window of this process: then text
    on it put with Tk's clipboard_append is this process's own promise."""
    if sys.platform != "win32":
        return False
    import ctypes
    import os
    from ctypes import wintypes

    u32 = ctypes.windll.user32
    u32.GetClipboardOwner.restype = wintypes.HWND
    u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    owner = u32.GetClipboardOwner()
    if not owner:
        return False
    pid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(owner, ctypes.byref(pid))
    return pid.value == os.getpid()


def _busy(what: str) -> str:
    """The clipboard stayed out of reach: raise ClipboardBusy - unless this
    process owns it. Then what keeps it out of reach is this process's own
    promise, a reader sitting on a render this process never gives: under the
    mutation that puts the test's text with Tk again, rdpclip.exe opened the
    clipboard to read the promise and stayed (step2html, 23.10.2026). That
    defect is this process's, so `what` comes back for the caller to fail on."""
    if clipboard_owned_here():
        return f"{what}, while the clipboard is this process's own promise"
    raise ClipboardBusy(f"{what}: another program kept the clipboard open")


def clipboard_shown(text, own=()) -> str:
    """What a check may print of text that came off the clipboard, or out of
    a field it was pasted into: the text when every line of it is one of the
    test's own (`own`), or when there is none - else only its length. The
    clipboard holds whatever the user last copied, a password as easily as a
    path: on 23.10.2026 a check that printed it put the owner's copied text
    into 18 stress logs on the 4090 (step2html; round 98)."""
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not text or all(line in own for line in lines):
        return repr(text)
    return f"{len(text)} characters that are not this test's"


def put_clipboard_text(text, seconds: float = 10.0, pump=None) -> str:
    """Put `text` on the Windows clipboard as real data - or empty it, for
    None. Returns "" once done, or why it could not be; raises ClipboardBusy
    when another program keeps the clipboard open for `seconds`.

    `pump` - a Tk window's update - is called while the put waits (round 99).
    A copy of Tk's own (the app's Copy, or clipboard_append) is a promise, and
    a reader that opens the clipboard to read it - rdpclip.exe does on every
    change in an RDP session - sits there until this process renders it: a
    put that waits without pumping waits for that reader, which waits for the
    put. step2html's suite, the same code, failed "Ctrl+X cuts it" so in 2
    runs of 102 on the 4090, the put giving up after 10 s with the clipboard
    still its own (23.10.2026).

    Not with Tk's clipboard_clear/clipboard_append (round 96). Those make the
    Tk window the clipboard's OWNER and only promise the text: Windows asks
    the owner for it when somebody reads (delayed rendering), so a reader
    waits for the owner's event loop - up to 30 s, after which it gets
    nothing - and emptying the clipboard waits for the owner too. Measured
    23.10.2026 on the 4090 (build/scratch/clip_deadlock.py): an owner asleep
    8 s held a reader 7.5 s, one past 30 s left it with nothing after exactly
    30.0 s, one that had exited left no text at all; text put here was read
    at once while its writer slept. And in 16 parallel copies of test_gui
    (build/scratch/turn_stress.py): a copy put the user's text back through
    Tk, gave the turn away and went into its give-back probe - a blocking
    subprocess.run, no messages pumped - so the next copy's clipboard_get in
    its turn waited the full 30 s for it, and eight copies' probes ran out
    meanwhile. That is how five unrelated mutations read as caught. After a
    round of those copies the user's own text was gone, or the test's.

    Opened with no owner window, so nobody's event loop is ever needed and the
    text outlives this process. Another process may hold the clipboard open
    for a while - DefenderSessionHelper does for a moment, on the 4090, and
    rdpclip.exe while it reads a change - so the put waits up to `seconds`
    and then leaves the verdict to _busy, never to a plain failure. (One put
    of step2html's that gave up after 2 s was put down to the owner's copy
    over RDP; it was the check right after the app's Cut, as the deadlock
    above - which of the two it was is not measured.)
    """
    if sys.platform != "win32":
        return "not Windows"
    import ctypes
    import time
    from ctypes import wintypes

    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    u32.OpenClipboard.argtypes = [wintypes.HWND]
    u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    u32.SetClipboardData.restype = wintypes.HANDLE
    k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k32.GlobalAlloc.restype = wintypes.HGLOBAL
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalLock.restype = wintypes.LPVOID
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    deadline = time.monotonic() + seconds
    while not u32.OpenClipboard(None):
        if time.monotonic() >= deadline:
            return _busy(f"OpenClipboard failed for {seconds:g} s")
        if pump:
            pump()
        time.sleep(0.02)
    try:
        if not u32.EmptyClipboard():
            return f"EmptyClipboard failed (error {ctypes.GetLastError()})"
        if text is None:
            return ""
        data = (str(text) + "\0").encode("utf-16-le")
        handle = k32.GlobalAlloc(0x0002, len(data))           # GMEM_MOVEABLE
        if not handle:
            return f"GlobalAlloc failed (error {ctypes.GetLastError()})"
        ctypes.memmove(k32.GlobalLock(handle), data, len(data))
        k32.GlobalUnlock(handle)
        if not u32.SetClipboardData(CF_UNICODETEXT, handle):
            k32.GlobalFree(handle)          # still ours: only a success hands it over
            return f"SetClipboardData failed (error {ctypes.GetLastError()})"
        return ""
    finally:
        u32.CloseClipboard()


_CLIP_PROBE = """\
import ctypes, json, sys, time
from ctypes import wintypes
u = ctypes.windll.user32
k = ctypes.windll.kernel32
u.OpenClipboard.argtypes = [wintypes.HWND]
u.GetClipboardData.restype = wintypes.HANDLE
u.GetClipboardData.argtypes = [wintypes.UINT]
k.GlobalLock.restype = wintypes.LPVOID
k.GlobalLock.argtypes = [wintypes.HGLOBAL]
k.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
deadline = time.monotonic() + float(sys.argv[1])
while not u.OpenClipboard(None):
    if time.monotonic() >= deadline:
        sys.exit(3)
    time.sleep(0.02)
try:
    h = u.GetClipboardData(13)
    text = None
    if h:
        text = ctypes.wstring_at(k.GlobalLock(h))
        k.GlobalUnlock(h)
finally:
    u.CloseClipboard()
sys.stdout.write(json.dumps(text))
"""


def clipboard_sequence() -> int:
    """The clipboard's sequence number: every change moves it, whoever makes
    it, and reading never does - so a test that notes it right after its own
    put knows whether anybody has put something since. The user's own copy
    is one: round 96 saw notepad++.exe take the clipboard in the middle of
    test_gui [7g], twice in 220 runs on the 4090."""
    if sys.platform != "win32":
        return 0
    import ctypes

    return ctypes.windll.user32.GetClipboardSequenceNumber()


def put_back_clipboard_text(text, ours: int) -> tuple:
    """Put the user's `text` back as put_clipboard_text does - unless the
    clipboard changed since `ours` (clipboard_sequence() right after this
    test's own last put): what is on it then is newer than `text`, most
    likely the user's own copy, and it is left there.

    Returns ("put", ""), ("left", why) or ("failed", why); ClipboardBusy as
    put_clipboard_text raises it."""
    if clipboard_sequence() != ours:
        return "left", "the clipboard changed since this test's own put"
    why = put_clipboard_text(text)
    return ("failed", why) if why else ("put", "")


_HOLD_OPEN = """\
import ctypes, sys, time
from ctypes import wintypes
u = ctypes.windll.user32
u.CreateWindowExW.restype = wintypes.HWND
u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                              ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
u.OpenClipboard.argtypes = [wintypes.HWND]
# A message-only window (parent HWND_MESSAGE), never shown anywhere: opened
# with no window at all, the clipboard bars nobody else from opening it.
hwnd = u.CreateWindowExW(0, "STATIC", None, 0, 0, 0, 0, 0, wintypes.HWND(-3), None, None, None)
for _ in range(250):
    if hwnd and u.OpenClipboard(hwnd):
        break
    time.sleep(0.02)
else:
    sys.exit(3)
sys.stdout.write("open\\n")
sys.stdout.flush()
time.sleep(float(sys.argv[1]))
u.CloseClipboard()
"""


def clipboard_open_elsewhere() -> bool:
    """Whether a window of another process has the clipboard open right now.
    OpenClipboard then fails (error 5), and so does Tk's read - "clipboard
    cannot be opened, another application grabbed it" - which an entry's
    <<Paste>> swallows, pasting nothing. Opened with no window, the clipboard
    bars nobody. Measured 23.10.2026 (build/scratch/clip_hold_probe.py)."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    u32 = ctypes.windll.user32
    u32.OpenClipboard.argtypes = [wintypes.HWND]
    if u32.OpenClipboard(None):
        u32.CloseClipboard()
        return False
    return True


def hold_clipboard_open(seconds: float):
    """Another process that opens the clipboard with a window of its own and
    holds it `seconds`, as a program that reads it on every change does for
    a moment (rdpclip.exe and DefenderSessionHelper.exe open it in the 4090's
    RDP session): the Popen once the clipboard is open, or None if it never
    was. Wait for it to end."""
    if sys.platform != "win32":
        return None
    import subprocess

    holder = subprocess.Popen([sys.executable, "-c", _HOLD_OPEN, str(seconds)],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if holder.stdout.readline().strip() != b"open":
        holder.wait(10)
        return None
    return holder


_READ_HELD = """\
import ctypes, json, sys, time
from ctypes import wintypes
u = ctypes.windll.user32
k = ctypes.windll.kernel32
u.CreateWindowExW.restype = wintypes.HWND
u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                              ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
u.OpenClipboard.argtypes = [wintypes.HWND]
u.GetClipboardData.restype = wintypes.HANDLE
u.GetClipboardData.argtypes = [wintypes.UINT]
u.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
k.GlobalLock.restype = wintypes.LPVOID
k.GlobalLock.argtypes = [wintypes.HGLOBAL]
k.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
fmt = u.RegisterClipboardFormatW(sys.argv[1]) if len(sys.argv) > 1 else 13
hwnd = u.CreateWindowExW(0, "STATIC", None, 0, 0, 0, 0, 0, wintypes.HWND(-3), None, None, None)
for _ in range(250):
    if hwnd and u.OpenClipboard(hwnd):
        break
    time.sleep(0.02)
else:
    sys.exit(3)
sys.stdout.write("open\\n")
sys.stdout.flush()
sys.stdin.readline()            # "go": the caller pumps no more
h = u.GetClipboardData(fmt)
text = None
if h:
    text = ctypes.wstring_at(k.GlobalLock(h))
    k.GlobalUnlock(h)
u.CloseClipboard()
sys.stdout.write(json.dumps(text))
"""


def read_clipboard_in_background(fmt_name=None, pump=None):
    """Another process that opens the clipboard with a window of its own and,
    told "go" on its stdin, reads the text in the format `fmt_name` (plain
    text for None) - waiting, while that is this process's promise, for this
    process to render it, as rdpclip.exe does with Tk's copy: the Popen once
    the clipboard is open, or None if it never was. Its last line is the
    text, as JSON; the "open" before it is read here.

    `pump` runs while the reader opens the clipboard: a reader of another
    program may hold it open meanwhile, sitting on a promise of this
    process's, and gets out only once this process renders it. Waited for
    without pumping, step2html's reader never got in, in 53 stress runs of
    100 in the owner's session, and the window holding the clipboard was
    rdpclip.exe's (23.10.2026; the same code since round 99)."""
    if sys.platform != "win32":
        return None
    import subprocess
    import threading

    reader = subprocess.Popen([sys.executable, "-c", _READ_HELD] + ([fmt_name] if fmt_name else []),
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL)
    first = []
    waiter = threading.Thread(target=lambda: first.append(reader.stdout.readline()), daemon=True)
    waiter.start()
    while waiter.is_alive():
        if pump is not None:
            pump()
        waiter.join(0.02)
    if not first or first[0].strip() != b"open":
        reader.wait(10)
        return None
    return reader


class ClipboardPromise:
    """Text this thread only promises, in a clipboard format of the test's
    own: a message-only window takes the clipboard and renders the text when
    a reader asks, from this thread's message loop - as a Tk window does with
    its copy, and update() runs that loop for every window of the thread.
    `renders` gets the time of each render, so a check can tell a reader that
    waited on the promise from one that found it rendered.

    Tk's own text would not do in the owner's session: rdpclip.exe opens the
    clipboard for it on every change, and step2html's reader either never got
    in or found nothing to wait for - of 100 stress runs 53 unjudged and 2
    failed on a reader that read nothing, and the row for the rule survived
    (23.10.2026). A format of the test's own nobody else asked for: no render
    before the reader's, and nobody holding the clipboard after the promise,
    in 6 runs of 6 there (step2html's work/clip96/pump_probe2.py). `why` says
    why there is no promise, "" when there is one; close() ends it. `pump`
    runs while the clipboard is out of reach, as in put_clipboard_text.
    Round 99, the same code as step2html's tests/harness.py."""

    def __init__(self, text: str, fmt_name: str, pump=None):
        self.text, self.renders, self.why, self.hwnd = text, [], "", None
        if sys.platform != "win32":
            self.why = "not Windows"
            return
        import ctypes
        import os
        import time
        from ctypes import wintypes

        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        lresult = ctypes.c_ssize_t
        proc_type = ctypes.WINFUNCTYPE(lresult, wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                       wintypes.LPARAM)

        class WndClass(ctypes.Structure):
            _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", proc_type),
                        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

        u32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u32.DefWindowProcW.restype = lresult
        u32.RegisterClassW.argtypes = [ctypes.POINTER(WndClass)]
        u32.RegisterClassW.restype = wintypes.ATOM
        u32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        u32.CreateWindowExW.restype = wintypes.HWND
        u32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        u32.DestroyWindow.argtypes = [wintypes.HWND]
        u32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
        u32.OpenClipboard.argtypes = [wintypes.HWND]
        u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        u32.SetClipboardData.restype = wintypes.HANDLE
        k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        k32.GetModuleHandleW.restype = wintypes.HMODULE
        k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        k32.GlobalAlloc.restype = wintypes.HGLOBAL
        k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        k32.GlobalLock.restype = wintypes.LPVOID
        k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        k32.GlobalFree.argtypes = [wintypes.HGLOBAL]
        self._u32, fmt = u32, u32.RegisterClipboardFormatW(fmt_name)

        def render(hwnd, msg, wparam, lparam):
            if msg == 0x0305 and wparam == fmt:              # WM_RENDERFORMAT
                self.renders.append(time.monotonic())
                data = (self.text + "\0").encode("utf-16-le")
                handle = k32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
                if not handle:
                    self.why = f"GlobalAlloc failed at the render (error {ctypes.GetLastError()})"
                    return 0
                ctypes.memmove(k32.GlobalLock(handle), data, len(data))
                k32.GlobalUnlock(handle)
                if not u32.SetClipboardData(fmt, handle):
                    self.why = f"SetClipboardData failed at the render (error {ctypes.GetLastError()})"
                    k32.GlobalFree(handle)
                return 0
            return u32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._proc = proc_type(render)       # kept alive: Windows calls it while the window lives
        self._hinst = k32.GetModuleHandleW(None)
        self._class = f"Simple3D-test-promise-{os.getpid()}-{id(self)}"
        if not u32.RegisterClassW(ctypes.byref(WndClass(lpfnWndProc=self._proc, hInstance=self._hinst,
                                                        lpszClassName=self._class))):
            self.why = f"RegisterClassW failed (error {ctypes.GetLastError()})"
            return
        self.hwnd = u32.CreateWindowExW(0, self._class, None, 0, 0, 0, 0, 0, wintypes.HWND(-3),
                                        None, self._hinst, None)
        if not self.hwnd:
            self.why = f"CreateWindowExW failed (error {ctypes.GetLastError()})"
            return
        deadline = time.monotonic() + 10
        while not u32.OpenClipboard(self.hwnd):
            if time.monotonic() >= deadline:
                self.why = "OpenClipboard failed for 10 s"
                return
            if pump is not None:
                pump()
            time.sleep(0.02)
        try:
            if not u32.EmptyClipboard():                     # this window is the owner now
                self.why = f"EmptyClipboard failed (error {ctypes.GetLastError()})"
            else:
                u32.SetClipboardData(fmt, None)              # NULL: rendered when asked
        finally:
            u32.CloseClipboard()

    def close(self) -> None:
        if self.hwnd:
            self._u32.DestroyWindow(self.hwnd)
            self.hwnd = None
        if getattr(self, "_class", None):
            self._u32.UnregisterClassW(self._class, self._hinst)
            self._class = None


def clipboard_text_elsewhere(seconds: float = 10.0) -> tuple:
    """What ANOTHER process reads from the clipboard while this one waits for
    it and pumps no messages: (text, "") - text None when there is none - or
    (None, why) when it could not; ClipboardBusy when another program kept
    the clipboard open for half of `seconds` (_busy, round 98).

    Text this process only promised (Tk's clipboard_append) cannot be read
    this way: the reader waits for this process's event loop, which is
    blocked right here, until Windows gives up after 30 s - so `seconds`
    under 30 makes the promise a failure instead of a long wait (round 96).
    The probe opens the clipboard within the first half of `seconds`, so an
    open it never gets (busy) and a read it never finishes (a promise) come
    apart."""
    if sys.platform != "win32":
        return None, "not Windows"
    import json
    import subprocess

    try:
        done = subprocess.run([sys.executable, "-c", _CLIP_PROBE, str(seconds / 2)],
                              capture_output=True, timeout=seconds)
    except subprocess.TimeoutExpired:
        return None, f"another process could not read the clipboard within {seconds:g} s"
    if done.returncode == 3:
        return None, _busy(f"another process could not open the clipboard for {seconds / 2:g} s")
    if done.returncode:
        return None, f"the clipboard probe failed with exit code {done.returncode}"
    return json.loads(done.stdout.decode("utf-8") or "null"), ""


# ---- measuring a STEP file, the way the suites and tools/golden.py do ---- #

def read_step(path):
    """Every root of the file as one shape (STEPControl_Reader.OneShape)."""
    from OCP.STEPControl import STEPControl_Reader
    reader = STEPControl_Reader()
    reader.ReadFile(str(path))
    reader.TransferRoots()
    return reader.OneShape()


def volume(shape) -> float:
    """Volume through the ITERATIVE integrator.

    The plain BRepGProp.VolumeProperties_s(shape, props) measures a solid with
    B-spline walls - which is what a wrapped bend has - about 1.5% light, and
    every number in the fold suite would be measuring that instead of the
    geometry. On planar and cylindrical solids the two agree to 1e-8 (measured
    on the C++ regression board in round 70), so one integrator serves all.
    """
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props, 1.0e-6, False, False)
    return props.Mass()


def bbox(shape) -> tuple[float, float, float, float, float, float]:
    """(xmin, ymin, zmin, xmax, ymax, zmax), using the triangulation where there is one."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from stepbuilder._occt import box_limits
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, True)
    return box_limits(box)


def count_solids(shape) -> int:
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    n = 0
    while exp.More():
        n += 1
        exp.Next()
    return n


def free_edges(shape) -> int:
    """Edges of *shape* that belong to no face of it - a wireframe.

    A face the fold cut away came back as its own flat edges with no face
    between them (round 89): 733 of them in one STEP file, and count_solids,
    volume and area all read the same as before. This is the question that
    sees it.
    """
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp
    from stepbuilder._occt import (TopTools_IndexedDataMapOfShapeListOfShape,
                                   TopTools_IndexedMapOfShape)
    owners = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_ShapeEnum.TopAbs_EDGE,
                                   TopAbs_ShapeEnum.TopAbs_FACE, owners)
    edges = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_ShapeEnum.TopAbs_EDGE, edges)
    return sum(1 for i in range(1, edges.Extent() + 1)
               if not owners.Contains(edges.FindKey(i))
               or owners.FindFromKey(edges.FindKey(i)).Extent() == 0)


def exporter_source() -> str:
    """The SKILL exporter as one text: its ten parts under skill/, in load
    order (round 76, D6; the pads since round 85). The suites that read the
    source for a rule read this, so the split moved no assertion."""
    parts = ("s3d_util", "s3d_json", "s3d_props", "s3d_variants", "s3d_geometry",
             "s3d_stackup", "s3d_bends", "s3d_silk", "s3d_pads", "s3d_export")
    return "\n".join((ROOT / "skill" / f"{p}.il").read_text(encoding="utf-8", errors="replace")
                     for p in parts)


def entity_count(path) -> int:
    """How many `#n = ...` entities the STEP file carries - a property of the
    writer, not of the geometry, which is why it is pinned separately."""
    n = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("#") and "=" in line and line[1:].split("=", 1)[0].strip().isdigit():
                n += 1
    return n
