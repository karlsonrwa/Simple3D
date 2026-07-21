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
ProgressFn = Callable[[int, int], None]


def _noop_log(message: str) -> None:
    pass


def _noop_progress(current: int, total: int) -> None:
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
        raise StepBuilderError(
            f"Contour is open (start and end do not meet within {WIRE_TOLERANCE})."
        )
    return wire


def make_board_geometry(pcb: dict, thickness: float, z_offset: float = 0.0) -> TopoDS_Shape:
    """Extrude the board outline downwards and cut every hole/cutout out of it.

    edges[0] is the outline; every following contour is a cutout. All cutout
    prisms are collected into one compound and removed with a single boolean
    Cut: the original per-cutout loop was quadratic (every Cut re-processed an
    increasingly complex board) and measured ~11x slower at 120 drill holes.
    """
    contours = pcb["edges"]
    if not contours:
        raise StepBuilderError("pcb.edges is empty")

    # FIX: the C++ version special-cased len==1 and passed the whole array
    # instead of contours[0]. It only worked because the nesting happened to
    # collapse. edges[0] is always the outline.
    wire = build_contour(contours[0], z_offset)
    face = BRepBuilderAPI_MakeFace(wire, True)
    if not face.IsDone():
        raise StepBuilderError("Board outline is not planar or self-intersects")

    direction = gp_Vec(0, 0, -thickness)
    board = BRepPrimAPI_MakePrism(face.Face(), direction).Shape()

    if len(contours) > 1:
        builder = BRep_Builder()
        compound = TopoDS_Compound()
        builder.MakeCompound(compound)
        for i, cutout in enumerate(contours[1:], start=1):
            cut_wire = build_contour(cutout, z_offset)
            cut_face = BRepBuilderAPI_MakeFace(cut_wire, True)
            if not cut_face.IsDone():
                raise StepBuilderError(f"Cutout #{i} is not planar or self-intersects")
            builder.Add(compound, BRepPrimAPI_MakePrism(cut_face.Face(), direction).Shape())

        cut = BRepAlgoAPI_Cut(board, compound)
        if not cut.IsDone():
            raise StepBuilderError("Boolean cut of board cutouts failed")
        board = cut.Shape()
        if board.IsNull():
            raise StepBuilderError("Board geometry is empty after cutting")

    return board


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

    position = gp_Trsf()
    position.SetTranslation(gp_Vec(component["x"], component["y"], z))

    return position * angle * mirror * offset * rotation



# --------------------------------------------------------------------------- #
# step file lookup
# --------------------------------------------------------------------------- #

class StepFileIndex:
    """Filename -> path index, built once.

    The C++ version ran a recursive_directory_iterator for every cache miss,
    which is O(components x files). One walk is enough.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        if not self.root.is_dir():
            raise StepBuilderError(f"STEP directory does not exist: {self.root}")
        self._index: dict[str, Path] = {}
        for path in self.root.rglob("*"):
            if path.is_file():
                self._index.setdefault(path.name, path)

    def find(self, name: str) -> Path | None:
        return self._index.get(name)


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
    # MFRPN reporting DISABLED (property attachment unreliable); kept for future:
    # missing_mfr_pn: list[str] = field(default_factory=list)


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


def _rim_faces(shape: TopoDS_Shape):
    """Return the vertical (edge/rim) faces of the board.

    The rim is the set of side walls, identified by a horizontal normal
    (normal_z ~ 0), i.e. faces whose plane is vertical. Classifying by
    z-position instead was wrong: a straight board's side walls have their
    centre of mass at mid-height, exactly on the top/bottom boundary, so they
    leaked into the "top" set and the rim colour landed on a flat face.
    Everything with a vertical normal is rim; the flat top and bottom faces
    keep the board colour.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_SurfaceType
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    rim = []
    exp = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        surf = BRepAdaptor_Surface(face)
        if surf.GetType() == GeomAbs_SurfaceType.GeomAbs_Plane:
            nz = surf.Plane().Axis().Direction().Z()
            if abs(nz) < 0.5:            # vertical wall -> rim
                rim.append(face)
        else:
            # curved wall (e.g. a rounded cutout edge) counts as rim too
            rim.append(face)
        exp.Next()
    return rim


def _sanitize(name: str) -> str:
    """Make a string safe as a STEP product/instance name."""
    return "".join(c if c.isalnum() or c in "_-+." else "_" for c in name)


