"""The copper pads: from the intermediate's padstack library and pin rows to
copper-coloured surfaces lying on the board's outer faces (round 85).

What the picture needs is the copper a pad shows through the mask, on the
two outer faces, in the copper colour. What it does not need is a body per
pad or a window per pad cut into the mask: a boolean over thousands of pad
prisms is minutes of OCCT time on a dense board and a real chance of an
empty result, and a picture cannot tell a flush copper pad from a face one
micron above the mask. So a pad is a FACE, lifted the same micron a flat
silkscreen is (`silk_flat_height`), and the board body is never touched.

The intermediate carries a LIBRARY (format_version 10, `pads`): one entry
per padstack with its drill and its REGULAR pads on the ETCH layers, each
with the outline Allegro itself holds for it (an axlPath, in the same
segment / arc / circle vocabulary as the board outline - every figure kind
carries one), and one row per pin: position, rotation, mirror, padstack,
and the pin's own layer span. From those:

* `pin_sides` decides which outer FACE(S) of the pin's zone the pin reaches
  and which pad figure goes there. The span does it, not the mirror flag:
  measured on Cadence's demo board, 48 of 2720 pins sit on INNER1 or span
  INNER1..INNER2 - the flex zone's outer copper - and have no pad on TOP or
  BOTTOM at all. A padstack with ONE etch pad is a surface padstack and that
  pad goes to the layer the span names, whatever the pad's own layer is
  called ("ETCH/TOP" there means "the side the part sits on"). A padstack
  with several is looked up by layer name, its etch list read backwards for
  a mirrored pin - Allegro flips the padstack with the part.
* `pad_face` builds one face per (padstack, layer, mirrored) at the origin:
  the outline, a DONUT's inside diameter as a hole, the drill cut out so the
  hole in the board stays visible, and the whole figure mirrored (x -> -x)
  for a mirrored pin before it is rotated - the same order Allegro applies.
  Built ONCE and instanced per pin, like a component model: a face costs its
  edges and surface every time it is written, an instance costs a placement.
* `build_pads` places every pin: one shared part per figure under
  `pads_top_<board>` / `pads_bot_<board>`, at the zone's outer face, through
  the fold plan where there is one.

Vias are not in the intermediate and not drawn: they are tented under the
mask on nearly every board.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_Transform
from OCP.Bnd import Bnd_Box
from OCP.GC import GC_MakeArcOfCircle
from OCP.GeomAbs import GeomAbs_SurfaceType
from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
from OCP.TopAbs import TopAbs_FACE, TopAbs_Orientation
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopTools import TopTools_HSequenceOfShape
from OCP.TopoDS import TopoDS, TopoDS_Face, TopoDS_Shape, TopoDS_Wire
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

from .contour import (WIRE_TOLERANCE, _face_from_wires, _open_wire_detail, build_contour,
                      contour_points, point_in_polygon)
from .errors import StepBuilderError
from .reporting import LogFn, _noop_log
from .stackup import _is_conductor, board_stackup

# A pad's declared bounding box (of the figure, about its own centre) shifted
# by the declared offset has to land this close (design units) to the box of
# the outline for the outline to be read as already in place. 0.02 clears
# the 0.01-mil rounding of a board laid out in mils and is well under any
# real offset - see _settle_offset.
BOX_TOLERANCE = 0.02

# How far apart two consecutive pieces of a pad's outline may end and start
# and still be joined. Allegro keeps a path arc's CENTRE to the design's
# resolution, so the radius measured from one end is not the radius to the
# other: on the user's my_test_board2 a ROUNDED_RECTANGLE's corner arc had
# 0.19985 from its centre to one end and 0.1999 to the other, and an arc
# rebuilt on the first radius missed the next line by 0.05 um - five times
# the wire tolerance, and the pad came out as four open wires. The two END
# POINTS are exact; the centre is the rounded thing. So a pad arc is built
# THROUGH its two ends and the midpoint of the exported arc (`_pad_wire`),
# and this is how close a neighbour's start has to be to count as that end.
JOIN_TOLERANCE = 1.0e-3


# --------------------------------------------------------------------------- #
# which face, which figure
# --------------------------------------------------------------------------- #

def layer_subclass(layer) -> str:
    """'ETCH/TOP' -> 'TOP', upper-cased; '' for nothing."""
    if not layer:
        return ""
    text = str(layer)
    return text.rpartition("/")[2].strip().upper()


def outer_conductors(stackup: dict | None) -> tuple[str, str]:
    """(top conductor, bottom conductor) of one stackup by POSITION, upper-cased
    subclass names; ('', '') when it has no conductor. List order is the
    physical order (`layer->position` is not - stackup.restack says why)."""
    names = [layer_subclass(lay.get("name")) for lay in (stackup or {}).get("layers") or []
             if isinstance(lay, dict) and _is_conductor(lay)]
    if not names:
        return "", ""
    return names[0], names[-1]


def etch_pads(padstack: dict) -> list[tuple[str, dict]]:
    """The padstack's REGULAR pads on ETCH layers as [(subclass, pad)], in the
    order the file lists them - the exporter writes them in Allegro's own
    order, top of the stack first."""
    out = []
    for layer, pad in (padstack.get("pads") or {}).items():
        if str(layer).upper().startswith("ETCH/") and isinstance(pad, dict):
            out.append((layer_subclass(layer), pad))
    return out


def pin_sides(pin: dict, padstack: dict, top: str, bottom: str) -> list[tuple[str, dict]]:
    """[(face, pad)] for one pin: which of the zone's outer faces ("top",
    "bottom") its copper reaches, and the pad figure that goes there.

    *top* / *bottom* are the outer conductor names of the pin's zone.
    """
    pads = etch_pads(padstack)
    if not pads:
        return []
    start, end = layer_subclass(pin.get("start")), layer_subclass(pin.get("end"))
    mirrored = bool(pin.get("mirrored"))

    if len(pads) == 1:
        # A surface padstack: one pad, placed where the span says. With no
        # span (a pin the exporter could not ask) the mirror flag decides.
        _, pad = pads[0]
        if not start:
            return [("bottom" if mirrored else "top", pad)]
        faces = []
        if start == top:
            faces.append(("top", pad))
        if start == bottom and start != top:
            faces.append(("bottom", pad))
        return faces

    # Several etch pads: a through (or blind) padstack defined layer by
    # layer. Mirrored, the stack is read backwards - the pad drawn for TOP
    # lands on BOTTOM.
    by_layer = {name: pad for name, pad in pads}
    if mirrored:
        names = [name for name, _ in pads]
        by_layer = {name: pads[len(pads) - 1 - i][1] for i, name in enumerate(names)}

    if not start and not end:
        span = {top, bottom}
    else:
        span = {start, end}
    faces = []
    if top and top in span and top in by_layer:
        faces.append(("top", by_layer[top]))
    if bottom and bottom in span and bottom != top and bottom in by_layer:
        faces.append(("bottom", by_layer[bottom]))
    return faces


# --------------------------------------------------------------------------- #
# one figure as a face
# --------------------------------------------------------------------------- #

def _rect_contour(bbox) -> list[dict]:
    (x0, y0), (x1, y1) = bbox
    return [{"type": "segment", "start": [x0, y0], "end": [x1, y0]},
            {"type": "segment", "start": [x1, y0], "end": [x1, y1]},
            {"type": "segment", "start": [x1, y1], "end": [x0, y1]},
            {"type": "segment", "start": [x0, y1], "end": [x0, y0]}]


def _tight_box(shape: TopoDS_Shape) -> tuple[float, float, float, float]:
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    x0, y0, _, x1, y1, _ = box.Get()
    return x0, y0, x1, y1


def _boxes_agree(a, b) -> bool:
    return all(abs(p - q) <= BOX_TOLERANCE for p, q in zip(a, b))


def _settle_offset(face: TopoDS_Face, pad: dict) -> tuple[TopoDS_Face, str | None]:
    """The outline is Allegro's path, and it already includes the padstack's
    offset; the declared bounding box is the figure's own, about its centre.
    MEASURED on the Dell board (fifteen padstacks with an offset, SHAPE and
    RECTANGLE alike): an outline running 0..29.53 against a box of +-14.77
    and an offset of 14.76 - so box + offset = outline, every time.

    The three facts are still checked per pad rather than trusted: when the
    outline's box is the declared box shifted by the offset, the path is in
    place (the normal case, offset 0 included); when it is the declared box
    itself and the offset is not zero, the path is the figure-centred one
    and is moved by the offset; when neither, the path is kept and the
    disagreement reported."""
    declared = pad.get("bbox")
    offset = pad.get("offset") or [0.0, 0.0]
    if not declared:
        return face, None
    ox, oy = float(offset[0]), float(offset[1])
    box = (float(declared[0][0]), float(declared[0][1]),
           float(declared[1][0]), float(declared[1][1]))
    placed = (box[0] + ox, box[1] + oy, box[2] + ox, box[3] + oy)
    got = _tight_box(face)
    if _boxes_agree(got, placed):
        return face, None
    if (abs(ox) > 1e-9 or abs(oy) > 1e-9) and _boxes_agree(got, box):
        trsf = gp_Trsf()
        trsf.SetTranslation(gp_Vec(ox, oy, 0.0))
        return TopoDS.Face_s(BRepBuilderAPI_Transform(face, trsf, True).Shape()), None
    return face, (f"outline box ({got[0]:.4f}, {got[1]:.4f})..({got[2]:.4f}, {got[3]:.4f}) "
                  f"is neither the declared box ({box[0]:.4f}, {box[1]:.4f})..({box[2]:.4f}, "
                  f"{box[3]:.4f}) nor that box at its offset ({ox:.4f}, {oy:.4f}); "
                  f"the outline is used as it is")


def _arc_point(prim: dict, degrees: float) -> tuple[float, float]:
    cx, cy, r = float(prim["center"][0]), float(prim["center"][1]), float(prim["radius"])
    a = math.radians(degrees)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def _arc_ends(prim: dict) -> tuple[tuple[float, float], tuple[float, float], float]:
    """(start, end, mid angle in degrees) of an arc primitive in the direction
    of TRAVEL: alpha..beta bound it counter-clockwise, and `ccw` says which end
    the contour enters it by (contour.build_contour has the whole story)."""
    alpha, beta = float(prim["alpha"]), float(prim["beta"])
    while beta < alpha:
        beta += 360.0
    a, b = _arc_point(prim, alpha), _arc_point(prim, beta)
    mid = (alpha + beta) / 2.0
    return (a, b, mid) if prim.get("ccw", True) else (b, a, mid)


def _prim_start(prim: dict) -> tuple[float, float] | None:
    kind = prim.get("type", "segment")
    if kind == "segment":
        return float(prim["start"][0]), float(prim["start"][1])
    if kind == "arc":
        return _arc_ends(prim)[0]
    return None


def _near(p, q) -> bool:
    return p is not None and q is not None and math.hypot(p[0] - q[0], p[1] - q[1]) <= JOIN_TOLERANCE


def _pad_wire(outline: list) -> TopoDS_Wire:
    """A pad outline as a closed wire, its pieces joined END TO END.

    The exporter walks the padstack's path in order, so each piece starts
    where the last one ended - and those end points are exact where an arc's
    centre is only as exact as the design's resolution (see JOIN_TOLERANCE).
    A segment is built between its own points. An arc is built THROUGH three
    points: where the previous piece ended, the midpoint of the exported arc,
    and where the next piece starts (the first piece's start for the last
    one) - each taken from the neighbour when it is within JOIN_TOLERANCE of
    the arc's own end, and from the arc itself otherwise. The wire then
    closes by construction. A lone circle goes through build_contour.
    """
    prims = [p for p in outline if p.get("type") in ("segment", "arc", "circle")]
    if len(prims) == 1 and prims[0].get("type") == "circle":
        return build_contour(prims, 0.0)

    edges = []
    current = _prim_start(prims[0]) if prims else None
    for i, prim in enumerate(prims):
        kind = prim.get("type", "segment")
        nxt = prims[(i + 1) % len(prims)]
        if kind == "segment":
            start = (float(prim["start"][0]), float(prim["start"][1]))
            end = (float(prim["end"][0]), float(prim["end"][1]))
            if math.dist(start, end) > 1.0e-12:
                edges.append(BRepBuilderAPI_MakeEdge(gp_Pnt(*start, 0.0), gp_Pnt(*end, 0.0)).Edge())
            current = end
        elif kind == "arc":
            own_start, own_end, mid_deg = _arc_ends(prim)
            start = current if _near(current, own_start) else own_start
            after = _prim_start(nxt) if len(prims) > 1 else None
            end = after if _near(after, own_end) else own_end
            mid = _arc_point(prim, mid_deg)
            if math.dist(start, end) < 1.0e-9:
                # An arc that closes on itself is a circle - the exporter
                # writes those as circles, but be safe.
                edges.append(build_contour([{"type": "circle", "x": prim["center"][0],
                                             "y": prim["center"][1], "radius": prim["radius"]}],
                                           0.0))
            else:
                arc = GC_MakeArcOfCircle(gp_Pnt(*start, 0.0), gp_Pnt(*mid, 0.0),
                                         gp_Pnt(*end, 0.0)).Value()
                edges.append(BRepBuilderAPI_MakeEdge(arc).Edge())
            current = end
        else:
            raise StepBuilderError("a circle among other pieces of a pad outline")
    if not edges:
        raise StepBuilderError("pad outline has no pieces")

    sequence = TopTools_HSequenceOfShape()
    for edge in edges:
        sequence.Append(edge)
    wires = TopTools_HSequenceOfShape()
    ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(sequence, WIRE_TOLERANCE, False, wires)
    if wires.Length() != 1:
        raise StepBuilderError(f"pad outline is not one loop: its pieces formed {wires.Length()} wires")
    wire = TopoDS.Wire_s(wires.Value(1))
    if not wire.Closed():
        raise StepBuilderError("pad outline is open" + _open_wire_detail(wire))
    return wire


def _first_face(shape: TopoDS_Shape) -> TopoDS_Face | None:
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    return TopoDS.Face_s(exp.Current()) if exp.More() else None


def _normal_up(face: TopoDS_Face) -> bool | None:
    """Does the face's ORIENTED normal point +z? None for a non-planar face."""
    surface = BRepAdaptor_Surface(face)
    if surface.GetType() != GeomAbs_SurfaceType.GeomAbs_Plane:
        return None
    z = surface.Plane().Axis().Direction().Z()
    if face.Orientation() == TopAbs_Orientation.TopAbs_REVERSED:
        z = -z
    return z > 0.0


