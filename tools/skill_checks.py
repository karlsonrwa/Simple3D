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

"""Six mechanical checks on the Simple3D SKILL sources (see round 14b notes):
  1. parenthesis balance (per file)
  2. string literals broken across a real newline
  3. calls to project-shaped procedures that are defined nowhere
  4. prog() locals written in let's (var value) form, which prog rejects at
     CALL time - so the file loads clean and the procedure dies when used
  5. an assignment inside a procedure to a name it never declared (round
     75, plan D1): SKILL is dynamically scoped, so such a name lands in
     the nearest caller that has it, or becomes a session global
  6. a format string that is not the author's own text (round 100): data
     used as the format of printf, fprintf, sprintf, error and the like
     turns a % in a name into a conversion

Strings and ; comments are stripped before paren/call analysis so that parens or
names inside them do not count.
"""
import re, sys
from pathlib import Path

from skill_lex import balanced_end, strip_line_comment, strip_strings  # noqa: E402 - tools/ is on sys.path when run from here

FILES = [
    str(_ROOT / "makeVariant3dIntermediates.il"),
    str(_ROOT / "simple3d.il"),
    # The exporter's nine parts (round 76, D6); the file above is their loader.
    *sorted(str(q) for q in (_ROOT / "skill").glob("s3d_*.il")),
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


# ---- check 5: assignments to names a procedure never declared ------------- #
#
# SKILL has no lexical scope. A name assigned inside a procedure is local ONLY
# if it is a parameter or in a let/prog/letseq list; otherwise the assignment
# lands in the nearest caller up the DYNAMIC chain that has that name, or
# creates a session global that outlives the export. The exporter carried 21
# such names for years (round 70's review listed them; ARCHITECTURE.md 4.1);
# none was read afterwards, which is the only reason it was not a bug - and
# makePcb assigned `pcbColor`, its caller's parameter name. Nothing else here
# could see that: the other checks compare calls with definitions, not
# assignments with declarations.

IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
# `name =` that is an assignment: not `==` (the lookahead), not `!=`/`<=`/`>=`
# (the character before `=` is then not the name), not `obj->attr =` (a `>`
# right before the name), not `tbl[key] =` (a `]` before the `=`).
ASSIGN_RE = re.compile(rf"(?<![\w>])({IDENT})\s*=(?!=)")
# Forms that bind a name without a let: the loop variable of foreach/for/
# forall/setof/exists, and `foreach( mapcar x ...)`.
BINDER_RE = re.compile(rf"\b(?:foreach|for|forall|setof|exists)\(\s*(?:(?:mapcar|mapc|mapcan|maplist)\s+)?({IDENT})")
SCOPE_RE = re.compile(r"\b(?:let|prog|letseq|lambda)\(\s*\(")
PROC_RE = re.compile(rf"\bprocedure\(\s*({IDENT})\s*\(")
GLOBAL_PREFIX = "S3D_"          # the project's declared session globals


def names_in_list(group):
    """The names a binding list declares: bare symbols and the heads of
    (sym value) forms. `@optional ( x 1 )` and `@key`/`@rest` read the same
    way; the @-words themselves are dropped by the caller."""
    out = set()
    inner = group.strip()[1:-1]
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch == "(":
            j = balanced_end(inner, i)
            m = re.match(rf"\(\s*({IDENT})", inner[i:j])
            if m:
                out.add(m.group(1))
            i = j
        else:
            m = re.match(IDENT, inner[i:])
            if m:
                out.add(m.group(0))
                i += len(m.group(0))
            else:
                i += 1
    return out


def check_undeclared(nostr):
    """[(line, procedure, name)] for each assignment to an undeclared name.

    *nostr* is the source with comments and strings removed. Declared means:
    a parameter, a name in any let/prog/letseq/lambda list of the procedure
    (nesting is not tracked - a name declared in an inner let counts for the
    whole body, which errs on the quiet side), a loop binder, or a project
    global (S3D_*). gets(name port) is an assignment too and is reported like
    one.
    """
    problems = []
    for m in PROC_RE.finditer(nostr):
        proc = m.group(1)
        head_start = m.end() - 1
        head_end = balanced_end(nostr, head_start)
        declared = names_in_list(nostr[head_start:head_end]) - {"optional", "key", "rest"}
        body_end = balanced_end(nostr, m.start() + len("procedure"))
        body = nostr[head_end:body_end]
        for sm in SCOPE_RE.finditer(body):
            g = sm.end() - 1
            declared |= names_in_list(body[g:balanced_end(body, g)])
        declared |= set(BINDER_RE.findall(body))
        targets = [(am.start(), am.group(1)) for am in ASSIGN_RE.finditer(body)]
        targets += [(gm.start(), gm.group(1)) for gm in re.finditer(rf"\bgets\(\s*({IDENT})", body)]
        for pos, name in sorted(targets):
            if name in declared or name.startswith(GLOBAL_PREFIX) or name in ("t", "nil"):
                continue
            line = nostr.count("\n", 0, head_end + pos) + 1
            problems.append((line, proc, name))
    return problems


# Check 6 (round 100): a format is the author's text, never the board's.
# printf, fprintf, sprintf, lsprintf, info, warn and error read their format
# for % conversions, and so do axlUIWPrint and axlMsgPut; text built from the
# board's data - a model, zone, layer or variant name, a path - used as the
# format turns a % in it into a conversion. Measured in Allegro 25.1 on
# 25.10.2026 (finding R1-1 of the 23.10 review): a variant named "BOM 100%"
# stopped the JSON writer at its third line ("*Error* fprintf/sprintf:
# illegal format spec."), and "R_1%%" came out as "R_1%". Data goes in as a
# %s argument. A constant format - a literal, a strcat of literals, an if
# whose branches are - is the author's own and passes.
FORMAT_ARG = {"printf": 0, "lsprintf": 0, "info": 0, "warn": 0, "error": 0, "axlMsgPut": 0,
              "fprintf": 1, "sprintf": 1}
# A procedure that takes a format as a parameter by contract: inside it that
# parameter may be the format, and its callers must pass a constant there
# (the argument's index counts from 0).
FORMAT_PARAMS = {"s3dSelectVisibleOn": ("t_missingFmt", 2)}
_STRING = re.compile(r'"(\\.|[^"\\])*"')
# The paren follows the name directly: `info ( n 0 )` in a let list is a
# variable and a binding, not a call.
_FORMAT_CALL = re.compile(r"(?<![\w>-])(" + "|".join([*FORMAT_ARG, "axlUIWPrint", *FORMAT_PARAMS])
                          + r")\(")


def _constant_format(arg):
    """Whether *arg* (literals masked as '"<n>"') can only ever be the author's text."""
    from check_arity import split_top_level  # noqa: E402 - the argument splitter lives there

    arg = arg.strip()
    if arg.startswith('"'):
        return True
    m = re.fullmatch(r"(strcat|if)\((.*)\)", arg, re.S)
    if not m:
        return False
    parts = split_top_level(m.group(2))
    if m.group(1) == "strcat":
        return bool(parts) and all(_constant_format(p) for p in parts)
    if "then" not in parts:                       # if( cond then a else b ): the branches make it
        return False
    branches = [p for p in parts[parts.index("then") + 1:] if p != "else"]
    return bool(branches) and all(_constant_format(p) for p in branches)


def check_formats(code):
    """[(line, call)] for every format that is not constant, in *code* - the
    source with comments removed and strings still in it."""
    from check_arity import split_top_level  # noqa: E402

    lits = []

    def mask(m):
        lits.append(m.group(0))
        return f'"{len(lits) - 1}"'
    masked = _STRING.sub(mask, code)
    allowed = {param for param, _ in FORMAT_PARAMS.values()}
    problems = []
    for m in _FORMAT_CALL.finditer(masked):
        name = m.group(1)
        open_paren = m.end() - 1
        args = split_top_level(masked[open_paren + 1:balanced_end(masked, open_paren) - 1])
        if name in FORMAT_ARG:
            fmt = args[FORMAT_ARG[name]] if len(args) > FORMAT_ARG[name] else None
        elif name in FORMAT_PARAMS:
            index = FORMAT_PARAMS[name][1]
            fmt = args[index] if len(args) > index else None
        else:                                     # axlUIWPrint( form [level] format args )
            rest = args[1:]
            fmt = rest[0] if rest and _constant_format(rest[0]) else (rest[1] if len(rest) > 1 else None)
        if fmt is None or fmt in allowed or _constant_format(fmt):
            continue
        shown = re.sub(r'"(\d+)"', lambda k: lits[int(k.group(1))], fmt)
        problems.append((masked.count("\n", 0, m.start()) + 1, f"{name}( ... {' '.join(shown.split())[:80]} ... )"))
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
    undeclared = check_undeclared(nostr)
    formats = check_formats(nocomment)
    return text, bal, broken, defs, calls, progs, undeclared, formats

def report(path, bal, broken, calls, known, progs=(), undeclared=(), formats=()):
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

    if undeclared:
        ok = False
        print("  assignments to names the procedure never declared (they leak):")
        by_proc = {}
        for n, proc, name in undeclared:
            by_proc.setdefault(proc, []).append(f"{name} (line {n})")
        for proc, items in by_proc.items():
            print(f"    {proc}: {', '.join(items)}")
    else:
        print("  undeclared assignments: none")

    if formats:
        ok = False
        print("  formats that are not the author's own text (a % in the data becomes a conversion):")
        for n, call in formats:
            print(f"    line {n}: {call}")
    else:
        print("  formats: all constant")
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
    # Check 5, the same way: a leak it must see, and every legal form it
    # must not mistake for one.
    leak = ("procedure( f( a )\n    let( ( b )\n        c = a + b\n        obj->w = 1\n"
            "        while( gets( line port ) nil )\n    )\n)")
    found = {name for _, _, name in check_undeclared(strip_strings(leak))}
    if found != {"c", "line"}:
        problems.append(f"the undeclared check sees {sorted(found)}, not c and line")
    clean = ("procedure( g( a @optional ( d 1 ) @key e )\n"
             "    let( ( b ( c nil ) )\n"
             "        c = a + b\n        d = 2\n        e = 3\n"
             "        foreach( x lst x = 1 )\n        for( i 1 3 i = 0 )\n"
             "        S3D_Flag = t\n        obj->w = 1\n        tbl[a] = 1\n"
             "        if( a == b || a != c || a >= d || a <= e then t )\n"
             "        prog( ( r ) r = 1 return( r ) )\n"
             "        mapcar( lambda( ( q ) q = 1 ) lst )\n    )\n)")
    wrong = check_undeclared(strip_strings(clean))
    if wrong:
        problems.append(f"the undeclared check fires on declared names: {wrong}")
    # Check 6, the same way: the forms that carry the board's text into a
    # format, and every constant form it must let pass.
    fmt_bad = ('fprintf( port strcat( "\\t" line ) )\n'
               'error( strcat( sprintf( nil "%s\\n" path ) "the rest" ) )\n'
               's3dSelectVisibleOn( layers filter fmt )\n'
               'printf( name )\n')
    found = [call.split("(")[0] for _, call in check_formats(fmt_bad)]
    if found != ["fprintf", "error", "s3dSelectVisibleOn", "printf"]:
        problems.append(f"the format check sees {found}, not fprintf, error, s3dSelectVisibleOn and printf")
    fmt_good = ('fprintf( port "\\t%s\\n" line )\n'
                'printf( "a %d\\n" n )\n'
                'axlUIWPrint( nil s_level "%s" msg )\n'
                "axlUIWPrint( nil 'warn \"%s\" msg )\n"
                'axlUIWPrint( nil "%s" msg )\n'
                'sprintf( nil t_missingFmt layer )\n'
                's3dSelectVisibleOn( layers filter "no layer %s" )\n'
                'fprintf( port if( more then "\\t},\\n" else "\\t}\\n" ) )\n'
                'error( strcat( "one, " "two\\n" ) )\n'
                'let( ( info ( n 0 ) ) n )\n')
    wrong = check_formats(fmt_good)
    if wrong:
        problems.append(f"the format check fires on constant formats: {wrong}")
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
        text, bal, broken, defs, calls, progs, undeclared, formats = analyze(f)
        per_file[f] = (bal, broken, calls, progs, undeclared, formats)
        all_defs |= defs

    ok = True
    for f, (bal, broken, calls, progs, undeclared, formats) in per_file.items():
        ok = report(f, bal, broken, calls, all_defs, progs, undeclared, formats) and ok

    for f in PROBES:
        text, bal, broken, defs, calls, progs, undeclared, formats = analyze(f)
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
                # Naming the loader means the parts it loads.
                if Path(f2).name in name or (
                        Path(f2).parent.name == "skill" and "makeVariant3dIntermediates.il" in name):
                    known |= analyze(f2)[3]
        ok = report(f, bal, broken, calls, known, progs, undeclared, formats) and ok

    print()
    print("ALL CHECKS PASS" if ok else "CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