def generate(
    step_dir: str | Path,
    json_file: str | Path,
    output_dir: str | Path,
    *,
    output_name: str | None = None,
    z_datum: str = "top",
    board_color: tuple[int, int, int] | None = None,
    rim_color: tuple[int, int, int] | None = None,
    # MFRPN DISABLED (kept for future): name_instances_with_mfr_pn: bool = False,
    minimize_size: bool = True,
    srgb_color: bool = True,
    log: LogFn = _noop_log,
    progress: ProgressFn = _noop_progress,
) -> BuildResult:
    """Build the STEP assembly described by *json_file*.

    output_name:
        Base filename (without .step). Defaults to the JSON's `name` field.
    z_datum:
        "top"    -> z=0 at the top face, board extends downwards (top parts at 0).
        "bottom" -> z=0 at the bottom face, board extends upwards (bottom parts at 0).
    board_color / rim_color:
        RGB 0-255. board_color defaults to the JSON's pcb.color. rim_color, if
        given, paints the board sides + underside separately from the top face.
    minimize_size:
        Set write.surfacecurve.mode = 0 (about half the file size, geometry
        unchanged) and share one part per distinct model.
    srgb_color:
        Treat colours as sRGB (what you set is what you see). False reproduces
        the original C++ linear-RGB behaviour.
    """
    json_file = Path(json_file)
    output_dir = Path(output_dir)

    if z_datum not in ("top", "bottom"):
        raise StepBuilderError(f"z_datum must be 'top' or 'bottom', got {z_datum!r}")

    if not json_file.is_file():
        raise StepBuilderError(f"Input file does not exist: {json_file}")

    index = StepFileIndex(step_dir)

    log(f"Reading {json_file.name}")
    try:
        data = json.loads(json_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StepBuilderError(f"{json_file.name} is not valid JSON: {exc}") from exc

    _validate(data)

    pcb_name = data["name"]
    json_stem = output_name or pcb_name
    thickness = total_board_thickness(data["pcb"]["thickness"])

    # Where the two board faces live, given the datum choice.
    if z_datum == "top":
        board_top_z, board_bottom_z = 0.0, -thickness
        extrude_z_offset = 0.0            # outline drawn at z=0, prism goes down
    else:
        board_top_z, board_bottom_z = thickness, 0.0
        extrude_z_offset = thickness       # outline at z=+T, prism goes down to 0

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
    log("Building board geometry")
    board = make_board_geometry(data["pcb"], thickness, extrude_z_offset)

    pcb_label = shape_tool.NewShape()
    shape_tool.SetShape(pcb_label, board)

    if board_color is None:
        rgb = data["pcb"]["color"]
        board_rgb01 = (float(rgb["r"]), float(rgb["g"]), float(rgb["b"]))
    else:
        board_rgb01 = (board_color[0] / 255.0, board_color[1] / 255.0, board_color[2] / 255.0)

    _set_color(color_tool, pcb_label, board_rgb01, srgb_color)

    if rim_color is not None:
        # Paint the rim (vertical side walls) separately. This needs per-face
        # colour, which costs a few extra entities but is what the user asked
        # for. The flat top/bottom keep the board colour.
        rim_rgb01 = (rim_color[0] / 255.0, rim_color[1] / 255.0, rim_color[2] / 255.0)
        rim_faces = _rim_faces(board)
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
    TDataStd_Name.Set_s(pcb_label, TCollection_ExtendedString(_sanitize(f"PCB_{json_stem}")))
    shape_tool.AddComponent(main_assembly, pcb_label, TopLoc_Location(gp_Trsf()))

    # ---- component group assemblies (symbols_top / symbols_bot) ---------- #
    # Created lazily so a single-sided board does not get an empty group.
    groups: dict[str, TDF_Label] = {}

    def group_for(side: str) -> TDF_Label:
        if side not in groups:
            grp = shape_tool.NewShape()
            TDataStd_Name.Set_s(grp, TCollection_ExtendedString(side))
            shape_tool.AddComponent(main_assembly, grp, TopLoc_Location(gp_Trsf()))
            groups[side] = grp
        return groups[side]

    # ---- components ------------------------------------------------------ #
    _reserved = ("name", "pcb", "format", "format_version")
    components = {k: v for k, v in data.items() if k not in _reserved}
    result = BuildResult(output=output_dir / f"{json_stem}.step")

    # One shared part per distinct STEP model (task 5). The label is imported
    # once and every refdes referencing that model becomes an instance of it, so
    # ten identical resistors cost one solid, not ten. Named by the model file,
    # which co-varies with geometry -> no cross-board substitution.
    label_cache: dict[str, list[TDF_Label]] = {}
    named_parts: set[str] = set()

    total = len(components)
    for i, (ref_des, component) in enumerate(components.items(), start=1):
        progress(i, total)

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
                log(f"Reading {step_name}")
                reader = STEPCAFControl_Reader()
                reader.SetColorMode(True)
                reader.SetNameMode(True)

                if reader.ReadFile(str(path)) != IFSelect_ReturnStatus.IFSelect_RetDone:
                    raise StepBuilderError(f"Could not read STEP file: {path}")

                # FIX: diff the free shapes around the transfer instead of
                # assuming everything from index 2 belongs to this file.
                before = _free_shape_entries(shape_tool)
                if not reader.Transfer(doc):
                    raise StepBuilderError(f"Could not transfer STEP file: {path}")
                after = _free_shape_entries(shape_tool)

                new_labels = [lab for e, lab in after.items() if e not in before]
                if not new_labels:
                    raise StepBuilderError(f"{step_name} contained no shapes")

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

        trsf = component_transform(mapping, component, board_top_z, board_bottom_z)

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

    # Without this the written document is empty.
    shape_tool.UpdateAssemblies()

    # ---- write ----------------------------------------------------------- #
    # FIX: the C++ version hardcoded a backslash separator, which produced a
    # file literally named "out\name.step" on anything but Windows.
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

    log(f"Wrote {result.output}")
    return result
