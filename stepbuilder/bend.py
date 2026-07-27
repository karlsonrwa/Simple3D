"""Folding a flex or rigid-flex board along its bend areas.

The exporter writes the board flat, which is how Allegro holds it: a bend is
not geometry there, it is a line plus a property saying what will happen to
the material around it. This module turns that description into a fold.

What a bend is, from the rigid-flex documentation and the probe data:

- A **bend line** on RIGID FLEX/BEND_LINE. The docs are explicit that it "represents
  the midpoint of the bend and the extents of the bend area along the line's
  axis" - so the strip that curls is centred on the line, half of it either side,
  and not, as one might assume, starting at it.
- A **bend area** on RIGID FLEX/BEND_AREA, trimmed to the design outline, and
  drawn at the INNER radius - measured on a real board, 1.2337 mm across for
  28.26 deg and R = 2.5, which is 28.26 deg x 2.5 and carries no thickness term.
  It is the region to keep vias and packages out of, not a bend allowance, so
  the material the fold consumes is computed from the neutral axis and the drawn
  area is only a check.
- The parameters (angle, inner side, order, radius) in an undocumented property,
  IDX_BEND_TYPE_INFO, plus `axlGetBendInnerRadius` for the radius alone.

**How the fold is built.** A bend divides the board into a part that stays put
and a part that moves. The moving part is carried by one rigid transform; the
strip between them is cut into slices, each of which is also rigid but hinged a
little further round the arc, so the curve is faceted rather than exact. This is
the standard sheet-metal approximation and it is what makes the whole thing
possible in OpenCASCADE at all: OCC can transform a solid, and it can cut one,
but it has no operation that deforms a solid along a curve.

Two details make the faceting hold together:

- **Slice j is hinged at its own leading edge and rotated by the angle the arc
  has reached there.** That places every slice's leading edge exactly on the
  true arc, so the error is one-sided and bounded by the sagitta of one slice
  (7.5 deg by default, about 0.2% of the radius).
- **Slices overlap by a hair before they are transformed.** Rotating a straight
  slice about its leading edge leaves a wedge-shaped gap on the outside of the
  bend and an overlap on the inside; without the deliberate overlap, consecutive
  slices would touch along a line and the fuse would not produce a solid.

The alternative - deriving the whole bend as a revolution - only works when the
plan-view outline of the bend area is a rectangle, which a flex tail's is not
once it has been trimmed to the design outline.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Callable

from OCP.BRep import BRep_Builder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Fuse
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.Bnd import Bnd_Box
from OCP.TopAbs import TopAbs_ShapeEnum
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape
from OCP.TopTools import TopTools_ListOfShape
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

LogFn = Callable[[str], None]


def _noop_log(message: str) -> None:
    pass


# A bend shallower than this is not worth cutting the board for.
MIN_ANGLE = 0.5

# Degrees of arc per rigid slice, for the bends that cannot be built exactly.
# 7.5 puts twelve facets in a 90 deg bend and the facet chords 0.2% of the
# radius inside the true surface.
DEFAULT_SLICE_ANGLE = 7.5

# The point of the board that stays in the XY plane. The ORIGIN by convention:
# Allegro's own "Anchor 3D View" never writes its point to the database (24.1),
# so the design cannot tell us, and a fixed, documented convention beats a
# heuristic that quietly picks a different piece when a board changes shape.
DEFAULT_ANCHOR = (0.0, 0.0)

# Where the neutral axis sits in the stack, as a fraction of the thickness from
# the inner surface. 0.5 is the middle, which is right for a symmetric flex.
DEFAULT_NEUTRAL_FACTOR = 0.5

# Numerical slack for "is this point on that side of the line".
EPS = 1.0e-7


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


def bend_from_dict(entry: dict) -> Bend | None:
    """One JSON bend entry -> Bend, or None when it cannot be read.

    The exporter emits the parsed fields AND the raw property string. The parsed
    fields win; the raw string is re-parsed only for what is missing, so a newer
    Allegro that adds a field can be picked up here without a re-export.
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
    side = entry.get("inner_side") or fields.get("INNER_SIDE") or "TOP"
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
        inner_side="bottom" if str(side).strip().upper().startswith("B") else "top",
        order=int(order) if order is not None else None,
        width=float(entry["width"]) if isinstance(entry.get("width"), (int, float)) else None,
        info=info,
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
        bends.append(bend)
    return bends


# --------------------------------------------------------------------------- #
# flat polygon helpers - used only to decide which side of the board is held
# --------------------------------------------------------------------------- #

def contour_points(contour, arc_steps: int = 8) -> list[tuple[float, float]]:
    """A JSON contour as a plain polygon. Arcs are sampled, not preserved.

    Only ever used for area and containment tests, where a chord approximation
    is not merely acceptable but the point: this decides which side of a bend
    holds still, and that answer must not depend on a curve's exact sampling.
    """
    points: list[tuple[float, float]] = []
    for prim in contour or []:
        kind = prim.get("type", "segment")
        if kind == "segment":
            points.append((float(prim["start"][0]), float(prim["start"][1])))
            points.append((float(prim["end"][0]), float(prim["end"][1])))
        elif kind in ("arc", "circle"):
            cx, cy = (float(prim["center"][0]), float(prim["center"][1])) \
                if kind == "arc" else (float(prim["x"]), float(prim["y"]))
            r = float(prim["radius"])
            if kind == "circle":
                a0, a1 = 0.0, 360.0
            else:
                a0, a1 = float(prim["alpha"]), float(prim["beta"])
                if prim.get("ccw", True):
                    while a1 < a0:
                        a1 += 360.0
                else:
                    while a1 > a0:
                        a1 -= 360.0
            for i in range(arc_steps + 1):
                a = math.radians(a0 + (a1 - a0) * i / arc_steps)
                points.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    # drop consecutive duplicates, which every shared vertex produces
    out: list[tuple[float, float]] = []
    for p in points:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-9:
            out.append(p)
    return out


def polygon_area(points: list[tuple[float, float]]) -> float:
    """Unsigned area by the shoelace formula."""
    if len(points) < 3:
        return 0.0
    total = 0.0
    for i in range(len(points)):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % len(points)]
        total += x0 * y1 - x1 * y0
    return abs(total) / 2.0


def clip_halfplane(points: list[tuple[float, float]],
                   nx: float, ny: float, d: float) -> list[tuple[float, float]]:
    """Sutherland-Hodgman clip to `n . p <= d`.

    Correct for a non-convex subject polygon as long as the clip region is a
    half plane, which it always is here: the pieces it can leave joined along
    the clip line have zero area and do not disturb the area comparison this
    is used for.
    """
    if not points:
        return []
    out: list[tuple[float, float]] = []
    n = len(points)
    for i in range(n):
        cur = points[i]
        nxt = points[(i + 1) % n]
        dc = nx * cur[0] + ny * cur[1] - d
        dn = nx * nxt[0] + ny * nxt[1] - d
        if dc <= 0:
            out.append(cur)
        if (dc < 0 < dn) or (dn < 0 < dc):
            t = dc / (dc - dn)
            out.append((cur[0] + t * (nxt[0] - cur[0]),
                        cur[1] + t * (nxt[1] - cur[1])))
    return out


