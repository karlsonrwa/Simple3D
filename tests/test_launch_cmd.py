# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, OUT, fails, check

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
import json, os, re, shutil, sys, time
from pathlib import Path

if sys.platform != "win32":
    print("not Windows - this shape is cmd-specific; skipped")
    sys.exit(0)


# Spaces in both directories, deliberately: that is the case that broke.
WORK = OUT / "launch cmd"
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
# The config's two names: "python" and "pythonw". s3dLaunch starts the window
# with pythonw - no console - and so does the stand-in (round 94: with
# python.exe, `start` gave it a console of its own, a Windows Terminal window
# on the user's desktop, twice per run and four copies at once under
# tools/mutate.py). Since round 114 the preflight runs the same interpreter;
# `start /B` with pythonw opens nothing either.
PYW = (str(Path(PY).with_name("pythonw.exe"))
       if Path(PY).with_name("pythonw.exe").is_file() else PY)
OUTF = WORK / "argv.json"
LOGF = DESIGN_DIR / "_simple3d_preflight.txt"

CONFIG = WORK / "my config dir" / "simple3d_config.json"   # never read: a spaced path to carry
SKILL_ESCAPES = {'\\"': '"', "\\\\": "\\", "\\n": "\n", "\\t": "\t"}


def skill_tail(il, values):
    """The window's argument tail as s3dExportCommand builds it - its
    `argTail = strcat( ... )` read out of simple3d.il, the literal pieces as
    the source spells them, each variable given values[name]. -> (tail, None)
    or (None, why). Until round 118 this suite wrote a tail of its own, "the
    same shape", so the quotes the SKILL puts round each path were never
    asked about: dropped from --json-dir, every suite stayed green (review
    23.10.2026, R2-9)."""
    m = re.search(r"argTail = strcat\(", il)
    if not m:
        return None, "no `argTail = strcat(` in simple3d.il"
    token = re.compile(r'\s*(?:("(?:\\.|[^"\\])*")|(\()|(\))|([A-Za-z_][A-Za-z0-9_]*))')
    pos, pieces = m.end(), []
    while True:
        t = token.match(il, pos)
        if t is None:
            return None, f"cannot read the strcat at {il[pos:pos + 40]!r}"
        pos = t.end()
        string, opened, closed, name = t.groups()
        if string is not None:
            pieces.append(re.sub(r"\\.", lambda e: SKILL_ESCAPES.get(e.group(0), e.group(0)),
                                 string[1:-1]))
        elif opened:
            return None, "a call inside the strcat - not a shape this reads"
        elif closed:
            return "".join(pieces), None
        elif name in values:
            pieces.append(values[name])
        else:
            return None, f"the tail names {name}, which this suite gives no value"


SKILL_TAIL, TAIL_WHY = skill_tail(
    (ROOT / "simple3d.il").read_text(encoding="utf-8"),
    {"S3D_ConfigFile": str(CONFIG), "cadDir": str(DESIGN_DIR), "designName": "my board"})
# What the window must receive, each spaced value in one piece.
WANT_ARGV = ["--gui", "--config", str(CONFIG), "--json-dir", str(DESIGN_DIR),
             "--output-dir", str(DESIGN_DIR), "--brd-name", "my board", "--dated-name"]
# The stand-in in place of the package, the file it writes to first.
TAIL = (f'-m probepkg "{OUTF}"' + SKILL_TAIL[len("-m stepbuilder"):]
        if SKILL_TAIL and SKILL_TAIL.startswith("-m stepbuilder ") else None)


def window_python(python, pythonw):
    """s3dWindowPython: the interpreter the 3D window runs under - pythonw,
    or python when pythonw is configured as "". The launch and the check both
    ask it. Until round 114 the check ran python and the window pythonw, and
    this suite copied that, so it reproduced the mismatch instead of catching
    it (review 23.10.2026, R2-2); [7] holds the source to this rule."""
    return pythonw if pythonw != "" else python


def launch_cmd(exe=None):
    """s3dLaunch: detached, no console, working directory set by /D."""
    exe = exe or window_python(PY, PYW)
    return f'cmd /c start "" /D "{SCRIPT_DIR}" "{exe}" {TAIL}'


