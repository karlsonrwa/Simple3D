# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, OUT, fails, check, exporter_source

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
import re, shutil, sys

from skill_transliterations import (Tconc, VariantFileError, alternate_line, exported,
                                    is_refdes_token, not_placed, parse_variants,
                                    s3d_design_folder, s3d_variant_file_path, tconc,
                                    variant_file_clashes, variant_file_name, variant_fit)


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
# Rebuilt from parseString's pieces, \\server\share\boards comes back as
# server/share/boards - a relative folder - which is why the SKILL scans for
# the last separator instead. A check here used to work that rebuild out of a
# literal and find it broken, which no change to the product could alter
# (review 23.10.2026, R2-9); what holds the product is its source.
src = exporter_source()
unc = r"\\server\share\boards\flex2-a0.brd"
folder = re.search(r"^procedure\( s3dDesignFolder\(.*?(?=^procedure\()", src, re.S | re.M)
folder_code = "\n".join(line.split(";")[0] for line in (folder.group(0) if folder else "").splitlines())
check("s3dDesignFolder cuts the path by scanning it, with no parseString in it",
      folder is not None and "parseString(" not in folder_code and "substring( full i 1 )" in folder_code,
      folder_code[:240])
check("the scan keeps them", s3d_design_folder(unc) == r"\\server\share\boards")

print("\n[4] the SKILL source still says the same thing")
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
# Since 2026-09-03 the first is named and WRITTEN rather than refused: a
# variant that installs nothing is also how the schematic asks for the bare
# board (every part set to not installed), and the file cannot say which.


check("a list that installs nothing is named as such",
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
empty_branch = re.search(r"when\(\s*nKnown == 0[\s\S]*?return\(\s*t\s*\)", src)
check("...and goes on to the export with a warning, not an error",
      empty_branch and "s3dWarn(" in empty_branch.group(0) and "error(" not in empty_branch.group(0),
      empty_branch and empty_branch.group(0)[:80])
check("the foreign file still stops the export rather than exporting something wrong",
      re.search(r'onBoard == 0\)[\s\S]{0,40}?error\(\s*"%s"\s+strcat\(', src))
check("a file with no variant shape at all stops it too",
      re.search(r"variantCount == 0[\s\S]{0,40}?error\(\s*strcat\(", src))

print("\n[6] who obeys the variant list, and who is outside it")
# The rule, settled by the user on 2026-08-03: a refdes is what makes a part
# nameable in a Variants.lst, so the list governs EVERYTHING that has one -
# mechanical or not. A symbol without a refdes can never be named there, so only
# NO_STEP_EXPORT can remove it. Two earlier rules stood here and each was wrong
# on the other's case: "the list IS the export list" lost mechanical parts;
# "subtract only what is not mechanical" kept a MECHANICAL-class MOLEX housing
# (A1/A2/A4 on variants_test-b0) in variants that do not install it.


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
launcher = (ROOT / "simple3d.il").read_text(encoding="utf-8")
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
refdes, _, ends = alternate_line(ALT)
check("the refdes is what reaches the symbol list", refdes == "C43", refdes)
check("not the first property", refdes != 'VALUE="12pF"')
# parseString breaks the "\n" off a line's last piece, so a block closed on
# its own line ends in ")". Until round 119 the parser looked for ")\n" there,
# which never came: a one-line block was closed by the line after it - the
# blank one Capture writes - or, with none, never (Allegro 25.1, round 118).
check("a one-line block is closed on its own line", ends)
USERS = (ROOT / "tests/fixtures/variants/v6-users-alternate-line.lst").read_bytes().decode("ascii")
check("and in a file of the user's shape the part is installed",
      parse_variants(USERS).get("A", [])[-1:] == ["C43"], parse_variants(USERS))
check("a continued block is not mistaken for a finished one",
      not alternate_line('\t\t(C43 VALUE="12pF" JEDEC_TYPE="CAPC\n')[2])
# The copy above is held to Allegro's own answers; this holds the SKILL to
# the fix itself, in both branches that close a block (R2-9: reverted in
# both, every suite had stayed green). Whole-line comments off - the FIX note
# quotes the old line.
code = "\n".join(line for line in src.splitlines() if not line.lstrip().startswith(";"))
check("and the SKILL appends the refdes, not the first property, wherever a block ends: "
      "on its line, after its wrapped lines, and where its variant or the next block ends it",
      code.count("symbols = nconc( symbols list( refDes ) )") == 3
      and "list( nth( 0 subStrings ) )" not in code,
      code.count("symbols = nconc( symbols list( refDes ) )"))

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
                r"s3dSymbolsToExport\(\s*nil\s+nil(\s+state)?\s*\)", src))
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
      # the member list of round 77 (D8): `when( g_fullBoard` adds the marker
      re.search(r'when\(\s*g_fullBoard[\s\S]{0,120}?"\\"full_board\\": true', src))
