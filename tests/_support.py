"""What every test script shares: where the repository is, where a test may
write, the one check() that decides the exit code, and the one way a STEP
file is measured.

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
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, True)
    return box.Get()


def count_solids(shape) -> int:
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    n = 0
    while exp.More():
        n += 1
        exp.Next()
    return n


def entity_count(path) -> int:
    """How many `#n = ...` entities the STEP file carries - a property of the
    writer, not of the geometry, which is why it is pinned separately."""
    n = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("#") and "=" in line and line[1:].split("=", 1)[0].strip().isdigit():
                n += 1
    return n
