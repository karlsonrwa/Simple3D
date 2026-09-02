"""The silkscreen legend: from the exporter's polygons to solids (or flat
faces) on the board, with the arc convention worked out from the board's
own areas.

A legend polygon arrives as vertices with a radius per edge, and three
things about that radius are ambiguous in the documentation - which side
the arc bulges to, what a positive radius means, and which of two radii
closes the polygon. `_pick_convention` settles it by measurement: the
exporter also writes Allegro's own area for each polygon, and the reading
that reproduces those areas wins (the known-right one is tried first). Then
`build_silkscreen` builds every polygon, merges what is coplanar, and
`clip_silk_to_zones` leaves out what lies on a zone whose stackup carries
no legend. Round 73, plan A5: moved verbatim out of core.py.
"""

from __future__ import annotations

import math
from typing import Iterable

from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.GC import GC_MakeArcOfCircle
from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
from OCP.TopTools import TopTools_HSequenceOfShape
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Wire
from OCP.gp import gp_Pnt, gp_Vec

from .contour import WIRE_TOLERANCE, _face_from_wires, _open_wire_detail, build_contour, contour_points, point_in_polygon
from .errors import StepBuilderError
from .reporting import LogFn, _noop_log


# --------------------------------------------------------------------------- #
# silkscreen
# --------------------------------------------------------------------------- #

# Fallback ink thickness (mm) when the JSON does not carry one. 25 um is a
# typical cured screen-printed legend; the SKILL side normally supplies it from
# simple3d_config.json.
DEFAULT_SILK_THICKNESS = 0.025

# How far a FLAT legend is lifted off the board face, in mm. It is not ink
# thickness - a flat legend has none - it exists only so the two faces are not
# coplanar: coincident planes flicker against each other in any viewer that
# resolves depth per pixel, which is what happens with a legend lying exactly on
# the board. 1 um is invisible at board scale; raise it (0.005-0.01) if a
# particular viewer's depth buffer still cannot separate them.
DEFAULT_FLAT_HEIGHT = 0.001


# How a polygon's vertex list is read. Allegro gives (x, y, signed_radius) per
# point, and three things about it are ambiguous in the documentation:
#
#   rule - what the sign is measured against. The sentence is "The sign of the
#       radius indicates for postive the arc is to the left of the y-axis".
#       TRAVEL reads it as the arc bulging left of the direction of travel.
#       AXIS takes "the y-axis" literally: the vertical through the arc's own
#       centre, so the sign says which side of its centre the arc sits on. The
#       neighbouring sentence - polygon arcs never cross a quadrant, and
#       quadrants are measured from the centre - is what makes AXIS coherent.
#       The two rules disagree exactly where a shape doubles back: the two round
#       ends of one stroke get the SAME sign under TRAVEL and OPPOSITE signs
#       under AXIS, which is why reading it wrong leaves one end correct and
#       turns the other inside out.
#   polarity - whether a positive radius means the first side or the second.
#   first_radius_closes - each vertex carries the radius of the edge REACHING
#       it, and the list does not repeat its first point, so the first vertex's
#       radius either describes the closing edge back to it or is unused.
#
# Rather than pick and hope, every combination is tried against the area Allegro
# reported for those same polygons; whichever reproduces them wins.
# See _pick_convention.
RULE_TRAVEL = "travel"
RULE_AXIS = "axis"

_Convention = tuple  # (rule: str, positive_is_first: bool, first_radius_closes: bool)

# MEASURED on a real board (Allegro 24.1, 2026-07-22): the reading Allegro
# actually uses is AXIS / positive-sits-left / first-radius-closes. Scored
# against that board's own polygon areas it lands at 0.0004% (top) and 0.0000%
# (bottom), while every other reading is off by 1.3% to 677%. It is listed
# first so that a legend of nothing but straight lines - where every reading is
# equivalent and the scores tie - still resolves to the one known to be right.
#
# The search is kept rather than hard-coding it: it costs one pass over a
# handful of small polygons, it is what established this in the first place,
# and it will say so in the log if another Allegro version disagrees.
_CONVENTIONS: list[_Convention] = [
    (RULE_AXIS, True, True),
] + [
    (rule, polarity, closes)
    for rule in (RULE_AXIS, RULE_TRAVEL)
    for polarity in (True, False)
    for closes in (True, False)
    if (rule, polarity, closes) != (RULE_AXIS, True, True)
]