def point_in_polygon(point: tuple[float, float],
                     polygon: list[tuple[float, float]]) -> bool:
    """Ray casting. Used to find which zone a bend line sits in."""
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        x0, y0 = polygon[i]
        x1, y1 = polygon[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            xc = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if x < xc:
                inside = not inside
    return inside


# --------------------------------------------------------------------------- #
# the plan
# --------------------------------------------------------------------------- #

@dataclass
class _Region:
    """A piece of the flat board and the rigid transform that carries it.

    `bounds` are half-plane constraints in flat XY, each (nx, ny, lo, hi)
    meaning `lo <= n . p <= hi`, with +/-inf for an open side. They are applied
    to the FLAT shape, before any transform: that is what makes a chain of bends
    composable, because every cut is made in the one frame where the board is
    still a plane.
    """

    label: str
    bounds: list[tuple[float, float, float, float]]
    trsf: gp_Trsf
    moved: bool = True
    # "panel" - a flat piece carried by one rigid transform; "slice" - one facet
    # of a bend, used only when the exact construction below does not apply.
    kind: str = "panel"


@dataclass
class _Strip:
    """The part of the board that curls, and everything needed to curl it.

    Kept apart from the panels because it is built in one of two ways and the
    choice is made per shape: exactly, as a revolved section, or as the rigid
    slices in `facets`. See FoldPlan.apply.
    """

    bend: Bend
    bounds: list[tuple[float, float, float, float]]
    normal: tuple[float, float]
    lo: float
    hi: float
    axis_z: float
    turn: float                       # signed, radians: the finished angle
    carried: gp_Trsf                  # what the bends before this one do to it
    facets: list[_Region] = field(default_factory=list)

    def axis(self) -> gp_Ax1:
        """The cylinder the board wraps onto, in the flat frame."""
        nx, ny = self.normal
        return gp_Ax1(gp_Pnt(nx * self.lo, ny * self.lo, self.axis_z),
                      gp_Dir(ny, -nx, 0.0))


@dataclass
class FoldPlan:
    """Everything needed to fold one board, and nothing about how it was built."""

    regions: list[_Region] = field(default_factory=list)
    strips: list[_Strip] = field(default_factory=list)
    bends: list[Bend] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # (bend name, unit normal away from the anchor, point on the line, half width)
    chain: list[tuple[Bend, tuple[float, float], tuple[float, float], float]] = \
        field(default_factory=list)
    slice_angle: float = DEFAULT_SLICE_ANGLE
    # how each bend was actually built, the first time it was built that way
    built: dict = field(default_factory=dict)
    # and how many pieces went each way, which is what says a bend is uneven
    tally: dict = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.bends) and any(r.moved for r in self.regions)

    # -- placing a point ---------------------------------------------------- #

    def transform_at(self, x: float, y: float) -> gp_Trsf:
        """The rigid transform for anything sitting at flat (x, y).

        A component in a bend area is a design-rule violation ("Avoid placing
        vias within a bend area", and packages likewise), but if one is there it
        gets the transform of the slice it stands on rather than being dropped.
        """
        for region in self.regions:
            if all(lo - EPS <= nx * x + ny * y <= hi + EPS
                   for nx, ny, lo, hi in region.bounds):
                return region.trsf
        return gp_Trsf()

    def region_at(self, x: float, y: float) -> str:
        for region in self.regions:
            if all(lo - EPS <= nx * x + ny * y <= hi + EPS
                   for nx, ny, lo, hi in region.bounds):
                return region.label
        return "?"

    def flat_frame(self, point: gp_Pnt) -> gp_Trsf | None:
        """The transform that puts a FOLDED point back where it started.

        Used to ask a question about a face of the folded board in the frame it
        was built in - "is this wall vertical" being the one that matters, since
        after a 90 degree fold half the board's flat faces are vertical and half
        its walls are not.

        The region is found by trying each one's inverse and keeping the one
        whose flat bounds the result lands in, which is exact: the regions
        partition the flat board, and every folded point came from exactly one
        of them (bar the slice overlaps, where either answer is right to within
        one slice angle).
        """
        for region in self.regions:
            back = region.trsf.Inverted()
            flat = point.Transformed(back)
            if all(lo - EPS <= nx * flat.X() + ny * flat.Y() <= hi + EPS
                   for nx, ny, lo, hi in region.bounds):
                return back
        return None

    def in_bend_area(self, x: float, y: float) -> str | None:
        """The bend whose strip covers (x, y), if any."""
        for bend, (nx, ny), (px, py), half in self.chain:
            w = nx * (x - px) + ny * (y - py)
            if -half <= w <= half:
                return bend.name
        return None

    # -- folding geometry ---------------------------------------------------- #

    def apply(self, shape: TopoDS_Shape, fuse: bool = True,
              note: bool = True, log: LogFn = _noop_log) -> TopoDS_Shape:
        """Fold one shape: cut it region by region, bend, put back together.

        `fuse=False` returns a compound instead - right for the silkscreen,
        where the pieces were never one solid to begin with and fusing thousands
        of barely touching prisms was measured at 154% of the file size.
        """
        if shape is None or shape.IsNull() or not self:
            return shape

        box = _bbox(shape)
        if box is None:
            return shape

        pieces: list[TopoDS_Shape] = []
        for region in self.regions:
            if region.kind != "panel":
                continue
            piece = _cut_to_region(shape, region.bounds, box)
            if piece is None:
                continue
            if region.moved:
                piece = BRepBuilderAPI_Transform(piece, region.trsf, True).Shape()
            pieces.append(piece)

        for strip in self.strips:
            flat = _cut_to_region(shape, strip.bounds, box)
            if flat is None:
                continue
            bent = _revolve_strip(flat, strip)
            how, why = "exact", []
            if bent is None:
                bent = _map_strip(flat, strip, why)
                how = "wrapped"
            if bent is None:
                if note:
                    self._note_build(strip.bend.name, "faceted", log,
                                     why[0] if why else "")
                for region in strip.facets:
                    piece = _cut_to_region(shape, region.bounds, box)
                    if piece is None:
                        continue
                    pieces.append(
                        BRepBuilderAPI_Transform(piece, region.trsf, True).Shape())
            else:
                if note:
                    self._note_build(strip.bend.name, how, log)
                pieces.append(bent)

        if not pieces:
            log("warning: folding cut the shape away entirely; left flat")
            return shape
        if len(pieces) == 1:
            return pieces[0]
        if not fuse:
            builder = BRep_Builder()
            compound = TopoDS_Compound()
            builder.MakeCompound(compound)
            for piece in pieces:
                builder.Add(compound, piece)
            return compound
        return _fuse_all(pieces, log)

    def summary(self) -> list[str]:
        """One line per bend that did not build the same way throughout.

        A bend where some pieces are exact and some are faceted is the shape of
        a bend area that does not fit the board it is drawn on - which is a
        DESIGN question, not a modelling one, and the log has to say so plainly.
        Measured on a real board: a bend across a round stiffener built nine of
        its sixteen layer pieces and faceted the other seven, and Allegro's own
        3D canvas tears the same board in the same place.
        """
        lines = []
        for bend in self.bends:
            ways = {how: count for (name, how), count in self.tally.items()
                    if name == bend.name}
            if len(ways) < 2:
                continue
            spread = ", ".join(f"{count} {how}" for how, count in sorted(ways.items()))
            lines.append(
                f"  {bend.name}: built in more than one way ({spread}). A bend "
                f"that only partly builds usually means its bend area does not "
                f"match the board there - worth checking in Allegro.")
        return lines

    def _note_build(self, name: str, how: str, log: LogFn,
                    detail: str = "") -> None:
        """Say how a bend came out - once per bend per way, not once per layer.

        A board is folded layer by layer, so this runs tens of times per build;
        both outcomes are worth one line each and no more. Mixed is legitimate:
        a stiffener that stops short inside the bend area is faceted while every
        other layer of the same bend is exact.
        """
        self.tally[(name, how)] = self.tally.get((name, how), 0) + 1
        if (name, how) in self.built:
            return
        self.built[(name, how)] = True
        if how == "exact":
            log(f"  {name}: true cylindrical surfaces, revolved")
        elif how == "wrapped":
            log(f"  {name}: true cylindrical surfaces, outline wrapped onto them")
        else:
            log(f"  {name}: faceted at {self.slice_angle:g} deg per slice"
                + (f" - {detail}" if detail else ""))

    def describe(self) -> list[str]:
        lines = list(self.notes)
        for bend, _, _, half in self.chain:
            lines.append(
                f"  {bend.name}: {bend.angle:.2f} deg over {2 * half:.3f} mm, "
                f"inner radius {bend.radius:.3f} mm on the {bend.inner_side}"
                + (f", order {bend.order}" if bend.order is not None else ""))
        return lines


# --------------------------------------------------------------------------- #
# building the plan
# --------------------------------------------------------------------------- #

