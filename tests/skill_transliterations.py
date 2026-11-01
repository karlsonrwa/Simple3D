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


# mirrors skill/s3d_pads.il: s3dBoxesMeet
def s3dBoxesMeet(a, b):
    """Do two bounding boxes meet? Touching counts.

    The test that replaced axlAddSelectBox in the exposed-copper sweep
    (2026-09-14): the copper of a side is swept once and each polygon is
    matched to the openings its box meets, instead of asking Allegro for an
    interactive box select per opening. Touching counts because the AND that
    follows decides anyway, and a strict test would have to pick a tolerance.
    """
    if not a or not b:
        return True                    # no box to judge by: let the AND decide
    (ax0, ay0), (ax1, ay1) = a[0], a[1]
    (bx0, by0), (bx1, by1) = b[0], b[1]
    return not (ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0)


# mirrors skill/s3d_json.il: s3dJsonQuote  -- and its control-character class
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


# mirrors skill/s3d_export.il: symbolReturn3DElements, create3dIntermediateFormat; skill/s3d_silk.il: s3dWriteSilkPolys, s3dWriteSilkscreen
# -- placement; the header; silk_poly; silk_warnings
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


# mirrors skill/s3d_util.il: s3dAddIndent; skill/s3d_export.il: makePcb, create3dIntermediateFormat
# -- the member list and the re-indent
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


def create3dIntermediateFormat(variantName, full_board, edges, cuts, placements, silk, pads=False):
    members = ['"format": "simple3d"', '"format_version": 12', '"name": ' + s3dJsonQuote(variantName)]
    if full_board:
        members.append('"full_board": true')
    members += ['"embedded_models": []', '"stackups": {\n}', '"zones": []', '"bends": []']
    members.append(makePcb((0.025, 1.054, 0.025), edges, cuts, (0.0, 0.4, 0.0)))
    # v9: one "components" object, {} when there is none (round 79, E1)
    members.append('"components": {\n' + s3dAddIndent(",\n".join(placements)) + "\n}" if placements
                   else '"components": {}')
    body = ",\n".join(members)
    if silk or pads:
        body += ","
    out = "{\n" + "".join("\t" + line + "\n" for line in body.split("\n") if line != "")
    # v10 (round 85): the pads are streamed before the silkscreen and told
    # whether it follows - s3dWritePads
    if pads:
        out += ('\t"pads": {\n\t\t"padstacks": {\n\t\t\t"P1": {\n\t\t\t\t"usage": "Smd",\n'
                '\t\t\t\t"drill": null,\n\t\t\t\t"pads": {}\n\t\t\t}\n\t\t},\n'
                '\t\t"pins": [\n\t\t\t[1.0, 2.0, 0.0, false, "P1", "ETCH/TOP", "ETCH/TOP", "pin"]\n\t\t],\n'
                '\t\t"exposed": {\n\t\t\t"top": [\n\n\t\t\t],\n\t\t\t"bottom": [\n\n\t\t\t]\n\t\t},\n'
                '\t\t"bare": {\n\t\t\t"top": [\n\n\t\t\t],\n\t\t\t"bottom": [\n\n\t\t\t]\n\t\t}\n')
        out += "\t},\n" if silk else "\t}\n"
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


def s3dDrillXY(pin_xy, pin_rotation, drill_offset, mirrored=False):
    """pin->xy, pin->rotation, padstack->drillOffset, pin->isMirrored."""
    dx = dy = 0.0
    if drill_offset is not None:
        if isinstance(drill_offset[0], (int, float)):
            dx = drill_offset[0]
        if isinstance(drill_offset[1], (int, float)):
            dy = drill_offset[1]
    if not isinstance(pin_rotation, (int, float)):
        pin_rotation = 0.0
    if mirrored:                                  # flipped before it is turned (round 128)
        dx = -dx
    if dx == 0.0 and dy == 0.0:
        return pin_xy
    return rotateXY(pin_xy, [pin_xy[0] + dx, pin_xy[1] + dy], pin_rotation)


