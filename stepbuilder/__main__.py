"""Entry point.

    python -m stepbuilder                          -> opens the GUI
    python -m stepbuilder STEP_DIR JSON OUT_DIR    -> headless, for shell() from Allegro

The headless form accepts a single JSON or, with --batch, a directory of them
(one per variant), building a STEP for each.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import core
from .colors import DEFAULT_SILK, SILK_ORDER, resolve_board_color, resolve_silk_color


def _gui_prefill(argv: list[str]) -> int:
    """Open the GUI with paths and options prefilled from the Allegro launcher.

    Recognised flags: --step-dir, --json-dir (a folder of variant JSONs),
    --output-dir, --brd-name, --dated-name, --color.
    """
    p = argparse.ArgumentParser(prog="stepbuilder --gui", add_help=False)
    p.add_argument("--gui", action="store_true")
    p.add_argument("--step-dir", default="")
    p.add_argument("--json-dir", default="")
    p.add_argument("--json-file", default="")
    p.add_argument("--output-dir", default="")
    p.add_argument("--brd-name", default="")
    p.add_argument("--dated-name", action="store_true")
    p.add_argument("--color", default="")
    p.add_argument("--silk-color", default="")
    p.add_argument("--no-silkscreen", action="store_true")
    p.add_argument("--flat-silkscreen", action="store_true")
    p.add_argument("--no-silk-top", action="store_true")
    p.add_argument("--no-silk-bottom", action="store_true")
    p.add_argument("--config", default="")
    args, _ = p.parse_known_args(argv)

    from .gui import StepBuilderApp

    try:
        app = StepBuilderApp(Path(args.config) if args.config else None)
        if args.step_dir:
            app.step_dir.set(args.step_dir)
        if args.color:
            app.theme.set(args.color)
            app._update_swatch()
        if args.silk_color:
            app.silk_color.set(args.silk_color)
        # Launch flags override what the config remembered, for this run only.
        if args.no_silkscreen or args.no_silk_top:
            app.silk_top.set(False)
        if args.no_silkscreen or args.no_silk_bottom:
            app.silk_bottom.set(False)
        if args.flat_silkscreen:
            app.silk_flat.set(True)
        app.prefill_jobs(
            json_dir=args.json_dir or None,
            json_file=args.json_file or None,
            output_dir=args.output_dir or None,
            brd_name=args.brd_name or None,
            dated_name=args.dated_name,
        )
        app.mainloop()
    except Exception:
        # Under pythonw there is no console, so a startup crash would vanish.
        # Write a log next to the package and try to show a dialog.
        import traceback
        from pathlib import Path

        tb = traceback.format_exc()
        try:
            log = Path(__file__).resolve().parent.parent / "simple3d_crash.log"
            log.write_text(tb, encoding="utf-8")
        except OSError:
            log = None
        try:
            import tkinter.messagebox as mb

            mb.showerror("Simple 3D failed to start",
                         tb + (f"\n\nSaved to {log}" if log else ""))
        except Exception:
            pass
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    if not argv:
        from .gui import main as gui_main

        gui_main()
        return 0

    # --gui: open the window with paths prefilled (used by the Allegro launcher).
    if "--gui" in argv:
        return _gui_prefill(argv)

    parser = argparse.ArgumentParser(
        prog="stepbuilder",
        description="Build a STEP assembly from an Allegro intermediate JSON file. "
        "Run without arguments to open the GUI.",
    )
    parser.add_argument("step_dir", help="directory containing the footprint STEP files")
    parser.add_argument("json_file", help="intermediate .json (or a directory, with --batch)")
    parser.add_argument("output_dir", help="directory to write the .step assembly into")
    parser.add_argument(
        "--batch",
        action="store_true",
        help="treat json_file as a directory and build every *.json in it (variants)",
    )
    parser.add_argument(
        "--brd-name",
        default=None,
        help="base board name for the output file (default: the JSON's own name)",
    )
    parser.add_argument(
        "--dated-name",
        action="store_true",
        help="name output <brd>_simple_DD_MM_YYYY.step, trailing _ on collision",
    )
    parser.add_argument(
        "--z-datum", choices=["top", "bottom"], default="top",
        help="which board face is z=0 (default: top)",
    )
    parser.add_argument(
        "--color", default=None,
        help="board colour: a theme name (e.g. Dark_green), 'r,g,b', or '#rrggbb'",
    )
    parser.add_argument(
        "--rim-color", default=None,
        help="separate colour for the board rim/underside (same formats as --color)",
    )
    parser.add_argument(
        "--no-silkscreen", action="store_true",
        help="do not build the printed legend even if the JSON carries one",
    )
    parser.add_argument(
        "--no-silk-top", action="store_true",
        help="skip the top-side legend only",
    )
    parser.add_argument(
        "--no-silk-bottom", action="store_true",
        help="skip the bottom-side legend only",
    )
    parser.add_argument(
        "--flat-silkscreen", action="store_true",
        help="draw the legend as surfaces, not solids: about a quarter of the "
             "file size, but the ink then has no thickness",
    )
    parser.add_argument(
        "--silk-color", default=DEFAULT_SILK,
        help=f"silkscreen colour: {' or '.join(SILK_ORDER)} (default: {DEFAULT_SILK})",
    )
    # MFRPN DISABLED (property attachment unreliable); kept for future:
    # parser.add_argument(
    #     "--mfr-pn-in-name", action="store_true",
    #     help="append MFRPN to each instance name",
    # )
    parser.add_argument(
        "--no-minimize", action="store_true",
        help="do not shrink the file (keep surface curves)",
    )
    parser.add_argument(
        "--legacy-color", action="store_true",
        help="treat colours as linear RGB, reproducing the original C++ behaviour",
    )
    parser.add_argument("--quiet", action="store_true", help="suppress progress output")
    args = parser.parse_args(argv)

    def log(message: str) -> None:
        if not args.quiet:
            print(message, flush=True)

    board_color = resolve_board_color(args.color) if args.color else None
    rim_color = resolve_board_color(args.rim_color) if args.rim_color else None
    silk_color = resolve_silk_color(args.silk_color) if args.silk_color else None

    json_path = Path(args.json_file)
    output_dir = Path(args.output_dir)

    if args.batch:
        jsons, ignored = core.resolve_json_jobs(json_path)
        for j in ignored:
            log(f"ignoring non-Simple-3D json: {j.name}")
        if not jsons:
            print(f"error: no Simple 3D *.json files in {json_path}", file=sys.stderr)
            return 1
    else:
        jsons = [json_path]

    failures = 0
    for jf in jsons:
        try:
            # With several variants, each json's stem (design_variant) must
            # name the output, or all variants would collide into one base and
            # differ only by underscores. --brd-name applies to a single json.
            if len(jsons) > 1:
                base = jf.stem
            else:
                base = args.brd_name or jf.stem
            output_name = (core.dated_output_name(base, output_dir)
                           if args.dated_name else None)
            result = core.generate(
                args.step_dir,
                jf,
                output_dir,
                output_name=output_name,
                z_datum=args.z_datum,
                board_color=board_color,
                rim_color=rim_color,
                silk_top=not (args.no_silkscreen or args.no_silk_top),
                silk_bottom=not (args.no_silkscreen or args.no_silk_bottom),
                silk_color=silk_color,
                silk_flat=args.flat_silkscreen,
                # MFRPN DISABLED (kept for future): name_instances_with_mfr_pn=args.mfr_pn_in_name,
                minimize_size=not args.no_minimize,
                srgb_color=not args.legacy_color,
                log=log,
            )
        except core.StepBuilderError as exc:
            print(f"error ({jf.name}): {exc}", file=sys.stderr)
            failures += 1
            continue

        if result.missing_step_files:
            log(f"warning: {len(result.missing_step_files)} STEP file(s) not found")
        if result.silkscreen_solids:
            log(f"silkscreen: {result.silkscreen_solids} solid(s)")
        # MFRPN DISABLED (kept for future):
        # if result.missing_mfr_pn:
        #     log(f"warning: {len(result.missing_mfr_pn)} component(s) without MFRPN")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