def preflight_cmd(exe=None, imports="probepkg, tkinter"):
    """s3dPreflight: synchronous (/B /WAIT), output captured to a file, run
    with the interpreter the window will run under.

    The sentinels are SPLIT literals - print('S3D' '_OK') - and that is the
    point of case [3] below. From Python 3.13 a traceback echoes the source
    line of a -c command, so a sentinel written whole appears in the check's
    own FAILURE output and the check passes itself. Two adjacent literals
    concatenate at compile time: the process still prints S3D_OK, the source
    text cannot contain it.
    """
    exe = exe or window_python(PY, PYW)
    return (f'cmd /c start /B /WAIT "" /D "{SCRIPT_DIR}" "{exe}" -u '
            f'-c "import sys; print(\'S3D\' \'_PY\', sys.executable, '
            f'sys.version.split()[0]); '
            f'import {imports}; print(\'S3D\' \'_OK\')" > "{LOGF}" 2>&1')


# 40 s, not the 8 s this had: `start` is detached, so the wait is for a whole
# Python to come up, and on a loaded machine that is not 8 seconds. Measured
# 2026-09-22 - with three other mutation runs going, this suite went red on the
# clean tree inside tools/mutate.py, which then SKIPS an already-red suite for
# every row that names it: two rows would have been reported SURVIVED for a
# reason that has nothing to do with the test. A deadline is a machine's answer,
# not the program's ([[a-pass-the-environment-hands-you]]).
def run_launch(cmd, wait=40.0):
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
check("the argument tail is the one simple3d.il builds, read out of its strcat",
      TAIL is not None, TAIL_WHY or f"it does not start '-m stepbuilder ': {SKILL_TAIL!r}")
for label, cmd in ([("one cmd layer", launch_cmd()),
                    ("two cmd layers", "cmd /c " + launch_cmd())] if TAIL else []):
    got = run_launch(cmd)
    if got is None:
        check(f"{label}: the GUI stand-in ran", False, "no output file")
        continue
    check(f"{label}: the GUI stand-in ran", True)
    check(f"{label}: every argument arrives whole - the spaced config, cad folder and board name",
          got["argv"] == WANT_ARGV, f"got {got['argv']}")
    check(f"{label}: /D set the working directory",
          Path(got["cwd"]) == SCRIPT_DIR, f"got {got['cwd']}")

print("\n[2] preflight: synchronous, output captured, sentinel present")
for label, cmd in [("one cmd layer", preflight_cmd()),
                   ("two cmd layers", "cmd /c " + preflight_cmd())]:
    log = run_preflight(cmd)
    check(f"{label}: sentinel in the log", "S3D_OK" in log, f"log was {log!r}")
    check(f"{label}: the interpreter names itself",
          "S3D_PY " in log, f"log was {log!r}")

print("\n[3] preflight reports a Python failure in Python's own words")
broken = preflight_cmd().replace("import probepkg,", "import no_such_module,")
# A replace that matches nothing is silent, and this one carries the whole case.
check("the failing variant was actually built", "no_such_module" in broken,
      "the import text in preflight_cmd() changed")
log = run_preflight(broken)
check("stderr is captured too", "Traceback" in log or "ModuleNotFoundError" in log,
      f"log was {log!r}")
check("the branch that prints the log text is reachable",
      "Error" in log or "Traceback" in log, f"log was {log!r}")
# THE ONE THAT MATTERS. Python 3.13+ echoes the source line of a -c command in
# the traceback, so a sentinel written as print('S3D_OK') puts itself into the
# failure output and s3dPreflight reads its own echo as success - then launches
# a GUI under pythonw, which has no console, and it dies silently. Fixed by
# splitting the literal; this is what keeps it split. Vacuous on 3.12 and
# earlier, which is why case [5] checks the source text as well.
check("the sentinel does NOT appear in the failing log",
      "S3D_OK" not in log,
      f"the check would pass itself on this Python ({sys.version.split()[0]}); "
      f"log was {log!r}")
check("the failing run still names the interpreter",
      "S3D_PY " in log, f"log was {log!r}")

print("\n[4] the negative control: a line that BEGINS with a quote loses its quoting")
# This is the form the .bat existed to avoid. Kept as a test so the reason for
# the "start" prefix survives the next tidy-up.
if OUTF.exists():
    OUTF.unlink()
