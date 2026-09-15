# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, fails, check, exporter_source

"""Every Python copy of a SKILL procedure, pinned to the procedure it copies.

Half the product is SKILL and no test runs it. What the suites test instead
are the Python transliterations in `tests/skill_transliterations.py`, and that
is worth exactly as much as the link between the copy and the original. The
audit of 2026-09-15 measured the link and found it absent: of five semantic
mutations made in `skill/`, four passed the whole suite unnoticed
(docs/test-audit.md, finding 3) -

    s3dLayerIsNegative  `neg = t` -> `neg = nil`  (nothing is negative)
    s3dDrillXY          the drill offset applied with the opposite sign
    s3dBoxesMeet        the separating-axis result inverted
    s3dJsonMerge        the recursive branch replaced by "take the whole value"
    s3dJsonQuote        the control-character branch deleted

The two that WERE caught show the pattern this suite copies: test_launcher [6]
pulls every `--flag` out of the .il with a regex and asks the real parser
whether it knows them, and tools/skill_checks.py catches a call to a procedure
defined nowhere. One assertion at the seam, and the whole seam holds.

So: for each copied procedure, the statements that carry its meaning are read
out of the SKILL source and compared - character for character after comments
and layout are normalised away - with what is written here. An edit to the
.il that changes the meaning changes those statements, and this suite says
which procedure drifted from its copy. Where the meaning can be DERIVED from
the source rather than matched (the control-character class, the sign of the
drill offset) it is derived and run against the Python, which is stronger
still.

[6] closes the loop the other way: every `# mirrors` line in
skill_transliterations.py has to name a procedure that exists, and every
procedure named there has to be pinned below, so a copy added without a pin
fails here rather than silently going unwatched.
"""
import json
import re
import sys

import skill_transliterations as T

IL = exporter_source()


def body(name):
    """One procedure's text, to the start of the next top-level procedure."""
    m = re.search(r"^procedure\( " + re.escape(name) + r"\(.*?(?=^procedure\()",
                  IL, re.S | re.M)
    if not m:
        return None
    return m.group(0)


def normalise(text):
    """Comments out, runs of whitespace to one space - so that reindenting a
    procedure or rewording a comment does not fail this suite, and changing
    what it computes does."""
    out = []
    for line in text.splitlines():
        line = re.sub(r";.*$", "", line)
        line = " ".join(line.split())
        if line:
            out.append(line)
    return " ".join(out)


PINNED = {}       # procedure -> the statements this suite pins


def pin(proc, *statements):
    """Every statement must appear, exactly once, in that procedure."""
    PINNED[proc] = statements
    text = body(proc)
    if text is None:
        check(f"{proc} is in the SKILL source", False, "procedure not found")
        return
    flat = normalise(text)
    for statement in statements:
        want = normalise(statement)
        n = flat.count(want)
        check(f"{proc}: {want[:88]}", n == 1,
              f"found {n} times" if n != 1 else "")


print("\n[1] s3dLayerIsNegative - what makes a layer negative")

# `neg` starts nil and the ONLY thing that sets it is a key matching the
# probe. `neg = nil` in place of `neg = t` makes every layer positive, which
# is a board with no coverlay openings and no soldermask - and test_neg.py's
# fourteen assertions never saw it, because they were asking a copy of this
# written three lines above them.
pin("s3dLayerIsNegative",
    'probe = ""',
    'when( stringp( fn )  probe = upperCase( fn ) )',
    'when( stringp( nm )  probe = strcat( probe " " upperCase( nm ) ) )',
    'for( i 1 (strlen( probe ) - strlen( key ) + 1)',
    'when( substring( probe i strlen( key ) ) == upperCase( key ) neg = t )')

neg_body = normalise(body("s3dLayerIsNegative") or "")
check("the only assignment to neg is `neg = t`",
      re.findall(r"neg = (\w+)", neg_body) == ["t"],
      re.findall(r"neg = (\w+)", neg_body))
check("and it starts nil", "( neg nil )" in neg_body, neg_body[:120])

