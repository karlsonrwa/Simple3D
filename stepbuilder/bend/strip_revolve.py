"""The exact construction of a bent strip: its cross-section revolved.

If the strip is the same shape at every point along the bend - a straight
tail crossing the bend, the ordinary case - the bent strip is exactly its
cross-section revolved about the bend axis: six faces, two of them true
cylinders, no sewing. Whether it IS that shape is decided by measurement
(volume, and the span of the section against the strip's own) rather than
by topology; when it is not, None comes back and the caller wraps or facets
instead. `_prism_of` is the shared "is this a vertical prism" reading.
"""

from __future__ import annotations

import math

from OCP.BRep import BRep_Builder
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.Bnd import Bnd_Box
from OCP.TopAbs import TopAbs_ShapeEnum
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

from .constants import EPS, MIN_ANGLE
from .cut import _plane_face
from .regions import _Strip, _bbox, _is_empty


# How closely the strip must be a straight prism before it is revolved rather
# than faceted: its volume has to equal one cross-section times its width to
# within this fraction.
PRISM_TOLERANCE = 0.002

# How far the cross-section may fall short of the strip's own extent, along the
# bend line and in z, before the strip is not a prism after all. A LENGTH and
# not a fraction, deliberately: what it catches is a feature small enough to
# disappear into the volume it sits in - see _spans_alike.
PRISM_SPAN_TOLERANCE = 1e-3          # 1 micron


def _spans_alike(flat: TopoDS_Shape, face: TopoDS_Shape, strip: _Strip) -> bool:
    """Does the cross-section reach as far as the strip itself does?

    Measured in the strip's own frame - the bend line turned onto X - so a bend
    line at any angle is treated the same way; an axis-aligned box would call
    every diagonal strip a taper.

    Tight boxes (AddOptimal), because Bnd_Box pads by the shape's tolerance and
    the difference that matters here is microns. AddOptimal also follows curved
    edges properly, which a vertex-by-vertex comparison would not: the outline
    this exists to catch bulges along an arc.
    """
    nx, ny = strip.normal
    turn = gp_Trsf()
    turn.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)),
                     -math.atan2(nx, -ny))          # tangent (-ny, nx) -> +X

    def extents(shape: TopoDS_Shape):
        box = Bnd_Box()
        BRepBndLib.AddOptimal_s(
            BRepBuilderAPI_Transform(shape, turn, True).Shape(), box, False, False)
        if box.IsVoid():
            return None
        xmin, _, zmin, xmax, _, zmax = box.Get()
        return xmin, xmax, zmin, zmax

    whole, section = extents(flat), extents(face)
    if whole is None or section is None:
        return False
    return all(abs(a - b) <= PRISM_SPAN_TOLERANCE for a, b in zip(whole, section))


