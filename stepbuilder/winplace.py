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

# How much of a remembered window must still be on ONE monitor for the
# position to count as usable: enough to see and grab - its title strip, the
# top MIN_VISIBLE_HEIGHT px of the frame, at least MIN_VISIBLE_WIDTH of them
# wide (geometry_is_reachable).
MIN_VISIBLE_WIDTH = 120
MIN_VISIBLE_HEIGHT = 40

# What Windows draws round the client area a geometry's size describes: the
# title bar and border above it, the border below. Measured 01.11.2026 at
# 100% scaling with Tk 8.6 (build/fix-2026-10-31/r130/frame_measure.py): a
# 908x600 client in a 926x647 frame, 38 px above the client and 9 below.
FRAME_ALLOWANCE = 48

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


def monitor_areas(root) -> list[tuple[int, int, int, int]]:
    """(x, y, w, h) of each monitor's work area - the part no taskbar covers -
    in the virtual desktop's coordinates (EnumDisplayMonitors and
    GetMonitorInfoW's rcWork); [virtual_screen(root)] when they cannot be
    listed, so this degrades to the rectangle it replaced.

    The virtual screen alone is the rectangle round EVERY monitor, and
    monitors need not fill it: two set diagonally, or a tall one beside a
    short one, leave corners that no screen shows. A window remembered there
    was taken for visible and opened where nobody could see it (review
    23.10.2026, R6-6, round 130).
    """
    try:
        import ctypes
        from ctypes import wintypes

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

        user32 = ctypes.windll.user32
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
        found = []

        def one(handle, _dc, _rect, _data):
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(handle, ctypes.byref(info)):
                r = info.rcWork
                found.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
            return True

        each = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                                  ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)(one)
        user32.EnumDisplayMonitors(None, None, each, 0)
        areas = [a for a in found if a[2] > 0 and a[3] > 0]
        if areas:
            return areas
    except Exception:
        pass
    return [virtual_screen(root)]


def geometry_is_reachable(areas: list[tuple[int, int, int, int]],
                          w: int, h: int, x: int, y: int) -> bool:
    """Can the user actually see and grab a window placed here?

    The case that matters: the window was last closed on a second monitor
    that is no longer attached, or that has moved. Restoring those
    coordinates puts it somewhere invisible with no way to drag it back,
    which reads as the program failing to start. *areas* is what
    monitor_areas() gave; the window counts when its title strip - the top
    MIN_VISIBLE_HEIGHT px of the frame, MIN_VISIBLE_WIDTH of them wide at the
    least - lies on one of them. Until round 130 the test was any overlap
    with the rectangle round all of them (R6-6).
    """
    for mx, my, mw, mh in areas:
        across = min(x + w, mx + mw) - max(x, mx)
        if across >= MIN_VISIBLE_WIDTH and my <= y and y + MIN_VISIBLE_HEIGHT <= my + mh:
            return True
    return False


def parse_geometry(text: str | None) -> tuple[int, int, int, int] | None:
    """'WIDTHxHEIGHT+X+Y' -> (w, h, x, y); None for anything else."""
    if not text:
        return None
    match = _GEOMETRY.match(text.strip())
    if not match:
        return None
    return tuple(int(g) for g in match.groups())   # type: ignore[return-value]


def primary_work_area(root) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the primary monitor's work area - the screen less the
    taskbar (SystemParametersInfoW, SPI_GETWORKAREA); the primary screen
    whole when that call is unavailable."""
    try:
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
            if rect.right > rect.left and rect.bottom > rect.top:
                return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    except Exception:
        pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def center_on_primary(root, width: int = FIRST_RUN_WIDTH,
                      work: tuple[int, int, int, int] | None = None) -> None:
    """First run, or a remembered position that is no longer usable: centred
    in the primary monitor's work area (*work*, else primary_work_area), and
    no taller than it, frame included.

    The window asks for 910 px of client; until round 130 that was the height
    whatever the screen, with the top clamped to 0, so on a 1366x768 screen
    the bottom 142 px - the progress bar, Generate and the status line - were
    under the screen's edge (review 23.10.2026, R6-7). A shorter window gives
    the room back from the log, the one row that grows.
    """
    root.update_idletasks()
    wx, wy, ww, wh = work if work is not None else primary_work_area(root)
    w = min(width, ww)
    h = max(1, min(root.winfo_reqheight(), wh - FRAME_ALLOWANCE))
    root.geometry(f"{w}x{h}")
    root.update_idletasks()
    x = wx + max(0, (ww - w) // 2)
    y = wy + max(0, (wh - h - FRAME_ALLOWANCE) // 2)
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
