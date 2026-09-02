"""Cutting a folded-to-be shape down to one piece of the board.

`_cut_to_region` is what FoldPlan.apply calls once per region per shape: the
part of the shape inside a region's half-plane bounds and inside its face,
with every boolean that can be skipped skipped. `_slab` and `_plane_face`
are the cutters, sized and placed from the SHAPE's own box - round 63's
lesson: a cutter placed from the origin misses a board drawn at x = 1000.
"""

from __future__ import annotations

import math

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakePrism
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

from ..contour import point_in_polygon
from .constants import EPS
from .regions import _extent, _is_empty


def _cut_to_region(shape: TopoDS_Shape,
                   bounds: list[tuple[float, float, float, float]],
                   box, piece=None) -> TopoDS_Shape | None:
    """The part of *shape* inside *face* and every one of *bounds*, or None.

    Each bound that the shape already satisfies is skipped rather than turned
    into a boolean - on a board with one bend that leaves the far panel and the
    held panel each costing a single cut, and the silkscreen on either of them
    costing none at all.

    *piece* is the region or strip, whose `face` is the part of the flat board
    it covers - what tells one arm from another. Its bounding box is tried
    FIRST, because it rejects outright and costs nothing: that is what makes
    folding a legend one glyph at a time affordable.
    """
    pbox = piece.face_box() if piece is not None else None
    if pbox is not None:
        xmin, ymin, _, xmax, ymax, _ = pbox
        sxmin, symin, _, sxmax, symax, _ = box
        if (sxmax < xmin - EPS or sxmin > xmax + EPS
                or symax < ymin - EPS or symin > ymax + EPS):
            return None

    out = shape
    for nx, ny, lo, hi in bounds:
        low, high = _extent(box, nx, ny)
        if high < lo - EPS or low > hi + EPS:
            return None
        if low >= lo - EPS and high <= hi + EPS:
            continue
        cutter = _slab(nx, ny, lo, hi, box)
        common = BRepAlgoAPI_Common(out, cutter)
        if not common.IsDone():
            return None
        out = common.Shape()
        if _is_empty(out):
            return None

    if piece is not None and piece.face is not None:
        # Wholly inside the piece? Then there is nothing to cut. A glyph is a
        # millimetre across and a panel is most of the board, so this is the
        # answer for nearly every polygon of a legend.
        sxmin, symin, _, sxmax, symax, _ = box
        corners = ((sxmin, symin), (sxmax, symin), (sxmax, symax), (sxmin, symax))
        whole = (piece.poly is not None
                 and all(point_in_polygon(c, piece.poly) for c in corners)
                 and not _crosses(piece.poly, sxmin, symin, sxmax, symax))
        if not whole:
            zmin, zmax = box[2], box[5]
            prism = BRepPrimAPI_MakePrism(
                piece.face, gp_Vec(0, 0, (zmax - zmin) + 2.0)).Shape()
            lift = gp_Trsf()
            lift.SetTranslation(gp_Vec(0, 0, zmin - 1.0))
            prism = BRepBuilderAPI_Transform(prism, lift, True).Shape()
            common = BRepAlgoAPI_Common(out, prism)
            if not common.IsDone():
                return None
            out = common.Shape()
            if _is_empty(out):
                return None

    return None if _is_empty(out) else out


def _crosses(poly, xmin: float, ymin: float, xmax: float, ymax: float) -> bool:
    """Does any edge of *poly* pass through the box?

    All four corners of a box can be inside a polygon while an edge still cuts
    across it - a piece with a notch in it. Cheap, and it has to be right: the
    answer decides whether a boolean is skipped.
    """
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (max(x0, x1) < xmin or min(x0, x1) > xmax
                or max(y0, y1) < ymin or min(y0, y1) > ymax):
            continue
        return True
    return False


def _slab(nx: float, ny: float, lo: float, hi: float, box) -> TopoDS_Shape:
    """A box covering everything in *box* between `n.p = lo` and `n.p = hi`.

    Sized and placed from the SHAPE's own extent, in both directions. It used to
    run half the board's diagonal either side of the point `n * lo` - the foot
    of the near plane, measured from the ORIGIN - which silently assumes the
    board sits near the origin. Cadence's demo board does not: BEND_1's band has
    its foot at (16.9, -17.2) while the arm it cuts is at (140, 90), 163 mm away
    along the bend line against a 102 mm half-span, so the slab missed the board
    entirely and that bend was quietly built out of nothing. Every board drawn
    away from the origin loses bends this way, the more so the further out and
    the more diagonal the bend.
    """
    zmin, zmax = box[2], box[5]
    tx, ty = -ny, nx                       # along the bend line
    tlow, thigh = _extent(box, tx, ty)
    tlow -= 1.0
    thigh += 1.0

    low, high = _extent(box, nx, ny)
    lo = max(lo, low - 1.0) if lo != -math.inf else low - 1.0
    hi = min(hi, high + 1.0) if hi != math.inf else high + 1.0

    # frame with X across the bend, Y along it, Z up
    origin = gp_Pnt(nx * lo + tx * tlow, ny * lo + ty * tlow, zmin - 1.0)
    frame = gp_Ax2(origin, gp_Dir(0, 0, 1), gp_Dir(nx, ny, 0))
    return BRepPrimAPI_MakeBox(frame, hi - lo, thigh - tlow,
                               (zmax - zmin) + 2.0).Shape()


def _plane_face(nx: float, ny: float, at: float, box) -> TopoDS_Shape:
    """A planar face at `n . p = at`, big enough to cut anything in *box*."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.gp import gp_Pln

    xmin, ymin, zmin, xmax, ymax, zmax = box
    span = math.hypot(xmax - xmin, ymax - ymin) + abs(zmax - zmin) + 10.0
    plane = gp_Pln(gp_Pnt(nx * at, ny * at, (zmin + zmax) / 2.0),
                   gp_Dir(nx, ny, 0.0))
    return BRepBuilderAPI_MakeFace(plane, -span, span, -span, span).Face()
