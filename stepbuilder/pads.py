"""The copper pads: from the intermediate's padstack library and pin rows to
copper-coloured surfaces lying on the board's outer faces (round 85).

What the picture needs is the copper a pad shows through the mask, on the
two outer faces, in the copper colour. What it does not need is a window
per pad cut into the mask with a body set into it: a boolean over thousands
of pad prisms is minutes of OCCT time on a dense board and a real chance of
an empty result, and a picture cannot tell a flush copper pad from one
standing ten microns proud of the mask. So a pad is a THIN SOLID,
`PAD_THICKNESS` high, standing on the outer face and growing away from the
board like the solid legend does, and the board body is never touched. A
solid rather than a face lifted a micron: the first cut of this drew faces,
and in the user's CAD not every pad showed - a face a micron off a large
face is inside the depth resolution of an ordinary viewer and flickers or
vanishes, and a surface body is not shown the way a solid is by every
reader. A prism ten microns high has its top well clear of the mask, and
its bottom face, coincident with the mask, is hidden under its own top.

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
  `pad_solid` extrudes it `PAD_THICKNESS` up for the top side, down for the
  bottom. Built ONCE and instanced per pin, like a component model: a solid
  costs its faces every time it is written, an instance costs a placement.
* `build_pads` places every pin: one shared part per figure and side under
  `pads_top_<board>` / `pads_bot_<board>`, standing on the zone's outer face,
  through the fold plan where there is one.

The pad's declared bounding box is the FIGURE's own box, about its centre;
its outline path already includes the padstack's offset. Measured on the
Dell board's fifteen offset padstacks: an outline running 0..29.53 against a
box of +-14.77 and an offset of 14.76. `_settle_offset` keeps that reading
as the normal case and shifts the outline only when it is plainly the
figure-centred one.

Vias are not in the intermediate and not drawn: they are tented under the
mask on nearly every board.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.Bnd import Bnd_Box
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Face, TopoDS_Shape
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

from .contour import _face_from_wires, build_contour, contour_points, point_in_polygon
from .errors import StepBuilderError
from .reporting import LogFn, _noop_log
from .stackup import _is_conductor, board_stackup

# How high a pad stands on the mask, in design units (mm on every board this
# tool has met; a mil board would get a hundredth of a mil, which a viewer
# still separates). Ten microns: clear of any depth buffer at board scale,
# invisible as a step, and a tenth of the solid legend's 25 um.
PAD_THICKNESS = 0.01

# A pad's declared bounding box (of the figure, about its own centre) shifted
# by the declared offset has to land this close (design units) to the box of
# the outline for the outline to be read as already in place. 0.02 clears
# the 0.01-mil rounding of a board laid out in mils and is well under any
# real offset - see _settle_offset.
BOX_TOLERANCE = 0.02


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


def _first_face(shape: TopoDS_Shape) -> TopoDS_Face | None:
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    return TopoDS.Face_s(exp.Current()) if exp.More() else None


def pad_face(pad: dict, hole: list | None, mirrored: bool) -> tuple[TopoDS_Face | None, str | None]:
    """One pad figure as a planar face at the origin, z = 0, in the pin's frame.

    Returns (face, note): the face is None when the figure cannot be built
    or has nothing left once its hole is cut out; the note, when there is
    one, is a line for the log (a box disagreement, an empty figure).
    """
    outline = pad.get("outline")
    if not outline:
        bbox = pad.get("bbox")
        if not bbox:
            return None, "no outline and no bounding box"
        outline = _rect_contour(bbox)

    outer = build_contour(outline, 0.0)
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
    return face, note


def pad_solid(face: TopoDS_Face, up: bool, thickness: float = PAD_THICKNESS) -> TopoDS_Shape:
    """The pad as a thin solid standing on z = 0: extruded +z for the top
    side, -z for the bottom, so placed at the outer face it grows away from
    the board like the solid legend does."""
    return BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, thickness if up else -thickness)).Shape()


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
               fold, document, group_for, rgb01, srgb: bool,
               json_stem: str, thickness: float = PAD_THICKNESS,
               log: LogFn = _noop_log) -> PadsResult:
    """Every pin's copper into the document, as instances of shared thin solids.

    *group_for(side)* hands back the assembly label of `pads_top` /
    `pads_bot`, created on first use; *thickness* is how high a pad stands
    on the outer face; *rgb01* the copper.
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
                    face, note = pad_face(pad, padstack.get("drill"), mirrored)
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
                    shape_tool.SetShape(label, pad_solid(face, face_side == "top", thickness))
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
            z = top_z if face_side == "top" else bottom_z
            trsf = _placement(x, y, z, rotation, fold)
            shape_tool.AddComponent(group_for("pads_top" if face_side == "top" else "pads_bot"),
                                    label, TopLoc_Location(trsf))
            result.placed += 1

    return result
