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

"""Folding flex bends: the property parser, the plan, and the built geometry.

The numbers here are not snapshots of what the code happened to produce - each
one is worked out from the bend by hand first (arc length, where the far panel
lands, how high the fold reaches) and the geometry is required to match it.
"""
import json, math, sys

ROOT = _ROOT
sys.path.insert(0, str(ROOT))
from stepbuilder import core
from stepbuilder.bend import (
    Bend, DEFAULT_SLICE_ANGLE, bend_from_dict, bends_from_json, clip_halfplane,
    contour_points, info_length, parse_bend_info, plan_fold, plan_from_json,
    point_in_polygon, polygon_area,
)

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.gp import gp_Dir, gp_Pnt

OUT = _OUT / "bend"
OUT.mkdir(exist_ok=True)
fails = []


def check(n, c, d=""):
    print(f"  {'PASS' if c else 'FAIL'}  {n}{'' if c else '  <- ' + str(d)}")
    c or fails.append(n)


def near(a, b, tol=1e-6):
    return abs(a - b) <= tol


def volume(shape):
    # The ITERATIVE integrator. The plain call measures a solid with B-spline
    # walls - which is what a wrapped bend has - about 1.5% light, and every
    # number in this file would be measuring that instead of the geometry.
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props, 1.0e-6, False, False)
    return props.Mass()


def bbox(shape):
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, True)
    return box.Get()


def rect(x0, y0, x1, y1):
    return [{"type": "segment", "start": [x0, y0], "end": [x1, y0]},
            {"type": "segment", "start": [x1, y0], "end": [x1, y1]},
            {"type": "segment", "start": [x1, y1], "end": [x0, y1]},
            {"type": "segment", "start": [x0, y1], "end": [x0, y0]}]


# --------------------------------------------------------------------------- #
print("\n[1] IDX_BEND_TYPE_INFO - the undocumented property")

REAL = ("TYPE=CircularBend, INNER_SIDE=TOP, INNER_ANGLE=28.2600, "
        "INNER_RADIUS=2.5000 MILLIMETERS, ORDER=0")
f = parse_bend_info(REAL)
check("TYPE read", f.get("TYPE") == "CircularBend", f)
check("INNER_SIDE read", f.get("INNER_SIDE") == "TOP", f)
check("INNER_ANGLE read", near(float(f["INNER_ANGLE"]), 28.26), f)
check("ORDER read", f.get("ORDER") == "0", f)
check("radius carries its unit and converts",
      near(info_length(f["INNER_RADIUS"]), 2.5), info_length(f["INNER_RADIUS"]))
check("a mil radius is not read as mm",
      near(info_length("100.0 MILS"), 2.54), info_length("100.0 MILS"))
check("a bare number is taken as mm", near(info_length("2.5"), 2.5))
check("no number at all -> None", info_length("MILLIMETERS") is None)
check("unknown keys survive rather than being dropped",
      parse_bend_info("A=1, WHAT=yes").get("WHAT") == "yes")
check("garbage does not raise", parse_bend_info("nonsense") == {})
check("a non-string does not raise", parse_bend_info(None) == {})
# The memo's copy of the property ends in ", ..." - the real one has more
# fields, and the parser must not care.
check("trailing unknown fields are harmless",
      parse_bend_info(REAL + ", SOMETHING_NEW=7").get("TYPE") == "CircularBend")

# --------------------------------------------------------------------------- #
print("\n[2] reading a bend out of the intermediate")

ENTRY = {"name": "BEND1", "line": {"start": [10.0, 0.0], "end": [10.0, 20.0]},
         "inner_radius": 2.5, "width": 4.5, "info": REAL}
b = bend_from_dict(ENTRY)
check("angle comes from the raw property when nothing else carries it",
      b is not None and near(b.angle, 28.26), b)
check("radius comes from the API field", near(b.radius, 2.5))
check("inner side read", b.inner_side == "top")
check("order read", b.order == 0)
check("measured width kept", near(b.width, 4.5))
check("midpoint", b.midpoint == (10.0, 10.0))
check("length", near(b.length, 20.0))

over = dict(ENTRY, angle=45.0, inner_side="BOTTOM")
b2 = bend_from_dict(over)
check("an explicit field wins over the raw property",
      near(b2.angle, 45.0) and b2.inner_side == "bottom")
check("no line -> unreadable", bend_from_dict({"name": "x"}) is None)
check("no angle anywhere -> unreadable",
      bend_from_dict({"name": "x", "line": ENTRY["line"], "inner_radius": 1.0}) is None)

logs = []
check("a flat bend is dropped, with a word about it",
      bends_from_json({"bends": [dict(ENTRY, angle=0.0)]}, logs.append) == []
      and any("left flat" in m for m in logs), logs)
check("no bends key at all -> nothing, silently",
      bends_from_json({}, logs.append) == [])

# --------------------------------------------------------------------------- #
print("\n[3] one 90 degree bend, worked out by hand")

# A 40 x 10 strip, 0.4 thick, top face at z=0 (the datum the builder uses).
T = 0.4
R = 1.0
strip = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, -T), 40.0, 10.0, T).Shape()
flat_volume = volume(strip)
outline = [(0, 0), (40, 0), (40, 10), (0, 10)]

bend = Bend(name="B1", start=(20.0, 0.0), end=(20.0, 10.0),
            angle=90.0, radius=R, inner_side="top", order=0)
plan = plan_fold([bend], outline, board_top_z=0.0, board_bottom_z=-T)

# Neutral radius = inner radius + half the stack; an arc that long is the flat
# material the fold consumes, half of it either side of the bend line.
neutral = R + T / 2
developed = neutral * math.pi / 2
arc_start = 20.0 - developed / 2          # where the board stops being flat
arc_end = 20.0 + developed / 2            # where it is flat again, standing up
tail = 40.0 - arc_end
z_axis = 0.0 + R                          # cylinder axis: R above the top face

# The whole fold, in closed form. For a 90 degree bend with the top face on the
# inside, a flat point (v, z) past the strip lands at
#     x = arc_start + (z_axis - z)        <- how far it was below the axis
#     z = z_axis + (v - arc_end)          <- how far it was past the strip
# Panels get the exact transform, so these are not approximations: only the
# curved part between arc_start and arc_end is faceted.
def fold90(v, z):
    return arc_start + (z_axis - z), z_axis + (v - arc_end)


folded = plan.apply(strip)
xmin, ymin, zmin, xmax, ymax, zmax = bbox(folded)

check("the strip is cut into panels and slices, not left whole",
      len(plan.regions) == 2 + math.ceil(90.0 / DEFAULT_SLICE_ANGLE),
      len(plan.regions))
check("the far panel stands up exactly as far as it is long",
      near(zmax, fold90(40.0, 0.0)[1], 1e-6), (zmax, fold90(40.0, 0.0)[1]))
check("nothing pokes out past the outside of the bend",
      near(xmax, fold90(40.0, -T)[0], 0.02), (xmax, fold90(40.0, -T)[0]))
check("the held end has not moved", near(xmin, 0.0, 1e-6), xmin)
check("the board is not thinner or thicker where it is flat",
      near(zmin, -T, 1e-6), zmin)
check("volume is preserved to within the deliberate slice overlap",
      abs(volume(folded) - flat_volume) / flat_volume < 0.005,
      (volume(folded), flat_volume))
check("the fold is one solid, not a heap of slices",
      volume(folded) > 0 and not folded.IsNull())

# --------------------------------------------------------------------------- #
print("\n[4] inner side decides which way it folds")

down = Bend(name="B1", start=(20.0, 0.0), end=(20.0, 10.0),
            angle=90.0, radius=R, inner_side="bottom")
plan_down = plan_fold([down], outline, 0.0, -T)
_, _, zmin_d, _, _, zmax_d = bbox(plan_down.apply(strip))
# mirror of the case above: the axis sits R BELOW the bottom face
check("inner side BOTTOM folds the tail downwards, by the same amount",
      near(zmin_d, -(T + R) - tail, 1e-6), (zmin_d, -(T + R) - tail))
check("and nothing of it is left above the board", near(zmax_d, 0.0, 1e-6), zmax_d)

# --------------------------------------------------------------------------- #
print("\n[5] the anchor decides what is held - the origin by default")

# Bend at x=10 on a strip running 0..40: the anchor at the origin holds the
# SHORT end, which is the opposite of what "hold the largest piece" would do.
near_end = Bend(name="B1", start=(10.0, 0.0), end=(10.0, 10.0),
                angle=90.0, radius=R, inner_side="top")
plan_near = plan_fold([near_end], outline, 0.0, -T)
folded_near = plan_near.apply(strip)
xmin_n, _, _, xmax_n, _, zmax_n = bbox(folded_near)
# the far edge of the model is now the OUTSIDE of the bend, not the tail
check("the piece containing the origin stays put",
      near(xmin_n, 0.0, 1e-6)
      and near(xmax_n, (10.0 - developed / 2) + (z_axis + T), 1e-6),
      (xmin_n, xmax_n))
check("and the long side is the one that stands up",
      near(zmax_n, z_axis + (40.0 - (10.0 + developed / 2)), 1e-6), zmax_n)

auto = plan_fold([near_end], outline, 0.0, -T, anchor=None)
folded_auto = auto.apply(strip)
_, _, _, xmax_a, _, zmax_a = bbox(folded_auto)
check("'auto' still holds the largest piece, the way it did before",
      near(xmax_a, 40.0, 1e-6), xmax_a)
check("and then it is the short side that stands up",
      near(zmax_a, z_axis + (10.0 - developed / 2), 1e-6), zmax_a)

far = plan_fold([near_end], outline, 0.0, -T, anchor=(40.0, 5.0))
_, _, _, xmax_f, _, _ = bbox(far.apply(strip))
check("an anchor at the other end holds that end instead",
      near(xmax_f, 40.0, 1e-6), xmax_f)
