"""
Core logic for building a STEP assembly from the Allegro intermediate JSON.

Port of StepBuilder.cpp (https://github.com/juulsA/exportStep) to Python/OCP.
Contains no UI code: everything reports through callbacks so it can be driven
from the GUI, from the CLI, or from tests.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from OCP.BRep import BRep_Builder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
)
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.GC import GC_MakeArcOfCircle
from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.Interface import Interface_Static
from OCP.Quantity import Quantity_Color, Quantity_TypeOfColor
from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
from OCP.STEPCAFControl import STEPCAFControl_Reader, STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_StepModelType
from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label, TDF_LabelSequence, TDF_Tool
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape, TopoDS_Wire
from OCP.TopTools import TopTools_HSequenceOfShape
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool
from OCP.gp import gp_Ax1, gp_Ax2, gp_Circ, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

# Tolerance used to stitch contour edges into a closed wire.
# Matches the value used by the original C++ implementation.
WIRE_TOLERANCE = 1.0e-5


class StepBuilderError(Exception):
    """Raised for any condition the original code handled with cin.get()."""


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #

LogFn = Callable[[str], None]
# (value, total, what is happening). The label is optional so an older caller
# passing a two-argument function still works.
ProgressFn = Callable[..., None]


def _noop_log(message: str) -> None:
    pass


def _noop_progress(current: int, total: int, label: str = "") -> None:
    pass


# --------------------------------------------------------------------------- #
# contour geometry
# --------------------------------------------------------------------------- #

def build_contour(contour: Iterable[dict], z_offset: float = 0.0) -> TopoDS_Wire:
    """Turn a list of JSON primitives (segment / arc / circle) into a wire."""
    edges = []

    for segment in contour:
        kind = segment.get("type", "segment")

        if kind == "arc":
            center = gp_Pnt(segment["center"][0], segment["center"][1], z_offset)
            circle = gp_Circ(gp_Ax2(center, gp_Dir(0, 0, 1)), segment["radius"])
            arc = GC_MakeArcOfCircle(
                circle,
                math.radians(segment["alpha"]),
                math.radians(segment["beta"]),
                segment["ccw"],
            ).Value()
            edges.append(BRepBuilderAPI_MakeEdge(arc).Edge())

        elif kind == "circle":
            center = gp_Pnt(segment["x"], segment["y"], z_offset)
            circle = gp_Circ(gp_Ax2(center, gp_Dir(0, 0, 1)), segment["radius"])
            edges.append(BRepBuilderAPI_MakeEdge(circle).Edge())

        elif kind == "segment":
            start = gp_Pnt(segment["start"][0], segment["start"][1], z_offset)
            end = gp_Pnt(segment["end"][0], segment["end"][1], z_offset)
            edges.append(BRepBuilderAPI_MakeEdge(start, end).Edge())

        else:
            raise StepBuilderError(f"Unknown contour primitive: {kind!r}")

    if not edges:
        raise StepBuilderError("Contour contains no primitives")

    edge_seq = TopTools_HSequenceOfShape()
    for edge in edges:
        edge_seq.Append(edge)

    wires = TopTools_HSequenceOfShape()
    ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(
        edge_seq, WIRE_TOLERANCE, False, wires
    )

    if wires.Length() < 1:
        raise StepBuilderError("Could not stitch contour edges into a wire")
    if wires.Length() > 1:
        # The original code silently took wire #1 and dropped the rest, which
        # produces a subtly wrong board. Surfacing it is more useful.
        raise StepBuilderError(
            f"Contour is not closed: edges formed {wires.Length()} separate "
            f"wires (tolerance {WIRE_TOLERANCE}). Check for gaps in the outline."
        )

    wire = TopoDS.Wire_s(wires.Value(1))
    if not wire.Closed():
        # A single but open wire: MakeFace would silently build garbage.
        # Report the actual gap and where it is: a large gap means the source
        # never emitted a closing edge, a tiny one means the tolerance is what
        # needs looking at. Without this the message cannot tell them apart.
        raise StepBuilderError(
            f"Contour is open (start and end do not meet within {WIRE_TOLERANCE})."
            + _open_wire_detail(wire)
        )
    return wire


def _open_wire_detail(wire: TopoDS_Wire) -> str:
    """' Gap 3.81 mm between (x, y) and (x, y).' — best effort, never raises."""
    try:
        from OCP.BRep import BRep_Tool
        from OCP.TopExp import TopExp
        from OCP.TopoDS import TopoDS_Vertex

        v1, v2 = TopoDS_Vertex(), TopoDS_Vertex()
        TopExp.Vertices_s(wire, v1, v2)
        if v1.IsNull() or v2.IsNull():
            return ""
        p1, p2 = BRep_Tool.Pnt_s(v1), BRep_Tool.Pnt_s(v2)
        return (f" Gap {p1.Distance(p2):.6g} between "
                f"({p1.X():.4f}, {p1.Y():.4f}) and ({p2.X():.4f}, {p2.Y():.4f}).")
    except Exception:
        return ""


# A layer counts as soldermask if this survives in its name or IPC function
# once everything but letters and digits is stripped - so SOLDERMASK_TOP,
# "Solder Mask" and SOLDER-MASK-BOTTOM all match.
SOLDERMASK_MARKER = "SOLDERMASK"


def _is_soldermask(layer: dict) -> bool:
    probe = f"{layer.get('name') or ''} {layer.get('function') or ''}".upper()
    return SOLDERMASK_MARKER in "".join(c for c in probe if c.isalnum())


def restack(layers: list[dict]) -> list[dict]:
    """Recompute every layer's z from its thickness, core top back at 0.

    The same walk the exporter does: everything outside the top conductor is
    summed, and each layer then hangs off that. Re-running it after layers have
    been removed is what closes the gap - the stack settles toward the core by
    exactly the thickness taken out, above and below independently.

    List order is the physical order (`layer->position` is not - it duplicates
    and indexes the combined All-Stackups view), so this walks the list.
    """
    first = next((i for i, lay in enumerate(layers)
                  if str(lay.get("type") or "").upper() in ("CONDUCTOR", "PLANE")),
                 None)
    if first is None:
        return layers

    above = sum(float(lay["thickness"]) for lay in layers[:first])
    out, cum = [], 0.0
    for lay in layers:
        thickness = float(lay["thickness"])
        z_top = above - cum
        cum += thickness
        out.append({**lay, "z_top": z_top, "z_bottom": z_top - thickness})
    return out


def drop_soldermask(stackups: dict, log: LogFn = _noop_log) -> dict:
    """Every stackup with its soldermask layers removed and the rest re-stacked.

    Removing a layer is not enough on its own: the layers outside it would keep
    their old heights and float, leaving a gap where the mask used to be. So
    the survivors are re-walked, which settles them toward the core.
    """
    out, dropped = {}, []
    for name, stackup in stackups.items():
        layers = stackup.get("layers") or []
        keep = [lay for lay in layers if not _is_soldermask(lay)]
        dropped += [str(lay.get("name")) for lay in layers if _is_soldermask(lay)]
        out[name] = {**stackup, "layers": restack(keep)}

    if dropped:
        seen = sorted(set(dropped))
        log(f"Ignoring soldermask: {len(dropped)} layer(s) removed from the "
            f"stack ({', '.join(seen)}); the rest closes up toward the core")
    else:
        log("Ignoring soldermask: this design has none in its stackups")
    return out


def stackup_levels(stackups: dict, zones: list[dict],
                   z_datum: str) -> tuple[dict, float, float, float]:
    """Zone faces, board extent and the datum shift, from the per-layer data.

    Returns ({zone: (top, bottom)}, board_top, board_bottom, shift).

    Every layer arrives with its own z_top/z_bottom measured from the top of
    the conductor core, which the exporter puts at 0 for every stackup. That
    datum is the whole point: FLEX, STIFFENER1 and STIFFENER2 are 0.365, 0.49
    and 2.44 thick but share a 0.215 core, so they can only be stacked
    correctly by their copper - a stiffener grows outwards from it.

    Verified against Allegro's own export of the same board, which spans
    -0.315 .. 2.125 in exactly this frame.
    """
    tops, bottoms = {}, {}
    for zone in zones:
        layers = stackups.get(str(zone["stackup"]), {}).get("layers") or []
        if not layers:
            continue
        name = str(zone["name"])
        tops[name] = max(float(lay["z_top"]) for lay in layers)
        bottoms[name] = min(float(lay["z_bottom"]) for lay in layers)

    if not tops:
        raise StepBuilderError("No zone resolved to a stackup with layers")

    board_top = max(tops.values())
    board_bottom = min(bottoms.values())
    shift = -board_top if z_datum == "top" else -board_bottom
    levels = {n: (tops[n] + shift, bottoms[n] + shift) for n in tops}
    return levels, board_top + shift, board_bottom + shift, shift


def _shape_face(shape: dict, z: float):
    """One drawn layer shape as a face, its voids becoming holes."""
    outer = build_contour(shape["outline"], z)
    inner = [build_contour(v, z) for v in (shape.get("voids") or [])]
    return _face_from_wires(outer, inner)


def _layer_region(layer: dict, zone_contour: list, z: float, log: LogFn):
    """The material of one layer inside one zone, as a face or compound.

    Three cases:

    **No shapes** - the layer spans the whole zone. Conductors and the
    dielectric are like this; Allegro's own tree shows the dielectric as
    exactly one body per zone, which is the same statement.

    **Positive shapes** - the material IS those shapes. Stiffener, adhesive
    and epoxy are drawn this way, and it is what this per-layer model exists
    for: Allegro puts 86.763 mm2 at the stiffener height where a plain zone
    prism puts 171.761, because the stiffener is a drawn shape smaller than
    the zone.

    **Negative shapes** - the shapes are OPENINGS and the material is the zone
    minus them. Coverlay, soldermask and pastemask are drawn this way by
    IPC-2581 convention. On the test board COVERLAY_TOP has a shape matching
    the FLEX1 zone outline exactly - as an opening that is a flex tail with
    its contacts exposed, which is ordinary; as material it would have been
    the only coverlay patch on a board that needs it everywhere.

    `negativeArtwork` does NOT answer this - it is about film generation and
    reads nil on every layer of a real board. Polarity comes from
    `layer["negative"]` when the exporter could determine it, and from the
    caller's name list otherwise.

    Shapes are design-wide, so they are always intersected with the zone: one
    ADHESIVE_TOP shape covers most of the board and belongs to three zones at
    once, each at its own height.
    """
    zone_face = _face_from_wires(build_contour(zone_contour, z), [])
    shapes = layer.get("shapes")
    if not shapes:
        return zone_face

    faces = []
    for i, shape in enumerate(shapes):
        try:
            faces.append(_shape_face(shape, z))
        except (StepBuilderError, RuntimeError, KeyError, TypeError, IndexError) as exc:
            log(f"warning: shape {i + 1} of layer {layer.get('name')} skipped ({exc})")
    if not faces:
        return zone_face if layer.get("negative") else None

    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut

    builder = BRep_Builder()
    drawn = TopoDS_Compound()
    builder.MakeCompound(drawn)
    for face in faces:
        builder.Add(drawn, face)

    if layer.get("negative"):
        cut = BRepAlgoAPI_Cut(zone_face, drawn)
        if not cut.IsDone():
            log(f"warning: could not open layer {layer.get('name')} in its zone; "
                f"leaving it solid")
            return zone_face
        return cut.Shape()

    common = BRepAlgoAPI_Common(drawn, zone_face)
    if not common.IsDone():
        log(f"warning: could not clip layer {layer.get('name')} to zone; "
            f"using it unclipped")
        return drawn
    return common.Shape()



def make_board_layer_parts(pcb: dict, stackups: dict, zones: list[dict],
                           shift: float,
                           log: LogFn = _noop_log) -> list[tuple[str, dict, TopoDS_Shape]]:
    """(zone name, layer dict, solid) for every layer of every zone, NOT fused.

    The LAYER ITSELF, not just its name: the layer-colored build needs its
    type and function to decide what kind of layer it is.

    The inspection build. Fusing is what the ordinary path does and what makes
    the file a quarter of the size, but it also welds the stack into one
    surface you cannot take apart by eye. Here each layer stays its own part,
    keeps its own name and gets its own color, so a stackup can be checked
    against the cross-section editor layer by layer.

    Cutouts are applied to each layer separately, so holes stay visible.
    """
    parts: list[tuple[str, dict, TopoDS_Shape]] = []
    cutouts = board_cutouts(pcb.get("edges") or [], log)

    for zone in zones:
        stackup = stackups.get(str(zone["stackup"]))
        if not stackup:
            continue
        for layer in stackup.get("layers") or []:
            height = float(layer["z_top"]) - float(layer["z_bottom"])
            if height <= 0:
                continue
            top = float(layer["z_top"]) + shift
            region = _layer_region(layer, zone["contour"], top, log)
            if region is None:
                continue
            solid = BRepPrimAPI_MakePrism(region, gp_Vec(0, 0, -height)).Shape()
            if solid.IsNull():
                continue
            if cutouts:
                solid = _cut_out(solid, cutouts, top + 0.01,
                                 gp_Vec(0, 0, -(height + 0.02)))
                # A layer entirely consumed by the cutouts is not an error -
                # a small drawn stiffener can sit inside a milled opening -
                # but an empty shape must not become a part.
                if solid.IsNull() or not has_solid(solid):
                    log(f"warning: layer {layer.get('name')} of zone "
                        f"{zone['name']} is left with nothing after its "
                        f"cutouts; skipped")
                    continue
            parts.append((str(zone["name"]), layer, solid))

    if not parts:
        raise StepBuilderError("No stackup layer produced a solid")
    return parts


def has_solid(shape: TopoDS_Shape) -> bool:
    """True if *shape* contains at least one solid.

    The check a boolean needs, and the one `IsDone()` does not give. See
    `board_cutouts` for what happens without it.
    """
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    return TopExp_Explorer(shape, TopAbs_SOLID).More()


def board_cutouts(contours: list, log: LogFn = _noop_log) -> list:
    """`edges[1:]` - every contour after the outline - with repeats dropped.

    A cutout that appears TWICE is not harmless. Two coincident prisms in the
    tool compound make `BRepAlgoAPI_Cut` return an **empty compound** while
    `IsDone()` is true and the result is not null - so both of the usual guards
    pass and the STEP is written with components, legend, and no board at all.
    Measured on 8231-a2, whose intermediate carried each of its two slot holes
    twice: 0 solids instead of one 724.18 mm3 board, and not a word in the log.
    One duplicate anywhere in the list is enough to erase the whole body.

    Exact repeats only. Cutouts that merely overlap are ordinary - a slot
    crossing a milled edge, two drawn shapes sharing a corner - and OCC deals
    with them; only geometry that coincides exactly does this.

    The SKILL side no longer emits duplicates (it used to append each export's
    pin holes to a list shared by every export in the run), but intermediates
    written before that fix are on disk and still have to build.
    """
    if len(contours) < 2:
        return []

    seen: set[str] = set()
    cutouts = []
    dropped = 0
    for contour in contours[1:]:
        try:
            key = json.dumps(contour, sort_keys=True)
        except (TypeError, ValueError):       # not comparable - keep it
            cutouts.append(contour)
            continue
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        cutouts.append(contour)

    if dropped:
        log(f"warning: {dropped} cutout(s) in this intermediate repeat another "
            f"one exactly, and were dropped. Kept, they would have left the "
            f"board with no body at all. Re-export from Allegro for a clean "
            f"file.")
    return cutouts


def _cut_out(shape: TopoDS_Shape, contours: list, cut_z: float,
             direction: gp_Vec) -> TopoDS_Shape:
    """Remove every contour in *contours* from *shape*, in one boolean."""
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for i, contour in enumerate(contours, start=1):
        wire = build_contour(contour, cut_z)
        face = BRepBuilderAPI_MakeFace(wire, True)
        if not face.IsDone():
            raise StepBuilderError(f"Cutout #{i} is not planar or self-intersects")
        builder.Add(compound, BRepPrimAPI_MakePrism(face.Face(), direction).Shape())
    cut = BRepAlgoAPI_Cut(shape, compound)
    if not cut.IsDone():
        raise StepBuilderError("Boolean cut of board cutouts failed")
    return cut.Shape()


def fuse_keeping_faces(parts: list[tuple[str, dict, TopoDS_Shape]],
                       log: LogFn = _noop_log):
    """Fuse the layer solids into ONE solid whose faces stay per-layer.

    *parts* is what make_board_layer_parts returns: (zone name, layer, solid),
    the LAYER ITSELF rather than its name, because the caller colors each face
    by what kind of layer it belongs to. Returns (solid, [(face, layer)]).

    **UnifySameDomain is deliberately NOT applied here**, and that is the whole
    trick. It is what makes the ordinary build small - it merges the coplanar
    faces every layer interface leaves behind - but merging them is exactly what
    destroys the stack on the rim: two layers with the same outline become one
    face and the board loses its stripes. Measured on the real STIFFENER2:
    eleven layer solids fuse to one solid with 47 faces, against 11 once
    unified.

    Which face came from which layer is taken from the boolean's own history
    (`Modified`), not guessed from geometry: with several zones, two different
    layers can occupy the same z, so a z-band lookup would be ambiguous.
    """
    if not parts:
        raise StepBuilderError("No stackup layer produced a solid")

    # Imported here, not at module scope, like every other OCCT helper in this
    # file - and never as a local rebinding of a name that IS module-level, for
    # the UnboundLocalError reason spelled out in _rim_faces.
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopTools import TopTools_DataMapOfShapeInteger, TopTools_ListOfShape

    solids = [solid for _, _, solid in parts]
    if len(solids) == 1:
        faces = []
        exp = TopExp_Explorer(solids[0], TopAbs_FACE)
        while exp.More():
            faces.append((TopoDS.Face_s(exp.Current()), parts[0][1]))
            exp.Next()
        return solids[0], faces

    arguments = TopTools_ListOfShape()
    arguments.Append(solids[0])
    tools = TopTools_ListOfShape()
    for solid in solids[1:]:
        tools.Append(solid)

    op = BRepAlgoAPI_Fuse()
    op.SetArguments(arguments)
    op.SetTools(tools)
    op.SetRunParallel(True)
    op.Build()
    if not op.IsDone():
        raise StepBuilderError("Could not fuse the stackup layers")
    fused = op.Shape()
    # IsNull() is not the test - a boolean that produced nothing hands back a
    # non-null, EMPTY compound. See board_cutouts.
    if fused.IsNull() or not has_solid(fused):
        raise StepBuilderError("Fusing the stackup layers produced nothing")

    # input face -> layer, followed through the boolean
    owner = TopTools_DataMapOfShapeInteger()
    for index, (_, layer, solid) in enumerate(parts):
        exp = TopExp_Explorer(solid, TopAbs_FACE)
        while exp.More():
            face = exp.Current()
            modified = op.Modified(face)
            if modified.Size() == 0:
                if not op.IsDeleted(face):
                    owner.Bind(face, index)
            else:
                # OCP makes TopTools_ListOfShape iterable directly; there is no
                # TopTools_ListIteratorOfListOfShape in these bindings.
                for produced in modified:
                    owner.Bind(produced, index)
            exp.Next()

    faces, unknown = [], 0
    exp = TopExp_Explorer(fused, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        if owner.IsBound(face):
            faces.append((face, parts[owner.Find(face)][1]))
        else:
            unknown += 1
        exp.Next()

    if unknown:
        log(f"warning: {unknown} board face(s) could not be traced back to a "
            f"layer and keep the default color")
    return fused, faces


def _stackup_board(stackups: dict, zones: list[dict], shift: float,
                   log: LogFn) -> TopoDS_Shape:
    """The board as one solid: every layer of every zone, fused.

    Fusing measured at **25.6%** of the compound's file size with the volume
    identical to nine decimals - stacked layers share large coplanar faces and
    each separate solid costs its own product definition in AP214. That is the
    opposite of the silkscreen legend, where fusing thousands of barely
    touching prisms came to 154%. One boolean over the whole list rather than
    pairwise, which is closer to linear.
    """
    solids = []
    for zone in zones:
        stackup = stackups.get(str(zone["stackup"]))
        if not stackup:
            log(f"warning: zone {zone['name']} names an unknown stackup "
                f"{zone['stackup']!r}, skipped")
            continue
        for layer in stackup.get("layers") or []:
            height = float(layer["z_top"]) - float(layer["z_bottom"])
            if height <= 0:
                continue
            region = _layer_region(layer, zone["contour"],
                                   float(layer["z_top"]) + shift, log)
            if region is None:
                continue
            solid = BRepPrimAPI_MakePrism(region, gp_Vec(0, 0, -height)).Shape()
            if not solid.IsNull():
                solids.append(solid)

    if not solids:
        raise StepBuilderError("No stackup layer produced a solid")
    log(f"Building board from {len(solids)} layer solid(s)")
    return fuse_and_unify(solids, log)


def fuse_and_unify(solids: list[TopoDS_Shape], log: LogFn) -> TopoDS_Shape:
    """One solid out of many, with the coplanar interfaces merged away."""
    if len(solids) == 1:
        return solids[0]

    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.TopTools import TopTools_ListOfShape

    # BRepAlgoAPI_Fuse in its multi-argument form, NOT BRepAlgoAPI_BuilderAlgo:
    # the general fuse computes the same boolean but leaves the pieces as
    # separate solids in a compound, which is exactly what this is trying to
    # get rid of (measured: 18 solids out, one expected).
    arguments = TopTools_ListOfShape()
    arguments.Append(solids[0])
    tools = TopTools_ListOfShape()
    for solid in solids[1:]:
        tools.Append(solid)

    op = BRepAlgoAPI_Fuse()
    op.SetArguments(arguments)
    op.SetTools(tools)
    op.SetRunParallel(True)
    op.Build()
    if not op.IsDone():
        raise StepBuilderError("Could not fuse the stackup layers")
    fused = op.Shape()
    if fused.IsNull() or not has_solid(fused):
        raise StepBuilderError("Fusing the stackup layers produced nothing")

    # Merge the coplanar faces the fuse leaves behind at every layer
    # interface. Never fatal: an unmerged board is correct, just heavier.
    try:
        unify = ShapeUpgrade_UnifySameDomain(fused, True, True, False)
        unify.Build()
        merged = unify.Shape()
        if not merged.IsNull():
            fused = merged
    except Exception as exc:
        log(f"warning: could not merge the board's coplanar faces ({exc})")
    return fused


def zone_levels(zones: list[dict], z_datum: str) -> tuple[dict, float, float]:
    """Where each stackup zone's two faces sit, and the board's overall extent.

    Returns ({zone name: (top_z, bottom_z)}, board_top_z, board_bottom_z).

    **Zones line up on the copper, not on their outer faces.** Measured on a
    real rigid-flex board: FLEX, STIFFENER1 and STIFFENER2 are 0.365, 0.49 and
    2.44 thick, but all three have a 0.215 conductor core. A 2.44 mm stiffener
    grows 2.125 above that core and 0.1 below it. Stacking them by total
    thickness, or aligning their top faces, would tear the board apart at every
    zone boundary.

    So the shared datum is the top of the core, and each zone extends `above`
    up and `core + below` down from it. The whole thing is then shifted so the
    chosen datum face lands on z=0, exactly as the single-stackup path does.
    """
    tops = {}
    bottoms = {}
    for zone in zones:
        name = str(zone["name"])
        tops[name] = float(zone["above"])
        bottoms[name] = -(float(zone["core"]) + float(zone["below"]))

    board_top = max(tops.values())
    board_bottom = min(bottoms.values())
    shift = -board_top if z_datum == "top" else -board_bottom

    levels = {n: (tops[n] + shift, bottoms[n] + shift) for n in tops}
    return levels, board_top + shift, board_bottom + shift


def _zone_solid(zones: list[dict], levels: dict, log: LogFn) -> TopoDS_Shape:
    """One solid per zone, fused into a single board.

    Fused rather than left as a compound: zone outlines are trimmed against
    each other and overlap slightly at their shared edges (measured: 0.14 mm on
    the test board), so a compound would carry doubled geometry along every
    seam. Four zones make this cheap - unlike the silkscreen legend, where
    fusing thousands of prisms was measured and rejected.
    """
    solids = []
    for zone in zones:
        name = str(zone["name"])
        top_z, bottom_z = levels[name]
        height = top_z - bottom_z
        if height <= 0:
            log(f"warning: zone {name} has no thickness, skipped")
            continue
        wire = build_contour(zone["contour"], top_z)
        face = BRepBuilderAPI_MakeFace(wire, True)
        if not face.IsDone():
            raise StepBuilderError(
                f"Zone {name} outline is not planar or self-intersects")
        solids.append(
            BRepPrimAPI_MakePrism(face.Face(), gp_Vec(0, 0, -height)).Shape())

    if not solids:
        raise StepBuilderError("No stackup zone produced a solid")
    if len(solids) == 1:
        return solids[0]

    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse

    board = solids[0]
    for solid in solids[1:]:
        fuse = BRepAlgoAPI_Fuse(board, solid)
        if not fuse.IsDone():
            raise StepBuilderError("Could not fuse the stackup zones")
        board = fuse.Shape()
    return board


def make_board_geometry(pcb: dict, thickness: float, z_offset: float = 0.0,
                        zones: list[dict] | None = None,
                        levels: dict | None = None,
                        stackups: dict | None = None,
                        shift: float = 0.0,
                        log: LogFn = _noop_log) -> TopoDS_Shape:
    """Extrude the board outline downwards and cut every hole/cutout out of it.

    edges[0] is the outline; every following contour is a cutout. All cutout
    prisms are collected into one compound and removed with a single boolean
    Cut: the original per-cutout loop was quadratic (every Cut re-processed an
    increasingly complex board) and measured ~11x slower at 120 drill holes.
    """
    contours = pcb["edges"]
    if not contours:
        raise StepBuilderError("pcb.edges is empty")

    if zones and levels:
        # Multi-stackup: the board IS the zones. pcb.edges[0] still describes
        # the overall outline, but it carries no per-zone thickness, so it is
        # not used for the body - only its cutouts are, below.
        if stackups:
            board = _stackup_board(stackups, zones, shift, log)
        else:
            board = _zone_solid(zones, levels, log)
        cut_top = max(top for top, _ in levels.values())
        cut_bottom = min(bottom for _, bottom in levels.values())
        # A through-cut that ends exactly on a face is a classic source of
        # boolean trouble; the zone path extends past both. The single-stackup
        # path below deliberately keeps its exact extents, which is what the
        # C++-verified regression measures.
        margin = 0.01
        cut_z = cut_top + margin
        cut_direction = gp_Vec(0, 0, -(cut_top - cut_bottom + 2 * margin))
    else:
        # FIX: the C++ version special-cased len==1 and passed the whole array
        # instead of contours[0]. It only worked because the nesting happened to
        # collapse. edges[0] is always the outline.
        wire = build_contour(contours[0], z_offset)
        face = BRepBuilderAPI_MakeFace(wire, True)
        if not face.IsDone():
            raise StepBuilderError("Board outline is not planar or self-intersects")

        board = BRepPrimAPI_MakePrism(face.Face(), gp_Vec(0, 0, -thickness)).Shape()
        cut_z = z_offset
        cut_direction = gp_Vec(0, 0, -thickness)

    cutouts = board_cutouts(contours, log)
    if cutouts:
        builder = BRep_Builder()
        compound = TopoDS_Compound()
        builder.MakeCompound(compound)
        for i, cutout in enumerate(cutouts, start=1):
            cut_wire = build_contour(cutout, cut_z)
            cut_face = BRepBuilderAPI_MakeFace(cut_wire, True)
            if not cut_face.IsDone():
                raise StepBuilderError(f"Cutout #{i} is not planar or self-intersects")
            builder.Add(compound,
                        BRepPrimAPI_MakePrism(cut_face.Face(), cut_direction).Shape())

        cut = BRepAlgoAPI_Cut(board, compound)
        if not cut.IsDone():
            raise StepBuilderError("Boolean cut of board cutouts failed")
        board = cut.Shape()
        if board.IsNull():
            raise StepBuilderError("Board geometry is empty after cutting")
        # IsDone() and IsNull() both pass on a boolean that produced NOTHING -
        # see board_cutouts. Without this the build carries on and writes a
        # STEP with components and legend but no board in it.
        if not has_solid(board):
            raise StepBuilderError(
                f"Cutting the {len(cutouts)} hole(s) out of the board left no "
                f"solid at all. OCC calls the boolean done and returns an "
                f"empty result, which is what coincident or outline-sized "
                f"cutouts do to it. Check the intermediate's pcb.edges.")
    elif not has_solid(board):
        # No cutouts at all, so nothing above has checked the body itself.
        raise StepBuilderError("The board outline produced no solid")

    return board


# --------------------------------------------------------------------------- #
# silkscreen
# --------------------------------------------------------------------------- #

# Fallback ink thickness (mm) when the JSON does not carry one. 25 um is a
# typical cured screen-printed legend; the SKILL side normally supplies it from
# simple3d_config.json.
DEFAULT_SILK_THICKNESS = 0.025

# How far a FLAT legend is lifted off the board face, in mm. It is not ink
# thickness - a flat legend has none - it exists only so the two faces are not
# coplanar: coincident planes flicker against each other in any viewer that
# resolves depth per pixel, which is what happens with a legend lying exactly on
# the board. 1 um is invisible at board scale; raise it (0.005-0.01) if a
# particular viewer's depth buffer still cannot separate them.
DEFAULT_FLAT_HEIGHT = 0.001


# How a polygon's vertex list is read. Allegro gives (x, y, signed_radius) per
# point, and three things about it are ambiguous in the documentation:
#
#   rule - what the sign is measured against. The sentence is "The sign of the
#       radius indicates for postive the arc is to the left of the y-axis".
#       TRAVEL reads it as the arc bulging left of the direction of travel.
#       AXIS takes "the y-axis" literally: the vertical through the arc's own
#       centre, so the sign says which side of its centre the arc sits on. The
#       neighbouring sentence - polygon arcs never cross a quadrant, and
#       quadrants are measured from the centre - is what makes AXIS coherent.
#       The two rules disagree exactly where a shape doubles back: the two round
#       ends of one stroke get the SAME sign under TRAVEL and OPPOSITE signs
#       under AXIS, which is why reading it wrong leaves one end correct and
#       turns the other inside out.
#   polarity - whether a positive radius means the first side or the second.
#   first_radius_closes - each vertex carries the radius of the edge REACHING
#       it, and the list does not repeat its first point, so the first vertex's
#       radius either describes the closing edge back to it or is unused.
#
# Rather than pick and hope, every combination is tried against the area Allegro
# reported for those same polygons; whichever reproduces them wins.
# See _pick_convention.
RULE_TRAVEL = "travel"
RULE_AXIS = "axis"

_Convention = tuple  # (rule: str, positive_is_first: bool, first_radius_closes: bool)

# MEASURED on a real board (Allegro 24.1, 2026-07-22): the reading Allegro
# actually uses is AXIS / positive-sits-left / first-radius-closes. Scored
# against that board's own polygon areas it lands at 0.0004% (top) and 0.0000%
# (bottom), while every other reading is off by 1.3% to 677%. It is listed
# first so that a legend of nothing but straight lines - where every reading is
# equivalent and the scores tie - still resolves to the one known to be right.
#
# The search is kept rather than hard-coding it: it costs one pass over a
# handful of small polygons, it is what established this in the first place,
# and it will say so in the log if another Allegro version disagrees.
_CONVENTIONS: list[_Convention] = [
    (RULE_AXIS, True, True),
] + [
    (rule, polarity, closes)
    for rule in (RULE_AXIS, RULE_TRAVEL)
    for polarity in (True, False)
    for closes in (True, False)
    if (rule, polarity, closes) != (RULE_AXIS, True, True)
]


def _describe_convention(convention: _Convention) -> str:
    rule, polarity, closes = convention
    if rule == RULE_TRAVEL:
        side = "bulges left" if polarity else "bulges right"
        what = f"positive radius {side} of travel"
    else:
        side = "left" if polarity else "right"
        what = f"positive radius means the arc sits {side} of its centre"
    return f"{what}, first radius {'closes' if closes else 'unused'}"

# A rebuilt polygon has to land this close to Allegro's own area to be accepted.
# Loose enough for float noise and OCCT's own tolerance, tight enough that a
# wrong arc side (several percent even on gentle curves) never slips through.
AREA_TOLERANCE = 0.005


def _arc_geometry(p0, p1, radius: float):
    """Chord bookkeeping shared by both readings.

    Returns (mx, my, nx, ny, rad, h) where (nx, ny) is the left normal of
    travel and h is the centre's distance from the chord midpoint. The two
    candidate centres are (mx, my) +/- h * (nx, ny), and the arc bulging to the
    LEFT of travel is the one whose centre sits to the right, and vice versa.
    """
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    chord = math.hypot(dx, dy)
    if chord < 1.0e-12:
        return None
    # A radius smaller than half the chord cannot span it (rounding in the
    # source); clamp to the semicircle instead of taking a negative sqrt.
    rad = max(abs(radius), chord / 2.0)
    h = math.sqrt(max(0.0, rad * rad - (chord / 2.0) ** 2))
    mx, my = (p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0
    return mx, my, -dy / chord, dx / chord, rad, h


def _arc_bulges_left(p0, p1, radius: float, rule: str, positive_is_first: bool) -> bool:
    """Which side of travel this arc bulges to, under the given reading."""
    positive = radius > 0.0
    if rule == RULE_TRAVEL:
        return positive == positive_is_first

    # AXIS: the sign says which side of the vertical through its own centre the
    # arc sits on. For the candidate that bulges LEFT, the arc's midpoint is one
    # radius from the centre along the left normal, so its offset in x is simply
    # rad * nx - the arc sits left of its own centre exactly when nx < 0.
    #
    # nx == 0 would mean a chord with no rise, which inside a single quadrant
    # only happens for a zero-length arc; the guard is there for arithmetic
    # safety, not for a case that occurs.
    geometry = _arc_geometry(p0, p1, radius)
    if geometry is None:
        return positive == positive_is_first
    _, _, nx, _, _, _ = geometry
    if abs(nx) < 1.0e-12:
        return positive == positive_is_first

    left_candidate_sits_left = nx < 0.0
    wants_left_of_centre = positive == positive_is_first
    return left_candidate_sits_left == wants_left_of_centre


def _arc_edge(p0, p1, radius: float, z: float, arc_left: bool):
    """Edge for an arc from p0 to p1 whose chord is `radius` away from centre.

    Built through three points - start, arc midpoint, end - so there is no
    angle bookkeeping and no sense flag to get backwards. Polygon arcs never
    cross a quadrant, so every one of them is a minor arc and the midpoint is
    unambiguous: it sits (radius - h) off the chord, on the side the arc bulges.
    """
    geometry = _arc_geometry(p0, p1, radius)
    if geometry is None:
        return None
    mx, my, nx, ny, rad, h = geometry
    sign = 1.0 if arc_left else -1.0
    mid = gp_Pnt(mx + sign * (rad - h) * nx, my + sign * (rad - h) * ny, z)

    arc = GC_MakeArcOfCircle(
        gp_Pnt(p0[0], p0[1], z), mid, gp_Pnt(p1[0], p1[1], z)
    ).Value()
    return BRepBuilderAPI_MakeEdge(arc).Edge()


def _wire_from_vertices(vertices: list, z: float, convention: _Convention) -> TopoDS_Wire:
    """Allegro vertex list -> closed wire, read under *convention*."""
    rule, positive_is_first, first_radius_closes = convention

    points = [(float(v[0]), float(v[1])) for v in vertices]
    radii = [float(v[2]) if len(v) > 2 else 0.0 for v in vertices]
    if len(points) < 2:
        raise StepBuilderError("polygon has fewer than two vertices")

    def make(p0, p1, radius):
        if abs(radius) > 1.0e-9:
            left = _arc_bulges_left(p0, p1, radius, rule, positive_is_first)
            return _arc_edge(p0, p1, radius, z, left)
        if math.dist(p0, p1) < 1.0e-12:
            return None
        return BRepBuilderAPI_MakeEdge(
            gp_Pnt(p0[0], p0[1], z), gp_Pnt(p1[0], p1[1], z)
        ).Edge()

    edges = []
    for i in range(1, len(points)):
        edge = make(points[i - 1], points[i], radii[i])
        if edge is not None:
            edges.append(edge)

    # The list does not repeat its first point, so the closing edge is ours to
    # add. If a list ever does repeat it, the distance test skips this and the
    # closing edge's radius was already consumed by the loop above.
    if math.dist(points[-1], points[0]) > 1.0e-9:
        edge = make(points[-1], points[0], radii[0] if first_radius_closes else 0.0)
        if edge is not None:
            edges.append(edge)

    if not edges:
        raise StepBuilderError("polygon produced no edges")

    edge_seq = TopTools_HSequenceOfShape()
    for edge in edges:
        edge_seq.Append(edge)
    wires = TopTools_HSequenceOfShape()
    ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(edge_seq, WIRE_TOLERANCE, False, wires)

    if wires.Length() != 1:
        raise StepBuilderError(
            f"polygon edges formed {wires.Length()} wires, expected 1"
        )
    wire = TopoDS.Wire_s(wires.Value(1))
    if not wire.Closed():
        raise StepBuilderError("polygon contour is open" + _open_wire_detail(wire))
    return wire


def _face_from_wires(outer: TopoDS_Wire, inner: list[TopoDS_Wire]):
    """Planar face from an outer wire and its hole wires."""
    maker = BRepBuilderAPI_MakeFace(outer, True)
    if not maker.IsDone():
        raise StepBuilderError("silkscreen outline is not planar or self-intersects")
    for wire in inner:
        # A hole wire has to run opposite to the outer one for MakeFace to read
        # it as a void; ShapeFix_Face below repairs whichever way it came.
        maker.Add(TopoDS.Wire_s(wire.Reversed()))
    face = maker.Face()
    if inner:
        from OCP.ShapeFix import ShapeFix_Face

        fix = ShapeFix_Face(face)
        fix.FixOrientation()
        face = fix.Face()
    return face


def _silk_face(polygon: dict, z: float, convention: _Convention):
    """One silkscreen polygon (vertex form, or the older primitive form)."""
    if "vertices" in polygon:
        outer = _wire_from_vertices(polygon["vertices"], z, convention)
        inner = [_wire_from_vertices(h, z, convention)
                 for h in polygon.get("holes", [])]
    else:
        # format_version 2.0 wrote pre-built segment/arc primitives.
        outer = build_contour(polygon["outline"], z)
        inner = [build_contour(h, z) for h in polygon.get("holes", [])]
    return _face_from_wires(outer, inner)


def _pick_convention(
    polygons: list[dict], z: float, log: LogFn, side: str
) -> _Convention:
    """Choose the vertex reading that reproduces Allegro's reported areas.

    Scored over the polygons that declare an area, worst-case first: the right
    convention matches every one of them, a wrong one is off on any polygon with
    a curve in it. Ties (a legend of nothing but straight lines, where the
    readings cannot differ) fall through to the first convention, which is then
    as good as any.
    """
    candidates = [p for p in polygons if p.get("vertices") and p.get("area")
                  and abs(float(p["area"])) > 1.0e-6]
    # Only polygons that actually contain an arc can tell the readings apart, and
    # the cheapest ones say it just as clearly, so sample small arc-bearing
    # polygons. A legend of nothing but straight lines leaves every reading
    # equivalent, and then the first is as good as any.
    curved = [p for p in candidates
              if any(abs(float(v[2])) > 1.0e-9 for v in p["vertices"] if len(v) > 2)]
    sample = sorted(curved or candidates, key=lambda p: len(p["vertices"]))[:8]
    if not sample:
        return _CONVENTIONS[0]

    scores: list[tuple[float, _Convention]] = []
    for convention in _CONVENTIONS:
        worst = 0.0
        for polygon in sample:
            declared = abs(float(polygon["area"]))
            try:
                area = _face_area(_silk_face(polygon, z, convention))
            except (StepBuilderError, RuntimeError, TypeError):
                area = None
            if area is None:
                worst = math.inf
                break
            worst = max(worst, abs(area - declared) / declared)
        scores.append((worst, convention))

    # Every candidate is scored - no early exit. Two readings can both land
    # inside the tolerance on a gently curved sample while only one is right,
    # and taking the first to pass would then pick by list order.
    best_error, best = min(scores, key=lambda s: s[0])

    if best_error > AREA_TOLERANCE:
        log(f"warning: no reading of the {side} vertex data reproduces the areas "
            f"Allegro reported (best is off by {best_error * 100:.1f}%: "
            f"{_describe_convention(best)}). The legend geometry may be distorted.")
    return best


def build_silkscreen(
    polygons: Iterable[dict],
    z: float,
    thickness: float,
    log: LogFn = _noop_log,
    side: str = "",
    flat: bool = False,
    flat_offset: float = 0.0,
) -> tuple[TopoDS_Compound | None, int, int]:
    """Extrude one side's silkscreen polygons into a compound of thin solids.

    Returns (compound, built, skipped). *thickness* is signed: positive extrudes
    upwards (top side), negative downwards (bottom side).

    The solids are deliberately NOT fused. Silkscreen is thousands of
    overlapping strokes and glyphs, and a boolean union of that many thin
    prisms is minutes of OCCT time with a real chance of failing outright,
    while the union buys nothing: the result is one label, one color, and it
    renders and exports identically. What it costs is that the compound is not
    a single manifold solid, which matters only if someone means to do
    downstream boolean work on the ink itself.

    A polygon that cannot be built is counted and skipped rather than taken as
    fatal - one malformed glyph must not cost the whole board.

    flat=True writes each polygon as a single planar face instead of a prism.
    Measured on a 150-polygon legend: 566 kB against 2191 kB, so about a
    quarter of the size. A prism costs V+2 faces for a V-vertex polygon (top,
    bottom and one wall per edge); a face costs one. What is given up is that
    the ink is then a surface, not a solid: it has no thickness to measure and
    nothing downstream can do boolean work with it.

    flat_offset lifts the flat face off the board face by that much, signed the
    same way as thickness. Coincident planes do flicker in a viewer that
    resolves depth per pixel - confirmed on a real board - so the default is a
    micron of clearance rather than a true zero. See DEFAULT_FLAT_HEIGHT.

    Fusing the prisms was measured too, and made the file LARGER (3377 kB,
    154%): a boolean union replaces analytic cylinders and planes with general
    surfaces, and after clipping the strokes barely overlap, so there is little
    interior geometry for it to remove. Not offered.
    """
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)

    polygons = list(polygons)
    convention = _pick_convention(polygons, z, log, side)

    shapes: list = []
    built = 0
    skipped = 0
    first_error: str | None = None
    area_checked = 0
    area_bad = 0
    worst: tuple[float, float, float] | None = None   # (ratio, declared, got)

    for polygon in polygons:
        if not polygon.get("vertices") and not polygon.get("outline"):
            skipped += 1
            continue
        try:
            # Solid mode builds on the board face and grows the prism away
            # from it. Flat mode has only the face, lifted just clear of the
            # board so the two planes are not coincident.
            face = _silk_face(polygon, z + flat_offset if flat else z, convention)
            shapes.append(
                face if flat
                else BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, thickness)).Shape()
            )
            built += 1
        except (StepBuilderError, RuntimeError, KeyError, TypeError, IndexError) as exc:
            skipped += 1
            if first_error is None:
                first_error = str(exc)
            continue

        # Every polygon is verified, not just the ones that chose the reading:
        # the convention is global, so a single polygon that still disagrees is
        # a polygon whose geometry did not survive, and it should be reported.
        declared = polygon.get("area")
        if declared and abs(declared) > 1.0e-6:
            got = _face_area(face)
            if got is not None:
                area_checked += 1
                ratio = abs(got - abs(declared)) / abs(declared)
                if ratio > AREA_TOLERANCE:
                    area_bad += 1
                    if worst is None or ratio > worst[0]:
                        worst = (ratio, abs(declared), got)

    # Flat faces are unioned before they go into the compound; see
    # _merge_coplanar for why, and why the solid path deliberately does not.
    if flat and len(shapes) > 1:
        merged = _merge_coplanar(shapes, log, side)
        if merged is not None:
            shapes = [merged]

    for shape in shapes:
        builder.Add(compound, shape)

    if skipped:
        log(f"warning: {skipped} {side} silkscreen polygon(s) skipped "
            f"(first: {first_error})")
    if area_bad and worst is not None:
        log(f"warning: {area_bad} of {area_checked} {side} polygons still differ "
            f"from the area Allegro reported (worst: {worst[1]:.6g} vs "
            f"{worst[2]:.6g} mm2, {worst[0] * 100:.1f}%).")
    elif area_checked:
        log(f"{side}: {area_checked} polygon(s) match Allegro's areas "
            f"(arc reading: {_describe_convention(convention)})")
    if not built:
        return None, 0, skipped
    return compound, built, skipped


def _merge_coplanar(faces: list, log: LogFn, side: str):
    """Boolean-union a side's flat faces into one shape, or None if that fails.

    Silkscreen polygons genuinely overlap - a stroke and the glyph beside it,
    two strokes meeting at a junction. As solids that is harmless
    interpenetration. As FLAT faces it is two coincident coplanar faces at the
    same z, which no depth buffer can order, so the overlap renders as a
    flickering blend. Measured on a real board: 5 of 8 candidate pairs overlap
    by real area, 0.16 mm2 double-counted across the side.

    A general fuse makes each overlapping region exist once instead of twice,
    and ShapeUpgrade_UnifySameDomain then merges the coplanar pieces back into
    whole faces. On that board, 117 faces -> 112, 0.08 s, and the STEP came out
    SMALLER (548 kB against 599 kB).

    That is the opposite of fusing the SOLID legend, which was measured at 154%
    of the size and is still not offered: a solid union has to build side walls
    and replaces analytic surfaces with general ones, while a coplanar union of
    faces only removes geometry.
    """
    try:
        from OCP.BRepAlgoAPI import BRepAlgoAPI_BuilderAlgo
        from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
        from OCP.TopTools import TopTools_ListOfShape

        arguments = TopTools_ListOfShape()
        for face in faces:
            arguments.Append(face)
        algo = BRepAlgoAPI_BuilderAlgo()
        algo.SetArguments(arguments)
        algo.SetRunParallel(True)
        algo.Build()
        fused = algo.Shape()
        if fused.IsNull():
            raise StepBuilderError("boolean union produced nothing")

        unify = ShapeUpgrade_UnifySameDomain(fused, True, True, False)
        unify.Build()
        merged = unify.Shape()
        return fused if merged.IsNull() else merged
    except Exception as exc:
        # Not fatal: unmerged faces still draw, they just flicker where they
        # overlap. Losing the legend entirely would be the worse outcome.
        log(f"warning: could not merge the {side} faces ({exc}); overlapping "
            f"areas may flicker. Solid mode does not have this problem.")
        return None


def _face_area(face) -> float | None:
    """Surface area of a face, or None if it cannot be measured."""
    try:
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps

        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        return props.Mass()
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# transforms
# --------------------------------------------------------------------------- #

def _rotation(axis: gp_Dir, degrees: float) -> gp_Trsf:
    trsf = gp_Trsf()
    trsf.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), axis), math.radians(degrees))
    return trsf


def component_transform(
    mapping: dict,
    component: dict,
    board_top_z: float,
    board_bottom_z: float,
    zone_levels: dict | None = None,
) -> gp_Trsf:
    """Build the full placement transform for one component.

    Order is significant and matches the original: applied right to left, so the
    STEP model is first oriented by its mapping rotation, shifted by its mapping
    offset, optionally flipped, then rotated by the symbol angle and moved into
    place.

    board_top_z / board_bottom_z are the z of the two board faces (which one is
    zero depends on the chosen datum). Top parts sit on board_top_z, mirrored
    (bottom) parts are flipped 180 deg about Y and sit on board_bottom_z. Parts
    rest on the soldermask face, i.e. on the board surface, because real pads
    carry solder that lifts the part to mask level.
    """
    rx = _rotation(gp_Dir(1, 0, 0), mapping["rotation_x"])
    ry = _rotation(gp_Dir(0, 1, 0), mapping["rotation_y"])
    rz = _rotation(gp_Dir(0, 0, 1), mapping["rotation_z"])
    rotation = rz * ry * rx

    offset = gp_Trsf()
    offset.SetTranslation(
        gp_Vec(mapping["offset_x"], mapping["offset_y"], mapping["offset_z"])
    )

    angle = _rotation(gp_Dir(0, 0, 1), component["angle"])

    mirror = gp_Trsf()
    if component["is_mirrored"]:
        z = board_bottom_z
        mirror = _rotation(gp_Dir(0, 1, 0), 180.0)
    else:
        z = board_top_z

    # On a multi-stackup board the surface a part rests on is its ZONE's, not
    # the board's: a part on a 2.44 mm stiffener and one on 0.365 mm flex are
    # two millimetres apart. zone_levels is None on an ordinary board, and on a
    # part whose zone is unknown the board-wide surface is the right fallback.
    if zone_levels:
        zone = component.get("zone")
        if zone and zone in zone_levels:
            zone_top, zone_bottom = zone_levels[zone]
            z = zone_bottom if component["is_mirrored"] else zone_top

    position = gp_Trsf()
    position.SetTranslation(gp_Vec(component["x"], component["y"], z))

    return position * angle * mirror * offset * rotation


# --------------------------------------------------------------------------- #
# step file lookup
# --------------------------------------------------------------------------- #

class StepFileIndex:
    """Filename -> path index over one or more model folders, built once.

    The C++ version ran a recursive_directory_iterator for every cache miss,
    which is O(components x files). One walk is enough.

    Several roots form an ORDERED SEARCH PATH, like PATH or an include path:
    the first root that holds a given filename wins. That makes it possible to
    keep a shared company library and let a project-local folder listed above it
    override individual models. Each root is still walked recursively, so
    subfolders need no listing of their own.

    First-wins was already the behaviour within a single root (dict.setdefault
    over rglob), but the order rglob happens to walk in is arbitrary, so a
    duplicate resolved unpredictably and in silence. With explicit roots the
    precedence is declared, and a name found in more than one root is reported
    with the path that won - a silent substitution of the wrong model is a
    thing you find out about at the CAD stage otherwise.

    A root that does not exist is reported and skipped; only having no usable
    root at all is fatal. One mistyped entry in a list of four should not cost
    the build.
    """

    def __init__(self, roots, log: LogFn = _noop_log):
        if isinstance(roots, (str, Path)):
            roots = [roots]
        self.roots: list[Path] = []
        missing: list[Path] = []
        for entry in roots:
            entry = str(entry).strip()
            if not entry:
                continue
            path = Path(entry)
            (self.roots if path.is_dir() else missing).append(path)

        for path in missing:
            log(f"warning: STEP folder does not exist, skipped: {path}")

        if not self.roots:
            if missing:
                raise StepBuilderError(
                    "None of the STEP folders exist: "
                    + ", ".join(str(p) for p in missing)
                )
            raise StepBuilderError("No STEP folder was given")

        self._log = log
        self._case_folded = 0
        self._index: dict[str, Path] = {}
        # The same index folded to lower case, for the lookup of last resort.
        # Windows cannot hold two files in one folder whose names differ only in
        # case, but the name being looked up does not come from the disk - it
        # comes from Allegro's STEP mapping table, where it is typed by hand -
        # so MODEL.STEP on disk against model.step in the mapping is an ordinary
        # miss, and it used to read as "could not find model.step". Exact match
        # is still tried first and always wins, so nothing that resolved before
        # resolves differently now; and first-wins here follows the same root
        # order, which is what settles the ambiguity that a case-SENSITIVE
        # filesystem can present and Windows cannot.
        self._folded: dict[str, Path] = {}
        shadowed = 0
        for root in self.roots:
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                winner = self._index.setdefault(path.name, path)
                self._folded.setdefault(path.name.lower(), path)
                # Only across roots: two files of one name inside a single root
                # cannot be told apart by precedence, and reporting the walk
                # order would suggest a meaning it does not have.
                if winner != path and not _same_root(winner, root):
                    shadowed += 1
                    if shadowed <= 10:
                        log(f"{path.name}: using {winner} (also in {root})")
        if shadowed > 10:
            log(f"({shadowed - 10} further name(s) found in more than one folder)")

    def find(self, name: str) -> Path | None:
        hit = self._index.get(name)
        if hit is None and name:
            # The index is keyed on the bare filename; a mapping that carries a
            # path component ("subdir/model.step") would otherwise miss a file
            # that is sitting right there.
            bare = Path(name).name
            hit = self._index.get(bare)
            if hit is None:
                hit = self._folded.get(bare.lower())
                if hit is not None:
                    self._note_case(bare, hit)
        return hit

    def _note_case(self, asked: str, found: Path) -> None:
        """Say that a model was found only by ignoring case - a few times.

        Worth saying: it means the mapping table and the disk disagree, which is
        a real thing to tidy up, and on a case-sensitive filesystem it is the
        difference between a build and a missing model. Not worth saying two
        hundred times on a board whose whole library is spelled the other way,
        hence the same cap the shadowed-name report uses.
        """
        self._case_folded += 1
        if self._case_folded <= 10:
            self._log(f"{asked}: using {found.name} - the names differ only in case")
        elif self._case_folded == 11:
            self._log("(further model names matched only after ignoring case)")


def _same_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #

def _label_entry(label: TDF_Label) -> str:
    entry = TCollection_AsciiString()
    TDF_Tool.Entry_s(label, entry)
    return entry.ToCString()


def _free_shape_entries(shape_tool) -> dict[str, TDF_Label]:
    seq = TDF_LabelSequence()
    shape_tool.GetFreeShapes(seq)
    return {_label_entry(seq.Value(i)): seq.Value(i) for i in range(1, seq.Length() + 1)}


@dataclass
class BuildResult:
    output: Path
    components_placed: int = 0
    components_skipped: list[str] = field(default_factory=list)
    missing_step_files: list[str] = field(default_factory=list)
    # Model files that are on disk but could not be turned into geometry -
    # locked, empty, or a dialect OCCT declines. A separate list from the
    # missing ones because the fix is a different one, and because the
    # embedded-model advice does not apply to a file that is right there.
    unreadable_step_files: list[str] = field(default_factory=list)
    # Models the board carries a copy of, that were not found on disk. A
    # different problem from a plain missing file: the geometry exists, it is
    # just not where this tool can read it. See _report_embedded_only.
    embedded_not_on_disk: list[str] = field(default_factory=list)
    silkscreen_solids: int = 0
    silkscreen_skipped: int = 0
    # MFRPN reporting DISABLED (property attachment unreliable); kept for future:
    # missing_mfr_pn: list[str] = field(default_factory=list)


def _report_embedded_only(data: dict, result: BuildResult, log: LogFn) -> None:
    """Name the models the board carries but the disk does not, and say what to do.

    Allegro keeps its own copy of every mapped 3D model inside the .brd. This
    tool does not read those copies - it builds from model files on disk - so a
    board can look complete in Allegro's own 3D while a component is missing
    here. Without this the log said only "could not find X.step", which does not
    distinguish "that model does not exist anywhere" from "it is right there in
    the board, just not in your STEP folders" - and only the second has a fix.

    Silent when the JSON predates format_version 4, when the board has no
    embedded models, or when nothing is missing.
    """
    embedded = data.get("embedded_models")
    if not isinstance(embedded, list) or not embedded:
        return

    # Compare on the bare filename: the index resolves that way too, so a
    # mapping carrying a path component still matches.
    missing = {Path(str(name)).name for name in result.missing_step_files}
    if not missing:
        return

    both = sorted({str(name) for name in embedded
                   if Path(str(name)).name in missing})
    if not both:
        return

    result.embedded_not_on_disk = both
    log(f"warning: {len(both)} model(s) are stored inside the board but were "
        f"not found on disk: {', '.join(both)}")
    log("warning: Allegro's own 3D shows these because the board carries a copy "
        "of each mapped model. Simple 3D builds from model files on disk. To "
        "include them: export the board from Allegro's 3DX canvas, take the "
        "missing model files out of that export, put them in a folder listed "
        "under \"STEP files\" (the board's own folder is a convenient one), and "
        "run again.")


def _validate(data: dict) -> None:
    if "name" not in data:
        raise StepBuilderError("JSON is missing the 'name' field.")
    if "pcb" not in data:
        raise StepBuilderError("JSON is missing the 'pcb' object.")
    pcb = data["pcb"]
    for key in ("thickness", "edges", "color"):
        if key not in pcb:
            raise StepBuilderError(f"JSON is missing 'pcb.{key}'.")
    if "board" not in pcb["thickness"]:
        raise StepBuilderError("JSON is missing 'pcb.thickness.board'.")


def total_board_thickness(thickness: dict) -> float:
    """board + both soldermasks, the full physical stack.

    The SKILL side already sums dielectrics + planes + conductors into `board`
    and reports the two mask layers separately. Here they are added back so the
    solid has its true finished thickness (e.g. 1.054 + 0.025 + 0.025 = 1.104).
    Missing mask keys default to 0 so older JSON still works.
    """
    return (
        float(thickness["board"])
        + float(thickness.get("soldermask_top", 0.0))
        + float(thickness.get("soldermask_bottom", 0.0))
    )


# Marker written into every Simple 3D intermediate JSON. Any .json without it
# is some other file that happens to share the folder and must be ignored.
FORMAT_MARKER = "simple3d"


def is_simple3d_json(path: str | Path) -> bool:
    """True if *path* is a readable Simple 3D intermediate (has the marker).

    Used to filter a folder that may also hold unrelated .json files (netlist
    variant tables, tool configs, etc). Reads only enough to check the marker.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and data.get("format") == FORMAT_MARKER


