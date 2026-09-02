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

import re


# The flat-polygon helpers moved to contour.py (round 72, plan A1); the tests
# and the window still import them from here, so they are re-exported.
from ..contour import (  # noqa: F401 - re-exported
    build_contour, clip_halfplane, contour_points, point_in_polygon,
    point_on_polygon, polygon_area,
)
# The package (round 72, plans B1-B6a): what a bend is, the pieces of the
# board, the cutters, both strip constructions, the plan and how it is built
# and applied, the numbers. Nothing is defined here any more; the
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
from .cut import _crosses, _cut_to_region, _plane_face, _slab  # noqa: F401
from .strip_revolve import (  # noqa: F401 - re-exported
    PRISM_SPAN_TOLERANCE, PRISM_TOLERANCE, _prism_of, _revolve_strip, _spans_alike,
)
from .strip_wrap import MAP_VOLUME_TOLERANCE, _map_strip  # noqa: F401
from .apply import _fuse_all, apply_plan  # noqa: F401
from .plan import (  # noqa: F401 - re-exported
    FoldPlan, _anchor_point, _anchor_signs, _double_claimed, _overlap_note,
    _seam_gap, plan_fold, plan_from_json,
)

