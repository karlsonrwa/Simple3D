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

"""The three board modes, on the real STIFFENER2 / FLEX stackups."""
import json, sys
from pathlib import Path
ROOT = _ROOT; sys.path.insert(0, str(ROOT))
from stepbuilder import core
from stepbuilder.colors import layer_kind, DEFAULT_LAYER_COLORS, LAYER_KINDS

OUT = _OUT / "modes"; OUT.mkdir(exist_ok=True)
fails = []
def check(n, c, d=""):
    print(f"  {'PASS' if c else 'FAIL'}  {n}{'' if c else '  <- ' + d}")
    if not c: fails.append(n)

def rect(a, b, c, d):
    return [{"type": "segment", "start": [a, b], "end": [c, b]},
            {"type": "segment", "start": [c, b], "end": [c, d]},
            {"type": "segment", "start": [c, d], "end": [a, d]},
            {"type": "segment", "start": [a, d], "end": [a, b]}]

S2 = [("STIFFENER_TOP2", "MASK", 2.0), ("ADHESIVE_TOP2", "MASK", 0.025),
      ("COVERLAY_TOP", "MASK", 0.025), ("ADHESIVE_TOP", "MASK", 0.05),
      ("SOLDERMASK_TOP", "MASK", 0.025), ("TOP", "CONDUCTOR", 0.045),
      ("DIEL", "DIELECTRIC", 0.125), ("BOTTOM", "CONDUCTOR", 0.045),
      ("SOLDERMASK_BOTTOM", "MASK", 0.025), ("ADHESIVE_BOTTOM", "MASK", 0.05),
      ("COVERLAY_BOTTOM", "MASK", 0.025)]
FLEX = S2[2:4] + S2[5:8] + S2[9:]

def mk(spec):
    return core.restack([{"name": n, "type": t, "thickness": k, "z_top": 0,
                          "z_bottom": 0, "negative": False, "function": None,
                          "shapes": None} for n, t, k in spec])

base = json.loads((ROOT / "demo/ap-214/demo.json").read_text())
def build(name, mode, colors=None):
    d = {"format": "simple3d", "format_version": 6, "name": name,
         "pcb": {"thickness": {"soldermask_top": 0.0, "board": 2.44,
                               "soldermask_bottom": 0.0},
                 "color": base["pcb"]["color"], "edges": [rect(0, 0, 30, 20)]},
         "stackups": {"S2": {"thickness": 2.44, "layers": mk(S2)},
                      "FLEX": {"thickness": 0.365, "layers": mk(FLEX)}},
         "zones": [{"name": "ZA", "stackup": "S2", "contour": rect(0, 0, 16, 11)},
                   {"name": "ZB", "stackup": "FLEX", "contour": rect(0, 11, 30, 20)}]}
    jf = OUT / f"{name}.json"; jf.write_text(json.dumps(d))
    logs = []
    core.generate(step_dir=ROOT / "demo/step_files", json_file=jf, output_dir=OUT,
                  output_name=name, board_mode=mode, layer_colors=colors,
                  log=logs.append)
    return logs, (OUT / f"{name}.step")

def inspect(path):
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorTool
    from OCP.TDF import TDF_LabelSequence
    from OCP.Quantity import Quantity_Color
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.STEPControl import STEPControl_Reader
    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("d"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)
    rd = STEPCAFControl_Reader(); rd.SetColorMode(True); rd.SetNameMode(True)
    rd.ReadFile(str(path)); rd.Transfer(doc)
    ct = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    seq = TDF_LabelSequence(); ct.GetColors(seq)
    cols = set()
    for i in range(1, seq.Length() + 1):
        c = Quantity_Color()
        if XCAFDoc_ColorTool.GetColor_s(seq.Value(i), c):
            cols.add((round(c.Red(), 3), round(c.Green(), 3), round(c.Blue(), 3)))
    r = STEPControl_Reader(); r.ReadFile(str(path)); r.TransferRoots()
    e = TopExp_Explorer(r.OneShape(), TopAbs_SOLID); n = 0
    while e.More(): n += 1; e.Next()
    return n, cols, path.stat().st_size

print("\n[1] layer_kind classifies the real stackup")
want = {"STIFFENER_TOP2": "stiffener", "ADHESIVE_TOP2": "adhesive",
        "COVERLAY_TOP": "coverlay", "SOLDERMASK_TOP": "soldermask",
        "TOP": "copper", "DIEL": "base"}
for n, t, _ in S2:
    if n in want:
        got = layer_kind({"name": n, "type": t, "function": None})
        check(f"{n} -> {want[n]}", got == want[n], got)
check("an unknown layer -> other",
      layer_kind({"name": "WHATEVER", "type": "MASK", "function": None}) == "other")

print("\n[2] the three modes")
res = {}
for mode in ("solid", "layers", "inspect"):
    logs, path = build(f"m_{mode}", mode)
    solids, cols, size = inspect(path)
    res[mode] = (solids, cols, size)
    print(f"     {mode:8} {solids:3} solid(s)  {len(cols):3} colour(s)  {size:9,} bytes")
check("solid: one solid", res["solid"][0] == 1, str(res["solid"][0]))
check("layers: still ONE solid", res["layers"][0] == 1, str(res["layers"][0]))
check("inspect: many parts", res["inspect"][0] > 10, str(res["inspect"][0]))
check("layers has more colours than solid",
      len(res["layers"][1]) > len(res["solid"][1]),
      f"{len(res['layers'][1])} vs {len(res['solid'][1])}")
check("layers >= 5 distinct colours", len(res["layers"][1]) >= 5, str(len(res["layers"][1])))
check("layers is bigger than solid", res["layers"][2] > res["solid"][2])
check("layers is smaller than inspect", res["layers"][2] < res["inspect"][2],
      f"{res['layers'][2]} vs {res['inspect'][2]}")

print("\n[3] the chosen colours are the ones written")
custom = {"copper": (255, 0, 0), "stiffener": (0, 255, 0), "base": (0, 0, 255)}
logs, path = build("m_custom", "layers", custom)
_, cols, _ = inspect(path)
for kind, rgb in custom.items():
    target = (round(rgb[0] / 255, 3), round(rgb[1] / 255, 3), round(rgb[2] / 255, 3))
    check(f"{kind} {rgb} present", any(
        all(abs(a - b) < 0.02 for a, b in zip(c, target)) for c in cols), str(target))
check("log names the kinds", any("copper" in m for m in logs), str(logs[-4:]))

print("\n[4] a plain board ignores the mode entirely")
d2 = {"format": "simple3d", "format_version": 6, "name": "plain",
      "pcb": {"thickness": {"soldermask_top": 0.03, "board": 1.036,
                            "soldermask_bottom": 0.03},
              "color": base["pcb"]["color"], "edges": [rect(0, 0, 10, 10)]}}
f2 = OUT / "plain.json"; f2.write_text(json.dumps(d2))
for mode in ("solid", "layers", "inspect"):
    lg = []
    core.generate(step_dir=ROOT / "demo/step_files", json_file=f2, output_dir=OUT,
                  output_name=f"p_{mode}", board_mode=mode, log=lg.append)
    n, _, _ = inspect(OUT / f"p_{mode}.step")
    check(f"plain board, mode {mode}: one solid", n == 1, str(n))

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
