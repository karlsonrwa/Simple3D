"""The pieces of a flat board and the rigid transforms that carry them.

A `_Region` is a panel - a piece carried by one transform - or one facet of a
bend; a `_Strip` is the part that curls, with everything needed to curl it.
Both are cut from the flat outline (see pieces.py) and both answer "is this
flat point mine" the same way, through `_Piece`. `_slice_trsf` is the
hinge-and-rotate that places one facet; the OCC plumbing at the end is what
every module of the package measures boxes and emptiness with.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.TopAbs import TopAbs_ShapeEnum
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

from ..contour import point_in_polygon, point_on_polygon
from .constants import EPS
from .info import Bend


class _Piece:
    """What a panel and a strip share: a face of the flat board, its box, and
    the question "is this flat point mine".

    A mixin rather than a base dataclass so the two keep their own field
    lists; the fields it reads (`face`, `_box`, `poly`, `polys`, `bounds`)
    are declared by both. One implementation since round 72 (plan B1) - the
    two copies had already drifted in their docstrings.
    """

    def face_box(self):
        """The piece's bounding box, worked out once.

        Asked for every shape folded against it, and the legend asks tens of
        thousands of times - see FoldPlan.apply.
        """
        if self.face is not None and self._box is None:
            self._box = _bbox(self.face)
        return self._box

    def holds(self, x: float, y: float) -> bool:
        """Is the flat point inside this piece - its polygon(s) AND its bounds?"""
        rings = self.polys or ([self.poly] if self.poly is not None else [])
        if rings and not any(point_in_polygon((x, y), r)
                             or point_on_polygon((x, y), r) for r in rings):
            return False
        return all(lo - EPS <= nx * x + ny * y <= hi + EPS
                   for nx, ny, lo, hi in self.bounds)


@dataclass
class _Region(_Piece):
    """A piece of the flat board and the rigid transform that carries it.

    `bounds` are half-plane constraints in flat XY, each (nx, ny, lo, hi)
    meaning `lo <= n . p <= hi`, with +/-inf for an open side. They are applied
    to the FLAT shape, before any transform: that is what makes a chain of bends
    composable, because every cut is made in the one frame where the board is
    still a plane.
    """

    label: str
    bounds: list[tuple[float, float, float, float]]
    trsf: gp_Trsf
    moved: bool = True
    # "panel" - a flat piece carried by one rigid transform; "slice" - one facet
    # of a bend, used only when the exact construction below does not apply.
    kind: str = "panel"
    # The piece of the flat board this region is, as a polygon and as a face.
    # This is what says which ARM the region belongs to; `bounds` only ever
    # subdivides it now - the slices of one strip. See _cut_into_pieces.
    poly: list[tuple[float, float]] | None = None
    # Every fragment of the piece, when a pinch had to be repaired into several
    # faces - see _piece_face. `poly` is the first and largest of them.
    polys: list | None = None
    face: object = None
    _box: object = None


@dataclass
class _Strip(_Piece):
    """The part of the board that curls, and everything needed to curl it.

    Kept apart from the panels because it is built in one of two ways and the
    choice is made per shape: exactly, as a revolved section, or as the rigid
    slices in `facets`. See FoldPlan.apply.
    """

    bend: Bend
    bounds: list[tuple[float, float, float, float]]
    normal: tuple[float, float]
    lo: float
    hi: float
    axis_z: float
    turn: float                       # signed, radians: the finished angle
    carried: gp_Trsf                  # what the bends before this one do to it
    facets: list[_Region] = field(default_factory=list)
    poly: list[tuple[float, float]] | None = None
    polys: list | None = None
    face: object = None
    _box: object = None


    def axis(self) -> gp_Ax1:
        """The cylinder the board wraps onto, in the flat frame."""
        nx, ny = self.normal
        return gp_Ax1(gp_Pnt(nx * self.lo, ny * self.lo, self.axis_z),
                      gp_Dir(ny, -nx, 0.0))


def _slice_trsf(carried: gp_Trsf, nx: float, ny: float, lo: float,
                hinge: float, axis_z: float, phi: float) -> gp_Trsf:
    """The transform of a piece hinged at `hinge`, rotated `phi` about the arc.

    Two steps, and the order is the whole trick: slide the piece back along the
    bend direction until its leading edge sits at the start of the arc, THEN
    rotate it about the cylinder axis. That is what makes the flat material the
    bend consumes disappear into the arc instead of stretching the board.

    `carried` is everything the earlier bends in the chain already do to this
    piece, and it is applied last.
    """
    shift = hinge - lo
    slide = gp_Trsf()
    slide.SetTranslation(gp_Vec(-shift * nx, -shift * ny, 0.0))

    # (nx, ny) is a unit vector, so the point `lo` along it is a foot of the
    # cylinder axis; the axis itself runs parallel to the bend line, and the
    # direction n x z is what makes a positive angle tip the far side upwards.
    origin = gp_Pnt(nx * lo, ny * lo, axis_z)
    direction = gp_Dir(ny, -nx, 0.0)

    turn = gp_Trsf()
    turn.SetRotation(gp_Ax1(origin, direction), phi)
    return carried * turn * slide


# --------------------------------------------------------------------------- #
# OCC plumbing
# --------------------------------------------------------------------------- #

def _bbox(shape: TopoDS_Shape):
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, True)
    if box.IsVoid():
        return None
    return box.Get()          # (xmin, ymin, zmin, xmax, ymax, zmax)


def _extent(box, nx: float, ny: float) -> tuple[float, float]:
    xmin, ymin, _, xmax, ymax, _ = box
    values = [nx * x + ny * y for x in (xmin, xmax) for y in (ymin, ymax)]
    return min(values), max(values)


def _is_empty(shape: TopoDS_Shape) -> bool:
    if shape is None or shape.IsNull():
        return True
    for kind in (TopAbs_ShapeEnum.TopAbs_SOLID,
                 TopAbs_ShapeEnum.TopAbs_FACE,
                 TopAbs_ShapeEnum.TopAbs_EDGE):
        if TopExp_Explorer(shape, kind).More():
            return False
    return True
