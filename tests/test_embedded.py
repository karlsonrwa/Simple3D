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

"""Embedded-vs-disk cross-check."""
import json, sys
from pathlib import Path
ROOT = _ROOT
sys.path.insert(0, str(ROOT))
from stepbuilder import core

OUT = _OUT / "emb"; OUT.mkdir(exist_ok=True)
fails=[]
def check(n,c,d=""):
    print(f"  {'PASS' if c else 'FAIL'}  {n}{'' if c else '  <- '+d}"); c or fails.append(n)

base = json.loads((ROOT/"demo/ap-214/demo.json").read_text())

def run(name, embedded=None, extra_component=None, fmt=4):
    d = json.loads(json.dumps(base))
    d["format"]="simple3d"; d["format_version"]=fmt
    if embedded is not None: d["embedded_models"]=embedded
    if extra_component:
        d["U9"] = {"step_mapping": {"step_name": extra_component,
                   "rotation_x":0.0,"rotation_y":0.0,"rotation_z":0.0,
                   "offset_x":0.0,"offset_y":0.0,"offset_z":0.0},
                   "is_mirrored": False, "x":10.0,"y":10.0,"angle":0.0}
    jf = OUT/f"{name}.json"; jf.write_text(json.dumps(d))
    logs=[]
    res = core.generate(step_dir=ROOT/"demo/step_files", json_file=jf,
                        output_dir=OUT, output_name=name, log=logs.append)
    return res, logs

print("\n[1] model missing from disk AND embedded -> named, with guidance")
res, logs = run("case1", embedded=["MISSING_PART.step"], extra_component="MISSING_PART.step")
check("recorded on the result", res.embedded_not_on_disk == ["MISSING_PART.step"],
      str(res.embedded_not_on_disk))
named = [m for m in logs if "MISSING_PART.step" in m and m.startswith("warning:")]
check("named in a warning line", named, str(logs[-3:]))
guide = [m for m in logs if "3DX canvas" in m]
check("guidance line present", guide)
check("guidance is a warning (coloured)", guide and guide[0].startswith("warning:"))

print("\n[2] missing but NOT embedded -> no extra noise")
res2, logs2 = run("case2", embedded=["SOMETHING_ELSE.step"], extra_component="MISSING_PART.step")
check("nothing recorded", res2.embedded_not_on_disk == [], str(res2.embedded_not_on_disk))
check("no 3DX guidance", not [m for m in logs2 if "3DX canvas" in m])
check("plain missing warning still there",
      any("could not find MISSING_PART.step" in m for m in logs2), str(logs2[-3:]))

print("\n[3] embedded but present on disk -> silent")
res3, logs3 = run("case3", embedded=["cap_D8x10mm.stp"])
check("nothing recorded", res3.embedded_not_on_disk == [])
check("silent", not [m for m in logs3 if "3DX canvas" in m])

print("\n[4] older JSON without the key -> silent, no crash")
res4, logs4 = run("case4", embedded=None, extra_component="MISSING_PART.step", fmt=3)
check("nothing recorded", res4.embedded_not_on_disk == [])
check("no guidance", not [m for m in logs4 if "3DX canvas" in m])
check("plain warning still emitted",
      any("could not find" in m for m in logs4))

print("\n[5] empty list, and a path component in the mapping")
res5, _ = run("case5", embedded=[])
check("empty list is silent", res5.embedded_not_on_disk == [])
res6, logs6 = run("case6", embedded=["sub/MISSING_PART.step"], extra_component="MISSING_PART.step")
check("matches on the bare filename", res6.embedded_not_on_disk == ["sub/MISSING_PART.step"],
      str(res6.embedded_not_on_disk))

print("\n[6] embedded_models is not walked as a component")
res7, logs7 = run("case7", embedded=["A.step","B.step"])
check("no component named embedded_models",
      not [m for m in logs7 if "embedded_models" in m], str(logs7[:4]))
check("component count unchanged", res7.components_placed == 1, str(res7.components_placed))

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
