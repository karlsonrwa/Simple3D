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
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakePrism
from OCP.Bnd import Bnd_Box
from OCP.TopAbs import TopAbs_ShapeEnum
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Iterator, TopoDS_Shape
from OCP.TopTools import TopTools_ListOfShape
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

# The flat-polygon helpers moved to contour.py (round 72, plan A1); the tests
# and the window still import them from here, so they are re-exported.
from ..contour import (  # noqa: F401 - re-exported
    build_contour, clip_halfplane, contour_points, point_in_polygon,
    point_on_polygon, polygon_area,
)
# The package, so far (round 72, plans B1-B2): what a bend is, the pieces of
# the board, the numbers. Everything below still waits for plans B3-B6; the
# names are re-exported here so `from stepbuilder.bend import X` holds.
from .constants import (  # noqa: F401 - re-exported
    DEFAULT_ANCHOR, DEFAULT_NEUTRAL_FACTOR, DEFAULT_SLICE_ANGLE, EPS, MIN_ANGLE,
    LogFn, _noop_log,
)
from .info import (  # noqa: F401 - re-exported
    Bend, bend_from_dict, bends_from_json, info_length, info_number,
    parse_bend_info,
)
from .regions import (  # noqa: F401 - re-exported
    _Piece, _Region, _Strip, _bbox, _extent, _is_empty, _slice_trsf,
)
from .pieces import (  # noqa: F401 - re-exported
    _band_face, _closest_point, _cut_into_pieces, _face_poly, _faces_of,
    _piece_face, _polygon_face, _touching,
)

