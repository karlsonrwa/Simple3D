"""Turn a probe_translit.il run into tests/fixtures/skill_answers.json.

The fixture is an oracle of the same kind as `pads_demo.json`: not a number
this repository computed, but what Allegro's own interpreter answered. Here
the subject is the procedures `tests/skill_transliterations.py` copies that
can be run on their own - the five pure ones, `s3dCmdExpands` since round
116, SKILL's own `parseString` and the variant parser `gdsysGetVariantInfo`
(on the files of tests/fixtures/variants) since round 118 - and the fixture
is what lets `test_skill_pins.py` compare each copy with the original's
answers rather than with a reading of its source.

    python tools/run_probe.py --with-exporter tools/probes/probe_translit.il \
           s3dProbeTranslit demo/demo.brd -o D:/.../build/probe-out
    python tools/skill_answers.py build/probe-out/demo.s3dProbeTranslit.txt

The inputs live HERE rather than in the probe's output, because a case name is
prose and parsing prose back into arguments is how a fixture comes to mean
something other than what it says. The probe prints the same case names; every
case in this table must appear in the run and every case in the run must be in
this table, or nothing is written.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# procedure -> case name -> the arguments the Python copy is to be called with.
# Kept in the order the probe prints them.
CASES: dict[str, dict[str, dict]] = {
    "s3dLayerIsNegative": {
        **{f"name={nm}": {"name": nm, "func": None, "keys": None}
           for nm in ("COVERLAY_TOP", "COVERLAY_BOTTOM", "SOLDERMASK_TOP",
                      "SOLDERMASK_BOTTOM", "PASTEMASK_TOP", "STIFFENER_TOP",
                      "STIFFENER_TOP2", "ADHESIVE_TOP", "ADHESIVE_TOP2",
                      "ADHESIVE_BOTTOM", "TOP", "BOTTOM")},
        "name=MASK_7 function=Coverlay": {"name": "MASK_7", "func": "Coverlay", "keys": None},
        "name=nil function=nil": {"name": None, "func": None, "keys": None},
        "keys=(EPOXY) name=EPOXY_TOP": {"name": "EPOXY_TOP", "func": None, "keys": ["EPOXY"]},
        "keys=(EPOXY) name=COVERLAY_TOP": {"name": "COVERLAY_TOP", "func": None, "keys": ["EPOXY"]},
        "keys=() name=COVERLAY_TOP": {"name": "COVERLAY_TOP", "func": None, "keys": []},
    },
    "s3dDrillXY": {
        "rot=0 off=(0.375 0)":   {"pin_xy": [2.19, 0.375], "rotation": 0.0,   "offset": [0.375, 0.0]},
        "rot=90 off=(0.375 0)":  {"pin_xy": [2.19, 0.375], "rotation": 90.0,  "offset": [0.375, 0.0]},
        "rot=180 off=(0.375 0)": {"pin_xy": [2.19, 0.375], "rotation": 180.0, "offset": [0.375, 0.0]},
        "rot=270 off=(0.375 0)": {"pin_xy": [2.19, 0.375], "rotation": 270.0, "offset": [0.375, 0.0]},
        "rot=90 off=(0 0.25)":   {"pin_xy": [2.19, 0.375], "rotation": 90.0,  "offset": [0.0, 0.25]},
        "rot=45 off=(0.5 0.5)":  {"pin_xy": [2.19, 0.375], "rotation": 45.0,  "offset": [0.5, 0.5]},
        "rot=90 off=nil":        {"pin_xy": [2.19, 0.375], "rotation": 90.0,  "offset": None},
        "rot=270 off=(0 0)":     {"pin_xy": [2.19, 0.375], "rotation": 270.0, "offset": [0.0, 0.0]},
        "rot=nil off=(0.375 0)": {"pin_xy": [2.19, 0.375], "rotation": None,  "offset": [0.375, 0.0]},
    },
    "s3dBoxesMeet": {},          # filled in below - each case has a reversed twin
    "s3dJsonQuote": {
        "plain":        {"value": "abc"},
        "a quote":      {"value": 'a"b'},
        "a backslash":  {"value": "a\\b"},
        "a tab":        {"value": "a\tb"},
        "a newline":    {"value": "a\nb"},
        "a return":     {"value": "a\rb"},
        "not a string": {"value": 7},
        "control 0x08 (escape \\b)": {"value": "a\x08b"},
        "control 0x0c (escape \\f)": {"value": "a\x0cb"},
    },
    "s3dJsonMerge": {},          # read as behaviour, below
}

_BOXES = [
    ("apart in x and y",     [[0, 0], [1, 1]], [[2, 2], [3, 3]]),
    ("apart in x only",      [[0, 0], [1, 1]], [[2, 0], [3, 1]]),
    ("apart in y only",      [[0, 0], [1, 1]], [[0, 2], [1, 3]]),
    ("touching at a corner", [[0, 0], [1, 1]], [[1, 1], [2, 2]]),
    ("overlapping",          [[0, 0], [2, 2]], [[1, 1], [3, 3]]),
    ("one inside the other", [[0, 0], [4, 4]], [[1, 1], [2, 2]]),
    ("no box on the left",   None,             [[1, 1], [2, 2]]),
]
for _name, _a, _b in _BOXES:
    CASES["s3dBoxesMeet"][_name] = {"a": _a, "b": _b}
    CASES["s3dBoxesMeet"][_name + " reversed"] = {"a": _b, "b": _a}

# The merge is read as behaviour: the two inputs, the key asked for, and how.
_MERGE_BASE = {"silk": {"top": True, "bottom": True, "flat": False}, "pads": True}
_MERGE_OVER = {"silk": {"flat": True}}
for _key in ("top", "bottom", "flat"):
    CASES["s3dJsonMerge"][f"silk.{_key}"] = {
        "base": _MERGE_BASE, "over": _MERGE_OVER, "path": ["silk", _key], "ask": "value"}
    CASES["s3dJsonMerge"][f"silk.{_key} present"] = {
        "base": _MERGE_BASE, "over": _MERGE_OVER, "path": ["silk", _key], "ask": "present"}
CASES["s3dJsonMerge"]["pads"] = {
    "base": _MERGE_BASE, "over": _MERGE_OVER, "path": ["pads"], "ask": "value"}
CASES["s3dJsonMerge"]["a scalar over an object"] = {
    "base": {"a": {"b": 1}}, "over": {"a": 2}, "path": ["a"], "ask": "value"}
CASES["s3dJsonMerge"]["a key only the base has"] = {
    "base": {"a": 1}, "over": {"b": 2}, "path": ["a"], "ask": "value"}
CASES["s3dJsonMerge"]["a key only the override has"] = {
    "base": {"a": 1}, "over": {"b": 2}, "path": ["b"], "ask": "value"}

# s3dCmdExpands (round 116): what Windows' cmd would replace. The case name
# is the text, so the table and the probe cannot drift apart on what was
# asked; the names are ones that hold, or do not, on any Windows.
CMD_TEXTS = ("x %OS% y", "x %os% y", "x %Os% y", "x %NOPE_S3D% y", "x %NOPE_S3D%OS% y",
             "x %OS:~0,3% y", "x %OS:Win=W% y", "x %:OS% y", "x %NOPE_S3D:~1% y", "x %CD% y",
             "x %random% y", "x %ERRORLEVEL% y", "x %=C:% y", "50% / 60%", "x % y", "x %% y",
             "x %%OS%% y", "x !OS! y", "x %windir% y", "x %PATH% y", "%OS%",
             "D:/Projects/AI/Claude/Simple3D", "")
CASES["s3dCmdExpands"] = {f"text={t}": {"text": t} for t in CMD_TEXTS}
CASES["s3dCmdExpands"]["text=nil"] = {"text": None}

# parseString (round 118): SKILL's own, with no break characters given - the
# tokenizer the variant parser's copy has to match.
CASES["parseString"] = {"space": {"text": "a b"}, "tab": {"text": "a\tb"},
                        "newline": {"text": "a\nb"}, "return": {"text": "a\rb"},
                        "runs": {"text": "  a   b  "}, "empty": {"text": ""}}

# gdsysGetVariantInfo (round 118): the variant parser, on the files in
# tests/fixtures/variants. The case is the file, so the table and the probe
# cannot drift apart on what was asked; the answer is the variant table,
# variants in name order.
VARIANT_FILES = sorted((ROOT / "tests" / "fixtures" / "variants").glob("*.lst"))
CASES["gdsysGetVariantInfo"] = {f.name: {"file": f"tests/fixtures/variants/{f.name}"}
                                for f in VARIANT_FILES}

# The names the variants' files get (round 120, review 23.10.2026 R2-10): what
# a file name cannot carry made "_", the design and the variant lower-cased,
# and which variants would share a file - the last asked of the real file
# system, in the order given, design "brd".
CASES["s3dFileNameSafe"] = {
    "plain": {"text": "Full"}, "a colon": {"text": "Rev:A"}, "a slash": {"text": "A/B"},
    "a backslash": {"text": "A\\B"}, "the rest": {"text": 'x*?"<>|y'},
    "a tab": {"text": "a\tb"}, "control 0x08": {"text": "a\x08b"},
    "kept": {"text": "BOM 100% #1 (v2) [x] {y} a.b ~!@$^&=+,;'`"}, "empty": {"text": ""}}
CASES["s3dVariantFileName"] = {
    f"design={d} variant={v}": {"design": d, "variant": v}
    for d, v in (("Variants_Test-B0", "Full"), ("brd", "FULL"), ("brd", "Rev:A"), ("brd", "A b"))}
CASES["s3dVariantFileClashes"] = {
    "Full FULL ALT": {"variants": ["Full", "FULL", "ALT"]},
    "full Full FULL": {"variants": ["full", "Full", "FULL"]},
    "A a b B": {"variants": ["A", "a", "b", "B"]},
    "Rev:A Rev_A": {"variants": ["Rev:A", "Rev_A"]},
    "Rev:A Rev:B": {"variants": ["Rev:A", "Rev:B"]},
    "a, a and a space": {"variants": ["a", "a "]},
    "x, x and a dot": {"variants": ["x", "x."]},
    # the names as the parser hands them over, in name order
    "the names of v21-cyrillic-case-twins.lst":
        {"file": "tests/fixtures/variants/v21-cyrillic-case-twins.lst"},
    # what the cases above left in the folder they were asked in
    "left behind": {"left": True},
}

# Cases the probe prints for its own sake, not for the copies to answer.
IGNORE = {("s3dJsonQuote", "control 0x08 (escape \\b) byte"),
          ("s3dJsonQuote", "control 0x0c (escape \\f) byte")}

LINE = re.compile(r"^CASE (\S+) \| (.+?) \| (.*)$")
# One piece of a `%L` rendering: a bracket, a string, or anything else up to
# white space or a bracket.
TOKEN = re.compile(r'\s*(?:(\()|(\))|("(?:\\.|[^"\\])*")|([^\s()"]+))')


def _atom(text: str):
    if text == "t":
        return True
    if text == "nil":
        return None
    try:
        return float(text) if ("." in text or "e" in text.lower()) else int(text)
    except ValueError:
        return text


_ESCAPE = re.compile(r'\\(?:([0-7]{3})|(.))|([^\\]+)', re.S)


def skill_string(quoted: str) -> str:
    """One `%L` string, quotes included, as the characters it holds. %L
    escapes the way JSON does, and a byte beyond ASCII as three octal digits
    ("\\317"): Allegro 25.1, the Cyrillic names of v21 (round 120). The run is
    read as latin-1, one character per byte, so such a byte comes back as the
    same one character either way."""
    out = []
    for octal, escaped, plain in _ESCAPE.findall(quoted[1:-1]):
        if octal:
            out.append(f"\\u{int(octal, 8):04x}")
        elif escaped:
            out.append("\\" + escaped)
        else:
            out.append(plain)
    return json.loads('"' + "".join(out) + '"')


def skill_value(text: str):
    """One `%L` rendering, as a Python value: t, nil, numbers, strings (%L
    escapes them the way JSON does, see skill_string) and lists of them,
    nested - the variant table is a list of ( name symbols ) pairs since round
    118. A flat list reads as it did before; a string holding a space no
    longer splits."""
    stack: list[list] = [[]]
    text = text.strip()
    pos = 0
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if m is None:
            raise ValueError(f"cannot read %L text at {pos}: {text[pos:pos + 30]!r}")
        pos = m.end()
        opened, closed, string, atom = m.groups()
        if opened:
            stack.append([])
        elif closed:
            if len(stack) == 1:
                raise ValueError(f"unbalanced ) in {text!r}")
            inner = stack.pop()
            stack[-1].append(inner)
        elif string is not None:
            stack[-1].append(skill_string(string))
        else:
            stack[-1].append(_atom(atom))
        while pos < len(text) and text[pos].isspace():
            pos += 1
    if len(stack) != 1 or len(stack[0]) != 1:
        raise ValueError(f"not one value: {text!r}")
    return stack[0][0]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    run = Path(argv[1])
    # One character per byte: SKILL's strings are bytes, and a name beyond
    # ASCII has to come back as the bytes it was (round 120).
    text = run.read_text(encoding="latin-1")

    seen: dict[tuple[str, str], object] = {}
    skipped = []
    for line in text.splitlines():
        if line.startswith("SKIP "):
            skipped.append(line[len("SKIP "):])
            continue
        m = LINE.match(line)
        if m:
            seen[(m.group(1), m.group(2))] = skill_value(m.group(3))

    wanted = {(proc, case) for proc, cases in CASES.items() for case in cases}
    got = set(seen) - IGNORE
    if wanted - got:
        print("cases in the table the run does not have:")
        for k in sorted(wanted - got):
            print("  ", k)
        return 1
    if got - wanted:
        print("cases in the run the table does not have:")
        for k in sorted(got - wanted):
            print("  ", k)
        return 1

    out = {
        "_comment": (
            f"What Allegro's own SKILL interpreter answered, run by "
            f"tools/probes/probe_translit.il on {run.name} and turned into this "
            f"file by tools/skill_answers.py. The oracle for the Python copies "
            f"in tests/skill_transliterations.py, compared against it in "
            f"test_skill_pins [7]. `inputs` are this repository's; `answer` is "
            f"Allegro's."),
        "source": run.name,
        "skipped": skipped,
        "cases": [
            {"procedure": proc, "case": case, "inputs": inputs,
             "answer": seen[(proc, case)]}
            for proc, cases in CASES.items() for case, inputs in cases.items()
        ],
    }
    dst = ROOT / "tests" / "fixtures" / "skill_answers.json"
    dst.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{dst}: {len(out['cases'])} cases, {len(skipped)} skipped by the probe")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