# mirrors skill/s3d_geometry.il: makeSlotAt
def make_slot_at(xy, rotation, width, height, flags=("true", "true")):
    """The slot makeSlotAt writes, as the intermediate's primitives: the
    first half circle, the left line, the second half circle, the right line,
    turned by *rotation* about *xy*. *flags* are the two arcs' ccw words as
    the SKILL spells them - test_skill_pins reads them out of the source, so
    this copy walks the slot the way the file does (round 128, R1-8)."""
    x, y = xy
    if width == height:
        return [{"type": "circle", "x": x, "y": y, "radius": width / 2}]
    if not height >= width:
        width, height = height, width
        rotation = rotation + 90.0
    radius = width / 2
    half = (height - width) / 2

    def turned(px, py):
        return rotateXY(xy, [px, py], rotation)

    return [{"type": "arc", "center": turned(x, y + half), "radius": radius,
             "alpha": math.fmod(0.0 + rotation, 360.0), "beta": math.fmod(180.0 + rotation, 360.0),
             "ccw": flags[0] == "true"},
            {"type": "segment", "start": turned(x - radius, y + half), "end": turned(x - radius, y - half)},
            {"type": "arc", "center": turned(x, y - half), "radius": radius,
             "alpha": math.fmod(180.0 + rotation, 360.0), "beta": math.fmod(360.0 + rotation, 360.0),
             "ccw": flags[1] == "true"},
            {"type": "segment", "start": turned(x + radius, y - half), "end": turned(x + radius, y + half)}]


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


# mirrors skill/s3d_util.il: s3dCmdExpands, s3dCmdDefined  -- what Windows' cmd would replace
CMD_OWN_NAMES = ("CD", "DATE", "TIME", "RANDOM", "ERRORLEVEL", "CMDEXTVERSION",
                 "CMDCMDLINE", "HIGHESTNUMANODENUMBER")


def s3d_cmd_defined(name, environ=None):
    """t if cmd would replace %name%: a variable by any case, one of cmd's
    own names, or a name beginning with "=". *environ* stands in for
    getShellEnvVar; the process environment by default."""
    import os
    env = os.environ if environ is None else environ
    folded = {k.upper() for k in env}
    return (name.upper() in folded or name[:1] == "="
            or name.upper() in CMD_OWN_NAMES)


def s3d_cmd_expands(text, environ=None):
    """The first "%NAME%" in *text* cmd would replace, or None - the SKILL
    scan, 1-based as it is: at a %, the next % closes a name; the part before
    a colon is the variable; an unknown one keeps the scan going from the
    closing %."""
    if not isinstance(text, str):
        return None
    n = len(text)
    i = 1
    while i <= n:
        if text[i - 1] == "%":
            j = i + 1
            while j <= n and text[j - 1] != "%":
                j += 1
            if j > n:
                return None
            name = text[i:j - 1] if j > i + 1 else ""
            base = name.split(":", 1)[0] if ":" in name else name
            if base != "" and s3d_cmd_defined(base, environ):
                return text[i - 1:j]
            i = j
        else:
            i += 1
    return None


# mirrors skill/s3d_variants.il: s3dVariantFit  -- the three answers
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


# mirrors skill/s3d_variants.il: s3dSymbolsToExport  -- its cond, for one symbol
def exported(*, refdes, installed, has_table=True, no_step_export=False,
             always_export=False, variant="ALL"):
    """s3dSymbolsToExport's cond, for one symbol."""
    if no_step_export:
        return False
    if has_table and variant and refdes and not installed and not always_export:
        return False
    return True


# mirrors SKILL's own parseString  -- no procedure of ours; skill/s3d_variants.il's parser stands on it
def parse_string(text, breaks=None):
    """parseString: the pieces between break characters, empty ones dropped.
    With no break characters given SKILL breaks at white space - space, tab,
    line feed and carriage return all, measured in Allegro 25.1 (round 118,
    test_skill_pins [7]) - so a line's last piece does not keep its "\\n"."""
    if breaks is None:
        return text.split()
    out, piece = [], ""
    for ch in text:
        if ch in breaks:
            if piece:
                out.append(piece)
            piece = ""
        else:
            piece += ch
    if piece:
        out.append(piece)
    return out


