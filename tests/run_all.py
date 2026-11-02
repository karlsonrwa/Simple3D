"""Run every check and every test suite. Exit 0 only if all of them pass.

    python tests/run_all.py               everything
    python tests/run_all.py --quick       only the jobs that never load OCCT
    python tests/run_all.py --timeout S   seconds a job may take (default 1200)

Four of these are mechanical checks on the SKILL sources, and each exists
because something got past the previous ones: parenthesis balance, string
literals broken across a real newline, calls to procedures defined nowhere,
and call arity. Run them after any edit to a .il file - SKILL resolves names
at call time, so a broken file loads without complaint and fails only when
that line executes.

How a job is judged (round 132, review 23.10.2026 R7-1, R7-2, R7-3):

- a SUITE passes when it exits 0, printed at least one PASS line and no FAIL
  line. Until then the exit code alone decided: a suite that printed FAIL and
  exited 0, one that ran no check at all and one that ended in sys.exit(None)
  after a FAIL all passed. A CHECK (the tools) is judged by its exit code, as
  it prints its findings and not PASS lines;
- a job still running at its time limit is HUNG: its process tree is taken
  down and it fails by name. Until then run_all waited without end and, its
  output captured, showed nothing. The output goes to files, not pipes, so a
  process a job started and left behind cannot hold the wait open;
- a job marked light that loads OCP fails as well. --quick skips what loads
  OCCT, and six jobs marked light did, one of them building a board through
  core.generate; the flags below are what -X importtime measured on every job
  (build/fix-2026-10-31/r132/measure132.py), and a light job is run under it
  so that a new import cannot quietly make the flag a lie again.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
TESTS = ROOT / "tests"

# How much of a failing job's output is shown after its FAIL lines.
TAIL_LINES = 12
# Seconds a job may take before it is HUNG. The fold suite, the slowest, takes
# 62 s on the 4090 and about three times that on the development machine.
DEFAULT_TIMEOUT = 1200.0
HUNG = None                                  # the exit code of a job that never finished

# (label, script, heavy?, kind). heavy: the job loads OCP (measured); kind:
# "suite" prints a PASS or FAIL line per check (tests/_support.check),
# "check" prints its findings and decides by its exit code.
JOBS = [
    ("SKILL: parens, strings, calls, leaks",     TOOLS / "skill_checks.py", False, "check"),
    ("SKILL: call arity",                       TOOLS / "check_arity.py", False, "check"),
    ("Allegro runner: a HOME of its own",       TESTS / "test_allegro_home.py", False, "suite"),
    ("docs vs code",                            TOOLS / "audit_docs.py", False, "check"),
    ("Python: every name defined (pyflakes)",   TOOLS / "python_names.py", False, "check"),
    ("geometry regression (C++ baseline)",      TESTS / "test_regression_geometry.py", True, "suite"),
    ("board: zones",                            TESTS / "test_zones.py", True, "suite"),
    ("board: per-layer stackups",               TESTS / "test_layers.py", True, "suite"),
    ("board: stitching modes",                  TESTS / "test_modes.py", True, "suite"),
    ("board: plain-board stitching",            TESTS / "test_plain_modes.py", True, "suite"),
    ("board: soldermask exclusion",             TESTS / "test_nomask.py", True, "suite"),
    ("board: negative layers",                  TESTS / "test_neg.py", True, "suite"),
    ("board: duplicated cutouts",               TESTS / "test_dupcuts.py", True, "suite"),
    ("board: overlapping cutouts",              TESTS / "test_overlapping_cutouts.py", True, "suite"),
    ("board: an outline walked twice",          TESTS / "test_doubled_back.py", True, "suite"),
    ("board: folding flex bends",               TESTS / "test_bend.py", True, "suite"),
    ("silkscreen",                              TESTS / "test_silk.py", True, "suite"),
    ("copper pads",                             TESTS / "test_pads.py", True, "suite"),
    ("board: the surface under a point",        TESTS / "test_surface.py", True, "suite"),
    ("board: a zone inside another",            TESTS / "test_nested.py", True, "suite"),
    ("mechanical symbols",                      TESTS / "test_mech.py", True, "suite"),
    ("embedded models cross-check",             TESTS / "test_embedded.py", True, "suite"),
    ("STEP folder search path",                 TESTS / "test_index.py", True, "suite"),
    ("JSON quoting",                            TESTS / "test_quote.py", False, "suite"),
    ("JSON emission: every string quoted",      TESTS / "test_emit.py", False, "suite"),
    ("drill offset: the hole is not the pad",   TESTS / "test_drill_offset.py", False, "suite"),
    ("SKILL: every Python copy pinned",         TESTS / "test_skill_pins.py", True, "suite"),
    ("mutation table: every pattern matches",   TESTS / "test_mutations.py", False, "suite"),
    ("launcher command shape",                  TESTS / "test_launch_cmd.py", False, "suite"),
    ("launcher: one parser, the --gui mode",    TESTS / "test_launcher.py", True, "suite"),
    ("where Variants.lst is looked for",        TESTS / "test_variant_path.py", True, "suite"),
    ("settings: defaults + the local file",     TESTS / "test_config_merge.py", False, "suite"),
    ("settings: the gui section, no window",    TESTS / "test_settings.py", True, "suite"),
    ("GUI widgets and config",                  TESTS / "test_gui.py", True, "suite"),
    ("GUI window placement",                    TESTS / "test_geom.py", False, "suite"),
    ("the window's rules, no screen needed",    TESTS / "test_window_rules.py", True, "suite"),
    ("the harness itself",                      TESTS / "test_harness.py", True, "suite"),
]

CHECK_LINE = re.compile(r"^\s*(PASS|FAIL)\s{2}")
OCP_IMPORT = re.compile(r"^import time:.*\|\s+OCP(\.|\s*$)")
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def kill_tree(proc: subprocess.Popen) -> None:
    """The child and everything it started."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.kill()


