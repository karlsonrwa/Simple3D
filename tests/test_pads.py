# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, out_dir, fails, check, rect, read_step, count_solids

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
face, note = P.pad_face(R130, None, False, True)
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
         "pads": {"padstacks": {"SMD": smd, "THRU": thru, "BARE": bare},
                  "pins": [[2.0, 2.0, 0.0, False, "SMD", "ETCH/TOP", "ETCH/TOP"],
                           [2.0, 8.0, 90.0, True, "SMD", "ETCH/BOTTOM", "ETCH/BOTTOM"],
                           [5.0, 5.0, 0.0, False, "THRU", "ETCH/TOP", "ETCH/BOTTOM"],
                           [15.0, 5.0, 0.0, False, "NOSUCH", "ETCH/TOP", "ETCH/TOP"],
                           [12.0, 2.0, 0.0, False, "BARE", "ETCH/TOP", "ETCH/TOP"]]}}
jf = OUT / "padboard.json"
jf.write_text(json.dumps(board))


def build(name, **kw):
    logs = []
    res = core.generate(step_dir=ROOT / "demo/step_files", json_file=jf, output_dir=OUT,
                        output_name=name, log=logs.append, **kw)
    return res, logs, (OUT / f"{name}.step").read_text(errors="replace")


res, logs, text = build("pads_on", copper_pads=True)
check("four pad faces placed: two surface pins, a through pin on both faces",
      res.pads_placed == 4 and res.pads_figures == 4, (res.pads_placed, res.pads_figures))
check("the pin whose padstack has no mask opening is under the mask: not drawn, and said",
      "pad_BARE" not in text and any("1 pad(s) have no mask opening" in m for m in logs),
      [m for m in logs if "mask" in m])
check("no v10 note on a v11 library", not any("carries no mask openings" in m for m in logs))

# A format_version 10 library - no mask pad anywhere - cannot say which pads
# are covered: the copper is drawn whole, as before, and the log says so once.
v10 = json.loads(json.dumps(board))
for ps in v10["pads"]["padstacks"].values():
    ps["pads"] = {l: p for l, p in ps["pads"].items() if "SOLDERMASK" not in l}
jf.write_text(json.dumps(v10))
res10, logs10, text10 = build("pads_v10", copper_pads=True)
check("a v10 library draws every pad whole, the bare one included",
      res10.pads_placed == 5 and "pad_BARE" in text10, (res10.pads_placed, [m for m in logs10 if "pads" in m]))
check("and says that the openings are not in the file",
      any("carries no mask openings" in m for m in logs10), logs10[-6:])
jf.write_text(json.dumps(board))
check("the pin with an unknown padstack is counted, not fatal", res.pads_skipped == 1
      and any("name a padstack" in m for m in logs), (res.pads_skipped, [m for m in logs if "padstack" in m]))
check("pads_top and pads_bot are nodes of the assembly, named per board",
      "pads_top_pads_on" in text and "pads_bot_pads_on" in text)
check("the figures are parts named after the padstack and layer",
      "pad_SMD_TOP" in text and "pad_SMD_TOPm" in text and "pad_THRU_TOP" in text and "pad_THRU_BOTTOM" in text)
check("the board is still one solid - no boolean touched it", count_solids(read_step(OUT / "pads_on.step")) == 1)
check("the log says what was placed", any("Copper pads: 4 placed" in m for m in logs), logs[-6:])

res2, logs2, text2 = build("pads_off", copper_pads=False)
check("off: nothing placed, nothing in the file, nothing said",
      res2.pads_placed == 0 and "pads_top" not in text2
      and not any("Copper pads" in m or "No pads" in m for m in logs2),
      [m for m in logs2 if "pads" in m])

# Instanced, not copied: a second pin on the same figure costs a placement,
# not a face. Measured on the demo board's 2906 placements of 83 figures.
more = json.loads(json.dumps(board))
more["pads"]["pins"] += [[x + 0.0, y + 1.0, r, m, n, s, e] for x, y, r, m, n, s, e in board["pads"]["pins"]]
jf.write_text(json.dumps(more))
res_more, _, _ = build("pads_more", copper_pads=True)
size_on = (OUT / "pads_on.step").stat().st_size
size_more = (OUT / "pads_more.step").stat().st_size
per_placement = (size_more - size_on) / max(res_more.pads_placed - res.pads_placed, 1)
check(f"twice the pins, the same figures: {res_more.pads_figures} figures still",
      res_more.pads_placed == 8 and res_more.pads_figures == 4, (res_more.pads_placed, res_more.pads_figures))
check(f"and each extra placement costs under 1.5 kB ({per_placement:.0f} bytes)", 0 < per_placement < 1500)
jf.write_text(json.dumps(board))

old = dict(board)
del old["pads"]
old["format_version"] = 9
jf.write_text(json.dumps(old))
res3, logs3, _ = build("pads_old", copper_pads=True)
check("a file without pads says so and builds", res3.pads_placed == 0
      and any("No pads in this JSON" in m for m in logs3), logs3[-4:])

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
