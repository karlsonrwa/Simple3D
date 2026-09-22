# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import (ROOT, out_dir, fails, check, rect, read_step, count_solids,
                      exporter_source, bbox, free_edges)

"""The copper pads (round 85): which face a pin reaches, what its figure
looks like, where it lands - against the pad polygons Allegro itself reports
- and the build that places them.

[1]-[3] are pure functions over dicts and faces. [4] is the oracle: a sample
of Cadence's demo board (tests/fixtures/pads_demo.json) with, for each pin,
the bounding box of the polygon axlPolyFromDB(pin ?layer "ETCH/TOP" /
"ETCH/BOTTOM") returned in Allegro 25.1 - the side rule and the mirror /
rotation convention are pinned to that, not to a reading of the docs. [5]
builds a board with the option on and off.
"""
import json
import math
import sys

from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from stepbuilder import core
from stepbuilder import pads as P
from stepbuilder.stackup import align_stackups

OUT = out_dir("pads")


def area(face) -> float:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    return props.Mass()


def circle(r, cx=0.0, cy=0.0):
    return [{"type": "circle", "x": cx, "y": cy, "radius": r}]


def inside(shape, x, y) -> bool:
    """Is the flat point on the copper of *shape* (a face, or the first face
    of a compound) - the question an area cannot answer, because a hole in
    the wrong place has the same area as a hole in the right one."""
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.TopAbs import TopAbs_State
    from OCP.gp import gp_Pnt
    face = P._first_face(shape)
    return BRepClass_FaceClassifier(face, gp_Pnt(x, y, 0.0), 1e-7).State() == TopAbs_State.TopAbs_IN


def pad(outline, bbox, figure="RECTANGLE", offset=(0.0, 0.0), inside=0.0):
    return {"figure": figure, "bbox": bbox, "offset": list(offset), "inside": inside, "outline": outline}


RECT = pad(rect(-1.0, -0.5, 1.0, 0.5), [[-1.0, -0.5], [1.0, 0.5]])
DISC = pad(circle(0.8), [[-0.8, -0.8], [0.8, 0.8]], "CIRCLE")

print("\n[1] which outer face a pin reaches, with which pad, through which opening")
# A surface padstack: one etch pad, placed where the span says - "ETCH/TOP"
# in the padstack is "the side the part sits on", not the layer called TOP.
# Its opening is its one mask pad, wherever the library drew it.
MASK = pad(rect(-1.1, -0.6, 1.1, 0.6), [[-1.1, -0.6], [1.1, 0.6]])
smd = {"usage": "Smd", "drill": None, "pads": {"ETCH/TOP": RECT, "PIN/SOLDERMASK_TOP": MASK}}
check("a surface pin on TOP: the top face, its pad, its opening",
      P.pin_sides({"mirrored": False, "start": "ETCH/TOP", "end": "ETCH/TOP"}, smd, "TOP", "BOTTOM")
      == [("top", RECT, MASK)])
check("a surface pin whose span says BOTTOM: the bottom face, same pad, same opening",
      P.pin_sides({"mirrored": True, "start": "ETCH/BOTTOM", "end": "ETCH/BOTTOM"}, smd, "TOP", "BOTTOM")
      == [("bottom", RECT, MASK)])
check("a surface pin on INNER1 in a zone whose top copper IS INNER1: the top face",
      P.pin_sides({"mirrored": False, "start": "ETCH/INNER1", "end": "ETCH/INNER1"}, smd, "INNER1", "INNER2")
      == [("top", RECT, MASK)])
check("a surface pin on INNER1 in the rigid zone: no outer face at all",
      P.pin_sides({"mirrored": False, "start": "ETCH/INNER1", "end": "ETCH/INNER1"}, smd, "TOP", "BOTTOM")
      == [])
check("no span: the mirror flag decides",
      P.pin_sides({"mirrored": True, "start": None, "end": None}, smd, "TOP", "BOTTOM") == [("bottom", RECT, MASK)]
      and P.pin_sides({"mirrored": False, "start": None, "end": None}, smd, "TOP", "BOTTOM") == [("top", RECT, MASK)])
bare = {"usage": "Smd", "drill": None, "pads": {"ETCH/TOP": RECT}}
check("a surface padstack with no mask pad: the face and the pad, and None for the opening",
      P.pin_sides({"mirrored": False, "start": "ETCH/TOP", "end": "ETCH/TOP"}, bare, "TOP", "BOTTOM")
      == [("top", RECT, None)])
MASKB = pad(rect(-1.2, -0.7, 1.2, 0.7), [[-1.2, -0.7], [1.2, 0.7]])
both = {"usage": "Smd", "drill": None,
        "pads": {"ETCH/TOP": RECT, "PIN/SOLDERMASK_TOP": MASK, "PIN/SOLDERMASK_BOTTOM": MASKB}}
check("a surface padstack with masks on both sides takes the one on its pad's side",
      P.pin_sides({"mirrored": True, "start": "ETCH/BOTTOM", "end": "ETCH/BOTTOM"}, both, "TOP", "BOTTOM")
      == [("bottom", RECT, MASK)])

# A through padstack: pads by layer name; mirrored, the stack is read backwards
# - openings included.
TOPPAD, BOTPAD = dict(RECT, tag="t"), dict(DISC, tag="b")
TOPMASK, BOTMASK = dict(MASK, tag="mt"), dict(MASK, tag="mb")
thru = {"usage": "Through", "drill": circle(0.4),
        "pads": {"ETCH/TOP": TOPPAD, "ETCH/INNER1": DISC, "ETCH/BOTTOM": BOTPAD,
                 "PIN/SOLDERMASK_TOP": TOPMASK, "PIN/SOLDERMASK_BOTTOM": BOTMASK}}
check("a through pin: both faces, each with its own layer's pad and opening",
      P.pin_sides({"mirrored": False, "start": "ETCH/TOP", "end": "ETCH/BOTTOM"}, thru, "TOP", "BOTTOM")
      == [("top", TOPPAD, TOPMASK), ("bottom", BOTPAD, BOTMASK)])
check("mirrored: the pad drawn for TOP lands on the bottom face, its opening with it",
      P.pin_sides({"mirrored": True, "start": "ETCH/TOP", "end": "ETCH/BOTTOM"}, thru, "TOP", "BOTTOM")
      == [("top", BOTPAD, BOTMASK), ("bottom", TOPPAD, TOPMASK)])
check("a through pin spanning the flex core only: nothing on the rigid faces",
      P.pin_sides({"mirrored": False, "start": "ETCH/INNER1", "end": "ETCH/INNER2"}, thru, "TOP", "BOTTOM")
      == [])
onemask = {"usage": "Through", "drill": circle(0.4),
           "pads": {"ETCH/TOP": TOPPAD, "ETCH/BOTTOM": BOTPAD, "PIN/SOLDERMASK_TOP": TOPMASK}}
check("a through padstack opened on one side only: the other face is covered (None)",
      P.pin_sides({"mirrored": False, "start": "ETCH/TOP", "end": "ETCH/BOTTOM"}, onemask, "TOP", "BOTTOM")
      == [("top", TOPPAD, TOPMASK), ("bottom", BOTPAD, None)])
check("a padstack with no etch pad reaches nothing",
      P.pin_sides({"mirrored": False, "start": "ETCH/TOP", "end": "ETCH/TOP"},
                  {"usage": "Smd", "drill": None, "pads": {"PIN/SOLDERMASK_TOP": RECT}}, "TOP", "BOTTOM") == [])
check("has_mask_data tells a v11 library from a v10 one",
      P.has_mask_data({"A": smd, "B": bare}) and not P.has_mask_data({"B": bare}))
check("outer conductors by position, not by name",
      P.outer_conductors({"layers": [{"name": "COVERLAY", "type": "MASK"}, {"name": "INNER1", "type": "CONDUCTOR"},
                                     {"name": "", "type": "DIELECTRIC"}, {"name": "INNER2", "type": "PLANE"}]})
      == ("INNER1", "INNER2"))

print("\n[2] one figure as a face: the outline, the donut, the drill, the mirror")
face, note = P.pad_face(RECT, None, False, True)
check("a rectangle: 2 x 1", face is not None and abs(area(face) - 2.0) < 1e-9, note or (face and area(face)))
face, note = P.pad_face(DISC, None, False, True)
check("a circle (one closing arc in the export) is a disc", face is not None
      and abs(area(face) - math.pi * 0.64) < 1e-6, note or (face and area(face)))
donut = pad(circle(1.0), [[-1, -1], [1, 1]], "DONUT", inside=1.0)
face, note = P.pad_face(donut, None, False, True)
check("a donut's inside diameter is a hole", face is not None
      and abs(area(face) - math.pi * (1.0 - 0.25)) < 1e-6, note or (face and area(face)))
# A donut standing at an offset. The outline (the ring's outer circle) already
# stands at the offset and the declared box is the figure's own about its
# centre - the rule measured on the Dell board below - so the hole belongs at
# the OUTLINE's centre. It was built at the box's, the whole offset away from
# its ring, and the area was right all the same (review of 2026-09-17).
shifted = pad(circle(1.0, 0.2, 0.0), [[-1.0, -1.0], [1.0, 1.0]], "DONUT", offset=(0.2, 0.0), inside=0.6)
face, note = P.pad_face(shifted, None, False, True)
check("a donut at an offset keeps its ring's area", face is not None and note is None
      and abs(area(face) - math.pi * (1.0 - 0.09)) < 1e-6, (note, face and area(face)))
check("and its hole is at the ring's centre, not at the declared box's",
      face is not None and not inside(face, 0.2, 0.0) and not inside(face, 0.45, 0.0)
      and inside(face, -0.2, 0.0) and inside(face, 0.9, 0.0),
      face and [inside(face, x, 0.0) for x in (0.2, 0.45, -0.2, 0.9)])