check("the marker is a reserved key, or the reader walks it as a component",
      re.search(r'RESERVED = \([^)]*"full_board"',
                (ROOT / "stepbuilder/intermediate.py").read_text(encoding="utf-8"), re.S))
check("and the exporter's NOTE points at that tuple, not at a name that moved",
      re.search(r"RESERVED[\s\S]{0,40}stepbuilder/intermediate\.py", src))

# The Python half decides only whether a BATCH includes it. A file the user
# pointed at directly is never dropped: a checkbox that silently refuses the one
# file you selected is worse than one that appears to do nothing. One rule,
# intermediate.batch_jobs, for the window and the CLI (round 73, plan A10).
from stepbuilder.intermediate import Intermediate, batch_jobs
full = Intermediate("board.json", {"format": "simple3d", "full_board": True})
var = Intermediate("board_lsm.json", {"format": "simple3d"})
said = []
# said[-1] on an empty list RAISES, and the failure these checks exist for is
# exactly the one that leaves it empty: the suite then ends with a traceback
# instead of naming the rule that broke (measured 2026-09-22, mutation
# intermediate-single-full-board-kept - "exit 1" and not one FAIL line).
last = lambda: said[-1] if said else ""
check("a queued folder can leave the full-board file out",
      batch_jobs([full, var], False, said.append) == [var] and "Not building" in last(), said)
said.clear()
check("and keeps it when asked to", batch_jobs([full, var], True, said.append) == [full, var] and not said)
check("but a single file chosen by hand is built anyway, and says so",
      batch_jobs([full], False, said.append) == [full] and "despite" in last(), said)
worker = (ROOT / "stepbuilder/worker.py").read_text(encoding="utf-8")
cli = (ROOT / "stepbuilder/__main__.py").read_text(encoding="utf-8")
check("the window's worker and the CLI both go through that one rule",
      "batch_jobs(" in worker and "batch_jobs(" in cli and "--no-full-board" in cli)

# And the reader itself, on real files rather than on the source of it.
import json as _json
from stepbuilder.core import is_full_board, is_simple3d_json

FB = OUT / "fullboard"
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

# The class behind those wrappers (round 72, plan A2): one parse, every answer.
from stepbuilder.core import resolve_json_jobs
from stepbuilder.intermediate import RESERVED, Intermediate, resolve_jobs
inter = Intermediate.probe(FB / "board.json")
check("probe parses once and answers both questions",
      inter is not None and inter.is_simple3d and inter.is_full_board)
check("a foreign json probes as not ours, not as an error",
      Intermediate.probe(FB / "notours.json").is_simple3d is False)
check("a missing file probes as None", Intermediate.probe(FB / "no_such_file.json") is None)
raw = {"name": "n", "pcb": {}, "format": "simple3d", "R1": {}, "silkscreen": {},
       "full_board": True, "J1": {}}
check("components are what is left after the reserved keys",
      Intermediate(FB / "x.json", raw).components == {"R1": {}, "J1": {}})
check("and metadata is exactly the reserved keys present",
      set(Intermediate(FB / "x.json", raw).metadata) == set(raw) - {"R1", "J1"}
      and set(Intermediate(FB / "x.json", raw).metadata) <= set(RESERVED))
