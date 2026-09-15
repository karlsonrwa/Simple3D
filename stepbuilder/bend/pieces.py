"""Cutting the flat outline into the pieces that fold.

A bend line is a segment across ONE arm, and which arm a point is on is a
question about connectivity, not about which side of a line it falls (the
half-plane model that came before could not ask it - see the note below).
So the outline is cut by the bend strips, the pieces that fall out ARE the
panels, and everything else follows from how those pieces touch.
`_cut_into_pieces` is the entry; the rest make, mend and read one face.
`_cutters` then makes, from those faces, what each layer is actually cut
WITH - the same faces grown along the outline and exact at the seams.
"""

from __future__ import annotations

import math

from OCP.BRep import BRep_Builder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.TopAbs import TopAbs_ShapeEnum
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound
from OCP.gp import gp_Pnt

from ..contour import build_contour, point_in_polygon
from ..errors import StepBuilderError
from .constants import (BAND_REACH, CUTTER_MARGIN, FACE_POLY_PER_CURVE, LogFn,
                        SHARED_STRIP_RATIO, SLIVER_RATIO, _noop_log)


# --------------------------------------------------------------------------- #
# cutting the flat board into pieces
# --------------------------------------------------------------------------- #
#
# A bend line is a segment across ONE arm, and which arm a point is on is a
# question about connectivity, not about which side of a line it falls. The
# half-plane model that came before this could not ask it: on Cadence's demo
# board "beyond BEND_5" also covers the LCD arm at the far end and the main
# board itself, so the held panel was being folded by a bend it has nothing to
# do with, and a quarter of the board was claimed by two regions at once.
#
# So the flat outline is cut by the bend strips, and the pieces that fall out
# ARE the panels. Everything else - which piece is held, what carries what,
# where a point ends up - follows from how those pieces touch.


