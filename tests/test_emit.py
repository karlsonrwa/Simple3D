# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, fails, check, exporter_source

"""Every string the exporter writes into the intermediate is quoted, and the
body is one join.

Round 76, plan D4. Until then five places glued a value between two quote
characters - the refdes key and step_name of a placement, the zone name, a
silkscreen polygon's layer, a silkscreen warning, the variant name in the
header - and the embedded-model list left a name with a quote or backslash
OUT of the file with a warning. A refdes like R"1 or a library path with a
backslash then produced a file json.load refuses whole.

Two halves. The first transliterates the five emission fragments the way
the SKILL builds them, feeds them names with a quote, a backslash and a tab, and asks the
json module for the value back (test_quote.py does the same for the quoter
itself). The second reads makeVariant3dIntermediates.il and refuses any line
that still glues a raw value between quotes, or writes one through a
quoted %s - the guard that keeps a sixth site from appearing.
"""
import json
import re

from skill_transliterations import (create3dIntermediateFormat, header, makePcb, placement,
                                    silk_poly, silk_warnings)
import sys

IL = exporter_source()


AWKWARD = ['R"1', 'C\\1', 'D:\\lib\\part "A".step', 'zone "flex"\\2', 'a\ttab', 'plain']

print("[1] a placement with an awkward refdes, step name and zone survives json.loads")
for ref in AWKWARD:
    for step in AWKWARD:
        got = json.loads("{" + placement(ref, step, 'zone "Z"\\1') + "}")
        check(f"refdes {ref!r} / step {step!r}",
              list(got) == [ref] and got[ref]["step_mapping"]["step_name"] == step
              and got[ref]["zone"] == 'zone "Z"\\1', str(got)[:80])
got = json.loads("{" + placement("R1", "x.step", None) + "}")
check("no zone is null, as before", got["R1"]["zone"] is None)

print("\n[2] a silkscreen layer and a warning with quotes in them")
for name in AWKWARD:
    got = json.loads("[" + silk_poly(name) + "]")
    check(f"layer {name!r}", got[0]["layer"] == name)
got = json.loads("{" + silk_warnings(['zero width: text "R1" on PACKAGE GEOMETRY/SILKSCREEN_TOP at (1.0, 2.0)',
                                        'path on A\\B', 'a\ttab']) + "}")
check("warnings come back verbatim", got["warnings"][0].startswith('zero width: text "R1"')
      and got["warnings"][1] == 'path on A\\B' and got["warnings"][2] == 'a\ttab')

print("\n[3] the header: the variant name, and embedded models no longer left out")
got = json.loads("{" + header('Board "B"\\lsm', AWKWARD) + "}")
check("the name", got["name"] == 'Board "B"\\lsm')
check("every model name is in the list, the awkward ones included", got["embedded_models"] == AWKWARD)

print("\n[4] the source: no raw value between quote characters is left in the writer")
# Comments off, and s3dJsonQuote's own body off: it is the one place a quote
# character is glued on purpose.
code = "\n".join(l.split(";")[0] if not l.lstrip().startswith(";") else "" for l in IL.splitlines())
m = re.search(r"procedure\( s3dJsonQuote\(.*?\n\)\n", code, re.S)
check("s3dJsonQuote is where it was", m is not None)
outside = code[:m.start()] + code[m.end():] if m else code
glued = [l.strip() for l in outside.splitlines()
         if re.search(r'"\\"" [A-Za-z(]|[A-Za-z)] "\\""', l) and "parseString" not in l]
check("no line glues a value between quote characters", not glued, str(glued[:3]))
quoted_fmt = [l.strip() for l in outside.splitlines() if re.search(r'fprintf\(.*\\"%s\\"', l)]
check("no fprintf writes a value through a quoted %s", not quoted_fmt, str(quoted_fmt[:3]))
# The line test above sees a value glued to a literal that is a quote
# character alone, "\"". A key and its opening quote in one literal,
# "\"key\": \"" value "\",\n", passed it (R1n-12 of the 28.10.2026 review,
# round 128): strcat's own arguments are asked now, a literal ending with \"
# before a value and a value before a literal starting with \".
sys.path.insert(0, str(ROOT / "tools"))
from check_arity import split_top_level  # noqa: E402
from skill_lex import strip_comments  # noqa: E402

# The comments off by the lexer, which keeps a ';' inside a literal: the line
# cut above (`split(";")`) breaks 25 of the exporter's lines inside a message,
# harmless to a test of one line and fatal to one that reads the whole text -
# every literal after the first such line paired the wrong quotes, and the
# first version of this guard passed the round-128 mutant it was written for.
lexed = strip_comments(IL)
open_lines = [l.strip()[:80] for l in lexed.splitlines() if '"' in re.sub(r'"(\\.|[^"\\])*"', "", l)]
check("with the comments off, every literal of the exporter closes on its own line",
      not open_lines, open_lines[:3])
lq = re.search(r"procedure\( s3dJsonQuote\(.*?\n\)\n", lexed, re.S)
lexed_outside = lexed[:lq.start()] + lexed[lq.end():] if lq else lexed


