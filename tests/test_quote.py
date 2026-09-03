# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, fails, check, exporter_source

"""Transliteration of s3dJsonQuote, checked against the json module.

Written to a FILE, not passed through a heredoc: heredocs mangle backslash
escapes, which is exactly what this is testing (round 14a lesson).
"""
import json, sys

from skill_transliterations import s3dJsonQuote


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
                 ('\\"', 'backslash-quote'), ('cr\rhere', 'carriage return')]:
    got = s3dJsonQuote(v)
    try:
        parsed = json.loads('{"k": ' + got + '}')["k"]
        ok = parsed == v
        detail = f"got {parsed!r}"
    except Exception as exc:
        ok, detail = False, f"does not parse: {exc}"
    check(f"{label:18} {v!r}", ok, detail)

print("\n[2b] every other control character, which JSON also forbids raw")
# One of these anywhere in any string makes the WHOLE intermediate unparsable,
# and the message names JSON rather than the name that carries it. They cannot
# round-trip - the character is replaced - so what is checked is that the file
# still parses and nothing else in the string is disturbed.
for n in list(range(0x01, 0x20)):
    c = chr(n)
    v = f"LAYER{c}NAME"
    got = s3dJsonQuote(v)
    try:
        parsed = json.loads('{"k": ' + got + '}')["k"]
        ok = parsed in (v, "LAYER NAME")
        detail = f"got {parsed!r}"
    except Exception as exc:
        ok, detail = False, f"does not parse: {exc}"
    check(f"0x{n:02x} in a layer name", ok, detail)

check("the SKILL source escapes CR too",
      '( c == "\\r"  "\\\\r" )' in
      exporter_source())

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
