"""The numbers the fold is built with, and the two type aliases.

Each constant carries the reason for its value; plan B7 will bring the ones
still living as bare literals in the other modules here.
"""

from __future__ import annotations

from typing import Callable

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
# The numbers that were bare literals until plan B7 (round 72). Each one is a
# tolerance or a sampling density somebody once chose; the reason is the line
# that used to sit beside it.
# --------------------------------------------------------------------------- #

# flat_frame: how far outside the flat stack an un-folded point may land and
# still count as "back in the board". A wrong region's inverse throws a point
# tens of millimetres out; this only has to absorb tolerance.
FLAT_FRAME_MARGIN = 1.0

# _cut_into_pieces: how far past the outline, along the bend line, the band a
# strip is cut with reaches - measured from the board, not from the origin.
BAND_REACH = 10.0

# _seam_gap: how close to a panel's boundary a strip's edge point may sit and
# still be judged against that panel. Half planes had EPS for this; polygons
# need a real allowance, since the point is ON the shared edge by construction.
SEAM_TOL = 0.05

# plan_fold: a seam that comes apart by more than this is reported. The
# tear it exists to catch was 23.8 mm; a micron is tolerance.
SEAM_WARN = 1.0e-6

# plan_fold: the fraction of the board that may be claimed by two pieces
# before the plan says so. It should be zero; 2% absorbs the sampling grid.
DOUBLE_CLAIM_WARN = 0.02

# _double_claimed: the sampling grid, in mm. Fine enough to catch a whole
# arm claimed twice, which is what the check is for, and cheap.
CLAIM_GRID = 2.0

# _piece_face: a fragment smaller than this fraction of the piece it was
# repaired out of is an artefact of the arithmetic, not board, and is dropped
# - a 0.085 mm2 chip once took a 173 mm3 dielectric down with it.
SLIVER_RATIO = 0.01

# _face_poly: points sampled per curved edge when a face is read as a polygon
# that only ever classifies, never becomes geometry. A few microns on a
# board's radii.
FACE_POLY_PER_CURVE = 12

# _chain_at: how far a drawn bend area may differ from angle x inner radius
# before the log says the design is telling us something - an absolute floor
# and a relative one, whichever is larger.
DRAWN_AREA_TOL_ABS = 0.05
DRAWN_AREA_TOL_REL = 0.1

# _walk: the least a faceted slice overlaps its neighbour, in mm, so that
# rotated slices interpenetrate instead of touching along a line.
SLICE_OVERLAP_MIN = 0.02

# _map_strip: how a curved flat edge is sampled before it is fitted as a 2-D
# spline on the cylinder - the probe that estimates its length, then one
# point per SAMPLE_STEP mm, never fewer than SAMPLE_MIN nor more than
# SAMPLE_MAX. The surface stays exact; only the trimming curve is fitted.
LENGTH_PROBE_STEPS = 8
SAMPLE_STEP = 0.05
SAMPLE_MIN = 8
SAMPLE_MAX = 200

# _map_strip: the sewing tolerance for the walls and the two cylinder faces.
SEW_TOL = 1.0e-6
