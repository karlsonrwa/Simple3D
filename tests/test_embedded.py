# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, out_dir, fails, check

"""Embedded-vs-disk cross-check."""
import json, sys
from stepbuilder import core

OUT = out_dir("emb")

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

print("\n[7] format_version 9 keeps the components under one key; v8 beside the metadata")
# Round 79, plan E1. The same demo board as two fixtures: tests/fixtures/
# demo_v8.json (components at the top level, the shape every release wrote)
# and demo_v9.json (a "components" object). Both must read to the same
# placements and build to the same STEP.
from stepbuilder.intermediate import RESERVED, Intermediate
v8 = Intermediate.read(ROOT / "tests/fixtures/demo_v8.json")
v9 = Intermediate.read(ROOT / "tests/fixtures/demo_v9.json")
check("the v9 fixture has no component beside the metadata",
      all(k in RESERVED for k in v9.data) and "components" in v9.data, str(list(v9.data)))
check("the two read to the same components", v8.components == v9.components and v9.components,
      str(list(v9.components)))
check("\"components\" is reserved, so a v9 file is never walked as if it were a refdes",
      "components" not in v8.components and "components" in RESERVED)
res8, logs8 = [], []
for tag, fx in (("v8", "demo_v8.json"), ("v9", "demo_v9.json")):
    r = core.generate(step_dir=ROOT / "demo/step_files", json_file=ROOT / "tests/fixtures" / fx,
                      output_dir=OUT, output_name=f"shape_{tag}", log=logs8.append)
    res8.append(r)
check("both shapes place the same components",
      res8[0].components_placed == res8[1].components_placed == 1, str([r.components_placed for r in res8]))
from _support import read_step, volume, entity_count
s8, s9 = OUT / "shape_v8.step", OUT / "shape_v9.step"
check("and the same STEP", abs(volume(read_step(s8)) - volume(read_step(s9))) < 1e-9
      and entity_count(s8) == entity_count(s9))

print("\n[8] one absent model file is counted once, however many refdes use it")

# ModelCache.labels_for reports a problem the FIRST time a name fails and None
# on every later ask, so a caller counts each FILE once rather than once per
# refdes. Dropping that line left every suite green (measured 2026-09-22):
# every board here reaches a missing model from exactly one component, which is
# the case where the two behave alike.
d = json.loads(json.dumps(base))
d["format"] = "simple3d"; d["format_version"] = 4
d["embedded_models"] = ["MISSING_PART.step"]
for ref in ("U1", "U2", "U3"):
    d[ref] = {"step_mapping": {"step_name": "MISSING_PART.step",
                               "rotation_x": 0.0, "rotation_y": 0.0, "rotation_z": 0.0,
                               "offset_x": 0.0, "offset_y": 0.0, "offset_z": 0.0},
              "is_mirrored": False, "x": 10.0, "y": 10.0, "angle": 0.0}
jf8 = OUT / "case8.json"; jf8.write_text(json.dumps(d))
logs8 = []
res8 = core.generate(step_dir=ROOT / "demo/step_files", json_file=jf8, output_dir=OUT,
                     output_name="case8", log=logs8.append)
check("three refdes on one absent model: the FILE is listed once",
      res8.missing_step_files == ["MISSING_PART.step"], str(res8.missing_step_files))
check("and warned about once, not once per refdes",
      len([m for m in logs8 if "could not find MISSING_PART.step" in m]) == 1,
      [m for m in logs8 if "could not find" in m])
check("while all three components are still skipped",
      sorted(res8.components_skipped) == ["U1", "U2", "U3"], str(res8.components_skipped))
check("the embedded-model name is not repeated either",
      res8.embedded_not_on_disk == ["MISSING_PART.step"], str(res8.embedded_not_on_disk))
check("and the good component is still placed", res8.components_placed == 1,
      str(res8.components_placed))

print("\n[9] the components a model is missing for are named, in every log (round 122)")
# Review 23.10.2026, R3-3: the log named the FILE ("could not find
# NOT_THERE.step") and the summaries counted files, and the refdes went into
# components_skipped only - measured on the 4090 (round 122): U9 and R77 on a
# model no folder holds, C2 and C3 on one that is on disk and unusable, R1-R15
# on one shared missing model: 19 left out, none named by generate(), the CLI
# or the window, whose last line said "Done: 1 file(s), 1 component(s) placed".
import contextlib, dataclasses, io, re, shutil
from stepbuilder import __main__ as stepbuilder_cli
from stepbuilder.build import BuildOptions
from stepbuilder.worker import BuildSettings, run_jobs

