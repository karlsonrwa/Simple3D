# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, out_dir, fails, check, rect, read_step

"""The board's faces at a point - where a part stands and a pad, its mask
window and a drawn opening lie - from the layers that have material there,
not from the zone's whole stack (round 103, findings R3-1 and R4-2 of the
23.10.2026 review). The oracle is the body itself: a vertical line through
the point, cut with the board the build wrote."""
import json
import sys

from stepbuilder import core
from stepbuilder import pads as P
from stepbuilder.build import BuildOptions
from stepbuilder.defaults import DEFAULT_FLAT_HEIGHT as H
from stepbuilder.models import component_transform
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.gp import gp_Dir, gp_Lin, gp_Pnt

OUT = out_dir("surface")


def circle(r, cx=0.0, cy=0.0):
    return [{"type": "circle", "x": cx, "y": cy, "radius": r}]


def near(a, b, tol=1e-6):
    return a is not None and b is not None and abs(a - b) <= tol


# tests/fixtures/rigidflex.json: zone S2 (x 0..16, y 0..11.38) on STIFFENER2,
# zone F2 above it on FLEX, and no layer drawn as shapes. Here S2's stiffener
# and its adhesive get a window of r = 1.5 around (8, 5) - flex-b2's connector,
# whose pads the zone's stack drew up to 2.033 mm in the air, and flex2-a0's
# X1, 0.575 mm - and the coverlay under S2 an opening at (12, 5), as
# flex3-a0's bottom pads have it (0.052 mm off).
WINDOW, OPENING, SOLID_POINT, DRILLED = (8.0, 5.0), (12.0, 5.0), (3.0, 8.0), (3.0, 3.0)
EDGE = (9.5, 5.0)                 # a through pin on the window's edge: its copper half under the stiffener
board = json.loads((ROOT / "tests/fixtures/rigidflex.json").read_text(encoding="utf-8"))
board.update({"format_version": 12, "name": "windowed"})
for layer in board["stackups"]["STIFFENER2"]["layers"]:
    if layer["name"] in ("STIFFENER_TOP2", "ADHESIVE_TOP2"):
        # and a hole of the drill's own radius round a through pin, as
        # flex3-a0's layers have over its top pins' copper
        layer["shapes"] = [{"outline": rect(0, 0, 16, 11.38),
                            "voids": [circle(1.5, *WINDOW), circle(0.3, *DRILLED)]}]
        layer["negative"] = False
    if layer["name"] == "COVERLAY_BOTTOM":
        layer["shapes"] = [{"outline": rect(11.0, 4.0, 13.0, 6.0)}]
        layer["negative"] = True
MASK = {"figure": "RECTANGLE", "bbox": [[-0.6, -0.6], [0.6, 0.6]], "offset": [0.0, 0.0], "inside": 0.0,
        "outline": rect(-0.6, -0.6, 0.6, 0.6)}
PAD = {"figure": "RECTANGLE", "bbox": [[-0.5, -0.5], [0.5, 0.5]], "offset": [0.0, 0.0], "inside": 0.0,
       "outline": rect(-0.5, -0.5, 0.5, 0.5)}
smd = {"usage": "Smd", "drill": None, "pads": {"ETCH/TOP": PAD, "PIN/SOLDERMASK_TOP": MASK}}
thru = {"usage": "Thru", "drill": circle(0.3), "pads": {"ETCH/TOP": PAD, "ETCH/BOTTOM": PAD,
                                                        "PIN/SOLDERMASK_TOP": MASK, "PIN/SOLDERMASK_BOTTOM": MASK}}
