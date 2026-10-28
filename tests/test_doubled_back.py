# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, out_dir, fails, check, read_step, volume

"""An outline that runs back over its own track (round 106).

flex2-a0's FLEX zone runs up the board circle from 223.6 to 210.2 degrees and
turns back down it - 1.50 mm walked twice, the legs 0.044 um apart - and
OCCT's mesher covered the face with a 26.25 mm2 triangle outside the board:
the wedge on the owner's step2html page of 28.10.2026. flex3-a0 and flex-b2
have such spikes too. contour.drop_doubled_back leaves the doubled stretch
out, and core.generate runs every outline the body is built from through it.

None of the owner's data is in here. The arcs of [2] are made up with the same
shape of fault: a disc of r 6.4 on a 6.5 mm strip with r 5 fillets, the zone
outline running up the circle past the left fillet and back, its legs on
circles 0.02 um either side of the disc's.
"""
import json
import math
import sys

from stepbuilder import core
from stepbuilder.contour import (build_contour, contour_points, drop_doubled_back,
                                 polygon_area)
from OCP.BRep import BRep_Tool
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_FACE, TopAbs_OUT
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.gp import gp_Pnt2d

OUT = out_dir("doubled_back")


def seg(p, q):
    return {"type": "segment", "start": [p[0], p[1]], "end": [q[0], q[1]]}


def arc(p, q, r, ccw):
    """The short arc of radius r from p to q, turning left (ccw) or right, read
    the round-63 way: alpha..beta bound it, ccw says the contour enters at
    alpha."""
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    dx, dy = q[0] - p[0], q[1] - p[1]
    half = math.hypot(dx, dy) / 2
    h = math.sqrt(max(r * r - half * half, 0.0))
    nx, ny = -dy / (2 * half), dx / (2 * half)          # left of p -> q
    s = 1.0 if ccw else -1.0
    c = (mx + s * h * nx, my + s * h * ny)
    ang = lambda t: math.degrees(math.atan2(t[1] - c[1], t[0] - c[0])) % 360.0
    return {"type": "arc", "center": [c[0], c[1]], "radius": r,
            "alpha": ang(p) if ccw else ang(q), "beta": ang(q) if ccw else ang(p), "ccw": ccw}


def area_of(contour):
    return polygon_area(contour_points(contour, 64))


def face_of(contour):
    return BRepBuilderAPI_MakeFace(build_contour(contour), True).Face()


def meshed(face, deflection):
    """-> (face area, mesh area, mesh area outside the face): every triangle's
    centroid classified in the face's own UV, as the wedge was found."""
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    BRepMesh_IncrementalMesh(face, deflection, False, math.radians(15.0), True)
    tri = BRep_Tool.Triangulation_s(face, TopLoc_Location())
    total = outside = 0.0
    for t in range(1, (tri.NbTriangles() if tri is not None else 0) + 1):
        n = tri.Triangle(t).Get()
        p = [tri.Node(i) for i in n]
        uv = [tri.UVNode(i) for i in n]
        a = 0.5 * abs((p[1].X() - p[0].X()) * (p[2].Y() - p[0].Y())
                      - (p[1].Y() - p[0].Y()) * (p[2].X() - p[0].X()))
        total += a
        centre = gp_Pnt2d(sum(q.X() for q in uv) / 3, sum(q.Y() for q in uv) / 3)
        if BRepClass_FaceClassifier(face, centre, 1e-7).State() == TopAbs_OUT:
            outside += a
    return props.Mass(), total, outside


def closes(contour) -> bool:
    """Does the contour stitch into one closed wire, as the builder needs it?"""
    try:
        return not build_contour(contour).IsNull()
    except core.StepBuilderError:
        return False


def faces_in(shape):
    exp, n = TopExp_Explorer(shape, TopAbs_FACE), 0
    while exp.More():
        n += 1
        exp.Next()
    return n


print("\n[1] segments: what is dropped and what is left alone")
SQUARE = [seg((0, 0), (10, 0)), seg((10, 0), (10, 5)), seg((10, 5), (10, 10)),
          seg((10, 10), (0, 10)), seg((0, 10), (0, 0))]
# Out from (10, 5) to (13, 5) and straight back: three millimetres walked twice.
SPIKED = SQUARE[:2] + [seg((10, 5), (13, 5)), seg((13, 5), (10, 5))] + SQUARE[2:]
new, turns = drop_doubled_back(SPIKED)
check("the spike is found once", len(turns) == 1, turns)
check("at its tip, (13, 5), 3 mm walked twice",
      turns and math.hypot(turns[0][0][0] - 13, turns[0][0][1] - 5) < 1e-9
      and abs(turns[0][1] - 3.0) < 1e-9, turns)
check("and what is left is the square, primitive for primitive", new == SQUARE, new)
check("the region is the same: 100 mm2 before and after",
      abs(area_of(SPIKED) - 100) < 1e-9 and abs(area_of(new) - 100) < 1e-9)