def _polygon_face(poly: list[tuple[float, float]]):
    """A planar face at z = 0 from a closed 2-D polygon."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon

    maker = BRepBuilderAPI_MakePolygon()
    for x, y in poly:
        maker.Add(gp_Pnt(x, y, 0.0))
    maker.Close()
    if not maker.IsDone():
        return None
    face = BRepBuilderAPI_MakeFace(maker.Wire(), True)
    return face.Face() if face.IsDone() else None


def _band_face(nx: float, ny: float, lo: float, hi: float,
               tlow: float, thigh: float):
    """The strip `lo <= n.p <= hi`, reaching from *tlow* to *thigh* across it.

    The across-extent is passed in rather than guessed from a length, because a
    length has to be measured from somewhere and the only defensible somewhere
    is the board itself. Reaching a board's diagonal either side of the ORIGIN -
    which is what this did - leaves the band nowhere near a board drawn at
    x = 1000, and the cut then finds nothing to cut. Same mistake as _slab's.
    """
    tx, ty = -ny, nx
    return _polygon_face([
        (nx * lo + tx * tlow, ny * lo + ty * tlow),
        (nx * hi + tx * tlow, ny * hi + ty * tlow),
        (nx * hi + tx * thigh, ny * hi + ty * thigh),
        (nx * lo + tx * thigh, ny * lo + ty * thigh),
    ])


def _faces_of(shape) -> list:
    out = []
    if shape is None or shape.IsNull():
        return out
    exp = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE)
    while exp.More():
        out.append(TopoDS.Face_s(exp.Current()))
        exp.Next()
    return out


def _face_poly(face, per_curve: int = FACE_POLY_PER_CURVE) -> list[tuple[float, float]]:
    """A face's outer wire as an ordered 2-D polygon.

    The wire is no longer polygonal: the board outline is cut with its ARCS
    intact, so a rounded arm end arrives as one circular edge between two
    vertices. Taking the vertices alone would cut that corner off entirely, and
    the polygon is what answers "is this point on this piece" and "which side of
    the strip is it on". So a curved edge is sampled.

    Coarsely, and deliberately: this polygon never becomes geometry. The pieces
    are cut with the exact face; these points only classify. Twelve per curve is
    a few microns on the radii a board carries and costs nothing.
    """
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
    from OCP.GeomAbs import GeomAbs_CurveType
    from OCP.TopAbs import TopAbs_Orientation

    pts = []
    exp = BRepTools_WireExplorer(BRepTools.OuterWire_s(face))
    while exp.More():
        p = BRep_Tool.Pnt_s(exp.CurrentVertex())
        pts.append((p.X(), p.Y()))
        edge = exp.Current()
        adaptor = BRepAdaptor_Curve(edge)
        if adaptor.GetType() != GeomAbs_CurveType.GeomAbs_Line:
            first, last = adaptor.FirstParameter(), adaptor.LastParameter()
            if edge.Orientation() == TopAbs_Orientation.TopAbs_REVERSED:
                first, last = last, first
            # The end point is the next edge's start vertex, so stop short of it
            for i in range(1, per_curve):
                q = adaptor.Value(first + (last - first) * i / per_curve)
                pts.append((q.X(), q.Y()))
        exp.Next()
    return pts


def _piece_face(face, log: LogFn = _noop_log, what: str = "a piece"):
    """One face out of the cut, made valid, as (face-or-compound, polygon).

    A boolean between the outline and the strips can leave a face PINCHED: on
    Cadence's demo board the wedge between BEND_6 and BEND_4 came back with a
    zero-width slit running 19 mm up the arm's edge and back, because the
    outline's edge and the strip's edge are collinear there. Its area was right
    - 15.34 mm2 - and `BRepCheck_Analyzer` said invalid, and a prism raised on
    it is unusable: 2 of the board's 57 layer parts intersected it instead of
    all 8 in that zone, so the wedge was simply missing from the model.

    ShapeFix splits the pinch into valid faces - two here, 0.085 and 15.42 mm2 -
    and they are kept together as one piece, because a piece pinched in two by
    the arithmetic is still one piece of board and must fold as one.
    """
    from OCP.BRepCheck import BRepCheck_Analyzer

    if BRepCheck_Analyzer(face).IsValid():
        return face, [_face_poly(face)]

    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.ShapeFix import ShapeFix_Shape

    # COPY first. ShapeFix edits in place, and every face out of one boolean
    # shares its edges with the faces beside it - so repairing this one reaches
    # into its neighbours and quietly damages them. Measured: without the copy
    # the folded board lost 173.7 mm3 against the 22679.233 it is made of,
    # while the pinch it was fixing is worth 7.
    fix = ShapeFix_Shape(BRepBuilderAPI_Copy(face).Shape())
    fix.Perform()
    good = [f for f in _faces_of(fix.Shape()) if BRepCheck_Analyzer(f).IsValid()]
    if not good:
        log(f"warning: {what} of this board came out of the cut pinched and "
            f"could not be repaired; it may be missing from the model")
        return face, [_face_poly(face)]

    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    def area(f):
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, props)
        return props.Mass()

    good.sort(key=area, reverse=True)
    # The repair leaves SLIVERS along the slit it opened, and a sliver is an
    # artefact of the arithmetic rather than board: prism one and it is a
    # degenerate solid, which is worse than nothing. Measured here - a 0.085 mm2
    # chip beside a 15.42 mm2 wedge took the whole 173.763 mm3 dielectric of
    # that arm down with it, because the fuse of the folded pieces then produced
    # nothing at all. Anything under a hundredth of the piece goes, and the log
    # says how much, so this can never quietly eat something real.
    biggest = area(good[0])
    slivers = [f for f in good[1:] if area(f) < SLIVER_RATIO * biggest]
    if slivers:
        log(f"{what}: {len(slivers)} sliver(s) totalling "
            f"{sum(area(f) for f in slivers):.4f} mm2 left by the repair were "
            f"dropped, beside {biggest:.2f} mm2 of board")
        good = [f for f in good if f not in slivers]

    log(f"{what} came out of the cut pinched (a zero-width slit) and was "
        f"repaired into {len(good)} valid face(s)")
    if len(good) == 1:
        return good[0], [_face_poly(good[0])]

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for f in good:
        builder.Add(compound, f)
    # EVERY surviving fragment's polygon is kept, largest first. "Is this point
    # on this piece" has to be true for all of them - the anchor landing on the
    # smaller half is not a special case, it is a coin toss - while the callers
    # that want one outline (area, centroid) take the first.
    return compound, [_face_poly(f) for f in good]


def _area_of(shape) -> float:
    """The surface area of a face, a compound of faces, or nothing at all."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, props)
    return props.Mass()