outside = plan_fold([near_end], outline, 0.0, -T, anchor=(-50.0, -50.0))
check("the anchor does not have to be inside the board",
      outside.region_at(1.0, 5.0) == "held", outside.region_at(1.0, 5.0))
check("the plan says where it held", any("anchor at 0.000, 0.000" in n
                                         for n in plan_near.notes), plan_near.notes)

print("\n[5b] the K factor sets how much material the bend eats")

for k, want in ((0.5, (R + T / 2) * math.pi / 2), (0.0, R * math.pi / 2),
                (1.0, (R + T) * math.pi / 2)):
    p = plan_fold([bend], outline, 0.0, -T, neutral_factor=k)
    check(f"k={k}: developed length is angle x (radius + {k} x thickness)",
          near(2 * p.chain[0][3], want, 1e-9), (2 * p.chain[0][3], want))
# k=0 is Allegro's own bend area, which is drawn at the inner radius: the real
# board's 28.26 deg at R=2.5 gives the 1.2331 mm the design actually carries.
real_shape = Bend(name="B", start=(20.0, 0.0), end=(20.0, 10.0),
                  angle=28.26, radius=2.5)
check("k=0 reproduces the bend area Allegro draws",
      near(2 * plan_fold([real_shape], outline, 0.0, -0.365,
                         neutral_factor=0.0).chain[0][3],
           2.5 * math.radians(28.26), 1e-9))

# --------------------------------------------------------------------------- #
print("\n[6] two bends in a chain")

# Bends at x=20 and x=30, both 90 deg up: a Z fold. The second is applied in
# the frame the first one leaves, so the far panel ends up horizontal again,
# pointing back the way it came.
b1 = Bend(name="B1", start=(20.0, 0.0), end=(20.0, 10.0), angle=90.0, radius=R)
b2 = Bend(name="B2", start=(30.0, 0.0), end=(30.0, 10.0), angle=90.0, radius=R)
plan2 = plan_fold([b1, b2], outline, 0.0, -T)
check("both bends make it into the chain", len(plan2.bends) == 2,
      [x.name for x in plan2.bends])
check("they are ordered from the held end outwards",
      [x.name for x in plan2.bends] == ["B1", "B2"])

folded2 = plan2.apply(strip)
x0, y0, z0, x1, y1, z1 = bbox(folded2)
# Both folds in closed form. The second one is applied in the frame the first
# leaves, so the far panel comes back horizontal, upside down, pointing the way
# it came - a Z fold. Its underside is the highest thing on the model:
#   fold 2 puts flat (40, -T) at   ( 30-dev/2 + (1+T),  1 + 40 - (30+dev/2) )
#   fold 1 then lifts that to      z = 1 + x - (20+dev/2)
p = (30.0 - developed / 2 + (z_axis + T), z_axis + 40.0 - (30.0 + developed / 2))
top_of_z_fold = z_axis + p[0] - arc_end
check("the far panel comes to rest a stack's thickness above the first fold",
      # +/- one facet: the second arc's outer surface overshoots its chord
      near(z1, top_of_z_fold, 0.05), (z1, top_of_z_fold))
check("the far panel folds back over the board, not further up",
      x1 < 40.0 - 5.0, x1)
check("volume still preserved", abs(volume(folded2) - flat_volume) / flat_volume < 0.01,
      volume(folded2))

# --------------------------------------------------------------------------- #
print("\n[7] bends that are not a chain are refused, loudly")

cross = Bend(name="B2", start=(20.4, 0.0), end=(20.4, 10.0), angle=90.0, radius=R)
plan3 = plan_fold([b1, cross], outline, 0.0, -T)
check("only the first of two overlapping bends is folded",
      [x.name for x in plan3.bends] == ["B1"], [x.name for x in plan3.bends])
check("and it says why", any("cannot be read" in n for n in plan3.notes),
      plan3.notes)

print("\n[7a] two PERPENDICULAR bends, both real")

# Cadence's own demo board, reduced. The FLEXI arm leaves the main board, turns
# a corner and turns again: BEND_2 and BEND_1 are at right angles to each other,
# 33.9 mm between their centres, sharing no material at all. Judged by a single
# projection along one normal - which is what the clash test used to do - they
# read as 9.19 mm apart with strips 8.3 and 9.9 mm wide, and one of the two real
# bends was thrown away as unreadable. A strip is a rectangle, not a band.
corner_a = Bend(name="B2", start=(132.25, 56.9), end=(119.5, 69.4),
                angle=180.0, radius=5.0)
corner_b = Bend(name="B1", start=(135.6, 85.622), end=(149.7, 99.5),
                angle=180.0, radius=6.0, inner_side="bottom")
arm_outline = [(90, 40), (160, 40), (160, 110), (90, 110)]
plan_corner = plan_fold([corner_a, corner_b], arm_outline, 0.0, -T,
                        anchor=(0.0, 0.0))
check("both bends of the corner are folded", len(plan_corner.bends) == 2,
      [b.name for b in plan_corner.bends])
check("neither is reported as unreadable",
      not any("cannot be read" in n for n in plan_corner.notes), plan_corner.notes)

print("\n[7a1] and a corner in ONE arm: the second rides on the first")

# An L-shaped arm, the shape a flex takes when it turns a corner: the only way
# from the held end to the far end is through A and then through B, and the two
# bend lines are at right angles. Nothing but the connectivity says so - the two
# strips are nowhere near each other, and neither lies "beyond" the other in any
# useful sense.
ell_arm = [(0, 0), (60, 0), (60, 80), (40, 80), (40, 20), (0, 20)]
ell_a = Bend(name="A", start=(30.0, 0.0), end=(30.0, 20.0), angle=90.0, radius=R)
ell_b = Bend(name="B", start=(40.0, 50.0), end=(60.0, 50.0), angle=90.0, radius=R)
plan_ell = plan_fold([ell_a, ell_b], ell_arm, 0.0, -T, anchor=(5.0, 10.0))
check("both fold", len(plan_ell.bends) == 2, [b.name for b in plan_ell.bends])
check("in the order the arm reaches them",
      [s.bend.name for s in plan_ell.strips] == ["A", "B"],
      [s.bend.name for s in plan_ell.strips])
check("the held end is the one the anchor is on",
      plan_ell.region_at(5.0, 10.0) == "held", plan_ell.region_at(5.0, 10.0))
check("the piece between them rides on A alone",
      plan_ell.region_at(50.0, 30.0) == "panel after A",
      plan_ell.region_at(50.0, 30.0))
check("and the far end rides on both",
      plan_ell.region_at(50.0, 75.0) == "panel after B",
      plan_ell.region_at(50.0, 75.0))
# A turns the far arm 90 deg up; B then turns its own far end 90 deg again, in
# the frame A left. The end cannot still be flat.
tip = gp_Pnt(50.0, 75.0, 0.0).Transformed(plan_ell.transform_at(50.0, 75.0))
check("so the tip has left the plane twice over", abs(tip.Z()) > 1.0, tip.Z())

print("\n[7b0] two arms whose normals are perpendicular, far apart")

# The crash. Two bends on DIFFERENT arms, ~135 mm apart one way and 66 mm the
# other: each lies far beyond the other's strip, so each read as containing the
# other, `parent` became a cycle and the build died with a KeyError before it
# reached any geometry. Neither carries anything here - both hang off the held
# panel.
far_a = Bend(name="FA", start=(88.15, -43.7), end=(98.4, -53.85),
             angle=45.0, radius=20.0)
far_b = Bend(name="FB", start=(135.6, 85.622), end=(149.7, 99.5),
             angle=180.0, radius=6.0, inner_side="bottom")
wide = [(-30, -60), (160, -60), (160, 110), (-30, 110)]
plan_far = plan_fold([far_a, far_b], wide, 0.0, -T, anchor=(0.0, 0.0))
check("both are folded rather than one being dropped", len(plan_far.bends) == 2,
      [b.name for b in plan_far.bends])
check("neither ends up carrying the other - they are separate arms",
      plan_far.region_at(0.0, 0.0) == "held", plan_far.region_at(0.0, 0.0))
check("and nothing was left unplaced", len(plan_far.strips) == 2,
      len(plan_far.strips))

print("\n[7b1] whatever the bends are, the plan is finite and complete")

# The property the KeyError broke: every bend that survives the clash test gets
# exactly one strip, and plan_fold returns. Random layouts, because the failing
# board was found by a user rather than by anything here - a bend set that makes
# the carries relation cyclic must degrade to a note, not to an exception or a
# loop that never ends.
import random

rng = random.Random(20260814)
worst = None
for trial in range(300):
    made = []
    for k in range(rng.randint(2, 5)):
        x, y = rng.uniform(-80, 160), rng.uniform(-60, 140)
        theta = rng.uniform(0, math.pi)
        half = rng.uniform(4, 12)
        made.append(Bend(name=f"R{k}",
                         start=(x - half * math.cos(theta), y - half * math.sin(theta)),
                         end=(x + half * math.cos(theta), y + half * math.sin(theta)),
                         angle=rng.choice([45.0, 90.0, 180.0]),
                         radius=rng.choice([2.0, 5.0, 10.0]),
                         inner_side=rng.choice(["top", "bottom"])))
    try:
        p = plan_fold(made, wide, 0.0, -T, anchor=(0.0, 0.0))
    except Exception as exc:                       # noqa: BLE001 - that is the test
        worst = f"trial {trial}: {type(exc).__name__}: {exc}"
        break
    if len(p.strips) != len(p.bends):
        worst = f"trial {trial}: {len(p.bends)} bends but {len(p.strips)} strips"
        break

check("300 random bend layouts all plan without raising", worst is None, worst)

print("\n[7b] two arms off one held panel - the shape the real board has")

