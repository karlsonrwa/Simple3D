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

"""Transliteration of s3dDesignFolder / s3dVariantFilePath, the way
test_quote.py transliterates s3dJsonQuote.

Variants.lst sits beside the board, always. It used to be opened by its bare
name, which resolves against Allegro's WORKING directory - and when the two
differ the file is invisible, the export takes its no-variant path and writes
one JSON with every component in it, which is what "the variant export does not
work" looked like from outside.

The folder is now cut off the drawing path by SCANNING for the last separator,
not with parseString: parseString collapses the leading slashes of a UNC path
and would turn //server/share into a relative folder. That is the case worth a
test, along with the ones that look alike but are not - a bare drive root, mixed
separators, a name with no folder at all.
"""
import re, sys

fails = []
def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + str(detail)}")
    if not cond:
        fails.append(name)


def s3d_design_folder(full):
    """The SKILL loop, character for character."""
    if not isinstance(full, str):
        return ""
    cut = 0
    for i, ch in enumerate(full, start=1):      # SKILL's substring is 1-based
        if ch in "/\\":
            cut = i
    if cut == 0:
        return ""
    return "/" if cut == 1 else full[:cut - 1]


def s3d_variant_file_path(full):
    folder = s3d_design_folder(full)
    if folder == "":
        return "Variants.lst"
    if folder[-1] in "/\\":
        return folder + "Variants.lst"
    return folder + "/Variants.lst"


print("\n[1] the folder, cut off the drawing path")
cases = [
    (r"d:\Projects\OrCAD\My Test Board\flex2-a0.brd", r"d:\Projects\OrCAD\My Test Board"),
    ("d:/Projects/OrCAD/My Test Board/flex2-a0.brd", "d:/Projects/OrCAD/My Test Board"),
    (r"d:\Projects/OrCAD\My Test Board/flex2-a0.brd", r"d:\Projects/OrCAD\My Test Board"),
    (r"\\server\share\boards\flex2-a0.brd", r"\\server\share\boards"),
    (r"d:\flex2-a0.brd", "d:"),
    ("flex2-a0.brd", ""),
    ("/flex2-a0.brd", "/"),
]
for full, want in cases:
    got = s3d_design_folder(full)
    check(f"{full!r}", got == want, f"got {got!r}, wanted {want!r}")

check("a non-string is not a folder", s3d_design_folder(None) == "")

print("\n[2] and where Variants.lst then is")
wants = [
    (r"d:\Projects\My Test Board\flex2-a0.brd",
     r"d:\Projects\My Test Board/Variants.lst"),
    (r"\\server\share\boards\flex2-a0.brd", r"\\server\share\boards/Variants.lst"),
    (r"d:\flex2-a0.brd", "d:/Variants.lst"),
    ("/flex2-a0.brd", "/Variants.lst"),          # not "//Variants.lst"
    ("flex2-a0.brd", "Variants.lst"),            # the old behaviour, as fallback
]
for full, want in wants:
    got = s3d_variant_file_path(full)
    check(f"{full!r}", got == want, f"got {got!r}, wanted {want!r}")

print("\n[3] the UNC case parseString would have broken")
# What the collapsing rebuild does, kept as the reason the scan exists.
unc = r"\\server\share\boards\flex2-a0.brd"
collapsed = "/".join([p for p in re.split(r"[/\\]", unc) if p][:-1])
check("parseString-style rebuild loses the leading slashes",
      collapsed == "server/share/boards", collapsed)
check("the scan keeps them", s3d_design_folder(unc) == r"\\server\share\boards")

print("\n[4] the SKILL source still says the same thing")
src = (_ROOT / "makeVariant3dIntermediates.il").read_text(encoding="utf-8")
# The bare name may appear ONLY inside the helper (its own fallback). A
# `( variantFile "Variants.lst" )` anywhere is the bug coming back: that is a
# let-init resolving against the working directory again.
check("no call site binds the bare name",
      not re.search(r"\(\s*variantFile\s+\"Variants\.lst\"\s*\)", src))