face, note = P.pad_face(DISC, circle(0.4), False, True)
check("a through pad keeps its drill hole (annular ring)", face is not None
      and abs(area(face) - math.pi * (0.64 - 0.16)) < 1e-6, note or (face and area(face)))
face, note = P.pad_face(pad(circle(0.3), [[-0.3, -0.3], [0.3, 0.3]], "CIRCLE"), circle(1.5), False, True)
check("a pad smaller than its drill is nothing, quietly", face is None and note is None, (face, note))
face, note = P.pad_face(pad(circle(0.5, 0.2, 0.0), [[-0.3, -0.5], [0.7, 0.5]], "CIRCLE"), circle(0.4), False, True)
check("a drill off the pad's centre still cuts (a boolean, not a hole wire)",
      face is not None and area(face) < math.pi * 0.25 - 1e-6, note or (face and area(face)))
# The offset, as the Dell board's fifteen offset padstacks have it: the
# declared box is the figure's own, about its centre, and the outline already
# stands at the offset. Checked from the three facts rather than assumed.
inplace = pad(rect(0, 0, 2, 1), [[-1, -0.5], [1, 0.5]], offset=(1.0, 0.5))
face, note = P.pad_face(inplace, None, False, True)
check("an outline standing at the offset of its figure-centred box is in place",
      face is not None and note is None and P._boxes_agree(P._tight_box(face), (0.0, 0.0, 2.0, 1.0)),
      (note, face and P._tight_box(face)))
centred = pad(rect(-1, -0.5, 1, 0.5), [[-1, -0.5], [1, 0.5]], offset=(1.0, 0.5))
face, note = P.pad_face(centred, None, False, True)
check("an outline that is the figure-centred box itself is moved by the offset",
      face is not None and note is None and P._boxes_agree(P._tight_box(face), (0.0, 0.0, 2.0, 1.0)),
      (note, face and P._tight_box(face)))
odd = pad(rect(0, 0, 2, 1), [[3, 3], [5, 4]], offset=(0.5, 0.5))
face, note = P.pad_face(odd, None, False, True)
check("one that matches neither is used as it is and says so",
      face is not None and note is not None and "neither the declared box" in note, note)
rounded = pad(rect(-47.06, -44.0, 47.05, 44.0), [[-47.06, -44.0], [47.06, 44.0]])
face, note = P.pad_face(rounded, None, False, True)
check("a hundredth of a mil of rounding (a board laid out in mils) is not a disagreement",
      face is not None and note is None, note)

# A ROUNDED_RECTANGLE exactly as my_test_board2 exports it: the corner arcs'
# centres are rounded to the design's resolution, so from one end the radius
# is 0.19985 and to the other 0.1999, and an arc rebuilt on the first misses
# the next line by 0.05 um - four open wires, and the pad was not drawn. The
# ends are exact; the arc is built through them.
def arc(cx, cy, r, alpha, beta):
    return {"type": "arc", "center": [cx, cy], "radius": r, "alpha": alpha, "beta": beta, "ccw": True}


def seg(x0, y0, x1, y1):
    return {"type": "segment", "start": [x0, y0], "end": [x1, y1]}


R130 = pad([seg(0.4501, 0.4, -0.4501, 0.4),
            arc(-0.4501, 0.20015, 0.19985, 90.0, 180.014331),
            seg(-0.65, 0.2001, -0.65, -0.2001),
            arc(-0.4501, -0.20015, 0.1999, 179.985669, 270.0),
            seg(-0.4501, -0.4, 0.4501, -0.4),
            arc(0.4501, -0.20015, 0.19985, 270.0, 0.014331),
            seg(0.65, -0.2001, 0.65, 0.2001),
            arc(0.4501, 0.20015, 0.1999, 359.985669, 90.0)],
           [[-0.65, -0.4001], [0.65, 0.4]], "ROUNDED_RECTANGLE")
# A wire that does not close RAISES out of pad_face rather than returning a
# note, and an uncaught raise here costs every check below it - the suite dies
# with a traceback instead of one FAIL line (measured 2026-09-22: breaking the
# end-to-end join took the whole suite out that way).
try:
    face, note = P.pad_face(R130, None, False, True)
except Exception as exc:
    face, note = None, f"{exc.__class__.__name__}: {exc}"
expected = 1.3 * 0.8 - (4 - math.pi) * 0.2 * 0.2
check("a rounded rectangle whose arc centres are rounded still closes, through its end points",
      face is not None and abs(area(face) - expected) < 2e-4, (note, face and area(face), expected))
# and the same figure with EXACT arcs builds to the same area, so the join
# rule changes nothing where nothing needs joining
R130x = pad([seg(0.45, 0.4, -0.45, 0.4), arc(-0.45, 0.2, 0.2, 90.0, 180.0),
             seg(-0.65, 0.2, -0.65, -0.2), arc(-0.45, -0.2, 0.2, 180.0, 270.0),
             seg(-0.45, -0.4, 0.45, -0.4), arc(0.45, -0.2, 0.2, 270.0, 360.0),
             seg(0.65, -0.2, 0.65, 0.2), arc(0.45, 0.2, 0.2, 0.0, 90.0)],
            [[-0.65, -0.4], [0.65, 0.4]], "ROUNDED_RECTANGLE")
face, note = P.pad_face(R130x, None, False, True)
check("an exact rounded rectangle: the same area to the micron",
      face is not None and abs(area(face) - expected) < 1e-9, (note, face and area(face)))
# a clockwise arc is entered from its beta end - the join has to follow travel
CW = pad([seg(0.0, 0.0, 1.0, 0.0),
          {"type": "arc", "center": [1.0, 0.5], "radius": 0.5, "alpha": 270.0, "beta": 90.0, "ccw": False},
          seg(1.0, 1.0, 0.0, 1.0), seg(0.0, 1.0, 0.0, 0.0)],
         [[0.0, 0.0], [1.5, 1.0]])
face, note = P.pad_face(CW, None, False, True)
check("a clockwise arc in the chain joins by travel, not by alpha",
      face is not None and abs(area(face) - (1.0 + math.pi * 0.125)) < 1e-9, (note, face and area(face)))
asym = pad(rect(0.0, -0.5, 2.0, 0.5), [[0.0, -0.5], [2.0, 0.5]])
face, _ = P.pad_face(asym, None, True, True)
check("mirrored: x -> -x", face is not None and P._boxes_agree(P._tight_box(face), (-2.0, -0.5, 0.0, 0.5)),
      face and P._tight_box(face))
check("top faces look up, bottom faces look down",
      P._normal_up(P.pad_face(RECT, None, False, True)[0]) is True
      and P._normal_up(P.pad_face(RECT, None, False, False)[0]) is False
      and P._normal_up(P.pad_face(RECT, None, True, True)[0]) is True
      and P._normal_up(P.pad_face(RECT, None, True, False)[0]) is False)
face, note = P.pad_face({"figure": "FLASH", "bbox": [[-1, -1], [1, 1]], "offset": [0, 0], "inside": 0, "outline": None},
                        None, False, True)
check("no outline: the bounding box stands in", face is not None and abs(area(face) - 4.0) < 1e-9, note)

print("\n[2b] the mask opening: what shows is copper AND opening")
# Per figure, one boolean: a solder-mask-defined pad shows the opening, a
# copper-defined one its own copper, and a covered pad is the caller's
# business (mask None in pin_sides) - pad_face with mask=None clips nothing.
small = pad(rect(-0.8, -0.4, 0.8, 0.4), [[-0.8, -0.4], [0.8, 0.4]])
face, note = P.pad_face(RECT, None, False, True, mask=small)
check("an opening smaller than the copper: the opening's area (mask-defined)",
      face is not None and abs(P.shape_area(face) - 1.28) < 1e-9, (note, face and P.shape_area(face)))
face, note = P.pad_face(RECT, None, False, True, mask=MASK)
check("an opening larger than the copper: the copper's area (copper-defined)",
      face is not None and abs(P.shape_area(face) - 2.0) < 1e-9, (note, face and P.shape_area(face)))
face, note = P.pad_face(RECT, None, False, True, mask=RECT)
check("an opening equal to the copper: the same area", face is not None and abs(P.shape_area(face) - 2.0) < 1e-9, note)
face, note = P.pad_face(DISC, circle(0.4), False, True, mask=pad(circle(0.6), [[-0.6, -0.6], [0.6, 0.6]], "CIRCLE"))
check("a through pad in a smaller round opening keeps its hole: a thinner ring",
      face is not None and abs(P.shape_area(face) - math.pi * (0.36 - 0.16)) < 1e-6, (note, face and P.shape_area(face)))
away = pad(rect(5, 5, 6, 6), [[5, 5], [6, 6]])
face, note = P.pad_face(RECT, None, False, True, mask=away)
check("an opening that misses the copper: nothing, quietly", face is None and note is None, (face, note))
half = pad(rect(0.0, -1.0, 1.0, 1.0), [[0.0, -1.0], [1.0, 1.0]])
face, note = P.pad_face(RECT, None, True, True, mask=half)
check("clipped, then mirrored: the visible half ends up on the mirrored side",
      face is not None and P._boxes_agree(P._tight_box(face), (-1.0, -0.5, 0.0, 0.5)), face and P._tight_box(face))
two = pad(rect(-1.0, -0.5, 1.0, 0.5), [[-1.0, -0.5], [1.0, 0.5]])
face, note = P.pad_face(two, circle(0.5), False, True, mask=RECT)
check("a slot-like drill wider than the pad cuts it in two: a compound of two faces, both kept",
      face is not None and abs(P.shape_area(face) - (2.0 - math.pi * 0.25)) < 1e-6 and len(P._faces_of(face)) == 2,
      (note, face and P.shape_area(face), face and len(P._faces_of(face))))

