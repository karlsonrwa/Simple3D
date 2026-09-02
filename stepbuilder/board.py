"""The board body: from the intermediate's outline, zones and layers to one
solid (or one solid per layer), with every hole cut out.

Three ways in, decided by `core.generate`: a plain board is its outline
extruded to `pcb.thickness` (`make_board_geometry`); a board with zones is
every layer of every zone built between the faces `stackup.stackup_levels`
computed, fused into one (`_stackup_board`) or kept apart for inspection
(`make_board_layer_parts`, then `fuse_keeping_faces` for the layer-coloured
build); a format_version 5 file with zones but no layers is one prism per
zone (`_zone_solid`). `_layer_region` is where a drawn layer shape becomes
material or an opening; `board_cutouts` is where a repeated cutout is
dropped before it can erase the whole board; `has_solid` is the test a
boolean's IsDone() does not give. `_rim_faces` picks the side walls for the
rim colour, in the panel's own frame on a folded board.

The reasons behind each are in the docstrings; the measurements behind
them in PROJECT_NOTES rounds 21, 26-34, 61 and 67.
"""

from __future__ import annotations

import json

from OCP.BRep import BRep_Builder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape
from OCP.gp import gp_Vec

from .contour import _face_from_wires, build_contour
from .errors import StepBuilderError
from .reporting import LogFn, _noop_log


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

    # Only the name that is not imported at module level. Importing
    # BRepAlgoAPI_Cut here too made it a LOCAL of this whole function, so
    # any use above this line would have raised UnboundLocalError.
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common

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
            # An EMPTY shape is not a null one. _layer_region hands back the
            # result of a boolean, and a layer whose drawn shapes lie entirely
            # outside this zone - a stiffener that is only on the flex arms,
            # say - intersects it in nothing at all. That is ordinary, and it
            # is why this is a skip and not an error; what must not happen is
            # an empty part being carried into the assembly, which is what the
            # bare IsNull() test used to allow.
            if solid.IsNull() or not has_solid(solid):
                # A negative layer whose openings swallow the whole zone is the
                # one case here that is usually a SETTING rather than a design,
                # so it gets told apart and named. Allegro's own 3D Canvas guide
                # says a coverlay is read as negative and that "coverlays
                # specified as positive shapes are not rendered in 3D canvas" -
                # so a design that draws them as material is a real thing, and
                # this is what it looks like from in here.
                if layer.get("negative") and layer.get("shapes"):
                    log(f"warning: {layer.get('name')} is marked as an OPENING "
                        f"in this intermediate and its shapes cover the whole "
                        f"of zone {zone['name']}, so none of it is left there. "
                        f"If this design draws that layer as MATERIAL instead, "
                        f"take its name out of settings.negativeLayers and "
                        f"export the board again - the polarity is decided at "
                        f"export time and written into the file.")
                else:
                    log(f"{layer.get('name')} has no material in zone "
                        f"{zone['name']}; not built there")
                continue
            if cutouts:
                solid = _cut_out(solid, cutouts, top + 0.01,
                                 gp_Vec(0, 0, -(height + 0.02)))
                # Likewise not an error - a small drawn shape can sit entirely
                # inside a milled opening.
                if solid.IsNull() or not has_solid(solid):
                    log(f"warning: layer {layer.get('name')} of zone "
                        f"{zone['name']} is left with nothing by its cutouts; "
                        f"skipped")
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
