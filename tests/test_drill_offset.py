# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, fails, check, exporter_source

"""s3dDrillXY: the hole is not always at the pad.

A padstack may carry an offset from its origin to the hole - Allegro's Padstack
Editor, Drill Offset tab, "Offset from padstack origin to hole". An edge
connector is what it is for: the pads sit on the board, the holes straddle the
edge as half-holes.

makeSlot had applied it since the upstream code; the ROUND-hole branch of
symbolReturnPinHoles never did, so an ordinary drilled pin came out at the pad
centre. Found on the user's bone-a2 (2026-08-21): four PLS-4 pins with offset
x = 0.375 and the padstack turned to face the board edge. Allegro's own 3D put
the holes on y = 0 - clean half-circles in the edge - and our STEP put them at
y = 0.375, where the same circle becomes a keyhole with a 0.66 mm mouth. The
hole positions "agreed" in both files, which is why it read as a rendering
difference rather than a geometry one.

Transliterated from makeVariant3dIntermediates.il the way test_quote.py
transliterates s3dJsonQuote. The last case reads the .il itself, so a future
edit cannot quietly go back to pin->xy in one branch and not the other.
"""
import math
import re

from skill_transliterations import s3dDrillXY
import sys


def close(a, b, tol=1e-9):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


PAD = [2.19, 0.375]

print("\n[1] no offset at all - the drill is the pad, exactly")
check("drillOffset nil", s3dDrillXY(PAD, 0.0, None) is PAD)
check("drillOffset nil, rotated pin", s3dDrillXY(PAD, 90.0, None) is PAD)
check("drillOffset (0,0)", s3dDrillXY(PAD, 270.0, [0.0, 0.0]) is PAD)
# Returned unchanged rather than rotated by zero: a coordinate that was exact
# must not pick up sin/cos noise on the way through.
check("a pin with no rotation is not an error",
      s3dDrillXY(PAD, None, None) is PAD)

print("\n[2] the offset is in the PADSTACK's frame, so the pin's rotation turns it")
OFF = [0.375, 0.0]
check("rotation 0   -> +x", close(s3dDrillXY(PAD, 0.0, OFF), [2.565, 0.375]))
check("rotation 90  -> +y", close(s3dDrillXY(PAD, 90.0, OFF), [2.19, 0.75]))
check("rotation 180 -> -x", close(s3dDrillXY(PAD, 180.0, OFF), [1.815, 0.375]))
check("rotation 270 -> -y", close(s3dDrillXY(PAD, 270.0, OFF), [2.19, 0.0]))
check("rotation nil is rotation 0",
      close(s3dDrillXY(PAD, None, OFF), s3dDrillXY(PAD, 0.0, OFF)))
check("an offset in y turns too",
      close(s3dDrillXY(PAD, 90.0, [0.0, 0.25]), [2.19 - 0.25, 0.375]))

print("\n[3] bone-a2: four PLS-4 pins, offset 0.375, padstack facing the edge")
# The pads as the intermediate carried them before the fix, and the board's
# bottom edge at y = 0. X5 - the HDRV4W64P254 header - is placed at y = 0.0,
# which is where the drill line belongs.
PADS = [[2.19, 0.375], [4.73, 0.375], [7.27, 0.375], [9.81, 0.375]]
drills = [s3dDrillXY(p, 270.0, OFF) for p in PADS]
check("every drill lands on the board edge, y = 0",
      all(abs(d[1]) < 1e-9 for d in drills), f"got {drills}")
check("x is untouched",
      all(abs(d[0] - p[0]) < 1e-9 for d, p in zip(drills, PADS)), f"got {drills}")
check("the four keep their 2.54 pitch",
      all(abs((drills[i + 1][0] - drills[i][0]) - 2.54) < 1e-9 for i in range(3)))

print("\n[4] what the 0.375 mm looked like - the two screenshots, as numbers")
R = 0.5
def profile(cy):
    """A circle of radius R centred at y=cy, cut by the board edge at y=0:
    how wide is its mouth in the edge, and how far does it reach inboard."""
    if cy >= R:
        return 0.0, 2 * R              # a closed hole, the edge is untouched
    mouth = 2.0 * math.sqrt(R * R - cy * cy)
    return mouth, cy + R
wrong_mouth, wrong_rise = profile(0.375)
right_mouth, right_rise = profile(0.0)
check("at the pad (y=0.375) the hole is a keyhole, not a half-circle",
      abs(wrong_mouth - 0.6614) < 1e-3 and abs(wrong_rise - 0.875) < 1e-9,
      f"mouth {wrong_mouth:.4f}, rise {wrong_rise:.4f}")
check("at the drill (y=0) it is a clean half-circle",
      abs(right_mouth - 1.0) < 1e-9 and abs(right_rise - 0.5) < 1e-9,
      f"mouth {right_mouth:.4f}, rise {right_rise:.4f}")
check("the mouth was 34% too narrow", wrong_mouth < right_mouth)

print("\n[5] both hole branches go through the one procedure")
il = exporter_source()
check("s3dDrillXY exists", "procedure( s3dDrillXY( pin padstack )" in il)

def body(name):
    """The text of one procedure, up to the next top-level procedure."""
    m = re.search(r"^procedure\( " + name + r"\(.*?(?=^procedure\()",
                  il, re.S | re.M)
    assert m, f"{name} not found - this test is stale"
    return m.group(0)

slot = body("makeSlot")
pins = body("symbolReturnPinHoles")
check("makeSlot asks s3dDrillXY", "s3dDrillXY( pin padstack )" in slot)
check("symbolReturnPinHoles asks s3dDrillXY", "s3dDrillXY( pin padstack )" in pins)
# The whole point of the fix is that there is ONE implementation. A second copy
# of the arithmetic is how the round-hole branch came to be without it.
check("makeSlot no longer re-implements the offset",
      "drillOffset" not in slot, "the five lines are back in makeSlot")
check("the round-hole branch does not drill at the pad",
      "xy = pin->xy" not in pins, "pin->xy is the PAD, not the hole")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
