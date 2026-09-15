# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import fails, check, count_solids, volume

"""Cutouts that overlap EACH OTHER used to come back as holes with plugs in them.

Every cutout prism used to be added to one TopoDS_Compound and that compound
handed to BRepAlgoAPI_Cut as the tool. OCC requires each argument of a boolean
to be free of self-interference: it intersects the arguments against one
another but never the members of ONE argument against each other. A compound
holding prisms that overlap is self-interfering, and where two of them met the
result was undefined.

What that looked like on the user's circle-a0 - a round board broken out of its
panel by six break-off tabs - is the reason this file exists. Each tab is a
1.0 mm cutout tangent to the outline, and the 0.25 mm mouse-bite drill beside
it overlaps that circle by 0.118 mm. Three of those six drills came back not as
holes but as loose 0.1654 mm3 plugs: separate solids sitting exactly in the
hole, so the STEP carried 4 bodies instead of 1 and the viewer showed a filled
hole with the hole's own wall drawn through it. Which three was arbitrary - two
tabs that are mirror images of each other across the board came out
differently - which is what self-interference buys you.

The prisms now go in as separate TOOLS. Then OCC intersects them pairwise and
the answer is right; it costs the same 0.3 s on that board.

The numbers here are analytic, not measured: a circle straddling the outline
removes the lens where the two discs meet, and `_lens` is that area.
"""
import math
import sys

from stepbuilder import core

R = 7.5           # board radius
TH = 1.0          # board thickness
TAB_R, TAB_D = 1.0, 8.5       # break-off tab: tangent to the outline from OUTSIDE
DRILL_R, DRILL_D = 0.25, 7.375  # mouse bite: straddles the outline, overlaps the tab


def circle(x, y, r):
    return [{"type": "circle", "x": x, "y": y, "radius": r}]


def _lens(big, small, d) -> float:
    """Area shared by two discs of radii *big* and *small*, centres *d* apart."""
    return (small ** 2 * math.acos((d * d + small ** 2 - big ** 2) / (2 * d * small))
            + big ** 2 * math.acos((d * d + big ** 2 - small ** 2) / (2 * d * big))
            - 0.5 * math.sqrt((-d + small + big) * (d + small - big)
                              * (d - small + big) * (d + small + big)))


def board(edges):
    pcb = {"thickness": {"soldermask_top": 0.0, "board": TH,
                         "soldermask_bottom": 0.0},
           "color": {"r": 0.0, "g": 0.4, "b": 0.0},
           "edges": edges}
    return core.make_board_geometry(pcb, TH, 0.0, log=lambda m: None)


def panel(angles) -> list:
    """The outline, then a tab and its mouse bite at each angle (degrees)."""
    edges = [circle(0.0, 0.0, R)]
    for deg in angles:
        a = math.radians(deg)
        edges.append(circle(TAB_D * math.cos(a), TAB_D * math.sin(a), TAB_R))
        edges.append(circle(DRILL_D * math.cos(a), DRILL_D * math.sin(a), DRILL_R))
    return edges


DISC = math.pi * R * R * TH
BITE = _lens(R, DRILL_R, DRILL_D) * TH        # 0.157 mm3, one mouse bite

print("\n[1] the two cutouts of one break-off tab, on their own")
# The tab circle sits OUTSIDE the board and touches it at a point: it is there
# to shape the panel, and it must take nothing off the board itself.
tab_only = volume(board([circle(0.0, 0.0, R), circle(TAB_D, 0.0, TAB_R)]))
check(f"a tangent tab cutout removes nothing: {DISC:.4f} mm3",
      abs(tab_only - DISC) < 1e-6, f"{tab_only:.6f}")

bite_only = volume(board([circle(0.0, 0.0, R), circle(DRILL_D, 0.0, DRILL_R)]))
check(f"the mouse bite alone takes {BITE:.6f} mm3",
      abs(bite_only - (DISC - BITE)) < 1e-6, f"{bite_only:.6f}")

print("\n[2] both together - the pair that used to leave a plug")
one = board(panel([0.0]))
check("one tab and its bite: still ONE solid", count_solids(one) == 1,
      count_solids(one))
check(f"and the bite really is gone: {DISC - BITE:.4f} mm3",
      abs(volume(one) - (DISC - BITE)) < 1e-6, f"{volume(one):.6f}")

print("\n[3] six tabs, as the board that found this")
ANGLES = [20.0, 90.0, 160.0, 200.0, 270.0, 340.0]
six = board(panel(ANGLES))
# THE assertion. Under the compound this was 7: the board and six loose plugs,
# every one of them exactly filling the hole it was supposed to be.
check("six tabs, six bites: ONE solid and no plugs", count_solids(six) == 1,
      f"{count_solids(six)} solids")
want = DISC - len(ANGLES) * BITE
check(f"all six bites are cut: {want:.4f} mm3",
      abs(volume(six) - want) < 1e-6, f"{volume(six):.6f}")

print("\n[4] cutouts that overlap well inside the board")
# Nothing degenerate here - no tangency to the outline - but it is the same
# self-interfering tool, and the union of two overlapping discs is what must
# come out, not their sum.
a, b, d = 1.0, 1.0, 1.2
both = volume(board([circle(0.0, 0.0, R), circle(0.0, 0.0, a),
                     circle(d, 0.0, b)]))