check("both call sites take the path from the helper",
      len(re.findall(r"\(\s*variantFile\s+s3dVariantFilePath\(\s*\)\s*\)", src)) == 2,
      re.findall(r"\(\s*variantFile\s+\S+", src))

print("\n[5] does the variant table describe THIS board? (s3dVariantFit)")
# Two Variants.lst files parse perfectly and then export the whole board under
# variant names, which is indistinguishable from variants working:
#   - a stub: one variant, usually "dummy", with an empty base list;
#   - another project's file: plenty of refdes, none of them on this board.
# Both were found on the user's own disk, the stub copied into five projects.


def variant_fit(known, board):
    """The SKILL decision, in the same three branches."""
    known = {r.upper() for r in known}
    board = [r.upper() for r in board]
    covered = sum(1 for r in board if r in known)
    if not known:
        return "installs nothing"
    if board and covered == 0:
        return "not this board"
    return f"{covered} of {len(board)}"


check("a stub variant list is refused",
      variant_fit([], ["C1", "R1"]) == "installs nothing")
check("another project's list is refused",
      variant_fit(["C41", "R77"], ["C1", "R1"]) == "not this board")
check("a real one is accepted",
      variant_fit(["C1", "R1", "R2"], ["C1", "R1", "X1"]) == "2 of 3")
check("case does not matter on either side",
      variant_fit(["c1"], ["C1"]) == "1 of 1")
check("a board with no refdes at all is not refused",
      variant_fit(["C41"], []) == "0 of 0")

check("the exporter asks the question before the variant loop",
      re.search(r"s3dVariantFit\(\s*variantSymbolList\s+variantFile\s*\)", src))
check("both bad files stop the export rather than exporting something wrong",
      len(re.findall(r"error\(\s*strcat\(", src)) >= 2)

print("\n[6] who obeys the variant list, and who is outside it")
# The rule, settled by the user on 2026-08-03: a refdes is what makes a part
# nameable in a Variants.lst, so the list governs EVERYTHING that has one -
# mechanical or not. A symbol without a refdes can never be named there, so only
# NO_STEP_EXPORT can remove it. Two earlier rules stood here and each was wrong
# on the other's case: "the list IS the export list" lost mechanical parts;
# "subtract only what is not mechanical" kept a MECHANICAL-class MOLEX housing
# (A1/A2/A4 on variants_test-b0) in variants that do not install it.


def exported(*, refdes, installed, has_table=True, no_step_export=False,
             always_export=False, variant="ALL"):
    """s3dSymbolsToExport's cond, for one symbol."""
    if no_step_export:
        return False
    if has_table and variant and refdes and not installed and not always_export:
        return False
    return True


R3 = dict(refdes="R3")
check("an electrical part the variant does not install is dropped",
      not exported(**R3, installed=False))
check("...and kept when it does",
      exported(**R3, installed=True))
check("a MECHANICAL-class part with a refdes obeys the list too",
      not exported(refdes="A4", installed=False))
check("...and is exported when the variant does install it",
      exported(refdes="A4", installed=True))
check("a symbol with no refdes is outside the list entirely",
      exported(refdes=None, installed=False))
check("NO_STEP_EXPORT removes it even so",
      not exported(refdes=None, installed=False, no_step_export=True))
check("NO_STEP_EXPORT wins over a variant that installs the part",
      not exported(**R3, installed=True, no_step_export=True))
check("absence from the variant drops it whatever the property says",
      not exported(**R3, installed=False, no_step_export=True))
check("with no variant table nothing is dropped",
      exported(**R3, installed=False, has_table=False))

# The transliteration above is only as good as its resemblance to the source.
# These pin the two halves of the cond it models.
check("a table with no variant named subtracts nothing, rather than everything",
      exported(**R3, installed=False, variant=None))