print("\n[3] placement: rotate about the pin, then move, then the fold")
face, _ = P.pad_face(asym, None, False, True)
placed = BRepBuilderAPI_Transform(face, P._placement(10.0, 20.0, 0.5, 90.0, None), True).Shape()
check("a 2x1 pad along +x turned 90 degrees stands along +y at the pin",
      P._boxes_agree(P._tight_box(placed), (9.5, 20.0, 10.5, 22.0)), P._tight_box(placed))


class _Fold:
    def transform_at(self, x, y):
        from OCP.gp import gp_Trsf, gp_Vec
        t = gp_Trsf()
        t.SetTranslation(gp_Vec(0, 0, 100.0))
        return t

    def in_bend_area(self, x, y):
        return None


placed = BRepBuilderAPI_Transform(face, P._placement(10.0, 20.0, 0.5, 0.0, _Fold()), True).Shape()
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
box = Bnd_Box()
BRepBndLib.AddOptimal_s(placed, box, False, False)
check("the fold's transform is applied last", abs(box.CornerMin().Z() - 100.5) < 1e-9, box.CornerMin().Z())


class _Bend:
    """A fold that is NOT a pure translation.

    _Fold above translates along z, and a z translation commutes with both
    factors of a pad's own placement - the move to the pin and the rotation
    about z - so `fold.transform_at(x, y) * trsf` and `trsf *
    fold.transform_at(x, y)` give the same shape and the check above cannot
    fail (measured 2026-09-22). A real bend stands a panel UP, which does not
    commute: 90 degrees about the x axis through the origin here.
    """

    def transform_at(self, x, y):
        from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf
        t = gp_Trsf()
        t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)), math.pi / 2.0)
        return t

    def in_bend_area(self, x, y):
        return None


# By hand: the 2 x 1 pad lies x 0..2, y -0.5..0.5 at z 0; the move puts it at
# x 10..12, y 19.5..20.5, z 0.5; then (x, y, z) -> (x, -z, y) stands it up at
# x 10..12, y -0.5, z 19.5..20.5. Applied the other way round it would end up
# at x 10..12, y 20, z 0..1 - the same pad, twenty millimetres away.
stood = BRepBuilderAPI_Transform(face, P._placement(10.0, 20.0, 0.5, 0.0, _Bend()), True).Shape()
box = Bnd_Box()
BRepBndLib.AddOptimal_s(stood, box, False, False)
stood_box = (box.CornerMin().X(), box.CornerMin().Y(), box.CornerMin().Z(),
             box.CornerMax().X(), box.CornerMax().Y(), box.CornerMax().Z())
check("a fold that stands the panel up is applied to the PLACED pad, not to the "
      "figure at the origin",
      all(abs(a - b) < 1e-9 for a, b in
          zip(stood_box, (10.0, -0.5, 19.5, 12.0, -0.5, 20.5))),
      tuple(round(v, 6) for v in stood_box))

print("\n[4] against Allegro: the pad polygon it reports for each pin of the demo sample")
fx = json.loads((ROOT / "tests/fixtures/pads_demo.json").read_text(encoding="utf-8"))
stackups = align_stackups(fx["stackups"], lambda m: None)
levels = {str(z["name"]): (0.0, 0.0) for z in fx["zones"]}
where = P._Zones(fx["zones"], stackups, levels, 0.0, 0.0)
lib = fx["padstacks"]
sides_ok = boxes_ok = flex = 0
bad = []
for entry in fx["pins"]:
    row, oracle = entry["row"], entry["oracle"]
    x, y, rot, mir, name = float(row[0]), float(row[1]), float(row[2]), bool(row[3]), row[4]
    (top, bottom), _ = where.at(x, y)
    sides = P.pin_sides({"mirrored": mir, "start": row[5], "end": row[6]}, lib[name], top, bottom)
    if "INNER" in str(row[5]):
        # the flex: the probe asked only ETCH/TOP and ETCH/BOTTOM, so the
        # oracle is empty there and what is pinned is the zone's answer
        flex += 1
        if top != "INNER1" or {s for s, _, _ in sides} != ({"top"} if row[5] == row[6] else {"top", "bottom"}):
            bad.append(f"{name} span {row[5]}..{row[6]}: zone {top}/{bottom}, sides {sorted(s for s, _, _ in sides)}")
        continue
    if {s for s, _, _ in sides} != set(oracle):
        bad.append(f"{name} mir={mir} span {row[5]}..{row[6]}: sides {sorted(s for s, _, _ in sides)} vs Allegro {sorted(oracle)}")
        continue
    sides_ok += 1
    for side, pd, _mask in sides:
        face, _ = P.pad_face(pd, None, mir, side == "top")
        placed = BRepBuilderAPI_Transform(face, P._placement(x, y, 0.0, rot, None), True).Shape()
        got = P._tight_box(placed)
        if all(abs(a - b) < 2e-3 for a, b in zip(got, oracle[side])):
            boxes_ok += 1
        else:
            bad.append(f"{name} {side} rot={rot} mir={mir}: {tuple(round(v, 4) for v in got)} vs {tuple(round(v, 4) for v in oracle[side])}")
check(f"every sampled pin lands on the face(s) Allegro draws it on ({sides_ok} rigid, {flex} flex)",
      not bad and sides_ok + flex == len(fx["pins"]), bad[:4])
check(f"and its box is Allegro's box, mirrored and turned pins included ({boxes_ok} pads)",
      boxes_ok >= sides_ok and not bad, bad[:4])
check("the sample covers a mirrored pin, a turned one, a through one and a SHAPE",
      any(bool(e["row"][3]) for e in fx["pins"]) and any(float(e["row"][2]) in (90.0, 270.0) for e in fx["pins"])
      and any(lib[e["row"][4]]["drill"] for e in fx["pins"])
      and any(p["figure"] == "SHAPE" for s in lib.values() for p in s["pads"].values()))

print("\n[5] the build: the option on and off, and an older file")
base = json.loads((ROOT / "demo/ap-214/demo.json").read_text())
board = {"format": "simple3d", "format_version": 10, "name": "padboard",
         "pcb": {"thickness": {"soldermask_top": 0.025, "board": 1.054, "soldermask_bottom": 0.025},
                 "color": base["pcb"]["color"], "edges": [rect(0, 0, 20, 10), circle(0.4, 5, 5)]},
         "stackups": {"Primary": {"thickness": 1.104, "layers": [
             {"name": "SOLDERMASK_TOP", "type": "MASK", "thickness": 0.025, "z_top": 0.025, "z_bottom": 0.0, "shapes": None},
             {"name": "TOP", "type": "CONDUCTOR", "thickness": 0.045, "z_top": 0.0, "z_bottom": -0.045, "shapes": None},
             {"name": "", "type": "DIELECTRIC", "thickness": 0.964, "z_top": -0.045, "z_bottom": -1.009, "shapes": None},
             {"name": "BOTTOM", "type": "CONDUCTOR", "thickness": 0.045, "z_top": -1.009, "z_bottom": -1.054, "shapes": None},
             {"name": "SOLDERMASK_BOTTOM", "type": "MASK", "thickness": 0.025, "z_top": -1.054, "z_bottom": -1.079, "shapes": None}]}},
         "zones": [], "components": {},
         "pads": {"padstacks": {"SMD": smd, "THRU": thru, "BARE": bare,
                                # an untented via: a mask pad on top only; a tented one: none
                                "VIA": {"usage": "Via", "drill": circle(0.15),
                                        "pads": {"ETCH/TOP": DISC, "ETCH/BOTTOM": DISC, "PIN/SOLDERMASK_TOP": MASK}},
                                "TENTED": {"usage": "Via", "drill": circle(0.15),
                                           "pads": {"ETCH/TOP": DISC, "ETCH/BOTTOM": DISC}}},
                  "pins": [[2.0, 2.0, 0.0, False, "SMD", "ETCH/TOP", "ETCH/TOP"],
                           [2.0, 8.0, 90.0, True, "SMD", "ETCH/BOTTOM", "ETCH/BOTTOM"],
                           [5.0, 5.0, 0.0, False, "THRU", "ETCH/TOP", "ETCH/BOTTOM"],
                           [15.0, 5.0, 0.0, False, "NOSUCH", "ETCH/TOP", "ETCH/TOP"],
                           [12.0, 2.0, 0.0, False, "BARE", "ETCH/TOP", "ETCH/TOP"],
                           [17.0, 8.0, 0.0, False, "VIA", "ETCH/TOP", "ETCH/BOTTOM", "via"],
                           [17.0, 2.0, 0.0, False, "TENTED", "ETCH/TOP", "ETCH/BOTTOM", "via"]],
                  # the copper under a drawn opening, as the exporter writes it:
                  # a 3 x 2 rectangle at (8, 8), Allegro's own area beside it
                  "exposed": {"top": [{"layer": "PACKAGE GEOMETRY/SOLDERMASK_TOP", "area": 6.0,
                                       "vertices": [[8, 8, 0], [11, 8, 0], [11, 10, 0], [8, 10, 0]]}],
                              "bottom": []},
                  # and the laminate an opening shows where no copper is: a
                  # part number cut into the mask, on the bottom here
                  "bare": {"top": [],
                           "bottom": [{"layer": "BOARD GEOMETRY/SOLDERMASK_BOTTOM", "area": 1.0,
                                       "vertices": [[3, 3, 0], [4, 3, 0], [4, 4, 0], [3, 4, 0]]}]}}}
jf = OUT / "padboard.json"
jf.write_text(json.dumps(board))


def build(name, **kw):
    logs = []
    res = core.generate(step_dir=ROOT / "demo/step_files", json_file=jf, output_dir=OUT,
                        output_name=name, log=logs.append, **kw)
    return res, logs, (OUT / f"{name}.step").read_text(errors="replace")