jobs, ignored = resolve_jobs(FB)
check("resolve_jobs hands back parsed intermediates, in resolve_json_jobs' order",
      [j.path for j in jobs] == resolve_json_jobs(FB)[0]
      and ignored == [FB / "notours.json"], (jobs, ignored))
check("a job that read as the whole board says so without a second parse",
      [j.path.name for j in jobs if j.is_full_board] == ["board.json"])

print("\n[9] the cutout list is copied per export, not shared")
# makePcbContour runs ONCE and its result is handed to every export of the run.
# create3dIntermediateFormat then appends that export's pin holes to it with
# tconc, which mutates IN PLACE - so with an alias the holes stayed in the list
# and the next file got them again. The first file written was right and every
# one after it carried one more copy. Found on 8231-a2 (2026-08-11), where the
# whole-board file had the two slot holes twice and OCC answered a coincident
# pair of prisms with an empty result: no board body in the STEP, no error.


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


# The model runs the way the SOURCE hands the list on - copied, or aliased as
# before 2026-08-11 - read off create3dIntermediateFormat, so its checks go
# red the day the alias is back. Until round 118 it ran on a switch the test
# set itself, and eight checks could not fail whatever the .il did (review
# 23.10.2026, R2-9). Whole-line comments off: the FIX note quotes the old line.
code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith(";"))
copies = bool(re.search(r"foreach\(\s*baseCut\s+car\(\s*cadr\(\s*edgeCuts\s*\)\s*\)", code))
aliases = bool(re.search(r"cuts\s*=\s*cadr\(\s*edgeCuts\s*\)", code))
check("the source copies the list instead of aliasing it", copies and not aliases,
      (copies, aliases))
runs = session(share=aliases)
shared = session(share=True)
check("so every file gets the same contours, each with its holes once - where the alias "
      "gave the second file two and the whole-board file three",
      all(f == runs[0] for f in runs) and all(f.count("PINHOLES") == 1 for f in runs)
      and [f.count("PINHOLES") for f in shared] == [1, 2, 3], (runs, shared))
check("and the whole-board file, written last, has the board's own cutouts in order",
      runs[-1] == ["cutoutA", "cutoutB", "PINHOLES"], runs[-1])
# The two ends of the list the model has from the source too: the holes start
# the list when there is no cutout, and an unbound list is written as none.
starts = bool(re.search(r"when\(\s*cut\s+if\(\s*boundp\(\s*'cuts\s*\)\s+then\s+tconc\(\s*cuts\s+cut\s*\)"
                        r"\s+else\s+cuts\s*=\s*tconc\(\s*nil\s+cut\s*\)", code))
check("a board with no cutouts at all still exports its holes: they start the list",
      starts and one_export([None, None], "PINHOLES", aliases) == ["PINHOLES"], starts)
unbound = bool(re.search(r"if\(\s*boundp\(\s*'cuts\s*\)\s+then\s+cuts\s+else\s+nil\s*\)", code))
check("and one with neither writes no list rather than failing on an unbound one",
      unbound and one_export([None, None], None, aliases) == [], unbound)

print("\n[10] a name Allegro wrote in the Windows code page is read, not crashed on")
# SKILL writes text as the bytes it holds - on a Russian Windows, cp1251 - and
# the reader asked for UTF-8 alone. A board named in Cyrillic (Allegro 25.1
# opens one from a Cyrillic FOLDER; the name itself still trips it at exit)
# or a model file named in Cyrillic produced a JSON the reader crashed on:
# UnicodeDecodeError is a ValueError, and neither read nor probe caught it,
# so the window's job list died with a traceback (round 78).
from stepbuilder.intermediate import ANSI_CODEPAGE, read_json_text
CYR = OUT / "cyrillic"
CYR.mkdir(parents=True, exist_ok=True)
name = "плата-а0"
ansi = ('{"format": "simple3d", "format_version": 8, "name": "' + name
        + '", "pcb": {}, "R1": {"step_mapping": {"step_name": "конденсатор.stp"}}}').encode("cp1251")
