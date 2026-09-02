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