res, logs, text = build("pads_on", exposed_copper=True)
check("five pad faces placed: two surface pins, a through pin on both faces, the untented via on top",
      res.pads_placed == 5 and res.pads_figures == 5, (res.pads_placed, res.pads_figures))
check("the via is a pin with no symbol: the log counts it, and the tented one draws nothing",
      "pad_VIA_TOP" in text and "pad_TENTED" not in text
      and any("2 via(s), 1 untented" in m for m in logs), [m for m in logs if "via" in m])
check("the copper under the drawn opening is one part per side, copper-coloured, named",
      "copper_top_pads_on" in text and "copper_bot_pads_on" not in text
      and any("Exposed copper under drawn openings, top: 1 polygon(s)" in m for m in logs),
      [m for m in logs if "xposed" in m])
check("its area is checked against Allegro's like the legend's",
      any("copper_top: 1 polygon(s) match Allegro's areas" in m for m in logs), [m for m in logs if "copper_top" in m])
check("the bare laminate in an opening belongs to the mask openings, not to the copper: none here",
      "bare_bot_pads_on" not in text and "bare_top_pads_on" not in text
      and not any("Bare laminate" in m for m in logs), [m for m in logs if "Bare" in m])
check("the pin whose padstack has no mask opening is under the mask: not drawn, and said",
      "pad_BARE" not in text and any("4 pad(s) have no mask opening" in m for m in logs),
      [m for m in logs if "mask" in m])
check("no v10 note on a v11 library", not any("carries no mask openings" in m for m in logs))

# A format_version 10 library - no mask pad anywhere - cannot say which pads
# are covered: the copper is drawn whole, as before, and the log says so once.
v10 = json.loads(json.dumps(board))
for ps in v10["pads"]["padstacks"].values():
    ps["pads"] = {l: p for l, p in ps["pads"].items() if "SOLDERMASK" not in l}
jf.write_text(json.dumps(v10))
res10, logs10, text10 = build("pads_v10", exposed_copper=True)
check("a v10 library draws every pad whole, the bare one and both vias included",
      res10.pads_placed == 9 and "pad_BARE" in text10 and "pad_TENTED" in text10,
      (res10.pads_placed, [m for m in logs10 if "pads" in m]))
check("and says that the openings are not in the file",
      any("carries no mask openings" in m for m in logs10), logs10[-6:])

# A format_version 11 file has the openings but not the copper under the
# drawn ones: built as before, and the log says what a re-export would add.
v11 = json.loads(json.dumps(board))
del v11["pads"]["exposed"]
jf.write_text(json.dumps(v11))
res11, logs11, text11 = build("pads_v11", exposed_copper=True)
check("a v11 file: the pads as before, no exposed copper, and a note",
      res11.pads_placed == 5 and "copper_top" not in text11
      and any("carries no copper under drawn mask openings" in m for m in logs11), logs11[-5:])
jf.write_text(json.dumps(board))
check("the pin with an unknown padstack is counted, not fatal", res.pads_skipped == 1
      and any("name a padstack" in m for m in logs), (res.pads_skipped, [m for m in logs if "padstack" in m]))
check("pads_top and pads_bot are nodes of the assembly, named per board",
      "pads_top_pads_on" in text and "pads_bot_pads_on" in text)
check("the figures are parts named after the padstack and layer",
      "pad_SMD_TOP" in text and "pad_SMD_TOPm" in text and "pad_THRU_TOP" in text and "pad_THRU_BOTTOM" in text)
check("the board is still one solid - no boolean touched it", count_solids(read_step(OUT / "pads_on.step")) == 1)
check("the log says what was placed", any("Copper pads: 5 placed" in m for m in logs), logs[-6:])

res2, logs2, text2 = build("pads_off", exposed_copper=False)
check("off: nothing placed, nothing in the file, nothing said",
      res2.pads_placed == 0 and "pads_top" not in text2
      and not any("Copper pads" in m or "No pads" in m for m in logs2),
      [m for m in logs2 if "pads" in m])

# Instanced, not copied: a second pin on the same figure costs a placement,
# not a face. Measured on the demo board's 2906 placements of 83 figures.
more = json.loads(json.dumps(board))
more["pads"]["pins"] += [[x + 0.0, y + 1.0] + rest for x, y, *rest in board["pads"]["pins"]]
jf.write_text(json.dumps(more))
res_more, _, _ = build("pads_more", exposed_copper=True)
size_on = (OUT / "pads_on.step").stat().st_size
size_more = (OUT / "pads_more.step").stat().st_size
per_placement = (size_more - size_on) / max(res_more.pads_placed - res.pads_placed, 1)
check(f"twice the pins, the same figures: {res_more.pads_figures} figures still",
      res_more.pads_placed == 10 and res_more.pads_figures == 5, (res_more.pads_placed, res_more.pads_figures))
check(f"and each extra placement costs under 1.5 kB ({per_placement:.0f} bytes)", 0 < per_placement < 1500)

print("\n[6] the mask openings: on their own, with the copper, and on a file without them")
# The figure first: a window is the mask figure whole; with the copper it
# is what the copper leaves - the mask's area less the copper the opening
# exposes - and a drill takes its hole out of it like it does of the pad.
whole_area = P.shape_area(P.figure_face(MASK)[0])
window, wnote = P.opening_face(MASK, None, False)
ring, rnote = P.opening_face(MASK, None, False, copper=DISC)
shown = P.shape_area(P.pad_face(DISC, None, False, mask=MASK)[0])
holed, hnote = P.opening_face(MASK, circle(0.15), False)
check("an opening on its own is the mask figure whole",
      window is not None and wnote is None and abs(P.shape_area(window) - whole_area) < 1e-6,
      (wnote, P.shape_area(window), whole_area))
check("with the copper it is the mask less what the copper shows through it",
      ring is not None and rnote is None and abs(P.shape_area(ring) - (whole_area - shown)) < 1e-6,
      (rnote, P.shape_area(ring), whole_area, shown))
check("a copper that fills its opening leaves nothing, and says nothing",
      P.opening_face(DISC, None, False, copper=DISC) == (None, None))
check("the drill is cut out of the opening as it is out of the pad",
      holed is not None and hnote is None and P.shape_area(holed) < whole_area, (hnote,))

jf.write_text(json.dumps(board))
res_o, logs_o, text_o = build("openings_on", exposed_copper=False, mask_openings=True)
check("openings alone: a window per pin and via with a mask pad, no copper anywhere",
      res_o.pads_placed == 0 and "pads_top_openings_on" not in text_o and "copper_top_openings_on" not in text_o
      and "openings_top_openings_on" in text_o and "openings_bot_openings_on" in text_o
      and res_o.openings_placed == 5 and res_o.opening_figures == 5,
      (res_o.pads_placed, res_o.openings_placed, res_o.opening_figures))
check("the figures are parts named after the padstack and the mask layer, a mirrored one with m",
      "opening_SMD_SOLDERMASK_TOP" in text_o and "opening_SMD_SOLDERMASK_TOPm" in text_o
      and "opening_THRU_SOLDERMASK_" in text_o and "opening_VIA_SOLDERMASK_TOP" in text_o
      and "opening_TENTED" not in text_o and "opening_BARE" not in text_o)
check("the drawn openings come whole, as laminate, on both sides",
      "bare_top_openings_on" in text_o and "bare_bot_openings_on" in text_o
      and any("Drawn openings, whole, top: 1 polygon(s)" in m for m in logs_o)
      and any("Drawn openings, whole, bottom: 1 polygon(s)" in m for m in logs_o),
      [m for m in logs_o if "Drawn" in m])
check("the log says what was placed, in the dielectric's colour",
      any("Mask openings: 5 placed" in m and "RGB 252,255,214" in m for m in logs_o)
      and not any("Copper pads:" in m for m in logs_o), [m for m in logs_o if "openings" in m])

res_b, logs_b, text_b = build("both_on", exposed_copper=True, mask_openings=True)
check("both on: the pads as before, the windows beside them, the laminate under the drawn openings",
      res_b.pads_placed == 5 and res_b.pads_figures == 5
      and "pads_top_both_on" in text_b and "openings_top_both_on" in text_b
      and "copper_top_both_on" in text_b and "bare_bot_both_on" in text_b
      and any("Bare laminate in drawn openings, bottom: 1 polygon(s)" in m for m in logs_b)
      and any("Exposed copper under drawn openings, top: 1 polygon(s)" in m for m in logs_b)
      and not any("Drawn openings, whole" in m for m in logs_b),
      (res_b.pads_placed, res_b.openings_placed, [m for m in logs_b if "opening" in m]))
# A window the copper fills - a padstack whose opening IS its copper - is
# counted, not placed. None of the board's figures fills its window (0.64 to
# 0.92 mm2 of ring is left in each), so the count is asked on a board with
# one that does: the same pins plus one such pad.
filled = json.loads(json.dumps(board))
filled["pads"]["padstacks"]["FILL"] = {"usage": "Smd", "drill": None,
                                       "pads": {"ETCH/TOP": RECT, "PIN/SOLDERMASK_TOP": RECT}}
filled["pads"]["pins"].append([12.0, 8.0, 0.0, False, "FILL", "ETCH/TOP", "ETCH/TOP"])
jf.write_text(json.dumps(filled))
res_f, logs_f, text_f = build("filled_on", exposed_copper=True, mask_openings=True)
jf.write_text(json.dumps(board))
check("a window the copper fills is counted, not placed: one more pad, no more windows, and said",
      res_f.pads_placed == res_b.pads_placed + 1 and res_f.openings_placed == res_b.openings_placed
      and res_f.openings_filled == 1 and "opening_FILL" not in text_f
      and any("1 filled by their copper" in m for m in logs_f),
      (res_f.pads_placed, res_f.openings_placed, res_f.openings_filled,
       [m for m in logs_f if "Mask openings" in m]))
