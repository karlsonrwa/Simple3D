"""Turn a probe_translit.il run into tests/fixtures/skill_answers.json.

The fixture is an oracle of the same kind as `pads_demo.json`: not a number
this repository computed, but what Allegro's own interpreter answered. Here
the subject is the five pure procedures that `tests/skill_transliterations.py`
copies, and the fixture is what lets `test_skill_pins.py` compare each copy
with the original's answers rather than with a reading of its source.

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

# Cases the probe prints for its own sake, not for the copies to answer.
IGNORE = {("s3dJsonQuote", "control 0x08 (escape \\b) byte"),
          ("s3dJsonQuote", "control 0x0c (escape \\f) byte")}

LINE = re.compile(r"^CASE (\S+) \| (.+?) \| (.*)$")


def skill_value(text: str):
    """One `%L` rendering, as a Python value."""
    text = text.strip()
    if text == "t":
        return True
    if text == "nil":
        return None
    if text.startswith('"'):
        return json.loads(text)          # %L escapes strings the way JSON does
    if text.startswith("("):
        return [skill_value(p) for p in text[1:-1].split()]
    try:
        return float(text) if ("." in text or "e" in text.lower()) else int(text)
    except ValueError:
        return text


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    run = Path(argv[1])
    text = run.read_text(encoding="utf-8", errors="replace")

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
