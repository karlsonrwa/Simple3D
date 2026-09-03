"""The stackup arithmetic: pure functions over the layer dicts the
intermediate carries, no OpenCASCADE in sight.

A layer is `{name, type, thickness, z_top, z_bottom, negative, function,
shapes}`; a stackup is `{thickness, layers, silkscreen}`; a zone names its
stackup and its contour. Everything here recomputes z from thickness
(`restack`), takes a layer kind out (`drop_soldermask`), puts several
stackups on one datum by the copper they share (`align_stackups`), or turns
the stackups and zones into the faces the board is built between
(`stackup_levels`, and `zone_levels` for a format_version 5 file that has
no layers). The "why" of each is in its docstring; the measurements behind
them are in PROJECT_NOTES rounds 26-34 and 62.
"""

from __future__ import annotations

from .errors import StepBuilderError
from .reporting import LogFn, _noop_log


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


def _is_conductor(layer: dict) -> bool:
    return str(layer.get("type") or "").upper() in ("CONDUCTOR", "PLANE")


def board_stackup(stackups: dict) -> tuple[str, dict] | None:
    """The stackup that is THE board: the one called Primary (any case), else
    the first one the file lists. None when there are none."""
    for name, stackup in stackups.items():
        if str(name).upper() == "PRIMARY" and isinstance(stackup, dict):
            return str(name), stackup
    for name, stackup in stackups.items():
        if isinstance(stackup, dict):
            return str(name), stackup
    return None


def thickness_parts(stackup: dict) -> dict | None:
    """pcb.thickness measured from one stackup's layers, by position: what is
    above the first conductor, the conductor span, what is below - the rule
    the exporter's s3dBoardThickness applies (round 79, E2). None when the
    stackup has no conductor."""
    layers = [lay for lay in (stackup.get("layers") or []) if isinstance(lay, dict)]
    idx = [i for i, lay in enumerate(layers) if _is_conductor(lay)]
    if not idx:
        return None
    thick = lambda part: sum(float(lay.get("thickness") or 0.0) for lay in part)
    return {"soldermask_top": thick(layers[:idx[0]]),
            "board": thick(layers[idx[0]:idx[-1] + 1]),
            "soldermask_bottom": thick(layers[idx[-1] + 1:])}


def align_stackups(stackups: dict, log: LogFn = _noop_log) -> dict:
    """Put every stackup on ONE z datum, by the conductor layers they share.

    Each stackup arrives measured from its own **first conductor**, which the
    exporter puts at z = 0. That is only a common datum when every stackup's
    first conductor is the same physical layer. On a board where the flex is an
    INNER pair it is not: Cadence's demo board declares INNER1 at z = 0 in the
    FLEXI1 stackup and at -0.5208 in PRIMARY, the same copper 0.52 mm apart, so
    the flex tail left the rigid board near its top face instead of out of its
    middle - and every bend axis, every zone height and every component on a
    tail went with it.

    A rigid-flex board is one laminate: a layer that appears in two stackups is
    the same sheet running through both. So the stackup with the most conductors
    - the rigid stack - is the reference, and every other is slid until the
    conductors it shares with the reference line up. A stackup that shares no
    named conductor with it is left where it is and said so; there is nothing to
    align it by, and guessing would be worse than the exporter's own answer.

    Boards where the datum already agrees measure an offset of 0 and are
    untouched, which is every single-stackup board and every rigid-flex board
    whose flex carries the outer copper.
    """
    usable = {name: (stackup.get("layers") or [])
              for name, stackup in stackups.items()}
    usable = {n: lays for n, lays in usable.items() if lays}
    if len(usable) < 2:
        return stackups

    def conductors(layers) -> dict:
        return {str(lay.get("name")): float(lay["z_top"])
                for lay in layers if _is_conductor(lay) and lay.get("name")}

    reference = max(usable, key=lambda n: (len(conductors(usable[n])),
                                           len(usable[n]), n))
    ref = conductors(usable[reference])

    out, moved = {}, []
    for name, stackup in stackups.items():
        layers = stackup.get("layers") or []
        mine = conductors(layers)
        shared = sorted(set(ref) & set(mine))
        if name == reference or not layers:
            out[name] = stackup
            continue
        if not shared:
            out[name] = stackup
            log(f"warning: stackup {name!r} shares no named conductor with "
                f"{reference!r}, so there is nothing to line the two up by; "
                f"left at the height the exporter gave it")
            continue

        offsets = [ref[n] - mine[n] for n in shared]
        offset = max(set(round(o, 9) for o in offsets),
                     key=lambda o: sum(1 for x in offsets if round(x, 9) == o))
        spread = max(offsets) - min(offsets)
        if spread > 1.0e-6:
            log(f"warning: stackup {name!r} does not line up with "
                f"{reference!r} by a single shift - its shared conductors "
                f"disagree by {spread:.4f} mm. Using {offset:.4f} mm, which "
                f"most of them agree on.")
        if abs(offset) > 1.0e-9:
            moved.append(f"{name} by {offset:+.4f} mm on {', '.join(shared)}")
        out[name] = {**stackup,
                     "layers": [{**lay,
                                 "z_top": float(lay["z_top"]) + offset,
                                 "z_bottom": float(lay["z_bottom"]) + offset}
                                for lay in layers]}

    if moved:
        log(f"Stackups lined up on {reference!r} by their shared conductors: "
            + "; ".join(moved))
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