check("and on the board where none fills, none is counted",
      res_b.openings_filled == 0 and not any("filled by their copper" in m for m in logs_b),
      (res_b.openings_filled, [m for m in logs_b if "Mask openings" in m]))

# Three heights, a flat-silkscreen clearance apart: the windows lowest, the
# copper one step up - so where the windows of two neighbouring through pins
# overlap each other's copper ring, the copper is on top by construction and
# not by the viewer's draw order (rings came out eaten on the demo board in
# step2html when both sat at one height). Measured through the placements.
from stepbuilder.defaults import DEFAULT_FLAT_HEIGHT as H
placed_z = []
drawn_lifts = []
_orig_placement = P._placement
_orig_exposed = core.build_exposed
P._placement = lambda x, y, z, rotation, fold: (placed_z.append(round(z, 6)), _orig_placement(x, y, z, rotation, fold))[1]
core.build_exposed = lambda *a, **kw: (drawn_lifts.append(kw.get("lift")), _orig_exposed(*a, **kw))[1]
try:
    build("both_on_heights", exposed_copper=True, mask_openings=True)
finally:
    P._placement = _orig_placement
    core.build_exposed = _orig_exposed
top_face, bottom_face = 0.0, -1.104            # z_datum top: the mask's top face at 0, the stack 1.104 down
check("the windows sit one clearance above the face and the copper two, on both sides",
      sorted(set(z for z in placed_z if z > 0)) == [round(top_face + H, 6), round(top_face + 2 * H, 6)]
      and sorted(set(z for z in placed_z if z < 0)) == [round(bottom_face - 2 * H, 6), round(bottom_face - H, 6)],
      sorted(set(placed_z)))
# The third height does not go through _placement: the drawn openings' parts
# are built flat like a legend, lifted by what _build_pads hands build_exposed.
# Collapsing 3h onto 2h - the copper part coplanar with the pads - passed the
# check above (review of 2026-09-17), so the lift is read where it is given.
check("and the drawn openings' copper and laminate stand a third step up, above the copper",
      len(drawn_lifts) >= 2 and all(abs(lift - 3 * H) < 1e-12 for lift in drawn_lifts), drawn_lifts)


# The line above reads the lift build_exposed was GIVEN, which is an argument
# and not a height: a build_silkscreen that ignored flat_offset, and a
# build_exposed that lifted the BOTTOM side into the board instead of away
# from it, both passed it (measured 2026-09-22). So read the z of what was
# actually built, on both sides.
def zrange(shape):
    b = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, b, False, False)
    return b.CornerMin().Z(), b.CornerMax().Z()


flat_z = dict(stackups=board["stackups"], zones=[], levels={},
              board_top_z=top_face, board_bottom_z=bottom_face, lift=3 * H)
exp_top = P.build_exposed(board, section="exposed", **flat_z)["top"][0]
bare_bot = P.build_exposed(board, section="bare", **flat_z)["bottom"][0]
check(f"the copper under a drawn opening really lies at z = {top_face + 3 * H}, "
      f"three clearances above the top face",
      exp_top is not None and all(abs(z - (top_face + 3 * H)) < 1e-9 for z in zrange(exp_top)),
      exp_top is not None and zrange(exp_top))
check(f"and the bottom one at z = {bottom_face - 3 * H}, three BELOW the bottom "
      f"face and not inside the board",
      bare_bot is not None and all(abs(z - (bottom_face - 3 * H)) < 1e-9 for z in zrange(bare_bot)),
      bare_bot is not None and zrange(bare_bot))
check("off: no openings node, nothing said", "openings_top" not in text2
      and not any("Mask openings" in m for m in logs2))

v10o = json.loads(json.dumps(board))
for stack in v10o["pads"]["padstacks"].values():
    stack["pads"] = {lay: p for lay, p in stack["pads"].items() if lay.startswith("ETCH/")}
del v10o["pads"]["exposed"]
del v10o["pads"]["bare"]
jf.write_text(json.dumps(v10o))
res_v, logs_v, text_v = build("openings_v10", exposed_copper=False, mask_openings=True)
check("a v10 library has no openings to draw, and says so",
      res_v.openings_placed == 0 and "openings_top" not in text_v
      and any("carries no mask openings (format_version 10)" in m for m in logs_v),
      [m for m in logs_v if "note" in m])
jf.write_text(json.dumps(board))

old = dict(board)
del old["pads"]
old["format_version"] = 9
jf.write_text(json.dumps(old))
res3, logs3, _ = build("pads_old", exposed_copper=True)
check("a file without pads says so and builds", res3.pads_placed == 0
      and any("No pads in this JSON" in m for m in logs3), logs3[-4:])

print("\n[7] a rigid-flex board: openings only where the zone's stackup carries a soldermask")
# tests/fixtures/rigidflex.json: zone S2 (x 0..16, y 0..11.38) on STIFFENER2,
# which has SOLDERMASK_TOP and _BOTTOM; zone F2 (x 0..41, y 11.38..26.5) on
# FLEX, coverlay and adhesive only. Cadence's demo is the same shape: its
# outline is drawn as strokes on BOARD GEOMETRY/SOLDERMASK_* through every
# zone, and the part over a flex zone floated two millimetres above it.
rf = json.loads((ROOT / "tests/fixtures/rigidflex.json").read_text())
rf.update({"format_version": 12, "name": "rfpads", "components": {}})
rf["pads"] = {"padstacks": {"SMD": smd},
              "pins": [[8.0, 5.0, 0.0, False, "SMD", "ETCH/TOP", "ETCH/TOP"],       # on S2: a mask there
                       [20.0, 20.0, 0.0, False, "SMD", "ETCH/TOP", "ETCH/TOP"]],    # on F2: coverlay, no mask
              "exposed": {"top": [], "bottom": []},
              "bare": {"top": [{"layer": "BOARD GEOMETRY/SOLDERMASK_TOP", "area": 4.0,       # inside S2
                                "vertices": [[2, 2, 0], [4, 2, 0], [4, 4, 0], [2, 4, 0]]},
                               {"layer": "BOARD GEOMETRY/SOLDERMASK_TOP", "area": 4.0,       # inside F2
                                "vertices": [[20, 18, 0], [22, 18, 0], [22, 20, 0], [20, 20, 0]]},
                               {"layer": "BOARD GEOMETRY/SOLDERMASK_TOP", "area": 6.0,       # across y = 11.38
                                "vertices": [[6, 10, 0], [8, 10, 0], [8, 13, 0], [6, 13, 0]]}],
                       "bottom": []}}
check("mask_sides reads the stackups: STIFFENER2 both sides, FLEX neither, no layers means both",
      P.mask_sides(rf["stackups"]["STIFFENER2"]) == (True, True)
      and P.mask_sides(rf["stackups"]["FLEX"]) == (False, False)
      and P.mask_sides({"layers": []}) == (True, True))
# Every stackup on hand is masked on both sides or on neither, so nothing said
# which of the two answers belongs to which side: swapping them passed
# (measured 2026-09-22). A stackup masked on ONE side is what tells them apart.
ONE_SIDED = {"layers": [{"name": "SOLDERMASK_TOP", "type": "MASK"},
                        {"name": "TOP", "type": "CONDUCTOR"},
                        {"name": "", "type": "DIELECTRIC"},
                        {"name": "BOTTOM", "type": "CONDUCTOR"},
                        {"name": "COVERLAY_BOTTOM", "type": "MASK"}]}
OTHER_SIDE = {"layers": [dict(lay, name=lay["name"].replace("SOLDERMASK_TOP", "COVERLAY_TOP")
                              .replace("COVERLAY_BOTTOM", "SOLDERMASK_BOTTOM"))
                         for lay in ONE_SIDED["layers"]]}
check("a stackup masked on one side only is read on the right side of it",
      P.mask_sides(ONE_SIDED) == (True, False) and P.mask_sides(OTHER_SIDE) == (False, True),
      (P.mask_sides(ONE_SIDED), P.mask_sides(OTHER_SIDE)))
jf.write_text(json.dumps(rf))
res_rf, logs_rf, text_rf = build("rf_open", exposed_copper=True, mask_openings=True, fold_bends=False)
check("both pins keep their copper, only the one on the masked zone gets a window",
      res_rf.pads_placed == 2 and res_rf.openings_placed == 1
      and any("1 opening(s) not drawn: their zone carries no soldermask on that side (F2)" in m for m in logs_rf),
      (res_rf.pads_placed, res_rf.openings_placed, [m for m in logs_rf if "opening" in m]))
check("the drawn opening on the flex is left out, the one across the boundary clipped, the log says so",
      any("bare_top: the mask is only on S2 - 1 drawn-opening polygon(s) clipped to it, 1 left out" in m for m in logs_rf)
      and any("Bare laminate in drawn openings, top: 2 polygon(s)" in m for m in logs_rf),
      [m for m in logs_rf if "bare_top" in m or "Bare" in m])
out_rf = P.build_exposed(rf, stackups=rf["stackups"], zones=rf["zones"],
                         levels={"S2": (0.0, -2.44), "F2": (-2.05, -2.415)},
                         board_top_z=0.0, board_bottom_z=-2.44, lift=0.003, section="bare")
comp_rf, built_rf, _ = out_rf["top"]
check("what is built is the square on S2 plus the clipped strip: 4 + 2 x 1.38 mm2, ending at the boundary",
      built_rf == 2 and comp_rf is not None and abs(P.shape_area(comp_rf) - 6.76) < 1e-3
      and abs(P._tight_box(comp_rf)[3] - 11.38) < 1e-6,
      (built_rf, P.shape_area(comp_rf) if comp_rf is not None else None,
       P._tight_box(comp_rf) if comp_rf is not None else None))

