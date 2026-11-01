"""A zone drawn inside another (round 127, R3-6 and R3-7 of the 23.10.2026
review).

Allegro nests stackup zones since release 22.1 QIR2: Cadence's migration
guide for 24.1 (Database Format) says a design with nested zones saves back
no further than that release, and Cadence's BoardSurfers blog of 18.04.2023
says what one is for - an area of a zone that needs another soldermask or
plating, drawn as a second zone inside it, its stack differing in the mask
layers and matching in the etch. The inner zone is that area's stack; the
zone around it holds the rest. Zones that cross are still not allowed:
Allegro trims a new zone to the old one's boundary. (Cadence's rigid-flex
book of 25.1 still says zones cannot be "overlapped or nested"; the second
half is out of date.) Allegro answers the same way: `axlZoneAccess('point)`
names the inner zone at every point of the owner's nested areas, and a part
placed there is in the inner zone.

Until this round every zone whose contour held a point counted there, so a
nested area had both stacks. The fused body hid it on the owner's boards -
the outer stack's material inside the inner zone lies within the inner
stack's on all three pairs, measured - but the Not stitched build kept both,
2.70 % (flex-b2) and 10.9 % (flex2-a0) too much board, and a thin zone inside
a thick one was built thick. Now a zone's own region is its contour less the
zones nested in it, and every question about a point asks that: `nest` finds
the nesting once, `own_face` gives the region as a face, `in_nested` answers
for a point against a zone's polygon.
"""

from __future__ import annotations

from .contour import _face_from_wires, build_contour, contour_points, point_in_polygon, point_on_polygon
from .errors import StepBuilderError
from .reporting import LogFn, _noop_log

# How much of a zone may lie outside another, as a share of its own area, and
# it still be inside it: boolean noise, not geometry. On the boards on hand a
# nested zone lies inside to the last digit (0.0 mm2 outside on flex-b2 and
# flex2-a0), and the two zones there that only touch share 5e-9 of the
# smaller one.
NEST_SHARE = 1.0e-6
# How far a zone's box may reach past another's and the boolean still be
# asked: a face's box carries its tolerance, 1e-7 mm.
BOX_GAP = 1.0e-5


def _area(shape) -> float:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, props)
    return abs(props.Mass())


def _box(face) -> tuple[float, float, float, float]:
    """The face's own box, arcs and all - a box of the polygon sampled from
    the contour lies inside an arc's bulge."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(face, box, False)
    x0, y0, _z0, x1, y1, _z1 = box.Get()
    return x0, y0, x1, y1


def nest(zones: list[dict], log: LogFn = _noop_log) -> list[dict]:
    """*zones*, a zone that has others inside it given their contours under
    "nested" (a new dict; the others are handed back as they were), and a
    line in the log for each zone inside another.

    A zone is inside another when no more than NEST_SHARE of its area lies
    outside it and it is the smaller of the two. A contour that makes no face
    is left alone here: the body's build names it (board._board_face)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common

    faces, areas, boxes = [], [], []
    for zone in zones:
        face, area, box = None, 0.0, None
        try:
            if zone.get("contour"):
                face = _face_from_wires(build_contour(zone["contour"], 0.0), [])
                area, box = _area(face), _box(face)
        except (StepBuilderError, RuntimeError, KeyError, TypeError, ValueError, IndexError):
            face = None
        faces.append(face)
        areas.append(area)
        boxes.append(box)

    inside: dict[int, list[int]] = {}
    for i, outer in enumerate(faces):
        for j, inner in enumerate(faces):
            if i == j or outer is None or inner is None or not areas[j] < areas[i]:
                continue
            (ix0, iy0, ix1, iy1), (ox0, oy0, ox1, oy1) = boxes[j], boxes[i]
            if ix0 < ox0 - BOX_GAP or iy0 < oy0 - BOX_GAP or ix1 > ox1 + BOX_GAP or iy1 > oy1 + BOX_GAP:
                continue                       # sticks out of its box: not inside it
            common = BRepAlgoAPI_Common(inner, outer)
            if common.IsDone() and areas[j] - _area(common.Shape()) <= NEST_SHARE * areas[j]:
                inside.setdefault(i, []).append(j)

    out = []
    for i, zone in enumerate(zones):
        if i not in inside:
            out.append(zone)
            continue
        out.append(dict(zone, nested=[zones[j]["contour"] for j in inside[i]]))
        for j in inside[i]:
            log(f"Zone {zones[j]['name']} lies inside zone {zone['name']}: the board there is "
                f"{zones[j]['name']}'s stack ({zones[j].get('stackup')}), not both")
    return out


def own_face(contour: list, nested: list | None, z: float):
    """A zone's own region at height *z*: the face of its *contour* less the
    zones *nested* in it - a face, or a compound of faces where they cut it
    apart. The nested zones go to the boolean as SEPARATE tools, as cutouts
    do (board._cut_out)."""
    face = _face_from_wires(build_contour(contour, z), [])
    if not nested:
        return face
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut

    from ._occt import TopTools_ListOfShape

    arguments = TopTools_ListOfShape()
    arguments.Append(face)
    tools = TopTools_ListOfShape()
    for inner in nested:
        tools.Append(_face_from_wires(build_contour(inner, z), []))
    cut = BRepAlgoAPI_Cut()
    cut.SetArguments(arguments)
    cut.SetTools(tools)
    cut.Build()
    if not cut.IsDone():
        raise StepBuilderError("the zones inside a zone could not be taken out of it")
    return cut.Shape()


def nested_polygons(zone: dict) -> list:
    """The zones nested in *zone*, as flat polygons."""
    return [contour_points(c) for c in zone.get("nested") or []]


def in_nested(point: tuple[float, float], polygons: list) -> bool:
    """Is the flat *point* inside one of the zones nested in a zone - and so
    in that zone, not in this one? On a nested zone's edge it is in both."""
    return any(point_in_polygon(point, poly) and not point_on_polygon(point, poly) for poly in polygons)
