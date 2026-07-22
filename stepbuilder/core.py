"""
Core logic for building a STEP assembly from the Allegro intermediate JSON.

Port of StepBuilder.cpp (https://github.com/juulsA/exportStep) to Python/OCP.
Contains no UI code: everything reports through callbacks so it can be driven
from the GUI, from the CLI, or from tests.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from OCP.BRep import BRep_Builder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
)
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.GC import GC_MakeArcOfCircle
from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.Interface import Interface_Static
from OCP.Quantity import Quantity_Color, Quantity_TypeOfColor
from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
from OCP.STEPCAFControl import STEPCAFControl_Reader, STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_StepModelType
from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label, TDF_LabelSequence, TDF_Tool
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape, TopoDS_Wire
from OCP.TopTools import TopTools_HSequenceOfShape
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool
from OCP.gp import gp_Ax1, gp_Ax2, gp_Circ, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

# Tolerance used to stitch contour edges into a closed wire.
# Matches the value used by the original C++ implementation.
WIRE_TOLERANCE = 1.0e-5


class StepBuilderError(Exception):
    """Raised for any condition the original code handled with cin.get()."""


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #

LogFn = Callable[[str], None]
ProgressFn = Callable[[int, int], None]


def _noop_log(message: str) -> None:
    pass


def _noop_progress(current: int, total: int) -> None:
    pass


# --------------------------------------------------------------------------- #
# contour geometry
# --------------------------------------------------------------------------- #

def build_contour(contour: Iterable[dict], z_offset: float = 0.0) -> TopoDS_Wire:
    """Turn a list of JSON primitives (segment / arc / circle) into a wire."""
    edges = []

    for segment in contour:
        kind = segment.get("type", "segment")

        if kind == "arc":
            center = gp_Pnt(segment["center"][0], segment["center"][1], z_offset)
            circle = gp_Circ(gp_Ax2(center, gp_Dir(0, 0, 1)), segment["radius"])
            arc = GC_MakeArcOfCircle(
                circle,
                math.radians(segment["alpha"]),
                math.radians(segment["beta"]),
                segment["ccw"],
            ).Value()
            edges.append(BRepBuilderAPI_MakeEdge(arc).Edge())

        elif kind == "circle":
            center = gp_Pnt(segment["x"], segment["y"], z_offset)
            circle = gp_Circ(gp_Ax2(center, gp_Dir(0, 0, 1)), segment["radius"])
            edges.append(BRepBuilderAPI_MakeEdge(circle).Edge())

        elif kind == "segment":
            start = gp_Pnt(segment["start"][0], segment["start"][1], z_offset)
            end = gp_Pnt(segment["end"][0], segment["end"][1], z_offset)
            edges.append(BRepBuilderAPI_MakeEdge(start, end).Edge())

        else:
            raise StepBuilderError(f"Unknown contour primitive: {kind!r}")

    if not edges:
        raise StepBuilderError("Contour contains no primitives")

    edge_seq = TopTools_HSequenceOfShape()
    for edge in edges:
        edge_seq.Append(edge)

    wires = TopTools_HSequenceOfShape()
    ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(
        edge_seq, WIRE_TOLERANCE, False, wires
    )

    if wires.Length() < 1:
        raise StepBuilderError("Could not stitch contour edges into a wire")
    if wires.Length() > 1:
        # The original code silently took wire #1 and dropped the rest, which
        # produces a subtly wrong board. Surfacing it is more useful.
        raise StepBuilderError(
            f"Contour is not closed: edges formed {wires.Length()} separate "
            f"wires (tolerance {WIRE_TOLERANCE}). Check for gaps in the outline."
        )

    wire = TopoDS.Wire_s(wires.Value(1))
    if not wire.Closed():
        # A single but open wire: MakeFace would silently build garbage.
        # Report the actual gap and where it is: a large gap means the source
        # never emitted a closing edge, a tiny one means the tolerance is what
        # needs looking at. Without this the message cannot tell them apart.
        raise StepBuilderError(
            f"Contour is open (start and end do not meet within {WIRE_TOLERANCE})."
            + _open_wire_detail(wire)
        )
    return wire


def _open_wire_detail(wire: TopoDS_Wire) -> str:
    """' Gap 3.81 mm between (x, y) and (x, y).' — best effort, never raises."""
    try:
        from OCP.BRep import BRep_Tool
        from OCP.TopExp import TopExp
        from OCP.TopoDS import TopoDS_Vertex

        v1, v2 = TopoDS_Vertex(), TopoDS_Vertex()
        TopExp.Vertices_s(wire, v1, v2)
        if v1.IsNull() or v2.IsNull():
            return ""
        p1, p2 = BRep_Tool.Pnt_s(v1), BRep_Tool.Pnt_s(v2)
        return (f" Gap {p1.Distance(p2):.6g} between "
                f"({p1.X():.4f}, {p1.Y():.4f}) and ({p2.X():.4f}, {p2.Y():.4f}).")
    except Exception:
        return ""


def make_board_geometry(pcb: dict, thickness: float, z_offset: float = 0.0) -> TopoDS_Shape:
    """Extrude the board outline downwards and cut every hole/cutout out of it.

    edges[0] is the outline; every following contour is a cutout. All cutout
    prisms are collected into one compound and removed with a single boolean
    Cut: the original per-cutout loop was quadratic (every Cut re-processed an
    increasingly complex board) and measured ~11x slower at 120 drill holes.
    """
    contours = pcb["edges"]
    if not contours:
        raise StepBuilderError("pcb.edges is empty")

    # FIX: the C++ version special-cased len==1 and passed the whole array
    # instead of contours[0]. It only worked because the nesting happened to
    # collapse. edges[0] is always the outline.
    wire = build_contour(contours[0], z_offset)
    face = BRepBuilderAPI_MakeFace(wire, True)
    if not face.IsDone():
        raise StepBuilderError("Board outline is not planar or self-intersects")

    direction = gp_Vec(0, 0, -thickness)
    board = BRepPrimAPI_MakePrism(face.Face(), direction).Shape()

    if len(contours) > 1:
        builder = BRep_Builder()
        compound = TopoDS_Compound()
        builder.MakeCompound(compound)
        for i, cutout in enumerate(contours[1:], start=1):
            cut_wire = build_contour(cutout, z_offset)
            cut_face = BRepBuilderAPI_MakeFace(cut_wire, True)
            if not cut_face.IsDone():
                raise StepBuilderError(f"Cutout #{i} is not planar or self-intersects")
            builder.Add(compound, BRepPrimAPI_MakePrism(cut_face.Face(), direction).Shape())

        cut = BRepAlgoAPI_Cut(board, compound)
        if not cut.IsDone():
            raise StepBuilderError("Boolean cut of board cutouts failed")
        board = cut.Shape()
        if board.IsNull():
            raise StepBuilderError("Board geometry is empty after cutting")

    return board


# --------------------------------------------------------------------------- #
# silkscreen
# --------------------------------------------------------------------------- #

# Fallback ink thickness (mm) when the JSON does not carry one. 25 um is a
# typical cured screen-printed legend; the SKILL side normally supplies it from
# simple3d_config.json.
DEFAULT_SILK_THICKNESS = 0.025


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

_CONVENTIONS: list[_Convention] = [
    (rule, polarity, closes)
    for rule in (RULE_TRAVEL, RULE_AXIS)
    for polarity in (True, False)
    for closes in (True, False)
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


def _face_from_wires(outer: TopoDS_Wire, inner: list[TopoDS_Wire]):
    """Planar face from an outer wire and its hole wires."""
    maker = BRepBuilderAPI_MakeFace(outer, True)
    if not maker.IsDone():
        raise StepBuilderError("silkscreen outline is not planar or self-intersects")
    for wire in inner:
        # A hole wire has to run opposite to the outer one for MakeFace to read
        # it as a void; ShapeFix_Face below repairs whichever way it came.
        maker.Add(TopoDS.Wire_s(wire.Reversed()))
    face = maker.Face()
    if inner:
        from OCP.ShapeFix import ShapeFix_Face

        fix = ShapeFix_Face(face)
        fix.FixOrientation()
        face = fix.Face()
    return face


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
) -> tuple[TopoDS_Compound | None, int, int]:
    """Extrude one side's silkscreen polygons into a compound of thin solids.

    Returns (compound, built, skipped). *thickness* is signed: positive extrudes
    upwards (top side), negative downwards (bottom side).

    The solids are deliberately NOT fused. Silkscreen is thousands of
    overlapping strokes and glyphs, and a boolean union of that many thin
    prisms is minutes of OCCT time with a real chance of failing outright,
    while the union buys nothing: the result is one label, one colour, and it
    renders and exports identically. What it costs is that the compound is not
    a single manifold solid, which matters only if someone means to do
    downstream boolean work on the ink itself.

    A polygon that cannot be built is counted and skipped rather than taken as
    fatal - one malformed glyph must not cost the whole board.
    """
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)

    polygons = list(polygons)
    convention = _pick_convention(polygons, z, log, side)

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
            face = _silk_face(polygon, z, convention)
            builder.Add(compound, BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, thickness)).Shape())
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


# --------------------------------------------------------------------------- #
# transforms
# --------------------------------------------------------------------------- #

def _rotation(axis: gp_Dir, degrees: float) -> gp_Trsf:
    trsf = gp_Trsf()
    trsf.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), axis), math.radians(degrees))
    return trsf


def component_transform(
    mapping: dict,
    component: dict,
    board_top_z: float,
    board_bottom_z: float,
) -> gp_Trsf:
    """Build the full placement transform for one component.

    Order is significant and matches the original: applied right to left, so the
    STEP model is first oriented by its mapping rotation, shifted by its mapping
    offset, optionally flipped, then rotated by the symbol angle and moved into
    place.

    board_top_z / board_bottom_z are the z of the two board faces (which one is
    zero depends on the chosen datum). Top parts sit on board_top_z, mirrored
    (bottom) parts are flipped 180 deg about Y and sit on board_bottom_z. Parts
    rest on the soldermask face, i.e. on the board surface, because real pads
    carry solder that lifts the part to mask level.
    """
    rx = _rotation(gp_Dir(1, 0, 0), mapping["rotation_x"])
    ry = _rotation(gp_Dir(0, 1, 0), mapping["rotation_y"])
    rz = _rotation(gp_Dir(0, 0, 1), mapping["rotation_z"])
    rotation = rz * ry * rx

    offset = gp_Trsf()
    offset.SetTranslation(
        gp_Vec(mapping["offset_x"], mapping["offset_y"], mapping["offset_z"])
    )

    angle = _rotation(gp_Dir(0, 0, 1), component["angle"])

    mirror = gp_Trsf()
    if component["is_mirrored"]:
        z = board_bottom_z
        mirror = _rotation(gp_Dir(0, 1, 0), 180.0)
    else:
        z = board_top_z

    position = gp_Trsf()
    position.SetTranslation(gp_Vec(component["x"], component["y"], z))

    return position * angle * mirror * offset * rotation



# --------------------------------------------------------------------------- #
# step file lookup
# --------------------------------------------------------------------------- #

class StepFileIndex:
    """Filename -> path index, built once.

    The C++ version ran a recursive_directory_iterator for every cache miss,
    which is O(components x files). One walk is enough.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        if not self.root.is_dir():
            raise StepBuilderError(f"STEP directory does not exist: {self.root}")
        self._index: dict[str, Path] = {}
        for path in self.root.rglob("*"):
            if path.is_file():
                self._index.setdefault(path.name, path)

    def find(self, name: str) -> Path | None:
        return self._index.get(name)


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #

def _label_entry(label: TDF_Label) -> str:
    entry = TCollection_AsciiString()
    TDF_Tool.Entry_s(label, entry)
    return entry.ToCString()


def _free_shape_entries(shape_tool) -> dict[str, TDF_Label]:
    seq = TDF_LabelSequence()
    shape_tool.GetFreeShapes(seq)
    return {_label_entry(seq.Value(i)): seq.Value(i) for i in range(1, seq.Length() + 1)}


@dataclass
class BuildResult:
    output: Path
    components_placed: int = 0
    components_skipped: list[str] = field(default_factory=list)
    missing_step_files: list[str] = field(default_factory=list)
    silkscreen_solids: int = 0
    silkscreen_skipped: int = 0
    # MFRPN reporting DISABLED (property attachment unreliable); kept for future:
    # missing_mfr_pn: list[str] = field(default_factory=list)


def _validate(data: dict) -> None:
    if "name" not in data:
        raise StepBuilderError("JSON is missing the 'name' field.")
    if "pcb" not in data:
        raise StepBuilderError("JSON is missing the 'pcb' object.")
    pcb = data["pcb"]
    for key in ("thickness", "edges", "color"):
        if key not in pcb:
            raise StepBuilderError(f"JSON is missing 'pcb.{key}'.")
    if "board" not in pcb["thickness"]:
        raise StepBuilderError("JSON is missing 'pcb.thickness.board'.")