# mirrors skill/s3d_variants.il: gdsysGetVariantInfo  -- the awaitEndCondition branch (alternate_line)
# The parser's `pattern`, the SKILL's own text: in a character class "\(" is
# the paren, so the class holds no backslash - Allegro 25.1 keeps the one in
# "X\2" (round 118), where this copy used to strip it.
STRIP = '"\t+()'                                     # the characters the class takes
_STRIP = re.compile('["\t+\\()]')                    # pattern
_PROPERTY_SEPARATOR = re.compile('(" )')             # propertySeparator


def alternate_line(line):
    """The parser's awaitEndCondition branch on an alternate-part line with
    properties on it: (refdes, properties, ends_on_this_line), or
    (None, "", False) for a line with a refdes alone. A block ends on its line
    where its last piece, split at `" `, is ")" - parseString has broken the
    "\\n" off - or ")\\n". Until round 119 only ")\\n" was asked, which never
    came: a one-line block was closed by the line after it, or never
    (Allegro 25.1, round 118)."""
    tokens = parse_string(line)
    if len(tokens) <= 1:
        return None, "", False
    refdes = _STRIP.sub("", tokens[0])
    properties = " ".join(tokens[1:])                # buildString
    chunks = parse_string(_PROPERTY_SEPARATOR.sub(r"\\", properties), "\\")
    return refdes, properties, bool(chunks) and chunks[-1] in (")", ")\n")


# mirrors skill/s3d_variants.il: s3dIsRefdesToken
# The tokens the parser leaves behind: a bare "\n" from a line that ended in
# " )", which can never match a refdes but did land in the counts.
def is_refdes_token(tok):                            # s3dIsRefdesToken
    return isinstance(tok, str) and bool(re.search(r"[A-Za-z0-9]", tok))


# mirrors skill/s3d_variants.il: gdsysGetVariantInfo  -- its states, line by line, the wrapped-property branch included
_NEW_LINE = re.compile("\t\t")                       # newLine
_NEW_LINE_END = re.compile("\t\t \\)")               # newLineEnd
_NEW_LINE_WITHIN = re.compile('="\t\t ')             # newLineWithinProperty
_PROPERTY_START = re.compile("^\t\t\\(.*")           # propertyStart