# A plain board that is all flex: one stackup, coverlay instead of a mask.
flex_only = json.loads(json.dumps(board))
for lay in flex_only["stackups"]["Primary"]["layers"]:
    if lay["name"].startswith("SOLDERMASK_"):
        lay["name"] = lay["name"].replace("SOLDERMASK_", "COVERLAY_")
jf.write_text(json.dumps(flex_only))
res_fo, logs_fo, text_fo = build("flex_only", exposed_copper=True, mask_openings=True)
check("a plain board without a soldermask gets its copper and no window anywhere",
      res_fo.pads_placed == 5 and res_fo.openings_placed == 0 and "openings_top" not in text_fo
      and any("5 opening(s) not drawn: their zone carries no soldermask on that side (the board)" in m for m in logs_fo)
      and any("bare_bottom: 1 drawn-opening polygon(s) left out - the board carries no soldermask on the bottom" in m
              for m in logs_fo),
      (res_fo.pads_placed, res_fo.openings_placed, [m for m in logs_fo if "soldermask" in m]))

# A plain board WITH a mask has no zone to clip to, but it has an edge, and
# Cadence's demo draws its outline as 1 mm strokes on the mask layers: the
# demo's zones clipped those, a plain board built them half in the air
# (review of 2026-09-17). The outline is the plain board's one masked zone.
over = json.loads(json.dumps(board))
over["pads"]["bare"]["top"] = [
    {"layer": "BOARD GEOMETRY/SOLDERMASK_TOP", "area": 8.0,        # across the right edge x = 20
     "vertices": [[18, 4, 0], [22, 4, 0], [22, 6, 0], [18, 6, 0]]},
    {"layer": "BOARD GEOMETRY/SOLDERMASK_TOP", "area": 4.0,        # outside the board altogether
     "vertices": [[25, 4, 0], [27, 4, 0], [27, 6, 0], [25, 6, 0]]},
    {"layer": "BOARD GEOMETRY/SOLDERMASK_TOP", "area": 1.0,        # inside, as before
     "vertices": [[1, 1, 0], [2, 1, 0], [2, 2, 0], [1, 2, 0]]}]
logs_over = []
comp_over, built_over, _ = P.build_exposed(over, stackups=over["stackups"], zones=[], levels={},
                                           board_top_z=0.0, board_bottom_z=-1.104, lift=0.003,
                                           section="bare", log=logs_over.append)["top"]
check("on a plain board a drawn opening across the edge is clipped to the outline, one outside it left out",
      built_over == 2 and comp_over is not None and abs(P.shape_area(comp_over) - 5.0) < 1e-6
      and abs(P._tight_box(comp_over)[2] - 20.0) < 1e-6,
      (built_over, comp_over is not None and P.shape_area(comp_over),
       comp_over is not None and P._tight_box(comp_over)))
check("and the log says so",
      any("1 drawn-opening polygon(s) reach past the board outline and are clipped to it, "
          "1 lie outside it and are left out" in m for m in logs_over), logs_over)
jf.write_text(json.dumps(over))
res_over, logs_ov, text_ov = build("plain_clip", exposed_copper=False, mask_openings=True)
jf.write_text(json.dumps(board))
check("through the build: the part is there and the clip is in the log",
      "bare_top_plain_clip" in text_ov and any("clipped to it" in m for m in logs_ov)
      and any("Drawn openings, whole, top: 3 polygon(s)" in m for m in logs_ov),
      [m for m in logs_ov if "bare_top" in m or "Drawn" in m])

print()
print("[8] the exposed-copper sweep finds the copper the same way everything else does")

# The pour that vanished (2026-09-14). s3dCollectExposed used to discover the
# copper under each opening with axlAddSelectBox - Allegro's INTERACTIVE find -
# and what that returns depends on the session. Headless, on 24.1 and 25.1
# alike, circle-A0 gave 24 polygons of copper and 50 of bare laminate, the
# first of them the 67.534 mm2 pour; the user's own GUI export of the same
# board with the same SKILL gave 25 and 48, the pour gone into bare laminate
# and two stubs of trace in its place, and the model showed traces and pads on
# a bare board. Every other sweep in the exporter uses axlAddSelectAll over a
# visibility set, and in that same journal every one of them matched headless
# exactly: legend 8 -> 2, openings 24, pins 3, vias 23.
#
# So the sweep now selects the side's copper once with axlAddSelectAll,
# converts each object once, and matches polygons to openings by bounding box
# in SKILL. These are the two halves of that: the box test, and the source.
from skill_transliterations import s3dBoxesMeet

BOX = [[0.0, 0.0], [10.0, 10.0]]
check("a box meets itself", s3dBoxesMeet(BOX, BOX))
check("and one inside it", s3dBoxesMeet(BOX, [[2.0, 2.0], [3.0, 3.0]]))
check("and one that swallows it", s3dBoxesMeet(BOX, [[-5.0, -5.0], [50.0, 50.0]]))
check("and one that overlaps a corner", s3dBoxesMeet(BOX, [[9.0, 9.0], [12.0, 12.0]]))
check("touching along an edge counts - the AND decides what it exposes",
      s3dBoxesMeet(BOX, [[10.0, 0.0], [12.0, 10.0]]))
check("clear to the right does not", not s3dBoxesMeet(BOX, [[10.001, 0.0], [12.0, 10.0]]))
check("nor clear above", not s3dBoxesMeet(BOX, [[0.0, 10.001], [10.0, 12.0]]))
check("nor clear to the left", not s3dBoxesMeet([[10.001, 0.0], [12.0, 10.0]], BOX))
check("nor clear below", not s3dBoxesMeet([[0.0, 10.001], [10.0, 12.0]], BOX))
# A polygon whose box could not be read must not be dropped silently: the
# whole point of the round is that missing copper was never reported.
check("an unreadable box is kept, not discarded", s3dBoxesMeet(None, BOX)
      and s3dBoxesMeet(BOX, None))

src = exporter_source()
sweep = src[src.index("procedure( s3dCollectExposed"):]
sweep = sweep[:sweep.index("\n; The whole \"pads\" object")]
check("the sweep selects the side's copper with axlAddSelectAll",
      "axlAddSelectAll()" in sweep, sweep[:200])
# The NAME still appears in the sweep - in the comment that says why it is
# not called - so the test is for a CALL, with the spaces normalised away.
check("and no longer asks for a box select per opening",
      "s3dSelectInBox(" not in sweep.replace(" ", ""))
check("it matches polygons to openings by bounding box instead",
      "s3dBoxesMeet(" in sweep)
check("and converts each object with no window, so a shape comes back whole",
      "s3dCopperPolys( o etch nil s_endCap )" in sweep)
check("the console says how much copper the sweep FOUND, not only what survived",
      "%d copper object(s)" in src)
check("and warns when a board with openings turns up no copper at all",
      "found NO copper at all" in src)

print()
print("[9] a drawn opening with a hole in it folds as a face, not as a wireframe")

# Round 86c's 2199 warnings on flex3-a0, found in the review of 2026-09-17.
# The bare laminate under a mask opening is a RING - the opening less the
# copper - so its face has more than one wire. FoldPlan.apply folds a
# fuse=False shape piece by piece through TopoDS_Iterator, and on a FACE that
# iterator yields WIRES: each wire's edges, then each edge's vertices, were
# "folded" and cut away (a vertex is empty to _is_empty), three warnings per
# edge, and the face came back as its flat edges with no face between them -
# 48.14 of 112.11 mm2 of bare laminate gone, 733 loose edges in the file, 350
# of them left flat where the panel after BEND_3 used to be. The rigid-flex
# fixture with a third masked zone beyond the bend reproduces both halves:
# the ring on the held panel loses its face, the ring beyond the bend is left
# flat as well.
from stepbuilder.bend import plan_from_json

rf9 = json.loads((ROOT / "tests/fixtures/rigidflex.json").read_text())
rf9.update({"format_version": 12, "name": "rfpads", "components": {}})
rf9["zones"][1]["contour"] = rect(0, 11.38, 41, 21.5)                       # F2, shortened
rf9["zones"].append({"name": "S3", "stackup": "STIFFENER2", "contour": rect(0, 21.5, 41, 26.5)})


def ring(x0, y0, x1, y1, hx0, hy0, hx1, hy1):
    """A drawn opening showing bare laminate around a copper island: an
    outer rectangle with a rectangular hole, Allegro's area beside it."""
    return {"layer": "BOARD GEOMETRY/SOLDERMASK_TOP",
            "area": (x1 - x0) * (y1 - y0) - (hx1 - hx0) * (hy1 - hy0),
            "vertices": [[x0, y0, 0], [x1, y0, 0], [x1, y1, 0], [x0, y1, 0]],
            "holes": [[[hx0, hy0, 0], [hx1, hy0, 0], [hx1, hy1, 0], [hx0, hy1, 0]]]}


rf9["pads"] = {"padstacks": {"SMD": smd},
               "pins": [[8.0, 5.0, 0.0, False, "SMD", "ETCH/TOP", "ETCH/TOP"]],
               "exposed": {"top": [], "bottom": []},
               "bare": {"top": [ring(2, 2, 6, 6, 3, 3, 5, 5),                 # inside S2: 12 mm2
                                ring(2, 9, 6, 13, 3, 10, 5, 11),              # across y = 11.38 into F2: 9.52 - 2 = 7.52 on S2
                                ring(10, 20.5, 14, 24, 11, 22, 13, 23)],      # across y = 21.5 into S3, beyond the bend: 10 - 2 = 8
                        "bottom": []}}