def total_board_thickness(thickness: dict) -> float:
    """board + both soldermasks, the full physical stack.

    The SKILL side already sums dielectrics + planes + conductors into `board`
    and reports the two mask layers separately. Here they are added back so the
    solid has its true finished thickness (e.g. 1.054 + 0.025 + 0.025 = 1.104).
    Missing mask keys default to 0 so older JSON still works.
    """
    return (
        float(thickness["board"])
        + float(thickness.get("soldermask_top", 0.0))
        + float(thickness.get("soldermask_bottom", 0.0))
    )


# Marker written into every Simple 3D intermediate JSON. Any .json without it
# is some other file that happens to share the folder and must be ignored.
FORMAT_MARKER = "simple3d"


def is_simple3d_json(path: str | Path) -> bool:
    """True if *path* is a readable Simple 3D intermediate (has the marker).

    Used to filter a folder that may also hold unrelated .json files (netlist
    variant tables, tool configs, etc). Reads only enough to check the marker.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and data.get("format") == FORMAT_MARKER


def dated_output_name(base: str, output_dir: str | Path) -> str:
    """<base>_simple_DD_MM_YYYY, with a trailing _ per existing collision.

    Shared by the GUI and the CLI so the naming rule cannot drift between them.
    """
    from datetime import date

    output_dir = Path(output_dir)
    stem = f"{base}_simple_{date.today().strftime('%d_%m_%Y')}"
    candidate = stem
    while (output_dir / f"{candidate}.step").exists():
        candidate += "_"
    return candidate


def resolve_json_jobs(path: str | Path) -> tuple[list[Path], list[Path]]:
    """Resolve what to build from a user-visible path, at generate time.

    *path* may be a single JSON file or a folder of variant JSONs. Returns
    (jobs, ignored): jobs are Simple 3D intermediates to build, ignored are
    .json files present but lacking the format marker.

    Resolving at generate time - instead of caching a job list when the paths
    are first filled in - means the field the user sees is always the truth:
    picking a different file or editing the path cannot leave a stale queue
    behind.
    """
    p = Path(path)
    if p.is_dir():
        all_jsons = sorted(p.glob("*.json"))
        jobs = [j for j in all_jsons if is_simple3d_json(j)]
        ignored = [j for j in all_jsons if j not in jobs]
        return jobs, ignored
    if p.is_file():
        if is_simple3d_json(p):
            return [p], []
        return [], [p]
    return [], []


def _set_color(color_tool, label, rgb01, srgb: bool) -> None:
    color_type = (
        Quantity_TypeOfColor.Quantity_TOC_sRGB
        if srgb
        else Quantity_TypeOfColor.Quantity_TOC_RGB
    )
    color = Quantity_Color(rgb01[0], rgb01[1], rgb01[2], color_type)
    for target in (
        XCAFDoc_ColorType.XCAFDoc_ColorSurf,
        XCAFDoc_ColorType.XCAFDoc_ColorCurv,
        XCAFDoc_ColorType.XCAFDoc_ColorGen,
    ):
        color_tool.SetColor(label, color, target)


def _rim_faces(shape: TopoDS_Shape):
    """Return the vertical (edge/rim) faces of the board.

    The rim is the set of side walls, identified by a horizontal normal
    (normal_z ~ 0), i.e. faces whose plane is vertical. Classifying by
    z-position instead was wrong: a straight board's side walls have their
    centre of mass at mid-height, exactly on the top/bottom boundary, so they
    leaked into the "top" set and the rim colour landed on a flat face.
    Everything with a vertical normal is rim; the flat top and bottom faces
    keep the board colour.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_SurfaceType
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    rim = []
    exp = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        surf = BRepAdaptor_Surface(face)
        if surf.GetType() == GeomAbs_SurfaceType.GeomAbs_Plane:
            nz = surf.Plane().Axis().Direction().Z()
            if abs(nz) < 0.5:            # vertical wall -> rim
                rim.append(face)
        else:
            # curved wall (e.g. a rounded cutout edge) counts as rim too
            rim.append(face)
        exp.Next()
    return rim


