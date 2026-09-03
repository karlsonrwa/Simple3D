"""
Core logic for building a STEP assembly from the Allegro intermediate JSON.

Port of StepBuilder.cpp (https://github.com/juulsA/exportStep) to Python/OCP.
Contains no UI code: everything reports through callbacks so it can be driven
from the GUI, from the CLI, or from tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from OCP.Quantity import Quantity_Color, Quantity_TypeOfColor
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Shape
from OCP.XCAFDoc import XCAFDoc_ColorType
from OCP.gp import gp_Trsf

# The contour primitives and the one exception live in modules of their own
# (round 72, plan A1) so that bend.py no longer has to reach into core for
# them. Re-exported here: callers wrote `core.build_contour` and
# `core.StepBuilderError` for a year.
from .contour import (  # noqa: F401 - re-exported
    WIRE_TOLERANCE, _face_from_wires, _open_wire_detail, build_contour,
    contour_points, point_in_polygon,
)
# The board builders (round 73, plan A4); re-exported, the tests call them
# as core.make_board_geometry and friends.
from .board import (  # noqa: F401 - re-exported
    _cut_out, _layer_region, _rim_faces, _shape_face, _stackup_board, _zone_solid,
    board_cutouts, fuse_and_unify, fuse_keeping_faces, has_solid, layer_solids,
    make_board_geometry, make_board_layer_parts,
)
from .errors import StepBuilderError  # noqa: F401 - re-exported
# What one build is asked for (round 73, plan A8).
from .build import BOARD_MODES, BuildOptions  # noqa: F401 - re-exported
# The XCAF document and its writer (round 73, plan A7).
from .stepdoc import StepDocument, _set_color  # noqa: F401 - re-exported
# Component models (round 73, plan A6); re-exported, test_index imports
# StepFileIndex from here.
from .models import (  # noqa: F401 - re-exported
    ModelCache, StepFileIndex, _free_shape_entries, _label_entry,
    _report_embedded_only, _rotation, _same_root, _sanitize, component_transform,
)
# The silkscreen legend (round 73, plan A5); re-exported, the window imports
# DEFAULT_FLAT_HEIGHT from here and the tests call core.build_silkscreen.
from .legend import (  # noqa: F401 - re-exported
    AREA_TOLERANCE, DEFAULT_FLAT_HEIGHT, DEFAULT_SILK_THICKNESS, RULE_AXIS,
    RULE_TRAVEL, _Convention, _arc_bulges_left, _arc_edge, _arc_geometry,
    _describe_convention, _face_area, _merge_coplanar, _pick_convention,
    _silk_face, _silk_point, _wire_from_vertices, build_silkscreen,
    clip_silk_to_zones,
)
from .reporting import (  # noqa: F401 - re-exported
    LogFn, ProgressFn, _noop_log, _noop_progress,
)
# The stackup arithmetic (round 72, plan A3); re-exported, the tests call it
# as core.restack and friends.
from .stackup import (  # noqa: F401 - re-exported
    SOLDERMASK_MARKER, _is_conductor, _is_soldermask, align_stackups,
    board_stackup, drop_soldermask, restack, stackup_levels, thickness_parts,
    zone_levels,
)
# The intermediate is read once per file (round 72, plan A2); the probes
# and the naming rule moved with it. Re-exported: the window, the worker and
# the CLI call them as core.<name>.
from .intermediate import (  # noqa: F401 - re-exported
    FORMAT_MARKER, RESERVED, Intermediate, batch_jobs, dated_output_name, is_full_board,
    is_simple3d_json, output_stem, resolve_jobs, resolve_json_jobs,
    silkscreen_layers,
)

# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #

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


def board_thickness_parts(data: dict, log: LogFn) -> dict:
    """{soldermask_top, board, soldermask_bottom}: `pcb.thickness` when the file
    has it and the stackups agree, the stackups otherwise.

    `pcb.thickness` is optional since format_version 9 (round 79, E2): a
    rigid-flex design with no Primary stackup writes none. What is missing
    is measured from the stackup that is the board (Primary, else the first);
    what is present is checked against it, and the stackup wins when the two
    disagree by more than a micron - an intermediate written before round 76
    carried the combined view's number on a rigid-flex board.
    """
    written = (data.get("pcb") or {}).get("thickness")
    chosen = board_stackup(data.get("stackups") or {})
    measured = thickness_parts(chosen[1]) if chosen else None
    if not isinstance(written, dict):
        if measured is None:
            raise StepBuilderError("JSON has no pcb.thickness and no stackup to measure it from.")
        log(f"note: pcb.thickness is not in the file; measured from stackup "
            f"{chosen[0]}: {total_board_thickness(measured):.3f} mm")
        return measured
    if measured is not None and abs(total_board_thickness(written) - total_board_thickness(measured)) > 1e-3:
        log(f"warning: pcb.thickness says {total_board_thickness(written):.3f} mm and stackup "
            f"{chosen[0]} says {total_board_thickness(measured):.3f} mm; using the stackup "
            f"(an intermediate exported before round 76 carried the combined view's "
            f"number on a rigid-flex board)")
        return measured
    return written


# --------------------------------------------------------------------------- #
# the stages of a build (round 73, plan A9)
# --------------------------------------------------------------------------- #

@dataclass
class _Stack:
    """What the stackup stage settled, read by every stage after it."""

    thickness: float
    zones: list | None
    stackups: dict | None
    levels: dict | None
    shift: float
    board_top_z: float
    board_bottom_z: float
    extrude_z_offset: float


def _prepare_stackups(data: dict, options: BuildOptions, log: LogFn) -> _Stack:
    """Thickness, zones, stackups and the two board faces, from the intermediate
    and the options - the arithmetic every later stage builds between."""
    z_datum = options.z_datum
    board_mode = options.board_mode
    ignore_soldermask = options.ignore_soldermask

    parts = board_thickness_parts(data, log)
    if ignore_soldermask:
        # The plain-board path keeps its masks in pcb.thickness rather than as
        # stackup layers, so it is the same decision expressed twice.
        thickness = float(parts["board"])
    else:
        thickness = total_board_thickness(parts)

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

    # AFTER drop_soldermask, never before: `restack` re-derives every z from the
    # stackup's own first conductor, which is exactly the datum being corrected
    # here, so aligning first would simply be undone.
    if stackups:
        stackups = align_stackups(stackups, log)

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

    return _Stack(thickness=thickness, zones=zones, stackups=stackups, levels=levels, shift=shift, board_top_z=board_top_z, board_bottom_z=board_bottom_z, extrude_z_offset=extrude_z_offset)


def _plan_fold(data: dict, stack: _Stack, options: BuildOptions, log: LogFn):
    """The fold plan, or None when the board is exported flat.

    Worked out here, once, because everything the fold touches - the board,
    the legend, every component - has to be carried by the SAME plan, and the
    plan needs the two board faces, which are only known now.
    """
    fold_bends = options.fold_bends
    fold_anchor = options.fold_anchor
    fold_neutral = options.fold_neutral
    fold_slice_angle = options.fold_slice_angle
    zones = stack.zones
    levels = stack.levels
    board_top_z = stack.board_top_z
    board_bottom_z = stack.board_bottom_z

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

    return fold


def _folded(fold, log: LogFn, shape, fuse: bool = True, note: bool = True):
    """One shape through the fold, or unchanged when there is nothing to do.

    note=False for the legend: a letter inside a bend area is never the
    straight strip the exact construction needs, and saying so once per
    build is noise - the board is what the message is about.
    """
    return fold.apply(shape, fuse=fuse, note=note, log=log) if fold else shape


def _build_board(data: dict, stack: _Stack, fold, options: BuildOptions,
                 document: StepDocument, json_stem: str, log: LogFn) -> None:
    """The board body into the document: one of the four ways, coloured and
    named. Nothing after this reads the board itself."""
    board_color = options.board_color
    rim_color = options.rim_color
    srgb_color = options.srgb_color
    board_mode = options.board_mode
    layer_colors = options.layer_colors
    thickness = stack.thickness
    zones = stack.zones
    stackups = stack.stackups
    levels = stack.levels
    shift = stack.shift
    extrude_z_offset = stack.extrude_z_offset
    shape_tool = document.shape_tool
    color_tool = document.color_tool
    main_assembly = document.root

    # ---- board ----------------------------------------------------------- #
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
            parts = [(zone, layer, _folded(fold, log, solid)) for zone, layer, solid in parts]
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
            shape_tool.SetShape(label, _folded(fold, log, solid))
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
        board = fuse_and_unify([_folded(fold, log, solid) for _, _, solid in parts], log)

        pcb_label = shape_tool.NewShape()
        shape_tool.SetShape(pcb_label, board)
    else:
        board = make_board_geometry(data["pcb"], thickness, extrude_z_offset,
                                    zones=zones, levels=levels, stackups=stackups,
                                    shift=shift, log=log)
        board = _folded(fold, log, board)

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


def _build_legend(data: dict, stack: _Stack, fold, options: BuildOptions,
                  document: StepDocument, json_stem: str, log: LogFn) -> tuple[int, int]:
    """The silkscreen legend into the document, one part per side.
    Returns (solids built, polygons skipped)."""
    silk_top = options.silk_top
    silk_bottom = options.silk_bottom
    silk_color = options.silk_color
    silk_flat = options.silk_flat
    silk_flat_height = options.silk_flat_height
    silk_layers_off = options.silk_layers_off
    srgb_color = options.srgb_color
    zones = stack.zones
    stackups = stack.stackups
    board_top_z = stack.board_top_z
    board_bottom_z = stack.board_bottom_z
    shape_tool = document.shape_tool
    color_tool = document.color_tool
    main_assembly = document.root

    # ---- silkscreen ------------------------------------------------------ #
    # Its own part per side, so it can be hidden or recolored in the viewer
    # without touching the board, and so the two sides stay distinguishable.
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
        for wanted, side, polygons, z, sign, face in (
            (silk_top, "silkscreen_top", silk_data.get("top") or [],
             board_top_z, 1.0, "top"),
            (silk_bottom, "silkscreen_bot", silk_data.get("bottom") or [],
             board_bottom_z, -1.0, "bottom"),
        ):
            if not wanted or not polygons:
                continue
            # A zone whose stackup has no silkscreen layer is not printed on.
            polygons = clip_silk_to_zones(polygons, stackups, zones, face, log)
            if not polygons:
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
            shape_tool.SetShape(silk_label, _folded(fold, log, compound, fuse=False, note=False))
            _set_color(color_tool, silk_label, ink01, srgb_color)
            TDataStd_Name.Set_s(
                silk_label,
                TCollection_ExtendedString(_sanitize(f"{side}_{json_stem}")),
            )
            shape_tool.AddComponent(main_assembly, silk_label, TopLoc_Location(gp_Trsf()))
    elif want_silk and not silk_data:
        log("No silkscreen in this JSON (re-export from Allegro to include it)")

    return silk_built, silk_skipped


def _place_components(inter: Intermediate, stack: _Stack, fold, options: BuildOptions,
                      document: StepDocument, index: StepFileIndex, json_stem: str,
                      output_dir: Path, silk_built: int, silk_skipped: int,
                      log: LogFn, phase) -> BuildResult:
    """Every component placed under symbols_top / symbols_bot, one shared part
    per distinct model. Returns the BuildResult, minus the write."""
    data = inter.data
    levels = stack.levels
    board_top_z = stack.board_top_z
    board_bottom_z = stack.board_bottom_z
    doc = document.doc
    shape_tool = document.shape_tool
    main_assembly = document.root

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
    # A v9 file has them under "components"; in a v1-v8 file anything not
    # reserved is a refdes (intermediate.RESERVED). Intermediate.components
    # knows both shapes.
    components = inter.components
    result = BuildResult(
        output=output_dir / f"{json_stem}.step",
        silkscreen_solids=silk_built,
        silkscreen_skipped=silk_skipped,
    )

    # One shared part per distinct STEP model: models.ModelCache reads each
    # file once and names the part after it.
    models = ModelCache(index, doc, shape_tool, log)

    total = len(components)
    for i, (ref_des, component) in enumerate(components.items(), start=1):
        phase(75 + 20.0 * i / max(total, 1), f"Placing components {i}/{total}")

        mapping = component.get("step_mapping")
        if not mapping or not mapping.get("step_name"):
            log(f"warning: {ref_des} has no step_mapping, skipped")
            result.components_skipped.append(ref_des)
            continue

        step_name = mapping["step_name"]

        roots, problem = models.labels_for(step_name)
        if problem == "missing":
            result.missing_step_files.append(step_name)
        elif problem == "unreadable":
            result.unreadable_step_files.append(step_name)
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

    return result


def generate(
    step_dir: str | Path | Iterable[str | Path],
    json_file: str | Path | Intermediate,
    output_dir: str | Path,
    *,
    options: BuildOptions | None = None,
    log: LogFn = _noop_log,
    progress: ProgressFn = _noop_progress,
    **keywords,
) -> BuildResult:
    """Build the STEP assembly described by *json_file*.

    step_dir:
        One model folder, or several as an ordered search path - the first that
        holds a given filename wins, so a project-local folder listed ahead of
        the shared library overrides individual models. Each is walked
        recursively. See StepFileIndex.

    Everything else is a BuildOptions field, passed as `options=` or as the
    keywords of the same names, which build one. See build.BuildOptions for
    what each means.
    """
    if options is None:
        options = BuildOptions(**keywords)      # an unknown keyword is a TypeError, as before
    elif keywords:
        raise TypeError(f"generate(): options= and {sorted(keywords)} given together")
    output_name = options.output_name
    z_datum = options.z_datum                 # validated below, before anything is built
    board_mode = options.board_mode           # likewise
    minimize_size = options.minimize_size

    # A path is read here; an Intermediate the caller already read (the
    # worker and the CLI batch resolve the jobs first) is used as it is, so a
    # build parses each file once.
    inter = json_file if isinstance(json_file, Intermediate) else None
    json_file = inter.path if inter is not None else Path(json_file)
    output_dir = Path(output_dir)

    if z_datum not in ("top", "bottom"):
        raise StepBuilderError(f"z_datum must be 'top' or 'bottom', got {z_datum!r}")
    if board_mode not in BOARD_MODES:
        # An unknown mode used to fall through to the plain solid, silently.
        raise StepBuilderError(f"board_mode must be one of {', '.join(BOARD_MODES)}, "
                               f"got {board_mode!r}")

    if inter is None and not json_file.is_file():
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
    if inter is None:
        inter = Intermediate.read(json_file)
    inter.validate()
    # The exporter's own lines about this file (a variant naming components
    # the board does not have), repeated here because the Allegro console has
    # scrolled away by the time the model is looked at (2026-09-03). The
    # silkscreen's warnings are logged where the legend is built.
    for message in inter.warnings:
        log(f"warning: {message}")
    data = inter.data

    pcb_name = data["name"]
    json_stem = output_name or pcb_name

    stack = _prepare_stackups(data, options, log)
    fold = _plan_fold(data, stack, options, log)
    document = StepDocument(json_stem)

    phase(10, "Building the board")
    _build_board(data, stack, fold, options, document, json_stem, log)

    phase(60, "Building the legend")
    silk_built, silk_skipped = _build_legend(data, stack, fold, options, document,
                                             json_stem, log)

    result = _place_components(inter, stack, fold, options, document, index,
                               json_stem, output_dir, silk_built, silk_skipped,
                               log, phase)

    # ---- write ----------------------------------------------------------- #
    # FIX: the C++ version hardcoded a backslash separator, which produced a
    # file literally named "out\name.step" on anything but Windows.
    phase(96, "Writing the STEP file")
    output_dir.mkdir(parents=True, exist_ok=True)
    document.write(result.output, minimize_size)

    phase(100, "Done")
    log(f"Wrote {result.output}")
    return result
