"""A bend drawn across a zone of another stack - a crooked bend (round 101).

The strip of a bend is the piece of the flat board that curls. When the bend
area reaches into a zone whose stack is not the one the rest of the strip lies
on - a stiffener, as a rule - the fold wraps that zone's layers onto the same
cylinders as the flex: built that way, the model shows material bent that the
real board would not bend. Measured on flex2-a0 (finding R5-1 of the
23.10.2026 review): BEND_6's strip, 4.867 mm across, has the round stiffener
zone STIFF_TOP_500_2 on its last 1.07 mm, 5.1 mm2 of it, about 29 deg of the
130; folded and fused, that board is a body OpenCASCADE's own check rejects -
a face, a wire and two edges as built, five faces and their wires once its
STEP is read back - while the log said only that the bend was built on true
cylinders. On flex-b2 a stiffener reaches 0.16 mm into BEND_2 - the case the
per-layer fold in core was written for - and on flex3-a0 one reaches 0.08 mm
into BEND_3.

The owner's rule (25.10.2026): such a bend is built as drawn - on some
boards it cannot be done otherwise - and the log says it is crooked, by how
much and where. Worked out once per plan, with planar faces at z = 0 like the
plan's own pieces: each strip's piece cut to its band, against each zone.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import EPS

# Below this much of a zone inside a strip, the two only touch: the edges of
# contours drawn to the same line meet to numerical noise, not to material.
AREA_TOL = 1e-3          # mm2
# How far beyond the board a band's rectangle reaches, so it never ends inside it.
FAR = 1e4                # mm


@dataclass
class Crooked:
    """One zone of another stack inside one bend's strip."""

    bend: str
    zone: str
    thickness: float     # the zone's own stack, mm
    own: float           # the stack most of the strip lies on, mm
    area: float          # of the zone inside the strip, mm2
    depth: float         # how far the zone reaches into the strip, mm
    edge: str            # where it enters from: "start", "end" or "inside"
    width: float         # the strip across, mm
    angle: float         # the bend's whole angle, deg

    @property
    def share(self) -> float:
        """The part of the bend's angle the zone is bent through, deg."""
        return self.angle * min(1.0, self.depth / self.width) if self.width > 0 else 0.0

    def line(self) -> str:
        where = {"start": "from the side it starts on", "end": "from the side it ends on",
                 "inside": "inside it"}[self.edge]
        return (f"{self.bend}: a crooked bend - its bend area reaches {self.depth:.3f} mm into zone "
                f"{self.zone} ({self.thickness:.3f} mm thick, {self.area:.2f} mm2 of it, {where}), "
                f"where the rest of it is {self.own:.3f} mm: that zone's layers are bent with it, about "
                f"{self.share:.0f} of the {self.angle:.0f} deg. Built as drawn; on the real board that "
                f"material does not bend like the flex - check the bend area in Allegro.")


def _face(points):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
    from OCP.gp import gp_Pnt

    maker = BRepBuilderAPI_MakePolygon()
    for x, y in points:
        maker.Add(gp_Pnt(x, y, 0.0))
    maker.Close()
    return BRepBuilderAPI_MakeFace(maker.Wire(), True).Face()


def _common(a, b):
    """a and b in common, both left as they were. In its default mode a
    boolean may change its arguments - the tolerances of their edges and
    vertices - and a is the plan's own strip face, which the fold builds from."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.TopTools import TopTools_ListOfShape

    args, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
    args.Append(a)
    tools.Append(b)
    op = BRepAlgoAPI_Common()
    op.SetArguments(args)
    op.SetTools(tools)
    op.SetNonDestructive(True)
    op.Build()
    return op.Shape() if op.IsDone() else None


def _area(shape) -> float:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, props)
    return abs(props.Mass())


def _across(shape, nx: float, ny: float) -> tuple[float, float]:
    """The shape's extent along (nx, ny), from its vertices."""
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    values = []
    exp = TopExp_Explorer(shape, TopAbs_VERTEX)
    while exp.More():
        p = BRep_Tool.Pnt_s(TopoDS.Vertex_s(exp.Current()))
        values.append(nx * p.X() + ny * p.Y())
        exp.Next()
    return (min(values), max(values)) if values else (0.0, 0.0)