# The keys themselves, read out of the SKILL rather than restated here.
default = re.search(r"S3D_NegativeLayersDefault = list\(([^)]*)\)", IL)
check("the default key list is in the SKILL source", bool(default),
      IL[IL.find("S3D_NegativeLayers"):][:80])
if default:
    keys = re.findall(r'"([^"]+)"', default.group(1))
    check(f"the copy carries the same default keys {keys}",
          T.NEGATIVE_LAYER_KEYS == keys, (T.NEGATIVE_LAYER_KEYS, keys))

# The copy, run on the same names the SKILL would see.
check("the copy calls a coverlay negative", T.s3d_layer_is_negative("COVERLAY_TOP"))
check("the copy calls a stiffener positive", not T.s3d_layer_is_negative("STIFFENER_TOP"))
check("the copy reads the layer function too",
      T.s3d_layer_is_negative("MASK_7", "Coverlay"))
check("and an empty key list makes nothing negative",
      not T.s3d_layer_is_negative("COVERLAY_TOP", None, []))

print("\n[2] s3dDrillXY and rotateXY - where the hole is")

pin("s3dDrillXY",
    'dx = 0.0',
    'dy = 0.0',
    'when( numberp( xCoord( offset ) )  dx = xCoord( offset ) )',
    'when( numberp( yCoord( offset ) )  dy = yCoord( offset ) )',
    'unless( numberp( rotation )  rotation = 0.0 )',
    'if( (dx == 0.0) && (dy == 0.0) then',
    'rotateXY( xy list( xCoord( xy ) + dx  yCoord( xy ) + dy ) rotation )')

pin("rotateXY",
    'dX = xCoord( xy ) - xCoord( origin )',
    'dY = yCoord( xy ) - yCoord( origin )',
    'x = xCoord( origin ) + xCoord( dXY ) * cos( angleRad ) - yCoord( dXY ) * sin( angleRad )',
    'y = yCoord( origin ) + xCoord( dXY ) * sin( angleRad ) + yCoord( dXY ) * cos( angleRad )')

# Derived, not matched: the two operators that join the pad to the offset are
# read out of the SKILL and the copy is run to see whether it agrees. This is
# the mutation that passed - the offset applied backwards - and it needs no
# knowledge of what the right answer is, only that both sides say the same.
m = re.search(r"rotateXY\( xy list\( xCoord\( xy \) ([-+]) dx\s+"
              r"yCoord\( xy \) ([-+]) dy \) rotation \)", normalise(body("s3dDrillXY") or ""))
check("the SKILL joins pad and offset with two readable operators", bool(m),
      normalise(body("s3dDrillXY") or "")[-120:])
if m:
    sx, sy = (1.0 if m.group(1) == "+" else -1.0), (1.0 if m.group(2) == "+" else -1.0)
    pad, off = [10.0, 20.0], [0.375, 0.25]
    got = T.s3dDrillXY(pad, 0.0, off)
    want = [pad[0] + sx * off[0], pad[1] + sy * off[1]]
    check(f"the copy applies the offset the way the SKILL does "
          f"({m.group(1)}dx, {m.group(2)}dy)",
          abs(got[0] - want[0]) < 1e-12 and abs(got[1] - want[1]) < 1e-12,
          (got, want))

print("\n[3] s3dBoxesMeet - the separating axis")

pin("s3dBoxesMeet",
    'if( !l_a || !l_b then t',
    '!( (ax1 < bx0) || (bx1 < ax0) || (ay1 < by0) || (by1 < ay0) )')

