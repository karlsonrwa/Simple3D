# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, out_dir, fails, check

"""The harness itself: how run_all judges a job, what the measuring helpers
of _support answer, the turn probe, the GUI suites' desktop, the name check,
the ignore rules (round 132, the review's batch 9). tools/mutate.py's own
rules are in test_mutations, beside the table they serve.

  [1] run_all judges what a job printed, not only its exit code (R7-1)
  [2] a job that does not end, or leaves a process behind (R7-2)
  [3] --quick and the heavy flags (R7-3)
  [4] bbox and volume measure what they say (R7-4, R7-5)
  [5] read_step names what it cannot read (R7-6)
  [6] the turn probe tells a refusal from a failure to ask (R7-7)
  [7] no desktop of their own, no GUI suite (R7-9)
  [8] the name check keeps every defect pyflakes finds (R7-15)
  [9] the ignore rules (R7-16)

Every stub is a script of its own under build/test-output/harness and every
probe of something that can crash runs in a process of its own: until round
132 a missing STEP file killed the suite reading it, and a hang hung run_all.
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import run_all
import _support

HERE = out_dir("harness")
shutil.rmtree(HERE, ignore_errors=True)
HERE.mkdir(parents=True)
PY = sys.executable


def stub(name: str, body: str) -> Path:
    path = HERE / name
    path.write_text(body, encoding="utf-8")
    return path


def judged(script: Path, kind="suite", heavy=True, limit=60.0, watch=False):
    code, seconds, out, err = run_all.run_job(script, limit, watch_imports=watch)
    return run_all.judge(kind, heavy, code, out, err, limit), code, seconds


print("[1] run_all judges what a job printed, not only its exit code (review 23.10.2026, R7-1)")
# Until round 132 the exit code alone decided: these three passed.
cases = {
    "prints FAIL and exits 0": ("stub_fail_exit0.py", "print('  FAIL  a rule  <- 1')\n", "printed FAIL"),
    "runs no check and exits 0": ("stub_no_checks.py", "print('hello')\n", "ran no check"),
    "FAILs, then sys.exit(None)": ("stub_exit_none.py",
                                   "import sys\nprint('  FAIL  a rule')\nsys.exit(None)\n", "printed FAIL"),
    "dies before its first check": ("stub_crash.py", "raise RuntimeError('early')\n", "exit 1"),
}
for what, (name, body, want) in cases.items():
    why, code, _ = judged(stub(name, body))
    check(f"a suite that {what} fails, and run_all says so", why.startswith(want), (why, code))
why, code, _ = judged(stub("stub_pass.py", "print('  PASS  a rule')\n"))
check("one that passes a check and exits 0 passes", why == "", why)
why, _, _ = judged(stub("stub_tool.py", "print('no findings')\n"), kind="check")
check("a check - one of the tools - is judged by its exit code alone", why == "", why)

print("\n[2] a job that does not end, or leaves a process behind (review 23.10.2026, R7-2)")
# Until round 132 run_all waited without end on a hung job, its output captured.
started = time.monotonic()
why, code, _ = judged(stub("stub_hang.py", "import time\nprint('  PASS  first', flush=True)\n"
                                           "time.sleep(60)\n"), limit=2.0)
spent = time.monotonic() - started
check("a job past its limit is HUNG, taken down, and named", code is run_all.HUNG
      and why.startswith("HUNG") and spent < 20, (why, round(spent, 1)))
# A child that outlives the job and holds its output - handed it explicitly,
# as Windows passes no handle otherwise: a pipe would stay open until the
# child ends, and so would a read of it - 20 s on, twice the bound here.
leaver = stub("stub_leaver.py",
              "import subprocess, sys\n"
              "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'],\n"
              "                 stdout=sys.stdout, stderr=sys.stderr)\n"
              "print('  PASS  left a child running', flush=True)\n")
started = time.monotonic()
folders_before = set((ROOT / "build").glob("run_all-*"))
why, code, _ = judged(leaver, limit=60.0)
left_behind = set((ROOT / "build").glob("run_all-*")) - folders_before
spent = time.monotonic() - started
check("a job that ends but leaves a child holding its output is judged when it ends, not when the child does",
      why == "" and spent < 10, (why, code, round(spent, 1)))

print("\n[3] --quick and the heavy flags (review 23.10.2026, R7-3)")
try:
    run_all.parse(["--quik"])
    refused = False
except SystemExit as exc:
    refused = exc.code == 2
check("a misspelt flag stops run_all: --quik ran everything", refused)
light_ocp = stub("stub_light_ocp.py", "import OCP.gp\nprint('  PASS  imported OCP')\n")
why, _, _ = judged(light_ocp, heavy=False, watch=True)
check("a job marked light that loads OCP fails, and says to mark it heavy",
      "loads OCP" in why, why)
why, _, _ = judged(stub("stub_light.py", "import json\nprint('  PASS  no OCCT')\n"), heavy=False, watch=True)
check("and one that does not passes", why == "", why)
flags = {Path(str(script)).name: heavy for _, script, heavy, _ in run_all.JOBS}
check("the flags are what -X importtime measured: the six light jobs that load OCP are heavy",
      all(flags[name] for name in ("test_skill_pins.py", "test_launcher.py", "test_variant_path.py",
                                   "test_settings.py", "test_gui.py", "test_window_rules.py")),
      {n: flags[n] for n in ("test_skill_pins.py", "test_variant_path.py")})

print("\n[4] bbox and volume measure what they say (review 23.10.2026, R7-4, R7-5)")
from OCP.BRep import BRep_Builder  # noqa: E402
from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon,  # noqa: E402
                                BRepBuilderAPI_NurbsConvert)
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeTorus  # noqa: E402
from OCP.TopAbs import TopAbs_ShapeEnum  # noqa: E402
from OCP.TopExp import TopExp_Explorer  # noqa: E402
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shell, TopoDS_Solid  # noqa: E402
from OCP.gp import gp_Pnt  # noqa: E402


def near_box(got, want, tol=1e-6):
    return all(abs(a - b) <= tol for a, b in zip(got, want))


nurbs = BRepBuilderAPI_NurbsConvert(BRepPrimAPI_MakeCylinder(5.0, 10.0).Shape(), True).Shape()
check("a NURBS cylinder, radius 5, height 10, is boxed exactly: it was 5 mm too wide",
      near_box(_support.bbox(nurbs), (-5, -5, 0, 5, 5, 10)), _support.bbox(nurbs))
torus = BRepPrimAPI_MakeTorus(10.0, 2.0).Shape()
check("an analytic torus, R 10, r 2, too: it was 0.99 mm too wide",
      near_box(_support.bbox(torus), (-12, -12, -2, 12, 12, 2)), _support.bbox(torus))
block = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 30.0, 20.0, 10.0).Shape()
check("a closed block weighs what it is", abs(_support.volume(block) - 6000.0) < 1e-6,
      _support.volume(block))


def ambiguous(shape):
    try:
        return f"{_support.volume(shape):.6f}"
    except _support.VolumeAmbiguous as exc:
        return f"refused: {exc}"


face = BRepBuilderAPI_MakeFace(BRepBuilderAPI_MakePolygon(
    gp_Pnt(40, 0, 1.6), gp_Pnt(50, 0, 1.6), gp_Pnt(50, 10, 1.6), gp_Pnt(40, 10, 1.6), True).Wire(),
    True).Face()
builder = BRep_Builder()
heap = TopoDS_Compound()
builder.MakeCompound(heap)
builder.Add(heap, block)
builder.Add(heap, face)
said = ambiguous(heap)
check("a block with a loose face beside it is refused: the face made its 6000 mm3 read 5902.857",
      said.startswith("refused"), said)
shell = TopoDS_Shell()
builder.MakeShell(shell)
faces = TopExp_Explorer(BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape(), TopAbs_ShapeEnum.TopAbs_FACE)
for _ in range(5):                                   # a cube with one face missing
    builder.Add(shell, TopoDS.Face_s(faces.Current()))
    faces.Next()
open_cube = TopoDS_Solid()
builder.MakeSolid(open_cube)
builder.Add(open_cube, shell)
said = ambiguous(open_cube)
check("so is a cube with a face missing: it read 0.8, one solid, no free edge", said.startswith("refused"),
      said)

print("\n[5] read_step names what it cannot read (review 23.10.2026, R7-6)")
# Each in a process of its own: until round 132 both died of an access
# violation inside OCCT, and took the asking suite with them.
garbage = HERE / "garbage.step"
garbage.write_text("ISO-10303-21;\nthis is not a STEP file\n", encoding="ascii")
for what, path, said in (("a missing file", HERE / "no such.step", "no STEP file at"),
                         ("a garbled file", garbage, "does not read as STEP")):
    done = subprocess.run([PY, "-B", "-c", "import sys; sys.path.insert(0, sys.argv[1]); "
                           "from _support import read_step; read_step(sys.argv[2])",
                           str(ROOT / "tests"), str(path)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)
    check(f"{what}: a StepUnreadable that names it and says '{said}', not a crash", done.returncode == 1
          and "StepUnreadable" in done.stderr and str(path.name) in done.stderr and said in done.stderr,
          (done.returncode, done.stderr.strip().splitlines()[-1:] if done.stderr.strip() else ""))

print("\n[6] the turn probe tells a refusal from a failure to ask (review 23.10.2026, R7-7)")
if sys.platform == "win32":
    import ctypes
    import os

    k32 = ctypes.windll.kernel32
    k32.CreateEventW.restype = ctypes.c_void_p
    k32.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p]
    k32.CreateMutexW.restype = ctypes.c_void_p
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    stem = f"Simple3D-harness-{os.getpid()}"
    event = k32.CreateEventW(None, 1, 0, stem + "-event")
    held = k32.CreateMutexW(None, 1, stem + "-held")
    got = {what: _support.session_turn_elsewhere(300, name)
           for what, name in (("free", stem + "-free"), ("held", stem + "-held"),
                              ("an event's name", stem + "-event"))}
    k32.CloseHandle(event)
    k32.CloseHandle(held)
    check("a free turn is taken, a held one refused",
          got["free"] == _support.TURN_TAKEN and got["held"] == _support.TURN_REFUSED, got)
    check("and a name an event holds is no refusal: the probe could not ask, and says so",
          got["an event's name"] == _support.TURN_UNASKED, got)
else:
    check("not Windows: there is no session turn to probe", True)

print("\n[7] no desktop of their own, no GUI suite (review 23.10.2026, R7-9)")
if sys.platform == "win32":
    # A message-only window first, as any import that makes one would: then
    # SetThreadDesktop refuses, error 170, and the suite must not go on.
    blocked = stub("stub_window_first.py",
                   "import ctypes, sys\nfrom ctypes import wintypes\n"
                   "u = ctypes.windll.user32\nu.CreateWindowExW.restype = wintypes.HWND\n"
                   "u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, "
                   "wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, "
                   "wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]\n"
                   "u.CreateWindowExW(0, 'STATIC', None, 0, 0, 0, 0, 0, wintypes.HWND(-3), None, None, None)\n"
                   f"sys.path.insert(0, {str(ROOT / 'tests')!r})\n"
                   "from _support import windows_off_screen_or_stop\n"
                   "windows_off_screen_or_stop()\nprint('went on to open its windows')\n")
    done = subprocess.run([PY, "-B", str(blocked)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120)
    check("a suite whose windows cannot go to a desktop of their own stops, with a FAIL line saying why",
          done.returncode == 1 and "  FAIL  the windows cannot be kept off the user's desktop" in done.stdout
          and "error 170" in done.stdout and "went on" not in done.stdout,
          (done.returncode, done.stdout.strip()[-200:], done.stderr.strip()[-200:]))
    # And four GUI suites at once, as tools/mutate.py runs them, each get one,
    # each holding a window there while the others ask. Until round 132 they
    # shared one name, and a desktop one process made another could neither
    # create nor open, error 5: of eight at once in session 0, one got it.
    together = stub("stub_desktop_shared.py",
                    f"import sys, time\nsys.path.insert(0, {str(ROOT / 'tests')!r})\n"
                    "from _support import windows_off_screen_or_stop\n"
                    "windows_off_screen_or_stop()\nimport tkinter\nt = tkinter.Tk()\nt.update()\n"
                    "print('went on, a window of its own', flush=True)\ntime.sleep(2)\nt.destroy()\n")
    four = [subprocess.Popen([PY, "-B", str(together)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace") for _ in range(4)]
    said = [p.communicate(timeout=120)[0] for p in four]
    went = [s for s in said if "went on" in s]
    check("four GUI suites at once each get a desktop of their own", len(went) == 4,
          [s.strip().splitlines()[-1:] for s in said if "went on" not in s])
else:
    check("not Windows: no user's desktop to keep them off", True)

print("\n[8] the name check keeps every defect pyflakes finds (review 23.10.2026, R7-15)")
sandbox = HERE / "names"
for folder in ("stepbuilder", "tests", "tools"):
    (sandbox / folder).mkdir(parents=True)
defects = {"syntax_broken.py": "def f(:\n    pass\n",
           "assert_tuple.py": "assert (1, 'always')\n",
           "keys.py": "d = {'a': 1, 'a': 2}\n",
           "islit.py": "x = 1\nif x is 'a':\n    pass\n",
           "fmt.py": "print('%s %s' % (1,))\n",
           "star.py": "from os import *\nprint(sep)\n"}
for name, body in defects.items():
    (sandbox / "tools" / name).write_text(body, encoding="utf-8")
(sandbox / "tests" / "reexport.py").write_text("import os\n", encoding="utf-8")
done = subprocess.run([PY, "-B", str(ROOT / "tools" / "python_names.py"), "--root", str(sandbox)],
                      capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
named = {name for name in defects if name in done.stdout}
check("a syntax error, an assert of a tuple, a key given twice, `is` with a literal, a % that "
      "does not fit, a name from a star import: each is named, and the check fails",
      done.returncode == 1 and named == set(defects), (done.returncode, sorted(set(defects) - named)))
check("an unused import - the package re-exports on purpose - is not",
      "reexport.py" not in done.stdout, done.stdout[-300:])

print("\n[9] the ignore rules hide no source and let no output or board through (review 23.10.2026, R7-16)")
IGNORED = ["demo/ap-214/demo.step", "demo/ap-214/MyBoard.step", "demo/ap-214/demo_variant1.step",
           "demo/ap-214/demo_simple_23_10_2026.step", "demo/ap-214/board.step.part", "myboard.brd",
           "pcb/myboard.brd", "cad/myboard.json", "input/myboard.brd", "failed/8231-a2.json",
           "build/skill_golden/myboard/myboard.json", "simple3d_config.local.json", "simple3d_crash.log",
           "demo/demo.jrl", "stepbuilder/__pycache__/core.cpython-314.pyc", ".claude/settings.local.json"]
KEPT = ["stepbuilder/lib/helpers.py", "skill/lib/s3d_extra.il", "stepbuilder/parts/plan.py",
        "tests/fixtures/target/expect.json", "docs/build/notes.md", "tests/fixtures/board.log",
        "tests/fixtures/preflight/new.log", "tests/fixtures/new_case.json", "demo/step_files/new_model.stp",
        "demo/step_files/new_model.step", "tools/probes/probe_new.il", "demo/demo.brd", "stepbuilder/env/x.py"]
repo = HERE / "ignore-rules"
repo.mkdir()
shutil.copy2(ROOT / ".gitignore", repo / ".gitignore")
made = subprocess.run(["git", "init", "-q", str(repo)], capture_output=True, text=True)
if not check("a scratch repository to ask git in", made.returncode == 0, made.stderr.strip()):
    pass
else:
    def ignored(rel):
        return subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", "--no-index", rel],
                              capture_output=True).returncode == 0
    wrong_in = [rel for rel in IGNORED if not ignored(rel)]
    wrong_out = [rel for rel in KEPT if ignored(rel)]
    check("every output, board and scratch file is ignored, dated or not", not wrong_in, wrong_in)
    check("and no source folder, fixture, model or the demo board is", not wrong_out, wrong_out)

# The folder run_job could not take away while [2]'s child still held its
# output, once that child has ended - waited for, 30 s at most. Only that
# one: a run_all running this suite has a folder of its own there, in use.
deadline = time.monotonic() + 30
for left in left_behind:
    shutil.rmtree(left, ignore_errors=True)
    while left.exists() and time.monotonic() < deadline:
        time.sleep(0.5)
        shutil.rmtree(left, ignore_errors=True)

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
