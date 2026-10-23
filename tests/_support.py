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


def put_clipboard_text(text) -> str:
    """Put `text` on the Windows clipboard as real data - or empty it, for
    None. Returns "" once done, or why it could not be.

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
    for a moment (DefenderSessionHelper does, on the 4090), hence the retry.
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
    for _ in range(100):
        if u32.OpenClipboard(None):
            break
        time.sleep(0.02)
    else:
        return f"OpenClipboard failed for 2 s (error {ctypes.GetLastError()})"
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
for _ in range(100):
    if u.OpenClipboard(None):
        break
    time.sleep(0.02)
else:
    sys.exit(3)
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

    Returns ("put", ""), ("left", why) or ("failed", why)."""
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


def clipboard_text_elsewhere(seconds: float = 10.0) -> tuple:
    """What ANOTHER process reads from the clipboard while this one waits for
    it and pumps no messages: (text, "") - text None when there is none - or
    (None, why) when it could not.

    Text this process only promised (Tk's clipboard_append) cannot be read
    this way: the reader waits for this process's event loop, which is
    blocked right here, until Windows gives up after 30 s - so `seconds`
    under 30 makes the promise a failure instead of a long wait (round 96)."""
    if sys.platform != "win32":
        return None, "not Windows"
    import json
    import subprocess

    try:
        done = subprocess.run([sys.executable, "-c", _CLIP_PROBE], capture_output=True,
                              timeout=seconds)
    except subprocess.TimeoutExpired:
        return None, f"another process could not read the clipboard within {seconds:.0f} s"
    if done.returncode == 3:
        return None, "another process could not open the clipboard for 2 s"
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