def parse_variants(text):
    """{variant: [refdes, ...]}, walking the lines the way the parser's state
    machine does: a line with one quoted name opens a variant, "\t\t(base"
    starts its list, "\t\t)" ends the list, "\t)" closes the variant, and a
    "\t\t(REFDES ..." block between the two is an alternate part (installed).
    Since 2026-09-03 a variant that closes - or whose first block is an
    alternate part - before any "(base" has an empty base list: Capture
    writes no base block when the variant installs nothing.

    Statement by statement since round 118, held to the real parser's
    answers on the files of tests/fixtures/variants (test_skill_pins [7],
    review 23.10.2026 R2-9): the pieces come from parseString as SKILL breaks
    them, and a block that does not end on its line goes on in
    awaitMoreProperties, as a property wrapped onto the next line does.
    Since round 119, as the SKILL: a one-line block ends on its own line; a
    refdes alone on its line opens a block; and a block still open when its
    variant closes or the next block begins, or a base list still open when
    its variant closes, ends there - where the machine used to read on to the
    end of the file and lose that variant and every one after it. Not
    mirrored: the property values (alternateParts). Line ends are normalised
    the way gets() does in text mode (a CRLF and an LF file answered alike).
    Since round 120 a name given to two variants raises once the file is
    read, as the SKILL does (VariantFileError), where the later used to
    replace the earlier in the table without a word.
    """
    table, state, current, symbols = {}, "findVariant", None, []
    refdes, properties = None, ""
    named_on, repeated = {}, []
    for line_no, line in enumerate(text.replace("\r\n", "\n").splitlines(keepends=True), 1):
        if (state == "awaitStartCondition" and line != "\t\t(base\n"
                and (line == "\t)\n" or _PROPERTY_START.search(line))):
            symbols, state = [], "awaitEndCondition"
        if state == "awaitMoreProperties" and (line == "\t)\n" or _PROPERTY_START.search(line)):
            symbols = symbols + [refdes]
            properties, state = "", "awaitEndCondition"
        if state == "appendSymbols" and line == "\t)\n":
            state = "awaitEndCondition"
        if state == "findVariant":
            parts = parse_string(line, '"')
            if len(parts) == 3:
                current = parts[1]
                if current in named_on:
                    repeated.append(f'"{current}" (lines {named_on[current]} and {line_no})')
                else:
                    named_on[current] = line_no
                state = "awaitStartCondition"
        elif state == "awaitStartCondition":
            if line == "\t\t(base\n":
                symbols, state = [], "appendSymbols"
        elif state == "appendSymbols":
            if line == "\t\t)\n":
                state = "awaitEndCondition"
            else:
                symbols = symbols + parse_string(line)
        elif state == "awaitEndCondition":
            if line == "\t)\n":
                table[current] = [_STRIP.sub("", t) for t in symbols if t != ")"]
                state = "findVariant"
            elif _PROPERTY_START.search(line):
                tokens = parse_string(line)
                if len(tokens) == 1 and line != "\t\t(base\n":
                    alone = _STRIP.sub("", tokens[0])
                    if alone != "":
                        refdes, properties, state = alone, "", "awaitMoreProperties"
                found, more, ends = alternate_line(line)
                if found is not None:
                    refdes, properties = found, more
                    if ends:
                        symbols = symbols + [refdes]
                    else:
                        state = "awaitMoreProperties"
        elif state == "awaitMoreProperties":
            properties = properties + _NEW_LINE_END.sub(" )", line)
            properties = _NEW_LINE_WITHIN.sub('="', properties)
            properties = _NEW_LINE.sub("", properties)
            temp = _PROPERTY_SEPARATOR.sub(r"\\", properties)
            temp = _NEW_LINE_END.sub(r"\\", temp)
            chunks = parse_string(temp, "\\")
            if chunks and chunks[-1] == ")\n":
                symbols = symbols + [refdes]
                properties = ""
                state = "awaitEndCondition"
    if repeated:
        raise VariantFileError("gives one name to two variants: " + ", ".join(repeated))
    return table


class VariantFileError(ValueError):
    """What the SKILL's error() says about a Variants.lst, as an exception."""


# mirrors skill/s3d_variants.il: s3dFileNameSafe  -- what no Windows file name takes, made "_"
UNSAFE = '\\/:*?"<>|'                                 # and every control character
_UNSAFE = re.compile('[\\\\/:*?"<>|\\x01-\\x1f]')     # the class pcreCompile is given


def file_name_safe(text):
    """The text with every character a Windows file name cannot carry made
    "_" (round 120, review 23.10.2026 R2-10): \\ / * ? " < > | and a control
    character are refused by outfile, and a colon is taken by NTFS as the
    start of a stream's name, which no listing shows."""
    return _UNSAFE.sub("_", text)


def skill_lower(text):
    """SKILL's lowerCase: the Latin capitals and nothing else. A byte beyond
    ASCII - here a latin-1 character standing for it - stays as it is
    (Allegro 25.1, 31.10.2026: cp1251 "ПОЛНЫЙ" came back unchanged), so
    str.lower(), which would fold it, is not the copy."""
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in text)


# mirrors skill/s3d_variants.il: s3dVariantFileName
def variant_file_name(design, variant):
    return skill_lower(design + "_" + file_name_safe(variant))