def _describe_convention(convention: _Convention) -> str:
    rule, polarity, closes = convention
    if rule == RULE_TRAVEL:
        side = "bulges left" if polarity else "bulges right"
        what = f"positive radius {side} of travel"
    else:
        side = "left" if polarity else "right"
        what = f"positive radius means the arc sits {side} of its centre"
    return f"{what}, first radius {'closes' if closes else 'unused'}"

# A rebuilt polygon has to land this close to Allegro's own area to be accepted.
# Loose enough for float noise and OCCT's own tolerance, tight enough that a
# wrong arc side (several percent even on gentle curves) never slips through.
AREA_TOLERANCE = 0.005


def _arc_geometry(p0, p1, radius: float):
    """Chord bookkeeping shared by both readings.

    Returns (mx, my, nx, ny, rad, h) where (nx, ny) is the left normal of
    travel and h is the centre's distance from the chord midpoint. The two
    candidate centres are (mx, my) +/- h * (nx, ny), and the arc bulging to the
    LEFT of travel is the one whose centre sits to the right, and vice versa.
    """
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    chord = math.hypot(dx, dy)
    if chord < 1.0e-12:
        return None
    # A radius smaller than half the chord cannot span it (rounding in the
    # source); clamp to the semicircle instead of taking a negative sqrt.
    rad = max(abs(radius), chord / 2.0)
    h = math.sqrt(max(0.0, rad * rad - (chord / 2.0) ** 2))
    mx, my = (p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0
    return mx, my, -dy / chord, dx / chord, rad, h


def _arc_bulges_left(p0, p1, radius: float, rule: str, positive_is_first: bool) -> bool:
    """Which side of travel this arc bulges to, under the given reading."""
    positive = radius > 0.0
    if rule == RULE_TRAVEL:
        return positive == positive_is_first

    # AXIS: the sign says which side of the vertical through its own centre the
    # arc sits on. For the candidate that bulges LEFT, the arc's midpoint is one
    # radius from the centre along the left normal, so its offset in x is simply
    # rad * nx - the arc sits left of its own centre exactly when nx < 0.
    #
    # nx == 0 would mean a chord with no rise, which inside a single quadrant
    # only happens for a zero-length arc; the guard is there for arithmetic
    # safety, not for a case that occurs.
    geometry = _arc_geometry(p0, p1, radius)
    if geometry is None:
        return positive == positive_is_first
    _, _, nx, _, _, _ = geometry
    if abs(nx) < 1.0e-12:
        return positive == positive_is_first

    left_candidate_sits_left = nx < 0.0
    wants_left_of_centre = positive == positive_is_first
    return left_candidate_sits_left == wants_left_of_centre


def _arc_edge(p0, p1, radius: float, z: float, arc_left: bool):
    """Edge for an arc from p0 to p1 whose chord is `radius` away from centre.

    Built through three points - start, arc midpoint, end - so there is no
    angle bookkeeping and no sense flag to get backwards. Polygon arcs never
    cross a quadrant, so every one of them is a minor arc and the midpoint is
    unambiguous: it sits (radius - h) off the chord, on the side the arc bulges.
    """
    geometry = _arc_geometry(p0, p1, radius)
    if geometry is None:
        return None
    mx, my, nx, ny, rad, h = geometry
    sign = 1.0 if arc_left else -1.0
    mid = gp_Pnt(mx + sign * (rad - h) * nx, my + sign * (rad - h) * ny, z)

    arc = GC_MakeArcOfCircle(
        gp_Pnt(p0[0], p0[1], z), mid, gp_Pnt(p1[0], p1[1], z)
    ).Value()
    return BRepBuilderAPI_MakeEdge(arc).Edge()


def _wire_from_vertices(vertices: list, z: float, convention: _Convention) -> TopoDS_Wire:
    """Allegro vertex list -> closed wire, read under *convention*."""
    rule, positive_is_first, first_radius_closes = convention

    points = [(float(v[0]), float(v[1])) for v in vertices]
    radii = [float(v[2]) if len(v) > 2 else 0.0 for v in vertices]
    if len(points) < 2:
        raise StepBuilderError("polygon has fewer than two vertices")

    def make(p0, p1, radius):
        if abs(radius) > 1.0e-9:
            left = _arc_bulges_left(p0, p1, radius, rule, positive_is_first)
            return _arc_edge(p0, p1, radius, z, left)
        if math.dist(p0, p1) < 1.0e-12:
            return None
        return BRepBuilderAPI_MakeEdge(
            gp_Pnt(p0[0], p0[1], z), gp_Pnt(p1[0], p1[1], z)
        ).Edge()

    edges = []
    for i in range(1, len(points)):
        edge = make(points[i - 1], points[i], radii[i])
        if edge is not None:
            edges.append(edge)

    # The list does not repeat its first point, so the closing edge is ours to
    # add. If a list ever does repeat it, the distance test skips this and the
    # closing edge's radius was already consumed by the loop above.
    if math.dist(points[-1], points[0]) > 1.0e-9:
        edge = make(points[-1], points[0], radii[0] if first_radius_closes else 0.0)
        if edge is not None:
            edges.append(edge)

    if not edges:
        raise StepBuilderError("polygon produced no edges")

    edge_seq = TopTools_HSequenceOfShape()
    for edge in edges:
        edge_seq.Append(edge)
    wires = TopTools_HSequenceOfShape()
    ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(edge_seq, WIRE_TOLERANCE, False, wires)

    if wires.Length() != 1:
        raise StepBuilderError(
            f"polygon edges formed {wires.Length()} wires, expected 1"
        )
    wire = TopoDS.Wire_s(wires.Value(1))
    if not wire.Closed():
        raise StepBuilderError("polygon contour is open" + _open_wire_detail(wire))
    return wire


def _silk_face(polygon: dict, z: float, convention: _Convention):
    """One silkscreen polygon (vertex form, or the older primitive form)."""
    if "vertices" in polygon:
        outer = _wire_from_vertices(polygon["vertices"], z, convention)
        inner = [_wire_from_vertices(h, z, convention)
                 for h in polygon.get("holes", [])]
    else:
        # format_version 2.0 wrote pre-built segment/arc primitives.
        outer = build_contour(polygon["outline"], z)
        inner = [build_contour(h, z) for h in polygon.get("holes", [])]
    return _face_from_wires(outer, inner)


def _pick_convention(
    polygons: list[dict], z: float, log: LogFn, side: str
) -> _Convention:
    """Choose the vertex reading that reproduces Allegro's reported areas.

    Scored over the polygons that declare an area, worst-case first: the right
    convention matches every one of them, a wrong one is off on any polygon with
    a curve in it. Ties (a legend of nothing but straight lines, where the
    readings cannot differ) fall through to the first convention, which is then
    as good as any.
    """
    candidates = [p for p in polygons if p.get("vertices") and p.get("area")
                  and abs(float(p["area"])) > 1.0e-6]
    # Only polygons that actually contain an arc can tell the readings apart, and
    # the cheapest ones say it just as clearly, so sample small arc-bearing
    # polygons. A legend of nothing but straight lines leaves every reading
    # equivalent, and then the first is as good as any.
    curved = [p for p in candidates
              if any(abs(float(v[2])) > 1.0e-9 for v in p["vertices"] if len(v) > 2)]
    sample = sorted(curved or candidates, key=lambda p: len(p["vertices"]))[:8]
    if not sample:
        return _CONVENTIONS[0]

    scores: list[tuple[float, _Convention]] = []
    for convention in _CONVENTIONS:
        worst = 0.0
        for polygon in sample:
            declared = abs(float(polygon["area"]))
            try:
                area = _face_area(_silk_face(polygon, z, convention))
            except (StepBuilderError, RuntimeError, TypeError):
                area = None
            if area is None:
                worst = math.inf
                break
            worst = max(worst, abs(area - declared) / declared)
        scores.append((worst, convention))

    # Every candidate is scored - no early exit. Two readings can both land
    # inside the tolerance on a gently curved sample while only one is right,
    # and taking the first to pass would then pick by list order.
    best_error, best = min(scores, key=lambda s: s[0])

    if best_error > AREA_TOLERANCE:
        log(f"warning: no reading of the {side} vertex data reproduces the areas "
            f"Allegro reported (best is off by {best_error * 100:.1f}%: "
            f"{_describe_convention(best)}). The legend geometry may be distorted.")
    return best


def build_silkscreen(
    polygons: Iterable[dict],
    z: float,
    thickness: float,
    log: LogFn = _noop_log,
    side: str = "",
    flat: bool = False,
    flat_offset: float = 0.0,
) -> tuple[TopoDS_Compound | None, int, int]:
    """Extrude one side's silkscreen polygons into a compound of thin solids.

    Returns (compound, built, skipped). *thickness* is signed: positive extrudes
    upwards (top side), negative downwards (bottom side).

    The solids are deliberately NOT fused. Silkscreen is thousands of
    overlapping strokes and glyphs, and a boolean union of that many thin
    prisms is minutes of OCCT time with a real chance of failing outright,
    while the union buys nothing: the result is one label, one color, and it
    renders and exports identically. What it costs is that the compound is not
    a single manifold solid, which matters only if someone means to do
    downstream boolean work on the ink itself.

    A polygon that cannot be built is counted and skipped rather than taken as
    fatal - one malformed glyph must not cost the whole board.

    flat=True writes each polygon as a single planar face instead of a prism.
    Measured on a 150-polygon legend: 566 kB against 2191 kB, so about a
    quarter of the size. A prism costs V+2 faces for a V-vertex polygon (top,
    bottom and one wall per edge); a face costs one. What is given up is that
    the ink is then a surface, not a solid: it has no thickness to measure and
    nothing downstream can do boolean work with it.

    flat_offset lifts the flat face off the board face by that much, signed the
    same way as thickness. Coincident planes do flicker in a viewer that
    resolves depth per pixel - confirmed on a real board - so the default is a
    micron of clearance rather than a true zero. See DEFAULT_FLAT_HEIGHT.

    Fusing the prisms was measured too, and made the file LARGER (3377 kB,
    154%): a boolean union replaces analytic cylinders and planes with general
    surfaces, and after clipping the strokes barely overlap, so there is little
    interior geometry for it to remove. Not offered.
    """
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)

    polygons = list(polygons)
    convention = _pick_convention(polygons, z, log, side)

    shapes: list = []
    built = 0
    skipped = 0
    first_error: str | None = None
    area_checked = 0
    area_bad = 0
    worst: tuple[float, float, float] | None = None   # (ratio, declared, got)

    for polygon in polygons:
        if not polygon.get("vertices") and not polygon.get("outline"):
            skipped += 1
            continue
        try:
            # Solid mode builds on the board face and grows the prism away
            # from it. Flat mode has only the face, lifted just clear of the
            # board so the two planes are not coincident.
            face = _silk_face(polygon, z + flat_offset if flat else z, convention)
            shapes.append(
                face if flat
                else BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, thickness)).Shape()
            )
            built += 1
        except (StepBuilderError, RuntimeError, KeyError, TypeError, IndexError) as exc:
            skipped += 1
            if first_error is None:
                first_error = str(exc)
            continue

        # Every polygon is verified, not just the ones that chose the reading:
        # the convention is global, so a single polygon that still disagrees is
        # a polygon whose geometry did not survive, and it should be reported.
        declared = polygon.get("area")
        if declared and abs(declared) > 1.0e-6:
            got = _face_area(face)
            if got is not None:
                area_checked += 1
                ratio = abs(got - abs(declared)) / abs(declared)
                if ratio > AREA_TOLERANCE:
                    area_bad += 1
                    if worst is None or ratio > worst[0]:
                        worst = (ratio, abs(declared), got)

    # Flat faces are unioned before they go into the compound; see
    # _merge_coplanar for why, and why the solid path deliberately does not.
    if flat and len(shapes) > 1:
        merged = _merge_coplanar(shapes, log, side)
        if merged is not None:
            shapes = [merged]

    for shape in shapes:
        builder.Add(compound, shape)

    if skipped:
        log(f"warning: {skipped} {side} silkscreen polygon(s) skipped "
            f"(first: {first_error})")
    if area_bad and worst is not None:
        log(f"warning: {area_bad} of {area_checked} {side} polygons still differ "
            f"from the area Allegro reported (worst: {worst[1]:.6g} vs "
            f"{worst[2]:.6g} mm2, {worst[0] * 100:.1f}%).")
    elif area_checked:
        log(f"{side}: {area_checked} polygon(s) match Allegro's areas "
            f"(arc reading: {_describe_convention(convention)})")
    if not built:
        return None, 0, skipped
    return compound, built, skipped


