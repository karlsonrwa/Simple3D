# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, OUT, fails, check, exporter_source

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
import shutil
import sys

import skill_transliterations as T

IL = exporter_source()


def body(name):
    """One procedure's text, to the start of the next top-level procedure -
    or to the end of the source, for the last one (makeVariant3dIntermediates,
    pinned since round 120)."""
    m = re.search(r"^procedure\( " + re.escape(name) + r"\(.*?(?=^procedure\(|\Z)",
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
    """Every statement must appear, exactly once, in that procedure. A
    procedure pinned in two sections keeps the statements of both."""
    PINNED[proc] = PINNED.get(proc, ()) + statements
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

print("\n[5b] s3dCollectExposed - the decisions of the copper sweep")

# Round 87's fix is a SWEEP, not a procedure a Python copy can run: it reads
# the design. test_pads [8] greps its tokens, and the review of 2026-09-17
# measured what that is worth - `found = nil` (the selection thrown away),
# the box match applied backwards at its call site, and "lines" dropped from
# the find filter all survived every suite while the tokens stayed in place.
# The behaviour is proved by the SKILL golden corpus (tools/skill_export.py
# --check, circle-A0's 24 polygons of copper at 73.832 mm2), which needs
# Allegro; what can run here is the pin on the statements that decide.
pin("s3dCollectExposed",
    'filter = list( "noall" "lines" "clines" "shapes" "pins" "vias" )',
    'when( errset( axlAddSelectAll() t ) found = axlGetSelSet() )',
    'one = s3dCopperPolys( o etch nil s_endCap )',
    'when( s3dBoxesMeet( cadr( entry )->bBox p->bBox )',
    "errset( res = axlPolyOperation( list( cadr( entry ) ) copper 'AND ) t )",
    'if( null( res ) then nFailed = nFailed + 1',
    "errset( bare = axlPolyOperation( list( cadr( entry ) ) copper 'ANDNOT ) t )",
    'when( null( bare ) nFailed = nFailed + 1')
sweep_body = normalise(body("s3dCollectExposed") or "")
check("the sweep never calls the interactive box select",
      "s3dSelectInBox(" not in sweep_body and "axlAddSelectBox(" not in sweep_body)
check("and the selection it takes is the one it asked for, once",
      sweep_body.count("found = axlGetSelSet()") == 1 and sweep_body.count("found = nil") == 1)

print("\n[5b2] a shape as its fill draws it: s3dPolysFromDbid, s3dCopperPolys (round 111)")

# R2-13 of the 28.10.2026 review: `fill` was never read, so a cross-hatched
# shape on a silkscreen or mask layer was converted the way axlPolyFromDB
# converts one by default - "cross-hatch shapes are treated as solid" - and an
# unfilled one would have been converted to its area too, but for the zero
# width Allegro 25.1 gives every unfilled outline. Round 111 measured both
# against Allegro's own artwork of the same figures (tools/silk_artwork.py,
# docs/records/silk-fill-artwork-2026-10-30.md): 16 mm2 of ink where the
# Gerber has 4.87. Both procedures read a design, so no recorded answer can
# stand in for them; the statements that decide are pinned.
pin("s3dPolysFromDbid",
    "errset( fill = o_dbid->fill )",
    "( null( fill ) errset( strokes = o_dbid->segments ) "
    "res = s3dStrokePolys( strokes s_endCap nil ) polys = car( res ) )",
    "( listp( fill ) errset( polys = axlPolyFromDB( o_dbid ?endCapType s_endCap ?xhatch t ) ) )")
silk_poly_body = normalise(body("s3dPolysFromDbid") or "")
unfilled = silk_poly_body.split("( null( fill )", 1)[-1].split("( listp( fill )", 1)[0]
check("an unfilled shape is stroked, never converted whole: its branch holds no "
      "axlPolyFromDB of the shape itself", "axlPolyFromDB( o_dbid" not in unfilled, unfilled[:160])
check("and the fill is asked in that order: unfilled, cross-hatch, then solid",
      0 < silk_poly_body.find("( null( fill )") < silk_poly_body.find("( listp( fill )")
      < silk_poly_body.rfind("( t errset( polys = axlPolyFromDB( o_dbid ?endCapType s_endCap ) ) )"),
      silk_poly_body[-400:])

# The copper under a drawn mask opening is a shape too: a cross-hatched pour
# exposes its hatch lines, not its area.
pin("s3dCopperPolys",
    "errset( hatched = o_obj->fill )",
    "hatched = hatched && listp( hatched )",
    "errset( polys = axlPolyFromDB( o_obj ?window l_window ?xhatch hatched ) )",
    "errset( polys = axlPolyFromDB( o_obj ?xhatch hatched ) )")

print("\n[5b3] a legend object lost in whole or in part is named, in the console and the JSON (round 117)")

# R2-5 of the 23.10.2026 review. axlPolyFromDB answers nil when "it cannot get
# the polys", and every call to it sat in an errset, so an object that came
# back empty left the legend with nothing said: only an error was named, the
# first one alone and on the console only, and the console line for a line
# short of a segment named neither its layer nor its place, nor reached the
# JSON. Allegro 25.1 on a scratch copy of my_test_board2 (s3dProbeLostCases in
# tools/probes/probe_silkfill.il): a path that is one quarter arc of radius 1,
# 2 or 5 database units, 0.3 wide, converts to nothing, whole and per
# segment, and as the corner of an L it drops out of the L. None of the 2000
# legend objects of the nine boards does either; flex3-a0 has one such arc in
# its copper. All of it reads a design, so the source is what is pinned.
pin("s3dStrokePolys",
    "if( g_line2poly then errset( one = axlPolyFromDB( stroke ?endCapType s_endCap ?line2poly t ) ) "
    "else errset( one = axlPolyFromDB( stroke ?endCapType s_endCap ) ) )",
    "if( one then polys = append( polys one ) else empty = cons( list( n stroke ) empty ) )",
    "list( polys reverse( empty ) )")
pin("s3dPolysFromDbid",
    # a line and a vectorised text go stroke by stroke, whole only when no
    # stroke gave anything
    '( o_dbid->objType == "path" errset( strokes = o_dbid->segments ) '
    "res = s3dStrokePolys( strokes s_endCap nil ) polys = car( res ) "
    "unless( polys errset( polys = axlPolyFromDB( o_dbid ?endCapType s_endCap ) ) ) )",
    'noun = "stroke" res = s3dStrokePolys( strokes s_endCap t ) polys = car( res ) '
    "unless( polys errset( polys = axlPolyFromDB( o_dbid ?endCapType s_endCap ) ) )",
    # some strokes and not others: a piece missing, said with its place
    "when( car( res ) && cadr( res ) "
    "s3dReportLoss( g_state s3dStrokesLost( o_dbid noun length( strokes ) cadr( res ) ) ) )")
check("the converter the mask openings and the copper share names no kind of layer in what it says",
      not [s for s in re.findall(r'"[^"]*"', silk_poly_body) if "silkscreen" in s.lower()],
      re.findall(r'"[^"]*"', silk_poly_body))
pin("s3dReportLoss",
    's3dWarn( sprintf( nil "Simple 3D: %s." t_message ) )',
    "when( g_state g_state['silkWarnings] = cons( t_message g_state['silkWarnings] ) )")
# The words that let the reader find the object and judge the stroke: its layer
# and place, the number of each lost stroke and, for a segment, its size.
pin("s3dStrokesLost",
    'sprintf( nil "part missing: %s - %d of its %d %s(s) gave no polygon and %s left out: %s" '
    "s3dDescribeObject( o_dbid layer ) length( l_empty ) x_strokes t_noun "
    'if( cdr( l_empty ) "are" "is" ) buildString( reverse( parts ) ", " ) )',
    'sprintf( nil "%d (%s)" car( entry ) size )')
pin("s3dStrokeSize",
    'sprintf( nil "an arc of radius %g" sqrt( dx * dx + dy * dy ) )',
    'sprintf( nil "a line %g long" sqrt( dx * dx + dy * dy ) )')
pin("s3dCollectSilkByLayer",
    'when( zero s3dReportLoss( g_state strcat( "zero width: " s3dDescribeObject( elem key )',
    "ok = zero || errset( polys = s3dPolysFromDbid( elem s_endCap g_state ) )",
    "kept = kept + 1",
    "unless( zero || (kept > 0) where = s3dDescribeObject( elem key ) s3dReportLoss( g_state if( ok "
    'strcat( "no polygon: " where " - left out, as Allegro converts it to no polygon" ) '
    'strcat( "conversion error: " where " - left out, as Allegro\'s conversion of it fails" ) ) ) )')
collect_body = normalise(body("s3dCollectSilkByLayer") or "")
check("and no failure is merely counted: every message names its object",
      "nBad" not in collect_body and "counted only" not in collect_body
      and collect_body.count("s3dWarn(") == 0, collect_body[:200])
pin("s3dMakeSilkscreen",
    "when( topPolys || botPolys || g_state['silkWarnings] "
    "list( thickness topPolys botPolys reverse( g_state['silkWarnings] ) ) )")

# --------------------------------------------------------------------------- #
# [5c] - the eleven the audit left "pinned by name only"
# --------------------------------------------------------------------------- #
# docs/test-audit.md, "What is still not covered": [6] below required each copy
# to NAME a procedure that exists, and nothing more - so `s3dVariantFit`,
# `gdsysGetVariantInfo`'s states, `s3dSymbolsToExport`, the two path helpers,
# the stackup body filter, the indenter and the four writers could all change
# their minds in the .il while their copies, and every suite built on them,
# stayed green. Each is pinned below the way [1]-[5] are: the statements that
# carry the decision, and - wherever the decision can be READ out of the source
# instead of restated here - the copy run against what the source says.

print("\n[5c] the variant list: which token is a refdes, which file fits, who is exported")

pin("s3dIsRefdesToken",
    'stringp( t_token ) && rexMatchp( "[A-Za-z0-9]" t_token )')

# Derived: the character class is read out of the SKILL and the copy is run
# against it. The stray "\n" the parser leaves behind when a line ends in " )"
# is the token this exists to drop - it can never match a refdes, but it did
# land in "variant list covers N of M".
cls = re.search(r'rexMatchp\( "\[([^"]+)\]" t_token \)',
                normalise(body("s3dIsRefdesToken") or ""))
check("the refdes character class is in the SKILL source", bool(cls),
      normalise(body("s3dIsRefdesToken") or "")[:120])
if cls:
    wanted = re.compile("[" + cls.group(1) + "]")
    TOKENS = ["R1", "C41", "\n", ")", "", "\t", "  ", "X", "1", "-", "_", "(+)"]
    disagree = [t for t in TOKENS
                if bool(T.is_refdes_token(t)) != bool(wanted.search(t))]
    check(f"the copy keeps exactly the tokens [{cls.group(1)}] matches", not disagree,
          disagree)
check("a non-string is not a refdes token", not T.is_refdes_token(None))

pin("s3dVariantFit",
    'when( known[upperCase( refdes )]  onBoard = onBoard + 1 )',
    'when( nKnown == 0',
    'when( (nBoard > 0) && (onBoard == 0)')

fit_body = normalise(body("s3dVariantFit") or "")
# Derived: the two conditions decide between the three answers, and the copy
# is run on boards that satisfy each in turn. The order matters as much as the
# conditions - "installs nothing" is tested first, so a file with no refdes at
# all is named rather than refused as another project's.
check("the empty-list branch is tested before the foreign-file one",
      0 <= fit_body.find("when( nKnown == 0") < fit_body.find("when( (nBoard > 0)"),
      (fit_body.find("when( nKnown == 0"), fit_body.find("when( (nBoard > 0)")))
check("the empty list warns and goes on rather than raising",
      "s3dWarn(" in fit_body.split("when( nKnown == 0")[1].split("return( t )")[0]
      and "error(" not in fit_body.split("when( nKnown == 0")[1].split("return( t )")[0])
# Its message carries the file's path and the names it lists, so it is the
# %s argument of error(), never the format (round 100, finding R1-1's kin).
check("the foreign file raises, its message a %s argument", 'error( "%s" strcat(' in
      fit_body.split("when( (nBoard > 0) && (onBoard == 0)")[1][:400])
check("the copy names an empty list rather than refusing it",
      T.variant_fit([], ["C1", "R1"]) == "installs nothing")
check("the copy refuses a list none of whose refdes is placed",
      T.variant_fit(["C41", "R77"], ["C1", "R1"]) == "not this board")
check("and counts the ones that are",
      T.variant_fit(["C1", "R1", "R2"], ["C1", "R1", "X1"]) == "2 of 3")

pin("s3dSymbolsToExport",
    'when( s3dIsRefdesToken( refdes )',
    '( s3dNoStepExport( sym )',
    '( g_variantSymbolList && t_variant && refdes &&\n'
    '                      !installed[upperCase( refdes )] &&\n'
    '                      !s3dAlwaysStepExport( sym )')

export_body = normalise(body("s3dSymbolsToExport") or "")
# Derived: "never" outranks "always". NO_STEP_EXPORT is the first branch of the
# cond and ALWAYS_STEP_EXPORT the last test of the second, so a symbol the
# first excluded can never be rescued by the second - and the copy's cond has
# to read the same way round.
no_export = export_body.find("( s3dNoStepExport( sym )")
always = export_body.find("!s3dAlwaysStepExport( sym )")
check("NO_STEP_EXPORT is tested before ALWAYS_STEP_EXPORT",
      0 <= no_export < always, (no_export, always))
check("the copy lets NO_STEP_EXPORT outrank ALWAYS_STEP_EXPORT",
      not T.exported(refdes="R1", installed=False, no_step_export=True,
                     always_export=True))
check("the copy drops a refdes this variant does not install",
      not T.exported(refdes="R1", installed=False))
check("ALWAYS_STEP_EXPORT rescues it",
      T.exported(refdes="R1", installed=False, always_export=True))
check("a symbol with no refdes is outside the list entirely",
      T.exported(refdes=None, installed=False))
check("and with no variant table everything is exported",
      T.exported(refdes="R1", installed=False, has_table=False))

print("\n[5d] gdsysGetVariantInfo - the three lines the state machine turns on")

pin("gdsysGetVariantInfo",
    'pattern = pcreCompile("[\\"\\t+\\\\()]")',
    'propertyStart = pcreCompile( "^\\t\\t\\\\(.*" )',
    'when( (state == "awaitStartCondition") && (strcmp( line "\\t\\t(base\\n" ) != 0) &&\n'
    '                      ((strcmp( line "\\t)\\n" ) == 0) || pcreMatchp( propertyStart line ))',
    'when( length( subStrings ) == 3',
    'currentVariant = nth( 1 subStrings )',
    'when( strcmp( line "\\t\\t(base\\n" ) == 0',
    'if( strcmp( line "\\t\\t)\\n" ) == 0 then',
    'symbols = nconc( symbols parseString( line ) )',
    'if( strcmp( line "\\t)\\n" ) == 0 then',
    'when( length( subStrings ) > 1',
    'variantTable[currentVariant] = symbols',
    # The fix of 2026-07-22, in both branches that close an alternate-part
    # block: the refdes reaches the variant's list, not the first property
    # ("VALUE=12pF"). Nothing held it until round 118 (review 23.10.2026,
    # R2-9: reverted in both, every suite stayed green).
    'partProperties = makeTable( "partProperties" nil ) '
    'symbols = nconc( symbols list( refDes ) ) else state = "awaitMoreProperties"',
    'symbols = nconc( symbols list( refDes ) ) properties = "" state = "awaitEndCondition" ) ) ( t warn(',
    # Round 119, the parser no longer loses a variant or a part: a block, or
    # a base list, still open when its variant closes - or a block when the
    # next one begins - ends there with its part installed; a refdes alone on
    # its line opens a block (Allegro 25.1 lost all three, round 118).
    'when( (state == "awaitMoreProperties") && ((strcmp( line "\\t)\\n" ) == 0) || '
    'pcreMatchp( propertyStart line )) parts[refDes] = partProperties '
    'partProperties = makeTable( "partProperties" nil ) symbols = nconc( symbols list( refDes ) ) '
    'properties = "" state = "awaitEndCondition" )',
    'when( (state == "appendSymbols") && (strcmp( line "\\t)\\n" ) == 0) state = "awaitEndCondition" )',
    'when( (length( subStrings ) == 1) && (strcmp( line "\\t\\t(base\\n" ) != 0) '
    'refDes = pcreReplace( pattern car( subStrings ) "" 0 ) '
    'when( refDes != "" properties = "" state = "awaitMoreProperties" ) )')

# Derived, and the strongest pin in this section: the three literal lines the
# machine compares against are READ OUT OF THE SKILL, a Variants.lst is built
# from exactly those, and the copy is asked to parse it. The copy spells them
# out, so an edit to any one of the three in the .il makes the built file stop
# parsing here - which is what "a state machine pinned to its own literals"
# means. The strip class comes out of `pattern` the same way.
parser_body = normalise(body("gdsysGetVariantInfo") or "")
lits = re.findall(r'strcmp\( line "((?:[^"\\]|\\.)*)" \)', parser_body)
# Three distinct lines, compared five times: "(base" opens the list from two
# states, "\t)" closes the variant from two. A fourth literal, or one of the
# three gone, is a state machine that no longer reads the file Capture writes.
THREE = {"\\t\\t(base\\n", "\\t\\t)\\n", "\\t)\\n"}
check(f"the machine turns on exactly three literal lines, found {sorted(set(lits))}",
      set(lits) == THREE, lits)
if set(lits) == THREE:
    base_line, close_list, close_variant = "\t\t(base\n", "\t\t)\n", "\t)\n"
    # Unescape what the source spells, so the text below is the SKILL's own.
    unescape = {"\\t": "\t", "\\n": "\n"}
    def unesc(text):
        for k, v in unescape.items():
            text = text.replace(k, v)
        return text
    base_line = unesc([l for l in lits if "(base" in l][0])
    close_list = unesc([l for l in lits if l == "\\t\\t)\\n"][0])
    close_variant = unesc([l for l in lits if l == "\\t)\\n"][0])
    built = ('(\n\t("VAR_A"\n' + base_line + '\t\t\tR1 C2 X3\n' + close_list
             + close_variant + '\t("VAR_B"\n' + base_line + '\t\t\tR9\n'
             + close_list + close_variant + ')\n')
    table = T.parse_variants(built)
    check("the copy reads a file built from the SKILL's own three lines",
          sorted(table) == ["VAR_A", "VAR_B"], sorted(table))
    # s3dIsRefdesToken is the SKILL's guard against a token that is no
    # refdes. Allegro 25.1 left none in the nine files of
    # tests/fixtures/variants (round 118): its parseString breaks at a line
    # end as at a space, so a line's last token does not keep the "\n".
    check("and the symbols of each land where they belong",
          [r.strip() for r in table.get("VAR_A", []) if T.is_refdes_token(r)] == ["R1", "C2", "X3"]
          and [r.strip() for r in table.get("VAR_B", []) if T.is_refdes_token(r)] == ["R9"],
          table)
    # The 2026-09-03 case: a variant that closes before any (base installs
    # nothing, and the file must still register it.
    bare = '(\n\t("BARE"\n' + close_variant + ')\n'
    check("a variant that closes before any base block is still registered",
          list(T.parse_variants(bare)) == ["BARE"], T.parse_variants(bare))

def skill_string(spelled):
    """A SKILL string literal's body as the characters it holds."""
    return re.sub(r"\\(.)", lambda m: {"t": "\t", "n": "\n"}.get(m.group(1), m.group(1)), spelled)


strip = re.search(r'pattern = pcreCompile\("\[((?:[^"\\]|\\.)*)\]"\)', parser_body)
check("the strip class is in the SKILL source", bool(strip), parser_body[:120])
if strip:
    # The literal's characters, read as the regex they are: in a class "\("
    # is the paren, so the class holds no backslash, and Allegro 25.1 keeps
    # the one in "X\2" (round 118). This check used to read the literal as a
    # bare set of characters, and agreed with a copy that stripped it.
    klass = re.compile("[" + skill_string(strip.group(1)) + "]")
    probe = '"\t+\\()aZ9 '
    spelled = {c for c in probe if klass.match(c)}
    check(f"the copy strips the same characters {''.join(sorted(spelled))!r}",
          set(T.STRIP) == spelled and {c for c in probe if T._STRIP.match(c)} == spelled,
          (sorted(T.STRIP), sorted(spelled)))

# The wrapped-property branch the copy follows since round 118 (R2-9: it did
# not, and lost a part the SKILL installs): where a block ends, on its line
# and after it, and what is put together on the way.
pin("gdsysGetVariantInfo",
    # a block closed on its own line ends in ")": parseString broke the "\n"
    # off its last piece, and ")\n" alone, asked until round 119, never came
    'if( member( car(last(subStrings)) list( ")" ")\\n" ) ) then',
    'properties = strcat( properties pcreReplace( newLineEnd line " )" 0 ) )',
    'properties = pcreReplace( newLine properties "" 0 )',
    'when( strcmp( car(last(subStrings)) ")\\n" ) == 0')
# ...and every regex it leans on, read out of the SKILL's pcreCompile calls
# and compared with the copy's, text for text.
compiled = {name: skill_string(text) for name, text in
            re.findall(r'(\w+) = pcreCompile\(\s*"((?:[^"\\]|\\.)*)"\s*\)', parser_body)}
copies = {"pattern": T._STRIP, "newLine": T._NEW_LINE, "newLineEnd": T._NEW_LINE_END,
          "newLineWithinProperty": T._NEW_LINE_WITHIN, "propertyStart": T._PROPERTY_START,
          "propertySeparator": T._PROPERTY_SEPARATOR}
differ = {k: (compiled.get(k), c.pattern) for k, c in copies.items() if compiled.get(k) != c.pattern}
check(f"the copy's {len(copies)} regexes are the SKILL's own, read out of its pcreCompile calls",
      not differ and set(copies) <= set(compiled), differ or sorted(compiled))

# Round 120 (review 23.10.2026, R2-10): a name given to two variants. The
# table keeps one entry per name, so the later replaced the earlier and the
# export lost it without a word (Allegro 25.1: "1 variant(s) parsed"). Noted
# on the line the name stands on, said once the file is shut - an error with
# the port still open would keep Variants.lst locked for the session.
pin("gdsysGetVariantInfo",
    'lineNo = lineNo + 1',
    'if( namedOn[currentVariant] then repeated = cons( sprintf( nil "\\"%s\\" (lines %d and %d)" '
    'currentVariant namedOn[currentVariant] lineNo ) repeated ) else namedOn[currentVariant] = lineNo )',
    'close( inPort ) when( repeated error(')

print("\n[5f] every variant a file of its own (round 120)")

# The name a variant's file gets, the one place it is made; what no Windows
# file name carries made "_"; and which variants would share a file, asked of
# the file system itself (review 23.10.2026, R2-10: "Full" and "FULL" were
# written to one file, the later over the earlier).
pin("s3dFileNameSafe",
    'pcreReplace( pcreCompile( "[\\\\\\\\/:*?\\"<>|\\\\x01-\\\\x1f]" ) t_text "_" 0 )')
pin("s3dVariantFileName",
    'lowerCase( strcat( t_design "_" s3dFileNameSafe( t_variant ) ) )')
pin("s3dVariantFileClashes",
    'probe = strcat( t_dir "/simple3d-name-check" )',
    'while( isDir( probe ) || isFile( probe )',
    'unless( createDir( probe )',
    'name = strcat( s3dVariantFileName( t_design variant ) ".json" )',
    'path = strcat( probe "/" name )',
    'if( isFile( path ) then',
    'clashes = cons( sprintf( nil "\\"%s\\" and \\"%s\\" both go to %s.json" earlier variant '
    's3dVariantFileName( t_design earlier ) ) clashes )',
    'port = outfile( path )',
    'fprintf( port "%s\\n" variant )',
    'made = cons( path made )',
    'foreach( path made deleteFile( path ) )',
    'unless( deleteDir( probe )',
    'reverse( clashes )')

# The export asks it before it writes anything, in the order its loop writes
# (both walk the variant table), and refuses on any answer; the loop's file
# name comes from the same procedure, the folder no longer lower-cased with
# it; a name made safe is said, in the console and in the file.
pin("makeVariant3dIntermediates",
    'foreach( variant variantSymbolList variantNames = cons( variant variantNames ) )',
    'clashes = s3dVariantFileClashes( dir dsnName reverse( variantNames ) )',
    'when( clashes error(',
    'variantName = s3dVariantFileName( dsnName variant ) fileName = strcat( dir "/" variantName ".json" )',
    'unless( s3dFileNameSafe( variant ) == variant',
    "state['warnings] = cons( message state['warnings] )")
export_body = normalise(body("makeVariant3dIntermediates") or "")
asked = export_body.find("clashes = s3dVariantFileClashes(")
writes = export_body.find('foreach( variant variantSymbolList printf( "Exporting .json for variant: %s\\n" variant )')
check("the check is asked before the loop that writes the variants",
      0 <= asked < writes, (asked, writes))
check("no variant's path is lower-cased with its folder any more",
      'lowerCase( strcat( dir' not in export_body, export_body[writes:writes + 300])

# Derived: the class is read out of the SKILL, as the regex it is, and run
# beside the copy's on every character a name could hold - so a class that
# lost the colon, or a control character, differs here by name.
safe = re.search(r'pcreCompile\( "((?:[^"\\]|\\.)*)" \)', normalise(body("s3dFileNameSafe") or ""))
check("the class of s3dFileNameSafe is in the SKILL source", bool(safe))
if safe:
    klass = re.compile(skill_string(safe.group(1)))
    every = "".join(chr(c) for c in range(1, 256))
    takes = {c for c in every if klass.match(c)}
    check(f"the copy makes the same {len(takes)} characters \"_\" - \\ / : * ? \" < > | and 31 control ones",
          takes == {c for c in every if T._UNSAFE.match(c)} and set(T.UNSAFE) <= takes
          and len(takes) == len(T.UNSAFE) + 31,
          sorted(takes ^ {c for c in every if T._UNSAFE.match(c)}))

print("\n[5e] where Variants.lst is, and what the stackup body is")

pin("s3dDesignFolder",
    'when( (ch == "/") || (ch == "\\\\")  cut = i )',
    'when( cut == 0  return( "" ) )',
    'return( if( cut == 1 then "/" else substring( full 1 cut - 1 ) ) )')

# Derived: the separators are read out of the SKILL, and the copy is run on a
# path built with each of them. A .il that recognised "/" only would leave a
# Windows path with no folder - Variants.lst opened by its bare name against
# Allegro's working directory, which is the fault this helper exists for.
seps = re.findall(r'\(ch == "((?:[^"\\]|\\.)*)"\)',
                  normalise(body("s3dDesignFolder") or ""))
check(f"the SKILL names its separators {seps}", len(seps) == 2, seps)
for spelled in seps:
    sep = spelled.replace("\\\\", "\\")
    check(f"the copy cuts a path on {sep!r} too",
          T.s3d_design_folder("d:" + sep + "boards" + sep + "b.brd")
          == "d:" + sep + "boards",
          T.s3d_design_folder("d:" + sep + "boards" + sep + "b.brd"))
check("a name with no separator at all has no folder",
      T.s3d_design_folder("flex2-a0.brd") == "")
check("and the root keeps its one slash", T.s3d_design_folder("/b.brd") == "/")

pin("s3dVariantFilePath",
    'dir = s3dDesignFolder()',
    'last = if( dir == "" then "" else substring( dir strlen( dir ) 1 ) )',
    '( dir == ""                        "Variants.lst" )',
    '( (last == "/") || (last == "\\\\")  strcat( dir "Variants.lst" ) )',
    '( t                                strcat( dir "/Variants.lst" ) )')

# Derived: the name and the separator the ordinary branch inserts are read out
# of the SKILL, and the copy has to build the same path.
tail = re.search(r'\( t strcat\( dir "((?:[^"\\]|\\.)*)" \) \)',
                 normalise(body("s3dVariantFilePath") or ""))
check("the SKILL's ordinary branch spells the whole tail", bool(tail),
      normalise(body("s3dVariantFilePath") or "")[-140:])
if tail:
    check(f"the copy appends the same {tail.group(1)!r}",
          T.s3d_variant_file_path("d:/boards/b.brd") == "d:/boards" + tail.group(1),
          T.s3d_variant_file_path("d:/boards/b.brd"))
check("a folder that already ends in a separator gets no second one",
      T.s3d_variant_file_path("/b.brd") == "/Variants.lst",
      T.s3d_variant_file_path("/b.brd"))
check("and no folder at all falls back to the bare name",
      T.s3d_variant_file_path("b.brd") == "Variants.lst")

pin("s3dLayerInBody",
    '!( s3dContains( probe "SILK" ) || s3dContains( probe "PASTE" ) )')

# Derived: the markers are read out of the SKILL and the copy is run on a layer
# name carrying each. Dropping one put the 0.025 mm paste sheets back into the
# board body - 1.204 mm reported on a 1.104 mm board.
markers = re.findall(r's3dContains\( probe "([^"]+)" \)',
                     normalise(body("s3dLayerInBody") or ""))
check(f"the SKILL names the markers it excludes {markers}", len(markers) == 2, markers)
for marker in markers:
    check(f"the copy keeps a layer named {marker} out of the body",
          not T.in_body(marker + "_TOP", None), marker)
check("and a conductor stays in", T.in_body("TOP", "CONDUCTOR"))
check("the layer FUNCTION is read as well as the name",
      not T.in_body("L7", "SOLDER_PASTE") and not T.in_body("L7", "SILKSCREEN"))
body_src = normalise(body("s3dLayerInBody") or "")
# The negation is the whole point: the body is what is NOT silk or paste. Drop
# the "!" and the board becomes the two sheets it was built to leave out.
check("the result is negated, and the negation is outside the or",
      body_src.count("!( s3dContains(") == 1
      and re.search(r'!\( s3dContains\( probe "\w+" \) \|\| s3dContains\( probe "\w+" \) \)',
                    body_src), body_src[-140:])

print("\n[5f] the writers: the indent, the version, the keys")

pin("s3dAddIndent",
    'pad = strcat( pad "\\t" )',
    '( !t_string           nil )',
    '( !stringp( t_string ) t_string )')

# Derived: the character the indent is made of is read out of the SKILL. The
# reference demo.json is tab-indented byte for byte, and every fragment in
# skill_transliterations builds its own tabs - a space here would be invisible
# to json.loads and visible in every diff of a re-exported board.
padchar = re.search(r'pad = strcat\( pad "((?:[^"\\]|\\.)*)" \)',
                    normalise(body("s3dAddIndent") or ""))
check("the SKILL spells the indent character", bool(padchar),
      normalise(body("s3dAddIndent") or "")[:140])
if padchar:
    one = padchar.group(1).replace("\\t", "\t")
    check(f"the copy indents with the same {one!r}",
          T.s3dAddIndent("a\nb", 2) == one * 2 + "a\n" + one * 2 + "b",
          T.s3dAddIndent("a\nb", 2))

pin("create3dIntermediateFormat",
    '"\\"format_version\\": 12"',
    'when( g_fullBoard\n            members = append( members list( "\\"full_board\\": true" ) )\n        )',
    '"\\"components\\": {}"')

# Derived: the version the exporter writes is read out of the SKILL and the
# copy has to write the same number. tools/audit_docs.py compares it with the
# docs; this compares it with the copy every suite's expectations are built on.
version = re.search(r'"\\"format_version\\": (\d+)"',
                    normalise(body("create3dIntermediateFormat") or ""))
check("the SKILL states one format_version", bool(version),
      normalise(body("create3dIntermediateFormat") or "")[:200])
if version:
    written = json.loads(T.create3dIntermediateFormat("b", False, ["{}"], None, [], False))
    check(f"the copy writes format_version {version.group(1)}",
          str(written.get("format_version")) == version.group(1),
          written.get("format_version"))
    check("the full-board key is optional and only ever true",
          "full_board" not in written
          and json.loads(T.create3dIntermediateFormat(
              "b", True, ["{}"], None, [], False))["full_board"] is True)
    check("and an export with no component writes an empty components object",
          written.get("components") == {}, written.get("components"))

pin("makePcb",
    '"\\t\\"thickness\\": {\\n"',
    'arrays = list( strcat( "[\\n" s3dAddIndent( buildString( car( edges ) ",\\n" ) ) "\\n]" ) )',
    'when( cuts\n            arrays = append( arrays car( cuts ) )\n        )',
    's3dAddIndent( buildString( arrays ",\\n" ) 2 )')

# Derived: which of car/cadr/caddr each colour channel takes is read out of the
# SKILL, and the copy is run with three values that tell them apart.
pcb_body = normalise(body("makePcb") or "")
channels = re.findall(r'"\\t\\"([rgb])\\": " sprintf\( nil "%f" (\w+)\( color \) \)', pcb_body)
check("the SKILL names one accessor per colour channel",
      [c for c, _ in channels] == ["r", "g", "b"], channels)
if len(channels) == 3:
    order = {"car": 0, "cadr": 1, "caddr": 2}
    triple = (0.125, 0.25, 0.5)
    got = json.loads("{" + T.makePcb(None, ["{}"], None, triple) + "}")["pcb"]["color"]
    check("the copy reads the same element for each channel",
          all(abs(got[name] - triple[order[acc]]) < 1e-9 for name, acc in channels),
          (got, channels))
check("a board with nothing to cut still writes one edges array",
      len(json.loads("{" + T.makePcb(None, ["{}"], None, (0.0, 0.4, 0.0)) + "}")["pcb"]["edges"]) == 1)

pin("symbolReturn3DElements",
    's3dJsonQuote( sprintf( nil "%s" refDes ) ) ": {\\n"',
    '"\\t\\"step_mapping\\": {\\n"',
    '"\\t\\"zone\\": " s3dJsonQuote( zoneName ) ",\\n"')

# Derived: every key the placement block writes is read out of the SKILL, and
# the copy's block has to carry the same ones at the same depth. `zone` is the
# one that decides which surface a part stands on: a part on a 2.44 mm
# stiffener and one on 0.365 mm flex are placed differently.
place_body = normalise(body("symbolReturn3DElements") or "")
outer = set(re.findall(r'"\\t\\"(\w+)\\": ', place_body))
inner = set(re.findall(r'"\\t\\t\\"(\w+)\\": ', place_body))
check(f"the SKILL writes {sorted(outer)} beside step_mapping", "zone" in outer, sorted(outer))
copy_block = json.loads("{" + T.placement("R1", "r.step", "FLEX") + "}")["R1"]
check("the copy carries the same outer keys, step_mapping's own excepted",
      outer - {"step_mapping"} <= set(copy_block) | {"is_mirrored", "y", "angle"},
      (sorted(outer), sorted(copy_block)))
check("and step_mapping's step_name is one of the inner keys on both sides",
      "step_name" in inner and "step_name" in copy_block["step_mapping"],
      (sorted(inner), sorted(copy_block["step_mapping"])))
check("the zone reaches the file and a missing one is null",
      copy_block["zone"] == "FLEX"
      and json.loads("{" + T.placement("R1", "r.step", None) + "}")["R1"]["zone"] is None)

pin("s3dWriteSilkPolys",
    'fprintf( p_port "\\t\\t\\t\\t\\"layer\\": %s,\\n" s3dJsonQuote( layer ) )',
    'fprintf( p_port "\\t\\t\\t\\t\\"vertices\\": [\\n" )')

pin("s3dWriteSilkscreen",
    'fprintf( p_port "\\t\\t\\"thickness\\": %f,\\n" thickness )',
    'fprintf( p_port "\\t\\t\\"warnings\\": [\\n" )')

# Derived: the layer line is written through a %s that takes the QUOTED name -
# round 76's fix (plan D4) and what test_emit [4] guards from the other side.
silk_body = normalise(body("s3dWriteSilkPolys") or "")
check("the layer name goes through s3dJsonQuote, not between two quote characters",
      re.search(r'\\"layer\\": %s,\\n" s3dJsonQuote\( layer \)', silk_body)
      and '\\"layer\\": \\"%s\\"' not in silk_body, silk_body[:160])
check("the copy quotes it the same way",
      json.loads("[" + T.silk_poly('odd"name') + "]")[0]["layer"] == 'odd"name')
warn_body = normalise(body("s3dWriteSilkscreen") or "")
check("the warnings array is written only when there is something to say",
      re.search(r'when\( warnings fprintf\( p_port "\\t\\t\\"warnings\\": \[\\n" \)', warn_body),
      warn_body[:200])
check("and the copy's warnings survive a quote and a backslash",
      json.loads("{" + T.silk_warnings(['a "q"', "b\\c"]) + "}")["warnings"]
      == ['a "q"', "b\\c"])

print("\n[5g] s3dCmdExpands, s3dCmdDefined - what Windows' cmd would replace (round 116)")
# The rule s3dExportCommand asks before it hands a path to cmd (review
# 23.10.2026, R2-4). [7] below holds the copy to Allegro's own answers,
# test_launch_cmd [9] holds the copy to cmd itself; these are the statements
# that decide.
pin("s3dCmdExpands",
    'when( j > n  return( nil ) )',
    'name = if( j > i + 1 then substring( t_text i + 1 j - i - 1 ) else "" )',
    'base = if( k > 1 then substring( name 1 k - 1 ) else "" )',
    'when( (base != "") && s3dCmdDefined( base ) return( substring( t_text i j - i + 1 ) ) )',
    # with its else: "i = j" alone is a substring of "i = j + 1", which skips
    # the % that may open the next name (the row survived a bare "i = j")
    'i = j else i = i + 1')
pin("s3dCmdDefined",
    'errset( value = getShellEnvVar( t_name ) )',
    'if( stringp( value ) || (substring( t_name 1 1 ) == "=") '
    '|| member( upperCase( t_name ) S3D_CmdOwnNames ) then t else nil )')
own = re.search(r"S3D_CmdOwnNames = list\(([^)]*)\)", IL)
check("cmd's own names in the SKILL are the copy's",
      own is not None and tuple(re.findall(r'"([^"]+)"', own.group(1))) == T.CMD_OWN_NAMES,
      own.group(1) if own else None)

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
# The exact counts, not a floor well under them: with a floor of 15, four
# `# mirrors` lines could go before anything said so (review of 2026-09-17).
# Update both numbers when a copy is added - a drop is the finding.
mirror_lines = sum(1 for line in src.splitlines() if line.startswith("# mirrors skill/"))
check(f"the copies name {len(named)} SKILL procedures on {mirror_lines} `# mirrors skill/` lines "
      f"(19 on 15 when this was written)", len(named) >= 19 and mirror_lines >= 15,
      (len(named), mirror_lines, sorted(named)))
missing = sorted(p for p in named if body(p) is None)
check("every procedure a copy names exists in the SKILL source", not missing, missing)

# The five the audit measured, plus rotateXY which s3dDrillXY is built on.
MUST_PIN = {"s3dLayerIsNegative", "s3dDrillXY", "rotateXY", "s3dBoxesMeet",
            "s3dJsonMerge", "s3dJsonQuote",
            # round 116: what cmd would replace, answered by Allegro too
            "s3dCmdExpands",
            # round 120: the variants' file names, answered by Allegro too
            "s3dFileNameSafe", "s3dVariantFileName", "s3dVariantFileClashes"}
# And the sweep of round 87, pinned by its source alone: it reads a design,
# so no recorded Allegro answer can stand in for it (see [5b]).
MUST_PIN_SOURCE_ONLY = {"s3dCollectExposed",
                        # and round 111's fill dispatch, for the same reason ([5b2])
                        "s3dPolysFromDbid", "s3dCopperPolys",
                        # and round 117's account of what the legend loses ([5b3])
                        "s3dStrokePolys", "s3dReportLoss", "s3dCollectSilkByLayer",
                        "s3dMakeSilkscreen", "s3dStrokesLost", "s3dStrokeSize"}
check("every procedure the audit found unpinned is pinned here",
      (MUST_PIN | MUST_PIN_SOURCE_ONLY) <= set(PINNED),
      sorted((MUST_PIN | MUST_PIN_SOURCE_ONLY) - set(PINNED)))
# The rule the audit's "what is still not covered" asked for: NAMING a
# procedure that exists was all [6] required, so eleven copies could drift
# from their originals with nothing to say so. A copy is pinned or it is not
# a copy - one `pin(...)` per name, or the name comes off the `# mirrors` line.
unpinned = sorted(p for p in named if p not in PINNED)
check(f"and every procedure a `# mirrors` line names is pinned by a statement "
      f"({len(named)} named, {len(PINNED)} pinned)", not unpinned, unpinned)
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
    if procedure == "s3dCmdExpands":
        return T.s3d_cmd_expands(inputs["text"])
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
    if procedure == "parseString":
        # SKILL's own, which the parser's copy stands on; nil for no pieces
        copy = getattr(T, "parse_string", None)
        return copy(inputs["text"]) or None if copy else "no copy of parseString"
    if procedure == "gdsysGetVariantInfo":
        # the variant table, variants in name order, an empty list nil; the
        # file's bytes one character each, as SKILL holds them (round 120:
        # v21 is cp1251); "error" where the SKILL raised
        try:
            table = T.parse_variants((ROOT / inputs["file"]).read_bytes().decode("latin-1"))
        except T.VariantFileError:
            return "error"
        return [[name, table[name] or None] for name in sorted(table)] or None
    if procedure == "s3dFileNameSafe":
        return T.file_name_safe(inputs["text"])
    if procedure == "s3dVariantFileName":
        return T.variant_file_name(inputs["design"], inputs["variant"])
    if procedure == "s3dVariantFileClashes":
        # asked of the real file system, in a folder of this run's own, as
        # the probe asks it in build/probe-names; the last case is what the
        # others left there
        if inputs.get("left"):
            left = sorted(p.name for p in CLASH_DIR.iterdir())
            return left or None
        if "file" in inputs:
            table = T.parse_variants((ROOT / inputs["file"]).read_bytes().decode("latin-1"))
            variants = sorted(table)
        else:
            variants = inputs["variants"]
        return T.variant_file_clashes(str(CLASH_DIR), "brd", variants) or None
    raise AssertionError(f"no copy wired up for {procedure}")


CLASH_DIR = OUT / "probe-names"
shutil.rmtree(CLASH_DIR, ignore_errors=True)
CLASH_DIR.mkdir(parents=True)


def same(got, want, tol=1e-9):
    """Numbers within a tolerance, everything else exactly; lists element by
    element and nested, numbers in them to 1e-6 (s3dDrillXY's points)."""
    if isinstance(want, list) and isinstance(got, list):
        return len(got) == len(want) and all(same(g, w, 1e-6) for g, w in zip(got, want))
    numbers = (int, float)
    if (isinstance(want, numbers) and isinstance(got, numbers)
            and not isinstance(want, bool) and not isinstance(got, bool)):
        return abs(float(got) - float(want)) < tol
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