# mirrors skill/s3d_variants.il: s3dVariantFileClashes  -- the file system asked, as the SKILL asks it
def variant_file_clashes(folder, design, variants, code_page="cp1251"):
    """Which variants would share a file, asked of the real file system as
    the SKILL asks it: a folder made fresh in `folder`, one small file per
    variant in the order given, carrying its name; a name that finds its file
    there already shares it with the variant written in it. What was made is
    deleted, the folder after it. `variants` hold SKILL strings - bytes, as
    latin-1 characters - and Windows reads a name through the ANSI code page,
    cp1251 where Allegro was measured, so that is how each file is named.
    One line per later variant that finds an earlier one's file, naming the
    file as the earlier one spells it."""
    import os
    probe = os.path.join(folder, "simple3d-name-check")
    n = 1
    while os.path.isdir(probe) or os.path.isfile(probe):
        n += 1
        probe = os.path.join(folder, f"simple3d-name-check-{n}")
    os.mkdir(probe)
    made, clashes = [], []
    try:
        for variant in variants:
            name = variant_file_name(design, variant) + ".json"
            path = os.path.join(probe, name.encode("latin-1").decode(code_page))
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    raw = f.readline()          # gets: nil at the end of the file
                earlier = raw.decode("latin-1") if raw else None
                if earlier is not None and earlier.endswith("\n"):
                    earlier = earlier[:-1]
                if earlier is None:
                    earlier = "?"
                clashes.append(f'"{earlier}" and "{variant}" both go to '
                               f"{variant_file_name(design, earlier)}.json")
            else:
                with open(path, "wb") as f:
                    f.write(variant.encode("latin-1") + b"\n")
                made.append(path)
    finally:
        for path in made:
            os.remove(path)
        os.rmdir(probe)
    return clashes


# mirrors skill/s3d_variants.il: s3dSymbolsToExport  -- its tail: the listed refdes the board does not have
def not_placed(variant_refdes, board_refdes):
    """The refdes a variant names that no symbol on the board carries, by
    name: what the export warns about per variant since 2026-09-03. The
    stray tokens are dropped the way s3dIsRefdesToken drops them."""
    on_board = {r.upper() for r in board_refdes}
    listed = {r.upper() for r in variant_refdes if is_refdes_token(r)}
    return sorted(r for r in listed if r not in on_board)


# mirrors SKILL's own tconc structure, destructive as the real one  -- no procedure of ours; skill/s3d_export.il uses it for the cutout list
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


# mirrors skill/s3d_stackup.il: s3dLayerInBody  -- what the name and the function say
# what the SKILL filter keeps, transliterated
def in_body(nm, fn):
    probe = (nm or "").upper() + " " + (fn or "").upper()
    return not ("SILK" in probe or "PASTE" in probe)


# mirrors skill/s3d_stackup.il: s3dLayerIsNegative, s3dLettersAndDigits
# The default S3D_NegativeLayers, as simple3d_config.json ships it.
NEGATIVE_LAYER_KEYS = ["COVERLAY", "SOLDERMASK", "PASTEMASK"]


def s3d_layer_is_negative(name, func=None, keys=None):
    """Is this stackup layer drawn negative - are its shapes openings?

    The probe is the layer FUNCTION followed by the layer NAME, both upper
    case, and any configured key appearing anywhere in it says yes. A
    substring search, so COVERLAY matches COVERLAY_TOP and a function spelled
    "Coverlay" alike.

    Lived in test_neg.py until 2026-09-15, three lines above the fourteen
    assertions that tested it - so `neg = t` -> `neg = nil` in the SKILL, which
    makes every layer on every board positive, passed the whole suite
    (docs/test-audit.md, finding 3). Pinned to the original in test_skill_pins.
    """
    if keys is None:
        keys = NEGATIVE_LAYER_KEYS
    # Since round 128 (R1n-10): the function and the name each on its own,
    # in letters and digits only, as the STEP tool reads a soldermask.
    parts = [letters_and_digits(p) for p in (func, name) if isinstance(p, str)]
    words = [letters_and_digits(k) for k in keys if isinstance(k, str)]
    return any(w in part for w in words if w for part in parts)


def letters_and_digits(text):
    """s3dLettersAndDigits: upper case, A-Z and 0-9 only - SKILL's pcreReplace
    of [^A-Z0-9] after upperCase, which leaves no other letter."""
    return "".join(c for c in text.upper() if "A" <= c <= "Z" or "0" <= c <= "9")
