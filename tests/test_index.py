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
from pathlib import Path
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

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