def plan_fold(bends: list[Bend], outline: list[tuple[float, float]],
              board_top_z: float, board_bottom_z: float,
              stack_at: Callable[[float, float], tuple[float, float]] | None = None,
              slice_angle: float = DEFAULT_SLICE_ANGLE,
              anchor: tuple[float, float] | None = DEFAULT_ANCHOR,
              neutral_factor: float = DEFAULT_NEUTRAL_FACTOR,
              log: LogFn = _noop_log) -> FoldPlan:
    """Work out what moves where.

    anchor:
        the point of the board that stays in the XY plane - **the origin by
        default**. It answers one question per bend, which side is held, and
        that is a signed distance from the bend line: the anchor does not have
        to be inside the outline, and sitting exactly on a corner of it, as the
        origin usually does, costs nothing.

        Allegro has this concept too (Setup - Anchor 3D View, and a declared
        design property ANCHOR_POINT_3D_VIEWER), but in 24.1 the point never
        reaches the database - it is not in the property before or after a save,
        not in the design's attributes, and not in any attachment. So it is a
        setting here, and the Allegro property is still read in case a later
        version starts filling it in.

        None falls back to holding the largest piece the bend lines leave.
    neutral_factor:
        where the neutral axis sits in the stack, as a fraction of thickness
        from the inner surface. 0.5 - the middle - is right for a symmetric
        flex, and it is the number that decides how much flat material a bend
        consumes: developed length = angle x (radius + k x thickness).
    stack_at:
        (x, y) -> (top z, bottom z) of the LOCAL stack. A bend's radius is
        measured from the surface of the flex, and on a rigid-flex board the
        board's own top face can be two millimetres above it - using that would
        put the cylinder axis in the wrong place and swing the tail through an
        arc of the wrong radius.
    outline:
        the flat board outline as a polygon. Only used when there is no anchor.
    """
    plan = FoldPlan(slice_angle=slice_angle)
    if not bends:
        return plan

    # -- which side is held ------------------------------------------------- #
    signs = _anchor_signs(bends, outline, anchor, plan.notes)

    # normal of each bend, pointing AWAY from the held side
    normals = []
    for bend, sign in zip(bends, signs):
        nx, ny = bend.normal()
        normals.append((sign * nx, sign * ny))

    # -- order along the chain ---------------------------------------------- #
    ref = anchor if anchor is not None else _anchor_point(bends, normals, outline)
    ordered = sorted(
        zip(bends, normals),
        key=lambda bn: abs((ref[0] - bn[0].midpoint[0]) * bn[1][0]
                           + (ref[1] - bn[0].midpoint[1]) * bn[1][1]))

    # -- geometry of each bend ---------------------------------------------- #
    chain = []
    for bend, (nx, ny) in ordered:
        px, py = bend.midpoint
        top, bottom = (stack_at(px, py) if stack_at else (board_top_z, board_bottom_z))
        thickness = abs(top - bottom)
        neutral = bend.radius + neutral_factor * thickness
        theta = math.radians(bend.angle)

        # How much flat material the arc consumes: its length along the NEUTRAL
        # axis, because that is the length a bend preserves.
        #
        # **Allegro's own bend area is drawn at the INNER radius**, which is a
        # different number and not a bend allowance. Measured on the real board:
        # the BEND_AREA shape is 1.2337 mm across for 28.26 deg and R = 2.5, and
        # 28.26 deg x 2.5 = 1.2331 - the inner arc to four decimals, with no
        # thickness term in it at all. It is the region to keep clear of vias
        # and packages, not the material budget. So the drawn area is used as a
        # CHECK: if it is not the inner arc either, the design is saying
        # something neither the parameters nor this reading explain, and that is
        # worth a line in the log.
        developed = neutral * theta
        drawn = bend.radius * theta
        if bend.width and bend.width > EPS and drawn > EPS:
            if abs(bend.width - drawn) > max(0.05, 0.1 * drawn):
                plan.notes.append(
                    f"  note: {bend.name}'s bend area is {bend.width:.3f} mm "
                    f"across, where its radius and angle draw {drawn:.3f} mm; "
                    f"folding {developed:.3f} mm of material either way")
        chain.append((bend, (nx, ny), (px, py), developed / 2.0, top, bottom))

    # -- bends that cross each other cannot be read ------------------------- #
    # Two bends are related in exactly one of three ways, and the third is
    # fatal: one lies wholly beyond the other (a chain), they lie on opposite
    # sides of the held panel (two arms - the real board has exactly this, a
    # tail bent up at one end and another bent down at the other), or their
    # strips overlap as seen from the held side, which says nothing about what
    # moves with what.
    kept = []
    for item in chain:
        bend, (nx, ny), (px, py), half, top, bottom = item
        clash = None
        for prev in kept:
            pbend, (pnx, pny), (ppx, ppy), phalf, _, _ = prev
            w = pnx * (px - ppx) + pny * (py - ppy)
            # Strips that MEET are fine - a flex rolled into a closed ring is
            # two 180 degree bends whose areas share a line, and there is
            # nothing ambiguous about it. Only material claimed by both is.
            if w + half > -phalf + EPS and w - half < phalf - EPS:
                clash = (prev, abs(w))
                break
        if clash:
            plan.notes.extend(_overlap_note(item, *clash, neutral_factor))
            continue
        kept.append(item)

    if not kept:
        return plan

    # -- who carries whom ---------------------------------------------------- #
    # A bend is a CHILD of every bend whose moving side wholly contains it, and
    # its parent is the innermost of those - the one with the most ancestors of
    # its own. Bends on different arms contain nothing and are all children of
    # the held panel. A flat list would only have described the single-tail
    # case; the real board is two tails off a middle.
    #
    # "Wholly contains" has to admit the case where the two strips MEET: a flex
    # rolled into a ring is two 180 degree bends whose bend areas share a line,
    # and read strictly neither would contain the other, both would be roots,
    # and the panel behind the first would swallow the second - which is how
    # the tail of a ring came back facing the wrong way.
    def contains(outer, inner) -> bool:
        _, (onx, ony), (opx, opy), ohalf, _, _ = outer
        _, _, (ipx, ipy), ihalf, _, _ = inner
        return onx * (ipx - opx) + ony * (ipy - opy) - ihalf > ohalf - EPS

    above = [[j for j in range(len(kept)) if j != i and contains(kept[j], kept[i])]
             for i in range(len(kept))]
    parent = [max(cands, key=lambda j: len(above[j])) if cands else None
              for cands in above]
    children = [[j for j in range(len(kept)) if parent[j] == i]
                for i in range(len(kept))]
    roots = [i for i in range(len(kept)) if parent[i] is None]

    plan.bends = [item[0] for item in kept]
    plan.chain = [(b, n, p, h) for b, n, p, h, _, _ in kept]

    def band(i) -> tuple[float, float]:
        """Where bend i's strip starts and ends, as n . p."""
        _, (nx, ny), (px, py), half, _, _ = kept[i]
        base = nx * px + ny * py
        return base - half, base + half

    def ancestry(i) -> list[tuple[float, float, float, float]]:
        """"Beyond every bend that carries this one" - the enclosing regions."""
        out = []
        k = parent[i]
        while k is not None:
            (nx, ny) = kept[k][1]
            out.append((nx, ny, band(k)[1], math.inf))
            k = parent[k]
        return out

    # -- the held panel ------------------------------------------------------ #
    # Everything on the near side of every bend that nothing else carries.
    plan.regions.append(_Region(
        label="held",
        bounds=[(kept[r][1][0], kept[r][1][1], -math.inf, band(r)[0]) for r in roots],
        trsf=gp_Trsf(), moved=False))

    # -- one strip and one panel per bend, deepest last ---------------------- #
    carried: dict[int | None, gp_Trsf] = {None: gp_Trsf()}
    for i in sorted(range(len(kept)), key=lambda k: len(above[k])):
        bend, (nx, ny), (px, py), half, top, bottom = kept[i]
        lo, hi = band(i)
        base_trsf = carried[parent[i]]
        enclosing = ancestry(i)

        steps = max(1, int(math.ceil(bend.angle / max(0.5, slice_angle))))
        step = 2 * half / steps
        sign = 1.0 if bend.inner_side == "top" else -1.0
        axis_z = (top + bend.radius) if sign > 0 else (bottom - bend.radius)
        theta = math.radians(bend.angle)
        # Overlap so consecutive slices interpenetrate instead of touching along
        # a line: the wedge a rotated slice opens on the outside of the bend is
        # about half the thickness times the slice angle.
        overlap = max(0.02, abs(top - bottom) * theta / steps)

        facets = []
        for j in range(steps):
            hinge = lo + j * step
            # The angle is interpolated across the strip rather than derived
            # from the neutral radius, so that the last slice always meets the
            # finished angle exactly whatever set the strip width.
            phi = theta * (hinge - lo) / (2 * half) if half > EPS else 0.0
            facets.append(_Region(
                label=f"{bend.name} slice {j + 1}/{steps}",
                bounds=[(nx, ny, hinge - overlap, hinge + step + overlap)] + enclosing,
                trsf=_slice_trsf(base_trsf, nx, ny, lo, hinge, axis_z, sign * phi),
                kind="slice"))

        # The strip is cut as ONE piece and bent exactly where it can be; the
        # facets are the fallback, and they stay in `regions` as well because
        # that list is what answers "where does a point at (x, y) end up".
        plan.strips.append(_Strip(
            bend=bend, bounds=[(nx, ny, lo, hi)] + enclosing, normal=(nx, ny),
            lo=lo, hi=hi, axis_z=axis_z, turn=sign * theta, carried=base_trsf,
            facets=facets))
        plan.regions.extend(facets)

        # everything past the bend rides on the finished angle
        carried[i] = _slice_trsf(base_trsf, nx, ny, lo, hi, axis_z, sign * theta)
        plan.regions.append(_Region(
            label=f"panel after {bend.name}",
            bounds=[(nx, ny, hi, math.inf)] + enclosing
                   + [(kept[c][1][0], kept[c][1][1], -math.inf, band(c)[0])
                      for c in children[i]],
            trsf=carried[i], moved=True))

    plan.notes.insert(0, (
        f"  held: the piece containing the anchor at "
        f"{anchor[0]:.3f}, {anchor[1]:.3f}" if anchor is not None
        else "  held: the largest piece the bend lines leave (no anchor set)"))
    plan.notes.insert(0, f"Folding {len(plan.bends)} bend(s):")
    return plan


