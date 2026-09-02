"""The plan: everything needed to fold one board, and nothing about how it
was built - plus, from plan B6 on, how it is built.

A `FoldPlan` answers where a flat point ends up (`transform_at`), which
region it is in, how to get a folded point back to the flat frame
(`flat_frame` - with the two tests that make the answer the right one),
and whether a point lies in a bend area; `apply` folds a shape by it, in
apply.py. `summary` and `describe` are what the log prints.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Pnt, gp_Trsf

from .apply import apply_plan
from .constants import DEFAULT_SLICE_ANGLE, LogFn, _noop_log
from .info import Bend
from .regions import _Region, _Strip


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
