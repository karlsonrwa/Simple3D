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

"""StepFileIndex as an ordered search path."""
import sys, shutil
ROOT = _ROOT
sys.path.insert(0, str(ROOT))
from stepbuilder.core import StepFileIndex, StepBuilderError

T = _OUT / "idx"
shutil.rmtree(T, ignore_errors=True)
lib, proj, nested = T/"lib", T/"proj", T/"lib"/"sub"
for d in (lib, proj, nested): d.mkdir(parents=True)
(lib/"shared.step").write_text("LIB")        # same name in both
(proj/"shared.step").write_text("PROJ")
(lib/"only_lib.step").write_text("L")
(proj/"only_proj.step").write_text("P")
(nested/"deep.step").write_text("D")         # recursive within a root

fails=[]
def check(n,c,d=""):
    print(f"  {'PASS' if c else 'FAIL'}  {n}{'' if c else '  <- '+d}"); c or fails.append(n)

print("\n[1] precedence follows list order")
logs=[]
i = StepFileIndex([proj, lib], log=logs.append)
check("proj wins when listed first", i.find("shared.step").read_text()=="PROJ")
i2 = StepFileIndex([lib, proj], log=lambda m: None)
check("lib wins when listed first", i2.find("shared.step").read_text()=="LIB")

print("\n[2] union and recursion")
check("finds file only in lib", i.find("only_lib.step") is not None)
check("finds file only in proj", i.find("only_proj.step") is not None)
check("recurses into subfolders", i.find("deep.step") is not None)
check("unknown name -> None", i.find("nope.step") is None)

print("\n[3] the shadowed name is reported with the winner")
rep=[m for m in logs if "shared.step" in m]
check("one report line", len(rep)==1, str(logs))
check("names the winning path", rep and "proj" in rep[0].lower(), str(rep))

print("\n[4] a missing folder warns but does not stop the build")
logs2=[]
i3 = StepFileIndex([proj, T/"does_not_exist", lib], log=logs2.append)
check("still indexes the good roots", i3.find("only_lib.step") is not None)
check("warns about the missing one",
      any(m.startswith("warning:") and "does_not_exist" in m for m in logs2), str(logs2))
check("roots list holds only real ones", len(i3.roots)==2, str(i3.roots))

print("\n[5] fatal only when nothing usable")
try:
    StepFileIndex([T/"nope1", T/"nope2"], log=lambda m: None); check("all-missing raises", False)
except StepBuilderError as e:
    check("all-missing raises", True); check("message lists them", "nope1" in str(e))
try:
    StepFileIndex([], log=lambda m: None); check("empty list raises", False)
except StepBuilderError: check("empty list raises", True)
try:
    StepFileIndex(["", "   "], log=lambda m: None); check("blank entries raise", False)
except StepBuilderError: check("blank entries raise", True)

print("\n[6] backward compatible with a single path")
check("plain str root", StepFileIndex(str(lib), log=lambda m: None).find("only_lib.step") is not None)
check("plain Path root", StepFileIndex(lib, log=lambda m: None).find("only_lib.step") is not None)

print("\n[7] a name carrying a path component still resolves")
check("subdir/deep.step found", i.find("sub/deep.step") is not None)

print("\n[8] case: the mapping table and the disk may disagree")
# The name looked up comes from Allegro's STEP mapping table, typed by hand;
# the file on disk is whatever the library vendor named it. On Windows the two
# cannot be told apart by the filesystem, so a miss on case alone was a model
# silently absent from the assembly.
(lib/"MiXeD.STEP").write_text("M")
logs3 = []
i4 = StepFileIndex([lib], log=logs3.append)
check("exact name still found", i4.find("MiXeD.STEP") is not None)
check("lower-cased extension found", i4.find("MiXeD.step") is not None)
check("whole name in another case found", i4.find("mixed.step") is not None)
check("upper-cased name found", i4.find("MIXED.STEP") is not None)
check("it is the same file", i4.find("mixed.step").read_text() == "M")
check("and it says so", any("differ only in case" in m for m in logs3), str(logs3))
check("a name that differs by more than case is still a miss",
      i4.find("mixxed.step") is None)

# Exact wins over folded, so nothing that resolved before resolves differently.
(proj/"Case.step").write_text("EXACT")
(lib/"CASE.STEP").write_text("FOLDED")
i5 = StepFileIndex([proj, lib], log=lambda m: None)
check("an exact match beats a case-folded one",
      i5.find("Case.step").read_text() == "EXACT")
check("and the folded one is still reachable by its own name",
      i5.find("CASE.STEP").read_text() == "FOLDED")

logs4 = []
i6 = StepFileIndex([lib], log=logs4.append)
for _ in range(14):                                  # a whole library, misspelled
    i6.find("mixed.step")
check("the case report is capped, not one line per component",
      len([m for m in logs4 if "differ only in case" in m]) == 10, str(len(logs4)))
check("and it says there were more",
      any("further model names" in m for m in logs4), str(logs4))

print("\n[9] a model file that is present but unusable costs its own component")
# It used to raise, so ONE file locked by another application, one zero-byte
# copy or one dialect OCCT declines took the whole board down - while the same
# model simply being absent cost only that component. Same treatment now, and
# the two are still reported apart: the fixes are different, and the
# "it is inside the board, not on your disk" advice is wrong for a file that
# is right there.
import json
from stepbuilder import core

W = _OUT / "unreadable"
shutil.rmtree(W, ignore_errors=True)
(W / "models").mkdir(parents=True)
shutil.copy(ROOT / "demo/step_files/cap_D8x10mm.stp", W / "models")
(W / "models" / "broken.step").write_text("this is not a STEP file at all\n")

demo = json.load(open(ROOT / "demo/ap-214/demo.json"))
board = {"name": demo["name"], "pcb": demo["pcb"]}
board["C1"] = json.loads(json.dumps(demo["C1"]))              # a good model
bad = json.loads(json.dumps(demo["C1"]))                      # the broken one
bad["step_mapping"]["step_name"] = "broken.step"
board["C2"] = bad
jf = W / "board.json"
jf.write_text(json.dumps(board, indent=1))

logs = []
res = core.generate(step_dir=W / "models", json_file=jf, output_dir=W,
                    output_name="unreadable_test", log=logs.append)
check("the board is still built", (W / "unreadable_test.step").exists())
check("the good component is placed", res.components_placed == 1,
      str(res.components_placed))
check("the bad one is skipped, not fatal", res.components_skipped == ["C2"],
      str(res.components_skipped))
check("it is reported as unreadable", res.unreadable_step_files == ["broken.step"],
      str(res.unreadable_step_files))
check("and NOT as missing - the file is on disk", res.missing_step_files == [],
      str(res.missing_step_files))
check("the log names the file and the reason",
      any("broken.step" in m and m.startswith("warning:") for m in logs),
      str([m for m in logs if "broken" in m]))

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
