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

"""The shape of the command line s3dLaunch and s3dPreflight hand to cmd.

Transliterated from simple3d.il the way test_quote.py transliterates
s3dJsonQuote, and run through os.system - the C runtime's system(), which is
the closest stand-in available for SKILL's.

Why this is worth a suite of its own: the launcher used to write a .bat and run
that, because a design path with a space did not survive the trip (round 5).
The real culprit was cmd's own rule - it strips the FIRST and LAST quote of a
/c command line - and not "start", which was blamed at the time. The shape below
is what works, and every part of it is load-bearing:

    cmd /c start "" /D "script dir" "interpreter" -m stepbuilder ...

Begin with a bare word so nothing is stripped; pass "" so start does not read
the interpreter path as a window title; use /D instead of a "cd /d ... &&"
chain, because a chain binds to the OUTER shell and would lose the working
directory if system() wrapped the line in a cmd of its own.

Every case therefore runs twice - once as written, once behind an extra
"cmd /c " - so the shape is proven independent of how many shells SKILL's
system() puts in front of it.
"""
import json, os, shutil, sys, time
from pathlib import Path

if sys.platform != "win32":
    print("not Windows - this shape is cmd-specific; skipped")
    sys.exit(0)

fails = []
def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(name)


# Spaces in both directories, deliberately: that is the case that broke.
WORK = _OUT / "launch cmd"
SCRIPT_DIR = WORK / "my script dir"      # stands in for S3D_ScriptDir
DESIGN_DIR = WORK / "my design dir"      # stands in for the design's cad folder
if WORK.exists():
    shutil.rmtree(WORK)
(SCRIPT_DIR / "probepkg").mkdir(parents=True)
DESIGN_DIR.mkdir(parents=True)

# A stand-in for the stepbuilder package: importable only when the working
# directory really is SCRIPT_DIR, which is what /D has to deliver.
(SCRIPT_DIR / "probepkg" / "__init__.py").write_text("", encoding="utf-8")
(SCRIPT_DIR / "probepkg" / "__main__.py").write_text(
    "import json, os, sys, pathlib\n"
    "pathlib.Path(sys.argv[1]).write_text(\n"
    "    json.dumps({'argv': sys.argv[2:], 'cwd': os.getcwd()}), encoding='utf-8')\n",
    encoding="utf-8")

PY = sys.executable
OUTF = WORK / "argv.json"
LOGF = DESIGN_DIR / "_simple3d_preflight.txt"

# The argument tail s3dExportCommand builds, shortened but the same shape.
TAIL = (f'-m probepkg "{OUTF}" --json-dir "{DESIGN_DIR}" '
        f'--brd-name "my board" --dated-name')


def launch_cmd():
    """s3dLaunch: detached, no console, working directory set by /D."""
    return f'cmd /c start "" /D "{SCRIPT_DIR}" "{PY}" {TAIL}'


def preflight_cmd():
    """s3dPreflight: synchronous (/B /WAIT), output captured to a file."""
    return (f'cmd /c start /B /WAIT "" /D "{SCRIPT_DIR}" "{PY}" '
            f'-c "import probepkg, tkinter; print(\'S3D_OK\')" > "{LOGF}" 2>&1')


def run_launch(cmd, wait=8.0):
    if OUTF.exists():
        OUTF.unlink()
    os.system(cmd)
    deadline = time.time() + wait          # start returns before the child runs
    while time.time() < deadline and not OUTF.exists():
        time.sleep(0.05)
    if not OUTF.exists():
        return None
    return json.loads(OUTF.read_text(encoding="utf-8"))


def run_preflight(cmd):
    if LOGF.exists():
        LOGF.unlink()
    os.system(cmd)
    return LOGF.read_text(encoding="utf-8", errors="replace") if LOGF.exists() else ""


print("\n[1] launch: argv and working directory survive, at both nesting depths")
for label, cmd in [("one cmd layer", launch_cmd()),
                   ("two cmd layers", "cmd /c " + launch_cmd())]:
    got = run_launch(cmd)
    if got is None:
        check(f"{label}: the GUI stand-in ran", False, "no output file")
        continue
    check(f"{label}: the GUI stand-in ran", True)
    check(f"{label}: spaced --json-dir arrives whole",
          got["argv"][:2] == ["--json-dir", str(DESIGN_DIR)], f"got {got['argv'][:2]}")
    check(f"{label}: spaced --brd-name arrives whole",
          "my board" in got["argv"], f"got {got['argv']}")
    check(f"{label}: /D set the working directory",
          Path(got["cwd"]) == SCRIPT_DIR, f"got {got['cwd']}")

print("\n[2] preflight: synchronous, output captured, sentinel present")
for label, cmd in [("one cmd layer", preflight_cmd()),
                   ("two cmd layers", "cmd /c " + preflight_cmd())]:
    log = run_preflight(cmd)
    check(f"{label}: sentinel in the log", "S3D_OK" in log, f"log was {log!r}")

print("\n[3] preflight reports a Python failure in Python's own words")
broken = preflight_cmd().replace("import probepkg,", "import no_such_module,")
log = run_preflight(broken)
check("stderr is captured too", "Traceback" in log or "ModuleNotFoundError" in log,
      f"log was {log!r}")
check("the branch that prints the log text is reachable",
      "Error" in log or "Traceback" in log, f"log was {log!r}")

print("\n[4] the negative control: a line that BEGINS with a quote loses its quoting")
# This is the form the .bat existed to avoid. Kept as a test so the reason for
# the "start" prefix survives the next tidy-up.
if OUTF.exists():
    OUTF.unlink()
# cmd's complaint about the mangled line is localised and lands in the OEM
# codepage, so it is sent to NUL - it would otherwise print as mojibake in the
# middle of a passing run. The redirect adds no quotes and so cannot rescue the
# form under test.
os.system(f'"{PY}" {TAIL} > nul 2>&1')
got = json.loads(OUTF.read_text(encoding="utf-8")) if OUTF.exists() else None
intact = got is not None and got["argv"][:2] == ["--json-dir", str(DESIGN_DIR)]
check("quoted-first form does NOT deliver the spaced path",
      not intact, "it survived - cmd's stripping rule may have changed")

print("\n[5] simple3d.il still uses the shape this suite proves")
il = (_ROOT / "simple3d.il").read_text(encoding="utf-8")
check('s3dLaunch uses  start "" /D', 'start \\"\\" /D' in il)
check('s3dPreflight uses  start /B /WAIT "" /D', 'start /B /WAIT \\"\\" /D' in il)
check("no batch file is written any more",
      "_simple3d_launch.bat" not in il and "_simple3d_preflight.bat" not in il)

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
