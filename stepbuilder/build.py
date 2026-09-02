"""What one build is asked for, in one place.

`generate` takes nineteen options besides its three paths; until round 73
(plan A8) that argument list existed three times - in generate's signature,
in worker._run's call and in __main__'s - and a new option meant editing all
three. `BuildOptions` is the one list: the worker builds one from the
window's frozen BuildSettings, the CLI builds one from its argparse
namespace, and generate accepts one (or the old keywords, which build one).

The meaning of each option, as generate documented it:

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

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .legend import DEFAULT_FLAT_HEIGHT

if TYPE_CHECKING:
    from .worker import BuildSettings


@dataclass(frozen=True)
class BuildOptions:
    """The options of one build. Defaults are generate's; see the module
    docstring for what each means."""

    output_name: str | None = None
    z_datum: str = "top"
    board_color: tuple[int, int, int] | None = None
    rim_color: tuple[int, int, int] | None = None
    silk_top: bool = True
    silk_bottom: bool = True
    silk_color: tuple[int, int, int] | None = None
    silk_flat: bool = False
    silk_flat_height: float = DEFAULT_FLAT_HEIGHT
    silk_layers_off: set[str] | frozenset[str] | None = None
    # MFRPN DISABLED (kept for future): name_instances_with_mfr_pn: bool = False
    minimize_size: bool = True
    srgb_color: bool = True
    board_mode: str = "solid"
    layer_colors: dict | None = None
    ignore_soldermask: bool = False
    fold_bends: bool = True
    fold_anchor: tuple[float, float] | str | None = None
    fold_neutral: float | None = None
    fold_slice_angle: float | None = None

    @classmethod
    def from_settings(cls, settings: BuildSettings, output_name: str | None) -> BuildOptions:
        """From the window's snapshot (worker.BuildSettings), which carries the
        same values under the names the window uses; `minimize` is
        `minimize_size` here, and the CLI-only `srgb_color` stays at its default."""
        return cls(
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
        )

    @classmethod
    def from_args(cls, args, *, output_name: str | None, board_color, rim_color,
                  silk_color, fold_anchor) -> BuildOptions:
        """From the headless CLI's argparse namespace. The colours and the anchor
        are passed in resolved: the CLI parses them and reports a bad one before
        anything is built."""
        return cls(
            output_name=output_name,
            z_datum=args.z_datum,
            board_color=board_color,
            rim_color=rim_color,
            silk_top=not (args.no_silkscreen or args.no_silk_top),
            silk_bottom=not (args.no_silkscreen or args.no_silk_bottom),
            silk_color=silk_color,
            silk_flat=args.flat_silkscreen,
            silk_flat_height=args.silk_flat_height,
            silk_layers_off=set(args.silk_layer_off),
            # MFRPN DISABLED (kept for future): name_instances_with_mfr_pn=args.mfr_pn_in_name,
            minimize_size=not args.no_minimize,
            srgb_color=not args.legacy_color,
            board_mode=args.board_mode,
            ignore_soldermask=args.ignore_soldermask,
            fold_bends=not args.no_fold,
            fold_anchor=fold_anchor,
            fold_neutral=args.fold_neutral,
            fold_slice_angle=args.fold_slice_angle,
        )