# ALWAYS_STEP_EXPORT, the way out of the rule above. A wire-solder pad and a
# connector housing are indistinguishable in the database - refdes, a STEP
# model, no BOM line, named in no variant - so the pad has to say what it is.
check("a marked part survives a variant that does not install it",
      exported(refdes="X4", installed=False, always_export=True))
check("...and is still exported when the variant does install it",
      exported(refdes="X4", installed=True, always_export=True))
check("NO_STEP_EXPORT outranks it - never beats always",
      not exported(refdes="X4", installed=True, always_export=True,
                   no_step_export=True))
check("it changes nothing without a variant table",
      exported(refdes="X4", installed=False, always_export=True,
               has_table=False))

check("the exporter reads the property at all three levels, as NO_STEP_EXPORT does",
      len(re.findall(r"s3dObjectHasProp\(\s*\w+(?:->\w+)*\s+S3D_AlwaysExportProp\s*\)",
                     src)) == 3)
check("and tests it LAST, so it cannot rescue a NO_STEP_EXPORT symbol",
      re.search(r"!installed\[\s*upperCase\(\s*refdes\s*\)\s*\]\s*&&\s*\n?\s*"
                r"!s3dAlwaysStepExport\(\s*sym\s*\)", src))

print("\n[6b] the property has to be created before it can be attached")
# NO_STEP_EXPORT is one of Allegro's own; ALWAYS_STEP_EXPORT does not exist
# until something defines it, and a property dictionary belongs to a DESIGN -
# so defining it once at load would only ever reach the board open at that
# moment. Both call sites are what make it reach a board opened later.
launcher = (_ROOT / "simple3d.il").read_text(encoding="utf-8")
check("the dictionary entry is created as BOOLEAN",
      re.search(r'axlDBCreatePropDictEntry\(\s*S3D_AlwaysExportProp\s*"BOOLEAN"\s*t\s*\)',
                launcher))
calls = [m.start() for m in
         re.finditer(r"errset\(\s*s3dEnsureAlwaysProp\(\s*\)\s*\)", launcher)]
check("there are exactly two call sites", len(calls) == 2, str(len(calls)))
check("one is the open trigger",
      any(launcher.index("procedure( s3dOpenTrigger") < c
          < launcher.index("procedure( s3dExportCommand") for c in calls))
check("the other is in the export command, before the folder is resolved",
      any(launcher.index("procedure( s3dExportCommand") < c
          < launcher.index("designDir = s3dDesignDir()") for c in calls))
# NOTHING at load may touch the database. A load-time call stood here for one
# round and Allegro then crashed on startup, repeatedly, offering to recover a
# .sav; which statement did it was never established, and a tool that can stop
# the editor from starting cannot be debugged from. So the rule is blunt:
# loading these files defines procedures and sets variables, nothing else.
tail = launcher[launcher.index("axlCmdRegister("):]
check("nothing calls it at load time",
      "s3dEnsureAlwaysProp(" not in tail, tail[:200])
# Registering a trigger is not doing work: it asks to be called later, when a
# board is open and the database can be written to. `open` is one of the nine
# triggers this Allegro reports (axlTriggerSet(nil nil) -> open save close exit
# menu xprobe select window xsection).
check("the open trigger is registered at load, and cleared first",
      re.search(r"errset\(\s*axlTriggerClear\(\s*'open\s+'s3dOpenTrigger\s*\)\s*\)\s*\n"
                r"errset\(\s*axlTriggerSet\(\s*'open\s+'s3dOpenTrigger\s*\)\s*\)", launcher))
check("the trigger function takes exactly one argument, as triggers must",
      re.search(r"procedure\(\s*s3dOpenTrigger\(\s*\w+\s*\)", launcher))
check("and it cannot stop a board from opening",
      re.search(r"procedure\(\s*s3dOpenTrigger\([\s\S]{0,200}?"
                r"errset\(\s*s3dEnsureAlwaysProp\(\s*\)\s*\)", launcher))