def run_job(script: Path, limit: float, watch_imports: bool = False) -> tuple:
    """(exit code or HUNG, seconds, stdout, stderr) of one job run from ROOT.

    The output goes to two files in a folder of their own under build/, not
    to pipes: a process the job started and left running keeps a pipe open
    and a read of it waits on that process, whatever the job itself did."""
    (ROOT / "build").mkdir(exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="run_all-", dir=str(ROOT / "build")))
    argv = [sys.executable] + (["-X", "importtime"] if watch_imports else []) + [str(script)]
    started = time.monotonic()
    try:
        with open(folder / "out.txt", "w", encoding="utf-8", errors="replace") as out, \
                open(folder / "err.txt", "w", encoding="utf-8", errors="replace") as err:
            proc = subprocess.Popen(argv, stdout=out, stderr=err, cwd=str(ROOT), env=ENV)
            try:
                proc.wait(timeout=limit)
                code = proc.returncode
            except subprocess.TimeoutExpired:
                kill_tree(proc)
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    pass
                code = HUNG
        seconds = time.monotonic() - started
        return (code, seconds, (folder / "out.txt").read_text(encoding="utf-8", errors="replace"),
                (folder / "err.txt").read_text(encoding="utf-8", errors="replace"))
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def judge(kind: str, heavy: bool, code, out: str, err: str, limit: float) -> str:
    """"" when the job passed, else why it did not (the module docstring)."""
    if code is HUNG:
        return f"HUNG: still running after {limit:.0f} s, taken down"
    if code != 0:
        return f"exit {code}"
    if kind == "suite":
        lines = [line for line in out.splitlines() if CHECK_LINE.match(line)]
        if any(line.lstrip().startswith("FAIL") for line in lines):
            return "printed FAIL, yet exited 0"
        if not lines:
            return "ran no check: it printed no PASS or FAIL line"
    if not heavy and any(OCP_IMPORT.match(line) for line in err.splitlines()):
        return "marked light, yet it loads OCP - mark it heavy"
    return ""


def parse(argv: list) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="run_all.py", description="Run every check and every test suite.")
    p.add_argument("--quick", action="store_true", help="only the jobs that never load OCCT")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, metavar="S",
                   help="seconds a job may take before it is HUNG (default %(default)g)")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse(argv)                 # an unknown argument stops here (R7-3: --quik ran everything)
    jobs = [j for j in JOBS if not (args.quick and j[2])]

    width = max(len(label) for label, _, _, _ in jobs)
    failed = []
    started = time.time()

    for label, script, heavy, kind in jobs:
        if not script.exists():
            print(f"{label:{width}}  MISSING {script.name}")
            failed.append(label)
            continue
        code, seconds, out, err = run_job(script, args.timeout, watch_imports=not heavy)
        why = judge(kind, heavy, code, out, err, args.timeout)
        print(f"{label:{width}}  {'pass' if not why else 'FAIL'}  {seconds:5.1f}s"
              + (f"  - {why}" if why else ""))
        if why:
            failed.append(label)
            # The job's own FAIL lines, then the tail of what it printed - a
            # traceback is at the end, whole. A green run stays one screen;
            # a red one no longer depends on the word "error" appearing in
            # the line that matters (round 80, F3). The import times a light
            # job was run under are left out.
            lines = (out + err).splitlines()
            lines = [line for line in lines if not line.startswith("import time:")]
            fail_lines = [line for line in lines if line.lstrip().startswith(("  FAIL", "FAIL"))]
            for line in fail_lines[:20]:
                print(f"    {line.strip()}")
            tail = [line for line in lines[-TAIL_LINES:] if line.strip() and line not in fail_lines]
            if tail:
                print(f"    --- last {len(tail)} line(s) of {script.name} ---")
                for line in tail:
                    print(f"    {line.rstrip()}")

    print()
    print(f"{len(jobs) - len(failed)}/{len(jobs)} passed in {time.time() - started:.0f}s"
          + ("" if not failed else f" — failed: {', '.join(failed)}"))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