# BEND_2 near one end folding down, BEND_1 near the other folding up, with the
# middle held. Neither bend is beyond the other, so a flat chain would have
# thrown the second one away.
arm_a = Bend(name="A", start=(0.0, 8.0), end=(10.0, 8.0), angle=90.0, radius=R,
             inner_side="bottom")
arm_b = Bend(name="B", start=(0.0, 24.0), end=(10.0, 24.0), angle=90.0, radius=R)
tall = [(0, 0), (10, 0), (10, 32), (0, 32)]
# The anchor is what makes this two arms rather than a chain: put it in the
# middle and both bends hang off the held panel. At the origin the same two
# bends would be a chain, and the board would swing as one.
plan_arms = plan_fold([arm_a, arm_b], tall, 0.0, -T, anchor=(5.0, 16.0))
check("both arms are folded", len(plan_arms.bends) == 2,
      [b.name for b in plan_arms.bends])
check("nothing is reported as unreadable",
      not any("cannot be read" in n for n in plan_arms.notes), plan_arms.notes)
check("the middle is held", plan_arms.region_at(5, 16) == "held",
      plan_arms.region_at(5, 16))
low = gp_Pnt(5.0, 2.0, 0.0).Transformed(plan_arms.transform_at(5.0, 2.0))
high = gp_Pnt(5.0, 30.0, 0.0).Transformed(plan_arms.transform_at(5.0, 30.0))
check("one arm goes down and the other up",
      low.Z() < -1.0 and high.Z() > 1.0, (low.Z(), high.Z()))
# Each arm swings about its own axis, and a point on the top face ends up its
# radius-plus-whatever away from where the arc starts: the downward fold puts
# the axis T+R below the top face, the upward one R above it.
check("each arm swings about its own axis and leaves the other alone",
      near(low.Y(), (8.0 + developed / 2) - (T + R), 1e-6)
      and near(high.Y(), (24.0 - developed / 2) + R, 1e-6), (low.Y(), high.Y()))

tall_strip = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, -T), 10.0, 32.0, T).Shape()
arms_solid = plan_arms.apply(tall_strip)
_, _, az0, _, _, az1 = bbox(arms_solid)
check("the folded board reaches both ways",
      az1 > 5.0 and az0 < -5.0, (az0, az1))
check("and keeps its material", abs(volume(arms_solid) - 10 * 32 * T) / (10 * 32 * T) < 0.01,
      volume(arms_solid))

# --------------------------------------------------------------------------- #
print("\n[7b2] no piece of the board is ever claimed twice")

# The invariant the half-plane model could not hold. A region used to be an
# intersection of half-planes, and a half-plane crosses the WHOLE board: on
# Cadence's demo board "beyond BEND_5" also covered the LCD arm 180 mm away and
# the main board itself, so 25% of the board was claimed by two or three regions
# at once, the held panel was folded by a bend it has nothing to do with, and the
# folded body weighed 114.7% of the flat one. Regions are pieces of the outline
# now, so every point belongs to exactly one, whatever shape the board is.
from stepbuilder.bend import _double_claimed

check("a plain single bend claims nothing twice",
      _double_claimed(plan, outline) == 0.0, _double_claimed(plan, outline))
check("nor does a Z fold, where the bends are parallel",
      _double_claimed(plan2, outline) == 0.0, _double_claimed(plan2, outline))
check("nor two arms in opposite directions",
      _double_claimed(plan_arms, tall) == 0.0, _double_claimed(plan_arms, tall))
check("nor a corner in one arm",
      _double_claimed(plan_ell, ell_arm) == 0.0,
      _double_claimed(plan_ell, ell_arm))


# The shape that used to break it. Two of Cadence's own bends: XA leaves the
# middle on a diagonal towards the bottom right, XB straight up 180 mm away.
# "Beyond XA" has a large +y component and sweeps across the whole of XB's arm.
cross_a = Bend(name="XA", start=(88.15, -43.7), end=(98.4, -53.85),
               angle=45.0, radius=20.0)
cross_b = Bend(name="XB", start=(35.95, 132.428), end=(25.95, 132.428),
               angle=180.0, radius=10.0)
wide_board = [(-40, -60), (160, -60), (160, 190), (-40, 190)]
plan_cross = plan_fold([cross_a, cross_b], wide_board, 0.0, -T, anchor=(0.0, 0.0))
check("two arms at right angles claim nothing in common",
      _double_claimed(plan_cross, wide_board) == 0.0,
      _double_claimed(plan_cross, wide_board))
check("and the middle, where the anchor is, is still held",
      plan_cross.region_at(0.0, 0.0) == "held", plan_cross.region_at(0.0, 0.0))
check("neither arm is folded by the other's bend",
      plan_cross.region_at(20.0, 170.0) != plan_cross.region_at(120.0, -55.0),
      (plan_cross.region_at(20.0, 170.0), plan_cross.region_at(120.0, -55.0)))
check("and nothing is reported as unreadable",
      not any("cannot be read" in n for n in plan_cross.notes), plan_cross.notes)

# --------------------------------------------------------------------------- #
print("\n[7c] two 180 deg bends that MEET - the ring, and the K factor")

# The real reason two bends collide, nine times out of ten, is the K factor -
# and the log has to say so, because the board looks perfectly legal in Allegro.
# Two 180 degree bends whose areas touch: Allegro draws each area at the INNER
# arc, pi x R, so at k = 0 they meet exactly and the flex closes into a ring. At
# k = 0.5 each strip wants pi x (R + T/2) instead and they overlap.
ring_r = 0.8
ring_gap = math.pi * ring_r                 # what Allegro draws, and the spacing
ring_a = Bend(name="R1", start=(0.0, 20.0), end=(10.0, 20.0), angle=180.0,
              radius=ring_r, inner_side="top", width=ring_gap)
ring_b = Bend(name="R2", start=(0.0, 20.0 + ring_gap), end=(10.0, 20.0 + ring_gap),
              angle=180.0, radius=ring_r, inner_side="top", width=ring_gap)
ring_outline = [(0, 0), (10, 0), (10, 40), (0, 40)]
ring_half = plan_fold([ring_a, ring_b], ring_outline, 0.0, -T, anchor=(5.0, 0.0))
check("at k = 0.5 the second of two touching 180 deg bends is refused",
      [b.name for b in ring_half.bends] == ["R1"],
      [b.name for b in ring_half.bends])
check("and the log blames the neutral factor, not the board",
      any("neutral factor" in n for n in ring_half.notes), ring_half.notes)
check("and names the value that would fit - 0.00, the inner arc",
      any("at 0.00 the two strips meet" in n for n in ring_half.notes),
      ring_half.notes)
ring_zero = plan_fold([ring_a, ring_b], ring_outline, 0.0, -T, anchor=(5.0, 0.0),
                      neutral_factor=0.0)
check("at k = 0 both fold, and the flex closes into a ring",
      [b.name for b in ring_zero.bends] == ["R1", "R2"],
      [b.name for b in ring_zero.bends])
# Two 180 degree bends the same way with nothing flat between them is one whole
# turn: pi x R + pi x R of material is exactly the circumference of the top
# face's circle, so the tail comes back into the plane it started in, pointing
# the same way, beginning exactly where the held panel stopped. The loop stands
# up out of the board - which is what the ring board looks like.
ring_end = gp_Pnt(5.0, 40.0, 0.0).Transformed(ring_zero.transform_at(5.0, 40.0))
check("and the tail comes back into the plane it started in",
      near(ring_end.Z(), 0.0, 1e-6), ring_end.Z())
check("pointing the same way, shortened by the material the loop ate",
      near(ring_end.Y(), 40.0 - 2 * ring_gap, 1e-6),
      (ring_end.Y(), 40.0 - 2 * ring_gap))
ring_board = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, -T), 10.0, 40.0, T).Shape()
ring_solid = ring_zero.apply(ring_board)
_, _, rz0, _, _, rz1 = bbox(ring_solid)
# the loop's outer surface is the far side of the circle: 2R above the top
# face, plus the stack, and nothing hangs below the flat board
check("and the loop stands a diameter and a stack above the board",
      near(rz1, 2 * ring_r + T, 0.01) and near(rz0, -T, 1e-6), (rz0, rz1))
check("the ring keeps its material",
      abs(volume(ring_solid) - 10 * 40 * T) / (10 * 40 * T) < 0.01,
      (volume(ring_solid), 10 * 40 * T))

print("\n[7c1] a board drawn far from the origin still gets its bends")

# The cutter that takes a strip out of a shape was sized from the board but
# PLACED from the origin: half the board's diagonal either side of the point
# `n * lo`, which is the foot of the bend's near plane measured from (0, 0).
# A board sitting away from the origin then misses its own cutter. On Cadence's
# demo board BEND_1's foot is at (16.9, -17.2) and the arm it cuts is at
# (140, 90) - 163 mm along the bend line against a 102 mm half-span - so that
# bend was built out of nothing at all and the arm came out flat, with no
# warning: an empty cut looks exactly like a shape that is not in that region.
from stepbuilder.bend import _seam_gap

far_bend = Bend(name="F", start=(1035.6, 985.6), end=(1049.7, 999.5),
                angle=90.0, radius=R)
far_outline = [(1000, 950), (1060, 950), (1060, 1010), (1000, 1010)]
plan_far_origin = plan_fold([far_bend], far_outline, 0.0, -T, anchor=(1005.0, 955.0))
check("the bend is planned", len(plan_far_origin.bends) == 1,
      [b.name for b in plan_far_origin.bends])
far_board = BRepPrimAPI_MakeBox(gp_Pnt(1000, 950, -T), 60.0, 60.0, T).Shape()
far_folded = plan_far_origin.apply(far_board)
check("and the folded board keeps its material",
      abs(volume(far_folded) - 60 * 60 * T) / (60 * 60 * T) < 0.01,
      (volume(far_folded), 60 * 60 * T))
