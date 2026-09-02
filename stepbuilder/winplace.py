"""Where a window opens, and where it was: placement remembered across runs,
multi-monitor aware, for any `tk.Tk`.

Round 73, plan C3: the placement methods of StepBuilderApp as functions
that take the window. The window keeps thin methods that call these, and
tests/test_geom.py still drives it through those.
"""

from __future__ import annotations

import re
from typing import Callable

# What a first run opens at. The natural request is wider than this; the
# groups simply start narrower and the silk column, which is the one with
# weight, gives the room back as soon as the window is widened.
FIRST_RUN_WIDTH = 908

# How much of a remembered window must still be on some screen for the
# position to count as usable: enough to see and grab.
MIN_VISIBLE_WIDTH = 120
MIN_VISIBLE_HEIGHT = 40

# A window this close to the screen's own size is maximized in all but name,
# and its rect must not be remembered as the "normal" one.
NEAR_SCREEN_WIDTH_SLACK = 20
NEAR_SCREEN_HEIGHT_SLACK = 80

# Tk writes a negative coordinate as "+-1920", so the sign sits after the
# plus. A bare "-1920" in a geometry string means something else entirely (an
# offset from the right edge), which is why this matches the "+" form only.
_GEOMETRY = re.compile(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$")


def virtual_screen(root) -> tuple[int, int, int, int]:
    """(x, y, w, h) covering EVERY monitor, not just the primary one.

    Tk's winfo_screenwidth/height describe the primary display only, so a
    window legitimately sitting on a second monitor looks off-screen by
    those numbers - which is exactly the case this feature exists for.
    Windows reports the whole virtual desktop through GetSystemMetrics
    (SM_[XY]VIRTUALSCREEN / SM_C[XY]VIRTUALSCREEN), and a monitor left of
    the primary gives a negative origin.

    Falls back to the primary display if that call is unavailable, so this
    degrades to single-monitor behaviour rather than failing.
    """
    try:
        import ctypes

        metrics = ctypes.windll.user32.GetSystemMetrics
        x, y, w, h = (metrics(i) for i in (76, 77, 78, 79))
        if w > 0 and h > 0:
            return x, y, w, h
    except Exception:
        pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def geometry_is_reachable(virtual: tuple[int, int, int, int],
                          w: int, h: int, x: int, y: int) -> bool:
    """Can the user actually see and grab a window placed here?

    The case that matters: the window was last closed on a second monitor
    that is no longer attached. Restoring those coordinates puts it
    somewhere invisible with no way to drag it back, which reads as the
    program failing to start. *virtual* is what virtual_screen() gave.
    """
    vx, vy, vw, vh = virtual
    if y < vy:
        return False                      # title bar above every screen
    visible_w = max(0, min(x + w, vx + vw) - max(x, vx))
    visible_h = max(0, min(y + h, vy + vh) - max(y, vy))
    return visible_w >= MIN_VISIBLE_WIDTH and visible_h >= MIN_VISIBLE_HEIGHT


def parse_geometry(text: str | None) -> tuple[int, int, int, int] | None:
    """'WIDTHxHEIGHT+X+Y' -> (w, h, x, y); None for anything else."""
    if not text:
        return None
    match = _GEOMETRY.match(text.strip())
    if not match:
        return None
    return tuple(int(g) for g in match.groups())   # type: ignore[return-value]


def center_on_primary(root, width: int = FIRST_RUN_WIDTH) -> None:
    """First run, or a remembered position that is no longer usable."""
    root.update_idletasks()
    w = width
    h = root.winfo_reqheight()
    root.geometry(f"{w}x{h}")
    root.update_idletasks()
    x = max(0, (root.winfo_screenwidth() - w) // 2)
    y = max(0, (root.winfo_screenheight() - h) // 2)
    root.geometry(f"+{x}+{y}")


def restore_geometry(root, saved: str | None, state: str, *,
                     reachable: Callable[[int, int, int, int], bool],
                     center: Callable[[], None],
                     on_unreachable: Callable[[], None]) -> None:
    """Put the window where it was, or centre it.

    A remembered rect is restored only when *reachable* says so; a rect that
    is not - typically because the monitor it was on has been disconnected -
    is reported through *on_unreachable* and the window is centred. A
    garbled value is centred without a word: nothing about it is worth one.
    """
    parsed = parse_geometry(saved)
    if parsed is not None:
        w, h, x, y = parsed
        if reachable(w, h, x, y):
            root.geometry(f"{w}x{h}+{x}+{y}")
            if state == "zoomed":
                root.state("zoomed")
            return
        on_unreachable()
    center()


def normal_geometry(root) -> str | None:
    """The window's geometry when it is the NON-maximized one, else None.

    Meant for a <Configure> handler that keeps the last normal geometry. Two
    filters, and the second one is not redundant: maximizing arrives as a
    Configure whose event can still be seen while state() reports "normal",
    so the maximized rect would be recorded as if the user had sized the
    window that way, and un-maximizing on the next run would give back a
    screen-sized window that is not maximized.
    """
    if root.state() != "normal":
        return None
    near_screen = (root.winfo_width() >= root.winfo_screenwidth() - NEAR_SCREEN_WIDTH_SLACK
                   and root.winfo_height() >= root.winfo_screenheight() - NEAR_SCREEN_HEIGHT_SLACK)
    if near_screen:
        return None
    return root.geometry()
