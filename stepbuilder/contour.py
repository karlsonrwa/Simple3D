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
END the contour enters it by. See the comments on each. `drop_doubled_back`
takes out a stretch a contour walks twice, out and back - a spike with no
width, which the mesher cannot triangulate round (round 106).

Nothing here knows about boards, stackups or bends, and nothing here imports
from the modules that do - that is the point of the file (plan A1).
"""

from __future__ import annotations

import math
from typing import Iterable

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace
from OCP.GC import GC_MakeArcOfCircle
from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
from ._occt import TopTools_HSequenceOfShape
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

    wire = TopoDS.Wire(wires.Value(1))
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


# --------------------------------------------------------------------------- #
# a contour that runs back over its own track
# --------------------------------------------------------------------------- #

# Two legs of a contour closer than this all along are one track walked twice.
# 1 um: the doubled zone outlines of the boards on hand lie 0.004 to 0.044 um
# from themselves, and nothing a board shop makes comes within a hundred times
# this of being so thin.
TRACK_WIDTH = 1.0e-3

# The two legs are compared at points this far apart. Legs that part at a
# tangent joint - the slowest way to part - are 1 um apart 0.08 mm past it.
_TRACK_STEP = 0.01

# A joint is a turn when the way out is within ~8 degrees of the way in,
# reversed. Only a filter: the walk decides what was walked twice.
_TURN_COS = -0.99

# Shorter than this is no length at all.
_NO_LENGTH = 1.0e-9


class _Walked:
    """One primitive as the contour walks it, by the distance from the end the
    contour enters it by - the reading contour_points walks in."""

    def __init__(self, prim: dict):
        self.prim = prim
        self.arc = prim.get("type", "segment") == "arc"
        if self.arc:
            self.centre = (float(prim["center"][0]), float(prim["center"][1]))
            self.r = float(prim["radius"])
            a0, a1 = float(prim["alpha"]), float(prim["beta"])
            while a1 < a0:
                a1 += 360.0
            if not prim.get("ccw", True):
                a0, a1 = a1, a0
            self.a0 = math.radians(a0)
            self.sweep = math.radians(a1 - a0)          # negative: clockwise
            self.length = self.r * abs(self.sweep)
        else:
            self.p0 = (float(prim["start"][0]), float(prim["start"][1]))
            self.p1 = (float(prim["end"][0]), float(prim["end"][1]))
            self.length = math.hypot(self.p1[0] - self.p0[0], self.p1[1] - self.p0[1])

    def _angle(self, t: float) -> float:
        return self.a0 + math.copysign(t / self.r, self.sweep)

    def point(self, t: float) -> tuple[float, float]:
        if self.arc:
            a = self._angle(t)
            return (self.centre[0] + self.r * math.cos(a),
                    self.centre[1] + self.r * math.sin(a))
        f = t / self.length if self.length > _NO_LENGTH else 0.0
        return (self.p0[0] + f * (self.p1[0] - self.p0[0]),
                self.p0[1] + f * (self.p1[1] - self.p0[1]))

    def heading(self, t: float) -> tuple[float, float]:
        """The unit direction the contour walks in at t."""
        if self.arc:
            a, s = self._angle(t), (1.0 if self.sweep >= 0.0 else -1.0)
            return (-s * math.sin(a), s * math.cos(a))
        if self.length <= _NO_LENGTH:
            return (0.0, 0.0)
        return ((self.p1[0] - self.p0[0]) / self.length,
                (self.p1[1] - self.p0[1]) / self.length)

    def part(self, t0: float, t1: float) -> dict:
        """The stretch t0..t1 as a primitive on this one's own line or circle.

        Never a new curve through the new ends. A zone shares its circle with
        the zone beside it, number for number, and an arc rebuilt through three
        points moved flex2-a0's FLEX boundary 0.17 um off the circle
        STIFF_TOP_500_2 draws: the folded build's fuse then produced nothing
        at all, and the inspect build's flex faces failed BRepCheck."""
        if t0 <= _NO_LENGTH and t1 >= self.length - _NO_LENGTH:
            return self.prim
        if not self.arc:
            s, e = self.point(t0), self.point(t1)
            return {"type": "segment", "start": [s[0], s[1]], "end": [e[0], e[1]]}
        # Only the end that moved is written again; `ccw` says which of
        # alpha and beta the contour enters by.
        prim = dict(self.prim)
        entry, leave = ("alpha", "beta") if prim.get("ccw", True) else ("beta", "alpha")
        if t0 > _NO_LENGTH:
            prim[entry] = math.degrees(self._angle(t0)) % 360.0
        if t1 < self.length - _NO_LENGTH:
            prim[leave] = math.degrees(self._angle(t1)) % 360.0
        return prim


def _same_track(back: _Walked, tb: float, on: _Walked, to: float, run: float) -> bool:
    """Do *back*, walked backwards from tb, and *on*, walked on from to, stay
    within TRACK_WIDTH of each other for the whole of *run*?"""
    steps = max(1, math.ceil(run / _TRACK_STEP))
    for i in range(steps + 1):
        s = run * i / steps
        p, q = back.point(tb - s), on.point(to + s)
        if math.hypot(p[0] - q[0], p[1] - q[1]) > TRACK_WIDTH:
            return False
    return True