(CYR / "ansi.json").write_bytes(ansi)
(CYR / "utf8.json").write_text(ansi.decode("cp1251"), encoding="utf-8")
(CYR / "bom.json").write_bytes(b"\xef\xbb\xbf" + ansi.decode("cp1251").encode("utf-8"))
read = Intermediate.read(CYR / "ansi.json")
check("the ANSI file reads, and the name comes back as the Russian string",
      read.data["name"] == name and read.data["R1"]["step_mapping"]["step_name"] == "конденсатор.stp", read.data["name"])
check("and the intermediate says which code page it was", read.encoding == ANSI_CODEPAGE, read.encoding)
check("a UTF-8 file reads as before, and says so",
      Intermediate.read(CYR / "utf8.json").data["name"] == name and Intermediate.read(CYR / "utf8.json").encoding == "utf-8")
check("a UTF-8 file with a BOM too", Intermediate.read(CYR / "bom.json").data["name"] == name)
check("probe does not crash on it either", Intermediate.probe(CYR / "ansi.json") is not None
      and Intermediate.probe(CYR / "ansi.json").data["name"] == name)
check("the folder scan keeps the file", any(j.path.name == "ansi.json" for j in resolve_jobs(CYR)[0]))
text, enc = read_json_text(CYR / "ansi.json")
check("read_json_text names the fallback", enc == ANSI_CODEPAGE and name in text)

print("\n[11] a path outside ASCII is said, not refused")
from stepbuilder.intermediate import path_notes
check("ASCII paths: nothing to say", path_notes(["D:/lib", "D:/lib2"], "D:/x.json", "D:/out") == [])
notes = path_notes(["D:/lib", "D:/Плата №1/библиотека"], "D:/Плата №1/cad/board.json", "D:/out")
check("one line per path with such characters, naming it",
      len(notes) == 2 and "библиотека" in notes[0] and "STEP folder" in notes[0] and "JSON" in notes[1], str(notes))
check("a warning, so the window colours it", all(n.startswith("warning:") for n in notes))

print("\n[12] a variant with no (base block: every part set to not installed")
# Capture writes no (base block when a variant installs nothing - the user's
# way of asking for the bare board (2026-09-03). The parser waited for "(base"
# for the rest of the file, registered no variant, and the export refused the
# file as another project's. Now the variant closing - or an alternate-part
# block opening - with no base seen is an empty base list.
EMPTY = '(\r\n\t("BOM"\r\n\r\n\t)\r\n\r\n\r\n)\r\n'        # verbatim, as the user made it
# An alternate-part block is closed by the line after it (see [7]), and
# Capture writes a blank one there; NORMAL and ALT_ONLY carry it. Until round
# 118 they did not, and passed only because the copy closed a block on its own
# line, which the parser does not.
NORMAL = ('(\n\t("V1"\n\t\t(base\n\t\t\tC1 C2 \n\t\t\tR1 \n\t\t)\n'
          '\t\t(C43 VALUE="12pF" TOL="1" )\n\n\t)\n)\n')
STUB = '(\n\t("dummy"\n\t\t(base\n\t\t)\n\t)\n)\n'
ALT_ONLY = '(\n\t("V2"\n\t\t(C43 VALUE="12pF" TOL="1" )\n\n\t)\n)\n'
BOTH = '(\n\t("V1"\n\t\t(base\n\t\t\tC1 C2 \n\t\t)\n\t)\n\t("BOM"\n\n\t)\n)\n'
# Capture's real shape, byte for byte from the user's probe file: the base
# list on one line inside its own parentheses, blank lines around the blocks.
CAPTURE = ('(\r\n\t("BOM"\r\n\r\n\t\t(base\r\n\t\t\t(VT1 VT2 VT3 VT4 X1 X2 )\r\n\t\t)\r\n'
           '\r\n\t)\r\n\r\n\r\n)\r\n')


def refdes_of(table, name):
    return [t for t in table[name] if is_refdes_token(t)]


