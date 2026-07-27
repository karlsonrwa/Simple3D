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

"""Three mechanical checks on the Simple3D SKILL sources (see round 14b notes):
  1. parenthesis balance (per file)
  2. string literals broken across a real newline
  3. calls to project-shaped procedures that are defined nowhere

Strings and ; comments are stripped before paren/call analysis so that parens or
names inside them do not count.
"""
import re, sys
from pathlib import Path

FILES = [
    str(_ROOT / "makeVariant3dIntermediates.il"),
    str(_ROOT / "simple3d.il"),
]

# The read-only diagnostics under tools/probes are SKILL too, and a probe with
# an unbalanced paren fails at load - in a live Allegro session, which costs a
# round trip with the user rather than a test run. Each is loaded on its own,
# so each is checked against its OWN definitions; pooling them with the shipped
# files would let a probe's procedure satisfy a call in the exporter.
PROBES = sorted(str(p) for p in (_ROOT / "tools" / "probes").glob("*.il"))

# project-shaped call prefixes we own and must have defined
PROJECT_RE = re.compile(r"^(s3d|make|add|symbolReturn|gdsys|create3d|calculateBoard|boardGeometry)")

# SKILL builtins that happen to match a project-shaped prefix but are not ours
BUILTIN_ALLOW = {"makeTable", "makeVector", "makeString", "makeInstance",
                 "makeSymbol", "makeList"}

def strip_line_comment(line):
    """Remove a ; comment, respecting string literals on that line."""
    out, in_str, esc = [], False, False
    for ch in line:
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == ";":
                break
            if ch == '"':
                in_str = True
            out.append(ch)
    return "".join(out)

def check_broken_strings(path, text):
    """Flag a " that opens on one line and does not close on the same line."""
    problems = []
    for n, line in enumerate(text.splitlines(), 1):
        in_str, esc = False, False
        for ch in line:
            if in_str:
                if esc: esc = False
                elif ch == "\\": esc = True
                elif ch == '"': in_str = False
            else:
                if ch == '"': in_str = True
        if in_str:
            problems.append((n, line.rstrip()))
    return problems

def strip_strings(code):
    """Replace "..." literals with spaces, keeping length-ish neutrality."""
    return re.sub(r'"(\\.|[^"\\])*"', '""', code)

def analyze(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    # code with comments and strings removed, for parens + calls
    nocomment = "\n".join(strip_line_comment(l) for l in text.splitlines())
    nostr = strip_strings(nocomment)

    bal = nostr.count("(") - nostr.count(")")

    # run the broken-string check on comment-stripped lines: a " inside a ;
    # comment is prose, not an unterminated literal.
    broken = check_broken_strings(path, nocomment)

    defs = set(re.findall(r"procedure\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", nostr))
    calls = set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", nostr))
    return text, bal, broken, defs, calls

def report(path, bal, broken, calls, known):
    """Print one file's findings; True if it is clean."""
    ok = True
    print(f"=== {Path(path).name} ===")
    print(f"  paren balance: {bal}" + ("" if bal == 0 else "   <-- UNBALANCED"))
    if bal != 0:
        ok = False
    if broken:
        ok = False
        print("  broken string literals:")
        for n, line in broken:
            print(f"    line {n}: {line}")
    else:
        print("  broken string literals: none")

    undef = sorted(c for c in calls
                   if PROJECT_RE.match(c) and c not in known
                   and c not in BUILTIN_ALLOW)
    if undef:
        ok = False
        print("  calls to undefined project procedures:")
        for c in undef:
            print(f"    {c}")
    else:
        print("  undefined project calls: none")
    return ok


def main():
    all_defs = set()
    per_file = {}
    for f in FILES:
        text, bal, broken, defs, calls = analyze(f)
        per_file[f] = (bal, broken, calls)
        all_defs |= defs

    ok = True
    for f, (bal, broken, calls) in per_file.items():
        ok = report(f, bal, broken, calls, all_defs) and ok

    for f in PROBES:
        text, bal, broken, defs, calls = analyze(f)
        # A probe is checked against its OWN definitions, so that a typo in it
        # cannot be satisfied by a procedure in the exporter. One kind of probe
        # legitimately calls into the shipped files - a diagnostic ABOUT the
        # exporter, which would be worthless if it re-implemented what it is
        # meant to be reporting on. It says so with a marker line, and then the
        # shipped definitions are pooled in for it alone:
        #
        #     ; REQUIRES: makeVariant3dIntermediates.il
        #
        # Explicit rather than automatic: the dependency is then visible at the
        # top of the probe, where whoever loads it in Allegro has to read it.
        required = set(re.findall(r"(?im)^\s*;\s*REQUIRES:\s*(.+?)\s*$", text))
        known = set(defs)
        for name in required:
            for f2 in FILES:
                if Path(f2).name in name:
                    known |= analyze(f2)[3]
        ok = report(f, bal, broken, calls, known) and ok

    print()
    print("ALL CHECKS PASS" if ok else "CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