def is_full_board(path: str | Path) -> bool:
    """True if this intermediate is the WHOLE board, with variants ignored.

    Written beside the per-variant files when `settings.exportFullBoard` is on,
    because the variant list says what is INSTALLED and a drawing sometimes has
    to show the bare board regardless. Told apart by a marker in the file rather
    than by its name: `<design>.json` against `<design>_<variant>.json` is a
    guess, and a variant is free to be called anything.

    False for anything unreadable or older - the key is optional, and an
    intermediate written before it simply does not have it.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and bool(data.get("full_board"))


def silkscreen_layers(path: str | Path) -> dict[str, dict[str, int]]:
    """{"top": {layer: polygon count}, "bottom": {...}} for one intermediate.

    What the GUI builds its checkbox list from. Taken from the file rather than
    from the config on purpose: the config says which layers were COLLECTED,
    this says which ones actually produced geometry on this board, so the list
    can never offer a layer that would do nothing.

    Empty for a format_version 2 file, whose polygons carry no layer - those
    build whole, as they always did.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    silk = data.get("silkscreen")
    if not isinstance(silk, dict):
        return {}

    out: dict[str, dict[str, int]] = {}
    for side in ("top", "bottom"):
        counts: dict[str, int] = {}
        for polygon in silk.get(side) or []:
            layer = polygon.get("layer")
            if layer:
                counts[layer] = counts.get(layer, 0) + 1
        if counts:
            out[side] = counts
    return out