board["pads"] = {"padstacks": {"SMD": smd, "THRU": thru},
                 "pins": [[WINDOW[0], WINDOW[1], 0.0, False, "SMD", "ETCH/TOP", "ETCH/TOP"],
                          [OPENING[0], OPENING[1], 0.0, True, "SMD", "ETCH/BOTTOM", "ETCH/BOTTOM"],
                          [SOLID_POINT[0], SOLID_POINT[1], 0.0, False, "SMD", "ETCH/TOP", "ETCH/TOP"],
                          [DRILLED[0], DRILLED[1], 0.0, False, "THRU", "ETCH/TOP", "ETCH/BOTTOM"],
                          [EDGE[0], EDGE[1], 0.0, False, "THRU", "ETCH/TOP", "ETCH/BOTTOM"]],
                 # copper under drawn openings: one inside the window, one
                 # across its edge (y = 6.5), half over the stiffener
                 "exposed": {"top": [{"layer": "BOARD GEOMETRY/SOLDERMASK_TOP", "area": 0.25,
                                      "vertices": [[7.75, 3.75, 0], [8.25, 3.75, 0], [8.25, 4.25, 0],
                                                   [7.75, 4.25, 0]]},
                                     {"layer": "BOARD GEOMETRY/SOLDERMASK_TOP", "area": 0.5,
                                      "vertices": [[7.75, 6.0, 0], [8.25, 6.0, 0], [8.25, 7.0, 0],
                                                   [7.75, 7.0, 0]]}],
                             "bottom": []},
                 "bare": {"top": [], "bottom": []}}
ZERO = {"step_name": "cap_D8x10mm.stp", "rotation_x": 0.0, "rotation_y": 0.0, "rotation_z": 0.0,
        "offset_x": 0.0, "offset_y": 0.0, "offset_z": 0.0}
board["components"] = {
    "P1": {"x": WINDOW[0], "y": WINDOW[1], "angle": 0.0, "is_mirrored": False, "zone": "S2",
           "step_mapping": dict(ZERO)},
    "P2": {"x": OPENING[0], "y": OPENING[1], "angle": 0.0, "is_mirrored": True, "zone": "S2",
           "step_mapping": dict(ZERO)},
    "P3": {"x": SOLID_POINT[0], "y": SOLID_POINT[1], "angle": 0.0, "is_mirrored": False, "zone": "S2",
           "step_mapping": dict(ZERO)}}
jf = OUT / "windowed.json"
jf.write_text(json.dumps(board), encoding="utf-8")

logs = []
core.generate(step_dir=ROOT / "demo/step_files", json_file=jf, output_dir=OUT, output_name="windowed",
              exposed_copper=True, mask_openings=True, fold_bends=False, log=logs.append)
shape = read_step(OUT / "windowed.step")


def x_extent(solid):
    box = Bnd_Box()
    BRepBndLib.Add_s(solid, box, False)
    x0, _y0, _z0, x1, _y1, _z1 = box.Get()
    return x1 - x0


# The board is the solid 41 mm across; the parts' models are 8 mm.
solids, exp = [], TopExp_Explorer(shape, TopAbs_SOLID)
while exp.More():
    solids.append(exp.Current())
    exp.Next()
body = max(solids, key=x_extent) if solids else None
hit = IntCurvesFace_ShapeIntersector()
hit.Load(body, 1e-7)


def faces_of_body(x, y):
    """(top, bottom) of the built board on the vertical line through (x, y)."""
    hit.Perform(gp_Lin(gp_Pnt(x, y, 0.0), gp_Dir(0, 0, 1)), -1e3, 1e3)
    zs = [hit.Pnt(k).Z() for k in range(1, hit.NbPnt() + 1)]
    return (max(zs), min(zs)) if zs else (None, None)


print("\n[1] the surface follows the material, and the body agrees")
stack = core._prepare_stackups(json.loads(jf.read_text(encoding="utf-8")), BuildOptions(), lambda m: None)
if not check("a board with zones and stackups is given a surface", stack.surface is not None, stack.surface):
    print("FAILURES:", fails)
    sys.exit(1)                    # every check below asks it
