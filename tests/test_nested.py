# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, out_dir, fails, check, rect, volume, read_step

"""A zone drawn inside another (round 127, R3-6 and R3-7 of the 23.10.2026
review). Allegro nests stackup zones since 22.1 QIR2, and the inner zone is
the region with its own stack: there the board is the inner zone's stack,
not both. The owner's boards nest three - flex-b2's SOLDERMASK1 inside
STIFFENER2, flex2-a0's LDI and LDI2 inside the two STIFF_TOP_500 zones.

Here tests/fixtures/rigidflex.json's zone S2 (x 0..16, y 0..11.38, the
2.315 mm STIFFENER2 stack, soldermask on both sides, a legend) is given a
zone W (x 2..14, y 3..8) on the 0.365 mm FLEX stack (coverlay, no mask, no
legend) - the thin zone inside a thick one of R3-7. Every question the
build asks of a point inside W must answer W, and none may answer S2 there.
"""
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

OUT = out_dir("nested")

W_RECT = rect(2.0, 3.0, 14.0, 8.0)
W_AREA = 12.0 * 5.0
INSIDE, OUTSIDE = (8.0, 5.0), (15.0, 10.0)        # in W; in S2 beside it
BASE = json.loads((ROOT / "tests/fixtures/rigidflex.json").read_text(encoding="utf-8"))
BASE.update({"format_version": 12, "components": {}})


def near(a, b, tol=1e-6):
    return a is not None and b is not None and abs(a - b) <= tol


def board(name, nested=True, change=None):
    d = json.loads(json.dumps(BASE))
    d["name"] = name
    if nested:
        d["zones"].append({"name": "W", "stackup": "FLEX", "contour": W_RECT})
    if change:
        change(d)
    return d


def build(d, **options):
    jf = OUT / f"{d['name']}.json"
    jf.write_text(json.dumps(d), encoding="utf-8")
    logs = []
    res = core.generate(step_dir=ROOT / "demo/step_files", json_file=jf, output_dir=OUT,
                        output_name=d["name"], fold_bends=False, log=logs.append, **options)
    return res, logs, read_step(OUT / f"{d['name']}.step")


def prepare(d, logs=None):
    return core._prepare_stackups(json.loads(json.dumps(d)), BuildOptions(),
                                  logs.append if logs is not None else (lambda m: None))


def solids_of(shape):
    found, exp = [], TopExp_Explorer(shape, TopAbs_SOLID)
    while exp.More():
        found.append(exp.Current())
        exp.Next()
    return found


def faces_of_body(body, x, y):
    """(top, bottom) of *body* on the vertical line through (x, y)."""
    hit = IntCurvesFace_ShapeIntersector()
    hit.Load(body, 1e-7)
    hit.Perform(gp_Lin(gp_Pnt(x, y, 0.0), gp_Dir(0, 0, 1)), -1e3, 1e3)
    zs = [hit.Pnt(k).Z() for k in range(1, hit.NbPnt() + 1)]
    return (max(zs), min(zs)) if zs else (None, None)


print("\n[1] the zone inside another is found, and only it")
said = []
stack = prepare(board("found"), said)
by_name = {str(z["name"]): z for z in stack.zones}
check("S2 is given W's contour as the zone nested in it", by_name["S2"].get("nested") == [W_RECT],
      by_name["S2"].get("nested"))
check("F2, which only touches S2 along y = 11.38, nests nothing and is in nothing",
      not by_name["F2"].get("nested") and not by_name["W"].get("nested"),
      (by_name["F2"].get("nested"), by_name["W"].get("nested")))
check("the log says W lies inside S2 and whose stack the board is there",
      any("Zone W lies inside zone S2" in m and "W's stack" in m for m in said),
      [m for m in said if "inside" in m])
from stepbuilder.zones import nest
said_l = []
L_SHAPE = [{"type": "segment", "start": a, "end": b} for a, b in
           (([0, 0], [20, 0]), ([20, 0], [20, 5]), ([20, 5], [10, 5]), ([10, 5], [10, 10]),
            ([10, 10], [0, 10]), ([0, 10], [0, 0]))]
crossed = nest([{"name": "L", "stackup": "STIFFENER2", "contour": L_SHAPE},
                {"name": "K", "stackup": "FLEX", "contour": rect(8, 6, 12, 8)}], said_l.append)
check("a zone inside another's box but half outside its corner is not inside it",
      not any(z.get("nested") for z in crossed) and not said_l, (crossed, said_l))