# Derived again: the four comparisons are read out of the SKILL and evaluated
# here, against the copy, on boxes that separate on each axis in turn and on
# boxes that touch. An inverted result on either side is a disagreement.
meet = normalise(body("s3dBoxesMeet") or "")
expr = re.search(r"!\( \(ax1 < bx0\) \|\| \(bx1 < ax0\) \|\| \(ay1 < by0\) \|\| \(by1 < ay0\) \)", meet)
check("the separating-axis test is the one the copy mirrors", bool(expr), meet[-160:])
CASES = [(((0, 0), (1, 1)), ((2, 2), (3, 3)), False),      # apart in x and y
         (((0, 0), (1, 1)), ((2, 0), (3, 1)), False),      # apart in x only
         (((0, 0), (1, 1)), ((0, 2), (1, 3)), False),      # apart in y only
         (((0, 0), (1, 1)), ((1, 1), (2, 2)), True),       # touching at a corner
         (((0, 0), (2, 2)), ((1, 1), (3, 3)), True),       # overlapping
         (((0, 0), (4, 4)), ((1, 1), (2, 2)), True),       # one inside the other
         (None, ((1, 1), (2, 2)), True)]                   # no box: let the AND decide
for a, b, want in CASES:
    check(f"boxes {a} and {b} {'meet' if want else 'do not meet'}",
          T.s3dBoxesMeet(a, b) == want, T.s3dBoxesMeet(a, b))
check("and the answer is symmetric",
      all(T.s3dBoxesMeet(a, b) == T.s3dBoxesMeet(b, a) for a, b, _ in CASES))

print("\n[4] s3dJsonMerge - a local config overrides key by key, not wholesale")

pin("s3dJsonMerge",
    'unless( s3dJsonIsObj( g_over ) && s3dJsonIsObj( g_base ) return( g_over ) )',
    's3dJsonMerge( cadr( entry ) cadr( hit ) ) ) out )',
    "return( list( 'jobj reverse( out ) ) )")

merge_body = normalise(body("s3dJsonMerge") or "")
check("the merge calls itself - it is recursive, not a replacement",
      merge_body.count("s3dJsonMerge(") == 2,      # its own header, and the call
      merge_body.count("s3dJsonMerge("))

# What recursion buys, stated as behaviour: a local file that sets ONE key of
# a nested object leaves the object's other keys alone. Flatten the merge and
# this is what breaks, silently, in whatever the user did not re-state.
base = {"silk": {"top": True, "bottom": True, "flat": False}, "pads": True}
over = {"silk": {"flat": True}}
merged = T.skill_merge(base, over)
silk = merged.get("silk") or {}
# .get(), not [...]: a merge that replaced the nested object wholesale
# leaves the sibling keys absent, and a KeyError here would end the suite
# instead of naming which key went missing.
check("the overridden key changes", silk.get("flat") is True, merged)
check("its siblings survive",
      silk.get("top") is True and silk.get("bottom") is True, merged)
check("and untouched top-level keys survive", merged.get("pads") is True, merged)
check("a scalar over an object replaces it whole",
      T.skill_merge({"a": {"b": 1}}, {"a": 2}).get("a") == 2)
check("a key only the override has is added",
      T.skill_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2})

print("\n[5] s3dJsonQuote - one control character must not cost the whole file")

pin("s3dJsonQuote",
    '( c == "\\"" "\\\\\\"" )',
    '( c == "\\\\" "\\\\\\\\" )',
    '( c == "\\t" "\\\\t" )',
    '( c == "\\n" "\\\\n" )',
    '( c == "\\r" "\\\\r" )',
    '( scan && pcreMatchp( pattern c ) " " )',
    '( t c )')

quote_body = normalise(body("s3dJsonQuote") or "")
check("the control-character branch is still in the cond",
      "pcreMatchp( pattern c )" in quote_body, quote_body[-200:])

# Derived: the character class is read out of s3dCtrlCharPattern and turned
# into a Python predicate, then compared with the copy's `_is_other_control`
# over every code point it can see. Nothing here restates which characters
# those are - the .il says so.
pat = re.search(r'pcreCompile\( "\[([^"]*)\]" \)', IL)
check("the control-character class is in the SKILL source", bool(pat),
      IL[IL.find("pcreCompile"):][:80] if "pcreCompile" in IL else "no pcreCompile")