levels9 = {"S2": (0.0, -2.44), "F2": (-2.05, -2.415), "S3": (0.0, -2.44)}
plan9 = plan_from_json(rf9, 0.0, -2.44, zones=rf9["zones"], levels=levels9)
check("the fixture's bend is read and the origin's panel is held",
      len(plan9.bends) == 1 and plan9.region_at(3.0, 3.0) == "held" and plan9.region_at(12.0, 25.0) != "held",
      (len(plan9.bends), plan9.region_at(3.0, 3.0), plan9.region_at(12.0, 25.0)))
comp9, built9, _ = P.build_exposed(rf9, stackups=rf9["stackups"], zones=rf9["zones"], levels=levels9,
                                   board_top_z=0.0, board_bottom_z=-2.44, lift=0.003, section="bare")["top"]
flat_area = 12.0 + 7.52 + 8.0
check("flat: three rings, two of them clipped at a zone boundary, 27.52 mm2",
      built9 == 3 and abs(P.shape_area(comp9) - flat_area) < 1e-6 and len(P._faces_of(comp9)) == 3,
      (built9, P.shape_area(comp9), len(P._faces_of(comp9))))
logs9 = []
folded9 = plan9.apply(comp9, fuse=False, note=False, log=logs9.append)
check("folding a ring does not cut it away", not any("folding cut the shape away" in m for m in logs9),
      f"{sum(1 for m in logs9 if 'cut the shape away' in m)} warning(s)")
check("the rings keep their faces and their area through the fold, and leave no loose edge",
      abs(P.shape_area(folded9) - flat_area) < 1e-6 and len(P._faces_of(folded9)) == 3 and free_edges(folded9) == 0,
      (P.shape_area(folded9), len(P._faces_of(folded9)), free_edges(folded9)))
fb9 = bbox(folded9)
check("the ring beyond the bend stands up with its panel; nothing is left flat past the bend line",
      fb9[5] > 1.0 and fb9[4] < 21.0, tuple(round(v, 3) for v in fb9))

jf.write_text(json.dumps(rf9))
res9, logs9, text9 = build("rf_fold", exposed_copper=True, mask_openings=True)
jf.write_text(json.dumps(board))
check("through the build, folded: the bare part is there, nothing was cut away, and the file has no wireframe",
      "bare_top_rf_fold" in text9 and not any("folding cut the shape away" in m for m in logs9)
      and free_edges(read_step(OUT / "rf_fold.step")) == 0,
      (sum(1 for m in logs9 if "cut the shape away" in m), free_edges(read_step(OUT / "rf_fold.step"))))

print()
print("[10] at the board's edge: pads and openings clipped to the outline and the cutouts")

# The user's 5988-a1 (2026-09-22, round 91): sixteen mouse-bite holes 0.2 mm
# inside the edge, drill r 0.3, mask opening r 0.35 - and the opening, a
# shared annulus instanced per via, reached 0.15 mm into the air on all 32
# placements. A copper pad at the edge would have done the same. So a
# placement whose figure reaches the outline or a cutout is clipped to the
# board's face and becomes a face of its own; the rest stay instances.
EDGES = [rect(0, 0, 20, 10), circle(0.4, 5, 5)]
bd = P._Boundary(EDGES)
check("the edge is read: outline and cutout, five exact pieces on a grid",
      bd.ok and len(bd.pieces) == 5 and bd.cutouts == [circle(0.4, 5, 5)], (bd.ok, len(bd.pieces)))
check("a figure well inside reaches nothing; one at the edge reaches the outline, one over the cutout the cutout",
      bd.reaches(10.0, 5.0, 1.0) == set() and bd.reaches(19.5, 5.0, 1.0) == {0} and bd.reaches(5.0, 5.9, 1.0) == {1}
      and bd.reaches(5.0, 6.5, 1.0) == set(),
      (bd.reaches(10.0, 5.0, 1.0), bd.reaches(19.5, 5.0, 1.0), bd.reaches(5.0, 5.9, 1.0), bd.reaches(5.0, 6.5, 1.0)))
# A cutout that repeats the pin's own drill takes nothing off a figure the
# drill is already out of: the cutouts script leaves one on every through
# pin (270 of the demo's 274 cutouts), and each was a 40 ms boolean for
# nothing. The drill's offset turns and mirrors with the pin.
check("a cutout inside the pin's drill is known as such - by size, centre, offset, mirror and turn",
      bd.within_drill(1, 5.0, 5.0, circle(0.4), False, 0.0) and bd.within_drill(1, 5.0, 5.0, circle(0.5), False, 0.0)
      and not bd.within_drill(1, 5.0, 5.0, circle(0.3), False, 0.0)          # the cutout is larger than the drill
      and not bd.within_drill(1, 5.0, 5.5, circle(0.4), False, 0.0)          # off the pin
      and bd.within_drill(1, 4.5, 5.0, circle(0.4, 0.5, 0.0), False, 0.0)    # an offset drill lands on it
      and not bd.within_drill(1, 4.5, 5.0, circle(0.4, 0.5, 0.0), True, 0.0)  # mirrored, it lands the other way
      and bd.within_drill(1, 5.5, 5.0, circle(0.4, 0.5, 0.0), False, 180.0)  # turned half round, on it again
      and not bd.within_drill(1, 5.0, 5.0, None, False, 0.0))                # no drill: a real hole in the copper
check("on_board: inside yes, outside no, in the cutout no, beside the edge yes, past it no",
      bd.on_board(10.0, 5.0) and not bd.on_board(25.0, 5.0) and not bd.on_board(5.0, 5.0)
      and bd.on_board(19.9, 9.9) and not bd.on_board(20.1, 5.0),
      (bd.on_board(10.0, 5.0), bd.on_board(25.0, 5.0), bd.on_board(5.0, 5.0), bd.on_board(19.9, 9.9),
       bd.on_board(20.1, 5.0)))
# The reach test is exact against the arc, not against a chord: a pad
# 0.05 mm clear of a round edge does not reach it, one 0.05 mm short does.
# contour_points samples a circle in eight chords, whose sag on r 0.4 is
# 0.03 mm - so a chord would have put the clear pad over the hole.
check("the distance to a circle is measured to the circle",
      not bd.reaches(5.0, 5.0 + 0.4 + 1.0 + 0.05, 1.0) and bd.reaches(5.0, 5.0 + 0.4 + 1.0 - 0.05, 1.0))
bf = P.board_face(EDGES[0], EDGES[1:], 0.0)
check("the board's face is the outline less the cutout",
      abs(P.shape_area(bf) - (200.0 - math.pi * 0.16)) < 1e-6, P.shape_area(bf))
disc, _ = P.pad_face(DISC, None, False, True)                       # r 0.8
rim, hole = bd.outline_face(), bd.cutout_face(1)
check("the outline's face and the cutout's are built on demand, once each",
      rim is not None and hole is not None and rim is bd.outline_face() and hole is bd.cutout_face(1)
      and abs(P.shape_area(rim) - 200.0) < 1e-9 and abs(P.shape_area(hole) - math.pi * 0.16) < 1e-9)
half, whole_h, note_h = P.clip_to_board(disc, 20.0, 5.0, 0.0, rim, [])
check("a disc centred on the right edge: half of it stays, ending at x = 20",
      half is not None and not whole_h and note_h is None and abs(P.shape_area(half) - math.pi * 0.32) < 1e-6
      and abs(P._tight_box(half)[2] - 20.0) < 1e-9, (whole_h, note_h, half is not None and P.shape_area(half)))
over_cut, whole_c, _ = P.clip_to_board(disc, 5.0, 5.0, 0.0, rim, [hole])
check("a disc over the cutout loses the hole", over_cut is not None and not whole_c
      and abs(P.shape_area(over_cut) - math.pi * (0.64 - 0.16)) < 1e-6,
      over_cut is not None and P.shape_area(over_cut))
over_only, whole_o, _ = P.clip_to_board(disc, 5.0, 5.0, 0.0, None, [hole])
check("and the same with no outline given - a figure that reaches only the cutout",
      over_only is not None and not whole_o and abs(P.shape_area(over_only) - math.pi * (0.64 - 0.16)) < 1e-6)
inside_d, whole_i, _ = P.clip_to_board(disc, 10.0, 5.0, 0.0, rim, [])
check("a disc well inside comes back whole", whole_i and abs(P.shape_area(inside_d) - math.pi * 0.64) < 1e-9)
check("a disc off the board is nothing, and not a failure",
      P.clip_to_board(disc, 30.0, 5.0, 0.0, rim, []) == (None, False, None))
check("a disc inside a cutout of its own size is nothing too",
      P.clip_to_board(disc, 5.0, 5.0, 0.0, None, [P._face_from_wires(P.build_contour(circle(0.8, 5, 5), 0.0), [])])
      == (None, False, None))
# The coincident wall. The THRU pin at (5, 5) has its drill r 0.4 cut out
# already and the board's cutout there is the same circle - which is what
# the cutouts script leaves on 5988-a1 at every mounting hole and every
# mouse bite. The boolean has to hand the ring back whole, to the last
# digit, or every such pin would get a face of its own for nothing.
ring_t, _ = P.pad_face(TOPPAD, circle(0.4), False, True)
ring_c, whole_r, _ = P.clip_to_board(ring_t, 5.0, 5.0, 0.0, rim, [hole])
check("a ring whose hole IS the cutout comes back whole",
      whole_r and abs(P.shape_area(ring_c) - P.shape_area(ring_t)) < 1e-9,
      (whole_r, P.shape_area(ring_c), P.shape_area(ring_t)))
# Mirrored and turned: the 2 x 1 rectangle at 90 degrees stands x 19.5..20.5
# on the right edge; the inner half stays, its normals still facing down.
rect_m, _ = P.pad_face(RECT, None, True, False)
strip, whole_s, _ = P.clip_to_board(rect_m, 20.0, 5.0, 90.0, rim, [], face_up=False)
check("a turned, mirrored pad on the edge keeps its inner half, normals facing down",
      strip is not None and not whole_s and abs(P.shape_area(strip) - 1.0) < 1e-9
      and abs(P._tight_box(strip)[0] - 19.5) < 1e-9 and abs(P._tight_box(strip)[2] - 20.0) < 1e-9
      and all(P._normal_up(f) is False for f in P._faces_of(strip)),
      (strip is not None and P.shape_area(strip), strip is not None and P._tight_box(strip)))