def dated_output_name(base: str, output_dir: str | Path) -> str:
    """<base>_simple_DD_MM_YYYY, with a trailing _ per existing collision.

    Shared by the GUI and the CLI so the naming rule cannot drift between them.
    """
    from datetime import date

    output_dir = Path(output_dir)
    stem = f"{base}_simple_{date.today().strftime('%d_%m_%Y')}"
    candidate = stem
    while (output_dir / f"{candidate}.step").exists():
        candidate += "_"
    return candidate


def output_stem(json_file: str | Path, output_dir: str | Path, *,
                brd_name: str | None = None, several: bool = False,
                dated: bool = False) -> str | None:
    """What to call one job's .step, or None to use the JSON's own `name`.

    The whole naming rule in one place, because keeping it in two is what let
    the GUI and the CLI disagree: **brd_name used to be read on the dated path
    only**, so `--brd-name X` without `--dated-name` was silently ignored and
    the file came out named after the JSON. The launcher always passes both, so
    nothing in the shipped flow ever showed it.

    brd_name is the board's name in its ORIGINAL case - the exporter lower-cases
    the JSON filename, and this is what puts the capitals back.

    several: more than one variant is being built in this run. Then each JSON's
    own stem (design_variant) has to name its output, or one brd_name would be
    handed to every variant and they would collide.
    """
    stem = Path(json_file).stem
    base = stem if several else (brd_name or stem)
    if dated:
        return dated_output_name(base, output_dir)
    if brd_name and not several:
        return brd_name
    return None