def _revolve_strip(flat: TopoDS_Shape, strip: _Strip) -> TopoDS_Shape | None:
    """The bent strip as a REVOLVED section - exact cylinders, no facets.

    The bend map takes (u across the board, v along the bend, z) to cylindrical
    coordinates about an axis parallel to u: v becomes the angle, z becomes the
    radius, and u is untouched. So if the strip is the same shape at every v -
    a straight tail crossing the bend, which is the ordinary case and what the
    real board has - then the bent strip is exactly its cross-section revolved
    about the bend axis. Six faces instead of fifty, two of them true cylinders,
    and no sewing or repair anywhere.

    "The same shape at every v" is checked by MEASUREMENT rather than by
    topology: one cross-section times the width of the strip must equal the
    strip's volume. A taper, a fillet running into the bend area or a hole
    inside it all break that equality, and then None comes back and the caller
    facets instead. The section is taken a quarter of the way in, where a taper
    shows; at the middle a symmetric one would average out.

    The section is measured inside the solid and then slid to the start of the
    arc, rather than being taken on the boundary face, because a boolean against
    a face that is coincident with the solid's own face is exactly the kind of
    thing that returns something empty on one board in twenty.
    """
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
    from OCP.GProp import GProp_GProps

    width = strip.hi - strip.lo
    if width <= EPS or abs(strip.turn) < math.radians(MIN_ANGLE):
        return None

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(flat, props)
    volume = props.Mass()
    if volume <= 0:
        return None

    box = _bbox(flat)
    if box is None:
        return None

    nx, ny = strip.normal
    cut_at = strip.lo + width / 4.0
    section = BRepAlgoAPI_Common(flat, _plane_face(nx, ny, cut_at, box))
    if not section.IsDone():
        return None
    face = section.Shape()
    if _is_empty(face):
        return None

    BRepGProp.SurfaceProperties_s(face, props)
    area = props.Mass()
    if area <= 0 or abs(area * width - volume) > PRISM_TOLERANCE * volume:
        return None

    # The volume test alone is not enough, and a real board says so. On
    # flex2-a0 the outline runs straight past BEND_1 and then curves outward
    # INSIDE the bend area, reaching 0.0252 mm beyond the straight part by the
    # far edge of the strip. That is 0.04% of the strip's volume - comfortably
    # under PRISM_TOLERANCE - so the strip was revolved as though it were
    # straight, the curve was dropped, and the model came out with a 25 micron
    # ledge along the edge of the flex where the bend ended. Measured, and the
    # number reported from the board matched to the micron.
    #
    # So the section must also SPAN what the strip spans: compared in the
    # strip's own frame, along the bend line and in z. Nothing extra is built
    # for it - the section is already in hand, and the two tight boxes cost
    # nothing next to the booleans around them.
    #
    # What this still cannot see: an extremum strictly inside a curved edge
    # that leaves the box unchanged AND the volume within 0.2%. The wrap is the
    # general construction and is what such a strip falls through to.
    if not _spans_alike(flat, face, strip):
        return None

    slide = gp_Trsf()
    slide.SetTranslation(gp_Vec(-(cut_at - strip.lo) * nx,
                                -(cut_at - strip.lo) * ny, 0.0))
    face = BRepBuilderAPI_Transform(face, slide, True).Shape()

    # MakeRevol only ever turns the positive way about its axis, so a bend that
    # goes the other way flips the axis instead of the angle.
    axis = strip.axis()
    if strip.turn < 0:
        axis = gp_Ax1(axis.Location(), axis.Direction().Reversed())

    builder = BRep_Builder()
    bent = TopoDS_Compound()
    builder.MakeCompound(bent)
    made = 0
    explorer = TopExp_Explorer(face, TopAbs_ShapeEnum.TopAbs_FACE)
    while explorer.More():
        try:
            solid = BRepPrimAPI_MakeRevol(explorer.Current(), axis,
                                          abs(strip.turn)).Shape()
        except Exception:
            return None
        if solid.IsNull() or not BRepCheck_Analyzer(solid).IsValid():
            return None
        builder.Add(bent, solid)
        made += 1
        explorer.Next()

    if not made:
        return None
    return BRepBuilderAPI_Transform(bent, strip.carried, True).Shape()


def _prism_of(shape: TopoDS_Shape):
    """(top faces, z_top, z_bottom) if *shape* is a vertical prism, else None.

    Every piece this module folds is one: the board is built by extruding a
    planar region in z and then cutting it with vertical prisms, so its faces
    are two horizontal planes and walls that all contain the z direction. That
    is what lets the whole solid be rebuilt from its top face alone.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.GeomAbs import GeomAbs_SurfaceType

    flat: list[tuple[float, TopoDS_Shape, float]] = []
    explorer = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        surf = BRepAdaptor_Surface(face)
        kind = surf.GetType()
        if kind == GeomAbs_SurfaceType.GeomAbs_Plane:
            nz = surf.Plane().Axis().Direction().Z()
            if abs(nz) > 0.999:
                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face, props)
                flat.append((props.CentreOfMass().Z(), face, props.Mass()))
            elif abs(nz) > 1.0e-6:
                return None                    # a slanted wall: not a prism
        elif kind == GeomAbs_SurfaceType.GeomAbs_Cylinder:
            if abs(surf.Cylinder().Axis().Direction().Z()) < 0.999:
                return None                    # a hole that is not vertical
        else:
            return None                        # anything else: not our shape
        explorer.Next()

    if not flat:
        return None
    z_top = max(z for z, _, _ in flat)
    z_bottom = min(z for z, _, _ in flat)
    if z_top - z_bottom <= EPS:
        return None
    tops = [(f, a) for z, f, a in flat if abs(z - z_top) < 1.0e-7]
    if not tops:
        return None
    return tops, z_top, z_bottom
