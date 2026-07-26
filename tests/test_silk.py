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

"""Silkscreen path as a real package import (exercises `from .colors import`),
plus layer filtering, flat mode, warnings and the area cross-check."""
import json, math, sys
from pathlib import Path

ROOT = _ROOT
sys.path.insert(0, str(ROOT))
from stepbuilder import core           # package import, not a bare module

OUT = Path(__file__).parent
fails = []
def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + detail}")
    if not cond: fails.append(name)

base = json.loads((ROOT / "demo/ap-214/demo.json").read_text())

def square(x, y, s, layer):
    """CCW square, area s*s, tagged with a layer."""
    return {"vertices": [[x, y, 0.0], [x + s, y, 0.0], [x + s, y + s, 0.0], [x, y + s, 0.0]],
            "area": s * s, "layer": layer}

def ring(x, y, outer, inner, layer):
    o = outer / 2.0; i = inner / 2.0
    return {"vertices": [[x-o, y-o, 0], [x+o, y-o, 0], [x+o, y+o, 0], [x-o, y+o, 0]],
            "holes": [[[x-i, y-i, 0], [x+i, y-i, 0], [x+i, y+i, 0], [x-i, y+i, 0]]],
            "area": outer*outer - inner*inner, "layer": layer}

def build(name, **kw):
    d = json.loads(json.dumps(base))
    d["format"] = "simple3d"; d["format_version"] = 3
    d["silkscreen"] = {
        "thickness": 0.025,
        "top": [square(20, 20, 4, "REF DES/SILKSCREEN_TOP"),
                ring(40, 30, 6, 3, "BOARD GEOMETRY/SILKSCREEN_TOP"),
                square(60, 20, 2, "COMPONENT VALUE/SILKSCREEN_TOP")],
        "bottom": [square(30, 40, 3, "REF DES/SILKSCREEN_BOTTOM")],
        "warnings": ["zero width: text on REF DES/SILKSCREEN_TOP at (1.0, 2.0) - skipped"],
    }
    jf = OUT / f"{name}.json"; jf.write_text(json.dumps(d))
    logs = []
    res = core.generate(step_dir=ROOT/"demo/step_files", json_file=jf,
                        output_dir=OUT, output_name=name,
                        log=lambda m: logs.append(m), **kw)
    return res, logs

print("\n[1] silkscreen builds (package import reaches `from .colors import`)")
res, logs = build("silk_solid")
check("4 solids built", res.silkscreen_solids == 4, str(res.silkscreen_solids))
check("none skipped", res.silkscreen_skipped == 0, str(res.silkscreen_skipped))
txt = (OUT/"silk_solid.step").read_text(errors="replace")
check("silkscreen_top part present", "silkscreen_top" in txt)
check("silkscreen_bot part present", "silkscreen_bot" in txt)

print("\n[2] Allegro's declared areas are reproduced (arc/convention check quiet)")
area_warn = [m for m in logs if "differ from the area" in m]
check("no area disagreement", not area_warn, str(area_warn))
match = [m for m in logs if "match Allegro's areas" in m]
check("area agreement reported for both sides", len(match) == 2, str(match))

print("\n[3] warnings from the JSON reach the log with a colouring prefix")
warn = [m for m in logs if m.startswith("warning:") and "zero width" in m]
check("zero-width warning re-logged with prefix", len(warn) == 1, str(warn))

print("\n[4] layer exclusion")
res2, logs2 = build("silk_filtered",
                    silk_layers_off={"REF DES/SILKSCREEN_TOP", "REF DES/SILKSCREEN_BOTTOM"})
check("2 of 4 polygons left out", res2.silkscreen_solids == 2, str(res2.silkscreen_solids))
dropped = [m for m in logs2 if "left out by layer" in m]
check("both sides report the drop", len(dropped) == 2, str(dropped))

print("\n[5] a layer name that matches nothing changes nothing")
res3, _ = build("silk_nomatch", silk_layers_off={"NO SUCH LAYER"})
check("still 4 solids", res3.silkscreen_solids == 4, str(res3.silkscreen_solids))

print("\n[6] silkscreen switched off")
res4, logs4 = build("silk_off", silk_top=False, silk_bottom=False)
check("0 solids", res4.silkscreen_solids == 0, str(res4.silkscreen_solids))
check("warnings still logged when legend is off",
      any("zero width" in m for m in logs4), "warning lost")

print("\n[7] flat mode: faces unioned, file smaller")
res5, logs5 = build("silk_flat", silk_flat=True)
check("flat built 4", res5.silkscreen_solids == 4, str(res5.silkscreen_solids))
solid_sz = (OUT/"silk_solid.step").stat().st_size
flat_sz = (OUT/"silk_flat.step").stat().st_size
check(f"flat smaller than solid ({flat_sz} < {solid_sz})", flat_sz < solid_sz)
check("no merge failure warning",
      not [m for m in logs5 if "could not merge" in m], str(logs5[-3:]))

print("\n[8] one bad polygon is skipped, not fatal")
d = json.loads(json.dumps(base))
d["format"] = "simple3d"; d["format_version"] = 3
d["silkscreen"] = {"thickness": 0.025,
                   "top": [square(20, 20, 4, "L1"), {"vertices": [[0, 0, 0]], "area": 1.0, "layer": "L1"}],
                   "bottom": []}
jf = OUT/"silk_bad.json"; jf.write_text(json.dumps(d))
logs6 = []
res6 = core.generate(step_dir=ROOT/"demo/step_files", json_file=jf, output_dir=OUT,
                     output_name="silk_bad", log=lambda m: logs6.append(m))
check("good polygon still built", res6.silkscreen_solids == 1, str(res6.silkscreen_solids))
check("bad one counted as skipped", res6.silkscreen_skipped == 1, str(res6.silkscreen_skipped))
check("skip reported as a warning",
      any(m.startswith("warning:") and "skipped" in m for m in logs6), str(logs6[-2:]))

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
