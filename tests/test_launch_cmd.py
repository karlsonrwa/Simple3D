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


def preflight_cmd(exe=None, imports="probepkg, tkinter", script_dir=None):
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
    return (f'cmd /c start /B /WAIT "" /D "{script_dir or SCRIPT_DIR}" "{exe}" -u '
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


sys.path.insert(0, str(ROOT / "tools"))
from skill_lex import strip_comments  # noqa: E402


def uncommented(text):
    """SKILL with its comments off - a word in a comment is not a call. By the
    lexer, which keeps a ';' inside a literal: until round 129 this cut each
    line at its first ';', and s3dPreflight's command line holds two inside
    its -c string ("import sys; print(...)"), so every check of that body read
    it cut short - the cut test_emit's strcat guard was rid of in round 128."""
    return strip_comments(text)

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
# Round 129 (R2n-14 of the 28.10.2026 review): success is a LINE that reads
# S3D_OK. A word anywhere in a line is forged by any path that holds it - a
# traceback names each file by its path - and Allegro 25.1 read a failed import
# from an install folder "S3D_OK inst plain" as success. The reading lives in
# s3dPreflightRead, whose copy test_skill_pins [7] holds to Allegro's own
# answers on tests/fixtures/preflight; here the source, and the case itself.
import skill_transliterations as T  # noqa: E402
code = uncommented(il)
check("no line of the code takes S3D_OK anywhere in a line for success",
      'rexMatchp( "S3D_OK"' not in code, [l.strip() for l in code.splitlines() if 'rexMatchp( "S3D_OK"' in l])
check("s3dPreflight reads its log with s3dPreflightRead, once",
      " ".join(code[code.index("procedure( s3dPreflight("):].split()).count(
          "verdict = s3dPreflightRead( logFile )") == 1)
read_body = " ".join(code[code.index("procedure( s3dPreflightRead("):].split("\nprocedure( ")[0].split()) \
    if "procedure( s3dPreflightRead(" in code else ""
for statement in ('text = s3dLineText( line )', 'when( text == "S3D_OK" ok = t )',
                  'when( (strlen( text ) > 7) && (substring( text 1 7 ) == "S3D_PY ") whichPy = text )'):
    check(f"s3dPreflightRead: {statement}", read_body.count(statement) == 1, read_body[:200])
BAD_DIR = WORK / "S3D_OK inst plain"
BAD_DIR.mkdir(exist_ok=True)
(BAD_DIR / "failing_standin.py").write_text("raise ImportError(\"No module named 'OCP'\")\n", encoding="utf-8")
run_preflight(preflight_cmd(imports="failing_standin, tkinter", script_dir=BAD_DIR))
raw = LOGF.read_bytes() if LOGF.exists() else b""
held = [l for l in raw.decode("utf-8", "replace").splitlines() if "S3D_OK" in l]
check("an import failing in a folder whose name holds S3D_OK puts the word on a traceback line",
      held and all("failing_standin" in l or "S3D_OK inst plain" in l for l in held), held)
check("...which the check's reading does not take for success",
      T.s3d_preflight_read(raw)[0] is None and T.s3d_preflight_read(raw)[1] is True,
      T.s3d_preflight_read(raw))
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
cad = uncommented(il)[uncommented(il).index("procedure( s3dResolveCadDir("):]
cad = cad[:cad.index("\nprocedure( ", 1)]
flat = " ".join(cad.split())
# Since round 129 (R2n-17 of the 28.10.2026 review) the leaf and its parent
# are found by scanning, not by parseString, which drops the "//" of a UNC
# path: a board opened as //server/share/.../rev/pcb asked for the RELATIVE
# server/share/.../rev/cad and wrote beside itself, though the cad folder was
# there (measured in Allegro 25.1 on //localhost/D$/...).
for statement in ('leaf = s3dLeafOf( t_designDir )',
                  'parent = s3dFolderOf( t_designDir )',
                  'if( (upperCase( leaf ) == "PCB") && (parent != "") then',
                  'cad = strcat( parent "/cad" )',
                  'if( isDir( cad ) then'):
    check(f"s3dResolveCadDir: {statement}", flat.count(" ".join(statement.split())) == 1,
          flat.count(" ".join(statement.split())))
check("s3dResolveCadDir splits nothing with parseString", "parseString" not in flat, flat[:200])
slashes = " ".join(uncommented(il)[uncommented(il).index("procedure( s3dSlashes("):].split(
    "\nprocedure( ")[0].split())
check("s3dSlashes makes each back-slash a slash, with no parseString to drop a UNC path's \"//\"",
      'out = pcreReplace( pcreCompile( "\\\\\\\\" ) t_path "/" 0 )' in slashes and "parseString" not in slashes,
      slashes[:200])
# The rule, run: the copy (test_skill_pins [7] holds s3dSlashes, s3dLeafOf
# and s3dFolderOf to Allegro's own answers) with the folders that exist named.
HAVE = {"D:/p/rev/cad", "//srv/share/p/rev/cad"}
for design, want in (("D:/p/rev/pcb", "D:/p/rev/cad"), ("D:\\p\\rev\\pcb", "D:/p/rev/cad"),
                     ("D:/p/rev/pcb/", "D:/p/rev/cad"), ("D:/q/rev/pcb", "D:/q/rev/pcb"),
                     ("D:/p/rev/board", "D:/p/rev/board"), ("pcb", "pcb"),
                     ("//srv/share/p/rev/pcb", "//srv/share/p/rev/cad"),
                     ("\\\\srv\\share\\p\\rev\\pcb", "//srv/share/p/rev/cad"),
                     ("//srv/share/q/rev/pcb", "//srv/share/q/rev/pcb")):
    got = T.s3d_resolve_cad_dir(design, HAVE.__contains__)
    check(f"{design!r} writes to {want!r}", got == want, got)
check("an unreadable folder is said, not parsed", T.s3d_resolve_cad_dir(None, HAVE.__contains__) is None)
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

print("\n[10] the interpreter is looked for before start is asked "
      "(round 129, review 28.10.2026 R2n-18)")
# start's answer to a program it cannot find is a message box of Windows',
# titled with the name, that waits for someone to close it - and system()
# waits for start. Measured in round 129 on a desktop of its own
# (build/fix-2026-10-31/r129/launch_cases.py): a pinned path that does not
# exist and a bare name on no PATH alike left no log and a cmd still waiting
# 15 s later; on the 4090, with no desktop, the review's run hung 40 s. So no
# missing program is started here either: the rule is run on its copy, which
# finds what cmd would find.
pre = body("s3dPreflight")
looked, started = pre.find("failure = if( s3dProgramFile( exe ) then nil else 'missing )"), pre.find("errset( system(")
check("s3dPreflight looks for the interpreter, then starts it only when it was found",
      0 <= looked < started and pre[looked:started].count("unless( failure") == 1, (looked, started))
prog = body("s3dProgramFile")
for statement in ('exts = cons( "" parseString( extVar ";" ) )', "if( s3dIsPathName( t_exe ) then",
                  'dirs = cons( getWorkingDir() parseString(', "when( isFile( candidate ) hit = candidate )"):
    check(f"s3dProgramFile: {statement}", prog.count(statement) == 1, prog[:200])
here = Path(PY)
on_path = f'"{here.parent}";{WORK / "nowhere"}'
cases = [
    (str(here), "this interpreter, by its full path"),
    (str(here)[:-4] if str(here).lower().endswith(".exe") else str(here), "...and without its .exe (PATHEXT)"),
    (str(WORK / "no such folder" / here.name), None),
    (here.stem, "its bare name, its folder on PATH - the quotes round it dropped"),
    ("s3d_no_such_python", None),
    ("", None),
]
for exe, found in cases:
    got = T.s3d_program_file(exe, pathext=os.environ.get("PATHEXT"), path=on_path, cwd=str(WORK),
                             is_file=os.path.isfile)
    check(f"{exe!r}: {found or 'nothing to start'}", (got is not None) == (found is not None), got)

print("\n[11] the dialog says what the check found (round 129, review 28.10.2026 R2n-15)")
# Until round 129 every failure said "Python ran, but could not import what it
# needs", also when Windows found nothing to run - where installing packages
# is no answer. test_skill_pins [7] holds the copy to Allegro's own words.
check("after start, the case is Python's when Python spoke, and silent otherwise",
      pre.count("failure = if( pySpoke then 'python else 'silent )") == 1, pre[started:started + 400])
check("s3dPreflight's dialog takes its words from s3dPreflightDialog, by case",
      pre.count("errset( axlUIConfirm( s3dPreflightDialog( failure exe ) 'error ) )") == 1
      and "Python ran, but could not import" not in pre, pre[-300:])
words = {case: T.s3d_preflight_dialog(case, "C:/x/pythonw.exe") for case in ("missing", "python", "silent")}
check("'missing names the program and offers no packages",
      "C:/x/pythonw.exe" in words["missing"] and "import" not in words["missing"], words["missing"])
check("'python says the import failed", "could not import" in words["python"], words["python"])
check("'silent names the program and does not blame the packages",
      "C:/x/pythonw.exe" in words["silent"] and "import" not in words["silent"], words["silent"])
check("the three are three different texts", len(set(words.values())) == 3)

print("\n[12] the originals of the copies test_skill_pins [7] holds to Allegro (round 129)")
# [7] says each copy answers as Allegro answered when the fixture was
# recorded; these say the source still computes what it computed then. Without
# them a change to a body no other check reads - s3dLineText's line end, the
# trailing separator s3dSlashes takes off - passes every suite.


def pin_launcher(name, *statements):
    text = body(name)
    for statement in statements:
        want = " ".join(statement.split())
        check(f"{name}: {want[:90]}", text.count(want) == 1, f"found {text.count(want)} times")


pin_launcher("s3dSlashes",
             'while( (n > 1) && (substring( out n 1 ) == "/") && !((n == 3) && (substring( out 2 1 ) == ":")) '
             'n = n - 1 )',
             "if( n > 0 then substring( out 1 n ) else out )")
pin_launcher("s3dLeafOf",
             'when( (c == "/") || (c == "\\\\") cut = i )',
             'if( cut < strlen( t_path ) then substring( t_path cut + 1 ) else "" )')
pin_launcher("s3dLineText",
             'while( (n > 0) && ((substring( t_line n 1 ) == "\\n") || (substring( t_line n 1 ) == "\\r")) '
             'n = n - 1 )',
             'if( n > 0 then substring( t_line 1 n ) else "" )')
pin_launcher("s3dIsPathName", 'when( (c == "/") || (c == "\\\\") || (c == ":") path = t )')
pin_launcher("s3dPreflightRead",
             'when( rexMatchp( "Traceback" line ) pySpoke = t )', 'when( rexMatchp( "Error" line ) pySpoke = t )')
pin_launcher("s3dPreflightDialog",
             "( (s_case == 'missing) sprintf( nil \"Windows finds no program %s to run.\\n\" t_exe ) )",
             "( (s_case == 'python) \"Python ran, but could not import what it needs (cadquery-ocp / tkinter).\\n\" )",
             "( t sprintf( nil \"%s started, but said nothing the check could read.\\n\" t_exe ) )")
pin_launcher("s3dProgramFile",
             'folder = if( stringp( dir ) then s3dSlashes( pcreReplace( pcreCompile( "\\"" ) dir "" 0 ) ) else "" )',
             'candidate = strcat( if( folder != "" then strcat( folder "/" ) else "" ) t_exe ext )')

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