print("\n[6c] a name is not a board")
# Started from its own icon, Allegro sometimes comes up on an empty placeholder
# instead of the previous design; the API answers every question about it, and
# editing it produces errors that make no sense. Nothing this tool writes may
# land there - that placeholder is the likeliest thing the load-time version
# was writing to when the editor began crashing on startup.
check("the export refuses a design with no board file behind it",
      re.search(r"unless\(\s*s3dRealDesign\(\s*\)", launcher))
check("the property is never defined on one either",
      re.search(r"unless\(\s*s3dRealDesign\(\s*\)\s+return\(\s*nil\s*\)\s*\)", launcher))
check("and the test is the drawing FILE, not just the name",
      re.search(r"procedure\(\s*s3dRealDesign\([\s\S]{0,600}?isFile\(\s*path\s*\)",
                launcher))
check("and the exporter compiles its regex on first use, not at load",
      re.search(r"^S3D_CtrlChars = 'unset", src, re.M)
      and re.search(r"procedure\(\s*s3dCtrlCharPattern", src))
# A silent errset is how the first version of this went missing entirely: the
# procedure had let-style locals, prog rejected it at call time, and the
# wrapper swallowed the error. errset returns nil ONLY on a fault - a genuine
# nil return arrives as (nil) - so the two are distinguishable, and now said.
check("the call does not swallow a failure",
      len(re.findall(r"unless\(\s*errset\(\s*s3dEnsureAlwaysProp\(\s*\)\s*\)\s*\n\s*s3dWarn\(",
                     launcher)) == 1)
check("and the procedure's own locals are bare symbols, as prog demands",
      re.search(r"prog\(\s*\(\s*dict\s+found\s+name\s+made\s*\)", launcher))
check("the config switch can turn the whole thing off",
      "defineAlwaysExportProp" in launcher
      and re.search(r"unless\(\s*S3D_DefineAlwaysProp\s+return\(\s*nil\s*\)\s*\)",
                    launcher))
check("and false in the config really reads as false",
      re.search(r"S3D_DefineAlwaysProp\s*=\s*if\(\s*value\s*==\s*nil\s*then\s*nil\s*else\s*t\s*\)",
                launcher))

check("the exporter subtracts on the refdes alone, with no mechanical test",
      re.search(r"g_variantSymbolList\s*&&\s*t_variant\s*&&\s*refdes\s*&&\s*\n?\s*"
                r"!installed\[\s*upperCase\(\s*refdes\s*\)\s*\]", src))
check("s3dIsMechanical no longer decides an export",
      not re.search(r"!s3dIsMechanical\(\s*sym\s*\)", src))
check("a symbol with no refdes is what counts as outside the system",
      re.search(r"when\(\s*g_variantSymbolList\s*&&\s*!refdes", src))

print("\n[7] a variant that overrides properties on some components")
# A Variants.lst variant may carry, after its base list, one block per component
# whose properties this variant changes:
#
#     (C43 VALUE="12pF" JEDEC_TYPE="CAPC100X50X55L25N" TOL="1" )
#
# Those components ARE installed in that variant - they are just built from a
# different part. The refdes has to reach the variant's symbol list, or the new
# rule would drop a component the variant does install. The parser once appended
# the first PROPERTY token instead ("VALUE=12pF"), which is the bug fixed on
# 2026-07-22 and pinned here on the real line from the user's own file.
ALT = '\t\t(C43 VALUE="12pF" JEDEC_TYPE="CAPC100X50X55L25N" TOL="1" )\n'
STRIP = '"\t+\\()'                                   # the parser's own char class


def alternate_line(line):
    """The parser's awaitEndCondition branch: (refdes, ends_on_this_line)."""
    tokens = line.split(" ")                         # parseString, space-separated
    if len(tokens) <= 1:
        return None, False
    refdes = "".join(c for c in tokens[0] if c not in STRIP)
    properties = " ".join(tokens[1:])
    chunks = properties.replace('" ', "\\").split("\\")
    return refdes, chunks[-1] == ")\n"


