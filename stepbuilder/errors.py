"""The one exception the package raises.

Every condition the original C++ tool handled with a message and `cin.get()`
is a StepBuilderError here, and the window, the CLI and the tests catch this
one class. It has a module of its own so that contour.py, bend.py and core.py
can all raise it without importing one another (plan A1).
"""

from __future__ import annotations


class StepBuilderError(Exception):
    """Raised for any condition the original code handled with cin.get()."""
