"""The copper pads: from the intermediate's padstack library and pin rows to
copper-coloured surfaces lying on the board's outer faces (round 85).

What the picture needs is the copper a pad shows through the mask, on the
two outer faces, in the copper colour. What it does not need is a body per
pad or a window per pad cut into the mask: a boolean over thousands of pad
prisms is minutes of OCCT time on a dense board and a real chance of an
empty result, and a picture cannot tell a flush copper pad from a face one
micron above the mask. So a pad is a FACE, lifted two of the microns a flat
silkscreen is (`silk_flat_height`) - the mask openings take the first, so a
window overlapping a neighbour's copper lies under it - and the board body
is never touched.

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

Since format_version 11 each padstack carries its mask openings too, and
`pad_face` draws copper AND opening: a solder-mask-defined pad shows the
opening's shape, a covered pad nothing. Since 12 the rows include the vias
(a via is a pin with no symbol: an untented one shows its ring, a tented
one draws nothing), and the DRAWN openings - a line, a shape or a text on
a SOLDERMASK layer - come as polygons in the legend's form: `exposed`, the
copper under them, and `bare`, the laminate they show where there is none
(a part number cut into the mask); `build_exposed` builds either through
the legend's machinery, one flat part per side, in the copper or the
dielectric colour.

The mask openings are a second option beside the copper: `opening_face`
is the window in the mask as a face - the mask figure, the drill out of
it, and minus the copper pad when the pads are drawn too, so the two never
overlap - shared per figure and instanced per pin like the pads, under
`openings_top` / `openings_bot`; the drawn openings' laminate (and, with
the copper off, their copper area as laminate too) is the `bare` part.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from OCP.BRep import BRep_Builder
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut
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
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Face, TopoDS_Shape, TopoDS_Wire
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

from .contour import (WIRE_TOLERANCE, _face_from_wires, _open_wire_detail, build_contour,
                      contour_points, point_in_polygon)
from .errors import StepBuilderError
from .reporting import LogFn, _noop_log
from .stackup import _is_conductor, _is_soldermask, board_stackup

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


def mask_sides(stackup: dict | None) -> tuple[bool, bool]:
    """(top, bottom): whether the stackup carries a SOLDERMASK layer outside
    its outer conductors on that side. A flex stackup has coverlay and
    adhesive there and no soldermask at all - Cadence's demo: FLEXI1 is
    STIFFNER / COVERLAY / ADHESIVE over INNER1 - so a mask opening drawn
    over it, or a padstack's mask pad on a pin there, is a window in a mask
    that does not exist. A stackup with no layers (a file older than
    format_version 6) cannot say, and is taken to have a mask on both
    sides, as every build before this assumed."""
    layers = [lay for lay in (stackup or {}).get("layers") or [] if isinstance(lay, dict)]
    conductors = [i for i, lay in enumerate(layers) if _is_conductor(lay)]
    if not layers or not conductors:
        return True, True
    return (any(_is_soldermask(lay) for lay in layers[:conductors[0]]),
            any(_is_soldermask(lay) for lay in layers[conductors[-1] + 1:]))


def etch_pads(padstack: dict) -> list[tuple[str, dict]]:
    """The padstack's REGULAR pads on ETCH layers as [(subclass, pad)], in the
    order the file lists them - the exporter writes them in Allegro's own
    order, top of the stack first."""
    out = []
    for layer, pad in (padstack.get("pads") or {}).items():
        if str(layer).upper().startswith("ETCH/") and isinstance(pad, dict):
            out.append((layer_subclass(layer), pad))
    return out


def mask_pads(padstack: dict) -> dict[str, dict]:
    """The padstack's REGULAR pads on the SOLDERMASK subclasses, by subclass
    ("SOLDERMASK_TOP", "SOLDERMASK_BOTTOM") - the openings the copper shows
    through, in the library since format_version 11. The class is dropped:
    a padstack names them "PIN/SOLDERMASK_TOP" whether a pin or a via wears
    it."""
    out = {}
    for layer, pad in (padstack.get("pads") or {}).items():
        sub = layer_subclass(layer)
        if sub.startswith("SOLDERMASK_") and isinstance(pad, dict):
            out[sub] = pad
    return out


def has_mask_data(library: dict) -> bool:
    """Does this library carry mask pads at all? A format_version 10 file
    does not, and then "no mask pad" means "unknown", not "covered"."""
    return any(mask_pads(ps) for ps in (library or {}).values() if isinstance(ps, dict))


def _mask_for(masks: dict, face: str, mirrored: bool) -> dict | None:
    """The opening of a THROUGH padstack on one outer face: the mask drawn
    for that side, or for the other side when the pin is mirrored - the
    padstack flips with the part, mask pads included."""
    wanted = ("SOLDERMASK_TOP" if face == "top" else "SOLDERMASK_BOTTOM")
    if mirrored:
        wanted = "SOLDERMASK_BOTTOM" if wanted == "SOLDERMASK_TOP" else "SOLDERMASK_TOP"
    return masks.get(wanted)


def pin_sides(pin: dict, padstack: dict, top: str, bottom: str) -> list[tuple[str, dict, dict | None]]:
    """[(face, pad, mask)] for one pin: which of the zone's outer faces
    ("top", "bottom") its copper reaches, the pad figure that goes there, and
    the mask opening it shows through - None when the padstack has no
    opening on that face, which is a covered pad (or, in a library that
    carries no mask pads at all, an older file: see has_mask_data).

    *top* / *bottom* are the outer conductor names of the pin's zone.
    """
    pads = etch_pads(padstack)
    if not pads:
        return []
    masks = mask_pads(padstack)
    start, end = layer_subclass(pin.get("start")), layer_subclass(pin.get("end"))
    mirrored = bool(pin.get("mirrored"))

    if len(pads) == 1:
        # A surface padstack: one pad, placed where the span says. With no
        # span (a pin the exporter could not ask) the mirror flag decides.
        # Its opening is its one mask pad, on whichever side the library
        # drew it - a surface padstack is defined for "the side the part
        # sits on"; given both, the one on the etch pad's own side.
        layer, pad = pads[0]
        if len(masks) == 1:
            mask = next(iter(masks.values()))
        else:
            mask = masks.get("SOLDERMASK_BOTTOM" if layer == "BOTTOM" else "SOLDERMASK_TOP")
        if not start:
            return [("bottom" if mirrored else "top", pad, mask)]
        faces = []
        if start == top:
            faces.append(("top", pad, mask))
        if start == bottom and start != top:
            faces.append(("bottom", pad, mask))
        return faces

    # Several etch pads: a through (or blind) padstack defined layer by
    # layer. Mirrored, the stack is read backwards - the pad drawn for TOP
    # lands on BOTTOM, and so does its opening.
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
        faces.append(("top", by_layer[top], _mask_for(masks, "top", mirrored)))
    if bottom and bottom in span and bottom != top and bottom in by_layer:
        faces.append(("bottom", by_layer[bottom], _mask_for(masks, "bottom", mirrored)))
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


def _faces_of(shape: TopoDS_Shape) -> list[TopoDS_Face]:
    faces = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        faces.append(TopoDS.Face_s(exp.Current()))
        exp.Next()
    return faces


def _assemble(faces: list[TopoDS_Face]) -> TopoDS_Shape:
    """One face as itself, several as a compound - a pad cut in two by a
    slot, or an opening that shows two islands of it."""
    if len(faces) == 1:
        return faces[0]
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for face in faces:
        builder.Add(compound, face)
    return compound


def figure_face(pad: dict) -> tuple[TopoDS_Face | None, str | None]:
    """One pad figure - copper or mask opening - as a planar face at the
    origin, in the pin's frame: the outline (the bounding box standing in
    when there is none), a DONUT's inside diameter as a hole, and the offset
    settled. Returns (face, note)."""
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
    return _settle_offset(face, pad)


def pad_face(pad: dict, hole: list | None, mirrored: bool, face_up: bool = True,
             mask: dict | None = None) -> tuple[TopoDS_Shape | None, str | None]:
    """One pad's VISIBLE copper as a planar face (or a compound of faces) at
    the origin, z = 0, ready to be placed.

    The copper figure, its drill cut out, and - when *mask* is given - only
    what lies inside the mask opening: a solder-mask-defined pad shows the
    opening's shape, a copper-defined one its own, and a pad whose opening
    misses it entirely shows nothing. Returns (shape, note): the shape is
    None when the figure cannot be built or nothing of it is visible; the
    note, when there is one, is a line for the log (a box disagreement, a
    figure that failed). No note with None means "all hole" or "nothing
    inside the opening" - ordinary, and counted by the caller.

    *face_up* says which way the faces' normals should point: up for the top
    side, down for the bottom, so a viewer that culls back faces shows the
    pad from the side it is on.
    """
    face, note = figure_face(pad)
    if face is None:
        return None, note
    faces = [face]

    if hole:
        cutter = _face_from_wires(build_contour(hole, 0.0), [])
        cut = BRepAlgoAPI_Cut(face, cutter)
        if not cut.IsDone():
            return None, "the drill could not be cut out of the pad"
        faces = _faces_of(cut.Shape())
        if not faces:
            # A mounting hole with a nominal pad smaller than its drill: the
            # copper is all hole. Ordinary, not an error - no note, and the
            # caller counts it as a pad that is all hole.
            return None, None

    if mask is not None:
        window, mask_note = figure_face(mask)
        if window is None:
            return None, f"its mask opening could not be built ({mask_note})"
        if mask_note and not note:
            note = "mask opening: " + mask_note
        common = BRepAlgoAPI_Common(_assemble(faces), window)
        if not common.IsDone():
            return None, "the copper could not be clipped to its mask opening"
        faces = _faces_of(common.Shape())
        if not faces:
            return None, None

    return _finish(faces, mirrored, face_up), note


def opening_face(mask: dict, hole: list | None, mirrored: bool, face_up: bool = True,
                 copper: dict | None = None) -> tuple[TopoDS_Shape | None, str | None]:
    """One padstack's mask OPENING as a planar face (or a compound of faces)
    at the origin, z = 0, ready to be placed - the window in the mask.

    The opening's figure, the drill cut out so the hole stays a hole, and -
    when *copper* is given, the pad the copper pads draw - minus that pad:
    what is left is the laminate the opening shows around a copper-defined
    pad, and nothing at all for a solder-mask-defined one, whose copper
    fills its opening. Without *copper* the opening comes whole, for a model
    that shows the windows and not the pads. Same (shape, note) contract as
    `pad_face`: None with no note is "nothing to show", ordinary.
    """
    window, note = figure_face(mask)
    if window is None:
        return None, note
    faces = [window]

    if hole:
        cutter = _face_from_wires(build_contour(hole, 0.0), [])
        cut = BRepAlgoAPI_Cut(window, cutter)
        if not cut.IsDone():
            return None, "the drill could not be cut out of the opening"
        faces = _faces_of(cut.Shape())
        if not faces:
            return None, None

    if copper is not None:
        pad, pad_note = figure_face(copper)
        if pad is None:
            return None, f"its copper could not be built ({pad_note})"
        if pad_note and not note:
            note = "copper: " + pad_note
        cut = BRepAlgoAPI_Cut(_assemble(faces), pad)
        if not cut.IsDone():
            return None, "the copper could not be taken out of the opening"
        faces = _faces_of(cut.Shape())
        if not faces:
            return None, None

    return _finish(faces, mirrored, face_up), note


def _finish(faces: list, mirrored: bool, face_up: bool) -> TopoDS_Shape:
    """Mirror the faces of a figure for a mirrored pin (x -> -x, before the
    rotation, the order Allegro applies) and turn their normals to face out
    of the side they lie on, so a viewer that culls back faces shows them."""
    if mirrored:
        mirror = gp_Trsf()
        mirror.SetMirror(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)))
        faces = [TopoDS.Face_s(BRepBuilderAPI_Transform(f, mirror, True).Shape()) for f in faces]

    oriented = []
    for f in faces:
        up = _normal_up(f)
        oriented.append(TopoDS.Face_s(f.Reversed()) if up is not None and up != face_up else f)
    return _assemble(oriented)


def shape_area(shape: TopoDS_Shape | None) -> float:
    """Surface area of a face or a compound of faces; 0 for None."""
    if shape is None:
        return 0.0
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, props)
    return props.Mass()


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
    covered: int = 0                # placements with no mask opening in the padstack: under the mask
    hidden: int = 0                 # placements whose opening misses the copper entirely
    mask_defined: int = 0           # distinct figures whose opening is smaller than the copper
    no_mask_data: bool = False      # a format_version 10 library: no openings known, copper drawn whole
    vias: int = 0                   # via rows read (format_version 12)
    via_placed: int = 0             # of the placements, those that are vias - untented ones
    in_bend: int = 0                # pins standing in a bend area
    openings_placed: int = 0        # opening faces placed (the mask-openings option)
    opening_figures: int = 0        # distinct opening faces built
    openings_filled: int = 0        # placements whose copper fills the opening: nothing left to draw
    no_mask_zone: int = 0           # openings not drawn: the pin's zone has no soldermask on that side
    no_mask_zone_names: set = field(default_factory=set)
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
    """Which zone a point is in, and that zone's outer conductors, faces and
    soldermask sides."""

    def __init__(self, zones, stackups, levels, board_top_z, board_bottom_z):
        self.entries = []
        for zone in zones or []:
            name = str(zone.get("name"))
            stackup = (stackups or {}).get(str(zone.get("stackup")))
            contour = zone.get("contour") or []
            polygon = contour_points(contour)
            if not polygon or not stackup or not levels or name not in levels:
                continue
            xs = [p[0] for p in polygon]
            ys = [p[1] for p in polygon]
            self.entries.append((name, polygon, outer_conductors(stackup), levels[name],
                                 mask_sides(stackup), contour,
                                 (min(xs), min(ys), max(xs), max(ys))))
        # A plain board: the one stackup, the two board faces.
        chosen = board_stackup(stackups or {})
        self.default = (outer_conductors(chosen[1]) if chosen else ("", ""),
                        (board_top_z, board_bottom_z))
        self.default_masks = mask_sides(chosen[1]) if chosen else (True, True)

    def at(self, x: float, y: float):
        """((top name, bottom name), (top z, bottom z)) for a point."""
        for _, polygon, conductors, faces, *_rest in self.entries:
            if point_in_polygon((x, y), polygon):
                return conductors, faces
        return self.default

    def mask_at(self, x: float, y: float) -> tuple[bool, bool, str | None]:
        """(mask on top, mask on the bottom, zone name) for a point; the
        plain board's stackup answers for a point on no zone."""
        for name, polygon, _conductors, _faces, masks, *_rest in self.entries:
            if point_in_polygon((x, y), polygon):
                return masks[0], masks[1], name
        return self.default_masks[0], self.default_masks[1], None

    def mask_zones(self, side: str) -> list:
        """The zones that carry a soldermask on *side*, as
        [(name, polygon, contour, bbox, z of that face)]."""
        i = 0 if side == "top" else 1
        return [(name, polygon, contour, bbox, faces[i])
                for name, polygon, _c, faces, masks, contour, bbox in self.entries if masks[i]]