# cmd's complaint about the mangled line is localised and lands in the OEM
# codepage, so it is sent to NUL - it would otherwise print as mojibake in the
# middle of a passing run. The redirect adds no quotes and so cannot rescue the
# form under test.
if TAIL:
    os.system(f'"{PY}" {TAIL} > nul 2>&1')
got = json.loads(OUTF.read_text(encoding="utf-8")) if OUTF.exists() else None
intact = got is not None and got["argv"] == WANT_ARGV
check("quoted-first form does NOT deliver the spaced path",
      not intact, "it survived - cmd's stripping rule may have changed")

print("\n[5] simple3d.il still uses the shape this suite proves")
il = (ROOT / "simple3d.il").read_text(encoding="utf-8")


def uncommented(text):
    """SKILL with its comments off - a word in a comment is not a call."""
    return "\n".join(line.split(";")[0] if not line.lstrip().startswith(";") else ""
                     for line in text.splitlines())

check('s3dLaunch uses  start "" /D', 'start \\"\\" /D' in il)
check('s3dPreflight uses  start /B /WAIT "" /D', 'start /B /WAIT \\"\\" /D' in il)
check("no batch file is written any more",
      "_simple3d_launch.bat" not in il and "_simple3d_preflight.bat" not in il)
# Version-independent half of case [3]: whatever Python runs this suite, the
# sentinel must not be spelled out in the source handed to -c, or a traceback
# on 3.13+ hands it straight back and the check passes itself.
# Matched with the escaped quote that closes the -c argument, so the comment
# above s3dPreflight - which quotes the wrong form on purpose, to explain it -
# is not mistaken for the command itself.
check("the success sentinel is a SPLIT literal in the -c command",
      "print('S3D' '_OK')" in il and "print('S3D_OK')\\\"" not in il,
      "s3dPreflight's sentinel can be forged by its own traceback echo")
check("the check reports which interpreter answered",
      "sys.executable" in il and "S3D_PY " in il)
# The CALL, not the word: the comment three lines above the call explains what
# axlUIConfirm is for, so a grep over the whole file passes with the call gone.
# And in s3dPreflight's own body: since round 116 the refusal of a path cmd
# would change has a dialog of its own, which a whole-file grep found as well
# when the check's was gone (the row skill-preflight-no-dialog survived).
preflight_src = il[il.index("procedure( s3dPreflight("):]
preflight_src = preflight_src[:preflight_src.index("\nprocedure( ", 1)]
check("a failed preflight also says so in a blocking dialog",
      re.search(r"^\s*errset\(\s*axlUIConfirm\(", uncommented(preflight_src), re.M),
      "the console can be closed or not looked at")

print("\n[6] where the export writes: the pcb -> cad folder rule")
# The rule (simple3d.il, s3dResolveCadDir): a design in a folder called "pcb"
# that has a SIBLING "cad" writes into that sibling; anything else - no "pcb"
# folder, or a "pcb" folder with no "cad" beside it - writes beside the .brd.
# Nothing else in the repository reads this procedure, so what holds it is the
# statements that decide. A `cad` taken without asking whether it exists sends
# every export of a pcb-only layout into a folder that was never created;
# dropping the leaf test sends every export into a sibling of wherever the
# board happens to be.
cad = il[il.index("procedure( s3dResolveCadDir("):]
cad = cad[:cad.index("\nprocedure( ", 1)]
flat = " ".join(cad.split())
for statement in ('parts = parseString( t_designDir "/" )',
                  'leaf = if( n >= 1 then nth( n - 1 parts ) else nil )',
                  'if( leaf && (upperCase( leaf ) == "PCB") then',
                  'parent = buildString( s3dHeadList( parts n - 1 ) "/" )',
                  'cad = strcat( parent "/cad" )',
                  'if( isDir( cad ) then'):
    check(f"s3dResolveCadDir: {statement}", flat.count(" ".join(statement.split())) == 1,
          flat.count(" ".join(statement.split())))
# Derived: the folder NAMES are read out of the source rather than restated
# here, and both branches that fall back must hand back the design's own
# folder - never the candidate that does not exist.
leaf_name = re.search(r'upperCase\( leaf \) == "(\w+)"', flat)
sibling = re.search(r'cad = strcat\( parent "/(\w+)" \)', flat)
check("the two folder names are in the source", bool(leaf_name) and bool(sibling),
      (leaf_name, sibling))