W9 = OUT / "left_out"
shutil.rmtree(W9, ignore_errors=True)
(W9 / "models").mkdir(parents=True)
shutil.copy(ROOT / "demo/step_files/cap_D8x10mm.stp", W9 / "models")
(W9 / "models" / "broken.step").write_text("this is not a STEP file at all\n")


def on(step_name, x):
    part = json.loads(json.dumps(base["C1"]))
    part["step_mapping"]["step_name"] = step_name
    part["x"] = x
    return part


board = json.loads(json.dumps(base))
board["U9"], board["R77"] = on("NOT_THERE.step", 20.0), on("NOT_THERE.step", 25.0)
board["C3"], board["C2"] = on("broken.step", 30.0), on("broken.step", 35.0)
# 25 on one shared model, listed out of order: R10 is the JSON's first
SHARED = [f"R{i}" for i in (10, 2, 25, 1, 11, 3, 4, 5, 6, 7, 8, 9, 12, 13, 14, 15, 16,
                            17, 18, 19, 20, 21, 22, 23, 24)]
for i, ref in enumerate(SHARED):
    board[ref] = on("SHARED_MISSING.step", 40.0 + i)
jf9 = W9 / "board.json"
jf9.write_text(json.dumps(board), encoding="utf-8")

WANT = {
    "NOT_THERE.step": "warning: NOT_THERE.step not found - 2 component(s) left out: R77, U9",
    "broken.step": "warning: broken.step could not be used - 2 component(s) left out: C2, C3",
    "SHARED_MISSING.step": ("warning: SHARED_MISSING.step not found - 25 component(s) left out: "
                            + ", ".join(f"R{i}" for i in range(1, 21)) + " and 5 more"),
}


def said(lines, model):
    return [l for l in lines if l.startswith(f"warning: {model} ") and "left out" in l]


log9 = []
res9 = core.generate(step_dir=W9 / "models", json_file=jf9, output_dir=W9, output_name="gen",
                     log=log9.append)
check("29 components left out, 1 placed", len(res9.components_skipped) == 29
      and res9.components_placed == 1, (len(res9.components_skipped), res9.components_placed))
for model, line in WANT.items():
    check(f"generate()'s log names what {model} leaves out, once, in refdes order"
          f"{' - the first 20, then a count' if 'SHARED' in model else ''}",
          said(log9, model) == [line], said(log9, model) or log9[-6:])

out9, err9 = io.StringIO(), io.StringIO()
with contextlib.redirect_stdout(out9), contextlib.redirect_stderr(err9):
    rc9 = stepbuilder_cli.main([str(W9 / "models"), str(jf9), str(W9 / "cli")])
cli9 = (out9.getvalue() + err9.getvalue()).splitlines()
check("the CLI says the same three lines",
      rc9 == 0 and all(said(cli9, m) == [l] for m, l in WANT.items()), [l for l in cli9 if "left out" in l])
check("and counts what is left out in its summary",
      "warning: 29 component(s) left out of the model (named above)" in cli9,
      [l for l in cli9 if "warning: " in l and "(" in l][-4:])

defaults = BuildOptions()
names = {f.name for f in dataclasses.fields(BuildSettings)}
values = {n: getattr(defaults, n) for n in names if hasattr(defaults, n)}
values.update(step_dirs=(str(W9 / "models"),), json_file=str(jf9), output_dir=str(W9 / "window"),
              minimize=defaults.minimize_size, brd_name=None, dated_name=False, build_full_board=True)
(W9 / "window").mkdir()


class Channel:
    def __init__(self):
        self.items = []

    def put(self, item):
        self.items.append(item)


ch9 = Channel()
run_jobs(BuildSettings(**values), ch9)
win9 = [text for kind, text in ch9.items if kind == "log"]
done9 = [text for kind, text in ch9.items if kind == "done"]
check("the window's log says them too", all(said(win9, m) == [l] for m, l in WANT.items()),
      [l for l in win9 if "left out" in l])
check("and counts them per file and in its last line",
      "warning: demo.step: 29 component(s) left out (named above)" in win9
      and done9 == ["Done: 1 file(s), 1 component(s) placed, 29 left out"], (done9, win9[-4:]))

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