def shared_strips(strips: list, ratio: float = SHARED_STRIP_RATIO) -> list:
    """(i, j, mm2) for every pair of strips that claims the same material.

    THE question `_strips_overlap` in plan.py is trying to answer, asked of
    the faces the cut actually uses instead of the rectangles the bend lines
    draw. The two are not the same shape: a strip is the band across the
    board that holds the bend line, and the band reaches right across the
    outline, so two short perpendicular bend lines far apart draw rectangles
    that miss each other while their strips cross in the middle of the board.
    Cadence's demo has that arrangement in miniature.

    Material claimed by two strips is folded twice, onto two different
    cylinders, which is exactly what `_readable` refuses a bend for. The
    rectangle test stays where it is - it is cheap, it runs per trial neutral
    factor, and it catches the ordinary case of two bend areas laid edge to
    edge - and this backs it up once the strips exist.

    *ratio* is of the SMALLER strip, because the absolute number says nothing
    on its own: see SHARED_STRIP_RATIO for the two measurements it sits
    between. Below it the shared piece is a sliver along a seam, and a real
    board that folds correctly has one.
    """
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common

    areas = [_area_of(face) for _, face in strips]
    out = []
    for i in range(len(strips)):
        for j in range(i + 1, len(strips)):
            smaller = min(areas[i], areas[j])
            if smaller <= 0.0:
                continue
            common = BRepAlgoAPI_Common(strips[i][1], strips[j][1])
            if not common.IsDone():
                continue
            shared = _area_of(common.Shape())
            if shared > ratio * smaller:
                out.append((i, j, shared))
    return out


def _touching(a, b, tol: float = 1.0e-6) -> bool:
    """Do two faces share a boundary?"""
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    dist = BRepExtrema_DistShapeShape(a, b)
    return bool(dist.IsDone()) and dist.Value() <= tol


def _closest_point(a, b) -> tuple[float, float] | None:
    """A point of *a* nearest to *b*, in 2-D. On the seam when they touch."""
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    dist = BRepExtrema_DistShapeShape(a, b)
    if not dist.IsDone() or dist.NbSolution() < 1:
        return None
    p = dist.PointOnShape1(1)
    return (p.X(), p.Y())


