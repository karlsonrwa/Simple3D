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

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
