# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, out_dir, fails, check, rect, volume

"""A cutout that appears twice used to erase the whole board body.

Two coincident prisms in the tool compound make BRepAlgoAPI_Cut return an EMPTY
compound while IsDone() is true and the shape is not null - so both guards the
builder had passed, and the STEP was written with components, legend and no
board. Measured on the user's 8231-a2: 26 contours instead of 24, the last two
byte-identical repeats of the two slot holes, 0 solids instead of 724.18 mm3.

Both halves of the fix are checked here: the duplicates are dropped before the
boolean, and a boolean that produces no solid for any OTHER reason is now an
error with a message instead of an empty part.

And since round 125 the other contours the body cannot be made of: one that
crosses itself or encloses no area ([6]), a primitive of no length, an open
zone ([7]) - each an error that says which contour, where none did.
"""
import json
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


def seg(a, b):
    return {"type": "segment", "start": list(a), "end": list(b)}


def ring(points):
    return [seg(points[i], points[(i + 1) % len(points)]) for i in range(len(points))]


def refusal(build):
    """The StepBuilderError's text, None when *build* went through, or the
    name of any other exception - which says nothing of where the fault is."""
    try:
        build()
    except core.StepBuilderError as exc:
        return str(exc)
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


STACK = {"S": {"thickness": 1.0, "layers": LAYERS}}
PCB6 = {"thickness": {"soldermask_top": 0.0, "board": 1.0, "soldermask_bottom": 0.0},
        "color": {"r": 0.0, "g": 0.4, "b": 0.0}, "edges": [OUTLINE]}

print("\n[6] a contour of the body that makes no face is refused by name (round 125)")
# R3-9 of the 23.10.2026 review: a bow-tie outline, one that crosses itself,
# made a face all the same, and the STEP was written with a board of no
# volume and not a word. MakeFace's IsDone() was the only test.
BOWTIE = ring([(0, 0), (10, 10), (10, 0), (0, 10)])
msg = refusal(lambda: board([BOWTIE]))
check("a bow-tie outline is refused, and said to cross itself",
      msg == "Board outline crosses itself: OpenCASCADE's own check (BRepCheck) rejects its face", msg)
msg = refusal(lambda: board([[seg((0, 0), (10, 0)), seg((10, 0), (0, 0))]]))
check("one that runs out along a track and back, which that check passes, encloses no area",
      msg == "Board outline encloses no area", msg)
msg = refusal(lambda: board([ring([(0, 0), (5, 0), (10, 0)])]))
check("one along a straight line is no valid face",
      msg == "Board outline is not a valid face: OpenCASCADE's own check (BRepCheck) rejects it", msg)
msg = refusal(lambda: board([OUTLINE, HOLE, HOLE, ring([(2, 6), (4, 8), (4, 6), (2, 8)])]))
check("a bow-tie cutout is named by its place in pcb.edges, a repeat dropped before it, "
      "and by where it begins",
      msg == "Cutout 3 near (2, 6) crosses itself: OpenCASCADE's own check (BRepCheck) rejects its face",
      msg)
ZONES = [{"name": "Z", "stackup": "S", "contour": BOWTIE}]
msg = refusal(lambda: core.make_board_layer_parts(PCB6, STACK, ZONES, 0.0, lambda m: None))
check("a bow-tie zone, its layers kept apart",
      msg is not None and msg.startswith("Zone Z outline crosses itself"), msg)
msg = refusal(lambda: core.make_board_geometry(PCB6, 1.0, zones=ZONES, levels={"Z": (0.0, -1.0)},
                                               stackups=STACK, log=lambda m: None))
check("the same, fused", msg is not None and msg.startswith("Zone Z outline crosses itself"), msg)
msg = refusal(lambda: core.make_board_geometry(PCB6, 1.0, zones=ZONES, levels={"Z": (0.0, -1.0)},
                                               log=lambda m: None))
check("and a zone with no layers (format_version 5)",
      msg is not None and msg.startswith("Zone Z outline crosses itself"), msg)
# the way in the review went: the whole build, both modes
W6 = out_dir("dupcuts_bowtie")
for mode, want in (("solid", "Board outline crosses itself"),
                   ("inspect", "Zone board outline crosses itself")):
    jf = W6 / f"bowtie_{mode}.json"
    (W6 / f"bowtie_{mode}.step").unlink(missing_ok=True)      # an earlier run's
    jf.write_text(json.dumps({"format": "simple3d", "format_version": 12, "name": "bowtie",
                              "pcb": dict(PCB6, edges=[BOWTIE]), "stackups": STACK,
                              "components": {}}), encoding="utf-8")
    msg = refusal(lambda: core.generate(step_dir=ROOT / "demo/step_files", json_file=jf,
                                        output_dir=W6, output_name=f"bowtie_{mode}",
                                        board_mode=mode, log=lambda m: None))
    check(f"core.generate refuses it, board mode {mode}",
          msg is not None and msg.startswith(want), msg)
    check("and writes no STEP", not (W6 / f"bowtie_{mode}.step").exists())

print("\n[7] what is wrong with a contour, and which contour it is (round 125)")
# R3-12 of the review: a segment of no length was a bare StdFail_NotDone, an
# open zone named no zone, and a zone's or drawn shape's face that would not
# build was called the "silkscreen outline".
zero = OUTLINE[:2] + [seg((10, 10), (10, 10))] + OUTLINE[2:]
msg = refusal(lambda: board([zero]))
check("a segment of no length is named, by its place in the contour and where it is",
      msg == "Board outline: segment #3 has no length, at (10, 10)", msg)
msg = refusal(lambda: board([OUTLINE, [{"type": "arc", "center": [5, 5], "radius": 2,
                                        "alpha": 90, "beta": 90}]]))
check("an arc of no sweep too",
      msg == "Cutout 1 near (5, 5): arc #1 has no length (alpha 90, beta 90 degrees)", msg)
msg = refusal(lambda: core.make_board_layer_parts(
    PCB6, STACK, [{"name": "ZOPEN", "stackup": "S", "contour": OUTLINE[:3]}], 0.0, lambda m: None))
check("an open zone says which zone", msg is not None
      and msg.startswith("Zone ZOPEN outline: Contour is open"), msg)
said7 = []
flat = [dict(layer) for layer in LAYERS]
flat[0]["shapes"] = [{"outline": [{"type": "circle", "x": 5, "y": 5, "radius": 0}]}]
core.make_board_layer_parts(PCB6, {"S": {"thickness": 1.0, "layers": flat}},
                            [{"name": "Z", "stackup": "S", "contour": OUTLINE}], 0.0, said7.append)
check("a drawn shape that makes no face is not called a silkscreen outline",
      "warning: shape 1 of layer TOP skipped (outline makes no flat face "
      "(OpenCASCADE: BRepBuilderAPI_NotPlanar))" in said7, said7)

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