def _cut_into_pieces(outline: list[tuple[float, float]], chain: list,
                     log: LogFn = _noop_log, curves: list | None = None):
    """Cut the flat outline by every bend strip.

    -> (panels, strips), each a list of (polygon, face); strips[i] belongs to
    chain[i]. None if the outline cannot be made into a face at all, which
    leaves the caller to fall back on the old half-plane reading.

    *curves* is the outline as the intermediate writes it, arcs and all. It is
    what the board is CUT with, and *outline* - the same outline flattened - is
    only used to size the bands and to classify points afterwards.

    That distinction is the whole of this argument. `contour_points` samples an
    arc into eight chords, which was chosen when its answers were only areas and
    containment tests. Since the pieces are cut from it the same eight chords
    became the edge of the board: 67 um of flat on a 14 mm corner, and plainly
    visible on a rounded arm end once the wrap carried them onto the cylinder.
    Cutting with the real curve costs nothing - `_map_strip` already turns a
    circular edge into an exact ellipse in the cylinder's parameter space - and
    the flattened copy goes on doing the job it was accurate enough for.

    A band is infinite across its own direction, so `outline AND band` can come
    back in several pieces - BEND_5's band on the demo board also clips the LCD
    arm 180 mm away. Only the piece the bend LINE is in is that bend's strip;
    the others are ordinary board that happens to lie between the same two
    parallel lines, and they stay part of their own panel.
    """
    face = None
    if curves:
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace

        try:
            maker = BRepBuilderAPI_MakeFace(build_contour(curves, 0.0), True)
            face = maker.Face() if maker.IsDone() else None
        except (StepBuilderError, RuntimeError) as exc:
            log(f"note: the outline's own curves could not be used to cut the "
                f"board ({exc}); falling back on the flattened one")
            face = None
    if face is None:
        face = _polygon_face(outline)
    if face is None:
        return None

    strips = []
    for bend, (nx, ny), (px, py), half, _, _ in chain:
        base = nx * px + ny * py
        # How far the OUTLINE reaches across this bend, which is how long the
        # band has to be - measured from the board, not from the origin.
        across = [(-ny) * vx + nx * vy for vx, vy in outline]
        band = _band_face(nx, ny, base - half, base + half,
                          min(across) - BAND_REACH, max(across) + BAND_REACH)
        if band is None:
            return None
        common = BRepAlgoAPI_Common(face, band)
        if not common.IsDone():
            return None
        mid = bend.midpoint
        best, best_d = None, None
        for part in _faces_of(common.Shape()):
            part, polys = _piece_face(part, log, f"the strip of {bend.name}")
            polys = [q for q in polys if len(q) >= 3]
            if not polys:
                continue
            if any(point_in_polygon(mid, q) for q in polys):
                best, best_d = (polys, part), -1.0
                break
            d = min(math.hypot(vx - mid[0], vy - mid[1])
                    for q in polys for vx, vy in q)
            if best_d is None or d < best_d:
                best, best_d = (polys, part), d
        if best is None:
            return None
        strips.append(best)

    # One boolean, but the strips go in as SEPARATE TOOLS. A boolean's
    # argument must not interfere with itself and OCC does not intersect the
    # members of one argument against each other, so a compound of strips that
    # cross is undefined input. Two bends CAN cross: the gate in plan.py
    # compares the rectangles their bend lines draw, while the cut here uses a
    # band that reaches right across the outline, so two short perpendicular
    # bend lines far apart can still leave strips that share material.
    #
    # Measured on a 100 x 100 board with a bend line at y = 30 over
    # x = 10..20 and another at x = 70 over y = 10..20, both strips 6 mm wide
    # and sharing the 36 mm2 where they cross:
    #
    #   as one compound  : ONE pinched face, 8800.000 mm2 - the shared square
    #                      subtracted twice, and the four corner pieces welded
    #                      together through zero-width slits
    #   separate tools   : FOUR faces, 1809 + 729 + 4489 + 1809 = 8836.000 mm2,
    #                      which is 10000 - 600 - 600 + 36 exactly
    #
    # _piece_face repairs the pinched face into four and drops the 36 mm2 as a
    # sliver, so the AREA came back - but all four corners stayed inside one
    # `panels` entry, and a panel is what the fold moves as one rigid piece.
    # On Cadence's demo board the same thing happens at 0.065 mm2 between
    # BEND_4 and BEND_6, small enough to have left no mark.
    #
    # The strips sharing material at all is a separate fault, and plan.py
    # refuses one of the pair for it; this is only about the boolean being
    # given input it is allowed to have.
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.TopTools import TopTools_ListOfShape

    arguments = TopTools_ListOfShape()
    arguments.Append(face)
    tools = TopTools_ListOfShape()
    for _, part in strips:
        tools.Append(part)

    cut = BRepAlgoAPI_Cut()
    cut.SetArguments(arguments)
    cut.SetTools(tools)
    cut.Build()
    if not cut.IsDone():
        return None
    panels = []
    for part in _faces_of(cut.Shape()):
        part, polys = _piece_face(part, log, "a flat piece of the board")
        polys = [q for q in polys if len(q) >= 3]
        if polys:
            panels.append((polys, part))
    if not panels:
        return None
    return panels, strips