check("the fold actually happened - it is not still flat",
      bbox(far_folded)[5] - bbox(far_folded)[2] > T * 2,
      (bbox(far_folded)[2], bbox(far_folded)[5]))
check("and it joins up", _seam_gap(plan_far_origin) < 1e-6,
      _seam_gap(plan_far_origin))

print("\n[7c2] a rounded edge stays round through the cut")

# The pieces are cut FROM the outline, so whatever the outline is made of ends
# up as the edge of the board and is then carried onto the cylinder by the wrap.
# contour_points chords an arc into eight, which was accurate enough while its
# answers were only areas and containment tests; once the cut used it, those
# eight chords became 67 um of flat on a 14 mm corner - plainly visible on a
# rounded arm end. Cutting with the real curve costs nothing: _map_strip already
# turns a circular edge into an exact ellipse in the cylinder's parameter space.
from stepbuilder.bend import _cut_into_pieces
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_CurveType
from OCP.TopAbs import TopAbs_ShapeEnum as _TAS
from OCP.TopExp import TopExp_Explorer as _TEE
from OCP.TopoDS import TopoDS as _TDS

# a 40 x 20 bar with both ends rounded on r = 10, one bend across the middle
round_end = [
    {"type": "segment", "start": [10.0, 0.0], "end": [30.0, 0.0]},
    {"type": "arc", "center": [30.0, 10.0], "radius": 10.0,
     "alpha": 270.0, "beta": 90.0, "ccw": True},
    {"type": "segment", "start": [30.0, 20.0], "end": [10.0, 20.0]},
    {"type": "arc", "center": [10.0, 10.0], "radius": 10.0,
     "alpha": 90.0, "beta": 270.0, "ccw": True},
]
bar = contour_points(round_end)
across = Bend(name="X", start=(20.0, 0.0), end=(20.0, 20.0), angle=90.0, radius=R)
bar_chain = [(across, (1.0, 0.0), (20.0, 10.0), 2.0, 0.0, -T)]


def circles(face):
    n = 0
    walk = _TEE(face, _TAS.TopAbs_EDGE)
    while walk.More():
        if (BRepAdaptor_Curve(_TDS.Edge_s(walk.Current())).GetType()
                == GeomAbs_CurveType.GeomAbs_Circle):
            n += 1
        walk.Next()
    return n


chorded = _cut_into_pieces(bar, bar_chain, lambda m: None, None)
exact = _cut_into_pieces(bar, bar_chain, lambda m: None, round_end)
check("both readings cut the bar into the same pieces",
      len(chorded[0]) == len(exact[0]), (len(chorded[0]), len(exact[0])))
check("the chorded cut leaves no arc anywhere",
      sum(circles(f) for _, f in chorded[0]) == 0)
check("the exact cut keeps the rounded ends as circles",
      sum(circles(f) for _, f in exact[0]) >= 2,
      sum(circles(f) for _, f in exact[0]))
ea = abs(polygon_area(exact[0][0][0][0]))
ca = abs(polygon_area(chorded[0][0][0][0]))
check("and it is still the same board, to within the chord error",
      abs(ea - ca) < 0.02 * ca, (ea, ca))

# An outline whose curves will not close must fall back, not lose the board.
told = []
check("a contour that cannot be built falls back to the flat one",
      _cut_into_pieces(bar, bar_chain, told.append,
                       [{"type": "segment", "start": [0.0, 0.0],
                         "end": [1.0, 0.0]}]) is not None)

print("\n[7c3] a folded panel is not mistaken for the board's edge")

# _rim_faces asks "is this wall vertical" in the frame the face was BUILT in,
# because after a fold half the flat faces stand vertical. flat_frame finds that
# frame by trying each region's inverse - and a wrong region's inverse is a
# rotation about a different axis, which throws the point clean out of the
# stack. On Cadence's demo board the LCD panel's top face came back at z = 31.08
# through a slice of BEND_3, on a board 1.63 mm thick; judged in that frame it
# stood vertical, and all 2398 mm2 of it was painted with the board EDGE colour.
# So the un-folded point has to land back IN the board, and panels are tried
# before slices.
tall_two = [(0, 0), (10, 0), (10, 60), (0, 60)]
over = Bend(name="O", start=(0.0, 20.0), end=(10.0, 20.0), angle=180.0,
            radius=1.0, inner_side="top")
plan_over = plan_fold([over], tall_two, 0.0, -T, anchor=(5.0, 5.0))
check("the plan knows where the flat board's faces are",
      plan_over.flat_top == 0.0 and plan_over.flat_bottom == -T,
      (plan_over.flat_top, plan_over.flat_bottom))

folded_over = plan_over.apply(
    BRepPrimAPI_MakeBox(gp_Pnt(0, 0, -T), 10.0, 60.0, T).Shape())
rim = core._rim_faces(folded_over, plan_over)


def face_area(f):
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(f, props)
    return props.Mass()


flat_face = 10.0 * 60.0                     # the whole board, one side
biggest = max((face_area(f) for f in rim), default=0.0)
check("no rim face is anywhere near the size of a panel",
      biggest < 0.25 * flat_face, (biggest, flat_face))
check("but the board still has a rim at all", rim, len(rim))

# and the frame it hands back must be the panel's own, not a slice's
past = gp_Pnt(5.0, 40.0, 0.0).Transformed(plan_over.transform_at(5.0, 40.0))
back = plan_over.flat_frame(past)
check("a point past the bend unfolds back into the board", back is not None)
if back is not None:
    home = past.Transformed(back)
    check("and lands back inside the stack, not out in space",
          -T - 1.0 <= home.Z() <= 1.0, home.Z())

print("\n[7d] the fold joins up - every seam, every shape")

# The invariant that actually showed on Cadence's demo board, and the one
# nothing else here would have caught. Both edges of every strip have to land
# where the piece on that side puts them. Which side a piece is on was judged
# from its overall EXTENT, and the main board is wide enough to lie on both
# sides of a strip's infinite band, so BEND_1 was folded back to front: the
# strip's near edge was sewn to the far panel. The arm came away from the board
# by 23.8 mm and floated off on its own. Volume was still right, no region was
# claimed twice, and every other check still passed - a fold can be continuous
# or not, and only this asks.
from stepbuilder.bend import _seam_gap

for name, p in (("one bend", plan), ("a Z fold", plan2), ("two arms", plan_arms),
                ("a corner in one arm", plan_ell),
                ("arms at right angles", plan_cross),
                ("a ring", ring_zero)):
    check(f"the fold joins up: {name}", _seam_gap(p) < 1e-6, _seam_gap(p))

# And the shape that broke it: a big held piece reaching past a narrow arm's
# bend on both sides, so its extent says nothing about which side it is on.
wide_hold = [(0, 0), (120, 0), (120, 60), (70, 60), (70, 100), (55, 100),
             (55, 60), (0, 60)]
narrow = Bend(name="N", start=(55.0, 80.0), end=(70.0, 80.0), angle=180.0,
              radius=4.0)
plan_narrow = plan_fold([narrow], wide_hold, 0.0, -T, anchor=(5.0, 5.0))
check("a wide board with a narrow arm folds where it should",
      plan_narrow.region_at(5.0, 5.0) == "held", plan_narrow.region_at(5.0, 5.0))
check("and joins up", _seam_gap(plan_narrow) < 1e-6, _seam_gap(plan_narrow))

print("\n[8] where a component ends up")

held = plan.transform_at(5.0, 5.0)
moved = plan.transform_at(35.0, 5.0)
p_held = gp_Pnt(5.0, 5.0, 0.0).Transformed(held)
p_moved = gp_Pnt(35.0, 5.0, 0.0).Transformed(moved)
check("a part on the held panel does not move",
      near(p_held.X(), 5.0) and near(p_held.Z(), 0.0), (p_held.X(), p_held.Z()))
check("a part on the tail goes up with it, by how far along the tail it sits",
      near(p_moved.Z(), fold90(35.0, 0.0)[1], 1e-6),
      (p_moved.Z(), fold90(35.0, 0.0)[1]))
check("and it is still standing on the surface it was placed on",
      near(p_moved.X(), fold90(35.0, 0.0)[0], 1e-6),
      (p_moved.X(), fold90(35.0, 0.0)[0]))
check("a part standing in the bend area is reported",
      plan.in_bend_area(20.0, 5.0) == "B1")
check("one outside it is not", plan.in_bend_area(5.0, 5.0) is None)
check("the region names read sensibly",
      plan.region_at(5, 5) == "held" and "B1" in plan.region_at(20, 5),
      (plan.region_at(5, 5), plan.region_at(20, 5)))

# a folded point put back into the flat frame lands where it started
back = plan.flat_frame(gp_Pnt(p_moved.X(), p_moved.Y(), p_moved.Z()))
flat_again = p_moved.Transformed(back)
check("flat_frame is the exact inverse of the fold",
      near(flat_again.X(), 35.0, 1e-6) and near(flat_again.Z(), 0.0, 1e-6),
      (flat_again.X(), flat_again.Z()))

# --------------------------------------------------------------------------- #
print("\n[9] the radius is measured from the LOCAL stack, not the board")

# A stiffener zone 2.44 thick and a flex zone 0.365 thick, sharing a core, as
# on the real board. The bend is in the flex; if the fold took the board's own
# top face it would swing the tail through an arc 2 mm too high.
zones = [{"name": "STIFF", "stackup": "S", "contour": rect(0, 0, 20, 10)},
         {"name": "FLEX", "stackup": "F", "contour": rect(20, 0, 40, 10)}]
levels = {"STIFF": (0.0, -2.44), "FLEX": (-2.05, -2.415)}
data = {"pcb": {"edges": [rect(0, 0, 40, 10)]},
        "bends": [{"name": "B1", "line": {"start": [30.0, 0.0], "end": [30.0, 10.0]},
                   "inner_radius": 1.0, "info": "INNER_ANGLE=90, INNER_SIDE=TOP"}]}
