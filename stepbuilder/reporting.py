"""How the build reports: a log line at a time, and a progress fraction.

`core.generate` takes both as callbacks so it can be driven from the window,
from the CLI and from the tests without printing anything itself. They live
here, apart from core, because every stage module the plans split out of it
needs the type and the no-op default, and none of them may import core for
it (round 72, plan A3).
"""

from __future__ import annotations

from typing import Callable

# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #

LogFn = Callable[[str], None]
# (value, total, what is happening). The label is optional so an older caller
# passing a two-argument function still works.
ProgressFn = Callable[..., None]


def _noop_log(message: str) -> None:
    pass


def _noop_progress(current: int, total: int, label: str = "") -> None:
    pass