def pad_face(pad: dict, hole: list | None, mirrored: bool, face_up: bool = True) -> tuple[TopoDS_Face | None, str | None]:
    """One pad figure as a planar face at the origin, z = 0, ready to be placed.

    Returns (face, note): the face is None when the figure cannot be built
    or has nothing left once its hole is cut out; the note, when there is
    one, is a line for the log (a box disagreement, an empty figure).

    *face_up* says which way the face's normal should point: up for the top
    side, down for the bottom, so a viewer that culls back faces shows the
    pad from the side it is on.
    """
    outline = pad.get("outline")
    if not outline:
        bbox = pad.get("bbox")
        if not bbox:
            return None, "no outline and no bounding box"
        outline = _rect_contour(bbox)

    outer = _pad_wire(outline)
    inner = []
    inside = float(pad.get("inside") or 0.0)
    if inside > 0.0 and pad.get("bbox"):
        (x0, y0), (x1, y1) = pad["bbox"]
        inner.append(build_contour([{"type": "circle", "x": (x0 + x1) / 2.0,
                                     "y": (y0 + y1) / 2.0, "radius": inside / 2.0}], 0.0))
    face = _face_from_wires(outer, inner)
    face, note = _settle_offset(face, pad)

    if hole:
        cutter = _face_from_wires(build_contour(hole, 0.0), [])
        cut = BRepAlgoAPI_Cut(face, cutter)
        if not cut.IsDone():
            return None, "the drill could not be cut out of the pad"
        left = _first_face(cut.Shape())
        if left is None:
            # A mounting hole with a nominal pad smaller than its drill: the
            # copper is all hole. Ordinary, not an error - no note, and the
            # caller counts it as a pad that is all hole.
            return None, None
        face = left

    if mirrored:
        mirror = gp_Trsf()
        mirror.SetMirror(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)))
        face = TopoDS.Face_s(BRepBuilderAPI_Transform(face, mirror, True).Shape())

    up = _normal_up(face)
    if up is not None and up != face_up:
        face = TopoDS.Face_s(face.Reversed())
    return face, note


