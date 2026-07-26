"""The build, run in a process of its own.

**Why a process and not a thread.** OpenCASCADE can die outright - an access
violation inside a boolean, not an exception - and a thread cannot survive that:
it takes the whole interpreter with it, and with the GUI that means the window
simply disappears with nothing written anywhere. Measured on a real board:
`flex2-a0` with a bend that has to be faceted at 5 degrees per slice kills
`fuse_keeping_faces` with 0xC0000005, in "Solid" and in "Solid colored layers"
alike, while "Not stitched" - which fuses nothing - comes through. At 7.5
degrees the same board builds.

So the build runs in a child process and the window keeps a pipe to it. If the
child dies, the parent has its exit code and says so, which is the difference
between a bug report and a mystery.

Everything here has to be picklable and must not import tkinter: on Windows the
child is spawned, not forked, and re-imports this module from scratch.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from pathlib import Path

from . import core


@dataclass(frozen=True)
class BuildSettings:
    """Everything one Generate needs, taken off the widgets in one go.

    Frozen, and made of plain values only: it crosses a process boundary, and a
    later widget edit must not change a build already in flight.
    """

    step_dirs: tuple[str, ...]
    json_file: str
    output_dir: str
    z_datum: str
    board_color: tuple[int, int, int] | None
    rim_color: tuple[int, int, int] | None
    silk_top: bool
    silk_bottom: bool
    silk_color: tuple[int, int, int] | None
    silk_flat: bool
    silk_flat_height: float
    silk_layers_off: frozenset[str]
    minimize: bool
    board_mode: str
    layer_colors: dict
    ignore_soldermask: bool
    fold_bends: bool
    fold_anchor: tuple[float, float] | str | None
    fold_neutral: float
    fold_slice_angle: float
    brd_name: str | None
    dated_name: bool


def run_jobs(settings: BuildSettings, channel) -> None:
    """Build every JSON the settings point at, reporting through *channel*.

    The message shapes are the ones the window already understands:
    ("log", text), ("progress", (value, total, label)), ("done", summary) and
    ("error", text).
    """
    try:
        _run(settings, channel)
    except core.StepBuilderError as exc:
        channel.put(("error", str(exc)))
    except Exception:
        channel.put(("error", traceback.format_exc()))


def _run(settings: BuildSettings, channel) -> None:
    field = Path(settings.json_file)
    jobs, ignored = core.resolve_json_jobs(field)

    for j in ignored:
        channel.put(("log", f"Ignoring non-Simple-3D json: {j.name}"))

    if not jobs:
        # Explain precisely what was found, so a wrong path, an empty folder and
        # a foreign json are distinguishable at a glance.
        if field.is_dir():
            entries = sorted(p.name for p in field.iterdir())
            detail = (f"Folder {field} contains: "
                      + (", ".join(entries) if entries else "(empty)"))
        elif field.is_file():
            detail = (f"{field} is not a Simple 3D intermediate (missing the "
                      '"format": "simple3d" marker). Pick a JSON produced by '
                      "File -> Export -> Simple 3D.")
        else:
            detail = f"Path does not exist: {field}"
        raise core.StepBuilderError(f"No JSON file to build.\n{detail}")

    total_placed = 0
    outputs: list[str] = []
    warnings: list[str] = []
    failures: list[str] = []

    for number, jf in enumerate(jobs, start=1):
        # Base name for the output file. With SEVERAL variants the stem of each
        # json (design_variant) must win, or every variant would get the same
        # name and only differ by collision underscores. The launcher's brd_name
        # (original-case board name) applies only when there is a single json.
        base = jf.stem if len(jobs) > 1 else (settings.brd_name or jf.stem)
        prefix = f"{jf.stem}: " if len(jobs) > 1 else ""

        def progress(value: int, total: int, label: str = "",
                     _prefix=prefix, _n=number) -> None:
            # Several jobs share one bar: each takes its own slice of it.
            span = 100.0 / len(jobs)
            channel.put(("progress",
                         (span * (_n - 1) + span * value / max(total, 1), 100.0,
                          _prefix + label)))

        # One variant must not take the rest of the batch down with it: a gap in
        # board 2's outline should still leave boards 3..n built. This mirrors
        # the CLI, which counts failures and carries on.
        try:
            output_name = (core.dated_output_name(base, settings.output_dir)
                           if settings.dated_name else None)
            result = core.generate(
                list(settings.step_dirs),
                jf,
                settings.output_dir,
                output_name=output_name,
                z_datum=settings.z_datum,
                board_color=settings.board_color,
                rim_color=settings.rim_color,
                silk_top=settings.silk_top,
                silk_bottom=settings.silk_bottom,
                silk_color=settings.silk_color,
                silk_flat=settings.silk_flat,
                silk_flat_height=settings.silk_flat_height,
                silk_layers_off=settings.silk_layers_off,
                minimize_size=settings.minimize,
                board_mode=settings.board_mode,
                layer_colors=settings.layer_colors,
                ignore_soldermask=settings.ignore_soldermask,
                fold_bends=settings.fold_bends,
                fold_anchor=settings.fold_anchor,
                fold_neutral=settings.fold_neutral,
                fold_slice_angle=settings.fold_slice_angle,
                log=lambda m: channel.put(("log", m)),
                progress=progress,
            )
        except core.StepBuilderError as exc:
            failures.append(f"{jf.name}: {exc}")
            channel.put(("log", f"error ({jf.name}): {exc}"))
            continue
        except Exception:
            # Unexpected (a malformed JSON key, an OCCT failure): keep the
            # traceback so the bug is reportable, but still build the rest.
            failures.append(f"{jf.name}: unexpected error (see log)")
            channel.put(("log", f"error ({jf.name}):\n{traceback.format_exc()}"))
            continue

        total_placed += result.components_placed
        outputs.append(result.output.name)
        if result.silkscreen_solids:
            channel.put(("log", f"{result.output.name}: silkscreen "
                                f"{result.silkscreen_solids} solid(s)"))
        if result.missing_step_files:
            warnings.append(f"{result.output.name}: "
                            f"{len(result.missing_step_files)} STEP missing")
        if result.embedded_not_on_disk:
            warnings.append(
                f"{result.output.name}: {len(result.embedded_not_on_disk)} of "
                f"those are in the board but not on disk (see the log)")

    for w in warnings:
        channel.put(("log", "warning: " + w))

    # Nothing built at all -> report as a failure, not a green "Done: 0".
    if failures and not outputs:
        channel.put(("error", f"All {len(failures)} job(s) failed:\n"
                              + "\n".join(failures)))
        return

    summary = f"Done: {len(outputs)} file(s), {total_placed} component(s) placed"
    if failures:
        summary += f", {len(failures)} failed"
    channel.put(("done", summary))