got = parse_variants(EMPTY)
check("the user's file parses to one variant", list(got) == ["BOM"], got)
check("...that installs nothing", refdes_of(got, "BOM") == [])
got = parse_variants(NORMAL)
check("a normal file still parses: the base parts and the alternate",
      refdes_of(got, "V1") == ["C1", "C2", "R1", "C43"], got)
check("the stub with an empty base list parses as it did",
      parse_variants(STUB) == {"dummy": []}, parse_variants(STUB))
check("an alternate part with no base list before it is installed on its own",
      refdes_of(parse_variants(ALT_ONLY), "V2") == ["C43"], parse_variants(ALT_ONLY))
got = parse_variants(BOTH)
check("a full variant and an empty one in one file are both found",
      set(got) == {"V1", "BOM"} and refdes_of(got, "V1") == ["C1", "C2"] and refdes_of(got, "BOM") == [],
      got)
got = parse_variants(CAPTURE)
check("Capture's own shape: the six refdes, in order",
      refdes_of(got, "BOM") == ["VT1", "VT2", "VT3", "VT4", "X1", "X2"], got)
# Round 52's memo reasoned that a line ending in " )" leaves a bare "\n"
# token, and this check held the copy to it; Allegro 25.1's parseString breaks
# at a line end as at a space, and its parser left no such token in any of the
# files of tests/fixtures/variants (round 118).
check("...and no stray token beside them: parseString breaks the line end off",
      got["BOM"] == ["VT1", "VT2", "VT3", "VT4", "X1", "X2"], got)
# Without the blank line, until round 119 the block's end was looked for down
# to the end of the file, and that variant and every one after it were lost
# (Allegro 25.1 on tests/fixtures/variants v10 and v11, round 118).
lost = NORMAL.replace(' )\n\n\t)', ' )\n\t)')
check("without the blank line after a block the variant is still found, and the next with it",
      parse_variants(lost) == {"V1": ["C1", "C2", "R1", "C43"]}
      and parse_variants(lost.replace(")\n)\n", ")\n\t(\"V9\"\n\t\t(base\n\t\t\tR9 \n\t\t)\n\n\t)\n)\n"))
      == {"V1": ["C1", "C2", "R1", "C43"], "V9": ["R9"]},
      parse_variants(lost))
check("the SKILL parser has the same branch, ahead of its case",
      re.search(r'when\(\s*\(state == "awaitStartCondition"\)\s*&&[\s\S]{0,200}?'
                r'pcreMatchp\(\s*propertyStart line\s*\)\s*\)\s*\n\s*symbols = list\(\)', src))
check("and closes the file it opened before it refuses a name given twice, or returns"
      " - it stayed locked until Allegro exited",
      re.search(r"close\(\s*inPort\s*\)\s*\n\s*when\(\s*repeated\s*\n\s*error\([\s\S]{0,700}?\)\s*\)\s*\n"
                r"\s*\)\s*\n\s*list\(\s*variantTable alternateParts\s*\)", src))

print("\n[13] a variant naming components that are not on the board")
# The list comes from the schematic and the board from Allegro; a refdes in
# one and not the other is a revision mismatch. The export used to say
# nothing: "covers 1 of 48" counts from the board's side only. Now each
# variant says which of its refdes the board does not have - in the console,
# and in the file, so the window's log repeats it (2026-09-03; the user's
# probe listed VT1-VT4, X1, X2 on variants_test-b0, where one is placed).
check("the ones the board lacks, by name, case-blind, stray tokens dropped",
      not_placed(["X2", "VT1", "vt3", "\n"], ["x2", "R1"]) == ["VT1", "VT3"])
check("nothing to say when every one is placed", not_placed(["R1"], ["R1", "R2"]) == [])
check("a board with no refdes at all lacks them all", not_placed(["R1"], []) == ["R1"])
check("the export marks a listed refdes it meets",
      re.search(r"installed\[\s*upperCase\(\s*refdes\s*\)\s*\]\s*=\s*'placed", src))
check("...and reports what stayed unmet, per variant, to the console and the file",
      re.search(r"lists %d component\(s\) that are not on this board", src)
      and re.search(r"g_state\['warnings\]\s*=\s*cons\(\s*message", src))
