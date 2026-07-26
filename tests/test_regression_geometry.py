# Paths are derived from this file's own location, so the suite runs from
# wherever the repository is checked out. Anything a test writes goes to
# build/test-output/, which is gitignored.
import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parent.parent
_OUT = _ROOT / "build" / "test-output"
_OUT.mkdir(parents=True, exist_ok=True)
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

"""Baseline comparison with masks zeroed, which is how 12073.309477 was measured."""
import sys, json
from pathlib import Path
ROOT = _ROOT
sys.path.insert(0, str(ROOT))
# The PACKAGE import: core.py imports its siblings relatively inside the
# functions that need them, so a bare `import core` fails there and not at
# the top of the file.
from stepbuilder import core
out = _OUT / "regression"
out.mkdir(exist_ok=True)
d = json.load(open(ROOT/"demo/ap-214/demo.json"))
d["pcb"]["thickness"]["soldermask_top"] = 0.0
d["pcb"]["thickness"]["soldermask_bottom"] = 0.0
jf = out/"nomask.json"; jf.write_text(json.dumps(d))
core.generate(step_dir=ROOT/"demo/step_files", json_file=jf, output_dir=out,
              output_name="nomask", minimize_size=False, log=lambda m: None)
from OCP.STEPControl import STEPControl_Reader
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
r = STEPControl_Reader(); r.ReadFile(str(out/"nomask.step")); r.TransferRoots()
p = GProp_GProps(); BRepGProp.VolumeProperties_s(r.OneShape(), p)
v = p.Mass()
print(f"volume (masks zeroed) = {v:.6f}")
print("BASELINE 12073.309477 ->", "MATCH" if abs(v-12073.309477) < 1e-4 else f"DRIFT {v-12073.309477:+.6f}")