refdes, ends = alternate_line(ALT)
check("the refdes is what reaches the symbol list", refdes == "C43", refdes)
check("not the first property", refdes != 'VALUE="12pF"')
check("and the block is seen to end on its own line", ends)
check("a continued block is not mistaken for a finished one",
      not alternate_line('\t\t(C43 VALUE="12pF" JEDEC_TYPE="CAPC\n')[1])

# The tokens the parser leaves behind: a bare "\n" from a line that ended in
# " )", which can never match a refdes but did land in the counts.
def is_refdes_token(tok):                            # s3dIsRefdesToken
    return isinstance(tok, str) and bool(re.search(r"[A-Za-z0-9]", tok))


check("a stray newline token is not a refdes", not is_refdes_token("\n"))
check("nor an empty one", not is_refdes_token(""))
check("C43 is", is_refdes_token("C43"))
check("the exporter filters them in both tables",
      re.search(r"procedure\(\s*s3dIsRefdesToken", src)
      and src.count("s3dIsRefdesToken(") >= 3)

print("\n[8] the whole board, written beside the variants")
# The variant list says what is INSTALLED; a drawing sometimes has to show the
# bare board instead. The path that writes it already existed - it is the
# no-variant branch - so this is about it being reached with a Variants.lst
# present, guarded, marked, and named so it cannot collide with a variant.
check("the full board is written with NO variant table, so only NO_STEP_EXPORT applies",
      re.search(r"when\(\s*S3D_ExportFullBoard[\s\S]{0,200}?"
                r"s3dSymbolsToExport\(\s*nil\s+nil\s*\)", src))
check("under the config switch",
      re.search(r'when\(\s*s3dJsonHas\(\s*settings\s+"exportFullBoard"\s*\)', src))
check("whose default is restored before every read, not left from the last board",
      re.search(r"S3D_ExportFullBoard = t\s*\n\s*S3D_NegativeLayers = "
                r"S3D_NegativeLayersDefault", src))
# ...and restored BEFORE the file is even looked for, so a board exported with
# no config beside it does not inherit the last board's settings either. Both
# globals, together, above the isFile branch.
check("and restored whether or not a config file is found",
      re.search(r"S3D_ExportFullBoard = t[\s\S]{0,200}?unless\(\s*t_file[\s\S]{0,200}?"
                r"if\(\s*isFile\(\s*t_file\s*\)", src))
check("the negative-layer list has a default to be restored to",
      re.search(r"S3D_NegativeLayersDefault = list\(", src)
      and re.search(r"S3D_NegativeLayers = S3D_NegativeLayersDefault", src))
check("it is named <design>.json, which no <design>_<variant> can collide with",
      re.search(r"when\(\s*S3D_ExportFullBoard[\s\S]{0,400}?"
                r"variantName = lowerCase\(\s*dsnName\s*\)", src))
check("and marked in the file rather than left to be guessed from its name",
      re.search(r'if\(\s*g_fullBoard\s+then\s+"\\"full_board\\": true', src))
check("the marker is a reserved key, or the reader walks it as a component",
      '"full_board"' in (_ROOT / "stepbuilder/core.py").read_text(encoding="utf-8")
      and re.search(r'_reserved = \([^)]*"full_board"',
                    (_ROOT / "stepbuilder/core.py").read_text(encoding="utf-8"), re.S))

# The Python half decides only whether a BATCH includes it. A file the user
# pointed at directly is never dropped: a checkbox that silently refuses the one
# file you selected is worse than one that appears to do nothing.
worker = (_ROOT / "stepbuilder/worker.py").read_text(encoding="utf-8")
check("a queued folder can leave the full-board file out",
      re.search(r"if len\(jobs\) > 1 and not settings\.build_full_board", worker))
check("but a single file chosen by hand is built anyway, and says so",
      re.search(r"elif len\(jobs\) == 1 and not settings\.build_full_board", worker))

# And the reader itself, on real files rather than on the source of it.
import json as _json
from stepbuilder.core import is_full_board, is_simple3d_json

