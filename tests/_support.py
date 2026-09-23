"""What every test script shares: where the repository is, where a test may
write, the one check() that decides the exit code, the one way a STEP file is
measured, and the one turn at the session's clipboard (SessionTurn, round 94).

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
