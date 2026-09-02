"""A JSON contour, as an OpenCASCADE wire and as a flat polygon.

The intermediate describes every outline - board edge, cutout, drill, zone,
drawn layer shape, silkscreen glyph - as a list of primitives:

    {"type": "segment", "start": [x, y], "end": [x, y]}
    {"type": "arc", "center": [x, y], "radius": r, "alpha": deg, "beta": deg, "ccw": bool}
    {"type": "circle", "x": x, "y": y, "radius": r}

`build_contour` turns one into a closed wire for the solid modeller, exactly.
`contour_points` turns one into a polygon with the arcs sampled, for the
questions that only need area and containment (which side of a bend holds
still, which zone a point is in). Both read an arc the same way, and the
reading is the round-63 one: `alpha`..`beta` bound the arc, `ccw` says which
END the contour enters it by. See the comments on each.

Nothing here knows about boards, stackups or bends, and nothing here imports
from the modules that do - that is the point of the file (plan A1).
"""

from __future__ import annotations

import math
from typing import Iterable

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.GC import GC_MakeArcOfCircle
from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
from OCP.TopTools import TopTools_HSequenceOfShape
from OCP.TopoDS import TopoDS, TopoDS_Wire
from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt

from .errors import StepBuilderError

# Tolerance used to stitch contour edges into a closed wire.
# Matches the value used by the original C++ implementation.
WIRE_TOLERANCE = 1.0e-5


# --------------------------------------------------------------------------- #
# contour -> wire
# --------------------------------------------------------------------------- #

def build_contour(contour: Iterable[dict], z_offset: float = 0.0) -> TopoDS_Wire:
    """Turn a list of JSON primitives (segment / arc / circle) into a wire."""
    edges = []

    for segment in contour:
        kind = segment.get("type", "segment")

        if kind == "arc":
            center = gp_Pnt(segment["center"][0], segment["center"][1], z_offset)
            circle = gp_Circ(gp_Ax2(center, gp_Dir(0, 0, 1)), segment["radius"])
            # alpha..beta bound the arc; `ccw` says which END the contour enters
            # it by, NOT which way the sweep goes. Passing ccw as the sense - as
            # this did - turns a 90 degree corner into the 270 degree arc the
            # long way round. Settled by measurement on Cadence's demo board:
            # under this reading every contour in the file joins head to tail to
            # 0.000 mm, including the board outline; under the old one three of
            # them had joints 5.657, 12.728 and 19.799 mm apart and every
            # affected arc came out at 270 degrees where the design draws 90.
            #
            # Direction does not matter here: the stitcher below reorders and
            # reverses edges as it likes, so the arc is always built the short
            # way from alpha to beta. contour_points, which walks the contour in
            # order, does have to honour `ccw` - see there.
            alpha = math.radians(segment["alpha"])
            beta = math.radians(segment["beta"])
            while beta < alpha:
                beta += 2.0 * math.pi
            arc = GC_MakeArcOfCircle(circle, alpha, beta, True).Value()
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


# --------------------------------------------------------------------------- #
# flat polygon helpers - area and containment tests on a chord approximation
# --------------------------------------------------------------------------- #

def contour_points(contour, arc_steps: int = 8) -> list[tuple[float, float]]:
    """A JSON contour as a plain polygon. Arcs are sampled, not preserved.

    Only ever used for area and containment tests, where a chord approximation
    is not merely acceptable but the point: this decides which side of a bend
    holds still, and that answer must not depend on a curve's exact sampling.
    """
    points: list[tuple[float, float]] = []
    for prim in contour or []:
        kind = prim.get("type", "segment")
        if kind == "segment":
            points.append((float(prim["start"][0]), float(prim["start"][1])))
            points.append((float(prim["end"][0]), float(prim["end"][1])))
        elif kind in ("arc", "circle"):
            cx, cy = (float(prim["center"][0]), float(prim["center"][1])) \
                if kind == "arc" else (float(prim["x"]), float(prim["y"]))
            r = float(prim["radius"])
            if kind == "circle":
                a0, a1 = 0.0, 360.0
            else:
                # alpha..beta bound the arc; `ccw` says which END the contour
                # enters it by, not which way the sweep goes. See the note in
                # build_contour above: reading `ccw` as the direction turns a 90
                # degree corner into the 270 degree arc the long way round, and
                # leaves the contour with joints up to 19.8 mm apart. Here the
                # direction does matter - the polygon is walked in order - so
                # the arc is sampled backwards when it is entered from beta.
                a0, a1 = float(prim["alpha"]), float(prim["beta"])
                while a1 < a0:
                    a1 += 360.0
                if not prim.get("ccw", True):
                    a0, a1 = a1, a0
            for i in range(arc_steps + 1):
                a = math.radians(a0 + (a1 - a0) * i / arc_steps)
                points.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    # drop consecutive duplicates, which every shared vertex produces
    out: list[tuple[float, float]] = []
    for p in points:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-9:
            out.append(p)
    return out


def polygon_area(points: list[tuple[float, float]]) -> float:
    """Unsigned area by the shoelace formula."""
    if len(points) < 3:
        return 0.0
    total = 0.0
    for i in range(len(points)):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % len(points)]
        total += x0 * y1 - x1 * y0
    return abs(total) / 2.0


def clip_halfplane(points: list[tuple[float, float]],
                   nx: float, ny: float, d: float) -> list[tuple[float, float]]:
    """Sutherland-Hodgman clip to `n . p <= d`.

    Correct for a non-convex subject polygon as long as the clip region is a
    half plane, which it always is here: the pieces it can leave joined along
    the clip line have zero area and do not disturb the area comparison this
    is used for.
    """
    if not points:
        return []
    out: list[tuple[float, float]] = []
    n = len(points)
    for i in range(n):
        cur = points[i]
        nxt = points[(i + 1) % n]
        dc = nx * cur[0] + ny * cur[1] - d
        dn = nx * nxt[0] + ny * nxt[1] - d
        if dc <= 0:
            out.append(cur)
        if (dc < 0 < dn) or (dn < 0 < dc):
            t = dc / (dc - dn)
            out.append((cur[0] + t * (nxt[0] - cur[0]),
                        cur[1] + t * (nxt[1] - cur[1])))
    return out


def point_on_polygon(point: tuple[float, float],
                     polygon: list[tuple[float, float]],
                     tol: float = 1.0e-6) -> bool:
    """Is the point within *tol* of the polygon's boundary?

    Ray casting answers a strict inside/outside, and the questions asked of a
    fold region are usually about a CORNER of the board or the seam between two
    pieces - points that sit exactly on a boundary and belong to both. Half
    planes had EPS for this; polygons need the same allowance, spelled out.
    """
    x, y = point
    n = len(polygon)
    for i in range(n):
        x0, y0 = polygon[i]
        x1, y1 = polygon[(i + 1) % n]
        dx, dy = x1 - x0, y1 - y0
        length = dx * dx + dy * dy
        if length <= 0.0:
            if math.hypot(x - x0, y - y0) <= tol:
                return True
            continue
        t = ((x - x0) * dx + (y - y0) * dy) / length
        t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
        if math.hypot(x - (x0 + t * dx), y - (y0 + t * dy)) <= tol:
            return True
    return False


def point_in_polygon(point: tuple[float, float],
                     polygon: list[tuple[float, float]]) -> bool:
    """Ray casting. Used to find which zone a bend line sits in."""
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        x0, y0 = polygon[i]
        x1, y1 = polygon[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            xc = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if x < xc:
                inside = not inside
    return inside