FB = _OUT / "fullboard"
FB.mkdir(parents=True, exist_ok=True)
base = {"format": "simple3d", "format_version": 7, "pcb": {}}
(FB / "board.json").write_text(_json.dumps({**base, "name": "board",
                                            "full_board": True}))
(FB / "board_lsm.json").write_text(_json.dumps({**base, "name": "board_lsm"}))
(FB / "old.json").write_text(_json.dumps({**base, "name": "old"}))
(FB / "notours.json").write_text(_json.dumps({"hello": "world"}))

check("the marked file is recognised", is_full_board(FB / "board.json"))
check("a variant file is not", not is_full_board(FB / "board_lsm.json"))
check("nor an intermediate written before the key existed",
      not is_full_board(FB / "old.json"))
check("nor a json that is not ours at all", not is_full_board(FB / "notours.json"))
check("and the marker does not disturb the format check",
      is_simple3d_json(FB / "board.json"))
check("a missing file is False, not an exception",
      not is_full_board(FB / "no_such_file.json"))

print("\n[9] the cutout list is copied per export, not shared")
# makePcbContour runs ONCE and its result is handed to every export of the run.
# create3dIntermediateFormat then appends that export's pin holes to it with
# tconc, which mutates IN PLACE - so with an alias the holes stayed in the list
# and the next file got them again. The first file written was right and every
# one after it carried one more copy. Found on 8231-a2 (2026-08-11), where the
# whole-board file had the two slot holes twice and OCC answered a coincident
# pair of prisms with an empty result: no board body in the STEP, no error.


class Tconc:
    """SKILL's tconc structure - (list . last-cell). car() is the list."""

    def __init__(self, first):
        self.items = [first]

    def car(self):
        return self.items


def tconc(structure, item):
    """Destructive, exactly as SKILL's is."""
    structure.items.append(item)
    return structure


def one_export(edge_cuts, holes, share):
    """The cut half of create3dIntermediateFormat: share=True is the old bug."""
    cuts = None
    if edge_cuts[1]:
        if share:
            cuts = edge_cuts[1]                       # cuts = cadr( edgeCuts )
        else:
            for base in edge_cuts[1].car():           # foreach over car( cadr( ... ) )
                cuts = Tconc(base) if cuts is None else tconc(cuts, base)
    if holes:
        cuts = tconc(cuts, holes) if cuts is not None else Tconc(holes)
    return list(cuts.car()) if cuts is not None else []


def session(share, exports=3):
    """One run: makePcbContour once, then N files out of the same edgeCuts."""
    edge_cuts = [None, Tconc("cutoutA")]
    tconc(edge_cuts[1], "cutoutB")
    return [one_export(edge_cuts, "PINHOLES", share) for _ in range(exports)]


shared = session(share=True)
check("the alias reproduces the bug: the first file is right",
      shared[0].count("PINHOLES") == 1, shared[0])
check("the second file already has the holes twice",
      shared[1].count("PINHOLES") == 2, shared[1])
check("and the whole-board file, written last, three times",
      shared[2].count("PINHOLES") == 3, shared[2])

copied = session(share=False)
check("the copy gives every file the same contours",
      all(f == copied[0] for f in copied), copied)
check("each with its holes exactly once",
      all(f.count("PINHOLES") == 1 for f in copied), copied)
check("and the board's own cutouts still there, in order",
      copied[0] == ["cutoutA", "cutoutB", "PINHOLES"], copied[0])
check("a board with no cutouts at all still exports its holes",
      one_export([None, None], "PINHOLES", False) == ["PINHOLES"])
check("and one with neither exports nothing rather than failing",
      one_export([None, None], None, False) == [])

check("the source copies the list instead of aliasing it",
      re.search(r"foreach\(\s*baseCut\s+car\(\s*cadr\(\s*edgeCuts\s*\)\s*\)", src))
# Whole-line comments only - the FIX note above the fix quotes the old line, and
# a naive search finds it there.
code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith(";"))
check("the alias is gone", not re.search(r"cuts\s*=\s*cadr\(\s*edgeCuts\s*\)", code))

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
