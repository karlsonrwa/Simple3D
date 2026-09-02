"""The plan: everything needed to fold one board, and how it is built.

A `FoldPlan` answers where a flat point ends up (`transform_at`), which
region it is in, how to get a folded point back to the flat frame
(`flat_frame` - with the two tests that make the answer the right one),
and whether a point lies in a bend area; `apply` folds a shape by it, in
apply.py. `summary` and `describe` are what the log prints.
"""

from __future__ import annotations

import math
from typing import Callable
from dataclasses import dataclass, field

from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Pnt, gp_Trsf

from ..contour import clip_halfplane, contour_points, point_in_polygon, point_on_polygon, polygon_area
from .apply import apply_plan
from .constants import DEFAULT_ANCHOR, DEFAULT_NEUTRAL_FACTOR, DEFAULT_SLICE_ANGLE, EPS, LogFn, _noop_log
from .info import Bend, bends_from_json
from .pieces import _closest_point, _cut_into_pieces, _touching
from .regions import _Region, _slice_trsf, _Strip


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
        """Fold one shape - apply.apply_plan, which says how."""
        return apply_plan(self, shape, fuse=fuse, note=note, log=log)

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
