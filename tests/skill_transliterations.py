"""The Python copies of SKILL procedures the suites test against, in one place.

Each one mirrors a procedure of the exporter (the `mirrors` line above it
names the part and the procedure) closely enough that the suite checks the
Python copy and, where it can, greps the SKILL source for the same shape - a
copy that drifts from its original is the risk, and a reader who changes the
SKILL has one file to update. Cut verbatim out of the suites that carried
them in round 80 (plan F2); every suite imports what it used to define. Not a
suite itself - run_all.py runs test_*.py only.
"""
import math
import re


# mirrors skill/s3d_json.il: s3dJsonQuote (and its control-character class)
def s3dJsonQuote(value):
    if not isinstance(value, str):
        return "null"
    out = '"'
    for c in value:
        if c == '"':
            out += '\\"'
        elif c == '\\':
            out += '\\\\'
        elif c == '\t':
            out += '\\t'
        elif c == '\n':
            out += '\\n'
        elif c == '\r':
            out += '\\r'
        elif _is_other_control(c):
            # SKILL has no verified way to turn a character into its code here,
            # so \u00XX cannot be built; the character is replaced instead. The
            # point of the branch is that the FILE still parses.
            out += ' '
        else:
            out += c
    return out + '"'


def _is_other_control(c):
    """The SKILL side's [\\x01-\\x08\\x0b\\x0c\\x0e-\\x1f], as a predicate."""
    n = ord(c)
    return 0x01 <= n <= 0x1f and c not in "\t\n\r"


# mirrors skill/s3d_export.il: symbolReturn3DElements (placement), the header of create3dIntermediateFormat; skill/s3d_silk.il: s3dWriteSilkPolys (silk_poly), s3dWriteSilkscreen (silk_warnings)
# ---- the fragments, as the SKILL writes them ------------------------------ #

def placement(refDes, stepFileName, zoneName):
    """symbolReturn3DElements' block: the key, step_name and zone."""
    return (s3dJsonQuote(refDes) + ': {\n'
            '\t"step_mapping": {\n'
            '\t\t"step_name": ' + s3dJsonQuote(stepFileName) + ',\n'
            '\t\t"rotation_x": 0.000000,\n'
            '\t\t"offset_z": 0.000000\n'
            '\t},\n'
            '\t"zone": ' + s3dJsonQuote(zoneName) + ',\n'
            '\t"x": 1.000000\n'
            '}')


def silk_poly(layer):
    """s3dWriteSilkPolys' per-polygon object, the layer line as written."""
    return '\t\t\t{\n\t\t\t\t"layer": %s,\n\t\t\t\t"vertices": [\n[0.0, 0.0]\n\t\t\t\t]\n\t\t\t}' % s3dJsonQuote(layer)


def silk_warnings(messages):
    """s3dWriteSilkscreen's warnings array."""
    return '\t\t"warnings": [\n' + ',\n'.join('\t\t\t' + s3dJsonQuote(m) for m in messages) + '\n\t\t]'


def header(variantName, models):
    """create3dIntermediateFormat's header with s3dEmbeddedModelsJson's list."""
    return ('"format": "simple3d",\n"format_version": 9,\n'
            '"name": ' + s3dJsonQuote(variantName) + ',\n'
            '"embedded_models": [' + ', '.join(s3dJsonQuote(m) for m in models) + ']')


# mirrors skill/s3d_util.il: s3dAddIndent; skill/s3d_export.il: makePcb, create3dIntermediateFormat (the member list and the re-indent)
def s3dAddIndent(text, levels=1):
    pad = "\t" * levels
    return "\n".join(pad + line for line in text.split("\n") if line != "")


def makePcb(thicknesses, edges, cuts, color):
    arrays = ["[\n" + s3dAddIndent(",\n".join(edges)) + "\n]"]
    if cuts:
        arrays += cuts
    # "thickness" is optional since v9 (round 79, E2): nil when no stackup is the board
    thick = ('\t"thickness": {\n\t\t"soldermask_top": %f,\n\t\t"board": %f,\n\t\t"soldermask_bottom": %f\n\t},\n' % thicknesses
             if thicknesses else "")
    return ('"pcb": {\n' + thick
            + s3dAddIndent('"color": {\n\t"r": %f,\n\t"g": %f,\n\t"b": %f\n}' % color)
            + ',\n\t"edges": [\n' + s3dAddIndent(",\n".join(arrays), 2) + "\n\t]\n}")


