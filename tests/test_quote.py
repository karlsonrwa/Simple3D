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

"""Transliteration of s3dJsonQuote, checked against the json module.

Written to a FILE, not passed through a heredoc: heredocs mangle backslash
escapes, which is exactly what this is testing (round 14a lesson).
"""
import json, sys


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
        else:
            out += c
    return out + '"'


fails = []
def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(name)


print("\n[1] real layer / stackup / zone names")
for v in ["SOLDERMASK_TOP", "STIFFENER_TOP2", "FLEX", "COVERLAY_BOTTOM",
          "STTIFFENER1", "Solder Mask", "DIELECTRIC(5)"]:
    got = s3dJsonQuote(v)
    parsed = json.loads('{"k": ' + got + '}')["k"]
    check(f"{v!r}", parsed == v, f"got {parsed!r}")

print("\n[2] characters that would break the whole intermediate")
for v, label in [('has"quote', 'quote'), ('back\\slash', 'backslash'),
                 ('tab\there', 'tab'), ('nl\nhere', 'newline'),
                 ('both"\\mixed', 'quote+backslash'), ('', 'empty'),
                 ('"', 'bare quote'), ('\\', 'bare backslash'),
                 ('\\"', 'backslash-quote')]:
    got = s3dJsonQuote(v)
    try:
        parsed = json.loads('{"k": ' + got + '}')["k"]
        ok = parsed == v
        detail = f"got {parsed!r}"
    except Exception as exc:
        ok, detail = False, f"does not parse: {exc}"
    check(f"{label:18} {v!r}", ok, detail)

print("\n[3] a whole emitted object still parses")
doc = ("{" + s3dJsonQuote("FLEX") + ': {"layers": [{"name": '
       + s3dJsonQuote('odd"name') + ', "function": '
       + s3dJsonQuote(None) + "}]}}")
try:
    d = json.loads(doc)
    check("object parses", True)
    check("name round-trips", d["FLEX"]["layers"][0]["name"] == 'odd"name')
    check("nil function -> null", d["FLEX"]["layers"][0]["function"] is None)
except Exception as exc:
    check("object parses", False, str(exc))

check("non-string -> null", s3dJsonQuote(None) == "null")
check("a number is not quoted", s3dJsonQuote(1.5) == "null")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
