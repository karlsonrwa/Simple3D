"""Run every check and every test suite. Exit 0 only if all of them pass.

    python tests/run_all.py            everything
    python tests/run_all.py --quick    skip the OCCT-heavy geometry suites

Four of these are mechanical checks on the SKILL sources, and each exists
because something got past the previous ones: parenthesis balance, string
literals broken across a real newline, calls to procedures defined nowhere,
and call arity. Run them after any edit to a .il file - SKILL resolves names
at call time, so a broken file loads without complaint and fails only when
that line executes.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
TESTS = ROOT / "tests"

# (label, script, heavy?) - heavy means it builds real geometry with OCCT
JOBS = [
    ("SKILL: parens, strings, undefined calls", TOOLS / "skill_checks.py", False),
    ("SKILL: call arity",                       TOOLS / "check_arity.py", False),
    ("docs vs code",                            TOOLS / "audit_docs.py", False),
    ("geometry regression (C++ baseline)",      TESTS / "test_regression_geometry.py", True),
    ("board: zones",                            TESTS / "test_zones.py", True),
    ("board: per-layer stackups",               TESTS / "test_layers.py", True),
    ("board: stitching modes",                  TESTS / "test_modes.py", True),
    ("board: plain-board stitching",            TESTS / "test_plain_modes.py", True),
    ("board: soldermask exclusion",             TESTS / "test_nomask.py", True),
    ("board: negative layers",                  TESTS / "test_neg.py", True),
    ("board: duplicated cutouts",               TESTS / "test_dupcuts.py", True),
    ("board: folding flex bends",               TESTS / "test_bend.py", True),
    ("silkscreen",                              TESTS / "test_silk.py", True),
    ("mechanical symbols",                      TESTS / "test_mech.py", True),
    ("embedded models cross-check",             TESTS / "test_embedded.py", True),
    ("STEP folder search path",                 TESTS / "test_index.py", True),
    ("JSON quoting",                            TESTS / "test_quote.py", False),
    ("launcher command shape",                  TESTS / "test_launch_cmd.py", False),
    ("where Variants.lst is looked for",        TESTS / "test_variant_path.py", False),
    ("settings: defaults + the local file",     TESTS / "test_config_merge.py", False),
    ("GUI widgets and config",                  TESTS / "test_gui.py", False),
    ("GUI window placement",                    TESTS / "test_geom.py", False),
]


def main(argv: list[str]) -> int:
    quick = "--quick" in argv
    jobs = [j for j in JOBS if not (quick and j[2])]

    width = max(len(label) for label, _, _ in jobs)
    failed = []
    started = time.time()

    for label, script, _ in jobs:
        if not script.exists():
            print(f"{label:{width}}  MISSING {script.name}")
            failed.append(label)
            continue
        t0 = time.time()
        done = subprocess.run([sys.executable, str(script)],
                              capture_output=True, text=True, cwd=str(ROOT))
        ok = done.returncode == 0
        print(f"{label:{width}}  {'pass' if ok else 'FAIL'}  {time.time() - t0:5.1f}s")
        if not ok:
            failed.append(label)
            # only the failing detail, so a green run stays one screen
            for line in (done.stdout + done.stderr).splitlines():
                if "FAIL" in line or "Error" in line or "error" in line:
                    print(f"    {line.strip()}")

    print()
    print(f"{len(jobs) - len(failed)}/{len(jobs)} passed in {time.time() - started:.0f}s"
          + ("" if not failed else f" — failed: {', '.join(failed)}"))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