check("the writer puts them in the file as \"warnings\"", re.search(r'"\\"warnings\\": \[', src))
check("reset before every export list is built, so a file does not inherit the last one's",
      len(re.findall(r"state\['warnings\]\s*=\s*nil", src)) >= 4)
from stepbuilder.intermediate import RESERVED
check("the reader reserves the key", "warnings" in RESERVED)
v9 = Intermediate("x.json", {"format": "simple3d", "format_version": 9, "name": "n",
                             "components": {"R1": {}}, "warnings": ["a"]})
check("...reads it back", v9.warnings == ["a"] and v9.components == {"R1": {}})
v8 = Intermediate("x.json", {"format": "simple3d", "format_version": 8, "name": "n", "R1": {}, "warnings": ["a"]})
check("and does not walk it as a component in the flat shape", v8.components == {"R1": {}} and v8.warnings == ["a"])
check("absent: an empty list, not a fault", Intermediate("x.json", {"name": "n"}).warnings == [])
# through generate(), the way the window and the CLI build
import json
from stepbuilder import core
fx = json.loads((ROOT / "tests/fixtures/demo_v9.json").read_text(encoding="utf-8"))
fx["warnings"] = ["variant BOM lists 2 component(s) that are not on this board: VT1, VT2"]
wf = OUT / "warned_v9.json"
wf.write_text(json.dumps(fx), encoding="utf-8")
lines = []
core.generate(step_dir=ROOT / "demo/step_files", json_file=wf, output_dir=OUT, log=lines.append)
check("the window's log repeats it, prefixed as a warning",
      any(l == "warning: " + fx["warnings"][0] for l in lines), lines[:6])

print("\n[14] no shape of block loses its part, its variant or the next one (round 119)")
# Every file of tests/fixtures/variants that the parser of round 118 lost
# something on - Allegro 25.1's own answers, recorded then - with what each
# holds. The parser of round 119 answers so in Allegro too (test_skill_pins [7]
# holds the copy to those answers); here they are written out, so a change
# that loses a part or a variant again fails by name.
LOST_BEFORE = {
    # a refdes alone on the block's first line: the part was not installed
    "v3-refdes-alone.lst": {"LSM": ["R1", "C43"]},
    "v19-refdes-alone-then-close.lst": {"ALONE": ["R1", "C43"]},
    # a one-line block with the variant's close straight after it: that
    # variant and every one after it were lost
    "v8-wrapped-three-lines.lst": {"W3": ["R1", "C43", "C44"]},
    "v10-block-then-close.lst": {"V1": ["C1", "C2", "R1", "C43"]},
    "v11-block-then-close-then-another.lst": {"V1": ["C1", "C2", "R1", "C43"], "V9": ["R9"]},
    "v12-alternate-only.lst": {"V2": ["C43"]},
    # two one-line blocks back to back: the second was read into the first
    "v15-two-blocks-back-to-back.lst": {"TWO": ["R1", "C43", "C44"]},
    # a block never closed the way the parser looks for: the variant's close,
    # or the next block, ends it
    "v16-wrapped-never-closed-then-close.lst": {"OPEN": ["R1", "C43"], "NEXT": ["R9"]},
    "v17-wrapped-never-closed-then-block.lst": {"OPEN": ["R1", "C43", "C44"]},
    # a base list with no close of its own: the next variant was read into it
    "v18-base-list-never-closed.lst": {"NOBASECLOSE": ["R1", "R2"], "NEXT": ["R9"]},
}
for name, want in LOST_BEFORE.items():
    got = parse_variants((ROOT / "tests/fixtures/variants" / name).read_bytes().decode("ascii"))
    check(f"{name}: {want}", got == want, got)

