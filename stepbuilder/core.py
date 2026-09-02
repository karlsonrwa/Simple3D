"""
Core logic for building a STEP assembly from the Allegro intermediate JSON.

Port of StepBuilder.cpp (https://github.com/juulsA/exportStep) to Python/OCP.
Contains no UI code: everything reports through callbacks so it can be driven
from the GUI, from the CLI, or from tests.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.Interface import Interface_Static
from OCP.Quantity import Quantity_Color, Quantity_TypeOfColor
from OCP.STEPCAFControl import STEPCAFControl_Reader, STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_StepModelType
from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label, TDF_LabelSequence, TDF_Tool
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Shape
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

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
    drop_soldermask, restack, stackup_levels, zone_levels,
)
# The intermediate is read once per file (round 72, plan A2); the probes
# and the naming rule moved with it. Re-exported: the window, the worker and
# the CLI call them as core.<name>.
from .intermediate import (  # noqa: F401 - re-exported
    FORMAT_MARKER, RESERVED, Intermediate, dated_output_name, is_full_board,
    is_simple3d_json, output_stem, resolve_jobs, resolve_json_jobs,
    silkscreen_layers,
)

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


def _sanitize(name: str) -> str:
    """Make a string safe as a STEP product/instance name."""
    return "".join(c if c.isalnum() or c in "_-+." else "_" for c in name)


def generate(
    step_dir: str | Path | Iterable[str | Path],
    json_file: str | Path | Intermediate,
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
    # A path is read here; an Intermediate the caller already read (the
    # worker and the CLI batch resolve the jobs first) is used as it is, so a
    # build parses each file once.
    inter = json_file if isinstance(json_file, Intermediate) else None
    json_file = inter.path if inter is not None else Path(json_file)
    output_dir = Path(output_dir)

    if z_datum not in ("top", "bottom"):
        raise StepBuilderError(f"z_datum must be 'top' or 'bottom', got {z_datum!r}")

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
    data = inter.data

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
    # Anything not reserved is a refdes; the reserved keys are the one list
    # in intermediate.RESERVED, which the exporter's NOTE points at.
    components = inter.components
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