# The list is a loop: a spike across its first and last primitive is the same spike.
rolled = SPIKED[3:] + SPIKED[:3]
new, turns = drop_doubled_back(rolled)
check("a spike across the list's end is found too",
      len(turns) == 1 and abs(turns[0][1] - 3.0) < 1e-9, turns)
check("and leaves the same square", sorted(map(json.dumps, new)) == sorted(map(json.dumps, SQUARE)), new)

# The way back 0.4 um off the way out, as Allegro's numbers are: still one track.
offset = SQUARE[:2] + [seg((10, 5), (13, 5)), seg((13, 5), (10, 5.0000004)),
                       seg((10, 5.0000004), (10, 10))] + SQUARE[3:]
new, turns = drop_doubled_back(offset)
check("legs 0.4 um apart are one track", len(turns) == 1 and len(new) == 5, (turns, new))
check("and the joint they leave closes into a wire",
      abs(polygon_area(contour_points(new)) - 100) < 1e-5 and closes(new))

# 0.05 um off is still one track, but further apart than the wire is stitched
# at (1e-5 mm): a segment has to span what the cut leaves, as on the boards.
wide = SQUARE[:2] + [seg((10, 5), (13, 5)), seg((13, 5), (10, 5.00005)),
                     seg((10, 5.00005), (10, 10))] + SQUARE[3:]
new, turns = drop_doubled_back(wide)
check("legs 0.05 um apart are one track too", len(turns) == 1, turns)
check("and a segment spans the 0.05 um the cut leaves, so the wire closes",
      len(new) == 6 and seg((10, 5), (10, 5.00005)) in new and closes(new), new)

# A notch with width - 0.1 mm across its mouth, 3 mm deep - is a shape, not a slip.
NOTCH = SQUARE[:2] + [seg((10, 5), (13, 5.05)), seg((13, 5.05), (10, 5.1)),
                      seg((10, 5.1), (10, 10))] + SQUARE[3:]
new, turns = drop_doubled_back(NOTCH)
check("a narrow notch with width is left alone", not turns and new is NOTCH, turns)
check("so is a square with nothing to drop - the very same list",
      drop_doubled_back(SQUARE) == (SQUARE, []) and drop_doubled_back(SQUARE)[0] is SQUARE)
TRACK = [seg((0, 0), (5, 0)), seg((5, 0), (2, 0)), seg((2, 0), (0, 0))]
new, turns = drop_doubled_back(TRACK)
check("an outline that is nothing but a doubled track keeps it: no region to keep",
      not turns and new is TRACK, (turns, new))
CIRCLE = [{"type": "circle", "x": 0.0, "y": 0.0, "radius": 1.0}]
check("a circle is left alone", drop_doubled_back(CIRCLE)[0] is CIRCLE)

print("\n[2] arcs: the shape of flex2-a0's fault, made up")
R, RF, HW = 6.4, 5.0, 3.25                  # the disc, the fillets, half the strip


def on_disc(deg, r=R):
    a = math.radians(deg)
    return (r * math.cos(a), r * math.sin(a))


yf = -math.sqrt((R + RF) ** 2 - (HW + RF) ** 2)
fillet_deg = math.degrees(math.atan2(-yf, HW + RF))
tl, tr = on_disc(180 + fillet_deg), on_disc(360 - fillet_deg)     # the fillets meet the disc
el, er = (-HW, yf), (HW, yf)                                      # ... and the strip
tip, back, back2 = on_disc(210.17), on_disc(217.87), on_disc(217.99)
TAIL = [arc(tr, er, RF, False), seg(er, (HW, -30.0)), seg((HW, -30.0), (-HW, -30.0)),
        seg((-HW, -30.0), el), arc(el, tl, RF, False)]
CLEAN = [arc(tl, tr, R, True)] + TAIL
# Up the circle on one leg, down on another, a 0.01 mm piece of fillet, then on
# along the disc: the four arcs flex2-a0's zone begins with.
SPIKY = [arc(tl, tip, R + 2e-5, False), arc(tip, back, R - 2e-5, True),
         arc(back, back2, RF, False), arc(back2, tr, R, True)] + TAIL

wedge = max(meshed(face_of(SPIKY), d)[2] for d in (0.0272, 0.0136, 0.0068))
check("the bug's path: the raw outline meshes outside its own face", wedge > 0.05,
      f"{wedge:.4f} mm2 outside - this OCCT meshes the spike, and the checks below prove less")

new, turns = drop_doubled_back(SPIKY)
walked = R * math.radians(180 + fillet_deg - 210.17)
check("one turn, at the top of the spike", len(turns) == 1
      and math.hypot(turns[0][0][0] - tip[0], turns[0][0][1] - tip[1]) < 1e-4, turns)
check(f"{walked:.4f} mm walked twice", turns and abs(turns[0][1] - walked) < 1e-3, turns)
circles = {(tuple(p["center"]), p["radius"]) for p in SPIKY if p["type"] == "arc"}
kept = {(tuple(p["center"]), p["radius"]) for p in new if p["type"] == "arc"}
check("every arc left stays on a circle the outline already had, number for number",
      kept <= circles, kept - circles)