if leaf_name and sibling:
    check(f"the leaf it looks for is {leaf_name.group(1)!r} and the sibling "
          f"{sibling.group(1)!r}",
          leaf_name.group(1) == "PCB" and sibling.group(1) == "cad",
          (leaf_name.group(1), sibling.group(1)))
check("the sibling is used only when it exists, and the fallback creates what it returns",
      flat.count("isDir( cad )") == 1 and flat.count("s3dMakeDirs( t_designDir )") == 2,
      (flat.count("isDir( cad )"), flat.count("s3dMakeDirs( t_designDir )")))
check("a folder that cannot be read is said rather than parsed",
      re.search(r'if\( !stringp\( t_designDir \) then s3dWarn\(', flat), flat[:160])

print("\n[7] the check runs the interpreter the window runs (round 114, review 23.10.2026 R2-2)")
# The reviewer's case: "python" pinned to an install with cadquery-ocp,
# "pythonw" left a bare name that PATH resolves to one without it. A stand-in
# module plays that dependency: it imports under python and refuses under
# pythonw, as the other install would. No missing program is started for it -
# `start` may answer one with a Windows message box, on whatever desktop runs
# the suite.
(SCRIPT_DIR / "ocp_standin.py").write_text(
    "import sys\n"
    "if sys.executable.lower().endswith('pythonw.exe'):\n"
    "    raise ImportError('no cadquery-ocp for this pythonw (stand-in)')\n",
    encoding="utf-8")
if PYW == PY:
    print("  (no pythonw.exe beside this interpreter: the behavioural half is skipped)")
else:
    log_py = run_preflight(preflight_cmd(PY, "ocp_standin, tkinter"))
    check("checked with python, as before round 114, the stand-in install passes",
          "S3D_OK" in log_py, f"log was {log_py!r}")
    log_win = run_preflight(preflight_cmd(window_python(PY, PYW), "ocp_standin, tkinter"))
    check("checked with the window's interpreter, it fails, and the log names pythonw",
          "S3D_OK" not in log_win and "pythonw" in log_win.lower()
          and "ImportError" in log_win, f"log was {log_win!r}")
check('pythonw configured as "" falls back to python', window_python(PY, "") == PY)


# simple3d.il holds the rule: one procedure says which interpreter, and both
# the launch and the check ask it. A procedure that is not there reads as
# empty, so its checks FAIL by name instead of ending the suite.
def body(name):
    start = il.find(f"procedure( {name}(")
    if start < 0:
        return ""
    end = il.find("\nprocedure( ", start + 1)
    return " ".join(uncommented(il[start:end if end > 0 else len(il)]).split())


which = body("s3dWindowPython")
check("s3dWindowPython: pythonw, or python when pythonw is empty",
      'if( (S3D_PythonW != "") then S3D_PythonW else S3D_Python )' in which, which)
for proc in ("s3dPreflight", "s3dLaunch"):
    assigned = re.findall(r"\bexe = (\S+)", body(proc))
    check(f"{proc} takes its interpreter from s3dWindowPython, and from nowhere else",
          assigned == ["s3dWindowPython()"], assigned)

print("\n[8] the export writes beside its own board, not into the working directory "
      "(round 115, review 23.10.2026 R2-3)")
# getWorkingDir() is wherever File > Open left Allegro - with "Change
# directory" unticked, another project's folder - while Variants.lst is looked
# for beside the board itself (s3dDesignFolder, the board's own path). In
# Allegro 25.1, with the working directory moved to project A, the command
# wrote board B's JSON into A's cad folder (docs/records/
# export-folder-2026-10-31.md). [6] above holds the pcb -> cad rule applied
# to the folder; this holds which folder it is applied to.
dd = body("s3dDesignDir")
first, fallback = dd.find("dir = s3dDesignFolder()"), dd.find("dir = getWorkingDir()")
check("s3dDesignDir asks the board's own path first",
      0 <= first < fallback, dd)
check("and the working directory only when that gives no folder, once",
      'unless( stringp( dir ) && (dir != "")' in dd and dd.count("getWorkingDir()") == 1, dd)