# --------------------------------------------------------------------------- #
# placing every pin
# --------------------------------------------------------------------------- #

@dataclass
class PadsResult:
    placed: int = 0                 # pad faces placed (a through pin counts twice)
    pins: int = 0                   # pin rows read
    figures: int = 0                # distinct (padstack, layer, mirrored) faces built
    no_outer_face: int = 0          # pins whose span reaches no outer face of their zone
    no_padstack: int = 0            # pins naming a padstack the library lacks
    unbuildable: int = 0            # figures that could not be built
    all_hole: int = 0               # pads placed on nothing: the drill is larger than the pad
    in_bend: int = 0                # pins standing in a bend area
    notes: list[str] = field(default_factory=list)


def _placement(x: float, y: float, z: float, rotation: float, fold) -> gp_Trsf:
    """Rotate about the pin, move to the pin, then wherever the fold takes it."""
    turn = gp_Trsf()
    if abs(rotation) > 1e-12:
        turn.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), math.radians(rotation))
    move = gp_Trsf()
    move.SetTranslation(gp_Vec(x, y, z))
    trsf = move * turn
    if fold is not None:
        trsf = fold.transform_at(x, y) * trsf
    return trsf


class _Zones:
    """Which zone a point is in, and that zone's outer conductors and faces."""

    def __init__(self, zones, stackups, levels, board_top_z, board_bottom_z):
        self.entries = []
        for zone in zones or []:
            name = str(zone.get("name"))
            stackup = (stackups or {}).get(str(zone.get("stackup")))
            polygon = contour_points(zone.get("contour") or [])
            if not polygon or not stackup or not levels or name not in levels:
                continue
            self.entries.append((name, polygon, outer_conductors(stackup), levels[name]))
        # A plain board: the one stackup, the two board faces.
        chosen = board_stackup(stackups or {})
        self.default = (outer_conductors(chosen[1]) if chosen else ("", ""),
                        (board_top_z, board_bottom_z))

    def at(self, x: float, y: float):
        """((top name, bottom name), (top z, bottom z)) for a point."""
        for _, polygon, conductors, faces in self.entries:
            if point_in_polygon((x, y), polygon):
                return conductors, faces
        return self.default