clean_area = meshed(face_of(CLEAN), 0.0272)[0]
for d in (0.0272, 0.0136, 0.0068):
    face = face_of(new)
    area, _mesh, outside = meshed(face, d)
    check(f"at {d} mm: nothing meshed outside the face", outside < 1e-6, f"{outside:.6f} mm2")
check("the face is valid and as big as the outline without the spike",
      BRepCheck_Analyzer(face_of(new)).IsValid() and abs(area - clean_area) < 1e-6,
      f"{area:.6f} against {clean_area:.6f}")

print("\n[3] the intermediate: every outline of the body, said once, the file untouched")
log = []
data = {"name": "spikes",
        "pcb": {"edges": [SPIKED, CIRCLE, rolled]},
        "zones": [{"name": "Z1", "stackup": "S", "contour": SPIKY},
                  {"name": "Z2", "stackup": "S", "contour": SQUARE}],
        "stackups": {"S": {"layers": [{"name": "STIFF", "shapes": [
                         {"outline": SPIKED, "voids": [rolled]}]},
                                      {"name": "CORE", "shapes": None}]},
                     "T": {"layers": [{"name": "STIFF", "shapes": [
                         {"outline": SPIKED, "voids": [rolled]}]}]}}}
before = json.dumps(data, sort_keys=True)
got = core._without_doubled_tracks(data, log.append)
check("the dict that was read is not touched", json.dumps(data, sort_keys=True) == before)
check("every outline of the body comes back without its spike",
      all(not drop_doubled_back(c)[1] for c in
          got["pcb"]["edges"] + [z["contour"] for z in got["zones"]]
          + [s["outline"] for st in got["stackups"].values() for layer in st["layers"]
             for s in (layer["shapes"] or [])]
          + [v for st in got["stackups"].values() for layer in st["layers"]
             for s in (layer["shapes"] or []) for v in s.get("voids", [])]))
check("an outline with nothing to drop is the very same list",
      got["pcb"]["edges"][1] is CIRCLE and got["zones"][1]["contour"] is SQUARE)
where = [line.split(":")[1].strip() for line in log]
check("one warning each, naming the place",
      where == ["the board outline", "cutout 2", "zone Z1", "layer STIFF shape 1",
                "layer STIFF shape 1, void 1"], where)
check("with the turn and the length, and what to do about it",
      log and "turns at (13.000, 5.000) and runs 3.000 mm back along itself" in log[0]
      and log[0].startswith("warning:") and "Allegro" in log[0], log[:1])
quiet = []
plain = {"name": "plain", "pcb": {"edges": [SQUARE]}, "zones": [{"name": "Z", "contour": SQUARE}]}
check("a board with nothing to drop builds from the very dict it was read into, in silence",
      core._without_doubled_tracks(plain, quiet.append) is plain and not quiet, quiet)

print("\n[4] a build: the rigid-flex fixture with a spike in its flex zone")
rf = json.loads((ROOT / "tests/fixtures/rigidflex.json").read_text(encoding="utf-8"))
spiky = json.loads(json.dumps(rf))
f2 = next(z for z in spiky["zones"] if z["name"] == "F2")
# Down the board's left edge past the flex zone's corner, into the stiffener's
# side, and back up - as flex2-a0's zone runs along its circle.
check("the fixture's flex zone ends on the left edge, going down to (0, 11.38)",
      f2["contour"][-1] == {"type": "segment", "start": [0, 26.5], "end": [0, 11.38]},
      f2["contour"][-1])
f2["contour"][-1:] = [seg((0, 26.5), (0, 8.0)), seg((0, 8.0), (0, 11.38))]
(OUT / "rigidflex_spiky.json").write_text(json.dumps(spiky), encoding="utf-8")
for fold in (False, True):
    view = "folded" if fold else "flat"
    built = {}
    for name, path in (("clean", ROOT / "tests/fixtures/rigidflex.json"),
                       ("spiky", OUT / "rigidflex_spiky.json")):
        lines = []
        res = core.generate(step_dir=ROOT / "demo/step_files", json_file=path, output_dir=OUT,
                            output_name=f"{name}_{view}", fold_bends=fold, log=lines.append)
        shape = read_step(res.output)
        # The lines that name the files differ by name alone.
        lines = [line for line in lines if path.name not in line and res.output.name not in line]
        built[name] = (volume(shape), faces_in(shape), lines)
    (vc, fc, lc), (vs, fs, ls) = built["clean"], built["spiky"]
    said = [line for line in ls if "back along itself" in line]
    check(f"{view}: the build says so, once, for zone F2 at (0.000, 8.000)",
          len(said) == 1 and said[0].startswith("warning: zone F2: the outline turns at "
                                                "(0.000, 8.000) and runs 3.380 mm"), said)
    check(f"{view}: and builds the board the clean fixture builds - "
          f"{vc:.4f} mm3 in {fc} faces", abs(vs - vc) < 1e-6 and fs == fc,
          f"{vs:.6f} mm3 in {fs} faces")
    check(f"{view}: nothing else in the log changes",
          [line for line in ls if line not in said] == lc,
          ([line for line in ls if line not in lc][:3], [line for line in lc if line not in ls][:3]))

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