def build_pads(data: dict, *, stackups, zones, levels, board_top_z, board_bottom_z,
               fold, lift: float, document, group_for, rgb01, srgb: bool,
               json_stem: str, copper: bool = True, openings: bool = False, base01=None,
               opening_lift: float | None = None, log: LogFn = _noop_log) -> PadsResult:
    """Every pin's copper - and/or its mask opening - into the document, as
    instances of shared faces.

    *group_for(side)* hands back the assembly label of `pads_top` /
    `pads_bot` (and `openings_top` / `openings_bot`), created on first use;
    *lift* is how far above the face the copper floats and *opening_lift*
    how far the windows do - BELOW the copper (the caller passes one and
    two flat-silkscreen clearances): two windows of neighbouring through
    pins overlap each other's copper ring, and two faces at one height
    leave the viewer to pick, which is how a ring came out eaten on the demo
    board; a micron apart, the copper wins. *rgb01* the copper, *base01*
    the dielectric. *copper* draws the pads, *openings* the windows in the
    mask: what the copper leaves of each when both are on, the openings
    whole otherwise.
    """
    if opening_lift is None:
        opening_lift = lift / 2.0
    result = PadsResult()
    pads = data.get("pads")
    if not isinstance(pads, dict):
        return result
    library = pads.get("padstacks") or {}
    rows = pads.get("pins") or []
    where = _Zones(zones, stackups, levels, board_top_z, board_bottom_z)
    shape_tool = document.shape_tool
    # A library without a single mask pad is a format_version 10 file: it
    # cannot say which pads are covered, so the copper is drawn whole, as it
    # was, and the caller says so once. With mask data, no opening on a face
    # means the pad is under the mask and draws nothing.
    masks_known = has_mask_data(library)
    result.no_mask_data = not masks_known

    parts: dict[tuple, object] = {}       # (padstack, layer, mirrored, face) -> label or None
    noted_boxes: set[str] = set()

    for row in rows:
        try:
            x, y, rotation = float(row[0]), float(row[1]), float(row[2])
            mirrored = bool(row[3])
            name = str(row[4])
            pin = {"mirrored": mirrored, "start": row[5] if len(row) > 5 else None,
                   "end": row[6] if len(row) > 6 else None}
            # An eighth element names the kind since format_version 12; a
            # row without one is a pin. A via is a pin with no symbol: the
            # same padstack rules, and a tented one has no mask pad and
            # draws nothing.
            is_via = len(row) > 7 and str(row[7]).lower() == "via"
        except (TypeError, ValueError, IndexError):
            continue
        result.pins += 1
        if is_via:
            result.vias += 1
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

        for face_side, pad, mask in sides:
            if mask is None and masks_known:
                result.covered += 1
                continue
            layer = next((lay for lay, p in (padstack.get("pads") or {}).items() if p is pad), "?")
            tag = "m" if mirrored else ""
            z = top_z + lift if face_side == "top" else bottom_z - lift
            trsf = _placement(x, y, z, rotation, fold)

            if copper:
                key = (name, layer, mirrored, face_side)
                if key not in parts:
                    empty = None                   # why nothing shows: "hole" or "hidden"
                    try:
                        # The copper first, whole - it says whether the drill took
                        # all of it - then what the opening leaves of it. Per
                        # figure, not per pin, so the second build is cheap.
                        whole, note = pad_face(pad, padstack.get("drill"), mirrored,
                                               face_up=(face_side == "top"))
                        face = whole
                        if whole is None:
                            empty = "hole" if note is None else None
                        elif mask is not None:
                            face, mask_note = pad_face(pad, padstack.get("drill"), mirrored,
                                                       face_up=(face_side == "top"), mask=mask)
                            note = note or mask_note
                            if face is None:
                                empty = "hidden" if mask_note is None else None
                            # Solder-mask-defined: the opening is what shows, and
                            # it is smaller than the copper. Counted per figure,
                            # for the log; a percent of slack covers the arcs.
                            elif shape_area(face) < 0.99 * shape_area(whole):
                                result.mask_defined += 1
                    except (StepBuilderError, RuntimeError, KeyError, TypeError,
                            ValueError, IndexError) as exc:
                        face, note = None, str(exc)
                    if note and (name not in noted_boxes):
                        noted_boxes.add(name)
                        result.notes.append(f"padstack {name} ({layer}): {note}")
                    if face is None:
                        # Nothing visible and no failure: the drill took all of
                        # it (a mounting hole's nominal pad) or the opening misses
                        # it. Counted apart from a figure that failed (None).
                        parts[key] = empty
                    else:
                        label = shape_tool.NewShape()
                        shape_tool.SetShape(label, face)
                        document.set_name(label, f"pad_{name}_{layer_subclass(layer)}{tag}")
                        document.set_color(label, rgb01, srgb)
                        parts[key] = label
                        result.figures += 1
                label = parts[key]
                if label is None:
                    result.unbuildable += 1
                elif label == "hole":
                    result.all_hole += 1
                elif label == "hidden":
                    result.hidden += 1
                else:
                    shape_tool.AddComponent(group_for("pads_top" if face_side == "top" else "pads_bot"),
                                            label, TopLoc_Location(trsf))
                    result.placed += 1
                    if is_via:
                        result.via_placed += 1

            # The window in the mask, shared per figure like the copper: what
            # the copper leaves of it when the pads are drawn too (nothing
            # for a solder-mask-defined pad), the opening whole otherwise.
            # Only where the pin's zone HAS a mask on that side: a pin on a
            # flex or stiffener zone sits under coverlay, and its padstack's
            # mask pad is a window in nothing.
            if openings and mask is not None:
                mask_top, mask_bottom, zone_name = where.mask_at(x, y)
                if not (mask_top if face_side == "top" else mask_bottom):
                    result.no_mask_zone += 1
                    result.no_mask_zone_names.add(zone_name or "the board")
                    continue
                mask_layer = next((lay for lay, p in (padstack.get("pads") or {}).items() if p is mask), "?")
                okey = (name, mask_layer, mirrored, face_side, "opening")
                if okey not in parts:
                    try:
                        window, onote = opening_face(mask, padstack.get("drill"), mirrored,
                                                     face_up=(face_side == "top"),
                                                     copper=pad if copper else None)
                    except (StepBuilderError, RuntimeError, KeyError, TypeError,
                            ValueError, IndexError) as exc:
                        window, onote = None, str(exc)
                    if onote and (name + "/opening" not in noted_boxes):
                        noted_boxes.add(name + "/opening")
                        result.notes.append(f"padstack {name} ({mask_layer}): {onote}")
                    if window is None:
                        parts[okey] = None if onote else "filled"
                    else:
                        label = shape_tool.NewShape()
                        shape_tool.SetShape(label, window)
                        document.set_name(label, f"opening_{name}_{layer_subclass(mask_layer)}{tag}")
                        document.set_color(label, base01 or rgb01, srgb)
                        parts[okey] = label
                        result.opening_figures += 1
                label = parts[okey]
                if label is None:
                    result.unbuildable += 1
                elif label == "filled":
                    result.openings_filled += 1
                else:
                    oz = top_z + opening_lift if face_side == "top" else bottom_z - opening_lift
                    shape_tool.AddComponent(group_for("openings_top" if face_side == "top" else "openings_bot"),
                                            label, TopLoc_Location(_placement(x, y, oz, rotation, fold)))
                    result.openings_placed += 1

    return result