def build_pads(data: dict, *, stackups, zones, levels, board_top_z, board_bottom_z,
               fold, lift: float, document, group_for, rgb01, srgb: bool,
               json_stem: str, log: LogFn = _noop_log) -> PadsResult:
    """Every pin's copper into the document, as instances of shared faces.

    *group_for(side)* hands back the assembly label of `pads_top` /
    `pads_bot`, created on first use; *lift* is how far above the face the
    copper floats (the flat-silkscreen clearance); *rgb01* the copper.
    """
    result = PadsResult()
    pads = data.get("pads")
    if not isinstance(pads, dict):
        return result
    library = pads.get("padstacks") or {}
    rows = pads.get("pins") or []
    where = _Zones(zones, stackups, levels, board_top_z, board_bottom_z)
    shape_tool = document.shape_tool

    parts: dict[tuple, object] = {}       # (padstack, layer, mirrored, face) -> label or None
    noted_boxes: set[str] = set()

    for row in rows:
        try:
            x, y, rotation = float(row[0]), float(row[1]), float(row[2])
            mirrored = bool(row[3])
            name = str(row[4])
            pin = {"mirrored": mirrored, "start": row[5] if len(row) > 5 else None,
                   "end": row[6] if len(row) > 6 else None}
        except (TypeError, ValueError, IndexError):
            continue
        result.pins += 1
        padstack = library.get(name)
        if not isinstance(padstack, dict):
            result.no_padstack += 1
            continue
        (top, bottom), (top_z, bottom_z) = where.at(x, y)
        sides = pin_sides(pin, padstack, top, bottom)
        if not sides:
            result.no_outer_face += 1
            continue
        if fold is not None and fold.in_bend_area(x, y):
            result.in_bend += 1

        for face_side, pad in sides:
            layer = next((lay for lay, p in (padstack.get("pads") or {}).items() if p is pad), "?")
            key = (name, layer, mirrored, face_side)
            if key not in parts:
                try:
                    face, note = pad_face(pad, padstack.get("drill"), mirrored,
                                          face_up=(face_side == "top"))
                except (StepBuilderError, RuntimeError, KeyError, TypeError,
                        ValueError, IndexError) as exc:
                    face, note = None, str(exc)
                if note and (name not in noted_boxes):
                    noted_boxes.add(name)
                    result.notes.append(f"padstack {name} ({layer}): {note}")
                if face is None:
                    # No note means the figure built and its drill took all
                    # of it - a mounting hole's nominal pad. Counted apart
                    # from a figure that failed.
                    parts[key] = "hole" if note is None else None
                else:
                    label = shape_tool.NewShape()
                    shape_tool.SetShape(label, face)
                    tag = "m" if mirrored else ""
                    document.set_name(label, f"pad_{name}_{layer_subclass(layer)}{tag}")
                    document.set_color(label, rgb01, srgb)
                    parts[key] = label
                    result.figures += 1
            label = parts[key]
            if label is None:
                result.unbuildable += 1
                continue
            if label == "hole":
                result.all_hole += 1
                continue
            z = top_z + lift if face_side == "top" else bottom_z - lift
            trsf = _placement(x, y, z, rotation, fold)
            shape_tool.AddComponent(group_for("pads_top" if face_side == "top" else "pads_bot"),
                                    label, TopLoc_Location(trsf))
            result.placed += 1

    return result