levels = stack.levels
w_thick = levels["W"][0] - levels["W"][1]
s2_thick = levels["S2"][0] - levels["S2"][1]
check("the two stacks are what the test is about: S2 2.315 mm, W 0.365 mm",
      near(s2_thick, 2.315) and near(w_thick, 0.365), (s2_thick, w_thick))

print("\n[2] the body: W's stack inside W, S2's around it (R3-7)")
_res, _logs, plain_shape = build(board("plain", nested=False))
_res, nested_logs, nested_shape = build(board("nested"))
plain_v, nested_v = volume(plain_shape), volume(nested_shape)
want = plain_v - W_AREA * (s2_thick - w_thick)
check(f"the board with W is S2's {s2_thick:.3f} mm less W's {w_thick:.3f} over W's 60 mm2: "
      f"{nested_v:.4f} = {want:.4f}", abs(nested_v - want) <= 1e-6 * want, (nested_v, want, plain_v))
body = max(solids_of(nested_shape), key=lambda s: volume(s))
inside_faces, outside_faces = faces_of_body(body, *INSIDE), faces_of_body(body, *OUTSIDE)
check("inside W the body's faces are W's", near(inside_faces[0], levels["W"][0])
      and near(inside_faces[1], levels["W"][1]), (inside_faces, levels["W"]))
check("beside it, in S2, S2's", near(outside_faces[0], levels["S2"][0])
      and near(outside_faces[1], levels["S2"][1]), (outside_faces, levels["S2"]))

print("\n[3] Not stitched holds each layer once: its parts add up to the stitched body (R3-6)")
_res, inspect_logs, inspect_shape = build(board("inspect"), board_mode="inspect")
inspect_v = volume(inspect_shape)
check(f"the separate layer parts {inspect_v:.4f} = the stitched body {nested_v:.4f}",
      abs(inspect_v - nested_v) <= 1e-6 * nested_v, (inspect_v, nested_v))

print("\n[4] the surface, and the zone that makes a face, at a point in W")
check("Surface.at inside W is W's two faces", stack.surface.at(*INSIDE) is not None
      and near(stack.surface.at(*INSIDE)[0], levels["W"][0])
      and near(stack.surface.at(*INSIDE)[1], levels["W"][1]), (stack.surface.at(*INSIDE), levels["W"]))
check("and beside it S2's", near(stack.surface.at(*OUTSIDE)[0], levels["S2"][0]), stack.surface.at(*OUTSIDE))
check("both faces inside W are W's alone", stack.surface.face_zones(*INSIDE) == ({"W"}, {"W"}),
      stack.surface.face_zones(*INSIDE))

print("\n[5] a part placed in W stands on W's face")
ZERO = {"step_name": "cap_D8x10mm.stp", "rotation_x": 0.0, "rotation_y": 0.0, "rotation_z": 0.0,
        "offset_x": 0.0, "offset_y": 0.0, "offset_z": 0.0}
part = {"x": INSIDE[0], "y": INSIDE[1], "angle": 0.0, "is_mirrored": False, "zone": "W", "step_mapping": ZERO}
z = component_transform(ZERO, part, stack.board_top_z, stack.board_bottom_z, zone_levels=levels,
                        surface=stack.surface).TranslationPart().Z()
check("on W's top, not S2's 2 mm above it", near(z, levels["W"][0]), (z, levels["W"][0], levels["S2"][0]))

print("\n[6] pads: copper on W's face, and no mask window where W has no mask")
MASK = {"figure": "RECTANGLE", "bbox": [[-0.6, -0.6], [0.6, 0.6]], "offset": [0.0, 0.0], "inside": 0.0,
        "outline": rect(-0.6, -0.6, 0.6, 0.6)}
PAD = {"figure": "RECTANGLE", "bbox": [[-0.5, -0.5], [0.5, 0.5]], "offset": [0.0, 0.0], "inside": 0.0,
       "outline": rect(-0.5, -0.5, 0.5, 0.5)}