plan_zone = plan_from_json(data, board_top_z=0.0, board_bottom_z=-2.44,
                           zones=zones, levels=levels)
check("the bend is read out of the JSON", len(plan_zone.bends) == 1)
flex_strip = BRepPrimAPI_MakeBox(gp_Pnt(20, 0, -2.415), 20.0, 10.0, 0.365).Shape()
_, _, _, _, _, ztop = bbox(plan_zone.apply(flex_strip))
# axis sits R above the FLEX top face (-2.05), not above the board top (0)
neutral_f = 1.0 + 0.365 / 2
dev_f = neutral_f * math.pi / 2
expected = (-2.05 + 1.0) + (40.0 - (30.0 + dev_f / 2))
check("the tail rises from the flex surface, 2.05 mm below the board top",
      near(ztop, expected, 5e-3), (ztop, expected))

no_zone = plan_from_json(data, board_top_z=0.0, board_bottom_z=-2.44)
_, _, _, _, _, ztop2 = bbox(no_zone.apply(flex_strip))
check("without zone data it falls back to the board faces, and differs",
      not near(ztop2, ztop, 0.5), (ztop2, ztop))

# --------------------------------------------------------------------------- #
print("\n[10] polygon helpers")

check("area of the outline", near(polygon_area(outline), 400.0))
check("a half-plane clip halves it",
      near(polygon_area(clip_halfplane(outline, 1.0, 0.0, 20.0)), 200.0),
      polygon_area(clip_halfplane(outline, 1.0, 0.0, 20.0)))
check("point in polygon", point_in_polygon((5, 5), outline)
      and not point_in_polygon((45, 5), outline))
pts = contour_points(rect(0, 0, 4, 3))
check("a JSON contour becomes a polygon of the same area",
      near(polygon_area(pts), 12.0), polygon_area(pts))
circle = contour_points([{"type": "circle", "x": 0, "y": 0, "radius": 5}], arc_steps=64)
check("a circle is sampled, not dropped",
      abs(polygon_area(circle) - math.pi * 25) < 0.5, polygon_area(circle))

print("\n[10a] what alpha, beta and ccw mean on an arc - settled by measurement")

# alpha..beta BOUND the arc; `ccw` says which END the contour enters it by, not
# which way the sweep goes. Read as a direction - which is what both halves used
# to do - a 90 degree corner becomes the 270 degree arc the long way round.
#
# Measured on Cadence's demo board: under this reading every contour in the file
# joins head to tail to 0.000 mm, the board outline included; under the old one
# the outline's joints were 5.657 mm apart, FLEXI's 19.799 and CONN_FLEXI's
# 12.728, and each affected arc came out at 270 degrees where the design draws
# 90. The zones then covered 94% of the board instead of all of it, and the flex
# arms had no material under three of the six bends.
CORNER = {"type": "arc", "center": [16.0, 16.0], "radius": 4.0,
          "alpha": 0.0, "beta": 90.0}
square_ccw = [                                    # anticlockwise, entered at alpha
    {"type": "segment", "start": [0.0, 0.0], "end": [20.0, 0.0]},
    {"type": "segment", "start": [20.0, 0.0], "end": [20.0, 16.0]},
    dict(CORNER, ccw=True),
    {"type": "segment", "start": [16.0, 20.0], "end": [0.0, 20.0]},
    {"type": "segment", "start": [0.0, 20.0], "end": [0.0, 0.0]},
]
square_cw = [                                     # the same shape, the other way
    {"type": "segment", "start": [0.0, 0.0], "end": [0.0, 20.0]},
    {"type": "segment", "start": [0.0, 20.0], "end": [16.0, 20.0]},
    dict(CORNER, ccw=False),                      # entered at BETA
    {"type": "segment", "start": [20.0, 16.0], "end": [20.0, 0.0]},
    {"type": "segment", "start": [20.0, 0.0], "end": [0.0, 0.0]},
]
rounded = 400.0 - (16.0 - math.pi * 16.0 / 4.0)   # square less the clipped corner


def joints(contour):
    """Worst gap between one primitive's end and the next one's start."""
    worst, prev, first = 0.0, None, None
    for p in contour:
        pts = contour_points([p], arc_steps=64)
        if not pts:
            continue
        if first is None:
            first = pts[0]
        if prev is not None:
            worst = max(worst, math.dist(prev, pts[0]))
        prev = pts[-1]
    return max(worst, math.dist(prev, first)) if prev else 0.0


for name, contour in (("entered at alpha", square_ccw), ("entered at beta", square_cw)):
    poly = contour_points(contour, arc_steps=64)
    check(f"{name}: the contour joins up", joints(contour) < 1e-9, joints(contour))
    check(f"{name}: and encloses the right area",
          abs(abs(polygon_area(poly)) - rounded) < 0.05,
          (abs(polygon_area(poly)), rounded))

# ...and the OCC side has to agree with the polygon side, or the board body and
# every containment test are two different boards.
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepGProp import BRepGProp as _BRepGProp
from OCP.GProp import GProp_GProps as _GProp

for name, contour in (("entered at alpha", square_ccw), ("entered at beta", square_cw)):
    face = BRepBuilderAPI_MakeFace(core.build_contour(contour, 0.0), True)
    props = _GProp()
    _BRepGProp.SurfaceProperties_s(face.Face(), props)
    check(f"{name}: the wire OCC builds encloses the same area",
          abs(props.Mass() - rounded) < 0.05, (props.Mass(), rounded))

# --------------------------------------------------------------------------- #
print("\n[11] end to end, through generate()")

demo = json.loads((ROOT / "demo/ap-214/demo.json").read_text())
demo["format"] = "simple3d"
demo["format_version"] = 7
# fold the right-hand 40 mm of the 160 x 80 board up through 90 degrees, and
# put a second capacitor out on the tail so a component has to travel with it
demo["C2"] = dict(demo["C1"], x=140.0, y=38.0)
demo["bends"] = [{
    "name": "BEND1",
    "line": {"start": [120.0, 0.0], "end": [120.0, 80.0]},
    "inner_radius": 1.0,
    "width": None,
    "info": "TYPE=CircularBend, INNER_SIDE=TOP, INNER_ANGLE=90.0000, "
            "INNER_RADIUS=1.0000 MILLIMETERS, ORDER=0",
}]
jf = OUT / "folded.json"
jf.write_text(json.dumps(demo))

from OCP.STEPControl import STEPControl_Reader


def build(name, **kw):
    logs = []
    core.generate(step_dir=ROOT / "demo/step_files", json_file=jf, output_dir=OUT,
                  output_name=name, minimize_size=False, log=logs.append, **kw)
    reader = STEPControl_Reader()
    reader.ReadFile(str(OUT / f"{name}.step"))
    reader.TransferRoots()
    return reader.OneShape(), logs


shape, logs = build("folded")
x0, y0, z0, x1, y1, z1 = bbox(shape)
# 160 x 80 board, 1.096 thick, bent up at x=120 with a 1 mm inner radius
dev_demo = (1.0 + 1.096 / 2) * math.pi / 2
demo_tail = 160.0 - (120.0 + dev_demo / 2)
check("the fold is announced", any("Folding 1 bend" in m for m in logs), logs[:5])
check("the tail stands up its own length",
      near(z1, 1.0 + demo_tail, 1e-3), (z1, 1.0 + demo_tail))
check("nothing is left out at the flat board's far end - the component that "
      "was there has moved with the tail", x1 < 130.0, x1)
check("the held end is untouched", near(x0, 0.0, 1e-3), x0)

# ...and it moved to the right place. The capacitor sits at x=140 on the tail,
# so it should now be standing off the INSIDE face of the fold, one tail-length
# up, pointing back over the board.
from OCP.TopAbs import TopAbs_ShapeEnum
from OCP.TopExp import TopExp_Explorer