# --------------------------------------------------------------------------- #
# the copper under the drawn mask openings (format_version 12)
# --------------------------------------------------------------------------- #

def build_exposed(data: dict, *, stackups, zones, levels, board_top_z, board_bottom_z,
                  lift: float, section: str = "exposed", log: LogFn = _noop_log) -> dict[str, tuple]:
    """What the DRAWN mask openings show, per side, as flat faces.

    `pads.exposed.top` / `.bottom` are the copper under the openings, and
    `pads.bare.top` / `.bottom` the laminate they show where there is none
    (a part number cut into the mask, the ring of an opening wider than its
    pad) - both as polygons in the silkscreen's vertex form, computed in
    Allegro (opening AND copper, opening ANDNOT copper) and written the way
    the legend is - so they are built with the legend's own machinery:
    `build_silkscreen` in flat mode, the arc reading scored against
    Allegro's areas, the faces unioned. *section* picks which. Lifted
    *lift* above the outer face (the caller passes twice the pads' lift, so
    a pad that lies under a drawn opening as well is covered by this, not
    fought; copper and bare never overlap each other by construction).

    On a board with zones each polygon is built at the level of the zone it
    stands in, by its centroid; a plain board has one level.

    Returns {side: (compound or None, built, skipped)} for the sides the
    file carries.
    """
    from .legend import build_silkscreen

    pads = data.get("pads")
    exposed = pads.get(section) if isinstance(pads, dict) else None
    if not isinstance(exposed, dict):
        return {}
    where = _Zones(zones, stackups, levels, board_top_z, board_bottom_z)
    out = {}
    tag = "copper" if section == "exposed" else "bare"
    for side, sign in (("top", 1.0), ("bottom", -1.0)):
        polygons = [p for p in (exposed.get(side) or []) if isinstance(p, dict)]
        if not polygons:
            continue
        pieces, built, skipped = [], 0, 0
        masked = where.mask_zones(side) if where.entries else []
        if where.entries and not masked:
            log(f"{tag}_{side}: {len(polygons)} drawn-opening polygon(s) left out - no zone "
                f"carries a soldermask on the {side}")
            out[side] = (None, 0, len(polygons))
            continue
        if not where.entries and not (where.default_masks[0] if side == "top" else where.default_masks[1]):
            log(f"{tag}_{side}: {len(polygons)} drawn-opening polygon(s) left out - the board "
                f"carries no soldermask on the {side}")
            out[side] = (None, 0, len(polygons))
            continue

        # A drawn opening is a window in the mask, so it exists only where
        # the zone under it has one: a flex zone has coverlay instead, and
        # the demo board's outline strokes on the mask layers run through
        # every zone - the part over the flex would float two millimetres
        # above it. So: a polygon with every vertex in one masked zone is
        # built at that zone's face; one that reaches beyond is built whole
        # and clipped to each masked zone it touches, at that zone's face;
        # one that touches none is left out.
        whole: dict[float, list] = {}          # z -> polygons
        straddling: list = []
        dropped = 0
        for polygon in polygons:
            verts = [(float(v[0]), float(v[1])) for v in (polygon.get("vertices") or []) if len(v) >= 2]
            if not verts:
                verts = contour_points(polygon.get("outline") or [])
            if not masked:
                # a plain board with a mask: one level, no clipping
                z = where.default[1][0] if side == "top" else where.default[1][1]
                whole.setdefault(z, []).append(polygon)
                continue
            homes = set()
            for v in verts:
                homes.add(next((name for name, poly, _c, _b, _z in masked if point_in_polygon(v, poly)), None))
            if len(homes) == 1 and None not in homes:
                z = next(zf for name, _p, _c, _b, zf in masked if name in homes)
                whole.setdefault(z, []).append(polygon)
            else:
                xs = [v[0] for v in verts]
                ys = [v[1] for v in verts]
                box = (min(xs), min(ys), max(xs), max(ys))
                touches = [m for m in masked
                           if not (box[2] < m[3][0] or box[0] > m[3][2] or box[3] < m[3][1] or box[1] > m[3][3])]
                if touches:
                    straddling.append((polygon, touches))
                else:
                    dropped += 1
        for z, group in whole.items():
            compound, n_built, n_skipped = build_silkscreen(
                group, z, 0.0, log=log, side=f"{tag}_{side}", flat=True, flat_offset=sign * abs(lift))
            built += n_built
            skipped += n_skipped
            if compound is not None:
                pieces.append(compound)
        clipped = 0
        if straddling:
            # every masked zone any of them touches, each at its own face
            for name, _poly, contour, _box, zf in masked:
                group = [p for p, touches in straddling if any(t[0] == name for t in touches)]
                if not group:
                    continue
                compound, n_built, n_skipped = build_silkscreen(
                    group, zf, 0.0, log=log, side=f"{tag}_{side} ({name})", flat=True,
                    flat_offset=sign * abs(lift))
                skipped += n_skipped
                if compound is None:
                    continue
                region = _face_from_wires(build_contour(contour, zf + sign * abs(lift)), [])
                common = BRepAlgoAPI_Common(compound, region)
                faces = _faces_of(common.Shape()) if common.IsDone() else []
                if faces:
                    pieces.append(_assemble(faces))
                    clipped += len(group)
                elif not common.IsDone():
                    log(f"warning: {tag}_{side}: {len(group)} drawn-opening polygon(s) could not be "
                        f"clipped to zone {name} and are left out")
            built += len({id(p) for p, _t in straddling})
        if dropped or straddling:
            log(f"{tag}_{side}: the mask is only on "
                + ", ".join(name for name, *_r in masked)
                + f" - {len(straddling)} drawn-opening polygon(s) clipped to it"
                + (f", {dropped} left out" if dropped else ""))
        if not pieces:
            out[side] = (None, built, skipped)
        elif len(pieces) == 1:
            out[side] = (pieces[0], built, skipped)
        else:
            builder = BRep_Builder()
            compound = TopoDS_Compound()
            builder.MakeCompound(compound)
            for piece in pieces:
                builder.Add(compound, piece)
            out[side] = (compound, built, skipped)
    return out