# --------------------------------------------------------------------------- #
# the plan
# --------------------------------------------------------------------------- #

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
    # The two faces of the FLAT board. flat_frame uses them to reject a region
    # whose inverse throws the point out of the stack - see there.
    flat_top: float | None = None
    flat_bottom: float | None = None
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
            if region.holds(x, y):
                return region.trsf
        return gp_Trsf()

    def region_at(self, x: float, y: float) -> str:
        for region in self.regions:
            if region.holds(x, y):
                return region.label
        return "?"

    def flat_frame(self, point: gp_Pnt) -> gp_Trsf | None:
        """The transform that puts a FOLDED point back where it started.

        Used to ask a question about a face of the folded board in the frame it
        was built in - "is this wall vertical" being the one that matters, since
        after a 90 degree fold half the board's flat faces are vertical and half
        its walls are not.

        The region is found by trying each one's inverse and keeping the one
        whose flat footprint the result lands in. Two things make that answer
        the right one rather than merely a possible one:

        - **the un-folded point has to land back IN the board**, in z. A wrong
          region's inverse is a rotation about a different axis, and it throws
          the point clean out of the stack: the LCD panel's top face on
          Cadence's demo board came back at z = 31.08 through a slice of
          BEND_3, on a board that is 1.63 mm thick. Without this test that
          slice answered first, the panel's flat face was judged in a frame
          where it stands vertical, and the whole 2398 mm2 of it was painted
          with the BOARD EDGE colour;
        - **panels are tried before slices.** A slice is a facet of a bend and
          is only ever real geometry when a bend could not be built exactly;
          it stays in `regions` to answer "where does this point end up", and
          it must not outrank the panel a face actually belongs to.
        """
        margin = 1.0
        if self.flat_top is not None and self.flat_bottom is not None:
            low = min(self.flat_top, self.flat_bottom) - margin
            high = max(self.flat_top, self.flat_bottom) + margin
        else:
            low = high = None

        for region in sorted(self.regions, key=lambda r: r.kind != "panel"):
            back = region.trsf.Inverted()
            flat = point.Transformed(back)
            if low is not None and not (low <= flat.Z() <= high):
                continue
            if region.holds(flat.X(), flat.Y()):
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

        # A COMPOUND of many small independent solids - the printed legend,
        # thousands of glyphs and strokes - is folded one piece at a time.
        # Folded whole it is a boolean between a 45000-face compound and every
        # region in turn, and none of the cheap rejections can fire because the
        # compound's own bounding box covers the entire board. Piece by piece,
        # a glyph is a millimetre across: it lands in one region, is rejected by
        # every other on its bounding box, and needs no boolean at all unless it
        # straddles a bend. Only for fuse=False, which is what the legend uses -
        # a board body is one solid and has nothing to gain here.
        if not fuse:
            children = []
            it = TopoDS_Iterator(shape)
            while it.More():
                children.append(it.Value())
                it.Next()
            if len(children) > 1:
                out = []
                for child in children:
                    done = self.apply(child, fuse=False, note=False, log=log)
                    if done is not None and not _is_empty(done):
                        out.append(done)
                if not out:
                    log("warning: folding cut the shape away entirely; left flat")
                    return shape
                builder = BRep_Builder()
                compound = TopoDS_Compound()
                builder.MakeCompound(compound)
                for piece in out:
                    builder.Add(compound, piece)
                return compound

        pieces: list[TopoDS_Shape] = []
        for region in self.regions:
            if region.kind != "panel":
                continue
            piece = _cut_to_region(shape, region.bounds, box, region)
            if piece is None:
                continue
            if region.moved:
                piece = BRepBuilderAPI_Transform(piece, region.trsf, True).Shape()
            pieces.append(piece)

        for strip in self.strips:
            flat = _cut_to_region(shape, strip.bounds, box, strip)
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
                    piece = _cut_to_region(shape, region.bounds, box, region)
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

        fused = _fuse_all(pieces, log)
        # A fuse that hands back nothing is how a whole layer disappears without
        # a word: one degenerate sliver among the pieces, and 173 mm3 of a flex
        # arm's dielectric came back as a null shape. The pieces themselves are
        # sound - they were cut and bent one at a time - so keep them as a
        # compound rather than lose the part, and say what happened.
        if fused is None or _is_empty(fused):
            log(f"warning: the {len(pieces)} folded piece(s) of this shape "
                f"could not be fused into one solid; keeping them as separate "
                f"bodies so the material is not lost")
            builder = BRep_Builder()
            compound = TopoDS_Compound()
            builder.MakeCompound(compound)
            for piece in pieces:
                builder.Add(compound, piece)
            return compound
        return fused

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
              outline_curves: list | None = None,
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
        the flat board outline as a polygon - for sizing, classifying points and
        for choosing the held piece when there is no anchor.
    outline_curves:
        the same outline as the intermediate writes it, arcs and all. When it is
        given the board is CUT with it, so a rounded edge stays round; without
        it the flattened polygon is cut instead, which chords every arc.
    """
    plan = FoldPlan(slice_angle=slice_angle,
                    flat_top=board_top_z, flat_bottom=board_bottom_z)
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
    # Built for a GIVEN neutral factor rather than only for the chosen one, so
    # the same arithmetic can answer "how far could k go on this board" without
    # a second, subtly different copy of it. See _neutral_ceiling below.
    # How much flat material an arc consumes: its length along the NEUTRAL axis,
    # because that is the length a bend preserves.
    #
    # **Allegro's own bend area is drawn at the INNER radius**, which is a
    # different number and not a bend allowance. Measured on the real board: the
    # BEND_AREA shape is 1.2337 mm across for 28.26 deg and R = 2.5, and 28.26
    # deg x 2.5 = 1.2331 - the inner arc to four decimals, with no thickness term
    # in it at all. It is the region to keep clear of vias and packages, not the
    # material budget. So the drawn area is used as a CHECK: if it is not the
    # inner arc either, the design is saying something neither the parameters nor
    # this reading explain, and that is worth a line in the log.
    def chain_at(factor: float, notes: list | None = None) -> list:
        out = []
        for bend, (nx, ny) in ordered:
            px, py = bend.midpoint
            top, bottom = (stack_at(px, py) if stack_at
                           else (board_top_z, board_bottom_z))
            thickness = abs(top - bottom)
            theta = math.radians(bend.angle)
            developed = (bend.radius + factor * thickness) * theta
            drawn = bend.radius * theta
            if notes is not None and bend.width and bend.width > EPS and drawn > EPS:
                if abs(bend.width - drawn) > max(0.05, 0.1 * drawn):
                    notes.append(
                        f"  note: {bend.name}'s bend area is {bend.width:.3f} mm "
                        f"across, where its radius and angle draw {drawn:.3f} mm; "
                        f"folding {developed:.3f} mm of material either way")
            out.append((bend, (nx, ny), (px, py), developed / 2.0, top, bottom))
        return out

    chain = chain_at(neutral_factor, plan.notes)

    def _strips_overlap(a, b) -> bool:
        """Do the two bend strips claim any of the same material?

        A strip is a RECTANGLE: as wide as the developed length across the bend
        line, as long as the bend line itself. Comparing them by a single
        projection along one normal - which is what this used to do - answers a
        question about two infinite bands instead, and two bends that share no
        material at all can then look like they overlap. On Cadence's demo
        board BEND_1 and BEND_2 are PERPENDICULAR, at the corner of the FLEXI
        arm, 33.9 mm between centres and disjoint by any measure; projected on
        BEND_1's normal alone they read as 9.19 mm apart with strips 8.3 and
        9.9 mm wide, so one of the two real bends was dropped as unreadable.

        Separating-axis test over the four edge directions. Rectangles that
        merely TOUCH count as separated, which is the ring case the 1-D test
        was careful about: a flex rolled closed is two 180 degree bends whose
        areas share a line, and there is nothing ambiguous about that.
        """
        (anx, any_), (apx, apy), ahalf = a[1], a[2], a[3]
        (bnx, bny), (bpx, bpy), bhalf = b[1], b[2], b[3]
        atx, aty = -any_, anx
        btx, bty = -bny, bnx
        alen, blen = a[0].length / 2.0, b[0].length / 2.0
        dx, dy = bpx - apx, bpy - apy

        for ax, ay in ((anx, any_), (atx, aty), (bnx, bny), (btx, bty)):
            reach = (ahalf * abs(ax * anx + ay * any_)
                     + alen * abs(ax * atx + ay * aty)
                     + bhalf * abs(ax * bnx + ay * bny)
                     + blen * abs(ax * btx + ay * bty))
            if abs(ax * dx + ay * dy) > reach - EPS:
                return False
        return True

    # -- bends that cross each other cannot be read ------------------------- #
    # Two bends are related in exactly one of three ways, and the third is
    # fatal: one lies wholly beyond the other (a chain), they lie on opposite
    # sides of the held panel (two arms - the real board has exactly this, a
    # tail bent up at one end and another bent down at the other), or their
    # strips overlap as seen from the held side, which says nothing about what
    # moves with what.
    def readable(items, notes: list | None = None) -> list:
        out = []
        for item in items:
            px, py = item[2]
            clash = None
            for prev in out:
                (pnx, pny), (ppx, ppy) = prev[1], prev[2]
                # Only material claimed by BOTH is unreadable - see
                # _strips_overlap for why this is a question about two
                # rectangles and not about two bands. The distance goes to the
                # note, which reports how far apart the two lines are along the
                # earlier bend's normal.
                if _strips_overlap(prev, item):
                    clash = (prev, abs(pnx * (px - ppx) + pny * (py - ppy)))
                    break
            if clash:
                if notes is not None:
                    notes.extend(_overlap_note(item, *clash, neutral_factor))
                continue
            out.append(item)
        return out

    kept = readable(chain, plan.notes)

    if not kept:
        return plan

    # -- cut the flat board into pieces -------------------------------------- #
    # The model, and the reason it is not a set of half-planes: see
    # _cut_into_pieces. A panel is a CONNECTED piece of the outline with the
    # bend strips taken out of it, and which piece a point is on is the only
    # question that has a right answer on a board whose arms leave in several
    # directions.
    # Tee the decomposition's log: the caller sees it as it happens, and the
    # ceiling search below needs to know whether anything had to be repaired.
    marks: list[str] = []

    def cut_log(message: str) -> None:
        marks.append(message)
        log(message)

    pieces = (_cut_into_pieces(outline, kept, cut_log, outline_curves)
              if outline else None)
    if pieces is None:
        plan.notes.append(
            "  warning: the outline could not be cut into pieces, so there is "
            "nothing to say which arm carries which. The board is left flat.")
        return FoldPlan(slice_angle=slice_angle)
    panels, strip_pieces = pieces

    plan.chain = [(b, n, p, h) for b, n, p, h, _, _ in kept]

    # Everything the board is now made of, as one list of pieces, and which of
    # them touch. Panels first, then strips - a strip's neighbour can be ANOTHER
    # STRIP, which is what a flex rolled into a ring is: two 180 degree bend
    # areas that meet along a line, with no flat panel between them.
    npanel = len(panels)
    parts = [face for _, face in panels] + [face for _, face in strip_pieces]
    rings = [rs for rs, _ in panels] + [rs for rs, _ in strip_pieces]
    # One outline per piece for the measurements below - area, centroid, which
    # side of a strip - and it is the largest fragment. Containment uses them
    # all, through _Region.holds.
    polys = [rs[0] for rs in rings]
    neighbours = [[] for _ in parts]
    for a in range(len(parts)):
        for b in range(a + 1, len(parts)):
            if a < npanel and b < npanel:
                continue              # two panels never touch: they would be one
            if _touching(parts[a], parts[b]):
                neighbours[a].append(b)
                neighbours[b].append(a)

    # -- which piece is held ------------------------------------------------- #
    # The anchor names a POINT, and the piece it lands on is held. It does not
    # have to be inside the board - the origin often sits on a corner or just
    # off it - so a point outside every piece takes the nearest one.
    def piece_at(point) -> int:
        for i, (rs, _) in enumerate(panels):
            if any(point_in_polygon(point, r) for r in rs):
                return i
        return min(range(len(panels)),
                   key=lambda i: min(math.hypot(vx - point[0], vy - point[1])
                                     for r in panels[i][0] for vx, vy in r))

    if anchor is not None:
        held = piece_at(anchor)
    else:
        held = max(range(len(panels)),
                   key=lambda i: sum(abs(polygon_area(r)) for r in panels[i][0]))

    def side_of(part: int, s: int) -> float:
        """Which way piece *part* lies from strip s: -1 before it, +1 beyond.

        Asked AT THE SEAM, not of the piece as a whole. A strip's band is
        infinite across its own direction, so a big piece can have material on
        both sides of it and still touch it along one edge only: the main board
        of Cadence's demo reaches past BEND_1's band on both sides, and judging
        it by its extent - or by its nearest vertex - put the strip's near edge
        against the FAR panel. The seam then came apart by 23.8 mm and the arm
        floated off the board.

        The two pieces touch, so the closest point between them is ON the shared
        edge, and that edge is one of the strip's two long sides.
        """
        (nx, ny), (px, py), half = kept[s][1], kept[s][2], kept[s][3]
        base = nx * px + ny * py
        seam = _closest_point(parts[part], parts[npanel + s])
        if seam is not None:
            v = nx * seam[0] + ny * seam[1]
            return -1.0 if abs(v - (base - half)) <= abs(v - (base + half)) else 1.0
        # Not touching at all - should not happen, since the walk only reaches a
        # strip from a piece beside it. Fall back on the extent.
        values = [nx * vx + ny * vy for vx, vy in polys[part]]
        return -1.0 if max(values) <= base + half + EPS else 1.0

    # -- walk out from the held piece ---------------------------------------- #
    # Every strip is reached from the side that is already placed, so a bend
    # folds away from whatever holds it - which is what the anchor means, asked
    # per bend instead of once globally. There is no ordering to get right and
    # no cycle to fall into: a piece is placed when it is reached, and the walk
    # ends when nothing new is. Crossing a strip applies its bend; a panel on
    # the far side of one simply inherits the angle the strip finished at.
    carried: dict[int, gp_Trsf] = {held: gp_Trsf()}
    labels = {held: "held"}
    queue = [held]
    while queue:
        here = queue.pop(0)
        for other in neighbours[here]:
            if other in carried:
                continue
            if other < npanel:
                # a flat piece beyond a strip already crossed
                carried[other] = carried[here]
                labels[other] = labels.get(here, "held")
                queue.append(other)
                continue

            s = other - npanel
            bend, (nx, ny), (px, py), half, top, bottom = kept[s]
            base = nx * px + ny * py
            if side_of(here, s) > 0:           # the held side is the far one:
                nx, ny = -nx, -ny              # turn the bend around
                base = -base
            lo, hi = base - half, base + half
            base_trsf = carried[here]

            steps = max(1, int(math.ceil(bend.angle / max(0.5, slice_angle))))
            step = 2 * half / steps
            sign = 1.0 if bend.inner_side == "top" else -1.0
            axis_z = (top + bend.radius) if sign > 0 else (bottom - bend.radius)
            theta = math.radians(bend.angle)
            # Overlap so consecutive slices interpenetrate instead of touching
            # along a line: the wedge a rotated slice opens on the outside of
            # the bend is about half the thickness times the slice angle.
            overlap = max(0.02, abs(top - bottom) * theta / steps)

            facets = []
            for j in range(steps):
                hinge = lo + j * step
                # The angle is interpolated across the strip rather than
                # derived from the neutral radius, so that the last slice
                # always meets the finished angle exactly whatever set the
                # strip width.
                phi = theta * (hinge - lo) / (2 * half) if half > EPS else 0.0
                facets.append(_Region(
                    label=f"{bend.name} slice {j + 1}/{steps}",
                    bounds=[(nx, ny, hinge - overlap, hinge + step + overlap)],
                    poly=strip_pieces[s][0][0], polys=strip_pieces[s][0],
                    face=strip_pieces[s][1],
                    trsf=_slice_trsf(base_trsf, nx, ny, lo, hinge, axis_z,
                                     sign * phi),
                    kind="slice"))

            # The strip is cut as ONE piece and bent exactly where it can be;
            # the facets are the fallback, and they stay in `regions` as well
            # because that list answers "where does a point at (x, y) end up".
            plan.strips.append(_Strip(
                bend=bend, bounds=[(nx, ny, lo, hi)], normal=(nx, ny),
                poly=strip_pieces[s][0][0], polys=strip_pieces[s][0],
                face=strip_pieces[s][1],
                lo=lo, hi=hi, axis_z=axis_z, turn=sign * theta,
                carried=base_trsf, facets=facets))
            plan.regions.extend(facets)

            # everything past the bend rides on the finished angle
            carried[other] = _slice_trsf(base_trsf, nx, ny, lo, hi, axis_z,
                                         sign * theta)
            labels[other] = f"panel after {bend.name}"
            queue.append(other)

    # In the order they were folded, which is outwards from the held piece.
    plan.bends = [strip.bend for strip in plan.strips]

    # A piece nothing reached is one the bend lines cut off from the rest of the
    # board - an island. Nothing says what carries it, so it stays where it is
    # and the log says so rather than leaving it to be noticed in the model.
    for i in range(len(panels)):
        if i not in carried:
            carried[i] = gp_Trsf()
            labels[i] = f"island {i}"
            plan.notes.append(
                f"  note: a piece of the board around "
                f"{panels[i][0][0][0][0]:.1f}, {panels[i][0][0][0][1]:.1f} is not "
                f"joined to the rest through any bend area; left where it is")
    for s, (bend, _, _, _, _, _) in enumerate(kept):
        if npanel + s not in carried:
            plan.notes.append(
                f"  note: {bend.name} is not reachable from the held piece, so "
                f"nothing says which way it folds; left flat")

    for i, (rs, face) in enumerate(panels):
        plan.regions.append(_Region(
            label=labels[i], bounds=[], poly=rs[0], polys=rs, face=face,
            trsf=carried[i], moved=(i != held)))

    # -- how much neutral factor this board can actually take ----------------- #
    # Allegro lays its bend areas out at k = 0 - the drawn area IS the inner arc
    # - so at any k above that every strip is wider than what the designer
    # allowed, by angle x k x thickness. On a board with room this never shows.
    # On a tight one the strips reach each other, and the answer is a NUMBER the
    # user can act on rather than a repair they have to notice: the largest k
    # this particular board takes cleanly.
    #
    # Only computed when there IS trouble, because it costs a dozen trial cuts.
    refused = len(chain) - len(kept)
    if (refused or any("pinch" in m for m in marks)) and neutral_factor > 0.0:
        def trouble_at(factor: float) -> bool:
            trial = chain_at(factor)
            good = readable(trial)
            if len(good) < len(trial):
                return True
            seen: list[str] = []
            return (_cut_into_pieces(outline, good, seen.append,
                                     outline_curves) is None
                    or any("pinch" in m for m in seen))

        low, high = 0.0, neutral_factor
        for _ in range(10):
            middle = (low + high) / 2.0
            if trouble_at(middle):
                high = middle
            else:
                low = middle
        plan.notes.append(
            f"  note: this board's bend areas are laid out at k = 0, as Allegro "
            f"draws them, and the tightest pair on it takes foldNeutral up to "
            f"{low:.2f}. At the current {neutral_factor:.2f} the strips reach "
            f"each other"
            + (f" and {refused} bend(s) had to be left flat" if refused
               else " and the piece between them had to be repaired")
            + f". foldNeutral 0 reproduces the drawing exactly; "
            f"{low:.2f} is as physical as this layout allows.")

    # The invariant, checked rather than assumed: the pieces come out of one
    # boolean cut, so every point of the board should belong to exactly one of
    # them. It held on every board tried, and it is what the half-plane model
    # could not do - a quarter of Cadence's demo board used to be claimed twice
    # and built twice. Cheap next to the fold itself, and silence here would
    # mean a plausible wrong model handed back with nothing said.
    doubled = _double_claimed(plan, outline)
    if doubled > 0.02:
        plan.notes.append(
            f"  warning: {doubled * 100:.0f}% of this board is claimed by more "
            f"than one piece, so that material will be built more than once. "
            f"This should not happen - please report the board. Exporting flat "
            f"(Fold flex bends off) avoids it.")

    # The other invariant, and the one that showed: a fold is CONTINUOUS. Both
    # edges of every strip have to land exactly where the piece on that side
    # puts them. Getting a strip's two sides the wrong way round tears the arm
    # off the board - 23.8 mm of daylight on Cadence's demo board - and the
    # model still builds and still measures the right volume, so nothing else
    # here would have caught it.
    gap = _seam_gap(plan)
    if gap > 1.0e-6:
        plan.notes.append(
            f"  warning: the fold does not join up - a seam comes apart by "
            f"{gap:.3f} mm, so a piece of the board will float away from the "
            f"rest. This should not happen; please report the board.")

    plan.notes.insert(0, (
        f"  held: the piece containing the anchor at "
        f"{anchor[0]:.3f}, {anchor[1]:.3f}" if anchor is not None
        else "  held: the largest piece the bend lines leave (no anchor set)"))
    plan.notes.insert(0, f"Folding {len(plan.bends)} bend(s):")
    return plan


def _seam_gap(plan: FoldPlan) -> float:
    """The worst distance by which the fold fails to join up, in mm.

    Every strip meets a piece along each of its two long edges. Placed by the
    strip and placed by that piece, a point on the shared edge must land in the
    same spot - that is what makes a fold a fold rather than an explosion.
    Two points per strip, so it costs nothing.
    """
    worst = 0.0
    panels = [r for r in plan.regions if r.kind == "panel" and r.poly]
    for strip in plan.strips:
        if not strip.poly:
            continue
        nx, ny = strip.normal
        cx = sum(p[0] for p in strip.poly) / len(strip.poly)
        cy = sum(p[1] for p in strip.poly) / len(strip.poly)
        base = nx * cx + ny * cy
        ends = ((strip.lo, strip.carried),
                (strip.hi, _slice_trsf(strip.carried, nx, ny, strip.lo,
                                       strip.hi, strip.axis_z, strip.turn)))
        for value, trsf in ends:
            ex = cx + nx * (value - base)
            ey = cy + ny * (value - base)
            mine = gp_Pnt(ex, ey, 0.0).Transformed(trsf)
            near = None
            for region in panels:
                if not (point_in_polygon((ex, ey), region.poly)
                        or point_on_polygon((ex, ey), region.poly, 0.05)):
                    continue
                theirs = gp_Pnt(ex, ey, 0.0).Transformed(region.trsf)
                d = mine.Distance(theirs)
                near = d if near is None else min(near, d)
            if near is not None:
                worst = max(worst, near)
    return worst


def _double_claimed(plan: FoldPlan, outline: list[tuple[float, float]],
                    step: float = 2.0) -> float:
    """Fraction of the board area that more than one fold region claims.

    Sampled on a grid rather than computed exactly: the answer is wanted as a
    warning threshold, and the regions are half-plane intersections whose exact
    pairwise areas would cost far more than the fold itself. 2 mm is fine
    enough to catch a whole arm being claimed twice, which is what this is for,
    and cheap - a few thousand points against a dozen regions.
    """
    if not outline or not plan.regions:
        return 0.0

    claimants = [r for r in plan.regions if r.kind == "panel"]
    claimants += list(plan.strips)
    if len(claimants) < 2:
        return 0.0

    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    on_board = doubled = 0
    y = min(ys)
    while y <= max(ys):
        x = min(xs)
        while x <= max(xs):
            if point_in_polygon((x, y), outline):
                on_board += 1
                seen = 0
                for claimant in claimants:
                    if claimant.holds(x, y):
                        seen += 1
                        if seen > 1:
                            doubled += 1
                            break
            x += step
        y += step
    return doubled / on_board if on_board else 0.0


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

        # Bound to the name below rather than defined as `stack_at` directly:
        # shadowing the None above reads as a redefinition to every linter, and
        # the reader has to check which one wins.
        def _stack_at(x: float, y: float, _polys=polys, _thin=thinnest):
            for _, poly, level in _polys:
                if poly and point_in_polygon((x, y), poly):
                    return level
            return _thin

        stack_at = _stack_at

    # The design's own anchor, if a future Allegro ever writes one: it beats the
    # setting, because it is what the designer marked on the board.
    from_design = data.get("anchor")
    if (isinstance(from_design, (list, tuple)) and len(from_design) >= 2
            and all(isinstance(v, (int, float)) for v in from_design[:2])):
        anchor = (float(from_design[0]), float(from_design[1]))
        log(f"Fold anchor {anchor[0]:.3f}, {anchor[1]:.3f} taken from the design")

    return plan_fold(bends, outline, board_top_z, board_bottom_z,
                     stack_at=stack_at, slice_angle=slice_angle,
                     anchor=anchor, neutral_factor=neutral_factor,
                     outline_curves=(contours[0] if contours else None), log=log)


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


def _cut_to_region(shape: TopoDS_Shape,
                   bounds: list[tuple[float, float, float, float]],
                   box, piece=None) -> TopoDS_Shape | None:
    """The part of *shape* inside *face* and every one of *bounds*, or None.

    Each bound that the shape already satisfies is skipped rather than turned
    into a boolean - on a board with one bend that leaves the far panel and the
    held panel each costing a single cut, and the silkscreen on either of them
    costing none at all.

    *piece* is the region or strip, whose `face` is the part of the flat board
    it covers - what tells one arm from another. Its bounding box is tried
    FIRST, because it rejects outright and costs nothing: that is what makes
    folding a legend one glyph at a time affordable.
    """
    pbox = piece.face_box() if piece is not None else None
    if pbox is not None:
        xmin, ymin, _, xmax, ymax, _ = pbox
        sxmin, symin, _, sxmax, symax, _ = box
        if (sxmax < xmin - EPS or sxmin > xmax + EPS
                or symax < ymin - EPS or symin > ymax + EPS):
            return None

    out = shape
    for nx, ny, lo, hi in bounds:
        low, high = _extent(box, nx, ny)
        if high < lo - EPS or low > hi + EPS:
            return None
        if low >= lo - EPS and high <= hi + EPS:
            continue
        cutter = _slab(nx, ny, lo, hi, box)
        common = BRepAlgoAPI_Common(out, cutter)
        if not common.IsDone():
            return None
        out = common.Shape()
        if _is_empty(out):
            return None

    if piece is not None and piece.face is not None:
        # Wholly inside the piece? Then there is nothing to cut. A glyph is a
        # millimetre across and a panel is most of the board, so this is the
        # answer for nearly every polygon of a legend.
        sxmin, symin, _, sxmax, symax, _ = box
        corners = ((sxmin, symin), (sxmax, symin), (sxmax, symax), (sxmin, symax))
        whole = (piece.poly is not None
                 and all(point_in_polygon(c, piece.poly) for c in corners)
                 and not _crosses(piece.poly, sxmin, symin, sxmax, symax))
        if not whole:
            zmin, zmax = box[2], box[5]
            prism = BRepPrimAPI_MakePrism(
                piece.face, gp_Vec(0, 0, (zmax - zmin) + 2.0)).Shape()
            lift = gp_Trsf()
            lift.SetTranslation(gp_Vec(0, 0, zmin - 1.0))
            prism = BRepBuilderAPI_Transform(prism, lift, True).Shape()
            common = BRepAlgoAPI_Common(out, prism)
            if not common.IsDone():
                return None
            out = common.Shape()
            if _is_empty(out):
                return None

    return None if _is_empty(out) else out


def _crosses(poly, xmin: float, ymin: float, xmax: float, ymax: float) -> bool:
    """Does any edge of *poly* pass through the box?

    All four corners of a box can be inside a polygon while an edge still cuts
    across it - a piece with a notch in it. Cheap, and it has to be right: the
    answer decides whether a boolean is skipped.
    """
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (max(x0, x1) < xmin or min(x0, x1) > xmax
                or max(y0, y1) < ymin or min(y0, y1) > ymax):
            continue
        return True
    return False


def _slab(nx: float, ny: float, lo: float, hi: float, box) -> TopoDS_Shape:
    """A box covering everything in *box* between `n.p = lo` and `n.p = hi`.

    Sized and placed from the SHAPE's own extent, in both directions. It used to
    run half the board's diagonal either side of the point `n * lo` - the foot
    of the near plane, measured from the ORIGIN - which silently assumes the
    board sits near the origin. Cadence's demo board does not: BEND_1's band has
    its foot at (16.9, -17.2) while the arm it cuts is at (140, 90), 163 mm away
    along the bend line against a 102 mm half-span, so the slab missed the board
    entirely and that bend was quietly built out of nothing. Every board drawn
    away from the origin loses bends this way, the more so the further out and
    the more diagonal the bend.
    """
    zmin, zmax = box[2], box[5]
    tx, ty = -ny, nx                       # along the bend line
    tlow, thigh = _extent(box, tx, ty)
    tlow -= 1.0
    thigh += 1.0

    low, high = _extent(box, nx, ny)
    lo = max(lo, low - 1.0) if lo != -math.inf else low - 1.0
    hi = min(hi, high + 1.0) if hi != math.inf else high + 1.0

    # frame with X across the bend, Y along it, Z up
    origin = gp_Pnt(nx * lo + tx * tlow, ny * lo + ty * tlow, zmin - 1.0)
    frame = gp_Ax2(origin, gp_Dir(0, 0, 1), gp_Dir(nx, ny, 0))
    return BRepPrimAPI_MakeBox(frame, hi - lo, thigh - tlow,
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