centres = []
exp = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_SOLID)
while exp.More():
    bx = bbox(exp.Current())
    centres.append(((bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2, (bx[2] + bx[5]) / 2))
    exp.Next()
arc_start_demo = 120.0 - dev_demo / 2
cap_z = 1.0 + (140.0 - (120.0 + dev_demo / 2))       # how far along the tail
cap_x = arc_start_demo + 1.0 - 5.0                   # 10 mm tall, off the face
check("the capacitor on the tail is where the fold puts it",
      any(abs(c[0] - cap_x) < 0.6 and abs(c[1] - 38.0) < 0.6
          and abs(c[2] - cap_z) < 0.6 for c in centres),
      (centres, (cap_x, 38.0, cap_z)))
check("the capacitor on the held part has not moved",
      any(abs(c[0] - 78.5) < 0.6 and abs(c[2] - 5.0) < 0.6 for c in centres),
      centres)

flat_shape, flat_logs = build("flat", fold_bends=False)
_, _, _, fx1, _, fz1 = bbox(flat_shape)
check("switched off, the board is flat and full length",
      near(fx1, 160.0, 1e-3) and fz1 < 10.5, (fx1, fz1))
check("and it says so rather than doing it silently",
      any("exported flat" in m for m in flat_logs), flat_logs[:5])

folded_v = volume(shape)
flat_v = volume(flat_shape)
check("folding neither loses nor invents material",
      abs(folded_v - flat_v) / flat_v < 0.01, (folded_v, flat_v))

# --------------------------------------------------------------------------- #
print("\n[11b] a feature INSIDE the bend area survives the fold")

# Round 44, from the user's flex2-a0: the outline runs straight past BEND_1 and
# then curves outward INSIDE the bend area, reaching 0.0252 mm beyond the
# straight part by the far edge of the strip. That is 0.04% of the strip's
# volume - under PRISM_TOLERANCE - so the prism test, which compared volumes
# only, called the strip straight, revolved one cross-section through the whole
# arc and dropped the curve. The board came out with a 25 micron ledge along the
# edge of the flex exactly where the bend ended, and that is what was reported.
#
# The same thing in miniature here, and deliberately well under the old
# tolerance: a 0.5 x 0.03 mm ear on the far edge, wholly inside the bend area,
# 0.008% of the strip's volume. The fold turns about an axis parallel to y, so
# the ear's y is untouched by it: material past y = 80 exists in the result if
# and only if the ear survived. It must, whichever construction builds the bend.
eared = json.loads((ROOT / "demo/ap-214/demo.json").read_text())
eared["format"] = "simple3d"
eared["format_version"] = 7
eared["pcb"]["edges"] = [[
    {"type": "segment", "start": [0.0, 0.0], "end": [160.0, 0.0]},
    {"type": "segment", "start": [160.0, 0.0], "end": [160.0, 80.0]},
    {"type": "segment", "start": [160.0, 80.0], "end": [121.0, 80.0]},
    {"type": "segment", "start": [121.0, 80.0], "end": [121.0, 80.03]},
    {"type": "segment", "start": [121.0, 80.03], "end": [120.5, 80.03]},
    {"type": "segment", "start": [120.5, 80.03], "end": [120.5, 80.0]},
    {"type": "segment", "start": [120.5, 80.0], "end": [0.0, 80.0]},
    {"type": "segment", "start": [0.0, 80.0], "end": [0.0, 0.0]},
]]
eared["bends"] = demo["bends"]
ear_file = OUT / "eared.json"
ear_file.write_text(json.dumps(eared))

# the bend area with k = 0.5 is x in [118.784, 121.216] - the ear is inside it
check("the ear really is inside the bend area",
      120.0 - dev_demo / 2 < 120.5 and 121.0 < 120.0 + dev_demo / 2,
      (120.0 - dev_demo / 2, 120.0 + dev_demo / 2))

ear_logs = []
core.generate(step_dir=ROOT / "demo/step_files", json_file=ear_file, output_dir=OUT,
              output_name="eared", minimize_size=False, log=ear_logs.append)
ear_reader = STEPControl_Reader()
ear_reader.ReadFile(str(OUT / "eared.step"))
ear_reader.TransferRoots()
ear_shape = ear_reader.OneShape()

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common

# Cut at 80.005 rather than at 80: a boolean against a plane coincident with the
# solid's own face is the one that comes back empty on one board in twenty.
past_edge = BRepPrimAPI_MakeBox(gp_Pnt(100.0, 80.005, -60.0),
                                gp_Pnt(160.0, 81.0, 60.0)).Shape()
cut = BRepAlgoAPI_Common(ear_shape, past_edge)
cut.Build()
ear_volume = volume(cut.Shape()) if cut.IsDone() else 0.0
# the fold preserves volume, so the ear keeps 0.5 x 0.025 x 1.096 above the cut
check("the ear inside the bend is still there after folding",
      ear_volume > 0.005, f"{ear_volume:.6f} mm3 past y=80.005")
check("and it is the whole ear, not a remnant",
      near(ear_volume, 0.5 * 0.025 * 1.096, 0.002),
      (ear_volume, 0.5 * 0.025 * 1.096))

# --------------------------------------------------------------------------- #
print("\n[12] a board with no bends is left exactly as it was")

plain = json.loads((ROOT / "demo/ap-214/demo.json").read_text())
pf = OUT / "plain.json"
pf.write_text(json.dumps(plain))


def plain_volume(name, fold):
    core.generate(step_dir=ROOT / "demo/step_files", json_file=pf, output_dir=OUT,
                  output_name=name, minimize_size=False, fold_bends=fold,
                  log=lambda m: None)
    reader = STEPControl_Reader()
    reader.ReadFile(str(OUT / f"{name}.step"))
    reader.TransferRoots()
    return volume(reader.OneShape())


on = plain_volume("plain_on", True)
off = plain_volume("plain_off", False)
check("identical with folding on and off", near(on, off, 1e-9), (on, off))

# --------------------------------------------------------------------------- #
print("\n[13] the rim of a folded board is still its rim")

# A 90 degree fold turns the top face of the tail into a vertical plane. Judged
# by orientation alone it would be painted as rim, which is most of the board
# in the wrong color.
def area(faces):
    total = 0.0
    for face in faces:
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        total += props.Mass()
    return total


folded_once = plan.apply(strip)
rim_flat = core._rim_faces(strip)
rim_folded = core._rim_faces(folded_once, plan)
rim_naive = core._rim_faces(folded_once)
check("a flat strip has four rim faces", len(rim_flat) == 4, len(rim_flat))
# Still four, as flat. The two long walls run parallel to the bend axis, so
# they stay in their own planes through the fold and the unify pass merges each
# back into one face across the held panel, the bend and the tail. The bend's
# inner and outer surfaces are cylinders and must NOT be counted - they are the
# board's faces wrapped round, not its edge.
check("the folded one keeps the same four rim faces",
      len(rim_folded) == 4, len(rim_folded))
# The rim of this strip is its perimeter times its thickness: 2*(40+10)*0.4 = 40,
# and bending it does not change that - an annular sector about a neutral axis
# at mid-thickness has exactly the area of the flat strip it came from.
check("and the same rim AREA, now exactly",
      abs(area(rim_folded) - 40.0) / 40.0 < 0.001,
      (area(rim_folded), area(rim_flat)))
check("judged by orientation alone it would grab the tail's flat faces - "
      "several times the area, and the wrong colour on most of the board",
      area(rim_naive) > 5 * area(rim_folded), (area(rim_naive), area(rim_folded)))

# --------------------------------------------------------------------------- #
print("\n[14] all three body stitchings fold the same way")

# A rigid-flex board of the shape the real one has: a 2.44 mm stiffener zone and
# a 0.365 mm flex zone sharing a conductor core, with the bend across the flex.
# The layer-colored mode is the interesting one - it colors the faces the fuse
# hands back, so folding has to happen BEFORE the fuse or the colors land on
# faces that no longer exist.
def stack(spec):
    idx = [i for i, (_, t, _) in enumerate(spec) if t == "CONDUCTOR"][0]
    above = sum(t for i, (_, _, t) in enumerate(spec) if i < idx)
    out, cum = [], 0.0
    for name, kind, thk in spec:
        top = above - cum
        out.append({"name": name, "type": kind, "thickness": thk,
                    "z_top": top, "z_bottom": top - thk, "shapes": None})
        cum += thk
    return out


FLEX = [("COVERLAY_TOP", "MASK", 0.025), ("ADHESIVE_TOP", "MASK", 0.05),
        ("TOP", "CONDUCTOR", 0.045), ("DIEL", "DIELECTRIC", 0.125),
        ("BOTTOM", "CONDUCTOR", 0.045), ("ADHESIVE_BOTTOM", "MASK", 0.05),
        ("COVERLAY_BOTTOM", "MASK", 0.025)]
STIFF = [("STIFFENER_TOP2", "MASK", 2.0), ("ADHESIVE_TOP2", "MASK", 0.025),
         ("SOLDERMASK_TOP", "MASK", 0.025), ("TOP", "CONDUCTOR", 0.045),
         ("DIEL", "DIELECTRIC", 0.125), ("BOTTOM", "CONDUCTOR", 0.045),
         ("SOLDERMASK_BOTTOM", "MASK", 0.025), ("COVERLAY_BOTTOM", "MASK", 0.025)]

rf = {"format": "simple3d", "format_version": 7, "name": "rigidflex",
      "pcb": {"thickness": {"soldermask_top": 0.0, "board": 0.365,
                            "soldermask_bottom": 0.0},
              "color": demo["pcb"]["color"], "edges": [rect(0, 0, 41, 26.5)]},
      "stackups": {"FLEX": {"thickness": 0.365, "layers": stack(FLEX)},
                   "STIFFENER2": {"thickness": 2.44, "layers": stack(STIFF)}},
      "zones": [{"name": "S2", "stackup": "STIFFENER2", "contour": rect(0, 0, 16, 11.38)},
                {"name": "F2", "stackup": "FLEX", "contour": rect(0, 11.38, 41, 26.5)}],
      "bends": [{"name": "B1", "line": {"start": [0.0, 20.0], "end": [41.0, 20.0]},
                 "inner_radius": 0.5, "width": None,
                 "info": "TYPE=CircularBend, INNER_SIDE=TOP, INNER_ANGLE=90.0000, "
                         "INNER_RADIUS=0.5000 MILLIMETERS, ORDER=0"}]}
rfj = OUT / "rigidflex.json"
rfj.write_text(json.dumps(rf))

heights, volumes = {}, {}
for mode in ("solid", "layers", "inspect"):
    logs = []
    core.generate(step_dir=ROOT / "demo/step_files", json_file=rfj, output_dir=OUT,
                  output_name=f"rf_{mode}", minimize_size=False, board_mode=mode,
                  log=logs.append)
    reader = STEPControl_Reader()
    reader.ReadFile(str(OUT / f"rf_{mode}.step"))
    reader.TransferRoots()
    shape = reader.OneShape()
    heights[mode] = bbox(shape)[5]
    volumes[mode] = volume(shape)
    check(f"{mode}: the fold is applied", any("Folding 1 bend" in m for m in logs),
          logs[:6])
    if mode == "layers":
        check("layers: the faces are still colored per layer kind",
              any("face(s) colored by layer kind" in m for m in logs), logs)

# Datum "top" puts the stiffener's own top face at 0, so the shared core top is
# 2.05 below it and the FLEX surface is the 0.075 of coverlay and adhesive above
# that core. The cylinder axis is the inner radius above the flex surface, and
# the tail past the bend area is 6.5 mm less half the developed width.
dev_rf = (0.5 + 0.365 / 2) * math.pi / 2
flex_top = -2.05 + 0.025 + 0.05
top_rf = (flex_top + 0.5) + (26.5 - (20.0 + dev_rf / 2))
for mode in heights:
    check(f"{mode}: the tail reaches the height the bend puts it at",
          near(heights[mode], top_rf, 5e-3), (heights[mode], top_rf))
check("the three modes agree on the fold to a micron",
      max(heights.values()) - min(heights.values()) < 1e-3, heights)
# With the bend built exactly there are no slice overlaps to double-count, so
# even the unfused build weighs the same as the others - and the same as the
# flat board, which is the strongest statement the fold can make about itself.
check("all three stitchings weigh exactly the same",
      max(volumes.values()) - min(volumes.values()) < 1e-6, volumes)

# --------------------------------------------------------------------------- #
print("\n[15] the SKILL emission, transliterated")

# s3dBendsJson cannot run here, so it is transliterated line for line and its
# output required to be JSON that this module reads back. That is how the
# round-34 layer filter and the round-28 escaper were checked, and it is the
# only thing standing between a typo in the emitter and a broken export.


def skill_json_quote(value):
    """s3dJsonQuote: quote, backslash, tab, newline; null for a non-string."""
    if not isinstance(value, str):
        return "null"
    out = '"'
    for c in value:
        out += {'"': '\\"', "\\": "\\\\", "\t": "\\t", "\n": "\\n"}.get(c, c)
    return out + '"'


def skill_span_across(points, a, b):
    """s3dSpanAcross: how wide a shape is measured across the line a-b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length <= 0.0:
        return None
    nx, ny = dy / length, -dx / length
    lo = hi = None
    for p in points:
        w = nx * (p[0] - a[0]) + ny * (p[1] - a[1])
        lo = w if lo is None or w < lo else lo
        hi = w if hi is None or w > hi else hi
    return hi - lo if lo is not None else None


def skill_bends_json(records):
    """s3dBendsJson, for records of (name, ends, radius, width, info)."""
    if not records:
        return '"bends": []'
    out = '"bends": [\n'
    first = True
    for name, ends, radius, width, info in records:
        if not ends:                       # no readable bend line: skipped
            continue
        body = (
            "{\n"
            '\t"name": ' + skill_json_quote(name) + ",\n"
            '\t"line": { "start": [' + f"{ends[0][0]:f}" + ", " + f"{ends[0][1]:f}"
            + '], "end": [' + f"{ends[1][0]:f}" + ", " + f"{ends[1][1]:f}" + "] },\n"
            # `if( radius then ... else "null" )`: in SKILL only nil is false,
            # so a zero radius - a sharp crease - emits 0.000000, not null.
            '\t"inner_radius": ' + (f"{radius:f}" if radius is not None else "null") + ",\n"
            '\t"width": ' + (f"{width:f}" if width is not None else "null") + ",\n"
            '\t"info": ' + skill_json_quote(info) + "\n"
            "}"
        )
        if not first:
            out += ",\n"
        first = False
        out += "\n".join("\t" + line for line in body.split("\n"))
    return out + "\n]"


# a bend area 4 mm across a diagonal bend line, to prove the width is measured
# perpendicular to the line and not in x or y
diag_a, diag_b = (0.0, 0.0), (10.0, 10.0)
half = 4.0 / 2 / math.sqrt(2)
area_pts = [(-half, half), (10 - half, 10 + half), (10 + half, 10 - half), (half, -half)]
check("the bend area is measured across the line, diagonal or not",
      near(skill_span_across(area_pts, diag_a, diag_b), 4.0, 1e-9),
      skill_span_across(area_pts, diag_a, diag_b))
check("a zero-length bend line measures nothing rather than dividing by it",
      skill_span_across(area_pts, diag_a, diag_a) is None)

emitted = skill_bends_json([
    ("BEND1", ((10.0, 0.0), (10.0, 20.0)), 2.5, 4.5, REAL),
    ('B"2', ((30.0, 0.0), (30.0, 20.0)), None, None, None),
    ("NOLINE", None, 1.0, 1.0, REAL),
])
parsed = json.loads("{" + emitted + "}")
check("two bends emitted, the one with no line dropped",
      len(parsed["bends"]) == 2, parsed)
check("a quote in a bend name does not break the file",
      parsed["bends"][1]["name"] == 'B"2', parsed["bends"][1]["name"])
check("a missing radius and width come out as null, not as nothing",
      parsed["bends"][1]["inner_radius"] is None
      and parsed["bends"][1]["width"] is None, parsed["bends"][1])
check("a missing property comes out as null", parsed["bends"][1]["info"] is None)
round_trip = bend_from_dict(parsed["bends"][0])
check("and the reader gets the same bend back out",
      round_trip is not None and near(round_trip.angle, 28.26)
      and near(round_trip.radius, 2.5) and near(round_trip.width, 4.5)
      and round_trip.midpoint == (10.0, 10.0), round_trip)
check("no bends at all is still valid JSON",
      json.loads("{" + skill_bends_json([]) + "}")["bends"] == [])
check("every bend unreadable is still valid JSON",
      json.loads("{" + skill_bends_json([("X", None, 1.0, 1.0, "")]) + "}")["bends"] == [])

# --------------------------------------------------------------------------- #
print("\n[16] the real board's own bends")

# Straight out of probe_bend.il on flex-b2, 2026-07-26. Both bends 28.26 deg
# with a 2.5 mm inner radius, one folding up and one down, both crossing the
# 0.365 mm flex.
REAL_INFO = ("TYPE=CircularBend, INNER_SIDE=%s, INNER_ANGLE=28.2600, "
             "INNER_RADIUS=2.5000 MILLIMETERS, ORDER=0, CREATE_VKO=1, "
             "VKO_OSIZE=0.0000 MILLIMETERS, CREATE_PKO=1, "
             "PKO_OSIZE=0.2490 MILLIMETERS")
b_real = bend_from_dict({
    "name": "BEND_2", "line": {"start": [0.0, 11.88], "end": [16.0, 11.88]},
    "inner_radius": 2.5, "width": 12.4969 - 11.2632,
    "info": REAL_INFO % "TOP"})
check("the whole property parses, keepout fields and all",
      b_real is not None and near(b_real.angle, 28.26) and near(b_real.radius, 2.5)
      and b_real.inner_side == "top" and b_real.order == 0, b_real)
check("the keepout fields are kept, not dropped",
      parse_bend_info(REAL_INFO % "TOP")["PKO_OSIZE"] == "0.2490 MILLIMETERS")
down_real = bend_from_dict({
    "name": "BEND_1", "line": {"start": [25.0, 23.6], "end": [41.0, 23.6]},
    "inner_radius": 2.5, "width": 24.2167 - 22.9832, "info": REAL_INFO % "BOTTOM"})
check("the two bends on the board go opposite ways",
      down_real.inner_side == "bottom" and b_real.inner_side == "top")

# The bend area Allegro drew is 1.2337 across; angle x INNER radius is 1.2331,
# angle x neutral radius (2.5 + 0.365/2) is 1.3232. The first match is what
# says the drawn area is not a bend allowance.
theta_real = math.radians(28.26)
# 0.0006 apart, which is the rounding of the four-decimal coordinates the area
# was measured from and of the angle itself. The other candidate is 0.09 out.
check("the drawn bend area IS the inner arc, to within its own rounding",
      abs(b_real.width - 2.5 * theta_real) < 1e-3,
      (b_real.width, 2.5 * theta_real))
check("and it is NOT the neutral-axis length, which is what gets folded",
      abs(b_real.width - (2.5 + 0.365 / 2) * theta_real) > 0.08,
      (b_real.width, (2.5 + 0.365 / 2) * theta_real))

real_plan = plan_fold([b_real], [(0, 0), (16, 0), (16, 32), (0, 32)],
                      board_top_z=0.0, board_bottom_z=-0.365)
check("a bend area that is the inner arc raises no note",
      not any("bend area is" in n for n in real_plan.notes), real_plan.notes)
half_real = real_plan.chain[0][3]
check("the strip folded is the neutral-axis length, not the drawn one",
      near(2 * half_real, (2.5 + 0.365 / 2) * theta_real, 1e-9), 2 * half_real)

odd = bend_from_dict({"name": "ODD", "line": {"start": [0.0, 11.88], "end": [16.0, 11.88]},
                      "inner_radius": 2.5, "width": 4.0, "info": REAL_INFO % "TOP"})
odd_plan = plan_fold([odd], [(0, 0), (16, 0), (16, 32), (0, 32)], 0.0, -0.365)
check("a bend area that is neither raises one",
      any("bend area is" in n for n in odd_plan.notes), odd_plan.notes)
check("and it still folds the neutral-axis length",
      near(2 * odd_plan.chain[0][3], 2 * half_real, 1e-9))

# --------------------------------------------------------------------------- #
print("\n[17] a straight strip is bent as a true cylinder, not faceted")

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_SurfaceType


def surfaces(shape):
    kinds = {}
    exp = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE)
    while exp.More():
        kind = BRepAdaptor_Surface(TopoDS.Face_s(exp.Current())).GetType()
        kinds[kind] = kinds.get(kind, 0) + 1
        exp.Next()
    return kinds


from OCP.TopoDS import TopoDS

# a fresh plan: how a bend was built is reported once per plan, and this one
# has already been folded twice above
fresh = plan_fold([bend], outline, board_top_z=0.0, board_bottom_z=-T)
logs = []
exact = fresh.apply(strip, log=logs.append)
kinds = surfaces(exact)
cylinders = kinds.get(GeomAbs_SurfaceType.GeomAbs_Cylinder, 0)
check("the bend is made of cylindrical faces", cylinders >= 2, kinds)
check("and it says so once", any("true cylindrical" in m for m in logs), logs)
check("the exact bend is far lighter than the faceted one",
      sum(kinds.values()) < 20, sum(kinds.values()))
check("volume is preserved better than by the facets - no slice overlap at all",
      abs(volume(exact) - flat_volume) / flat_volume < 1e-6,
      (volume(exact), flat_volume))
check("the tail still lands exactly where the fold puts it",
      near(bbox(exact)[5], fold90(40.0, 0.0)[1], 1e-6), bbox(exact)[5])
check("and the outside of the bend is now exact, not a chord overshoot",
      near(bbox(exact)[3], fold90(40.0, -T)[0], 1e-6),
      (bbox(exact)[3], fold90(40.0, -T)[0]))

print("\n[17b] an outline that is not straight is WRAPPED onto the cylinder")

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.gp import gp_Ax2, gp_Vec  # noqa: E402 (kept beside the shapes they build)

# A relief notch at the end of the bend line - which is exactly what a real flex
# board has, and what the revolve above cannot take: the strip is a different
# shape at every point across the bend.
notch = BRepPrimAPI_MakeCylinder(
    gp_Ax2(gp_Pnt(20.0, 0.0, -1.0), gp_Dir(0, 0, 1)), 0.5, 2.0).Shape()
notched = BRepAlgoAPI_Cut(
    BRepPrimAPI_MakeBox(gp_Pnt(0, 0, -T), 40.0, 10.0, T).Shape(), notch).Shape()
check("the notch really is cut out of the test strip",
      volume(notched) < flat_volume - 0.1, (volume(notched), flat_volume))

logs = []
folded_notch = plan_fold([bend], outline, 0.0, -T).apply(notched, log=logs.append)
check("the revolve refuses it and the outline is wrapped instead",
      any("wrapped onto" in m for m in logs), logs)
check("it is built on true cylinders all the same",
      surfaces(folded_notch).get(GeomAbs_SurfaceType.GeomAbs_Cylinder, 0) >= 2,
      surfaces(folded_notch))
# This strip is symmetric about the bend's neutral axis, so the wrap neither
# stretches nor compresses it on balance and its volume does not change.
check("and it weighs what it did flat, to a millionth",
      abs(volume(folded_notch) - volume(notched)) / volume(notched) < 1e-6,
      (volume(folded_notch), volume(notched)))
check("the notch is still missing from it - it was not filled in",
      volume(folded_notch) < volume(exact) - 0.1,
      (volume(folded_notch), volume(exact)))

# a hole THROUGH the bend area: a design rule forbids it and a board
# occasionally has one anyway
hole = BRepPrimAPI_MakeCylinder(
    gp_Ax2(gp_Pnt(20.0, 5.0, -1.0), gp_Dir(0, 0, 1)), 0.3, 2.0).Shape()
holed = BRepAlgoAPI_Cut(
    BRepPrimAPI_MakeBox(gp_Pnt(0, 0, -T), 40.0, 10.0, T).Shape(), hole).Shape()
folded_hole = plan_fold([bend], outline, 0.0, -T).apply(holed)
check("a hole inside the bend area comes through the wrap too",
      abs(volume(folded_hole) - volume(holed)) / volume(holed) < 1e-6,
      (volume(folded_hole), volume(holed)))
check("and it is still a hole", volume(folded_hole) < volume(exact) - 0.1,
      volume(folded_hole))

print("\n[17c] the wrap is isometric - the material stretches and compresses")

# A thin layer ABOVE the neutral axis is compressed by the bend: its volume comes
# out multiplied by its own radius over the neutral one. That is the physics the
# construction has to get right, and the reason a per-layer check cannot simply
# ask for the flat volume back - asking for it rejected every layer of the real
# board except the one at the core.
thin = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, -0.05), 40.0, 10.0, 0.05).Shape()
thin_folded = plan_fold([bend], outline, 0.0, -T).apply(thin)
# only the STRIP is bent; the two flat panels keep every cubic millimetre
ratio = abs(z_axis - (-0.025)) / (R + T / 2)
in_bend = developed * 10.0 * 0.05
want = volume(thin) - in_bend + in_bend * ratio
check("a layer above the neutral axis loses volume, by exactly r/rho",
      abs(volume(thin_folded) - want) / volume(thin) < 1e-5,
      (volume(thin_folded), want, ratio))

print("\n[17d] a piece that is not a prism still falls back to facets")

# Slanted cut: no longer the extrusion of its own top face, so neither
# construction applies and the slices take over.
wedge_face = BRepBuilderAPI_MakeFace(
    BRepBuilderAPI_MakePolygon(
        gp_Pnt(19.0, -1.0, 0.05), gp_Pnt(22.0, -1.0, -0.5),
        gp_Pnt(22.0, 12.0, -0.5), gp_Pnt(19.0, 12.0, 0.05), True).Wire(),
    True).Face()
wedge = BRepAlgoAPI_Cut(
    BRepPrimAPI_MakeBox(gp_Pnt(0, 0, -T), 40.0, 10.0, T).Shape(),
    BRepPrimAPI_MakePrism(wedge_face, gp_Vec(0, 0, 1.0)).Shape()).Shape()
logs = []
folded_wedge = plan_fold([bend], outline, 0.0, -T).apply(wedge, log=logs.append)
check("a slanted cut sends the bend back to the facets",
      any("faceted" in m for m in logs), logs)
check("and the message says which step refused",
      any("prism" in m for m in logs), logs)
check("it still folds and keeps its material",
      abs(volume(folded_wedge) - volume(wedge)) / volume(wedge) < 0.01,
      (volume(folded_wedge), volume(wedge)))

print("\n[17e] an outline whose corners only MEET to a tolerance still wraps")

# A solid that came out of a boolean does not have its edges meeting exactly.
# Each edge's own curve stops where its own geometry says, the shared vertex
# sits between the two ends, and its tolerance is what makes the shape legal -
# a few tenths of a micron on the real board, which is perfectly ordinary.
#
# The wrap rebuilds every edge from its own 2D curve, so those same few tenths
# of a micron reappear between the new edges. BRepBuilderAPI_MakeWire joins
# edges at Precision::Confusion, a hard 1e-7, and when the gap is wider it does
# not fail: it quietly drops edges and reports IsDone. That left two walls of a
# four-walled strip unsewn, the shell open, the solid "not valid", and every
# bend near the stiffener on the real board faceted for no visible reason.
#
# So: the same 40 x 10 strip, cut to a five-sided outline that the revolve
# cannot take, with one corner deliberately loose by 4e-7 - twice what OCC will
# join by itself, and well inside the tolerance the vertex is given.
from OCP.BRep import BRep_Builder                            # noqa: E402
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
from OCP.BRepCheck import BRepCheck_Analyzer                 # noqa: E402
from OCP.Geom import Geom_Line                               # noqa: E402
from OCP.TopoDS import TopoDS_Vertex                         # noqa: E402
from OCP.gp import gp_Vec as _gp_Vec                         # noqa: E402

LOOSE = 4.0e-7
inside = [(arc_start + 0.01, 0.5), (arc_end - 0.01, 0.5),
          (arc_end - 0.01, 8.0), (arc_start + 1.0, 9.5),
          (arc_start + 0.01, 9.5)]
# every corner is one vertex shared by its two edges; corner 2 is the loose one,
# where the two curves stop 4e-7 apart and the vertex sits between them
builder = BRep_Builder()
corners = []
for i, (cx, cy) in enumerate(inside):
    corner = TopoDS_Vertex()
    builder.MakeVertex(corner, gp_Pnt(cx, cy, 0.0), 1.0e-6)
    corners.append(corner)

loose_edges = []
for i in range(len(inside)):
    head, tail = inside[i], inside[(i + 1) % len(inside)]
    a = gp_Pnt(head[0], head[1], 0.0)
    b = gp_Pnt(tail[0], tail[1], 0.0)
    if i == 2:                       # this curve stops SHORT of its vertex
        a = gp_Pnt(head[0] - LOOSE, head[1], 0.0)
    if i == 1:                       # and this one overshoots it
        b = gp_Pnt(tail[0] + LOOSE, tail[1], 0.0)
    direction = gp_Vec(a, b)
    line = Geom_Line(a, gp_Dir(direction.X(), direction.Y(), direction.Z()))
    made = BRepBuilderAPI_MakeEdge(line, corners[i], corners[(i + 1) % len(inside)],
                                   0.0, direction.Magnitude())
    check(f"the loose-cornered outline builds edge {i}", made.IsDone())
    loose_edges.append(made.Edge())

loose_wire = BRepBuilderAPI_MakeWire()
for edge in loose_edges:
    loose_wire.Add(edge)
loose_face = BRepBuilderAPI_MakeFace(loose_wire.Wire(), True).Face()
loose = BRepPrimAPI_MakePrism(loose_face, _gp_Vec(0, 0, -T)).Shape()
check("and the flat solid it makes is valid - the tolerance covers the gap",
      BRepCheck_Analyzer(loose).IsValid())

logs = []
folded_loose = plan_fold([bend], outline, 0.0, -T).apply(loose, log=logs.append)
check("a loose corner does not send the bend back to the facets",
      not any("faceted" in m for m in logs), logs)
check("it is wrapped onto true cylinders like any other outline",
      any("wrapped onto" in m for m in logs)
      and surfaces(folded_loose).get(GeomAbs_SurfaceType.GeomAbs_Cylinder, 0) >= 2,
      (logs, surfaces(folded_loose)))
check("the wrapped solid is closed and valid",
      BRepCheck_Analyzer(folded_loose).IsValid())
# The piece lies wholly inside the bend area and is symmetric about the neutral
# axis, so the wrap neither stretches nor compresses it on balance.
check("and it weighs what it did flat",
      abs(volume(folded_loose) - volume(loose)) / volume(loose) < 1e-5,
      (volume(folded_loose), volume(loose)))

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)