print("\n[15] every variant a file of its own (round 120)")
# Review 23.10.2026, R2-10: "Full" and "FULL" were written to one file, the
# later over the earlier, and the console said "3 variant(s) written". The
# cases of test_skill_pins [7], written out with what each gives - the copy
# answers there as Allegro did, and here the file system answers both: it is
# asked for real, as the SKILL asks it. Measured in Allegro 25.1 (31.10.2026):
# lowerCase folds Latin letters only, and Windows folds Cyrillic too.
clash_dir = OUT / "variant-clashes"
shutil.rmtree(clash_dir, ignore_errors=True)
clash_dir.mkdir(parents=True)
CYRILLIC = [w.encode("cp1251").decode("latin-1") for w in ("Полный", "ПОЛНЫЙ")]
CLASHES = [
    (["Full", "FULL", "ALT"], ['"Full" and "FULL" both go to brd_full.json']),
    (["full", "Full", "FULL"], ['"full" and "Full" both go to brd_full.json',
                                '"full" and "FULL" both go to brd_full.json']),
    # a character no file name takes is "_", so "Rev:A" meets "Rev_A"
    (["Rev:A", "Rev_A"], ['"Rev:A" and "Rev_A" both go to brd_rev_a.json']),
    (["Rev:A", "Rev:B"], []),
    # the file system's rule, not a string compare: the ".json" after the name
    # keeps a trailing space or dot apart
    (["a", "a "], []),
    (["x", "x."], []),
    (CYRILLIC, [f'"{CYRILLIC[0]}" and "{CYRILLIC[1]}" both go to brd_{CYRILLIC[0]}.json']),
]
for variants, want in CLASHES:
    got = variant_file_clashes(str(clash_dir), "brd", variants)
    shown = [v.encode("latin-1").decode("cp1251") for v in variants]
    check(f"{shown}: {len(want)} clash(es)", got == want, got)
check("and the check leaves nothing behind in the folder it was asked in",
      list(clash_dir.iterdir()) == [], list(clash_dir.iterdir()))
check("a name the file system holds apart is told apart, though lowerCase folds it",
      variant_file_name("brd", "FULL") == variant_file_name("brd", "Full")
      and variant_file_name("brd", CYRILLIC[0]) != variant_file_name("brd", CYRILLIC[1]))

# The export asks before it writes, and refuses: the source, where it does.
EXPORT = re.sub(r";.*", "", (ROOT / "skill/s3d_export.il").read_text(encoding="utf-8"))
asked_at = EXPORT.find("clashes = s3dVariantFileClashes( dir dsnName reverse( variantNames ) )")
written_at = EXPORT.find('printf( "Exporting .json for variant: %s\\n" variant )')
check("makeVariant3dIntermediates asks which variants would share a file before writing one",
      0 <= asked_at < written_at, (asked_at, written_at))
check("and an answer stops the export", re.search(r"when\( clashes\s+error\(", EXPORT) is not None)

print("\n[16] one name given to two variants (round 120)")
# The variant table keeps one entry per name: the later replaced the earlier,
# "1 variant(s) parsed", without a word (Allegro 25.1 on v20, 31.10.2026).
twice = (ROOT / "tests/fixtures/variants/v20-one-name-twice.lst").read_bytes().decode("latin-1")
try:
    parse_variants(twice)
    check("v20, \"Full\" twice: the parser refuses it", False, "it parsed")
except VariantFileError as e:
    check("v20, \"Full\" twice: the parser refuses it, naming the name and both lines",
          '"Full" (lines 2 and 9)' in str(e), str(e))
thrice = twice.replace(")\r\n)\r\n", ")\r\n\t(\"Full\"\r\n\t\t(base\r\n\t\t\t(R9 )\r\n\t\t)\r\n\t)\r\n)\r\n")
try:
    parse_variants(thrice)
    check("three times: refused", False, "it parsed")
except VariantFileError as e:
    check("three times: each repeat named", str(e).count('"Full" (lines 2 and') == 2, str(e))