command = body("s3dExportCommand")
check("s3dExportCommand takes its folder from s3dDesignDir, and from nowhere else",
      command.count("designDir = s3dDesignDir()") == 1 and "getWorkingDir" not in command
      and "cadDir = s3dResolveCadDir( designDir )" in command,
      [m for m in re.findall(r"designDir = \S+|getWorkingDir", command)])

print("\n[9] a path cmd would change is named, never handed to it "
      "(round 116, review 23.10.2026 R2-4)")
# cmd replaces %NAME% inside quotes as well, and has no escape for it there;
# a folder "x %OS% y" made the check's log vanish and the console blame the
# interpreter. s3dCmdExpands (skill/s3d_util.il) says which strings cmd would
# change; test_skill_pins [7] holds its copy to Allegro's own answers, and
# here the copy is held to cmd itself: every case is echoed through cmd, and
# the copy must name a %NAME% exactly where the echo comes back changed.
# "%=C:%" is left to [7]: whether cmd has that hidden name depends on the
# process (the rule always counts it).
import subprocess
from skill_transliterations import s3d_cmd_expands

CMD_CASES = ["x %OS% y", "x %os% y", "x %Os% y", "x %NOPE_S3D% y", "x %NOPE_S3D%OS% y",
             "x %OS:~0,3% y", "x %OS:Win=W% y", "x %:OS% y", "x %NOPE_S3D:~1% y", "x %CD% y",
             "x %random% y", "x %ERRORLEVEL% y", "50% / 60%", "x % y", "x %% y",
             "x %%OS%% y", "x !OS! y", "x %windir% y", "x %PATH% y", "%OS%",
             "D:/Projects/AI/Claude/Simple3D"]
echoed = WORK / "echo.txt"
disagree = []
for text in CMD_CASES:
    if echoed.exists():
        echoed.unlink()
    subprocess.run(f'cmd /c echo ["{text}"] > "{echoed}"', shell=False)
    got = echoed.read_text(encoding="utf-8", errors="replace").strip() if echoed.exists() else ""
    changed = got != f'["{text}"]'
    if changed != (s3d_cmd_expands(text) is not None):
        disagree.append((text, got, s3d_cmd_expands(text)))
check(f"on all {len(CMD_CASES)} cases the rule names a %NAME% exactly where cmd changes the text",
      not disagree, disagree)

# The reviewer's case C: the install folder "x %OS% y". cmd hands start the
# folder "x Windows_NT y", which does not exist, and nothing runs - the log
# that should say S3D_OK holds cmd's own complaint, or nothing.
pct_dir = WORK / "x %OS% y"
pct_dir.mkdir(exist_ok=True)
log9 = run_preflight(f'cmd /c start /B /WAIT "" /D "{pct_dir}" "{PYW}" -u '
                     f'-c "print(\'S3D\' \'_OK\')" > "{LOGF}" 2>&1')
check("a folder with %OS% in it: the check's command finds nothing to run, and the rule names it",
      "S3D_OK" not in log9 and s3d_cmd_expands(str(pct_dir)) == "%OS%",
      (log9[:80], s3d_cmd_expands(str(pct_dir))))

# simple3d.il asks the rule before the check and the launch, about every
# string their command lines carry, and stops when it names one.
unsafe_at = command.find("unsafe = s3dCmdUnsafe(")
check("s3dExportCommand asks s3dCmdUnsafe before the check",
      0 <= unsafe_at < command.find("s3dPreflight( cadDir )"),
      (unsafe_at, command.find("s3dPreflight( cadDir )")))
for what in ("S3D_ScriptDir", "s3dWindowPython()", "S3D_ConfigFile", "cadDir", "designName"):
    check(f"  and asks it about {what}",
          re.search(r'list\( "[^"]+" ' + re.escape(what) + r' \)', command[unsafe_at:]) is not None,
          what)
check("and stops there, saying so, when it names one",
      "when( unsafe s3dMeterOff() s3dSayCmdUnsafe( unsafe cadDir ) return( nil ) )" in command,
      command[unsafe_at:unsafe_at + 400])
check("and the refusal says so in a blocking dialog too, as the failed check does",
      "errset( axlUIConfirm( strcat(" in body("s3dSayCmdUnsafe"), body("s3dSayCmdUnsafe")[:200])

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