def _merge_coplanar(faces: list, log: LogFn, side: str):
    """Boolean-union a side's flat faces into one shape, or None if that fails.

    Silkscreen polygons genuinely overlap - a stroke and the glyph beside it,
    two strokes meeting at a junction. As solids that is harmless
    interpenetration. As FLAT faces it is two coincident coplanar faces at the
    same z, which no depth buffer can order, so the overlap renders as a
    flickering blend. Measured on a real board: 5 of 8 candidate pairs overlap
    by real area, 0.16 mm2 double-counted across the side.

    A general fuse makes each overlapping region exist once instead of twice,
    and ShapeUpgrade_UnifySameDomain then merges the coplanar pieces back into
    whole faces. On that board, 117 faces -> 112, 0.08 s, and the STEP came out
    SMALLER (548 kB against 599 kB).

    That is the opposite of fusing the SOLID legend, which was measured at 154%
    of the size and is still not offered: a solid union has to build side walls
    and replaces analytic surfaces with general ones, while a coplanar union of
    faces only removes geometry.
    """
    try:
        from OCP.BRepAlgoAPI import BRepAlgoAPI_BuilderAlgo
        from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
        from OCP.TopTools import TopTools_ListOfShape

        arguments = TopTools_ListOfShape()
        for face in faces:
            arguments.Append(face)
        algo = BRepAlgoAPI_BuilderAlgo()
        algo.SetArguments(arguments)
        algo.SetRunParallel(True)
        algo.Build()
        fused = algo.Shape()
        if fused.IsNull():
            raise StepBuilderError("boolean union produced nothing")

        unify = ShapeUpgrade_UnifySameDomain(fused, True, True, False)
        unify.Build()
        merged = unify.Shape()
        return fused if merged.IsNull() else merged
    except Exception as exc:
        # Not fatal: unmerged faces still draw, they just flicker where they
        # overlap. Losing the legend entirely would be the worse outcome.
        log(f"warning: could not merge the {side} faces ({exc}); overlapping "
            f"areas may flicker. Solid mode does not have this problem.")
        return None