def _overlap_note(item, prev, apart: float, neutral_factor: float) -> list[str]:
    """Why two bends cannot both be folded, in the numbers that caused it.

    Nearly always the neutral factor, and the message has to say so. Allegro
    draws a bend area at the INNER arc, angle x radius, with no thickness term
    in it; the material a bend really consumes is the arc at the neutral axis,
    angle x (radius + k x thickness), which is longer. So a designer who lays
    two bend areas edge to edge - a flex rolled into a closed ring is exactly
    that, two 180 degree areas that touch - has drawn something that fits in
    Allegro and does not fit here, by k x thickness x angle per bend.

    Measured on the real board: two 180 degree bends at R = 0.795 with their
    lines 2.500 mm apart, drawn 2.4999 mm across each, which is the inner arc
    to a tenth of a micron and closes the ring exactly. At k = 0.5 each strip
    wants 2.805 mm, they overlap by 0.305 mm, and the second bend is refused.
    Nothing is wrong with the board; the answer is the setting, and the log
    now names it and the value that would fit.
    """
    bend, _, _, half, top, bottom = item
    other, _, _, ohalf, otop, obottom = prev
    lines = [
        f"  warning: bends {bend.name} and {other.name} both want to fold the "
        f"same material - {2 * half:.3f} mm and {2 * ohalf:.3f} mm of it with "
        f"their lines only {apart:.3f} mm apart - so which of them carries the "
        f"other cannot be read; {bend.name} is left flat"]

    drawn = (bend.width or 0.0) + (other.width or 0.0)
    if drawn <= EPS or drawn > 2 * apart + EPS:
        return lines                       # the drawn areas overlap too: a design

    # Both areas fit; only the neutral term does not. Solve for the k that
    # makes the two developed lengths exactly meet.
    theta = math.radians(bend.angle)
    otheta = math.radians(other.angle)
    slack = (2 * apart - bend.radius * theta - other.radius * otheta)
    room = abs(top - bottom) * theta + abs(otop - obottom) * otheta
    fits = max(0.0, slack / room) if room > EPS else 0.0
    lines.append(
        f"    their drawn bend areas do not overlap - Allegro draws them at the "
        f"inner arc, {drawn / 2:.3f} mm each on average - so this is the neutral "
        f"factor, now {neutral_factor:.2f}: at {fits:.2f} the two strips meet "
        f"exactly (foldNeutral in the config, --fold-neutral on the command line)")
    return lines


def plan_from_json(data: dict, board_top_z: float, board_bottom_z: float,
                   zones: list[dict] | None = None,
                   levels: dict | None = None,
                   slice_angle: float = DEFAULT_SLICE_ANGLE,
                   anchor: tuple[float, float] | None = DEFAULT_ANCHOR,
                   neutral_factor: float = DEFAULT_NEUTRAL_FACTOR,
                   log: LogFn = _noop_log) -> FoldPlan:
    """The fold for one intermediate, or an empty plan when it carries no bends.

    An intermediate written before format_version 7 has no `bends` key at all,
    which reads here as "nothing to fold" - the same way an absent `zones`
    means an ordinary board. Nothing warns about it: a board with no bend areas
    is the normal case, and every board exported until now was one.
    """
    bends = bends_from_json(data, log)
    if not bends:
        return FoldPlan(slice_angle=slice_angle)

    contours = (data.get("pcb") or {}).get("edges") or []
    outline = contour_points(contours[0]) if contours else []

    # A bend's radius is measured from the surface of the FLEX, so the stack
    # that matters is the local one. On the test board the flex is 0.365 thick
    # and sits 2.05 mm below the top of the stiffener: taking the board's own
    # top face would put the cylinder axis two millimetres out and swing the
    # tail through a visibly wrong arc.
    stack_at = None
    if zones and levels:
        polys = []
        for zone in zones:
            name = str(zone["name"])
            if name in levels:
                polys.append((name, contour_points(zone.get("contour")), levels[name]))
        thinnest = min((lv for _, _, lv in polys), key=lambda lv: lv[0] - lv[1],
                       default=(board_top_z, board_bottom_z))

        def stack_at(x: float, y: float, _polys=polys, _thin=thinnest):
            for name, poly, level in _polys:
                if poly and point_in_polygon((x, y), poly):
                    return level
            return _thin

    # The design's own anchor, if a future Allegro ever writes one: it beats the
    # setting, because it is what the designer marked on the board.
    from_design = data.get("anchor")
    if (isinstance(from_design, (list, tuple)) and len(from_design) >= 2
            and all(isinstance(v, (int, float)) for v in from_design[:2])):
        anchor = (float(from_design[0]), float(from_design[1]))
        log(f"Fold anchor {anchor[0]:.3f}, {anchor[1]:.3f} taken from the design")

    return plan_fold(bends, outline, board_top_z, board_bottom_z,
                     stack_at=stack_at, slice_angle=slice_angle,
                     anchor=anchor, neutral_factor=neutral_factor, log=log)


def _slice_trsf(carried: gp_Trsf, nx: float, ny: float, lo: float,
                hinge: float, axis_z: float, phi: float) -> gp_Trsf:
    """The transform of a piece hinged at `hinge`, rotated `phi` about the arc.

    Two steps, and the order is the whole trick: slide the piece back along the
    bend direction until its leading edge sits at the start of the arc, THEN
    rotate it about the cylinder axis. That is what makes the flat material the
    bend consumes disappear into the arc instead of stretching the board.

    `carried` is everything the earlier bends in the chain already do to this
    piece, and it is applied last.
    """
    shift = hinge - lo
    slide = gp_Trsf()
    slide.SetTranslation(gp_Vec(-shift * nx, -shift * ny, 0.0))

    # (nx, ny) is a unit vector, so the point `lo` along it is a foot of the
    # cylinder axis; the axis itself runs parallel to the bend line, and the
    # direction n x z is what makes a positive angle tip the far side upwards.
    origin = gp_Pnt(nx * lo, ny * lo, axis_z)
    direction = gp_Dir(ny, -nx, 0.0)

    turn = gp_Trsf()
    turn.SetRotation(gp_Ax1(origin, direction), phi)
    return carried * turn * slide


