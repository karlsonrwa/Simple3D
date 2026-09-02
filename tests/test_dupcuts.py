# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import fails, check, rect, volume

"""A cutout that appears twice used to erase the whole board body.

Two coincident prisms in the tool compound make BRepAlgoAPI_Cut return an EMPTY
compound while IsDone() is true and the shape is not null - so both guards the
builder had passed, and the STEP was written with components, legend and no
board. Measured on the user's 8231-a2: 26 contours instead of 24, the last two
byte-identical repeats of the two slot holes, 0 solids instead of 724.18 mm3.

Both halves of the fix are checked here: the duplicates are dropped before the
boolean, and a boolean that produces no solid for any OTHER reason is now an
error with a message instead of an empty part.
"""
import math
import sys

from stepbuilder import core


def circle(x, y, r):
    return [{"type": "circle", "x": x, "y": y, "radius": r}]


def board(edges):
    pcb = {"thickness": {"soldermask_top": 0.0, "board": 1.0,
                         "soldermask_bottom": 0.0},
           "color": {"r": 0.0, "g": 0.4, "b": 0.0},
           "edges": edges}
    return core.make_board_geometry(pcb, 1.0, 0.0, log=lambda m: None)


OUTLINE = rect(0, 0, 10, 10)
HOLE = circle(3, 3, 1.0)
OTHER = circle(7, 7, 0.5)
EXPECT = 100.0 - math.pi * 1.0 ** 2 - math.pi * 0.5 ** 2

print("\n[1] which contours board_cutouts keeps")
seen = []
check("nothing to cut when there is only an outline",
      core.board_cutouts([OUTLINE], seen.append) == [])
check("an empty list is not an error", core.board_cutouts([], seen.append) == [])
kept = core.board_cutouts([OUTLINE, HOLE, OTHER], seen.append)
check("two different holes both survive", len(kept) == 2)
check("and nothing is said about them", seen == [])

kept = core.board_cutouts([OUTLINE, HOLE, OTHER, HOLE], seen.append)
check("an exact repeat is dropped", len(kept) == 2, kept)
check("the survivors are the first of each", kept == [HOLE, OTHER])
check("and the log says so, by count", seen and "2 cutout" not in seen[0]
      and "1 cutout" in seen[0], seen)

# A repeat is EXACT geometry. Cutouts that merely overlap are ordinary - a slot
# running off a milled edge, two drawn shapes sharing a corner - and OCC deals
# with them, so they must not be touched.
nudged = circle(3, 3, 1.0000001)
kept = core.board_cutouts([OUTLINE, HOLE, nudged], lambda m: None)
check("a hole that is nearly the same is NOT a duplicate", len(kept) == 2)
overlap = core.board_cutouts([OUTLINE, circle(3, 3, 1.0), circle(3.5, 3, 1.0)],
                             lambda m: None)
check("nor is one that overlaps it", len(overlap) == 2)

print("\n[2] the board itself, with and without the duplicate")
clean = volume(board([OUTLINE, HOLE, OTHER]))
check(f"two holes: {EXPECT:.4f} mm3", abs(clean - EXPECT) < 1e-6, f"{clean:.6f}")

doubled = volume(board([OUTLINE, HOLE, OTHER, HOLE, OTHER]))
check("each hole repeated: the SAME board, not an empty one",
      abs(doubled - clean) < 1e-9, f"{doubled:.6f}")

# One duplicate anywhere is enough - it does not take a matched pair.
one = volume(board([OUTLINE, HOLE, OTHER, HOLE]))
check("and one repeat among many is enough to have broken it",
      abs(one - clean) < 1e-9, f"{one:.6f}")

print("\n[3] a boolean that really does leave nothing is now an error")
try:
    board([OUTLINE, rect(0, 0, 10, 10)])          # a cutout the size of the board
    check("a cutout that removes the whole board is reported", False,
          "it built something")
except core.StepBuilderError as exc:
    check("a cutout that removes the whole board is reported", True)
    check("and the message names what to look at", "pcb.edges" in str(exc), exc)

print("\n[4] has_solid, which is the check IsDone() does not give")
check("a board is a solid", core.has_solid(board([OUTLINE])))
from OCP.BRep import BRep_Builder
from OCP.TopoDS import TopoDS_Compound
_b, _c = BRep_Builder(), TopoDS_Compound()
_b.MakeCompound(_c)
check("an empty compound is not", not core.has_solid(_c))

print("\n[5] the per-layer build drops them too")
LAYERS = [{"name": "TOP", "type": "CONDUCTOR", "thickness": 0.5,
           "z_top": 0.0, "z_bottom": -0.5, "negative": False, "shapes": None},
          {"name": "BOTTOM", "type": "CONDUCTOR", "thickness": 0.5,
           "z_top": -0.5, "z_bottom": -1.0, "negative": False, "shapes": None}]
pcb = {"thickness": {"soldermask_top": 0.0, "board": 1.0, "soldermask_bottom": 0.0},
       "color": {"r": 0.0, "g": 0.4, "b": 0.0},
       "edges": [OUTLINE, HOLE, OTHER, HOLE, OTHER]}
parts = core.make_board_layer_parts(
    pcb, {"S": {"thickness": 1.0, "layers": LAYERS}},
    [{"name": "Z", "stackup": "S", "contour": OUTLINE}], 0.0, lambda m: None)
check("both layers survive the duplicated cutouts", len(parts) == 2, len(parts))
total = sum(volume(solid) for _, _, solid in parts)
check(f"and together they are the same board: {EXPECT:.4f} mm3",
      abs(total - EXPECT) < 1e-6, f"{total:.6f}")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