def with_pads(d):
    def square(x0, y0, x1, y1):
        return {"layer": "BOARD GEOMETRY/SOLDERMASK_TOP", "area": (x1 - x0) * (y1 - y0),
                "vertices": [[x0, y0, 0], [x1, y0, 0], [x1, y1, 0], [x0, y1, 0]]}
    d["pads"] = {"padstacks": {"SMD": {"usage": "Smd", "drill": None,
                                       "pads": {"ETCH/TOP": PAD, "PIN/SOLDERMASK_TOP": MASK}}},
                 "pins": [[INSIDE[0], INSIDE[1], 0.0, False, "SMD", "ETCH/TOP", "ETCH/TOP"],
                          [OUTSIDE[0], OUTSIDE[1], 0.0, False, "SMD", "ETCH/TOP", "ETCH/TOP"]],
                 # copper under drawn openings: one inside W, one across W's
                 # edge at x = 14, half of it in S2, and one in S2 drawn up to
                 # that edge - a vertex on it is at home on either side
                 "exposed": {"top": [square(5.75, 3.75, 6.25, 4.25), square(13.5, 6.0, 14.5, 7.0),
                                     square(14.0, 4.0, 15.0, 5.0)],
                             "bottom": []},
                 "bare": {"top": [], "bottom": []}}


pads_res, pads_logs, pads_shape = build(board("pads", change=with_pads), exposed_copper=True,
                                        mask_openings=True)
check("both pins' copper is placed", pads_res.pads_placed == 2, pads_res.pads_placed)
check("one mask window, S2's: W's stack has no soldermask", pads_res.openings_placed == 1,
      pads_res.openings_placed)