# --------------------------------------------------------------------------- #
# what a layer is cut WITH
# --------------------------------------------------------------------------- #

def _grown(face, margin: float):
    """*face* - or a compound of faces, a repaired pinch - with its boundary
    pushed outward by *margin*. None when the offset cannot be made."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffset
    from OCP.GeomAbs import GeomAbs_JoinType

    grown = []
    for f in _faces_of(face):
        try:
            offset = BRepOffsetAPI_MakeOffset(f, GeomAbs_JoinType.GeomAbs_Arc)
            offset.Perform(margin)
            if not offset.IsDone():
                return None
            exp = TopExp_Explorer(offset.Shape(), TopAbs_ShapeEnum.TopAbs_WIRE)
            while exp.More():
                maker = BRepBuilderAPI_MakeFace(TopoDS.Wire_s(exp.Current()), True)
                if maker.IsDone():
                    grown.append(maker.Face())
                exp.Next()
        except Exception:                     # OCC's Standard_Failure family
            return None
    if not grown:
        return None
    if len(grown) == 1:
        return grown[0]
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for f in grown:
        builder.Add(compound, f)
    return compound


def _cutters(faces: list, margin: float = CUTTER_MARGIN,
             log: LogFn = _noop_log) -> list:
    """What each piece is CUT WITH, one per face of *faces*, in order.

    A piece's exact face shares every outline wall with the layer it is
    about to cut, and a boolean between two walls that are only NEARLY the
    same surface is where OCC goes wrong. Round 84, flex2-a0: the FLEX
    zone's contour, as Allegro writes it, carries a zero-width spike along
    the round stiffener's arc - two arcs out and back, on circles 0.2 um
    apart - and that spike lies exactly on the cutter's cylinder. The
    boolean threw the WHOLE corner of the panel beyond BEND_6 away: a
    curved triangle of 0.12 mm2 on five of the seven flex layers, the notch
    the user saw. The two adhesive layers, built from their own drawn shape
    with the outline's exact arc, were untouched - which is what pointed at
    the cutter rather than the fold.

    So the cutter is the face grown by *margin* along its whole boundary,
    with every OTHER piece's exact face subtracted back out. Along the
    outline it now stands ten microns clear of anything the layer has; at
    the seams it is the neighbour's exact edge, so the pieces still tile the
    board without a gap or an overlap. Measured on every layer of that
    board: the pieces sum to the flat layer's volume to 1e-6 mm3, where the
    exact faces lost 0.029.

    A piece whose offset cannot be made keeps its exact face, and the log
    says so.
    """
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.TopTools import TopTools_ListOfShape

    out = []
    exact = 0
    for i, face in enumerate(faces):
        grown = _grown(face, margin) if len(faces) > 1 else None
        if grown is None:
            out.append(face)
            exact += len(faces) > 1
            continue
        arguments = TopTools_ListOfShape()
        arguments.Append(grown)
        tools = TopTools_ListOfShape()
        for j, other in enumerate(faces):
            if j != i:
                tools.Append(other)
        cut = BRepAlgoAPI_Cut()
        cut.SetArguments(arguments)
        cut.SetTools(tools)
        cut.Build()
        if not cut.IsDone() or not _faces_of(cut.Shape()):
            out.append(face)
            exact += 1
            continue
        out.append(cut.Shape())
    if exact:
        log(f"note: {exact} piece(s) of the board could not be given a grown "
            f"cutter and are cut with their exact face; a layer whose contour "
            f"only nearly follows the outline there may lose a corner")
    return out