def resolve_json_jobs(path: str | Path) -> tuple[list[Path], list[Path]]:
    """Resolve what to build from a user-visible path, at generate time.

    *path* may be a single JSON file or a folder of variant JSONs. Returns
    (jobs, ignored): jobs are Simple 3D intermediates to build, ignored are
    .json files present but lacking the format marker.

    Resolving at generate time - instead of caching a job list when the paths
    are first filled in - means the field the user sees is always the truth:
    picking a different file or editing the path cannot leave a stale queue
    behind.
    """
    p = Path(path)
    if p.is_dir():
        all_jsons = sorted(p.glob("*.json"))
        jobs = [j for j in all_jsons if is_simple3d_json(j)]
        ignored = [j for j in all_jsons if j not in jobs]
        return jobs, ignored
    if p.is_file():
        if is_simple3d_json(p):
            return [p], []
        return [], [p]
    return [], []


def _set_color(color_tool, label, rgb01, srgb: bool) -> None:
    color_type = (
        Quantity_TypeOfColor.Quantity_TOC_sRGB
        if srgb
        else Quantity_TypeOfColor.Quantity_TOC_RGB
    )
    color = Quantity_Color(rgb01[0], rgb01[1], rgb01[2], color_type)
    for target in (
        XCAFDoc_ColorType.XCAFDoc_ColorSurf,
        XCAFDoc_ColorType.XCAFDoc_ColorCurv,
        XCAFDoc_ColorType.XCAFDoc_ColorGen,
    ):
        color_tool.SetColor(label, color, target)