def _anchor_signs(bends: list[Bend], outline: list[tuple[float, float]],
                  anchor: tuple[float, float] | None,
                  notes: list[str]) -> list[float]:
    """+1 or -1 per bend, orienting its normal away from the piece that is held.

    With an anchor - the ordinary case, and the origin by default - this is one
    signed distance per bend and nothing else. Without one, the held piece is
    the largest the bend lines leave: every combination of sides is tried (2^n,
    and n is one or two on a real board), the outline is clipped to each, and
    the biggest survivor wins.
    """
    n = len(bends)

    if anchor is not None:
        signs = []
        for bend in bends:
            nx, ny = bend.normal()
            px, py = bend.midpoint
            side = nx * (anchor[0] - px) + ny * (anchor[1] - py)
            if abs(side) <= EPS:
                notes.append(
                    f"  warning: the fold anchor sits on bend {bend.name}'s own "
                    f"line, which cannot say which side is held; guessing")
            signs.append(-1.0 if side > 0 else 1.0)
        return signs

    if not outline or n > 8:
        return [1.0] * n

    best_area, best = -1.0, (1,) * n
    for mask in range(1 << n):
        poly = list(outline)
        signs = []
        for i, bend in enumerate(bends):
            sign = 1.0 if (mask >> i) & 1 else -1.0
            signs.append(sign)
            nx, ny = bend.normal()
            px, py = bend.midpoint
            # keep the side the sign points AT: sign * n . (p - p0) >= 0
            poly = clip_halfplane(poly, -sign * nx, -sign * ny,
                                  -sign * (nx * px + ny * py))
            if len(poly) < 3:
                break
        area = polygon_area(poly)
        if area > best_area:
            best_area, best = area, tuple(signs)

    # the held cell is the one just found; a bend's normal must point away from
    # it, which is the opposite sign
    return [-s for s in best]


def _anchor_point(bends: list[Bend], normals: list[tuple[float, float]],
                  outline: list[tuple[float, float]]) -> tuple[float, float]:
    """A point inside the held piece, used only to order the chain."""
    poly = list(outline)
    for bend, (nx, ny) in zip(bends, normals):
        px, py = bend.midpoint
        poly = clip_halfplane(poly, nx, ny, nx * px + ny * py)
        if len(poly) < 3:
            break
    if len(poly) >= 3:
        return (sum(p[0] for p in poly) / len(poly),
                sum(p[1] for p in poly) / len(poly))
    if outline:
        return (sum(p[0] for p in outline) / len(outline),
                sum(p[1] for p in outline) / len(outline))
    return (0.0, 0.0)


# --------------------------------------------------------------------------- #
# OCC plumbing
# --------------------------------------------------------------------------- #

def _bbox(shape: TopoDS_Shape):
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, True)
    if box.IsVoid():
        return None
    return box.Get()          # (xmin, ymin, zmin, xmax, ymax, zmax)


def _extent(box, nx: float, ny: float) -> tuple[float, float]:
    xmin, ymin, _, xmax, ymax, _ = box
    values = [nx * x + ny * y for x in (xmin, xmax) for y in (ymin, ymax)]
    return min(values), max(values)


def _is_empty(shape: TopoDS_Shape) -> bool:
    if shape is None or shape.IsNull():
        return True
    for kind in (TopAbs_ShapeEnum.TopAbs_SOLID,
                 TopAbs_ShapeEnum.TopAbs_FACE,
                 TopAbs_ShapeEnum.TopAbs_EDGE):
        if TopExp_Explorer(shape, kind).More():
            return False
    return True


def _cut_to_region(shape: TopoDS_Shape,
                   bounds: list[tuple[float, float, float, float]],
                   box) -> TopoDS_Shape | None:
    """The part of *shape* inside every one of *bounds*, or None if nothing is.

    Each bound that the shape already satisfies is skipped rather than turned
    into a boolean - on a board with one bend that leaves the far panel and the
    held panel each costing a single cut, and the silkscreen on either of them
    costing none at all.
    """
    piece = shape
    for nx, ny, lo, hi in bounds:
        low, high = _extent(box, nx, ny)
        if high < lo - EPS or low > hi + EPS:
            return None
        if low >= lo - EPS and high <= hi + EPS:
            continue
        cutter = _slab(nx, ny, lo, hi, box)
        common = BRepAlgoAPI_Common(piece, cutter)
        if not common.IsDone():
            return None
        piece = common.Shape()
        if _is_empty(piece):
            return None
    return None if _is_empty(piece) else piece


def _slab(nx: float, ny: float, lo: float, hi: float, box) -> TopoDS_Shape:
    """A box covering everything between the planes `n.p = lo` and `n.p = hi`."""
    xmin, ymin, zmin, xmax, ymax, zmax = box
    span = math.hypot(xmax - xmin, ymax - ymin) + abs(zmax - zmin) + 10.0
    low, high = _extent(box, nx, ny)
    lo = max(lo, low - 1.0) if lo != -math.inf else low - 1.0
    hi = min(hi, high + 1.0) if hi != math.inf else high + 1.0

    # frame with X across the bend, Y along it, Z up
    origin = gp_Pnt(nx * lo + ny * span, ny * lo - nx * span, zmin - 1.0)
    frame = gp_Ax2(origin, gp_Dir(0, 0, 1), gp_Dir(nx, ny, 0))
    return BRepPrimAPI_MakeBox(frame, hi - lo, 2 * span,
                               (zmax - zmin) + 2.0).Shape()


# How closely the strip must be a straight prism before it is revolved rather
# than faceted: its volume has to equal one cross-section times its width to
# within this fraction.
PRISM_TOLERANCE = 0.002

# How far the wrapped solid may weigh from what the bend says it should before
# it is thrown away and the facets used instead.
MAP_VOLUME_TOLERANCE = 0.01

# How far the cross-section may fall short of the strip's own extent, along the
# bend line and in z, before the strip is not a prism after all. A LENGTH and
# not a fraction, deliberately: what it catches is a feature small enough to
# disappear into the volume it sits in - see _spans_alike.
PRISM_SPAN_TOLERANCE = 1e-3          # 1 micron


def _spans_alike(flat: TopoDS_Shape, face: TopoDS_Shape, strip: _Strip) -> bool:
    """Does the cross-section reach as far as the strip itself does?

    Measured in the strip's own frame - the bend line turned onto X - so a bend
    line at any angle is treated the same way; an axis-aligned box would call
    every diagonal strip a taper.

    Tight boxes (AddOptimal), because Bnd_Box pads by the shape's tolerance and
    the difference that matters here is microns. AddOptimal also follows curved
    edges properly, which a vertex-by-vertex comparison would not: the outline
    this exists to catch bulges along an arc.
    """
    nx, ny = strip.normal
    turn = gp_Trsf()
    turn.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)),
                     -math.atan2(nx, -ny))          # tangent (-ny, nx) -> +X

    def extents(shape: TopoDS_Shape):
        box = Bnd_Box()
        BRepBndLib.AddOptimal_s(
            BRepBuilderAPI_Transform(shape, turn, True).Shape(), box, False, False)
        if box.IsVoid():
            return None
        xmin, _, zmin, xmax, _, zmax = box.Get()
        return xmin, xmax, zmin, zmax

    whole, section = extents(flat), extents(face)
    if whole is None or section is None:
        return False
    return all(abs(a - b) <= PRISM_SPAN_TOLERANCE for a, b in zip(whole, section))


