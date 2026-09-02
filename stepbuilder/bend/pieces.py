"""Cutting the flat outline into the pieces that fold.

A bend line is a segment across ONE arm, and which arm a point is on is a
question about connectivity, not about which side of a line it falls (the
half-plane model that came before could not ask it - see the note below).
So the outline is cut by the bend strips, the pieces that fall out ARE the
panels, and everything else follows from how those pieces touch.
`_cut_into_pieces` is the entry; the rest make, mend and read one face.
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
from .constants import LogFn, _noop_log


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


def _face_poly(face, per_curve: int = 12) -> list[tuple[float, float]]:
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
    slivers = [f for f in good[1:] if area(f) < 0.01 * biggest]
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
                          min(across) - 10.0, max(across) + 10.0)
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

    builder = BRep_Builder()
    tools = TopoDS_Compound()
    builder.MakeCompound(tools)
    for _, part in strips:
        builder.Add(tools, part)

    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut

    cut = BRepAlgoAPI_Cut(face, tools)
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