def glued_in_strcat(code):
    """'literal value' / 'value literal' for every value glued to a quote
    character among strcat's arguments in *code* (comments already off)."""
    lits = []

    def mask(match):
        lits.append(match.group(0))
        return f'"{len(lits) - 1}"'
    masked = re.sub(r'"(\\.|[^"\\])*"', mask, code)
    found = []
    for call in re.finditer(r"\bstrcat\(", masked):
        depth = 0
        for end in range(call.end() - 1, len(masked)):
            if masked[end] == "(":
                depth += 1
            elif masked[end] == ")":
                depth -= 1
                if depth == 0:
                    break
        args = [re.sub(r'"(\d+)"', lambda k: lits[int(k.group(1))], a)
                for a in split_top_level(masked[call.end():end])]
        for a, b in zip(args, args[1:]):
            if (a.startswith('"') and a.endswith('\\""') and not b.startswith('"')) or \
               (not a.startswith('"') and b.startswith('"\\"')):
                found.append(f"{a} {b}")
    return found


check("the strcat guard sees both forms on fragments, and not a value quoted through s3dJsonQuote",
      len(glued_in_strcat('strcat( "\\"" name "\\"" )')) == 2
      and len(glued_in_strcat('strcat( "\\"key\\": \\"" value "\\",\\n" )')) == 2
      and not glued_in_strcat('strcat( "\\t\\"step_name\\": " s3dJsonQuote( x ) ",\\n" )'),
      (glued_in_strcat('strcat( "\\"" name "\\"" )'), glued_in_strcat('strcat( "\\"key\\": \\"" value "\\",\\n" )')))
check("and on the source: s3dJsonQuote's own glue, the one place it is meant",
      bool(lq) and glued_in_strcat(lexed[lq.start():lq.end()]) != [],
      glued_in_strcat(lexed[lq.start():lq.end()]) if lq else None)
glued_strcat = glued_in_strcat(lexed_outside)
check("no strcat glues a value to a quote character outside s3dJsonQuote", not glued_strcat, glued_strcat[:3])
check("s3dHasJsonSpecial is gone with the skip it served", "s3dHasJsonSpecial" not in IL)
for site in ('s3dJsonQuote( sprintf( nil "%s" refDes ) )', 's3dJsonQuote( sprintf( nil "%s" stepFileName ) )',
             's3dJsonQuote( zoneName )', 's3dJsonQuote( layer )', 's3dJsonQuote( message )',
             's3dJsonQuote( variantName )', 's3dJsonQuote( m )'):
    check(f"the writer quotes through {site}", site in IL)

print("\n[5] the body: members joined once, every combination of what a board has")
# create3dIntermediateFormat and makePcb transliterated (round 77, D8): the
# top-level members are strings without commas, ONE join puts the commas in,
# the re-indent prefixes every line with a tab, and the silkscreen - streamed
# after the body - is what decides whether the last member gets a comma.


SEG = '{ "type": "segment", "start": [0.0, 0.0], "end": [10.0, 0.0] }'
CUT = "[\n\t" + SEG + "\n]"
for comps in (False, True):
    for cuts in (False, True):
        for silk in (False, True):
            for full in (False, True):
              for pads in (False, True):
                text = create3dIntermediateFormat("board", full, [SEG, SEG], [CUT] if cuts else None,
                                                  [placement("R1", "r.step", None), placement("MECH1", "m.step", "FLEX")] if comps else [],
                                                  silk, pads)
                label = f"components={comps} cutouts={cuts} silk={silk} full_board={full} pads={pads}"
                try:
                    got = json.loads(text)
                except ValueError as exc:
                    check(label, False, f"does not parse: {exc}")
                    continue
                keys = list(got)
                # v10: the pads sit between the components and the silkscreen,
                # so the last key is the silkscreen, else the pads, else the
                # components - and every combination of the three parses.
                check(label,
                      keys[:3] == ["format", "format_version", "name"]
                      and (("full_board" in got) == full)
                      and got["pcb"]["thickness"]["board"] == 1.054
                      and len(got["pcb"]["edges"]) == (2 if cuts else 1)
                      and (("R1" in got["components"] and "MECH1" in got["components"]) == comps)
                      and len(got["components"]) == (2 if comps else 0)
                      and (("silkscreen" in got) == silk)
                      and (("pads" in got) == pads)
                      and (not pads or (list(got["pads"]) == ["padstacks", "pins", "exposed", "bare"]
                                        and list(got["pads"]["exposed"]) == ["top", "bottom"]
                                        and got["pads"]["pins"][0][4] == "P1"))
                      and keys[-1] == ("silkscreen" if silk else "pads" if pads else "components"),
                      str(keys))

got = json.loads("{" + makePcb(None, [SEG], None, (0.0, 0.4, 0.0)) + "}")
check("a pcb with no thickness (v9, no stackup is the board) still parses, thickness absent",
      "thickness" not in got["pcb"] and got["pcb"]["edges"])

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
