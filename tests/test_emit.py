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
                text = create3dIntermediateFormat("board", full, [SEG, SEG], [CUT] if cuts else None,
                                                  [placement("R1", "r.step", None), placement("MECH1", "m.step", "FLEX")] if comps else [],
                                                  silk)
                label = f"components={comps} cutouts={cuts} silk={silk} full_board={full}"
                try:
                    got = json.loads(text)
                except ValueError as exc:
                    check(label, False, f"does not parse: {exc}")
                    continue
                keys = list(got)
                check(label,
                      keys[:3] == ["format", "format_version", "name"]
                      and (("full_board" in got) == full)
                      and got["pcb"]["thickness"]["board"] == 1.054
                      and len(got["pcb"]["edges"]) == (2 if cuts else 1)
                      and (("R1" in got["components"] and "MECH1" in got["components"]) == comps)
                      and len(got["components"]) == (2 if comps else 0)
                      and (("silkscreen" in got) == silk)
                      and keys[-1] == ("silkscreen" if silk else "components"),
                      str(keys))

got = json.loads("{" + makePcb(None, [SEG], None, (0.0, 0.4, 0.0)) + "}")
check("a pcb with no thickness (v9, no stackup is the board) still parses, thickness absent",
      "thickness" not in got["pcb"] and got["pcb"]["edges"])

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
