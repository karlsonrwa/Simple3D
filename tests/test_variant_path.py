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
# The rule this replaced only subtracted a refdes the table mentioned SOMEWHERE,
# which left a component the file never names - R3 on variants_test-b0 - in
# every variant. What separates R3 from a bracket is not whether the file
# mentions it: it is whether the part comes from the schematic at all.


def exported(*, refdes, in_netlist, sym_type, cls, installed, has_table=True):
    """s3dSymbolsToExport's cond, for one symbol."""
    mechanical = (not in_netlist
                  or (sym_type or "").upper() == "MECHANICAL"
                  or (cls or "").upper() == "MECHANICAL")
    if has_table and refdes and not mechanical and not installed:
        return False
    return True


R3 = dict(refdes="R3", in_netlist=True, sym_type="PACKAGE", cls="DISCRETE")
check("an electrical part the variant does not install is dropped",
      not exported(**R3, installed=False))
check("...and kept when it does",
      exported(**R3, installed=True))
check("a part the netlist has never heard of is kept",
      exported(refdes="A1", in_netlist=False, sym_type="PACKAGE", cls=None,
               installed=False))
check("a MECHANICAL-class part with a refdes is kept",
      exported(refdes="A1", in_netlist=True, sym_type="PACKAGE",
               cls="MECHANICAL", installed=False))
check("a MECHANICAL symbol with no refdes is kept",
      exported(refdes=None, in_netlist=False, sym_type="MECHANICAL", cls=None,
               installed=False))
check("with no variant table nothing is dropped",
      exported(**R3, installed=False, has_table=False))

check("the exporter tells the two apart by what the part IS",
      re.search(r"!s3dIsMechanical\(\s*sym\s*\)", src))
check("and being absent from the netlist is one of the ways",
      re.search(r"!comp\s*\|\|", src))

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

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
