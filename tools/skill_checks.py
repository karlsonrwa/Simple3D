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

"""Four mechanical checks on the Simple3D SKILL sources (see round 14b notes):
  1. parenthesis balance (per file)
  2. string literals broken across a real newline
  3. calls to project-shaped procedures that are defined nowhere
  4. prog() locals written in let's (var value) form, which prog rejects at
     CALL time - so the file loads clean and the procedure dies when used

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
# Standalone .il helpers directly under tools/ are loaded by hand in a live
# Allegro session too, so they get the same treatment as the probes.
PROBES += sorted(str(p) for p in (_ROOT / "tools").glob("*.il"))

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

def check_prog_locals(text, nostr):
    """Flag `prog( ( a (b nil) c )` - an init form in a prog's local list.

    prog takes BARE SYMBOLS; the (var value) form is let-only, and prog rejects
    the whole procedure with "local vars must be symbol". It does so at CALL
    time, so the file loads clean and the procedure fails when it is used -
    and if the caller wrapped it in errset, silently. That is not a theory:
    it cost s3dEnsureAlwaysProp a live round on 2026-08-04, in a file that
    already carried a comment warning about the same trap.

    The scan walks each `prog(` and reads its first balanced group, which is
    the local list; anything opening a paren inside that group is an init form.
    """
    problems = []
    for match in re.finditer(r"\bprog\(", nostr):
        i = match.end()
        while i < len(nostr) and nostr[i].isspace():
            i += 1
        if i >= len(nostr) or nostr[i] != "(":
            continue                       # prog with no locals at all
        depth, start = 0, i
        while i < len(nostr):
            if nostr[i] == "(":
                depth += 1
            elif nostr[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        locals_src = nostr[start + 1:i]
        if "(" in locals_src:
            line = nostr.count("\n", 0, start) + 1
            problems.append((line, " ".join(locals_src.split())[:70]))
    return problems


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
    progs = check_prog_locals(text, nostr)
    return text, bal, broken, defs, calls, progs

def report(path, bal, broken, calls, known, progs=()):
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

    if progs:
        ok = False
        print("  prog() locals that are not bare symbols (let-only syntax):")
        for n, src_ in progs:
            print(f"    line {n}: prog( ({src_} )")
    else:
        print("  prog locals: all bare symbols")
    return ok


def self_test():
    """A check that never fires is a check nobody can trust.

    The prog-locals scan was written after the trap it looks for had already
    escaped once, so it is exercised on both a known-bad and a known-good
    fragment before it is used on anything real.
    """
    bad = "procedure( f()\n    prog( ( a ( found nil ) b )\n        t\n    )\n)"
    good = "procedure( f()\n    prog( ( a found b )\n        found = nil\n    )\n)"
    let_ok = "procedure( f()\n    let( ( a ( found nil ) b )\n        found\n    )\n)"
    problems = []
    if not check_prog_locals(bad, bad):
        problems.append("the prog-locals check does NOT catch (found nil)")
    if check_prog_locals(good, good):
        problems.append("the prog-locals check fires on bare symbols")
    if check_prog_locals(let_ok, let_ok):
        problems.append("the prog-locals check fires on a let, where the form is legal")
    if problems:
        print("SELF-TEST FAILED:")
        for p in problems:
            print("   " + p)
        sys.exit(1)


def main():
    self_test()
    all_defs = set()
    per_file = {}
    for f in FILES:
        text, bal, broken, defs, calls, progs = analyze(f)
        per_file[f] = (bal, broken, calls, progs)
        all_defs |= defs

    ok = True
    for f, (bal, broken, calls, progs) in per_file.items():
        ok = report(f, bal, broken, calls, all_defs, progs) and ok

    for f in PROBES:
        text, bal, broken, defs, calls, progs = analyze(f)
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
        ok = report(f, bal, broken, calls, known, progs) and ok

    print()
    print("ALL CHECKS PASS" if ok else "CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
