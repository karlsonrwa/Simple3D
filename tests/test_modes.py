# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, out_dir, fails, check, rect, read_step, count_solids

"""The three board modes, on the real STIFFENER2 / FLEX stackups."""
import json, sys
from stepbuilder import core
from stepbuilder.colors import layer_kind

OUT = out_dir("modes")


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
    n = count_solids(read_step(path))
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

# These names are typed by a person into the cross-section editor and Allegro
# does not police them. Cadence's own demo board spells it STIFFNER, without the
# second E, and its epoxy layer EXPOXY; both fell through to "other" and came
# out as undifferentiated grey - 51 faces of it - which is exactly what a
# layer-colored board exists to prevent.
for name, want_kind in (("STIFFNER_INNER1", "stiffener"),
                        ("STIFNER_TOP", "stiffener"),
                        ("EXPOXY_INNER1", "adhesive"),
                        ("EPOXY_TOP", "adhesive")):
    got = layer_kind({"name": name, "type": "MASK", "function": None})
    check(f"{name} -> {want_kind}", got == want_kind, got)
# ...and an epoxy layer that DOES declare its function is caught by that first,
# which is how this board's actually reads.
check("layerFunction still wins where it is set",
      layer_kind({"name": "EXPOXY_INNER1", "type": "MASK",
                  "function": "ADHESIVE"}) == "adhesive")

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

print("\n[6] the progress bar never goes backwards, and the stages answer alone")
# Round 73 (plan A9): generate is a sequence of stages now. The phase values
# it reports were asserted nowhere before the split; and each stage has to
# be callable on its own, which is what the split was for.
from stepbuilder.build import BuildOptions
from stepbuilder.core import _prepare_stackups, _plan_fold
seen = []
core.generate(step_dir=ROOT / "demo/step_files", json_file=ROOT / "tests/fixtures/rigidflex.json",
              output_dir=OUT, output_name="phases", progress=lambda v, t, label="": seen.append((v, t, label)),
              log=lambda m: None)
values = [v for v, _, _ in seen]
check("progress is reported", len(values) >= 5, str(len(values)))
check("never backwards", values == sorted(values), str(values))
check("out of 100, and ends at 100", all(t == 100 for _, t, _ in seen) and values[-1] == 100, str(seen[-1]))
check("every phase carries a label", all(label for _, _, label in seen), str([s for s in seen if not s[2]]))
rf = json.loads((ROOT / "tests/fixtures/rigidflex.json").read_text(encoding="utf-8"))
stack = _prepare_stackups(rf, BuildOptions(), lambda m: None)
check("the stackup stage alone: two zones with their faces",
      stack.zones and len(stack.levels) == 2 and stack.board_top_z > stack.board_bottom_z, str(stack))
plan = _plan_fold(rf, stack, BuildOptions(), lambda m: None)
check("the fold stage alone: one bend planned", plan is not None and len(plan.bends) == 1, str(plan and plan.bends))
flat = _plan_fold(rf, stack, BuildOptions(fold_bends=False), lambda m: None)
check("and none when folding is off", flat is None)

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