def _revolve_strip(flat: TopoDS_Shape, strip: _Strip) -> TopoDS_Shape | None:
    """The bent strip as a REVOLVED section - exact cylinders, no facets.

    The bend map takes (u across the board, v along the bend, z) to cylindrical
    coordinates about an axis parallel to u: v becomes the angle, z becomes the
    radius, and u is untouched. So if the strip is the same shape at every v -
    a straight tail crossing the bend, which is the ordinary case and what the
    real board has - then the bent strip is exactly its cross-section revolved
    about the bend axis. Six faces instead of fifty, two of them true cylinders,
    and no sewing or repair anywhere.

    "The same shape at every v" is checked by MEASUREMENT rather than by
    topology: one cross-section times the width of the strip must equal the
    strip's volume. A taper, a fillet running into the bend area or a hole
    inside it all break that equality, and then None comes back and the caller
    facets instead. The section is taken a quarter of the way in, where a taper
    shows; at the middle a symmetric one would average out.

    The section is measured inside the solid and then slid to the start of the
    arc, rather than being taken on the boundary face, because a boolean against
    a face that is coincident with the solid's own face is exactly the kind of
    thing that returns something empty on one board in twenty.
    """
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
    from OCP.GProp import GProp_GProps

    width = strip.hi - strip.lo
    if width <= EPS or abs(strip.turn) < math.radians(MIN_ANGLE):
        return None

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(flat, props)
    volume = props.Mass()
    if volume <= 0:
        return None

    box = _bbox(flat)
    if box is None:
        return None

    nx, ny = strip.normal
    cut_at = strip.lo + width / 4.0
    section = BRepAlgoAPI_Common(flat, _plane_face(nx, ny, cut_at, box))
    if not section.IsDone():
        return None
    face = section.Shape()
    if _is_empty(face):
        return None

    BRepGProp.SurfaceProperties_s(face, props)
    area = props.Mass()
    if area <= 0 or abs(area * width - volume) > PRISM_TOLERANCE * volume:
        return None

    # The volume test alone is not enough, and a real board says so. On
    # flex2-a0 the outline runs straight past BEND_1 and then curves outward
    # INSIDE the bend area, reaching 0.0252 mm beyond the straight part by the
    # far edge of the strip. That is 0.04% of the strip's volume - comfortably
    # under PRISM_TOLERANCE - so the strip was revolved as though it were
    # straight, the curve was dropped, and the model came out with a 25 micron
    # ledge along the edge of the flex where the bend ended. Measured, and the
    # number reported from the board matched to the micron.
    #
    # So the section must also SPAN what the strip spans: compared in the
    # strip's own frame, along the bend line and in z. Nothing extra is built
    # for it - the section is already in hand, and the two tight boxes cost
    # nothing next to the booleans around them.
    #
    # What this still cannot see: an extremum strictly inside a curved edge
    # that leaves the box unchanged AND the volume within 0.2%. The wrap is the
    # general construction and is what such a strip falls through to.
    if not _spans_alike(flat, face, strip):
        return None

    slide = gp_Trsf()
    slide.SetTranslation(gp_Vec(-(cut_at - strip.lo) * nx,
                                -(cut_at - strip.lo) * ny, 0.0))
    face = BRepBuilderAPI_Transform(face, slide, True).Shape()

    # MakeRevol only ever turns the positive way about its axis, so a bend that
    # goes the other way flips the axis instead of the angle.
    axis = strip.axis()
    if strip.turn < 0:
        axis = gp_Ax1(axis.Location(), axis.Direction().Reversed())

    builder = BRep_Builder()
    bent = TopoDS_Compound()
    builder.MakeCompound(bent)
    made = 0
    explorer = TopExp_Explorer(face, TopAbs_ShapeEnum.TopAbs_FACE)
    while explorer.More():
        try:
            solid = BRepPrimAPI_MakeRevol(explorer.Current(), axis,
                                          abs(strip.turn)).Shape()
        except Exception:
            return None
        if solid.IsNull() or not BRepCheck_Analyzer(solid).IsValid():
            return None
        builder.Add(bent, solid)
        made += 1
        explorer.Next()

    if not made:
        return None
    return BRepBuilderAPI_Transform(bent, strip.carried, True).Shape()