flat = []                          # (x, y, z) of every face the build wrote outside the board solid
exp = TopExp_Explorer(pads_shape, TopAbs_FACE, TopAbs_SOLID)
while exp.More():
    box = Bnd_Box()
    BRepBndLib.Add_s(exp.Current(), box, False)
    x0, y0, z0, x1, y1, z1 = box.Get()
    if z1 - z0 < 1e-6:
        flat.append(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    exp.Next()
copper_in_w = sorted(round(fz, 6) for fx, fy, fz in flat if abs(fx - INSIDE[0]) < 1e-3 and abs(fy - INSIDE[1]) < 1e-3)
check("the pin in W: its copper three clearances above W's top",
      copper_in_w and near(copper_in_w[-1], levels["W"][0] + 3 * H), (copper_in_w, levels["W"][0]))
check("the drawn opening inside W is left out, the one across W's edge clipped to what is S2's, "
      "and the one drawn up to the edge built whole",
      any(m.startswith("copper_top: the mask is only on S2 - 1 drawn-opening polygon(s) clipped to it, "
                       "1 reach it with nothing inside it") for m in pads_logs),
      [m for m in pads_logs if "drawn-opening" in m])
bare = P._Zones(stack.zones, stack.stackups, levels, stack.board_top_z, stack.board_bottom_z, None)
check("without a surface the pads' own lookup gives W's faces in W", bare.at(*INSIDE)[1] == levels["W"],
      (bare.at(*INSIDE), levels["W"]))
check("and W's mask, which is none", bare.mask_at(*INSIDE, "top") == (False, {"W"}),
      bare.mask_at(*INSIDE, "top"))

print("\n[7] the legend: W carries none, so nothing of it is printed on W")


def glyph(cx, cy):
    return {"layer": "REF DES/SILKSCREEN_TOP",
            "vertices": [[cx - 0.5, cy - 0.5, 0], [cx + 0.5, cy - 0.5, 0], [cx + 0.5, cy + 0.5, 0],
                         [cx - 0.5, cy + 0.5, 0]]}


printed = json.loads(json.dumps(stack.stackups))
printed["STIFFENER2"]["silkscreen"] = {"top": True, "bottom": True}
printed["FLEX"]["silkscreen"] = {"top": False, "bottom": False}
in_w, beside = glyph(*INSIDE), glyph(*OUTSIDE)
said_silk = []
kept = core.clip_silk_to_zones([in_w, beside], printed, stack.zones, "top", said_silk.append)
check("the glyph in W goes, the one beside it in S2 stays", kept == [beside], len(kept))
check("and the log names W", any("W carries no silkscreen" in m for m in said_silk), said_silk)
printed["STIFFENER2"]["silkscreen"] = {"top": False, "bottom": False}
said_bare = []
core.clip_silk_to_zones([in_w, beside], printed, stack.zones, "top", said_bare.append)
check("with S2 bare as well, the glyph in W is still W's to leave out, not S2's",
      any("S2 carries no silkscreen in its stackup (1)" in m and "W carries no silkscreen in its stackup (1)" in m
          for m in said_bare), said_bare)

print("\n[8] a bend in W is curled about W's stack, and S2 is the zone of another stack in its strip")


def with_bend(d):
    d["bends"].append({"name": "B2", "line": {"start": [0.0, 5.0], "end": [16.0, 5.0]},
                       "inner_radius": 0.5, "width": 0.7854,
                       "info": "TYPE=CircularBend, INNER_SIDE=TOP, INNER_ANGLE=90.0000, "
                               "INNER_RADIUS=0.5000 MILLIMETERS, ORDER=0"})


bent = board("bent", change=with_bend)
bent_stack = prepare(bent)
plan = core._plan_fold(bent, bent_stack, BuildOptions(), lambda m: None)
b2 = next((s for s in (plan.strips if plan else []) if s.bend.name == "B2"), None)
check("B2's axis is the radius above W's stack, not above S2's stiffener",
      b2 is not None and near(b2.axis_z, bent_stack.fold_levels["W"][0] + 0.5),
      (b2.axis_z if b2 else None, bent_stack.fold_levels["W"][0] + 0.5, bent_stack.fold_levels["S2"][0] + 0.5))
crooked = sorted({c.zone for c in (plan.crooked if plan else []) if c.bend == "B2"})
check("the strip lies mostly on W, and S2 is named as the zone of another stack in it", crooked == ["S2"],
      crooked)


def empty_stiffener(d):
    with_bend(d)
    for layer in d["stackups"]["STIFFENER2"]["layers"]:
        if layer["name"] == "STIFFENER_TOP2":
            layer["shapes"] = [{"outline": rect(30.0, 20.0, 35.0, 25.0)}]       # outside S2
            layer["negative"] = False


noted = []
quiet = board("quiet", change=empty_stiffener)
quiet_stack = prepare(quiet, noted)
core._plan_fold(quiet, quiet_stack, BuildOptions(), noted.append)
check("a bend whose middle is in W is not noted for S2's empty stiffener",
      not any("B2" in m and "zone S2" in m for m in noted), [m for m in noted if "B2" in m])

print("\n[9] a layer whose material lies only inside W holds none in S2")


def stiffener_in_w(d):
    for layer in d["stackups"]["STIFFENER2"]["layers"]:
        if layer["name"] == "STIFFENER_TOP2":
            layer["shapes"] = [{"outline": rect(5.0, 4.0, 11.0, 7.0)}]           # inside W
            layer["negative"] = False


_res, lost_logs, lost_shape = build(board("lost", change=stiffener_in_w))
check("S2's line names its stiffener as holding no material in it",
      any(m.startswith("  S2 (STIFFENER2)") and "STIFFENER_TOP2" in m for m in lost_logs),
      [m for m in lost_logs if m.startswith("  S2")])
lost_body = max(solids_of(lost_shape), key=lambda s: volume(s))
check("and no stiffener is built in W, where W's stack has none",
      near(faces_of_body(lost_body, 8.0, 5.5)[0], prepare(board("lost", change=stiffener_in_w)).levels["W"][0]),
      faces_of_body(lost_body, 8.0, 5.5))

print("\n[10] a file without stackup layers: one prism per zone, W's cut out of S2's")
PROF = {"FLEX": (0.075, 0.215, 0.075), "STIFFENER2": (2.125, 0.215, 0.100)}
prisms = {"format": "simple3d", "format_version": 5, "name": "prisms", "components": {},
          "pcb": {"thickness": {"soldermask_top": 0.0, "board": 0.365, "soldermask_bottom": 0.0},
                  "color": BASE["pcb"]["color"], "edges": [rect(0, 0, 41, 26.5)]},
          "zones": [{"name": n, "stackup": s, "above": PROF[s][0], "core": PROF[s][1], "below": PROF[s][2],
                     "contour": c} for n, s, c in (("S2", "STIFFENER2", rect(0, 0, 16, 11.38)),
                                                   ("F2", "FLEX", rect(0, 11.38, 41, 26.5)),
                                                   ("W", "FLEX", W_RECT))]}
_res, _l, prism_shape = build(prisms)
want_prisms = 16 * 11.38 * 2.44 + 41 * 15.12 * 0.365 - W_AREA * (2.44 - 0.365)
check(f"volume {volume(prism_shape):.4f} = S2 less W's area at its own thickness {want_prisms:.4f}",
      abs(volume(prism_shape) - want_prisms) <= 1e-6 * want_prisms, (volume(prism_shape), want_prisms))

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)
