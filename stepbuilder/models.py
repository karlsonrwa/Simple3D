"""Component models: where a STEP file is found, how it is read once and
shared, how a part is placed, and what to say about the ones that are
inside the board but not on disk.

`StepFileIndex` walks the model folders once, in order - the first folder
that holds a name wins, and a name found only by ignoring case is said so.
`ModelCache` reads each distinct model once into the assembly document and
hands back its labels, so N identical footprints cost one solid.
`component_transform` is the placement: mapping rotation, mapping offset,
the flip for a bottom-side part, the symbol angle, the position - and on a
multi-stackup board the surface of the part's own zone. Round 73, plan A6:
moved out of core.py, the cache being the one piece that was not a function
before.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label, TDF_LabelSequence, TDF_Tool
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

from .errors import StepBuilderError
from .reporting import LogFn, _noop_log

if TYPE_CHECKING:
    from .core import BuildResult


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


def _label_entry(label: TDF_Label) -> str:
    entry = TCollection_AsciiString()
    TDF_Tool.Entry_s(label, entry)
    return entry.ToCString()


def _free_shape_entries(shape_tool) -> dict[str, TDF_Label]:
    seq = TDF_LabelSequence()
    shape_tool.GetFreeShapes(seq)
    return {_label_entry(seq.Value(i)): seq.Value(i) for i in range(1, seq.Length() + 1)}


def _sanitize(name: str) -> str:
    """Make a string safe as a STEP product/instance name."""
    return "".join(c if c.isalnum() or c in "_-+." else "_" for c in name)


class ModelCache:
    """One shared part per distinct STEP model.

    The label is imported once and every refdes referencing that model
    becomes an instance of it, so ten identical resistors cost one solid,
    not ten. Named by the model file, which co-varies with geometry - no
    cross-board substitution. The read-once block of generate's component
    loop until round 73 (plan A6).
    """

    def __init__(self, index: StepFileIndex, doc, shape_tool, log: LogFn = _noop_log) -> None:
        self._index = index
        self._doc = doc
        self._shape_tool = shape_tool
        self._log = log
        self._labels: dict[str, list[TDF_Label]] = {}
        self._named: set[str] = set()

    def labels_for(self, step_name: str) -> tuple[list[TDF_Label], str | None]:
        """The document labels of *step_name*'s root shapes, read on first use.

        Returns (labels, problem). *problem* is "missing" (not in any model
        folder) or "unreadable" (on disk but unusable) the FIRST time a name
        fails and None on every later ask, so a caller counts each file once;
        *labels* is empty whenever the file could not be used.
        """
        if step_name in self._labels:
            return self._labels[step_name], None
        path = self._index.find(step_name)
        if path is None:
            self._log(f"warning: could not find {step_name}")
            self._labels[step_name] = []
            return [], "missing"
        else:
            # A model file that is PRESENT but unusable costs its own
            # component and nothing more - the same treatment a missing one
            # gets. It used to raise, which meant one file locked by another
            # application, one zero-byte copy or one dialect OCCT declines
            # took the whole board down. The three ways it can fail are
            # reported separately: they have different causes.
            self._log(f"Reading {step_name}")
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
                    before = _free_shape_entries(self._shape_tool)
                    if not reader.Transfer(self._doc):
                        problem = "could not be transferred into the assembly"
                    else:
                        after = _free_shape_entries(self._shape_tool)
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
                self._log(f"warning: {step_name} {problem}: {path}")
                self._labels[step_name] = []
                return [], "unreadable"
            else:
                # Name the shared part after the model file (stem), once.
                part_name = _sanitize(Path(step_name).stem)
                if part_name and part_name not in self._named:
                    TDataStd_Name.Set_s(
                        new_labels[0], TCollection_ExtendedString(part_name)
                    )
                    self._named.add(part_name)
                self._labels[step_name] = new_labels
                return new_labels, None


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