def _sanitize(name: str) -> str:
    """Make a string safe as a STEP product/instance name."""
    return "".join(c if c.isalnum() or c in "_-+." else "_" for c in name)


def generate(
    step_dir: str | Path,
    json_file: str | Path,
    output_dir: str | Path,
    *,
    output_name: str | None = None,
    z_datum: str = "top",
    board_color: tuple[int, int, int] | None = None,
    rim_color: tuple[int, int, int] | None = None,
    silkscreen: bool = True,
    silk_color: tuple[int, int, int] | None = None,
    # MFRPN DISABLED (kept for future): name_instances_with_mfr_pn: bool = False,
    minimize_size: bool = True,
    srgb_color: bool = True,
    log: LogFn = _noop_log,
    progress: ProgressFn = _noop_progress,
) -> BuildResult:
    """Build the STEP assembly described by *json_file*.

    output_name:
        Base filename (without .step). Defaults to the JSON's `name` field.
    z_datum:
        "top"    -> z=0 at the top face, board extends downwards (top parts at 0).
        "bottom" -> z=0 at the bottom face, board extends upwards (bottom parts at 0).
    board_color / rim_color:
        RGB 0-255. board_color defaults to the JSON's pcb.color. rim_color, if
        given, paints the board sides + underside separately from the top face.
    silkscreen:
        Build the printed legend, if the JSON carries one (format_version 2+).
        Silently does nothing for an older JSON or a board with no silkscreen.
    silk_color:
        RGB 0-255 for the ink; defaults to colors.SILK_COLORS["White"].
    minimize_size:
        Set write.surfacecurve.mode = 0 (about half the file size, geometry
        unchanged) and share one part per distinct model.
    srgb_color:
        Treat colours as sRGB (what you set is what you see). False reproduces
        the original C++ linear-RGB behaviour.
    """
    json_file = Path(json_file)
    output_dir = Path(output_dir)

    if z_datum not in ("top", "bottom"):
        raise StepBuilderError(f"z_datum must be 'top' or 'bottom', got {z_datum!r}")

    if not json_file.is_file():
        raise StepBuilderError(f"Input file does not exist: {json_file}")

    index = StepFileIndex(step_dir)

    log(f"Reading {json_file.name}")
    try:
        data = json.loads(json_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StepBuilderError(f"{json_file.name} is not valid JSON: {exc}") from exc

    _validate(data)

    pcb_name = data["name"]
    json_stem = output_name or pcb_name
    thickness = total_board_thickness(data["pcb"]["thickness"])

    # Where the two board faces live, given the datum choice.
    if z_datum == "top":
        board_top_z, board_bottom_z = 0.0, -thickness
        extrude_z_offset = 0.0            # outline drawn at z=0, prism goes down
    else:
        board_top_z, board_bottom_z = thickness, 0.0
        extrude_z_offset = thickness       # outline at z=+T, prism goes down to 0

    # (write.surfacecurve.mode is set AFTER the writer is constructed, see
    # below - the STEPCAFControl_Writer constructor resets it, so setting it
    # here would be silently undone.)

    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())

    main_assembly = shape_tool.NewShape()
    TDataStd_Name.Set_s(main_assembly, TCollection_ExtendedString(_sanitize(json_stem)))

    # ---- board ----------------------------------------------------------- #
    log("Building board geometry")
    board = make_board_geometry(data["pcb"], thickness, extrude_z_offset)

    pcb_label = shape_tool.NewShape()
    shape_tool.SetShape(pcb_label, board)

    if board_color is None:
        rgb = data["pcb"]["color"]
        board_rgb01 = (float(rgb["r"]), float(rgb["g"]), float(rgb["b"]))
    else:
        board_rgb01 = (board_color[0] / 255.0, board_color[1] / 255.0, board_color[2] / 255.0)

    _set_color(color_tool, pcb_label, board_rgb01, srgb_color)

    if rim_color is not None:
        # Paint the rim (vertical side walls) separately. This needs per-face
        # colour, which costs a few extra entities but is what the user asked
        # for. The flat top/bottom keep the board colour.
        rim_rgb01 = (rim_color[0] / 255.0, rim_color[1] / 255.0, rim_color[2] / 255.0)
        rim_faces = _rim_faces(board)
        rim_q = Quantity_Color(
            rim_rgb01[0], rim_rgb01[1], rim_rgb01[2],
            Quantity_TypeOfColor.Quantity_TOC_sRGB if srgb_color
            else Quantity_TypeOfColor.Quantity_TOC_RGB,
        )
        for face in rim_faces:
            color_tool.SetColor(face, rim_q, XCAFDoc_ColorType.XCAFDoc_ColorSurf)

    # Name the board part per board (PCB_<jsonstem>), not a bare "PCB": otherwise
    # importing several boards into one CAD session, each carrying a part called
    # "PCB", lets one board's PCB silently substitute another's.
    TDataStd_Name.Set_s(pcb_label, TCollection_ExtendedString(_sanitize(f"PCB_{json_stem}")))
    shape_tool.AddComponent(main_assembly, pcb_label, TopLoc_Location(gp_Trsf()))

    # ---- silkscreen ------------------------------------------------------ #
    # Its own part per side, so it can be hidden or recoloured in the viewer
    # without touching the board, and so the two sides stay distinguishable.
    silk_data = data.get("silkscreen")
    silk_built = 0
    silk_skipped = 0
    if silkscreen and silk_data:
        from .colors import SILK_COLORS

        ink = silk_color if silk_color is not None else SILK_COLORS["White"]
        ink01 = (ink[0] / 255.0, ink[1] / 255.0, ink[2] / 255.0)
        ink_thickness = float(silk_data.get("thickness", DEFAULT_SILK_THICKNESS))

        # The ink sits ON the outer face of each side and grows away from the
        # board, so it never intersects the solid it is printed on.
        for side, polygons, z, sign in (
            ("silkscreen_top", silk_data.get("top") or [], board_top_z, 1.0),
            ("silkscreen_bot", silk_data.get("bottom") or [], board_bottom_z, -1.0),
        ):
            if not polygons:
                continue
            log(f"Building {side} ({len(polygons)} polygons)")
            compound, built, skipped = build_silkscreen(
                polygons, z, sign * ink_thickness, log=log, side=side
            )
            silk_built += built
            silk_skipped += skipped
            if compound is None:
                continue
            silk_label = shape_tool.NewShape()
            shape_tool.SetShape(silk_label, compound)
            _set_color(color_tool, silk_label, ink01, srgb_color)
            TDataStd_Name.Set_s(
                silk_label,
                TCollection_ExtendedString(_sanitize(f"{side}_{json_stem}")),
            )
            shape_tool.AddComponent(main_assembly, silk_label, TopLoc_Location(gp_Trsf()))
    elif silkscreen and not silk_data:
        log("No silkscreen in this JSON (re-export from Allegro to include it)")

    # ---- component group assemblies (symbols_top / symbols_bot) ---------- #
    # Created lazily so a single-sided board does not get an empty group.
    groups: dict[str, TDF_Label] = {}

    def group_for(side: str) -> TDF_Label:
        if side not in groups:
            grp = shape_tool.NewShape()
            TDataStd_Name.Set_s(grp, TCollection_ExtendedString(side))
            shape_tool.AddComponent(main_assembly, grp, TopLoc_Location(gp_Trsf()))
            groups[side] = grp
        return groups[side]

    # ---- components ------------------------------------------------------ #
    # Anything not reserved is a refdes. "silkscreen" MUST be listed here or it
    # would be walked as if it were a component.
    _reserved = ("name", "pcb", "format", "format_version", "silkscreen")
    components = {k: v for k, v in data.items() if k not in _reserved}
    result = BuildResult(
        output=output_dir / f"{json_stem}.step",
        silkscreen_solids=silk_built,
        silkscreen_skipped=silk_skipped,
    )

    # One shared part per distinct STEP model (task 5). The label is imported
    # once and every refdes referencing that model becomes an instance of it, so
    # ten identical resistors cost one solid, not ten. Named by the model file,
    # which co-varies with geometry -> no cross-board substitution.
    label_cache: dict[str, list[TDF_Label]] = {}
    named_parts: set[str] = set()

    total = len(components)
    for i, (ref_des, component) in enumerate(components.items(), start=1):
        progress(i, total)

        mapping = component.get("step_mapping")
        if not mapping or not mapping.get("step_name"):
            log(f"warning: {ref_des} has no step_mapping, skipped")
            result.components_skipped.append(ref_des)
            continue

        step_name = mapping["step_name"]

        if step_name not in label_cache:
            path = index.find(step_name)
            if path is None:
                log(f"warning: could not find {step_name}")
                result.missing_step_files.append(step_name)
                label_cache[step_name] = []
            else:
                log(f"Reading {step_name}")
                reader = STEPCAFControl_Reader()
                reader.SetColorMode(True)
                reader.SetNameMode(True)

                if reader.ReadFile(str(path)) != IFSelect_ReturnStatus.IFSelect_RetDone:
                    raise StepBuilderError(f"Could not read STEP file: {path}")

                # FIX: diff the free shapes around the transfer instead of
                # assuming everything from index 2 belongs to this file.
                before = _free_shape_entries(shape_tool)
                if not reader.Transfer(doc):
                    raise StepBuilderError(f"Could not transfer STEP file: {path}")
                after = _free_shape_entries(shape_tool)

                new_labels = [lab for e, lab in after.items() if e not in before]
                if not new_labels:
                    raise StepBuilderError(f"{step_name} contained no shapes")

                # Name the shared part after the model file (stem), once.
                part_name = _sanitize(Path(step_name).stem)
                if part_name and part_name not in named_parts:
                    TDataStd_Name.Set_s(
                        new_labels[0], TCollection_ExtendedString(part_name)
                    )
                    named_parts.add(part_name)
                label_cache[step_name] = new_labels

        roots = label_cache[step_name]
        if not roots:
            result.components_skipped.append(ref_des)
            continue

        # MFRPN tracking DISABLED (property attachment unreliable); keep for future:
        # mfr_pn = component.get("mfr_pn")
        # if not mfr_pn:
        #     result.missing_mfr_pn.append(ref_des)

        trsf = component_transform(mapping, component, board_top_z, board_bottom_z)

        # Place the shared part DIRECTLY under symbols_top / symbols_bot, as an
        # instance that carries the STEP file's own name. No per-refdes wrapper
        # sub-assembly and no refdes_<board> instance name (that was
        # over-complication): the tree under symbols_* is just the model parts,
        # instanced in place. The part is still shared, so N identical footprints
        # cost one solid.
        side = "symbols_bot" if component["is_mirrored"] else "symbols_top"
        parent = group_for(side)

        for root in roots:
            shape_tool.AddComponent(parent, root, TopLoc_Location(trsf))
        result.components_placed += 1

    # Without this the written document is empty.
    shape_tool.UpdateAssemblies()

    # ---- write ----------------------------------------------------------- #
    # FIX: the C++ version hardcoded a backslash separator, which produced a
    # file literally named "out\name.step" on anything but Windows.
    output_dir.mkdir(parents=True, exist_ok=True)

    writer = STEPCAFControl_Writer()
    writer.SetColorMode(True)
    writer.SetNameMode(True)

    # Set write.surfacecurve.mode HERE, after the writer is constructed: its
    # constructor resets this global to 1, so setting it any earlier is undone.
    # mode 0 drops the p-curves on faces -> about half the file size, geometry
    # identical (same volume and bbox, verified). Set explicitly both ways so
    # the sticky global never leaks between successive builds in one process.
    Interface_Static.SetIVal_s("write.surfacecurve.mode", 0 if minimize_size else 1)

    if not writer.Transfer(doc, STEPControl_StepModelType.STEPControl_AsIs):
        raise StepBuilderError("STEP writer transfer failed")

    status = writer.Write(str(result.output))
    if status != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise StepBuilderError(f"Failed to write {result.output} (status {status})")

    log(f"Wrote {result.output}")
    return result
