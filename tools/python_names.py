"""Every name the Python half uses must be defined: pyflakes over the package,
the tests and the tools, every finding kept but the one that is no defect here.

    python tools/python_names.py
    python tools/python_names.py --root DIR     the same over another tree

Why this exists (round 72): two of the moves that split core.py and bend.py
into modules left a name behind - `_open_wire_detail` in an error path of
core, `MIN_ANGLE` inside `_map_strip` - and neither showed. The first is
reached only when a silkscreen contour is open; the second was swallowed by
the `except` that turns any failure of the wrap into a faceted bend, and the
fold suite reported it a full run later. A moved function carries its
dependencies in its head, not in its text, and nothing but a name check sees
the difference.

Everything pyflakes says is a finding except "imported but unused": the
package re-exports on purpose and pyflakes does not read `noqa`. A syntax
error, an assert that is always true, a dict key given twice, `is` with a
literal, a % format that does not fit, a name that may come from a star
import - each is reported, and so is a pyflakes that ends otherwise than with
0 or 1. Until round 132 only five kinds were kept and the exit code was not
read: a syntax error in a file no suite imports passed run_all green, and so
did an assert of a tuple (review 23.10.2026, R7-15). On the tree that round
pyflakes said 111 things, all "imported but unused".

Needs pyflakes (`pip install pyflakes`); refuses, loudly, when it is missing
rather than passing on nothing.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ["stepbuilder", "tests", "tools"]
HARMLESS = ("imported but unused",)


def main(argv: list | None = None) -> int:
    p = argparse.ArgumentParser(description="pyflakes over the Python half, defects only.")
    p.add_argument("--root", default=str(ROOT), help="the tree to check (default: this repository)")
    root = Path(p.parse_args(argv).root).resolve()
    targets = [t for t in TARGETS if (root / t).is_dir()]
    try:
        done = subprocess.run([sys.executable, "-m", "pyflakes", *targets],
                              capture_output=True, text=True, cwd=str(root))
    except OSError as exc:
        print(f"could not run pyflakes: {exc}")
        return 2
    if "No module named pyflakes" in done.stderr:
        print("pyflakes is not installed for", sys.executable)
        print("    pip install pyflakes")
        print("This check ran on NOTHING and is therefore a failure, not a pass.")
        return 2
    lines = (done.stdout + done.stderr).splitlines()
    findings = [line for line in lines if line.strip() and not any(h in line for h in HARMLESS)]
    if done.returncode not in (0, 1):
        findings.append(f"pyflakes itself ended with exit code {done.returncode}")
    scanned = sum(1 for t in targets for _ in (root / t).rglob("*.py"))
    print(f"pyflakes over {scanned} files in {', '.join(targets)}")
    for line in findings:
        print("  " + line.rstrip())
    print("no undefined names" if not findings else f"{len(findings)} finding(s)")
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
