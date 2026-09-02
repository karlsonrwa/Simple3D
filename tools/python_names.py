"""Every name the Python half uses must be defined: pyflakes over the package,
the tests and the tools, kept to the findings that are bugs.

    python tools/python_names.py

Why this exists (round 72): two of the moves that split core.py and bend.py
into modules left a name behind - `_open_wire_detail` in an error path of
core, `MIN_ANGLE` inside `_map_strip` - and neither showed. The first is
reached only when a silkscreen contour is open; the second was swallowed by
the `except` that turns any failure of the wrap into a faceted bend, and the
fold suite reported it a full run later. A moved function carries its
dependencies in its head, not in its text, and nothing but a name check sees
the difference.

Only "undefined name", "referenced before assignment" and the redefinitions
are reported: those are defects. Unused imports are not - the package
re-exports on purpose and pyflakes does not read `noqa`.

Needs pyflakes (`pip install pyflakes`); refuses, loudly, when it is missing
rather than passing on nothing.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ["stepbuilder", "tests", "tools"]
DEFECTS = ("undefined name", "referenced before assignment", "redefinition of unused",
           "undefined local", "is assigned to but never used")


def main() -> int:
    try:
        done = subprocess.run([sys.executable, "-m", "pyflakes", *TARGETS],
                              capture_output=True, text=True, cwd=str(ROOT))
    except OSError as exc:
        print(f"could not run pyflakes: {exc}")
        return 2
    if "No module named pyflakes" in done.stderr:
        print("pyflakes is not installed for", sys.executable)
        print("    pip install pyflakes")
        print("This check ran on NOTHING and is therefore a failure, not a pass.")
        return 2
    lines = (done.stdout + done.stderr).splitlines()
    findings = [l for l in lines if any(d in l for d in DEFECTS)]
    scanned = sum(1 for t in TARGETS for _ in (ROOT / t).rglob("*.py"))
    print(f"pyflakes over {scanned} files in {', '.join(TARGETS)}")
    for line in findings:
        print("  " + line.strip())
    print("no undefined names" if not findings else f"{len(findings)} finding(s)")
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
