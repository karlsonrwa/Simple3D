"""One Simple 3D intermediate JSON, read once, and what is built from it.

The exporter writes one file per variant (plus the whole board when asked),
and every question the Python half asks of such a file - is it ours, is it
the whole board, which silkscreen layers does it carry, which keys are
components - used to be a function that opened and parsed the file again.
The window asked two of them per keystroke and a build asked three per file;
on a 2.7 MB intermediate that is not free. `Intermediate` parses once and
answers all of them. The module-level functions of the old names remain, as
thin wrappers, for a caller that holds a path and wants one answer.

`RESERVED` is the one list of top-level keys that are not components. The
exporter's NOTE beside its header (makeVariant3dIntermediates.il) points
here: a key added there and not here is walked as if it were a refdes.

The naming rule (`output_stem`, `dated_output_name`) lives here too, because
it is about what is built from one intermediate and both the window and the
CLI must apply the same one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .errors import StepBuilderError

# Marker written into every Simple 3D intermediate JSON. Any .json without it
# is some other file that happens to share the folder and must be ignored.
FORMAT_MARKER = "simple3d"

# Every top-level key that is NOT a component; anything else is a refdes or a
# mechanical symbol's synthetic name. "silkscreen" MUST be listed here or it
# would be walked as if it were a component - and so must every key the
# exporter adds in future.
RESERVED = ("name", "pcb", "format", "format_version", "silkscreen",
            "embedded_models", "zones", "stackups", "bends", "full_board")


class Intermediate:
    """One parsed intermediate: its path and the JSON object as read."""

    __slots__ = ("path", "data")

    def __init__(self, path: Path, data: dict) -> None:
        self.path = Path(path)
        self.data = data

    @classmethod
    def read(cls, path: str | Path) -> "Intermediate":
        """Parse *path* for a build: what cannot be used is a StepBuilderError."""
        path = Path(path)
        if not path.is_file():
            raise StepBuilderError(f"Input file does not exist: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StepBuilderError(f"{path.name} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise StepBuilderError(f"{path.name} does not hold a JSON object")
        return cls(path, data)

    @classmethod
    def probe(cls, path: str | Path) -> "Intermediate | None":
        """Parse *path* if it parses at all; None otherwise.

        For filtering a folder: an unreadable file, a file that is not JSON and
        a JSON that is not an object are all "not one of ours", not errors.
        """
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        return cls(path, data)

    @property
    def is_simple3d(self) -> bool:
        """Carries the format marker - i.e. the exporter wrote it."""
        return self.data.get("format") == FORMAT_MARKER

    @property
    def is_full_board(self) -> bool:
        """The WHOLE board, with variants ignored.

        Written beside the per-variant files when `settings.exportFullBoard` is
        on, because the variant list says what is INSTALLED and a drawing
        sometimes has to show the bare board regardless. Told apart by a marker
        in the file rather than by its name: `<design>.json` against
        `<design>_<variant>.json` is a guess, and a variant is free to be called
        anything. False for an older file - the key is optional.
        """
        return bool(self.data.get("full_board"))

    @property
    def components(self) -> dict:
        """Everything that is not a reserved key: refdes -> placement."""
        return {k: v for k, v in self.data.items() if k not in RESERVED}

    @property
    def metadata(self) -> dict:
        """The reserved keys this file carries, and their values."""
        return {k: v for k, v in self.data.items() if k in RESERVED}

    def validate(self) -> None:
        """The fields a build cannot default; their absence is an error."""
        data = self.data
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

    def silkscreen_layers(self) -> dict[str, dict[str, int]]:
        """{"top": {layer: polygon count}, "bottom": {...}} for this intermediate.

        What the GUI builds its checkbox list from. Taken from the file rather than
        from the config on purpose: the config says which layers were COLLECTED,
        this says which ones actually produced geometry on this board, so the list
        can never offer a layer that would do nothing.

        Empty for a format_version 2 file, whose polygons carry no layer - those
        build whole, as they always did.
        """
        data = self.data
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


# ---- the old names, for a caller that holds a path ----------------------- #

def is_simple3d_json(path: str | Path) -> bool:
    """True if *path* is a readable Simple 3D intermediate (has the marker).

    Used to filter a folder that may also hold unrelated .json files (netlist
    variant tables, tool configs, etc).
    """
    inter = Intermediate.probe(path)
    return inter is not None and inter.is_simple3d


def is_full_board(path: str | Path) -> bool:
    """True if *path* is the whole-board intermediate; False for anything else,
    unreadable and older files included."""
    inter = Intermediate.probe(path)
    return inter is not None and inter.is_full_board


def silkscreen_layers(path: str | Path) -> dict[str, dict[str, int]]:
    """{"top": {layer: polygon count}, "bottom": {...}} for the file at *path*;
    {} when it cannot be read."""
    inter = Intermediate.probe(path)
    return inter.silkscreen_layers() if inter is not None else {}


def resolve_jobs(path: str | Path) -> tuple[list[Intermediate], list[Path]]:
    """What to build from a user-visible path, parsed once each.

    *path* may be a single JSON file or a folder of variant JSONs. Returns
    (jobs, ignored): jobs are the Simple 3D intermediates to build, already
    read; ignored are .json files present but lacking the format marker.

    Resolving at generate time - instead of caching a job list when the paths
    are first filled in - means the field the user sees is always the truth:
    picking a different file or editing the path cannot leave a stale queue
    behind.
    """
    p = Path(path)
    if p.is_dir():
        jobs: list[Intermediate] = []
        ignored: list[Path] = []
        for j in sorted(p.glob("*.json")):
            inter = Intermediate.probe(j)
            if inter is not None and inter.is_simple3d:
                jobs.append(inter)
            else:
                ignored.append(j)
        return jobs, ignored
    if p.is_file():
        inter = Intermediate.probe(p)
        if inter is not None and inter.is_simple3d:
            return [inter], []
        return [], [p]
    return [], []


def batch_jobs(jobs: list[Intermediate], build_full_board: bool,
               log: Callable[[str], None]) -> list[Intermediate]:
    """The jobs of a batch, with the whole-board file left out when not wanted.

    The whole-board file, when the export wrote one, is just another job.
    Dropping it is a choice about a BATCH: with a folder queued you usually
    want the variants and only sometimes the full board as well. A single
    file the user pointed at directly is never dropped - they chose it, and
    a switch that silently refuses the one file you selected is worse than
    one that does nothing. One rule for the window's checkbox and the CLI's
    --no-full-board alike (round 73, plan A10; it lived in the worker only).
    """
    if len(jobs) > 1 and not build_full_board:
        full = [j for j in jobs if j.is_full_board]
        if full:
            jobs = [j for j in jobs if j not in full]
            log("Not building the full-board file(s): "
                + ", ".join(j.path.name for j in full))
    elif len(jobs) == 1 and not build_full_board and jobs[0].is_full_board:
        log(f"{jobs[0].path.name} is the whole board and the only file "
            f"queued, so it is built despite the switch")
    return jobs


def resolve_json_jobs(path: str | Path) -> tuple[list[Path], list[Path]]:
    """resolve_jobs, as paths - the shape callers had before round 72."""
    jobs, ignored = resolve_jobs(path)
    return [j.path for j in jobs], ignored


# ---- naming what is built ------------------------------------------------ #

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