s2_top, s2_bottom = stack.levels["S2"]
window_body, opening_body, solid_body = (faces_of_body(*WINDOW), faces_of_body(*OPENING),
                                         faces_of_body(*SOLID_POINT))
check("the board was built, the solid 41 mm across", body is not None and x_extent(body) > 40.0,
      (len(solids), body is not None and x_extent(body)))
check("where the stiffener stands, the zone's stack is the board: its top face is the zone's",
      near(solid_body[0], s2_top) and near(solid_body[1], s2_bottom), (solid_body, (s2_top, s2_bottom)))
check("in the stiffener's window the body is 2.025 mm lower - the stiffener and its adhesive are not there",
      near(window_body[0], s2_top - 2.025), (window_body[0], s2_top))
check("and under the coverlay's opening its bottom is 0.025 mm higher",
      near(opening_body[1], s2_bottom + 0.025), (opening_body[1], s2_bottom))
for name, point, body_faces in (("in the window", WINDOW, window_body), ("over the opening", OPENING, opening_body),
                                ("on the stiffener", SOLID_POINT, solid_body)):
    here = stack.surface.at(*point)
    check(f"Surface.at {name} is the body's two faces there", here is not None
          and near(here[0], body_faces[0]) and near(here[1], body_faces[1]), (here, body_faces))
check("a point no zone holds has no surface", stack.surface.at(-5.0, -5.0) is None,
      stack.surface.at(-5.0, -5.0))

# Zones overlap on real boards (flex-b2 53.6 mm2): a point in two zones has
# the body of both under it, and the higher of their faces is the top.
overlap = json.loads(jf.read_text(encoding="utf-8"))
overlap["zones"][1]["contour"] = rect(0, 10.0, 41, 26.5)          # F2 now reaches 1.38 mm into S2
overlap_stack = core._prepare_stackups(overlap, BuildOptions(), lambda m: None)
inside_both = overlap_stack.surface.at(8.0, 10.5)
both = overlap_stack.levels
check("a point in two overlapping zones takes the highest top of the two and the lowest bottom - "
      "S2's stiffener above, F2's coverlay below",
      inside_both is not None and both["F2"][1] < both["S2"][1]
      and near(inside_both[0], max(both["S2"][0], both["F2"][0]))
      and near(inside_both[1], min(both["S2"][1], both["F2"][1])), (inside_both, both))

print("\n[2] a part stands on the surface under it, and the log says where that is not its zone's face")
for ref, point, body_faces, mirrored in (("P1", WINDOW, window_body, False), ("P2", OPENING, opening_body, True),
                                         ("P3", SOLID_POINT, solid_body, False)):
    comp = dict(board["components"][ref])
    z = component_transform(ZERO, comp, stack.board_top_z, stack.board_bottom_z, zone_levels=stack.levels,
                            surface=stack.surface).TranslationPart().Z()
    want = body_faces[1] if mirrored else body_faces[0]
    check(f"{ref} {'under the board' if mirrored else 'on top'} at {point}: on the body's face there",
          near(z, want), (z, want))
check("the part in the window is named, with how far below its zone's top it stands",
      any("P1 stands on the board's surface under it, 2.025 mm below the top of its zone S2" in m for m in logs),
      [m for m in logs if "stands on" in m])
check("and the one under the opened coverlay, with how far above the bottom",
      any("P2 stands on the board's surface under it, 0.025 mm above the bottom of its zone S2" in m for m in logs),
      [m for m in logs if "stands on" in m])
check("the part on the stiffener is not named", not any("P3 stands" in m for m in logs),
      [m for m in logs if "stands on" in m])