# The kinds of sub-shape the check of the folded board names, in this order.
CHECKED = ("solid", "shell", "face", "wire", "edge", "vertex")
_PLURAL = {"vertex": "vertices"}


def rejected(shape) -> dict:
    """What OpenCASCADE's own check (BRepCheck) rejects in *shape*: kind of
    sub-shape -> the sub-shapes of that kind it rejects, each once, whether
    for a status of its own or for one it has inside a shape it belongs to.
    Empty when the shape passes.

    Each layer a bend wraps is checked as it is built (strip_wrap) and falls
    back to facets when it fails; what no check saw was the FUSED board.
    flex2-a0's, folded (round 101): a face (UnorientableShape), a wire
    (SelfIntersectingWire) and two edges whose curves are rejected only in the
    faces they bound - as on a box with one edge's curve moved off its faces,
    where the edge and its two vertices have no status of their own at all.
    """
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.TopAbs import (TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID,
                            TopAbs_VERTEX, TopAbs_WIRE)
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    analyzer = BRepCheck_Analyzer(shape, True)
    if analyzer.IsValid():
        return {}
    kinds = dict(zip(CHECKED, (TopAbs_SOLID, TopAbs_SHELL, TopAbs_FACE, TopAbs_WIRE,
                               TopAbs_EDGE, TopAbs_VERTEX)))
    found = {}
    for name in CHECKED:
        subs = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, kinds[name], subs)
        bad = [subs.FindKey(i) for i in range(1, subs.Extent() + 1)
               if _fails(analyzer.Result(subs.FindKey(i)))]
        if bad:
            found[name] = bad
    return found


def _fails(result) -> bool:
    """A status other than NoError: its own, or one in a shape it belongs to."""
    if result is None:
        return False
    if any(not _no_error(status) for status in result.Status()):
        return True
    result.InitContextIterator()
    while result.MoreShapeInContext():
        if any(not _no_error(status) for status in result.StatusOnShape()):
            return True
        result.NextShapeInContext()
    return False


def _no_error(status) -> bool:
    return str(status).split(".")[-1] == "BRepCheck_NoError"