def _walk_back(legs: list[_Walked], k: int):
    """Walk both legs from the turn at the end of legs[k], a primitive at a
    time, while they are one track.

    -> (a, ta, b, tb, walked): the walk stopped at legs[a] at ta going back and
    at legs[b] at tb going on, and every primitive between those two was walked
    twice; or None when nothing was - or when everything was, a contour that is
    all track and no region.
    """
    n = len(legs)
    a, ta = k, legs[k].length
    b, tb = (k + 1) % n, 0.0
    walked, eaten = 0.0, 0
    while True:
        run = min(ta, legs[b].length - tb)
        if not _same_track(legs[a], ta, legs[b], tb, run):
            break
        ta, tb, walked = ta - run, tb + run, walked + run
        if ta <= _NO_LENGTH:
            a = (a - 1) % n
            ta, eaten = legs[a].length, eaten + 1
        if legs[b].length - tb <= _NO_LENGTH:
            b = (b + 1) % n
            tb, eaten = 0.0, eaten + 1
        if a == b or eaten >= n - 1:
            return None
    return (a, ta, b, tb, walked) if walked > _NO_LENGTH else None


def _cut_out(prims: list, legs: list[_Walked], a: int, ta: float, b: int, tb: float) -> list:
    """prims without what lies between legs[a] at ta and legs[b] at tb.

    The two ends left are within TRACK_WIDTH of each other, not on top of each
    other: the legs lie on circles or lines of their own (0.2 um apart on
    flex2-a0). A segment spans them when they are further apart than the wire
    is stitched at - 2.7e-5 to 3.3e-5 mm on the boards on hand."""
    n = len(prims)
    keep_a, keep_b = legs[a].part(0.0, ta), legs[b].part(tb, legs[b].length)
    p, q = legs[a].point(ta), legs[b].point(tb)
    bridge = ([{"type": "segment", "start": [p[0], p[1]], "end": [q[0], q[1]]}]
              if math.hypot(q[0] - p[0], q[1] - p[1]) > WIRE_TOLERANCE else [])
    gone, i = set(), (a + 1) % n
    while i != b:
        gone.add(i)
        i = (i + 1) % n
    out = []
    for i, prim in enumerate(prims):
        if i == a:
            out += [keep_a] + bridge          # a's end, the bridge, b's start
        elif i == b:
            out.append(keep_b)
        elif i not in gone:
            out.append(prim)
    return out


def drop_doubled_back(contour: list) -> tuple[list, list]:
    """The contour with every stretch it runs back over its own track left out.

    -> (contour, [((x, y) where it turns, mm walked twice), ...]). With nothing
    walked twice the contour comes back as it was given, the same list.

    A designer's slip, on three boards of the four on hand: flex2-a0's FLEX
    zone runs up its circle from 223.6 to 210.2 degrees and turns back down
    it, 1.50 mm walked twice 0.044 um from itself; flex3-a0's FLEX zone does
    it for 0.78 mm, flex-b2's STTIFFENER1 twice for 0.19. A spike like that
    has no width, so the region is the same without it - but OCCT's mesher,
    the one a viewer of the STEP meshes with, cannot triangulate a face round
    it: it laid a 26.25 mm2 triangle outside flex2-a0's board on the top and
    the bottom face of every layer of the flex (the owner's step2html page,
    28.10.2026). BRepCheck calls the face valid, and ShapeFix does not see
    the spike - notched edges, small edges, self-intersection and the whole
    face each leave the wire as it was, measured at 1e-5 to 1e-2 mm.

    A turn is a joint where the contour reverses. From there both legs are
    walked together, one back and one on, a primitive at a time, while they
    stay within TRACK_WIDTH of each other the whole way; what they cover is
    dropped and the two ends joined. A notch with any real width parts at
    once and is left alone, and so is a contour that is nothing but a doubled
    track - there is no region to keep.
    """
    prims = list(contour or [])
    turns: list = []
    if len(prims) < 3 or any(p.get("type", "segment") not in ("segment", "arc")
                             for p in prims):
        return contour, turns
    # A pass takes out one stretch walked twice; the boards on hand need one
    # pass per spike. The bound - a pass per primitive the contour came with -
    # is there so that no outline, however odd, can keep a build turning.
    for _pass in range(len(prims)):
        legs = [_Walked(p) for p in prims]
        n = len(legs)
        found = None
        for k in range(n):
            if legs[k].length <= _NO_LENGTH:
                continue
            # A joint's way out is the next primitive that has a length: a
            # zero-length one between the legs has no direction to compare.
            nxt = next((j % n for j in range(k + 1, k + n)
                        if legs[j % n].length > _NO_LENGTH), None)
            if nxt is None:
                break
            h_in, h_out = legs[k].heading(legs[k].length), legs[nxt].heading(0.0)
            if h_in[0] * h_out[0] + h_in[1] * h_out[1] < _TURN_COS:
                found = _walk_back(legs, k)
                if found is not None:
                    turns.append((legs[k].point(legs[k].length), found[4]))
                    break
        if found is None:
            break
        prims = _cut_out(prims, legs, *found[:4])
    return (prims if turns else contour), turns


# --------------------------------------------------------------------------- #
# wires -> face
# --------------------------------------------------------------------------- #

def _face_from_wires(outer: TopoDS_Wire, inner: list[TopoDS_Wire]):
    """Planar face from an outer wire and its hole wires."""
    maker = BRepBuilderAPI_MakeFace(outer, True)
    if not maker.IsDone():
        raise StepBuilderError("silkscreen outline is not planar or self-intersects")
    for wire in inner:
        # A hole wire has to run opposite to the outer one for MakeFace to read
        # it as a void; ShapeFix_Face below repairs whichever way it came.
        maker.Add(TopoDS.Wire(wire.Reversed()))
    face = maker.Face()
    if inner:
        from OCP.ShapeFix import ShapeFix_Face

        fix = ShapeFix_Face(face)
        fix.FixOrientation()
        face = fix.Face()
    return face