def _rim_faces(shape: TopoDS_Shape, fold=None):
    """Return the vertical (edge/rim) faces of the board.

    The rim is the set of side walls, identified by a horizontal normal
    (normal_z ~ 0), i.e. faces whose plane is vertical. Classifying by
    z-position instead was wrong: a straight board's side walls have their
    centre of mass at mid-height, exactly on the top/bottom boundary, so they
    leaked into the "top" set and the rim color landed on a flat face.
    Everything with a vertical normal is rim; the flat top and bottom faces
    keep the board color.

    **On a folded board, "vertical" is asked in the panel's own frame.** A tail
    folded through 90 degrees has its top face standing vertically, and the
    plain test would paint the whole of it as rim - which is not a subtle
    error, it is most of the board in the wrong color. Each face is put back
    into the flat frame of the panel it came from before its normal is judged,
    so the rim of a folded board is the same set of faces it was before the
    fold.
    """
    # TopoDS is NOT re-imported here: it is a module-level import already, and
    # a local import of a module-level name makes that name local to the whole
    # function - which is how the GUI launcher acquired an UnboundLocalError.
    # Harmless while these lines sit first, a trap the moment anything is added
    # above them.
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.GeomAbs import GeomAbs_SurfaceType
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer

    def unfolded_z(face, direction) -> float:
        """A direction's z, in the frame of the panel the face sits on."""
        if fold is None:
            return direction.Z()
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        back = fold.flat_frame(props.CentreOfMass())
        if back is None:
            return direction.Z()
        return direction.Transformed(back).Z()

    rim = []
    exp = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        surf = BRepAdaptor_Surface(face)
        kind = surf.GetType()
        if kind == GeomAbs_SurfaceType.GeomAbs_Plane:
            nz = unfolded_z(face, surf.Plane().Axis().Direction())
            if abs(nz) < 0.5:            # vertical wall -> rim
                rim.append(face)
        elif kind == GeomAbs_SurfaceType.GeomAbs_Cylinder:
            # A cylinder is a drill or a rounded cutout edge - rim - UNLESS it
            # is the surface of a bend, which is the board's own face wrapped
            # round. The two are told apart by the axis: a hole's runs through
            # the board, a bend's runs along it. Getting this wrong paints the
            # whole inside and outside of every bend as rim.
            axis = surf.Cylinder().Axis().Direction()
            if abs(unfolded_z(face, axis)) > 0.5:
                rim.append(face)
        else:
            # any other curved wall (a swept cutout edge, say) counts as rim
            rim.append(face)
        exp.Next()
    return rim