if pat:
    ranges = re.findall(r"\\\\x([0-9a-fA-F]{2})-\\\\x([0-9a-fA-F]{2})|\\\\x([0-9a-fA-F]{2})",
                        pat.group(1))
    wanted = set()
    for lo, hi, single in ranges:
        if single:
            wanted.add(int(single, 16))
        else:
            wanted.update(range(int(lo, 16), int(hi, 16) + 1))
    check(f"it names {len(wanted)} code points", len(wanted) > 0, pat.group(1))
    disagree = [n for n in range(0, 0x80)
                if T._is_other_control(chr(n)) != (n in wanted)]
    check("the copy's predicate is the SKILL's character class, code point for "
          "code point", not disagree, [hex(n) for n in disagree])
    check("and the three with a spelling of their own are outside it",
          not ({0x09, 0x0a, 0x0d} & wanted), sorted(wanted & {0x09, 0x0a, 0x0d}))

check('a quote is escaped', T.s3dJsonQuote('a"b') == '"a\\"b"', T.s3dJsonQuote('a"b'))
check('a backslash is escaped', T.s3dJsonQuote("a\\b") == '"a\\\\b"', T.s3dJsonQuote("a\\b"))
check("a tab, newline and return keep their own spelling",
      T.s3dJsonQuote("a\tb\nc\rd") == '"a\\tb\\nc\\rd"', T.s3dJsonQuote("a\tb\nc\rd"))
check("any other control character becomes a space",
      T.s3dJsonQuote("a\x01b\x1fc") == '"a b c"', T.s3dJsonQuote("a\x01b\x1fc"))
check("a non-string is null", T.s3dJsonQuote(7) == "null")

print("\n[6] every copy is pinned, and pins something that exists")

# The loop the audit's finding is really about: a transliteration added later
# with no pin is a procedure nobody is watching, and nothing would say so.
#
# Read from the `# mirrors` lines, which carry one machine-readable form:
#     # mirrors skill/<file>.il: proc[, proc ...][; skill/<file>.il: ...]  -- prose
# Prose goes after the "  -- ", so what precedes it is names and nothing else.
src = (ROOT / "tests" / "skill_transliterations.py").read_text(encoding="utf-8")
named = set()
malformed = []
for line in src.splitlines():
    if not line.startswith("# mirrors "):
        continue
    spec = line[len("# mirrors "):].split("  -- ")[0]
    for segment in spec.split(";"):
        segment = segment.strip()
        m = re.match(r"skill/\S+\.il:\s*(.+)$", segment)
        if not m:
            continue                     # a line naming no procedure of ours
        for proc in m.group(1).split(","):
            proc = proc.strip()
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", proc):
                named.add(proc)
            else:
                malformed.append(proc)

check("every `# mirrors` line names bare procedures, so this can be read at all",
      not malformed, malformed)
check(f"the copies name {len(named)} SKILL procedures", len(named) >= 15, sorted(named))
missing = sorted(p for p in named if body(p) is None)
check("every procedure a copy names exists in the SKILL source", not missing, missing)

# The five the audit measured, plus rotateXY which s3dDrillXY is built on.
MUST_PIN = {"s3dLayerIsNegative", "s3dDrillXY", "rotateXY", "s3dBoxesMeet",
            "s3dJsonMerge", "s3dJsonQuote"}
check("every procedure the audit found unpinned is pinned here",
      MUST_PIN <= set(PINNED), sorted(MUST_PIN - set(PINNED)))
check(f"and every pin found its procedure ({len(PINNED)} pinned)",
      all(body(p) is not None for p in PINNED),
      [p for p in PINNED if body(p) is None])

print("\n[7] and each copy against the original's own answers")

# The pins above read the SKILL; this runs it. tools/probes/probe_translit.il
# calls the five procedures in a real headless Allegro over a fixed list of
# cases, and tools/skill_answers.py turns that run into
# tests/fixtures/skill_answers.json - the same kind of oracle as
# pads_demo.json, and the only place in this repository where the SKILL side's
# own answers are recorded. Measured 2026-09-15 on Allegro 25.1 against
# demo/demo.brd, which is only what gives the interpreter a session: none of
# the five procedures reads the design.
#
# The fixture goes stale silently if the .il changes - that is what [1] to [5]
# are for. The two together are the pin: [1]-[5] say the source still computes
# what it computed, [7] says the copy computes what the source answered.

