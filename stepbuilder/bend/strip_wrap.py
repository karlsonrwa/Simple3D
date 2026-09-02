"""The general construction of a bent strip: its outline wrapped onto the
cylinder.

Where the revolve refuses - a tail with relief notches, a zone that stops
inside the bend area, a hole - the flat outline is carried into the
cylinder's own parameter space, where the bend map is affine (a line stays a
line, a circle becomes an ellipse), and the two faces of the bent strip are
built ON the cylinder, exactly. `_map_strip` is one function today; plan B5
takes it apart into the frame, the 2-D curves, the wire on a surface, the
walls, and the sewing-and-checking, one commit each.
"""

from __future__ import annotations

import math

from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.TopAbs import TopAbs_ShapeEnum
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape
from OCP.gp import gp_Dir, gp_Pnt

from .constants import EPS, LENGTH_PROBE_STEPS, MIN_ANGLE, SAMPLE_MAX, SAMPLE_MIN, SAMPLE_STEP, SEW_TOL
from .regions import _Strip
from .strip_revolve import PRISM_TOLERANCE, _prism_of


# How far the wrapped solid may weigh from what the bend says it should before
# it is thrown away and the facets used instead.
MAP_VOLUME_TOLERANCE = 0.01


def _map_strip(flat: TopoDS_Shape, strip: _Strip,
               why: list[str] | None = None) -> TopoDS_Shape | None:
    """The bent strip, built by wrapping its outline onto the cylinder.

    This is the general construction, and it works on the shapes the revolve
    refuses: a tail with the relief notches a real flex board carries at the
    ends of its bend line, a zone that stops inside the bend area, a hole.

    **The whole thing rests on one property of the bend map.** In the cylinder's
    own PARAMETER space - angle across the bend, distance along it - the map is
    an affine change of coordinates: the angle is the distance across the bend
    divided by the neutral radius, and the distance along it is untouched. An
    affine map takes a line to a line and a circle to an ellipse; it does not
    bend anything. So the flat outline can be carried into that parameter space
    and the two faces of the bent strip built ON the cylinder, exactly, however
    complicated the outline is.

    What is built, per top face of the flat piece:

    - the same 2D outline serves BOTH cylinders, the inner one and the outer,
      which is what keeps them in registration - they are the same curve, and
      the only difference is the radius of the surface it is drawn on;
    - a ruled wall between each pair of corresponding edges. Where the flat edge
      ran along the bend the wall is a radial plane, where it ran across it is a
      plane at constant distance, and where it ran at an angle it is the ruled
      surface between two helices, which is what it physically is.

    Straight edges keep exact 2D lines. Everything else is sampled and fitted as
    a 2D spline: the SURFACE stays an exact cylinder either way, and only the
    curve trimming it is approximated, to well under a micron.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_MakeSolid, BRepBuilderAPI_MakeWire, BRepBuilderAPI_Sewing,
    )
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepFill import BRepFill
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepLib import BRepLib
    from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
    from OCP.GProp import GProp_GProps
    from OCP.Geom import Geom_CylindricalSurface
    from OCP.Geom2d import Geom2d_Ellipse, Geom2d_Line, Geom2d_TrimmedCurve
    from OCP.Geom2dAPI import Geom2dAPI_PointsToBSpline
    from OCP.GeomAbs import GeomAbs_CurveType
    from OCP.TColgp import TColgp_Array1OfPnt2d
    from OCP.TopAbs import TopAbs_Orientation
    from OCP.TopoDS import TopoDS_Vertex
    from OCP.gp import gp_Ax3, gp_Ax22d, gp_Dir2d, gp_Pnt2d, gp_Vec2d

    def give_up(reason: str) -> None:
        """Say which step refused, so a board that facets can be diagnosed."""
        if why is not None and not why:
            why.append(reason)
        return None

    width = strip.hi - strip.lo
    if width <= EPS or abs(strip.turn) < math.radians(MIN_ANGLE):
        return give_up("the strip has no width or no angle")
    rho = width / abs(strip.turn)          # the neutral radius, back out of it

    # A layer can arrive as several disjoint solids - a stiffener that the bend
    # area clips at both ends is two - and each is wrapped on its own. Sewing
    # them together would be asking for one shell out of pieces that do not
    # touch.
    separate = []
    explorer = TopExp_Explorer(flat, TopAbs_ShapeEnum.TopAbs_SOLID)
    while explorer.More():
        separate.append(explorer.Current())
        explorer.Next()
    if len(separate) > 1:
        builder = BRep_Builder()
        compound = TopoDS_Compound()
        builder.MakeCompound(compound)
        for piece in separate:
            one = _map_strip(piece, strip, why)
            if one is None:
                return None
            builder.Add(compound, one)
        return compound

    prism = _prism_of(flat)
    if prism is None:
        return give_up("the piece is not a prism standing on a flat face")
    tops, z_top, z_bottom = prism

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(flat, props)
    volume = props.Mass()
    area = sum(a for _, a in tops)
    thickness = z_top - z_bottom
    if volume <= 0 or abs(area * thickness - volume) > PRISM_TOLERANCE * volume:
        return give_up("the piece is not the extrusion of its own top face")

    # the cylinder frame: Z along the bend line, X pointing at the flat board
    nx, ny = strip.normal
    sign = 1.0 if strip.turn > 0 else -1.0
    origin = gp_Pnt(nx * strip.lo, ny * strip.lo, strip.axis_z)
    along = gp_Dir(ny, -nx, 0.0) if sign > 0 else gp_Dir(-ny, nx, 0.0)
    frame = gp_Ax3(origin, along, gp_Dir(0.0, 0.0, -sign))
    r_top = abs(strip.axis_z - z_top)
    r_bottom = abs(strip.axis_z - z_bottom)
    if min(r_top, r_bottom) <= EPS:
        return None                        # the axis runs through the material
    cyl_top = Geom_CylindricalSurface(frame, r_top)
    cyl_bottom = Geom_CylindricalSurface(frame, r_bottom)

    ax, ay = origin.X(), origin.Y()
    zx, zy = along.X(), along.Y()

    def to2d(point: gp_Pnt) -> gp_Pnt2d:
        """A flat point as (angle across the bend, distance along it)."""
        dx, dy = point.X() - ax, point.Y() - ay
        return gp_Pnt2d((nx * dx + ny * dy) / rho, zx * dx + zy * dy)

    def sampled(adaptor, first, last):
        """A stretch of one flat edge, as a 2D spline in parameter space."""
        length = 0.0
        previous = adaptor.Value(first)
        for i in range(1, LENGTH_PROBE_STEPS + 1):   # rough length, for the density
            here = adaptor.Value(first + (last - first) * i / LENGTH_PROBE_STEPS)
            length += previous.Distance(here)
            previous = here
        count = min(SAMPLE_MAX, max(SAMPLE_MIN, int(length / SAMPLE_STEP) + SAMPLE_MIN))
        points = TColgp_Array1OfPnt2d(1, count)
        for i in range(count):
            t = first + (last - first) * i / (count - 1)
            points.SetValue(i + 1, to2d(adaptor.Value(t)))
        curve = Geom2dAPI_PointsToBSpline(points).Curve()
        return curve, curve.FirstParameter(), curve.LastParameter()

    def curves2d(edge):
        """One flat edge as 2D curves in the cylinder's parameter space.

        A CLOSED edge - a drill hole is one circle and nothing else - comes back
        as two halves. Sampling it whole would hand the fitter a point list whose
        first and last point are the same, and the curve that comes out of that
        is not a curve.
        """
        adaptor = BRepAdaptor_Curve(edge)
        first, last = adaptor.FirstParameter(), adaptor.LastParameter()
        if edge.Orientation() == TopAbs_Orientation.TopAbs_REVERSED:
            first, last = last, first

        if adaptor.GetType() == GeomAbs_CurveType.GeomAbs_Line:
            start, end = to2d(adaptor.Value(first)), to2d(adaptor.Value(last))
            step = gp_Vec2d(start, end)
            length = step.Magnitude()
            if length < 1.0e-9:
                return None
            return [(Geom2d_TrimmedCurve(Geom2d_Line(start, gp_Dir2d(step)),
                                         0.0, length), 0.0, length)]

        if adaptor.GetType() == GeomAbs_CurveType.GeomAbs_Circle:
            # An arc becomes an ELLIPSE, exactly: the map scales one axis and
            # leaves the other, and that is all a circle needs to become one.
            #
            # This is not a nicety. Sampling a relief notch as a spline puts a
            # wiggle of a few nanometres at its ends, where it meets the
            # straight edge it was cut into, and OCC calls the wire
            # self-intersecting and throws the whole solid away. Every FLEX2
            # layer of the real board failed exactly there.
            circle = adaptor.Circle()
            centre = to2d(circle.Location())
            across, along = circle.Radius() / rho, circle.Radius()
            if across >= along:
                axes = gp_Ax22d(centre, gp_Dir2d(1.0, 0.0), gp_Dir2d(0.0, 1.0))
                major, minor = across, along
            else:
                axes = gp_Ax22d(centre, gp_Dir2d(0.0, 1.0), gp_Dir2d(-1.0, 0.0))
                major, minor = along, across
            if minor < 1.0e-12:
                return None
            ellipse = Geom2d_Ellipse(axes, major, minor)

            def where(point) -> float:
                step = gp_Vec2d(centre, point)
                return math.atan2(
                    step.Dot(gp_Vec2d(axes.YDirection())) / minor,
                    step.Dot(gp_Vec2d(axes.XDirection())) / major) % (2 * math.pi)

            start = where(to2d(adaptor.Value(first)))
            end = where(to2d(adaptor.Value(last)))
            middle = where(to2d(adaptor.Value((first + last) / 2.0)))
            forward = (middle - start) % (2 * math.pi) <= (end - start) % (2 * math.pi)
            if adaptor.Value(first).Distance(adaptor.Value(last)) < 1.0e-9:
                span = 2 * math.pi                     # a whole circle: a hole
                forward = True
            elif forward:
                span = (end - start) % (2 * math.pi)
            else:
                span = (start - end) % (2 * math.pi)
            low = start if forward else end
            curve = Geom2d_TrimmedCurve(ellipse, low, low + span, forward)
            return [(curve, curve.FirstParameter(), curve.LastParameter())]

        if adaptor.Value(first).Distance(adaptor.Value(last)) < 1.0e-9:
            middle = (first + last) / 2.0
            return [sampled(adaptor, first, middle),
                    sampled(adaptor, middle, last)]
        return [sampled(adaptor, first, last)]

    def wire_on(surface, curves):
        """The wrapped outline as a wire ON *surface*, sharing its corners.

        Each edge is rebuilt from its own 2D curve, so where two of them meet
        the two surface points agree only as well as the FLAT solid's own
        vertices did - a couple of tenths of a micron on a shape that came out
        of a boolean, which is well inside the tolerance the flat shape carries
        on that vertex and therefore perfectly legal there.

        BRepBuilderAPI_MakeWire joins edges by comparing vertices at
        Precision::Confusion, a flat 1e-7 that nothing can widen, and when the
        gap is bigger than that it does not report a failure: it starts a
        second wire, and IsDone() comes back TRUE as soon as some later edge
        closes a loop - having silently dropped the rest. Measured on the real
        board: a four-edge outline came back as a wire of two, the two missing
        walls stayed unsewn, the shell never closed and the bend fell back to
        facets, with nothing in the log but "not valid".

        So the corners are made explicit. One vertex per junction, placed
        between the two curve ends with a tolerance wide enough to reach both,
        and every edge is built on the vertices its neighbours share: the wire
        is then connected by TOPOLOGY and no tolerance decides anything. The
        edge count is checked anyway, because this is exactly the kind of
        failure that is invisible until a solid comes out inside out.
        """
        count = len(curves)
        if not count:
            return None

        ends = []
        for curve, first, last in curves:
            head, tail = curve.Value(first), curve.Value(last)
            ends.append((surface.Value(head.X(), head.Y()),
                         surface.Value(tail.X(), tail.Y())))

        builder = BRep_Builder()
        corners = []
        for i in range(count):
            here, there = ends[i][1], ends[(i + 1) % count][0]
            corner = TopoDS_Vertex()
            builder.MakeVertex(
                corner,
                gp_Pnt((here.X() + there.X()) / 2.0,
                       (here.Y() + there.Y()) / 2.0,
                       (here.Z() + there.Z()) / 2.0),
                here.Distance(there) / 2.0 + 1.0e-7)
            corners.append(corner)

        maker = BRepBuilderAPI_MakeWire()
        for i, (curve, first, last) in enumerate(curves):
            edge = BRepBuilderAPI_MakeEdge(curve, surface, corners[i - 1],
                                           corners[i], first, last)
            if not edge.IsDone():
                return None
            maker.Add(edge.Edge())
        if not maker.IsDone():
            return None
        wire = maker.Wire()

        kept = 0
        walker = TopExp_Explorer(wire, TopAbs_ShapeEnum.TopAbs_EDGE)
        while walker.More():
            kept += 1
            walker.Next()
        if kept != count:
            return None

        BRepLib.BuildCurves3d_s(wire)
        return wire

    sewing = BRepBuilderAPI_Sewing(SEW_TOL)
    for face, _ in tops:
        outer = BRepTools.OuterWire_s(face)
        wires = []
        explorer = TopExp_Explorer(face, TopAbs_ShapeEnum.TopAbs_WIRE)
        while explorer.More():
            wire = TopoDS.Wire_s(explorer.Current())
            wires.append((wire, wire.IsSame(outer)))
            explorer.Next()

        mapped: list[tuple[list, bool]] = []
        for wire, is_outer in wires:
            curves = []
            walker = BRepTools_WireExplorer(wire)
            while walker.More():
                one = curves2d(walker.Current())
                if one is None:
                    return give_up("an edge of the outline could not be carried "
                                   "onto the cylinder")
                curves.extend(one)
                walker.Next()
            if not curves:
                return give_up("a wire of the outline came back empty")
            mapped.append((curves, is_outer))

        for surface in (cyl_top, cyl_bottom):
            built = None
            for curves, is_outer in sorted(mapped, key=lambda m: not m[1]):
                wire = wire_on(surface, curves)
                if wire is None:
                    return give_up("the wrapped outline did not close into a wire")
                if built is None:
                    maker = BRepBuilderAPI_MakeFace(surface, wire, True)
                else:
                    # A hole. Its wire runs the opposite way round to the outer
                    # one on the flat face, and it has to keep doing so here, or
                    # the face comes out with the hole as its material.
                    maker = BRepBuilderAPI_MakeFace(built, TopoDS.Wire_s(wire.Reversed()))
                if not maker.IsDone():
                    return give_up("the wrapped outline did not close into a face")
                built = maker.Face()
            if built is None:
                return give_up("no face came out of the wrapped outline")
            sewing.Add(built)

        # the walls, one per edge, ruled between the two cylinders
        for curves, _ in mapped:
            for curve, first, last in curves:
                top_edge = BRepBuilderAPI_MakeEdge(curve, cyl_top, first, last)
                bottom_edge = BRepBuilderAPI_MakeEdge(curve, cyl_bottom, first, last)
                if not (top_edge.IsDone() and bottom_edge.IsDone()):
                    return give_up("a wall edge could not be built")
                one, two = top_edge.Edge(), bottom_edge.Edge()
                BRepLib.BuildCurves3d_s(one)
                BRepLib.BuildCurves3d_s(two)
                try:
                    wall = BRepFill.Face_s(one, two)
                except Exception as exc:
                    return give_up(f"a wall could not be ruled ({exc})")
                if wall.IsNull():
                    return give_up("a wall came out empty")
                sewing.Add(wall)

    sewing.Perform()
    shell = sewing.SewedShape()
    if shell.IsNull():
        return give_up("the faces did not sew together")

    solid = None
    explorer = TopExp_Explorer(shell, TopAbs_ShapeEnum.TopAbs_SHELL)
    if explorer.More():
        maker = BRepBuilderAPI_MakeSolid(TopoDS.Shell_s(explorer.Current()))
        if maker.IsDone():
            solid = maker.Solid()
    if solid is None or solid.IsNull():
        return give_up("the sewn faces did not make a closed shell")
    if not BRepCheck_Analyzer(solid).IsValid():
        return give_up("the solid built from them is not valid")

    # The ITERATIVE integrator, not the plain call. A solid with B-spline walls
    # measures 1.5% light through the default one - which sent every wrapped
    # piece of the real board back to the facets, for a defect that was in the
    # measurement and not in the geometry. With eps it agrees with the closed
    # form to 2e-6.
    BRepGProp.VolumeProperties_s(solid, props, 1.0e-5, False, False)
    made = props.Mass()
    if made < 0:                            # sewn inside out
        solid = TopoDS.Solid_s(solid.Reversed())
        made = -made

    # What the piece SHOULD weigh once bent, which is not what it weighed flat.
    #
    # The map multiplies volume by r/rho - material at a bigger radius than the
    # neutral one is stretched, material inside it is compressed - so a layer
    # above the core gains and one below loses, and only a stack symmetric about
    # the neutral axis comes out unchanged. Integrated over a prism that is
    # exactly `r at mid-thickness over rho`.
    #
    # Measured on the real board's stiffener zone: 0.937 for the top coverlay,
    # 1.000 for the dielectric at the core, 1.063 for the bottom coverlay -
    # symmetric about the middle, which is the bend being isometric. Checking
    # for the flat volume instead rejected every layer but the middle one.
    expected = volume * abs(strip.axis_z - (z_top + z_bottom) / 2.0) / rho
    if expected <= 0 or abs(made - expected) > MAP_VOLUME_TOLERANCE * expected:
        return give_up(f"it came out weighing {made:.6f} where the bend should "
                       f"make it {expected:.6f}")

    return BRepBuilderAPI_Transform(solid, strip.carried, True).Shape()