def _sanitize(name: str) -> str:
    """Make a string safe as a STEP product/instance name."""
    return "".join(c if c.isalnum() or c in "_-+." else "_" for c in name)


def generate(
    step_dir: str | Path | Iterable[str | Path],
    json_file: str | Path,
    output_dir: str | Path,
    *,
    output_name: str | None = None,
    z_datum: str = "top",
    board_color: tuple[int, int, int] | None = None,
    rim_color: tuple[int, int, int] | None = None,
    silk_top: bool = True,
    silk_bottom: bool = True,
    silk_color: tuple[int, int, int] | None = None,
    silk_flat: bool = False,
    silk_flat_height: float = DEFAULT_FLAT_HEIGHT,
    silk_layers_off: set[str] | frozenset[str] | None = None,
    # MFRPN DISABLED (kept for future): name_instances_with_mfr_pn: bool = False,
    minimize_size: bool = True,
    srgb_color: bool = True,
    board_mode: str = "solid",
    layer_colors: dict | None = None,
    ignore_soldermask: bool = False,
    fold_bends: bool = True,
    fold_anchor: tuple[float, float] | str | None = None,
    fold_neutral: float | None = None,
    fold_slice_angle: float | None = None,
    log: LogFn = _noop_log,
    progress: ProgressFn = _noop_progress,
) -> BuildResult:
    """Build the STEP assembly described by *json_file*.

    step_dir:
        One model folder, or several as an ordered search path - the first that
        holds a given filename wins, so a project-local folder listed ahead of
        the shared library overrides individual models. Each is walked
        recursively. See StepFileIndex.
    output_name:
        Base filename (without .step). Defaults to the JSON's `name` field.
    z_datum:
        "top"    -> z=0 at the top face, board extends downwards (top parts at 0).
        "bottom" -> z=0 at the bottom face, board extends upwards (bottom parts at 0).
    board_color / rim_color:
        RGB 0-255. board_color defaults to the JSON's pcb.color. rim_color, if
        given, paints the board sides + underside separately from the top face.
    silk_top / silk_bottom:
        Build the printed legend on that side, if the JSON carries one
        (format_version 2+). Both False skips silkscreen entirely. Silently
        does nothing for an older JSON or a board with no silkscreen.
    silk_color:
        RGB 0-255 for the ink; defaults to colors.SILK_COLORS["White"].
    silk_flat:
        Draw the legend as surfaces instead of thin solids. About a quarter of
        the file size; the ink then has no thickness and cannot be used in
        downstream boolean work. See build_silkscreen.
    silk_flat_height:
        Clearance in mm between the board face and a flat legend, so the two
        are not coplanar and do not flicker. Ignored in solid mode.
    silk_layers_off:
        Layer names whose polygons are left out of this build. The export
        collects every layer the config lists and tags each polygon with its
        own, so which of them reach the model is decided here, per build, with
        no re-export. Polygons with no layer (format_version 2) are never
        filtered - there is nothing to match them against.
    minimize_size:
        Set write.surfacecurve.mode = 0 (about half the file size, geometry
        unchanged) and share one part per distinct model.
    srgb_color:
        Treat colors as sRGB (what you set is what you see). False reproduces
        the original C++ linear-RGB behaviour.
    board_mode:
        How the board body is built - on ANY board, not only a multi-stackup
        one: with no zones, the outline becomes one implicit zone on the single
        stackup. The two non-solid modes need the stackup layers, so a JSON
        written before format_version 6 warns and falls back to one solid.
          "solid"   - one solid, one color, coplanar faces merged. Smallest.
          "layers"  - one solid, but the layer interfaces are kept and each
                      face is colored by what kind of layer it belongs to, so
                      the rim shows the stack. About 4.7x "solid".
          "inspect" - every layer a separate named part. For taking the board
                      apart by eye; largest of the three.
    layer_colors:
        {kind: (r, g, b)} for board_mode="layers", kinds as in colors.LAYER_KINDS
        (copper, base, coverlay, adhesive, stiffener, soldermask, other).
        Missing kinds fall back to colors.DEFAULT_LAYER_COLORS.
    ignore_soldermask:
        Leave the soldermask out of the board entirely, however the design
        defines it, and close the stack up toward the core by exactly the
        thickness removed - on both sides, independently. Components then sit
        on the copper rather than on the mask. Applies to a multi-stackup
        board's layers and to a plain board's pcb.thickness alike.
    fold_bends:
        Fold the board along its bend areas (format_version 7). The board, the
        legend and the components all move together. False exports it flat,
        which is how Allegro holds it and how every export before this behaved.
        A board with no bend areas is unaffected either way. See bend.py.
    fold_anchor:
        (x, y) of the piece that stays in the XY plane. None means the
        documented default, the ORIGIN; "auto" holds the largest piece the bend
        lines leave instead.
    fold_neutral:
        Where the neutral axis sits in the stack, as a fraction of thickness
        from the inner surface (default 0.5). It sets how much flat material a
        bend consumes: angle x (radius + k x thickness).
    fold_slice_angle:
        Degrees of arc per slice for a bend that has to be faceted (default
        7.5). Only reached when neither exact construction applies.
    """
    json_file = Path(json_file)
    output_dir = Path(output_dir)

    if z_datum not in ("top", "bottom"):
        raise StepBuilderError(f"z_datum must be 'top' or 'bottom', got {z_datum!r}")

    if not json_file.is_file():
        raise StepBuilderError(f"Input file does not exist: {json_file}")

    # Coarse phases, so the bar moves while the slow part is happening rather
    # than filling up at the very end. The board is the slow one on a folded
    # rigid-flex design - a minute of the two it takes - and it used to show
    # nothing at all.
    def phase(value: float, label: str) -> None:
        try:
            progress(value, 100, label)
        except TypeError:                    # a caller from before the label
            progress(int(value), 100)

    phase(2, "Reading the intermediate")
    index = StepFileIndex(step_dir, log=log)

    log(f"Reading {json_file.name}")
    try:
        data = json.loads(json_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StepBuilderError(f"{json_file.name} is not valid JSON: {exc}") from exc

    _validate(data)

    pcb_name = data["name"]
    json_stem = output_name or pcb_name
    if ignore_soldermask:
        # The plain-board path keeps its masks in pcb.thickness rather than as
        # stackup layers, so it is the same decision expressed twice.
        thickness = float(data["pcb"]["thickness"]["board"])
    else:
        thickness = total_board_thickness(data["pcb"]["thickness"])

    # Multi-stackup: a rigid-flex board is several zones of different
    # thickness. An empty or absent list means an ordinary board and every
    # path below stays exactly as it was.
    zones = data.get("zones")
    zones = zones if isinstance(zones, list) and zones else None
    stackups = data.get("stackups")
    stackups = stackups if isinstance(stackups, dict) and stackups else None
    levels = None
    shift = 0.0

    # An ordinary board has one stackup and no zones, because there is nothing
    # to divide. "Body stitching" still means something there - the layers are
    # known - so the whole outline becomes one implicit zone and every mode
    # works everywhere. Only for the modes that need it: plain "Solid" keeps the
    # single-prism path, which is what the C++-verified regression measures.
    if not zones and board_mode != "solid":
        contours = data["pcb"].get("edges") or []
        if stackups and len(stackups) == 1 and contours:
            only = next(iter(stackups))
            zones = [{"name": "board", "stackup": only, "contour": contours[0]}]
            log(f"Single-stackup board: building it as one zone on stackup "
                f"{only!r} so the body stitching applies")
        else:
            # An intermediate written before format_version 6 carries no
            # stackup layers, so there is nothing to stitch by. Say so: the
            # setting quietly doing nothing is exactly what this is here to
            # stop.
            log(f"warning: body stitching {board_mode!r} needs the stackup "
                f"layers and this JSON does not carry them - re-export from "
                f"Allegro. Building one plain solid instead.")

    if stackups and ignore_soldermask:
        stackups = drop_soldermask(stackups, log)

    if zones:
        if stackups:
            # format_version 6: every layer carries its own extent, so the
            # board is built layer by layer rather than as one prism per zone.
            levels, board_top_z, board_bottom_z, shift = stackup_levels(
                stackups, zones, z_datum)
        else:
            levels, board_top_z, board_bottom_z = zone_levels(zones, z_datum)
        extrude_z_offset = board_top_z
        log(f"Multi-stackup board: {len(zones)} zone(s), "
            f"{board_top_z - board_bottom_z:.3f} mm at its thickest")
        for zone in zones:
            name = str(zone["name"])
            if name in levels:
                top, bottom = levels[name]
                log(f"  {name} ({zone['stackup']}): {top - bottom:.3f} mm")
    elif z_datum == "top":
        # Where the two board faces live, given the datum choice.
        board_top_z, board_bottom_z = 0.0, -thickness
        extrude_z_offset = 0.0            # outline drawn at z=0, prism goes down
    else:
        board_top_z, board_bottom_z = thickness, 0.0
        extrude_z_offset = thickness       # outline at z=+T, prism goes down to 0

    # ---- bends ----------------------------------------------------------- #
    # Worked out here, once, because everything the fold touches - the board,
    # the legend, every component - has to be carried by the SAME plan, and the
    # plan needs the two board faces, which are only known now.
    fold = None
    if fold_bends:
        from .bend import (DEFAULT_ANCHOR, DEFAULT_NEUTRAL_FACTOR,
                           DEFAULT_SLICE_ANGLE, plan_from_json)

        # None means "the documented default", the origin; the string "auto"
        # is how a caller asks for the old behaviour of holding the largest
        # piece instead. A pair is the point itself.
        if fold_anchor is None:
            anchor = DEFAULT_ANCHOR
        elif isinstance(fold_anchor, str):
            anchor = None
        else:
            anchor = (float(fold_anchor[0]), float(fold_anchor[1]))

        plan = plan_from_json(
            data, board_top_z, board_bottom_z, zones=zones, levels=levels,
            anchor=anchor,
            neutral_factor=(DEFAULT_NEUTRAL_FACTOR if fold_neutral is None
                            else float(fold_neutral)),
            slice_angle=(DEFAULT_SLICE_ANGLE if fold_slice_angle is None
                         else float(fold_slice_angle)),
            log=log)
        if plan:
            for line in plan.describe():
                log(line)
            fold = plan
    elif data.get("bends"):
        log("Bend folding is off: the board is exported flat")

    def folded(shape, fuse: bool = True, note: bool = True):
        """One shape through the fold, or unchanged when there is nothing to do.

        note=False for the legend: a letter inside a bend area is never the
        straight strip the exact construction needs, and saying so once per
        build is noise - the board is what the message is about.
        """
        return fold.apply(shape, fuse=fuse, note=note, log=log) if fold else shape

    # (write.surfacecurve.mode is set AFTER the writer is constructed, see
    # below - the STEPCAFControl_Writer constructor resets it, so setting it
    # here would be silently undone.)

    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())

    main_assembly = shape_tool.NewShape()
    TDataStd_Name.Set_s(main_assembly, TCollection_ExtendedString(_sanitize(json_stem)))

    # ---- board ----------------------------------------------------------- #
    phase(10, "Building the board")
    log("Building board geometry")

    multi = bool(zones and stackups)
    mode = board_mode if multi else "solid"

    if mode == "layers":
        # One solid, but the layer interfaces survive and every face is
        # colored by the kind of layer it belongs to, so the rim shows the
        # stack. See fuse_keeping_faces for why UnifySameDomain is skipped.
        from .colors import DEFAULT_LAYER_COLORS, layer_kind

        palette = {**DEFAULT_LAYER_COLORS, **(layer_colors or {})}
        parts = make_board_layer_parts(data["pcb"], stackups, zones, shift, log)
        # Folded BEFORE the fuse, not after: the per-face colors below are keyed
        # on the face objects the fuse hands back, and folding a shape replaces
        # every face in it. Fold first and the two steps do not fight.
        if fold:
            parts = [(zone, layer, folded(solid)) for zone, layer, solid in parts]
        board, faces = fuse_keeping_faces(parts, log)

        pcb_label = shape_tool.NewShape()
        shape_tool.SetShape(pcb_label, board)

        used: dict[str, int] = {}
        for face, layer in faces:
            kind = layer_kind(layer)
            rgb = palette.get(kind, DEFAULT_LAYER_COLORS["other"])
            color = Quantity_Color(
                rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0,
                Quantity_TypeOfColor.Quantity_TOC_sRGB if srgb_color
                else Quantity_TypeOfColor.Quantity_TOC_RGB)
            color_tool.SetColor(face, color, XCAFDoc_ColorType.XCAFDoc_ColorSurf)
            used[kind] = used.get(kind, 0) + 1

        log(f"Layer-colored board: one solid, {len(faces)} face(s) colored "
            f"by layer kind")
        for kind, count in sorted(used.items()):
            rgb = palette.get(kind, DEFAULT_LAYER_COLORS["other"])
            log(f"  {kind}: {count} face(s), RGB {rgb[0]},{rgb[1]},{rgb[2]}")

    elif mode == "inspect":
        # Not stitched: every stackup layer stays its own named part. Colors
        # come from the SAME per-kind palette the stitched-and-colored mode
        # uses, so switching between the two changes how the board is put
        # together and nothing else - a second palette would have made the two
        # pictures needlessly hard to compare.
        from .colors import DEFAULT_LAYER_COLORS, layer_kind

        palette = {**DEFAULT_LAYER_COLORS, **(layer_colors or {})}
        parts = make_board_layer_parts(data["pcb"], stackups, zones, shift, log)
        group = shape_tool.NewShape()
        TDataStd_Name.Set_s(group,
                            TCollection_ExtendedString(_sanitize(f"PCB_{json_stem}")))
        shape_tool.AddComponent(main_assembly, group, TopLoc_Location(gp_Trsf()))

        for zone_name, layer, solid in parts:
            layer_name = str(layer.get("name") or "?")
            label = shape_tool.NewShape()
            shape_tool.SetShape(label, folded(solid))
            rgb = palette.get(layer_kind(layer), DEFAULT_LAYER_COLORS["other"])
            _set_color(color_tool, label,
                       (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0), srgb_color)
            TDataStd_Name.Set_s(
                label,
                TCollection_ExtendedString(_sanitize(f"{zone_name}__{layer_name}")))
            shape_tool.AddComponent(group, label, TopLoc_Location(gp_Trsf()))

        log(f"Not stitched: {len(parts)} separate layer part(s), "
            f"colored by layer kind")
        shape_tool.UpdateAssemblies()
        board = None
        pcb_label = None
    elif fold and multi:
        # Folded, and the board is several stackups: the bend has to be applied
        # to each LAYER and only then fused. A bend area on a real board reaches
        # across a zone boundary - 0.16 mm into the stiffener on the test board -
        # so the fused board is two different thicknesses inside the same bend,
        # which is not something that can be wrapped onto one pair of cylinders.
        # Per layer it is, and the fuse afterwards gives the same solid.
        parts = make_board_layer_parts(data["pcb"], stackups, zones, shift, log)
        board = fuse_and_unify([folded(solid) for _, _, solid in parts], log)

        pcb_label = shape_tool.NewShape()
        shape_tool.SetShape(pcb_label, board)
    else:
        board = make_board_geometry(data["pcb"], thickness, extrude_z_offset,
                                    zones=zones, levels=levels, stackups=stackups,
                                    shift=shift, log=log)
        board = folded(board)

        pcb_label = shape_tool.NewShape()
        shape_tool.SetShape(pcb_label, board)

    if fold:
        for line in fold.summary():
            log(f"warning: {line.strip()}")

    # Both non-solid modes have already decided every color on the board:
    # "inspect" per part, "layers" per face. A board color or a rim color
    # applied over the top would either be ignored by the viewer or, worse,
    # win - and paint the stack a single color, which is the one thing those
    # modes exist to avoid.
    if mode != "solid" and rim_color is not None:
        log(f"warning: the rim color is ignored in board mode {mode!r}")

    if board_color is None:
        rgb = data["pcb"]["color"]
        board_rgb01 = (float(rgb["r"]), float(rgb["g"]), float(rgb["b"]))
    else:
        board_rgb01 = (board_color[0] / 255.0, board_color[1] / 255.0, board_color[2] / 255.0)

    if pcb_label is not None and mode == "solid":
        _set_color(color_tool, pcb_label, board_rgb01, srgb_color)

    if pcb_label is not None and mode == "solid" and rim_color is not None:
        # Paint the rim (vertical side walls) separately. This needs per-face
        # color, which costs a few extra entities but is what the user asked
        # for. The flat top/bottom keep the board color.
        rim_rgb01 = (rim_color[0] / 255.0, rim_color[1] / 255.0, rim_color[2] / 255.0)
        rim_faces = _rim_faces(board, fold)
        rim_q = Quantity_Color(
            rim_rgb01[0], rim_rgb01[1], rim_rgb01[2],
            Quantity_TypeOfColor.Quantity_TOC_sRGB if srgb_color
            else Quantity_TypeOfColor.Quantity_TOC_RGB,
        )
        for face in rim_faces:
            color_tool.SetColor(face, rim_q, XCAFDoc_ColorType.XCAFDoc_ColorSurf)

    # Name the board part per board (PCB_<jsonstem>), not a bare "PCB": otherwise
    # importing several boards into one CAD session, each carrying a part called
    # "PCB", lets one board's PCB silently substitute another's.
    if pcb_label is not None:
        TDataStd_Name.Set_s(pcb_label,
                            TCollection_ExtendedString(_sanitize(f"PCB_{json_stem}")))
        shape_tool.AddComponent(main_assembly, pcb_label, TopLoc_Location(gp_Trsf()))

    # ---- silkscreen ------------------------------------------------------ #
    # Its own part per side, so it can be hidden or recolored in the viewer
    # without touching the board, and so the two sides stay distinguishable.
    phase(60, "Building the legend")
    silk_data = data.get("silkscreen")
    silk_built = 0
    silk_skipped = 0
    want_silk = silk_top or silk_bottom
    if silk_data:
        # Reported even when the legend is switched off: the objects are still
        # wrong in the board, and the Allegro console that first said so has
        # long scrolled away by the time anyone opens the model.
        for message in silk_data.get("warnings") or []:
            log(f"warning: {message}")
    if want_silk and silk_data:
        from .colors import SILK_COLORS

        ink = silk_color if silk_color is not None else SILK_COLORS["White"]
        ink01 = (ink[0] / 255.0, ink[1] / 255.0, ink[2] / 255.0)
        ink_thickness = float(silk_data.get("thickness", DEFAULT_SILK_THICKNESS))

        # The ink sits ON the outer face of each side and grows away from the
        # board, so it never intersects the solid it is printed on.
        excluded = set(silk_layers_off or ())
        for wanted, side, polygons, z, sign in (
            (silk_top, "silkscreen_top", silk_data.get("top") or [], board_top_z, 1.0),
            (silk_bottom, "silkscreen_bot", silk_data.get("bottom") or [],
             board_bottom_z, -1.0),
        ):
            if not wanted or not polygons:
                continue
            if excluded:
                total = len(polygons)
                polygons = [p for p in polygons
                            if p.get("layer") not in excluded]
                dropped = total - len(polygons)
                if dropped:
                    log(f"{side}: {dropped} polygon(s) left out by layer")
                if not polygons:
                    continue
            log(f"Building {side} ({len(polygons)} polygons)")
            compound, built, skipped = build_silkscreen(
                polygons, z, sign * ink_thickness, log=log, side=side,
                flat=silk_flat, flat_offset=sign * abs(silk_flat_height),
            )
            silk_built += built
            silk_skipped += skipped
            if compound is None:
                continue
            # fuse=False: the legend was never one solid, and fusing thousands
            # of barely touching prisms was measured at 154% of the file size
            # (round 10g). Folding does not change that arithmetic.
            silk_label = shape_tool.NewShape()
            shape_tool.SetShape(silk_label, folded(compound, fuse=False, note=False))
            _set_color(color_tool, silk_label, ink01, srgb_color)
            TDataStd_Name.Set_s(
                silk_label,
                TCollection_ExtendedString(_sanitize(f"{side}_{json_stem}")),
            )
            shape_tool.AddComponent(main_assembly, silk_label, TopLoc_Location(gp_Trsf()))
    elif want_silk and not silk_data:
        log("No silkscreen in this JSON (re-export from Allegro to include it)")

    # ---- component group assemblies (symbols_top / symbols_bot) ---------- #
    # Created lazily so a single-sided board does not get an empty group.
    # Named per board (<side>_<jsonstem>) for the same reason the board part and
    # the legend are: two boards imported into one CAD session would otherwise
    # each bring a "symbols_top", and one can silently substitute the other.
    groups: dict[str, TDF_Label] = {}

    def group_for(side: str) -> TDF_Label:
        if side not in groups:
            grp = shape_tool.NewShape()
            TDataStd_Name.Set_s(
                grp, TCollection_ExtendedString(_sanitize(f"{side}_{json_stem}")))
            shape_tool.AddComponent(main_assembly, grp, TopLoc_Location(gp_Trsf()))
            groups[side] = grp
        return groups[side]

    # ---- components ------------------------------------------------------ #
    # Anything not reserved is a refdes. "silkscreen" MUST be listed here or it
    # would be walked as if it were a component.
    _reserved = ("name", "pcb", "format", "format_version", "silkscreen",
                 "embedded_models", "zones", "stackups", "bends", "full_board")
    components = {k: v for k, v in data.items() if k not in _reserved}
    result = BuildResult(
        output=output_dir / f"{json_stem}.step",
        silkscreen_solids=silk_built,
        silkscreen_skipped=silk_skipped,
    )

    # One shared part per distinct STEP model (task 5). The label is imported
    # once and every refdes referencing that model becomes an instance of it, so
    # ten identical resistors cost one solid, not ten. Named by the model file,
    # which co-varies with geometry -> no cross-board substitution.
    label_cache: dict[str, list[TDF_Label]] = {}
    named_parts: set[str] = set()

    total = len(components)
    for i, (ref_des, component) in enumerate(components.items(), start=1):
        phase(75 + 20.0 * i / max(total, 1), f"Placing components {i}/{total}")

        mapping = component.get("step_mapping")
        if not mapping or not mapping.get("step_name"):
            log(f"warning: {ref_des} has no step_mapping, skipped")
            result.components_skipped.append(ref_des)
            continue

        step_name = mapping["step_name"]

        if step_name not in label_cache:
            path = index.find(step_name)
            if path is None:
                log(f"warning: could not find {step_name}")
                result.missing_step_files.append(step_name)
                label_cache[step_name] = []
            else:
                # A model file that is PRESENT but unusable costs its own
                # component and nothing more - the same treatment a missing one
                # gets. It used to raise, which meant one file locked by another
                # application, one zero-byte copy or one dialect OCCT declines
                # took the whole board down. The three ways it can fail are
                # reported separately: they have different causes.
                log(f"Reading {step_name}")
                reader = STEPCAFControl_Reader()
                reader.SetColorMode(True)
                reader.SetNameMode(True)

                problem = None
                new_labels: list[TDF_Label] = []
                try:
                    if reader.ReadFile(str(path)) != IFSelect_ReturnStatus.IFSelect_RetDone:
                        problem = ("could not be read (locked, empty, or not a "
                                   "STEP file OCCT accepts)")
                    else:
                        # FIX: diff the free shapes around the transfer instead
                        # of assuming everything from index 2 belongs to this file.
                        before = _free_shape_entries(shape_tool)
                        if not reader.Transfer(doc):
                            problem = "could not be transferred into the assembly"
                        else:
                            after = _free_shape_entries(shape_tool)
                            new_labels = [lab for e, lab in after.items()
                                          if e not in before]
                            if not new_labels:
                                problem = "contained no shapes"
                except Exception as exc:                # OCCT can throw here
                    problem = f"raised {exc.__class__.__name__}: {exc}"

                if problem is not None:
                    # Kept apart from missing_step_files on purpose: the file IS
                    # on disk, so the "it is inside the board, not on your disk"
                    # advice _report_embedded_only gives would be wrong here.
                    log(f"warning: {step_name} {problem}: {path}")
                    result.unreadable_step_files.append(step_name)
                    label_cache[step_name] = []
                else:
                    # Name the shared part after the model file (stem), once.
                    part_name = _sanitize(Path(step_name).stem)
                    if part_name and part_name not in named_parts:
                        TDataStd_Name.Set_s(
                            new_labels[0], TCollection_ExtendedString(part_name)
                        )
                        named_parts.add(part_name)
                    label_cache[step_name] = new_labels

        roots = label_cache[step_name]
        if not roots:
            result.components_skipped.append(ref_des)
            continue

        # MFRPN tracking DISABLED (property attachment unreliable); keep for future:
        # mfr_pn = component.get("mfr_pn")
        # if not mfr_pn:
        #     result.missing_mfr_pn.append(ref_des)

        trsf = component_transform(mapping, component, board_top_z, board_bottom_z,
                                   zone_levels=levels)

        # A folded board carries its parts with it. The component is placed in
        # the FLAT frame first and then moved by whatever its panel does, which
        # is the same composition the board geometry goes through - so a part
        # cannot drift off the surface it was placed on.
        if fold:
            x, y = float(component["x"]), float(component["y"])
            in_bend = fold.in_bend_area(x, y)
            if in_bend:
                log(f"warning: {ref_des} stands in bend area {in_bend} - it is "
                    f"placed on the curve, but a component there is a design "
                    f"rule violation, not a modelling choice")
            trsf = fold.transform_at(x, y) * trsf

        # Place the shared part DIRECTLY under symbols_top / symbols_bot, as an
        # instance that carries the STEP file's own name. No per-refdes wrapper
        # sub-assembly and no refdes_<board> instance name (that was
        # over-complication): the tree under symbols_* is just the model parts,
        # instanced in place. The part is still shared, so N identical footprints
        # cost one solid.
        side = "symbols_bot" if component["is_mirrored"] else "symbols_top"
        parent = group_for(side)

        for root in roots:
            shape_tool.AddComponent(parent, root, TopLoc_Location(trsf))
        result.components_placed += 1

    _report_embedded_only(data, result, log)

    # Without this the written document is empty.
    shape_tool.UpdateAssemblies()

    # ---- write ----------------------------------------------------------- #
    # FIX: the C++ version hardcoded a backslash separator, which produced a
    # file literally named "out\name.step" on anything but Windows.
    phase(96, "Writing the STEP file")
    output_dir.mkdir(parents=True, exist_ok=True)

    writer = STEPCAFControl_Writer()
    writer.SetColorMode(True)
    writer.SetNameMode(True)

    # Set write.surfacecurve.mode HERE, after the writer is constructed: its
    # constructor resets this global to 1, so setting it any earlier is undone.
    # mode 0 drops the p-curves on faces -> about half the file size, geometry
    # identical (same volume and bbox, verified). Set explicitly both ways so
    # the sticky global never leaks between successive builds in one process.
    Interface_Static.SetIVal_s("write.surfacecurve.mode", 0 if minimize_size else 1)

    if not writer.Transfer(doc, STEPControl_StepModelType.STEPControl_AsIs):
        raise StepBuilderError("STEP writer transfer failed")

    status = writer.Write(str(result.output))
    if status != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise StepBuilderError(f"Failed to write {result.output} (status {status})")

    phase(100, "Done")
    log(f"Wrote {result.output}")
    return result