def _points_on(shape):
    """Points of *shape* to place it by, best first: for a face the middle of
    its parameter box, then the points of a 9 x 9 grid in that box that lie on
    the face; then its vertices. A point on the seam between two pieces may
    unfold into neither: flex3-a0's rejected face is a sliver of 0.0000 mm2 at
    the end of BEND_3, and only one of its four vertices unfolds (round 101)."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.TopAbs import TopAbs_FACE, TopAbs_IN, TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pnt2d

    if shape.ShapeType() == TopAbs_FACE:
        face = TopoDS.Face_s(shape)
        surface = BRepAdaptor_Surface(face)
        u0, u1 = surface.FirstUParameter(), surface.LastUParameter()
        v0, v1 = surface.FirstVParameter(), surface.LastVParameter()
        yield surface.Value((u0 + u1) / 2, (v0 + v1) / 2)
        tolerance = BRep_Tool.Tolerance_s(face)
        for i in range(1, 10):
            for j in range(1, 10):
                u, v = u0 + (u1 - u0) * i / 10, v0 + (v1 - v0) * j / 10
                if BRepClass_FaceClassifier(face, gp_Pnt2d(u, v), tolerance).State() == TopAbs_IN:
                    yield surface.Value(u, v)
    exp = TopExp_Explorer(shape, TopAbs_VERTEX)
    while exp.More():
        yield BRep_Tool.Pnt_s(TopoDS.Vertex_s(exp.Current()))
        exp.Next()


def where(plan, shapes) -> list[str]:
    """The pieces of the flat board *shapes* of the folded one came from -
    "panel after BEND_6", "BEND_3 slice 12/12" - as the plan's regions are
    named, each placed by the first of its points that unfolds into one; a
    shape none of whose points does is left out."""
    places = []
    for shape in shapes:
        for point in _points_on(shape):
            back = plan.flat_frame(point)
            if back is None:
                continue
            flat = point.Transformed(back)
            label = plan.region_at(flat.X(), flat.Y())
            if label != "?":
                if label not in places:
                    places.append(label)
                break
    return places


def board_check(board, plan) -> str:
    """The warning for a folded board OpenCASCADE's own check rejects - what
    it rejects and in which pieces of the board - or "" when it passes."""
    found = rejected(board)
    if not found:
        return ""
    counts = [f"{len(found[name])} {name if len(found[name]) == 1 else _PLURAL.get(name, name + 's')}"
              for name in CHECKED if name in found]
    said = counts[0] if len(counts) == 1 else ", ".join(counts[:-1]) + " and " + counts[-1]
    places = where(plan, [shape for name in CHECKED for shape in found.get(name, [])])
    at = f" - in {', '.join(places)}" if places else ""
    return (f"the folded board fails OpenCASCADE's own check (BRepCheck): {said} rejected{at}. "
            f"Written all the same; some CAD programs refuse such a body or repair it their own way.")


def crooked_parts(strips: list, zones: list[dict], levels: dict) -> list[Crooked]:
    """Every zone of another stack inside a bend's strip, one entry per bend
    and zone (a bend cut into several strips adds them up).

    *levels*: zone name -> (top z, bottom z), as plan_from_json has them. A
    zone without a level or a contour is not judged. The strip's own stack is
    the one most of its area lies on.
    """
    from ..contour import build_contour
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace

    faces = {}
    for zone in zones:
        name = str(zone.get("name"))
        if name in levels and zone.get("contour"):
            maker = BRepBuilderAPI_MakeFace(build_contour(zone["contour"], 0.0), True)
            if maker.IsDone():
                faces[name] = maker.Face()

    found: dict[tuple[str, str], Crooked] = {}
    for strip in strips:
        if strip.face is None:
            continue
        nx, ny = strip.normal
        dx, dy = -ny, nx
        band = _face([(nx * strip.lo + dx * FAR, ny * strip.lo + dy * FAR),
                      (nx * strip.hi + dx * FAR, ny * strip.hi + dy * FAR),
                      (nx * strip.hi - dx * FAR, ny * strip.hi - dy * FAR),
                      (nx * strip.lo - dx * FAR, ny * strip.lo - dy * FAR)])
        piece = _common(strip.face, band)
        if piece is None:
            continue
        parts = []
        for name, face in faces.items():
            inside = _common(piece, face)
            if inside is None:
                continue
            area = _area(inside)
            if area >= AREA_TOL:
                parts.append((name, area, inside))
        if not parts:
            continue
        thick = {name: levels[name][0] - levels[name][1] for name, _, _ in parts}
        own_name = max(parts, key=lambda part: part[1])[0]
        own = thick[own_name]
        width = strip.hi - strip.lo
        for name, area, inside in parts:
            if abs(thick[name] - own) <= EPS:
                continue
            low, high = _across(inside, nx, ny)
            if low <= strip.lo + EPS:
                edge, depth = "start", high - strip.lo
            elif high >= strip.hi - EPS:
                edge, depth = "end", strip.hi - low
            else:
                edge, depth = "inside", high - low
            key = (strip.bend.name, name)
            if key in found:
                found[key].area += area
                found[key].depth = max(found[key].depth, depth)
            else:
                found[key] = Crooked(strip.bend.name, name, thick[name], own, area, depth, edge,
                                     width, strip.bend.angle)
    return list(found.values())