def _face_area(face) -> float | None:
    """Surface area of a face, or None if it cannot be measured."""
    try:
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps

        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        return props.Mass()
    except Exception:
        return None


def _silk_point(polygon: dict) -> tuple[float, float] | None:
    """One point inside a legend polygon - enough to say which zone it is on."""
    verts = polygon.get("vertices")
    if verts:
        pts = [(float(v[0]), float(v[1])) for v in verts if len(v) >= 2]
    else:
        pts = contour_points(polygon.get("outline") or [])
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def clip_silk_to_zones(polygons: list, stackups: dict | None, zones: list | None,
                       side: str, log: LogFn = _noop_log) -> list:
    """The legend polygons that lie on a zone whose stackup is printed.

    A cross section assigns its mask and coating layers PER STACKUP, so a
    rigid-flex board says "no legend on the stiffener zones" exactly by leaving
    the silkscreen layer out of those stackups. That statement used to be lost
    at export - the layer is not body material, so it was dropped and nothing
    remembered it - and the legend was then printed over every zone alike.

    `stackup.silkscreen` carries it now, as `{"top": bool, "bottom": bool}`.
    An intermediate written before that key exists says nothing about it, and
    then nothing is clipped: the legend goes everywhere, exactly as it did.

    *side* is "top" or "bottom".
    """
    if not polygons or not stackups or not zones:
        return polygons
    if not any(isinstance(st.get("silkscreen"), dict) for st in stackups.values()):
        return polygons                    # older intermediate: it cannot say

    printed, bare = [], []
    for zone in zones:
        flag = (stackups.get(str(zone["stackup"])) or {}).get("silkscreen")
        if not isinstance(flag, dict):
            continue
        contour = contour_points(zone.get("contour") or [])
        if not contour:
            continue
        (printed if flag.get(side) else bare).append((str(zone["name"]), contour))

    if not bare:
        return polygons                    # every zone is printed: nothing to do

    kept, dropped, where = [], 0, {}
    for polygon in polygons:
        point = _silk_point(polygon)
        if point is None:
            kept.append(polygon)
            continue
        # On a printed zone wins: a glyph that straddles a boundary belongs to
        # the side of it that has a legend.
        if any(point_in_polygon(point, c) for _, c in printed):
            kept.append(polygon)
            continue
        home = next((n for n, c in bare if point_in_polygon(point, c)), None)
        if home is None:
            kept.append(polygon)           # on no zone at all - leave it be
            continue
        dropped += 1
        where[home] = where.get(home, 0) + 1

    if dropped:
        log(f"{side}: {dropped} legend polygon(s) left out - "
            + ", ".join(f"{n} carries no silkscreen in its stackup ({k})"
                        for n, k in sorted(where.items())))
    return kept