ANSWERS = json.loads((ROOT / "tests/fixtures/skill_answers.json").read_text(encoding="utf-8"))


def ask_copy(procedure, inputs):
    """The Python copy's answer, shaped like the SKILL's."""
    if procedure == "s3dLayerIsNegative":
        keys = inputs["keys"]
        got = (T.s3d_layer_is_negative(inputs["name"], inputs["func"])
               if keys is None else
               T.s3d_layer_is_negative(inputs["name"], inputs["func"], keys))
        return True if got else None          # SKILL answers t or nil
    if procedure == "s3dDrillXY":
        return list(T.s3dDrillXY(inputs["pin_xy"], inputs["rotation"], inputs["offset"]))
    if procedure == "s3dBoxesMeet":
        a = [tuple(p) for p in inputs["a"]] if inputs["a"] else inputs["a"]
        b = [tuple(p) for p in inputs["b"]] if inputs["b"] else inputs["b"]
        return True if T.s3dBoxesMeet(a, b) else None
    if procedure == "s3dJsonQuote":
        return T.s3dJsonQuote(inputs["value"])
    if procedure == "s3dJsonMerge":
        merged = T.skill_merge(inputs["base"], inputs["over"])
        node, path = merged, inputs["path"]
        for step in path[:-1]:
            node = node.get(step, {}) if isinstance(node, dict) else {}
        last = path[-1]
        if inputs["ask"] == "present":
            return True if isinstance(node, dict) and last in node else None
        value = node.get(last) if isinstance(node, dict) else None
        # s3dJsonGet cannot tell a JSON false from a missing key: both are nil.
        # The copy is asked the same question, so it must answer the same way.
        return None if value is False or value is None else value
    raise AssertionError(f"no copy wired up for {procedure}")


def same(got, want):
    if isinstance(want, list) and isinstance(got, list):
        return len(got) == len(want) and all(
            abs(float(g) - float(w)) < 1e-6 for g, w in zip(got, want))
    if isinstance(want, float) and isinstance(got, (int, float)):
        return abs(got - want) < 1e-9
    return got == want


check(f"the fixture carries {len(ANSWERS['cases'])} answers from Allegro's own "
      f"interpreter", len(ANSWERS["cases"]) >= 50, len(ANSWERS["cases"]))
by_proc = {}
for case in ANSWERS["cases"]:
    by_proc.setdefault(case["procedure"], []).append(case)
check("and covers every procedure pinned above",
      set(by_proc) >= (MUST_PIN - {"rotateXY"}), sorted(set(by_proc)))

for procedure in sorted(by_proc):
    wrong = []
    for case in by_proc[procedure]:
        got = ask_copy(procedure, case["inputs"])
        if not same(got, case["answer"]):
            wrong.append(f"{case['case']}: copy {got!r}, Allegro {case['answer']!r}")
    check(f"{procedure}: the copy answers as Allegro did on all "
          f"{len(by_proc[procedure])} cases", not wrong, wrong[:4])

# The probe says what it could not exercise, and that is part of the record:
# a control character other than tab/newline/return can only be got into a
# SKILL string through the \b and \f escapes here (sprintf "%c" is not
# available), so those two are what ran, and they did take the branch.
check("the run records what it could not exercise",
      isinstance(ANSWERS.get("skipped"), list), type(ANSWERS.get("skipped")))
ctrl = [c for c in by_proc.get("s3dJsonQuote", []) if "control" in c["case"]]
check(f"the control-character branch was still exercised ({len(ctrl)} cases)",
      len(ctrl) >= 2 and all(c["answer"] == '"a b"' for c in ctrl),
      [(c["case"], c["answer"]) for c in ctrl])

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