# The fold: a clipped face already stands at its pin in the flat frame, so
# it takes only the lift and the fold - and has to land exactly where
# _placement puts the shared figure. The stub of [3] stands the panel up.
from OCP.gp import gp_Pnt as _Pnt
p_whole = _Pnt(0.7, 0.2, 0.0).Transformed(P._placement(10.0, 20.0, 0.5, 30.0, _Bend()))
p_clip = (_Pnt(0.7, 0.2, 0.0).Transformed(P._placement(10.0, 20.0, 0.0, 30.0, None))
          .Transformed(P._lift(10.0, 20.0, 0.5, _Bend())))
check("_lift after the flat placement is _placement with the fold, to the last digit",
      p_whole.Distance(p_clip) < 1e-9, p_whole.Distance(p_clip))
check("and without a fold it is the lift alone",
      abs(P._lift(1.0, 2.0, 0.5, None).TranslationPart().Z() - 0.5) < 1e-12)

# The mouse bite of 5988-a1 itself: drill r 0.3, copper r 0.025 (all hole),
# opening r 0.35, the hole 0.2 mm inside the edge and, after the cutouts
# script, a cutout of the drill's own size on it. Its window is the annulus
# less the part past the edge: 0.0726 of 0.1021 mm2, ending at y = 0.
TAB = {"usage": "Via", "drill": circle(0.3),
       "pads": {"ETCH/TOP": pad(circle(0.025), [[-0.025, -0.025], [0.025, 0.025]], "CIRCLE"),
                "ETCH/BOTTOM": pad(circle(0.025), [[-0.025, -0.025], [0.025, 0.025]], "CIRCLE"),
                "PIN/SOLDERMASK_TOP": pad(circle(0.35), [[-0.35, -0.35], [0.35, 0.35]], "CIRCLE"),
                "PIN/SOLDERMASK_BOTTOM": pad(circle(0.35), [[-0.35, -0.35], [0.35, 0.35]], "CIRCLE")}}
BITE = circle(0.3, 14.0, 0.2)


def segment_area(r, d):
    """The part of a disc of radius r beyond a chord d from its centre."""
    return r * r * math.acos(d / r) - d * math.sqrt(r * r - d * d)


tab_win, _ = P.opening_face(TAB["pads"]["PIN/SOLDERMASK_TOP"], TAB["drill"], False, True, copper=TAB["pads"]["ETCH/TOP"])
bd_tab = P._Boundary(EDGES + [BITE])
check("the bite's window reaches the outline and its own cutout, and that cutout is its drill",
      bd_tab.reaches(14.0, 0.2, 0.35) == {0, 2} and bd_tab.within_drill(2, 14.0, 0.2, TAB["drill"], False, 0.0),
      bd_tab.reaches(14.0, 0.2, 0.35))
# Clipped by both, as if the cutout were not its drill: the coincident
# circle must take nothing, the outline the part past the edge.
tab_clip, tab_whole, _ = P.clip_to_board(tab_win, 14.0, 0.2, 0.0, bd_tab.outline_face(), [bd_tab.cutout_face(2)])
tab_expected = math.pi * (0.35 ** 2 - 0.3 ** 2) - (segment_area(0.35, 0.2) - segment_area(0.3, 0.2))
check("the mouse bite's window is the annulus less its part past the edge, ending at y = 0",
      tab_clip is not None and not tab_whole and abs(P.shape_area(tab_clip) - tab_expected) < 1e-9
      and abs(P._tight_box(tab_clip)[1]) < 1e-9,
      (tab_whole, tab_clip is not None and P.shape_area(tab_clip), tab_expected))

# Through the build: three more surface pins - across the right edge, over
# the cutout, off the board - and the mouse bite with its cutout.
edge_board = json.loads(json.dumps(board))
edge_board["pads"]["padstacks"]["TAB"] = TAB
edge_board["pads"]["pins"] += [
    [20.0, 5.0, 0.0, False, "SMD", "ETCH/TOP", "ETCH/TOP"],           # across the right edge: half stays
    [5.0, 5.5, 0.0, False, "SMD", "ETCH/TOP", "ETCH/TOP"],            # over the cutout: the hole's upper half goes
    [25.0, 5.0, 0.0, False, "SMD", "ETCH/TOP", "ETCH/TOP"],           # off the board: nothing
    [14.0, 0.2, 0.0, False, "TAB", "ETCH/TOP", "ETCH/BOTTOM", "via"]]  # the mouse bite
edge_board["pcb"]["edges"].append(BITE)
jf.write_text(json.dumps(edge_board))
res_e, logs_e, text_e = build("edge", exposed_copper=True, mask_openings=True)
jf.write_text(json.dumps(board))
check("two pads clipped, one off the board, the rest instances as before",
      res_e.pads_placed == 7 and res_e.pads_clipped == 2 and res_e.pads_off_board == 1 and res_e.pads_figures == 5,
      (res_e.pads_placed, res_e.pads_clipped, res_e.pads_off_board, res_e.pads_figures))
check("four openings clipped - the two pins' and the bite's two - one off the board",
      res_e.openings_placed == 9 and res_e.openings_clipped == 4 and res_e.openings_off_board == 1,
      (res_e.openings_placed, res_e.openings_clipped, res_e.openings_off_board))
check("a clipped placement is a part of its own, named after the figure",
      "'pad_SMD_TOP_clipped'" in text_e and "'opening_SMD_SOLDERMASK_TOP_clipped'" in text_e
      and "'opening_TAB_SOLDERMASK_TOP_clipped'" in text_e and "'opening_TAB_SOLDERMASK_BOTTOM_clipped'" in text_e)
check("the pins that are clear of the edge still share their figure",
      "'pad_SMD_TOP'" in text_e and "'opening_SMD_SOLDERMASK_TOP'" in text_e)
check("a figure every placement of which is clipped is not left loose at the origin",
      "'opening_TAB_SOLDERMASK_TOP'" not in text_e and "'opening_TAB_SOLDERMASK_BOTTOM'" not in text_e
      and "'pad_TAB" not in text_e)
check("the log counts them",
      any("2 pad(s) reach the board's edge or a cutout and are clipped to it" in m for m in logs_e)
      and any("1 pad(s) lie off the board and draw nothing" in m for m in logs_e)
      and any("4 opening(s) reach the board's edge or a cutout and are clipped to it" in m for m in logs_e)
      and any("1 opening(s) lie off the board and draw nothing" in m for m in logs_e),
      [m for m in logs_e if "edge" in m or "off the board" in m])
check("the board is still one solid, with the bite in it",
      count_solids(read_step(OUT / "edge.step")) == 1)
check("and the board of [5], every pin of which is clear of the edge, builds exactly as before",
      res.pads_placed == 5 and res.pads_clipped == 0 and res.pads_off_board == 0
      and "_clipped" not in text and not any("clipped" in m for m in logs),
      (res.pads_placed, res.pads_clipped, [m for m in logs if "clipped" in m]))

# A file with no outline clips nothing and places every pad as it did.
no_edge = json.loads(json.dumps(edge_board))
no_edge["pcb"]["edges"] = []
check("no outline: the edge is not read, nothing is clipped", not P._Boundary([]).ok and not P._Boundary([[]]).ok)

# The drawn openings' parts are clipped to the cutouts the same way: a
# 2 x 2 opening drawn over the hole at (5, 5) loses it.
cut_over = json.loads(json.dumps(board))
cut_over["pads"]["bare"]["top"] = [
    {"layer": "BOARD GEOMETRY/SOLDERMASK_TOP", "area": 4.0,
     "vertices": [[4, 4, 0], [6, 4, 0], [6, 6, 0], [4, 6, 0]]}]
logs_c = []
comp_c, built_c, _ = P.build_exposed(cut_over, stackups=cut_over["stackups"], zones=[], levels={},
                                     board_top_z=0.0, board_bottom_z=-1.104, lift=0.003,
                                     section="bare", log=logs_c.append)["top"]
check("a drawn opening over a cutout loses the hole, and the log says so",
      built_c == 1 and comp_c is not None and abs(P.shape_area(comp_c) - (4.0 - math.pi * 0.16)) < 1e-6
      and any("1 drawn-opening polygon(s) reach past the board outline or over a cutout and are clipped to it"
              in m for m in logs_c),
      (built_c, comp_c is not None and P.shape_area(comp_c), logs_c))
# and on a zoned board, inside a masked zone: the square of [7] with a hole under it
rf_cut = json.loads(json.dumps(rf))
rf_cut["pcb"]["edges"] = rf_cut["pcb"]["edges"] + [circle(0.5, 3, 3)]
logs_rc = []
comp_rc, built_rc, _ = P.build_exposed(rf_cut, stackups=rf_cut["stackups"], zones=rf_cut["zones"],
                                       levels={"S2": (0.0, -2.44), "F2": (-2.05, -2.415)},
                                       board_top_z=0.0, board_bottom_z=-2.44, lift=0.003,
                                       section="bare", log=logs_rc.append)["top"]
check("on a zoned board a cutout inside a masked zone is taken out of the drawn opening over it",
      built_rc == 2 and comp_rc is not None and abs(P.shape_area(comp_rc) - (6.76 - math.pi * 0.25)) < 1e-3
      and any("2 drawn-opening polygon(s) clipped to it (1 of them over a cutout), 1 left out" in m
              for m in logs_rc),
      (built_rc, comp_rc is not None and P.shape_area(comp_rc), logs_rc))

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