def _prism_of(shape: TopoDS_Shape):
    """(top faces, z_top, z_bottom) if *shape* is a vertical prism, else None.

    Every piece this module folds is one: the board is built by extruding a
    planar region in z and then cutting it with vertical prisms, so its faces
    are two horizontal planes and walls that all contain the z direction. That
    is what lets the whole solid be rebuilt from its top face alone.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.GeomAbs import GeomAbs_SurfaceType

    flat: list[tuple[float, TopoDS_Shape, float]] = []
    explorer = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        surf = BRepAdaptor_Surface(face)
        kind = surf.GetType()
        if kind == GeomAbs_SurfaceType.GeomAbs_Plane:
            nz = surf.Plane().Axis().Direction().Z()
            if abs(nz) > 0.999:
                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face, props)
                flat.append((props.CentreOfMass().Z(), face, props.Mass()))
            elif abs(nz) > 1.0e-6:
                return None                    # a slanted wall: not a prism
        elif kind == GeomAbs_SurfaceType.GeomAbs_Cylinder:
            if abs(surf.Cylinder().Axis().Direction().Z()) < 0.999:
                return None                    # a hole that is not vertical
        else:
            return None                        # anything else: not our shape
        explorer.Next()

    if not flat:
        return None
    z_top = max(z for z, _, _ in flat)
    z_bottom = min(z for z, _, _ in flat)
    if z_top - z_bottom <= EPS:
        return None
    tops = [(f, a) for z, f, a in flat if abs(z - z_top) < 1.0e-7]
    if not tops:
        return None
    return tops, z_top, z_bottom


def _map_strip(flat: TopoDS_Shape, strip: _Strip,
               why: list[str] | None = None) -> TopoDS_Shape | None:
    """The bent strip, built by wrapping its outline onto the cylinder.

    This is the general construction, and it works on the shapes the revolve
    refuses: a tail with the relief notches a real flex board carries at the
    ends of its bend line, a zone that stops inside the bend area, a hole.

    **The whole thing rests on one property of the bend map.** In the cylinder's
    own PARAMETER space - angle across the bend, distance along it - the map is
    an affine change of coordinates: the angle is the distance across the bend
    divided by the neutral radius, and the distance along it is untouched. An
    affine map takes a line to a line and a circle to an ellipse; it does not
    bend anything. So the flat outline can be carried into that parameter space
    and the two faces of the bent strip built ON the cylinder, exactly, however
    complicated the outline is.

    What is built, per top face of the flat piece:

    - the same 2D outline serves BOTH cylinders, the inner one and the outer,
      which is what keeps them in registration - they are the same curve, and
      the only difference is the radius of the surface it is drawn on;
    - a ruled wall between each pair of corresponding edges. Where the flat edge
      ran along the bend the wall is a radial plane, where it ran across it is a
      plane at constant distance, and where it ran at an angle it is the ruled
      surface between two helices, which is what it physically is.

    Straight edges keep exact 2D lines. Everything else is sampled and fitted as
    a 2D spline: the SURFACE stays an exact cylinder either way, and only the
    curve trimming it is approximated, to well under a micron.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_MakeSolid, BRepBuilderAPI_MakeWire, BRepBuilderAPI_Sewing,
    )
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepFill import BRepFill
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepLib import BRepLib
    from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
    from OCP.GProp import GProp_GProps
    from OCP.Geom import Geom_CylindricalSurface
    from OCP.Geom2d import Geom2d_Ellipse, Geom2d_Line, Geom2d_TrimmedCurve
    from OCP.Geom2dAPI import Geom2dAPI_PointsToBSpline
    from OCP.GeomAbs import GeomAbs_CurveType
    from OCP.TColgp import TColgp_Array1OfPnt2d
    from OCP.TopAbs import TopAbs_Orientation
    from OCP.TopoDS import TopoDS_Vertex
    from OCP.gp import gp_Ax3, gp_Ax22d, gp_Dir2d, gp_Pnt2d, gp_Vec2d

    def give_up(reason: str) -> None:
        """Say which step refused, so a board that facets can be diagnosed."""
        if why is not None and not why:
            why.append(reason)
        return None

    width = strip.hi - strip.lo
    if width <= EPS or abs(strip.turn) < math.radians(MIN_ANGLE):
        return give_up("the strip has no width or no angle")
    rho = width / abs(strip.turn)          # the neutral radius, back out of it

    # A layer can arrive as several disjoint solids - a stiffener that the bend
    # area clips at both ends is two - and each is wrapped on its own. Sewing
    # them together would be asking for one shell out of pieces that do not
    # touch.
    separate = []
    explorer = TopExp_Explorer(flat, TopAbs_ShapeEnum.TopAbs_SOLID)
    while explorer.More():
        separate.append(explorer.Current())
        explorer.Next()
    if len(separate) > 1:
        builder = BRep_Builder()
        compound = TopoDS_Compound()
        builder.MakeCompound(compound)
        for piece in separate:
            one = _map_strip(piece, strip, why)
            if one is None:
                return None
            builder.Add(compound, one)
        return compound

    prism = _prism_of(flat)
    if prism is None:
        return give_up("the piece is not a prism standing on a flat face")
    tops, z_top, z_bottom = prism

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(flat, props)
    volume = props.Mass()
    area = sum(a for _, a in tops)
    thickness = z_top - z_bottom
    if volume <= 0 or abs(area * thickness - volume) > PRISM_TOLERANCE * volume:
        return give_up("the piece is not the extrusion of its own top face")

    # the cylinder frame: Z along the bend line, X pointing at the flat board
    nx, ny = strip.normal
    sign = 1.0 if strip.turn > 0 else -1.0
    origin = gp_Pnt(nx * strip.lo, ny * strip.lo, strip.axis_z)
    along = gp_Dir(ny, -nx, 0.0) if sign > 0 else gp_Dir(-ny, nx, 0.0)
    frame = gp_Ax3(origin, along, gp_Dir(0.0, 0.0, -sign))
    r_top = abs(strip.axis_z - z_top)
    r_bottom = abs(strip.axis_z - z_bottom)
    if min(r_top, r_bottom) <= EPS:
        return None                        # the axis runs through the material
    cyl_top = Geom_CylindricalSurface(frame, r_top)
    cyl_bottom = Geom_CylindricalSurface(frame, r_bottom)

    ax, ay = origin.X(), origin.Y()
    zx, zy = along.X(), along.Y()

    def to2d(point: gp_Pnt) -> gp_Pnt2d:
        """A flat point as (angle across the bend, distance along it)."""
        dx, dy = point.X() - ax, point.Y() - ay
        return gp_Pnt2d((nx * dx + ny * dy) / rho, zx * dx + zy * dy)

    def sampled(adaptor, first, last):
        """A stretch of one flat edge, as a 2D spline in parameter space."""
        length = 0.0
        previous = adaptor.Value(first)
        for i in range(1, 9):                    # rough length, for the density
            here = adaptor.Value(first + (last - first) * i / 8.0)
            length += previous.Distance(here)
            previous = here
        count = min(200, max(8, int(length / 0.05) + 8))
        points = TColgp_Array1OfPnt2d(1, count)
        for i in range(count):
            t = first + (last - first) * i / (count - 1)
            points.SetValue(i + 1, to2d(adaptor.Value(t)))
        curve = Geom2dAPI_PointsToBSpline(points).Curve()
        return curve, curve.FirstParameter(), curve.LastParameter()

    def curves2d(edge):
        """One flat edge as 2D curves in the cylinder's parameter space.

        A CLOSED edge - a drill hole is one circle and nothing else - comes back
        as two halves. Sampling it whole would hand the fitter a point list whose
        first and last point are the same, and the curve that comes out of that
        is not a curve.
        """
        adaptor = BRepAdaptor_Curve(edge)
        first, last = adaptor.FirstParameter(), adaptor.LastParameter()
        if edge.Orientation() == TopAbs_Orientation.TopAbs_REVERSED:
            first, last = last, first

        if adaptor.GetType() == GeomAbs_CurveType.GeomAbs_Line:
            start, end = to2d(adaptor.Value(first)), to2d(adaptor.Value(last))
            step = gp_Vec2d(start, end)
            length = step.Magnitude()
            if length < 1.0e-9:
                return None
            return [(Geom2d_TrimmedCurve(Geom2d_Line(start, gp_Dir2d(step)),
                                         0.0, length), 0.0, length)]

        if adaptor.GetType() == GeomAbs_CurveType.GeomAbs_Circle:
            # An arc becomes an ELLIPSE, exactly: the map scales one axis and
            # leaves the other, and that is all a circle needs to become one.
            #
            # This is not a nicety. Sampling a relief notch as a spline puts a
            # wiggle of a few nanometres at its ends, where it meets the
            # straight edge it was cut into, and OCC calls the wire
            # self-intersecting and throws the whole solid away. Every FLEX2
            # layer of the real board failed exactly there.
            circle = adaptor.Circle()
            centre = to2d(circle.Location())
            across, along = circle.Radius() / rho, circle.Radius()
            if across >= along:
                axes = gp_Ax22d(centre, gp_Dir2d(1.0, 0.0), gp_Dir2d(0.0, 1.0))
                major, minor = across, along
            else:
                axes = gp_Ax22d(centre, gp_Dir2d(0.0, 1.0), gp_Dir2d(-1.0, 0.0))
                major, minor = along, across
            if minor < 1.0e-12:
                return None
            ellipse = Geom2d_Ellipse(axes, major, minor)

            def where(point) -> float:
                step = gp_Vec2d(centre, point)
                return math.atan2(
                    step.Dot(gp_Vec2d(axes.YDirection())) / minor,
                    step.Dot(gp_Vec2d(axes.XDirection())) / major) % (2 * math.pi)

            start = where(to2d(adaptor.Value(first)))
            end = where(to2d(adaptor.Value(last)))
            middle = where(to2d(adaptor.Value((first + last) / 2.0)))
            forward = (middle - start) % (2 * math.pi) <= (end - start) % (2 * math.pi)
            if adaptor.Value(first).Distance(adaptor.Value(last)) < 1.0e-9:
                span = 2 * math.pi                     # a whole circle: a hole
                forward = True
            elif forward:
                span = (end - start) % (2 * math.pi)
            else:
                span = (start - end) % (2 * math.pi)
            low = start if forward else end
            curve = Geom2d_TrimmedCurve(ellipse, low, low + span, forward)
            return [(curve, curve.FirstParameter(), curve.LastParameter())]

        if adaptor.Value(first).Distance(adaptor.Value(last)) < 1.0e-9:
            middle = (first + last) / 2.0
            return [sampled(adaptor, first, middle),
                    sampled(adaptor, middle, last)]
        return [sampled(adaptor, first, last)]

    def wire_on(surface, curves):
        """The wrapped outline as a wire ON *surface*, sharing its corners.

        Each edge is rebuilt from its own 2D curve, so where two of them meet
        the two surface points agree only as well as the FLAT solid's own
        vertices did - a couple of tenths of a micron on a shape that came out
        of a boolean, which is well inside the tolerance the flat shape carries
        on that vertex and therefore perfectly legal there.

        BRepBuilderAPI_MakeWire joins edges by comparing vertices at
        Precision::Confusion, a flat 1e-7 that nothing can widen, and when the
        gap is bigger than that it does not report a failure: it starts a
        second wire, and IsDone() comes back TRUE as soon as some later edge
        closes a loop - having silently dropped the rest. Measured on the real
        board: a four-edge outline came back as a wire of two, the two missing
        walls stayed unsewn, the shell never closed and the bend fell back to
        facets, with nothing in the log but "not valid".

        So the corners are made explicit. One vertex per junction, placed
        between the two curve ends with a tolerance wide enough to reach both,
        and every edge is built on the vertices its neighbours share: the wire
        is then connected by TOPOLOGY and no tolerance decides anything. The
        edge count is checked anyway, because this is exactly the kind of
        failure that is invisible until a solid comes out inside out.
        """
        count = len(curves)
        if not count:
            return None

        ends = []
        for curve, first, last in curves:
            head, tail = curve.Value(first), curve.Value(last)
            ends.append((surface.Value(head.X(), head.Y()),
                         surface.Value(tail.X(), tail.Y())))

        builder = BRep_Builder()
        corners = []
        for i in range(count):
            here, there = ends[i][1], ends[(i + 1) % count][0]
            corner = TopoDS_Vertex()
            builder.MakeVertex(
                corner,
                gp_Pnt((here.X() + there.X()) / 2.0,
                       (here.Y() + there.Y()) / 2.0,
                       (here.Z() + there.Z()) / 2.0),
                here.Distance(there) / 2.0 + 1.0e-7)
            corners.append(corner)

        maker = BRepBuilderAPI_MakeWire()
        for i, (curve, first, last) in enumerate(curves):
            edge = BRepBuilderAPI_MakeEdge(curve, surface, corners[i - 1],
                                           corners[i], first, last)
            if not edge.IsDone():
                return None
            maker.Add(edge.Edge())
        if not maker.IsDone():
            return None
        wire = maker.Wire()

        kept = 0
        walker = TopExp_Explorer(wire, TopAbs_ShapeEnum.TopAbs_EDGE)
        while walker.More():
            kept += 1
            walker.Next()
        if kept != count:
            return None

        BRepLib.BuildCurves3d_s(wire)
        return wire

    sewing = BRepBuilderAPI_Sewing(1.0e-6)
    for face, _ in tops:
        outer = BRepTools.OuterWire_s(face)
        wires = []
        explorer = TopExp_Explorer(face, TopAbs_ShapeEnum.TopAbs_WIRE)
        while explorer.More():
            wire = TopoDS.Wire_s(explorer.Current())
            wires.append((wire, wire.IsSame(outer)))
            explorer.Next()

        mapped: list[tuple[list, bool]] = []
        for wire, is_outer in wires:
            curves = []
            walker = BRepTools_WireExplorer(wire)
            while walker.More():
                one = curves2d(walker.Current())
                if one is None:
                    return give_up("an edge of the outline could not be carried "
                                   "onto the cylinder")
                curves.extend(one)
                walker.Next()
            if not curves:
                return give_up("a wire of the outline came back empty")
            mapped.append((curves, is_outer))

        for surface in (cyl_top, cyl_bottom):
            built = None
            for curves, is_outer in sorted(mapped, key=lambda m: not m[1]):
                wire = wire_on(surface, curves)
                if wire is None:
                    return give_up("the wrapped outline did not close into a wire")
                if built is None:
                    maker = BRepBuilderAPI_MakeFace(surface, wire, True)
                else:
                    # A hole. Its wire runs the opposite way round to the outer
                    # one on the flat face, and it has to keep doing so here, or
                    # the face comes out with the hole as its material.
                    maker = BRepBuilderAPI_MakeFace(built, TopoDS.Wire_s(wire.Reversed()))
                if not maker.IsDone():
                    return give_up("the wrapped outline did not close into a face")
                built = maker.Face()
            if built is None:
                return give_up("no face came out of the wrapped outline")
            sewing.Add(built)

        # the walls, one per edge, ruled between the two cylinders
        for curves, _ in mapped:
            for curve, first, last in curves:
                top_edge = BRepBuilderAPI_MakeEdge(curve, cyl_top, first, last)
                bottom_edge = BRepBuilderAPI_MakeEdge(curve, cyl_bottom, first, last)
                if not (top_edge.IsDone() and bottom_edge.IsDone()):
                    return give_up("a wall edge could not be built")
                one, two = top_edge.Edge(), bottom_edge.Edge()
                BRepLib.BuildCurves3d_s(one)
                BRepLib.BuildCurves3d_s(two)
                try:
                    wall = BRepFill.Face_s(one, two)
                except Exception as exc:
                    return give_up(f"a wall could not be ruled ({exc})")
                if wall.IsNull():
                    return give_up("a wall came out empty")
                sewing.Add(wall)

    sewing.Perform()
    shell = sewing.SewedShape()
    if shell.IsNull():
        return give_up("the faces did not sew together")

    solid = None
    explorer = TopExp_Explorer(shell, TopAbs_ShapeEnum.TopAbs_SHELL)
    if explorer.More():
        maker = BRepBuilderAPI_MakeSolid(TopoDS.Shell_s(explorer.Current()))
        if maker.IsDone():
            solid = maker.Solid()
    if solid is None or solid.IsNull():
        return give_up("the sewn faces did not make a closed shell")
    if not BRepCheck_Analyzer(solid).IsValid():
        return give_up("the solid built from them is not valid")

    # The ITERATIVE integrator, not the plain call. A solid with B-spline walls
    # measures 1.5% light through the default one - which sent every wrapped
    # piece of the real board back to the facets, for a defect that was in the
    # measurement and not in the geometry. With eps it agrees with the closed
    # form to 2e-6.
    BRepGProp.VolumeProperties_s(solid, props, 1.0e-5, False, False)
    made = props.Mass()
    if made < 0:                            # sewn inside out
        solid = TopoDS.Solid_s(solid.Reversed())
        made = -made

    # What the piece SHOULD weigh once bent, which is not what it weighed flat.
    #
    # The map multiplies volume by r/rho - material at a bigger radius than the
    # neutral one is stretched, material inside it is compressed - so a layer
    # above the core gains and one below loses, and only a stack symmetric about
    # the neutral axis comes out unchanged. Integrated over a prism that is
    # exactly `r at mid-thickness over rho`.
    #
    # Measured on the real board's stiffener zone: 0.937 for the top coverlay,
    # 1.000 for the dielectric at the core, 1.063 for the bottom coverlay -
    # symmetric about the middle, which is the bend being isometric. Checking
    # for the flat volume instead rejected every layer but the middle one.
    expected = volume * abs(strip.axis_z - (z_top + z_bottom) / 2.0) / rho
    if expected <= 0 or abs(made - expected) > MAP_VOLUME_TOLERANCE * expected:
        return give_up(f"it came out weighing {made:.6f} where the bend should "
                       f"make it {expected:.6f}")

    return BRepBuilderAPI_Transform(solid, strip.carried, True).Shape()