print("\n[3] a pad, its window and a drawn opening lie on the surface under them")
flat = []                          # (x, y, z) of every face the build wrote outside the board solid
exp = TopExp_Explorer(shape, TopAbs_FACE, TopAbs_SOLID)
while exp.More():
    box = Bnd_Box()
    BRepBndLib.Add_s(exp.Current(), box, False)
    x0, y0, z0, x1, y1, z1 = box.Get()
    if z1 - z0 < 1e-6:
        flat.append(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    exp.Next()


def heights_at(point, size):
    """z of the free faces centred on *point*, *size* across."""
    return sorted(round(z, 6) for x, y, z in flat if abs(x - point[0]) < 1e-3 and abs(y - point[1]) < 1e-3)


window_faces = heights_at(WINDOW, 1.0)
check("in the window: the mask window one clearance and the copper two above the body's face",
      len(window_faces) >= 2 and near(window_faces[0], window_body[0] + H)
      and near(window_faces[-1], window_body[0] + 2 * H), (window_faces, window_body[0], H))
bottom_faces = heights_at(OPENING, 1.0)
check("under the opened coverlay: the pad two clearances below the body's bottom",
      bottom_faces and near(bottom_faces[0], opening_body[1] - 2 * H), (bottom_faces, opening_body[1], H))
solid_faces = heights_at(SOLID_POINT, 1.0)
check("on the stiffener: as before, on its face", len(solid_faces) >= 2
      and near(solid_faces[-1], solid_body[0] + 2 * H), (solid_faces, solid_body[0]))
drawn = heights_at((8.0, 4.0), 0.5)
check("the drawn opening in the window: three clearances above the body under it",
      drawn and near(drawn[-1], faces_of_body(8.0, 4.0)[0] + 3 * H), (drawn, faces_of_body(8.0, 4.0)[0]))
# One height per polygon, and over two levels the zone's face: it never cuts
# into the body, where the window's floor would put half of it inside the
# stiffener (flex3-a0: four polygons by their centroid, round 103).
across = heights_at((8.0, 6.5), 0.5)
check("one across the window's edge stays on its zone's face, three clearances up, above all of the body",
      across and near(across[-1], s2_top + 3 * H), (across, s2_top))
check("and the log counts it", any("copper_top: 1 drawn-opening polygon(s) lie over more than one level" in m
                                   for m in logs), [m for m in logs if "copper_top" in m])
# A through pin's centre lies over its drill, which the stiffener's own
# shape holes as well: asked there, the surface is the flex's, 2.025 mm down,
# and the pad would lie inside the stiffener. Asked round the drill, on the
# copper, it is the stiffener's (flex3-a0's top pins, round 103).
drilled_body = faces_of_body(DRILLED[0] + 0.4, DRILLED[1])
drilled_faces = heights_at(DRILLED, 1.0)
check("a through pin whose layers are holed to its drill: the centre alone would sink it 2.025 mm",
      near(stack.surface.at(*DRILLED)[0], s2_top - 2.025) and near(drilled_body[0], s2_top),
      (stack.surface.at(*DRILLED), drilled_body))
check("asked round the drill, its window and pad lie on the stiffener, one and two clearances up",
      len(drilled_faces) >= 4 and near(drilled_faces[-1], s2_top + 2 * H)
      and near(drilled_faces[-2], s2_top + H), (drilled_faces, s2_top))
check("and under the board, two clearances below its bottom",
      drilled_faces and near(drilled_faces[0], s2_bottom - 2 * H), (drilled_faces, s2_bottom))
# Half of the ring round a pin on the window's edge finds the window's floor,
# half the stiffener: the copper is laid on the outermost, never inside it.
edge_faces = heights_at(EDGE, 1.0)
check("a through pin on the window's edge: its pad on the stiffener, not inside it",
      edge_faces and near(edge_faces[-1], s2_top + 2 * H), (edge_faces, s2_top))
where = P._Zones(stack.zones, stack.stackups, stack.levels, stack.board_top_z, stack.board_bottom_z,
                 stack.surface)
check("the pads' own lookup gives the surface, the zone's conductors beside it",
      where.at(*WINDOW) == (("TOP", "BOTTOM"), stack.surface.at(*WINDOW)), where.at(*WINDOW))

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)