print("\n[17] a file the reader does not know is refused, by name (round 121)")
# Review 23.10.2026, R3-2: validate() asked for neither "format" nor
# "format_version", and the CLI hands one file straight to generate(), past
# resolve_jobs. Measured on the 4090 (round 121) with the demo board under
# each: another program's JSON, versions 99, 13, 0, "abc", true and 12.0, and
# files without the marker or the version - all twelve built, not a word said;
# the CLI wrote demo.step with exit code 0; the window queued every file that
# carried the marker. Every path builds through validate(), so it is asked.
import contextlib, copy, io
from stepbuilder import __main__ as stepbuilder_cli
from stepbuilder.errors import StepBuilderError
import stepbuilder.intermediate as reader

written = re.search(r'"\\"format_version\\": (\d+)"', src)
newest = getattr(reader, "FORMAT_VERSION", None)
check(f"the reader knows exactly the newest version the exporter writes "
      f"({written.group(1) if written else '?'})",
      written is not None and newest == int(written.group(1)), (newest, written and written.group(0)))

demo = json.loads((ROOT / "demo/ap-214/demo.json").read_text(encoding="utf-8"))
check("the repository's own demo board says what it is (the first exporter's layout, v1)",
      demo.get("format") == "simple3d" and demo.get("format_version") == 1,
      (demo.get("format"), demo.get("format_version")))


def refusal(keys, drop=()):
    """What validate() says of the demo board with these keys set and those
    dropped: the message, or None when it is let through."""
    data = copy.deepcopy(demo)
    data.update(keys)
    for key in drop:
        data.pop(key, None)
    try:
        Intermediate("x.json", data).validate()
    except StepBuilderError as exc:
        return str(exc)
    return None


REFUSED = [
    # the review's four of round 1, its fifth of round 2, then the edges
    ("format_version 99", {"format_version": 99}, (), ["99", "newer"]),
    ("format_version \"abc\"", {"format_version": "abc"}, (), ["'abc'", "whole number"]),
    ("another program's format", {"format": "kicad"}, (), ["'kicad'", "not a Simple 3D"]),
    ("format_version 0", {"format_version": 0}, (), ["0", "no exporter"]),
    ("neither key", {}, ("format", "format_version"), ["no \"format\" marker"]),
    ("format_version 13, one past the newest", {"format_version": 13}, (), ["13", "newer"]),
    ("format_version true", {"format_version": True}, (), ["True", "whole number"]),
    ("format_version 12.0", {"format_version": 12.0}, (), ["12.0", "whole number"]),
    ("no format_version", {}, ("format_version",), ["no 'format_version'"]),
    ("no format, version 12", {"format_version": 12}, ("format",), ["no \"format\" marker"]),
]
for label, keys, drop, words in REFUSED:
    said = refusal(keys, drop)
    check(f"{label}: refused, the message naming it", said is not None
          and all(w in said for w in words), said)
taken = [v for v in range(1, (newest or 12) + 1) if refusal({"format_version": v}) is None]
check("and every version from 1 to the newest is still taken",
      taken == list(range(1, (newest or 12) + 1)), taken)

# Through the two doors the review named: generate(), and the CLI given one
# file - refused before anything is written.
gate = OUT / "unknown-format"
shutil.rmtree(gate, ignore_errors=True)
gate.mkdir(parents=True)
for tag, keys in (("fv99", {"format_version": 99}), ("kicad", {"format": "kicad"})):
    data = copy.deepcopy(demo)
    data.update(keys)
    jf = gate / f"{tag}.json"
    jf.write_text(json.dumps(data), encoding="utf-8")
    try:
        core.generate(step_dir=ROOT / "demo/step_files", json_file=jf, output_dir=gate,
                      output_name=tag, log=lambda m: None)
        said = None
    except StepBuilderError as exc:
        said = str(exc)
    check(f"generate() refuses {tag}.json and writes no STEP",
          said is not None and not (gate / f"{tag}.step").exists(), said)
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        rc = stepbuilder_cli.main([str(ROOT / "demo/step_files"), str(jf), str(gate / f"cli_{tag}")])
    check(f"and the CLI given {tag}.json alone exits 1, naming the file and why",
          rc == 1 and f"error ({tag}.json):" in err.getvalue()
          and not list((gate / f"cli_{tag}").glob("*.step")), (rc, err.getvalue()[-300:]))

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