def create3dIntermediateFormat(variantName, full_board, edges, cuts, placements, silk):
    members = ['"format": "simple3d"', '"format_version": 9', '"name": ' + s3dJsonQuote(variantName)]
    if full_board:
        members.append('"full_board": true')
    members += ['"embedded_models": []', '"stackups": {\n}', '"zones": []', '"bends": []']
    members.append(makePcb((0.025, 1.054, 0.025), edges, cuts, (0.0, 0.4, 0.0)))
    # v9: one "components" object, {} when there is none (round 79, E1)
    members.append('"components": {\n' + s3dAddIndent(",\n".join(placements)) + "\n}" if placements
                   else '"components": {}')
    body = ",\n".join(members)
    if silk:
        body += ","
    out = "{\n" + "".join("\t" + line + "\n" for line in body.split("\n") if line != "")
    if silk:
        out += '\t"silkscreen": {\n\t\t"thickness": 0.025,\n\t\t"top": [\n\t\t],\n\t\t"bottom": [\n\t\t]\n\t}\n'
    return out + "}\n"


# mirrors skill/s3d_geometry.il: rotateXY, s3dDrillXY
# --------------------------------------------------------------------------- #
# the transliteration
# --------------------------------------------------------------------------- #

def rotateXY(origin, xy, angle):
    rad = math.radians(angle)
    dx = xy[0] - origin[0]
    dy = xy[1] - origin[1]
    return [origin[0] + dx * math.cos(rad) - dy * math.sin(rad),
            origin[1] + dx * math.sin(rad) + dy * math.cos(rad)]


def s3dDrillXY(pin_xy, pin_rotation, drill_offset):
    """pin->xy, pin->rotation, padstack->drillOffset."""
    dx = dy = 0.0
    if drill_offset is not None:
        if isinstance(drill_offset[0], (int, float)):
            dx = drill_offset[0]
        if isinstance(drill_offset[1], (int, float)):
            dy = drill_offset[1]
    if not isinstance(pin_rotation, (int, float)):
        pin_rotation = 0.0
    if dx == 0.0 and dy == 0.0:
        return pin_xy
    return rotateXY(pin_xy, [pin_xy[0] + dx, pin_xy[1] + dy], pin_rotation)


# mirrors skill/s3d_util.il: s3dDesignFolder, s3dVariantFilePath
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


# mirrors skill/s3d_variants.il: s3dVariantFit (the three answers)
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


# mirrors skill/s3d_variants.il: s3dSymbolsToExport's cond, for one symbol
def exported(*, refdes, installed, has_table=True, no_step_export=False,
             always_export=False, variant="ALL"):
    """s3dSymbolsToExport's cond, for one symbol."""
    if no_step_export:
        return False
    if has_table and variant and refdes and not installed and not always_export:
        return False
    return True


# mirrors skill/s3d_variants.il: gdsysGetVariantInfo's awaitEndCondition branch (alternate_line)
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


# mirrors skill/s3d_variants.il: s3dIsRefdesToken
# The tokens the parser leaves behind: a bare "\n" from a line that ended in
# " )", which can never match a refdes but did land in the counts.
def is_refdes_token(tok):                            # s3dIsRefdesToken
    return isinstance(tok, str) and bool(re.search(r"[A-Za-z0-9]", tok))


# mirrors SKILL's tconc structure, destructive as the real one (skill/s3d_export.il uses it for the cutout list)
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


# mirrors skill/s3d_json.il: s3dJsonMerge
def skill_merge(base, over):
    """s3dJsonMerge, in Python.

    Objects merge; anything else is replaced whole. Presence of the key
    decides, never truthiness - false is a setting, not an absence.
    """
    if not isinstance(over, dict) or not isinstance(base, dict):
        return over
    out = dict(base)
    for key, value in over.items():
        out[key] = skill_merge(base[key], value) if key in base else value
    return out


# mirrors skill/s3d_stackup.il: s3dLayerInBody (what the name and the function say)
# what the SKILL filter keeps, transliterated
def in_body(nm, fn):
    probe = (nm or "").upper() + " " + (fn or "").upper()
    return not ("SILK" in probe or "PASTE" in probe)