def _plane_face(nx: float, ny: float, at: float, box) -> TopoDS_Shape:
    """A planar face at `n . p = at`, big enough to cut anything in *box*."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.gp import gp_Pln

    xmin, ymin, zmin, xmax, ymax, zmax = box
    span = math.hypot(xmax - xmin, ymax - ymin) + abs(zmax - zmin) + 10.0
    plane = gp_Pln(gp_Pnt(nx * at, ny * at, (zmin + zmax) / 2.0),
                   gp_Dir(nx, ny, 0.0))
    return BRepBuilderAPI_MakeFace(plane, -span, span, -span, span).Face()


def _fuse_all(pieces: list[TopoDS_Shape], log: LogFn) -> TopoDS_Shape:
    """Fuse in one multi-argument boolean, then merge what is coplanar.

    The same shape of call as the stackup fuse, and for the same reason: pairwise
    fusing is quadratic and this list is one panel plus a dozen slices per bend.
    The unify pass is what removes the seams left where the board was cut into
    regions - inside a panel those faces are coplanar and have no business
    surviving.
    """
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain

    arguments = TopTools_ListOfShape()
    arguments.Append(pieces[0])
    tools = TopTools_ListOfShape()
    for piece in pieces[1:]:
        tools.Append(piece)

    op = BRepAlgoAPI_Fuse()
    op.SetArguments(arguments)
    op.SetTools(tools)
    op.SetRunParallel(True)
    op.Build()
    if not op.IsDone():
        log("warning: could not fuse the folded pieces; leaving them separate")
        builder = BRep_Builder()
        compound = TopoDS_Compound()
        builder.MakeCompound(compound)
        for piece in pieces:
            builder.Add(compound, piece)
        return compound

    fused = op.Shape()
    try:
        unify = ShapeUpgrade_UnifySameDomain(fused, True, True, False)
        unify.Build()
        merged = unify.Shape()
        if not merged.IsNull():
            fused = merged
    except Exception as exc:                       # never fatal - see _stackup_board
        log(f"warning: could not merge the folded board's coplanar faces ({exc})")
    return fused