union = (math.pi * a * a + math.pi * b * b - _lens(a, b, d)) * TH
check(f"two overlapping holes remove their union: {DISC - union:.4f} mm3",
      abs(both - (DISC - union)) < 1e-6, f"{both:.6f}")
check("and leave one solid", count_solids(board(
    [circle(0.0, 0.0, R), circle(0.0, 0.0, a), circle(d, 0.0, b)])) == 1)

print("\n[5] the per-layer build cuts them the same way")
# make_board_layer_parts goes through _cut_out rather than make_board_geometry,
# and used to carry its own copy of the same compound.
LAYERS = [{"name": "TOP", "type": "CONDUCTOR", "thickness": TH / 2,
           "z_top": 0.0, "z_bottom": -TH / 2, "negative": False, "shapes": None},
          {"name": "BOTTOM", "type": "CONDUCTOR", "thickness": TH / 2,
           "z_top": -TH / 2, "z_bottom": -TH, "negative": False, "shapes": None}]
edges = panel(ANGLES)
pcb = {"thickness": {"soldermask_top": 0.0, "board": TH, "soldermask_bottom": 0.0},
       "color": {"r": 0.0, "g": 0.4, "b": 0.0},
       "edges": edges}
parts = core.make_board_layer_parts(
    pcb, {"S": {"thickness": TH, "layers": LAYERS}},
    [{"name": "Z", "stackup": "S", "contour": edges[0]}], 0.0, lambda m: None)
check("both layers survive", len(parts) == 2, len(parts))
check("and neither carries a plug",
      all(count_solids(solid) == 1 for _, _, solid in parts),
      [count_solids(s) for _, _, s in parts])
total = sum(volume(solid) for _, _, solid in parts)
check(f"together they are the same board: {want:.4f} mm3",
      abs(total - want) < 1e-6, f"{total:.6f}")

print("\n[6] a layer's own shapes, which are the same mistake in 2-D")

# _layer_region carried the identical compound: the shapes of one layer handed
# to a boolean as ONE argument. On faces it does not even degrade - it drops
# all but one of them - and bare tangency is enough. Areas here, not volumes:
# the region is a face, and the layer solid is extruded from it afterwards.
from stepbuilder.board import _layer_region
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps


def face_area(shape) -> float:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, props)
    return props.Mass()


def zone_rect(x0, y0, x1, y1):
    return [{"type": "segment", "start": [x0, y0], "end": [x1, y0]},
            {"type": "segment", "start": [x1, y0], "end": [x1, y1]},
            {"type": "segment", "start": [x1, y1], "end": [x0, y1]},
            {"type": "segment", "start": [x0, y1], "end": [x0, y0]}]


ZONE = zone_rect(0.0, 0.0, 20.0, 20.0)
ZONE_AREA = 400.0
SR = 3.0                                   # both shapes are r = 3 discs


def region(d, negative):
    """The material of a layer carrying two r = 3 discs, centres *d* apart."""
    shapes = [{"outline": circle(10.0 - d / 2, 10.0, SR), "voids": []},
              {"outline": circle(10.0 + d / 2, 10.0, SR), "voids": []}]
    return _layer_region({"name": "L", "negative": negative, "shapes": shapes},
                         ZONE, 0.0, lambda m: None)


# Apart, touching, overlapping. The middle row is the one that names the fault:
# at d = 2r the discs share no area at all, and one of them still vanished.
for d, label in ((6.001, "1 um apart"), (6.0, "exactly touching"),
                 (5.0, "overlapping by 1 mm"), (4.0, "overlapping by 2 mm")):
    union = 2 * math.pi * SR ** 2 - (_lens(SR, SR, d) if d < 2 * SR else 0.0)
    got = face_area(region(d, negative=True))
    check(f"negative, {label}: the zone minus BOTH openings, {ZONE_AREA - union:.4f} mm2",
          abs(got - (ZONE_AREA - union)) < 1e-6, f"{got:.6f}")
    got = face_area(region(d, negative=False))
    check(f"positive, {label}: the union of both shapes, {union:.4f} mm2",
          abs(got - union) < 1e-6, f"{got:.6f}")

# What the compound gave, kept as the number to recognise it by: ONE disc, so
# 28.27433 mm2 of material and 371.72567 mm2 left in the zone - the same answer
# whatever the overlap was, because the second shape was not mis-cut but ignored.
ONE_DISC = math.pi * SR ** 2
check("and neither answer is the one-shape answer the compound gave",
      abs(face_area(region(4.0, True)) - (ZONE_AREA - ONE_DISC)) > 1.0
      and abs(face_area(region(4.0, False)) - ONE_DISC) > 1.0)

print("\n[7] a shape's voids are holes in it, not separate tools")

# The voids belong to the shape's own face, so they must survive the move to a
# list of arguments - a void turned into a tool of its own would ADD material.
holed = [{"outline": circle(6.0, 10.0, SR), "voids": [circle(6.0, 10.0, 1.0)]},
         {"outline": circle(11.0, 10.0, SR), "voids": []}]
cut = face_area(_layer_region({"name": "L", "negative": True, "shapes": holed},
                              ZONE, 0.0, lambda m: None))
opened = 2 * math.pi * SR ** 2 - _lens(SR, SR, 5.0) - math.pi * 1.0 ** 2
check(f"the void is left as material: {ZONE_AREA - opened:.4f} mm2",
      abs(cut - (ZONE_AREA - opened)) < 1e-6, f"{cut:.6f}")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
