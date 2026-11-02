"""What a bend IS: the undocumented property, one `Bend`, and the list a
format_version 7 intermediate carries.

The parameters (angle, inner side, order, radius) come from
`IDX_BEND_TYPE_INFO`, which appears in neither the SKILL reference nor the
rigid-flex documentation - see parse_bend_info for what is assumed about it.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .constants import EPS, MIN_ANGLE, LogFn, _noop_log


# --------------------------------------------------------------------------- #
# IDX_BEND_TYPE_INFO
# --------------------------------------------------------------------------- #

# Allegro writes lengths with their unit spelled out:
#     INNER_RADIUS=2.5000 MILLIMETERS
# The design is required to be in mm anyway (the intermediate is unitless), but
# the property carries its own unit and a board set up in mils would otherwise
# read 2.5 mm where it means 2.5 mils.
_UNITS = {
    "MILLIMETERS": 1.0, "MILLIMETER": 1.0, "MM": 1.0,
    "CENTIMETERS": 10.0, "CENTIMETER": 10.0, "CM": 10.0,
    "MICRONS": 0.001, "MICRON": 0.001, "UM": 0.001,
    "INCHES": 25.4, "INCH": 25.4, "IN": 25.4,
    "MILS": 0.0254, "MIL": 0.0254,
}

_NUMBER = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def parse_bend_info(raw: str) -> dict:
    """`"TYPE=CircularBend, INNER_ANGLE=28.26, ..."` -> `{"TYPE": "CircularBend", ...}`.

    Deliberately forgiving. The property is undocumented - it appears in neither
    the SKILL API index nor the DB attribute reference - so its full field list
    is whatever a given Allegro version chooses to write. Unknown keys are kept
    as strings rather than dropped, and a field that cannot be read leaves the
    bend to fall back on the value the dedicated API gave.
    """
    out: dict = {}
    if not isinstance(raw, str):
        return out
    for part in raw.split(","):
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        key = key.strip().upper()
        value = value.strip()
        if key:
            out[key] = value
    return out


def info_length(value: str | None) -> float | None:
    """`"2.5000 MILLIMETERS"` -> 2.5. None when there is no number in it."""
    if not isinstance(value, str):
        return None
    match = _NUMBER.search(value)
    if not match:
        return None
    number = float(match.group(0))
    for word in value[match.end():].strip().upper().split():
        scale = _UNITS.get(word.strip(".,"))
        if scale is not None:
            return number * scale
    return number


def info_number(value: str | None) -> float | None:
    """The first number in a field, unit or not."""
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    match = _NUMBER.search(value)
    return float(match.group(0)) if match else None


# --------------------------------------------------------------------------- #
# one bend
# --------------------------------------------------------------------------- #

@dataclass
class Bend:
    """One bend, in flat board coordinates."""

    name: str
    start: tuple[float, float]
    end: tuple[float, float]
    angle: float                      # degrees of arc, finished
    radius: float                     # INNER radius, mm
    inner_side: str = "top"           # which face is on the inside of the curve
    order: int | None = None          # Allegro's bending sequence number
    width: float | None = None        # bend area, measured across the line
    info: str = ""                    # the raw property, kept for diagnosis
    # Why inner_side is the default and not what the bend said: no INNER_SIDE
    # at all, or a value that is neither TOP nor BOTTOM. None when it was read.
    # bends_from_json says so; until round 131 such a bend folded the default
    # way with nothing in the log (review 23.10.2026, R5-8).
    side_unread: str | None = None

    @property
    def midpoint(self) -> tuple[float, float]:
        return ((self.start[0] + self.end[0]) / 2.0,
                (self.start[1] + self.end[1]) / 2.0)

    @property
    def length(self) -> float:
        return math.hypot(self.end[0] - self.start[0], self.end[1] - self.start[1])

    def normal(self) -> tuple[float, float]:
        """A unit vector across the bend line. Sense is arbitrary here."""
        dx, dy = self.end[0] - self.start[0], self.end[1] - self.start[1]
        n = math.hypot(dx, dy)
        if n <= EPS:
            return (1.0, 0.0)
        return (dy / n, -dx / n)


# The two values INNER_SIDE takes: every bend of the boards on hand says one
# or the other (19 bends in the golden corpus, 8 BOTTOM and 11 TOP).
_SIDES = {"TOP": "top", "BOTTOM": "bottom"}


def bend_from_dict(entry: dict) -> Bend | None:
    """One JSON bend entry -> Bend, or None when it cannot be read.

    The exporter writes a bend's name, line, inner radius and width, and the
    raw property string as `info` (s3d_bends.il); the angle, the inner side
    and the order are read out of that string here. A field the entry
    carries itself wins over the string - an intermediate written by hand or
    by another tool - so the string is read only for what is missing. (Until
    round 131 this said the exporter wrote the parsed fields too; it never
    has - review 23.10.2026, R5-9.)
    """
    if not isinstance(entry, dict):
        return None
    line = entry.get("line") or {}
    start, end = line.get("start"), line.get("end")
    if not (isinstance(start, (list, tuple)) and isinstance(end, (list, tuple))):
        return None
    if len(start) < 2 or len(end) < 2:
        return None

    info = entry.get("info") if isinstance(entry.get("info"), str) else ""
    fields = parse_bend_info(info)

    angle = entry.get("angle")
    if angle is None:
        angle = info_number(fields.get("INNER_ANGLE") or fields.get("ANGLE"))
    radius = entry.get("inner_radius")
    if radius is None:
        radius = info_length(fields.get("INNER_RADIUS") or fields.get("RADIUS"))
    side = entry.get("inner_side") or fields.get("INNER_SIDE")
    inner_side = _SIDES.get(str(side).strip().upper()) if side is not None else None
    order = entry.get("order")
    if order is None:
        order = info_number(fields.get("ORDER"))

    if angle is None or radius is None:
        return None

    return Bend(
        name=str(entry.get("name") or "bend"),
        start=(float(start[0]), float(start[1])),
        end=(float(end[0]), float(end[1])),
        angle=abs(float(angle)),
        radius=abs(float(radius)),
        inner_side=inner_side or "top",
        order=int(order) if order is not None else None,
        width=float(entry["width"]) if isinstance(entry.get("width"), (int, float)) else None,
        info=info,
        side_unread=None if inner_side else (
            "no INNER_SIDE" if side is None
            else f"INNER_SIDE={str(side).strip()!r}, neither TOP nor BOTTOM"),
    )


def bends_from_json(data: dict, log: LogFn = _noop_log) -> list[Bend]:
    """The `bends` array of a format_version 7 intermediate."""
    raw = data.get("bends")
    if not isinstance(raw, list) or not raw:
        return []
    bends = []
    for entry in raw:
        bend = bend_from_dict(entry)
        if bend is None:
            log(f"warning: a bend entry could not be read and is left flat "
                f"({entry.get('name') if isinstance(entry, dict) else entry!r})")
            continue
        if bend.angle < MIN_ANGLE:
            log(f"Bend {bend.name}: {bend.angle:.2f} deg, left flat")
            continue
        if bend.length <= EPS:
            log(f"warning: bend {bend.name} has a zero-length bend line, skipped")
            continue
        if bend.side_unread:
            # The property is undocumented (see parse_bend_info), so another
            # Allegro version may name the field otherwise; the bend is still
            # folded, the default way, and the log says it was not read.
            log(f"warning: bend {bend.name}: {bend.side_unread} in its "
                f"parameters, so it is folded with its top face on the inside "
                f"of the curve - the default, which may be the wrong way; "
                f"check the bend's inner side in Allegro (\"{bend.info}\")")
        bends.append(bend)
    return bends
