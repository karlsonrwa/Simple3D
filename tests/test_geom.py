# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import OUT, fails, check, rect
from _support import keep_windows_off_screen

# Every window below is mapped - it has to be, see the docstring - and every
# one of them used to pop up on the user's desktop, sixteen per run, one of
# them maximized (measured 2026-09-23). Mapped on a desktop of their own they
# are measured the same way and seen by nobody (round 94). Before the first
# Tk(), or it is too late.
_OFF_SCREEN = keep_windows_off_screen()
if _OFF_SCREEN:
    print(f"note: the windows are shown on this desktop - {_OFF_SCREEN}")

"""Window placement: remembered across runs, multi-monitor aware.

Windows are MAPPED (deiconify), not withdrawn: winfo_x/width on an unmapped
window report the requested size, not where it actually is, which silently
invalidates every placement assertion.
"""
import json, re, shutil, sys
from stepbuilder.gui import StepBuilderApp

TMP = OUT / "geomtest"
shutil.rmtree(TMP, ignore_errors=True); TMP.mkdir()

def parse(g):
    m = re.match(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$", g)
    return tuple(int(x) for x in m.groups()) if m else None


class _Fake:
    """What winplace.normal_geometry asks a window, and nothing else.

    A real Tk window cannot be made screen-sized-but-not-maximized reliably
    (the manager maximizes it and state() changes), which is why the filter
    that case exists for had never been measured - see [7b]."""

    def __init__(self, state, w, h, x, y, screen_w, screen_h):
        self._state, self._w, self._h = state, w, h
        self._x, self._y = x, y
        self._sw, self._sh = screen_w, screen_h

    def state(self):
        return self._state

    def winfo_width(self):
        return self._w

    def winfo_height(self):
        return self._h

    def winfo_screenwidth(self):
        return self._sw

    def winfo_screenheight(self):
        return self._sh

    def geometry(self):
        return f"{self._w}x{self._h}+{self._x}+{self._y}"

def make(cfgdata, name):
    p = TMP/name; p.write_text(json.dumps(cfgdata), encoding="utf-8")
    # The window writes a LOCAL file beside the one it is given, and that file
    # outlives the run. Left in place it would carry one case's geometry into
    # the next one's fixture - each case here states its own starting point and
    # must get it.
    local = p.with_name(p.stem + ".local" + p.suffix)
    local.unlink(missing_ok=True)
    a = StepBuilderApp(p)
    a.deiconify(); a.update()
    return a, p

from stepbuilder import winplace as winplace_module
probe, _ = make({"gui": {}}, "probe.json")
SW, SH = probe.winfo_screenwidth(), probe.winfo_screenheight()
NW, NH = probe.winfo_reqwidth(), probe.winfo_reqheight()
# Since round 130 (R6-7) a first run is centred in the primary monitor's WORK
# area - the screen less the taskbar - and no taller than it, frame included.
WX, WY, WW, WH = winplace_module.primary_work_area(probe)
probe.destroy()
FIRST_W = StepBuilderApp.FIRST_RUN_WIDTH   # a first run opens at a FIXED width
FRAME = winplace_module.FRAME_ALLOWANCE
FIRST_H = min(NH, WH - FRAME)
CX, CY = WX + max(0, (WW - FIRST_W) // 2), WY + max(0, (WH - FIRST_H - FRAME) // 2)
print(f"screen {SW}x{SH}, work area {WW}x{WH}+{WX}+{WY}, natural {NW}x{NH}, first-run width {FIRST_W}")

print("\n[1] first run -> centred in the primary screen's work area")
app,_ = make({"gui": {}}, "first.json")
check("x centred", abs(app.winfo_x() - CX) <= 4, f"{app.winfo_x()} vs {CX}")
check("y centred", abs(app.winfo_y() - CY) <= 4, f"{app.winfo_y()} vs {CY}")
check("no taller than the work area, frame included", app.winfo_height() <= WH - FRAME,
      f"{app.winfo_height()} vs {WH - FRAME}")
check("not Tk's default +160+157", (app.winfo_x(), app.winfo_y()) != (160,157))
app.destroy()

print("\n[2] a remembered, reachable position is restored exactly")
app,_ = make({"gui": {"windowGeometry": "900x700+300+120"}}, "saved.json")
check("size restored", (app.winfo_width(), app.winfo_height()) == (900,700),
      f"{app.winfo_width()}x{app.winfo_height()}")
check("position restored", (app.winfo_x(), app.winfo_y()) == (300,120),
      f"+{app.winfo_x()}+{app.winfo_y()}")
app.destroy()

print("\n[3] closing writes the geometry back")
app,p = make({"gui": {}}, "write.json")
app.geometry("880x640+210+90"); app.update()
app._save_config()
# The window writes the LOCAL file now; the tracked one is defaults only.
local = p.with_name(p.stem + ".local" + p.suffix)
g = json.loads(local.read_text(encoding="utf-8"))["gui"]
check("windowGeometry written", g.get("windowGeometry") == "880x640+210+90",
      str(g.get("windowGeometry")))
# The window writes only what changed since it opened (round 95): the state
# stayed "normal", so it is left out and the next run reads the default -
# [4] reopens such a file and finds the window normal, [7] writes "zoomed".
check("windowState not written: unchanged since the window opened",
      "windowState" not in g, str(g.get("windowState")))
app.destroy()

print("\n[4] a full round-trip: close here, reopen there")
app,p = make({"gui": {}}, "trip.json")
app.geometry("910x660+333+177"); app.update(); app._save_config(); app.destroy()
app2 = StepBuilderApp(p); app2.deiconify(); app2.update()
check("reopens at the same spot", (app2.winfo_x(), app2.winfo_y()) == (333,177),
      f"+{app2.winfo_x()}+{app2.winfo_y()}")
check("and the same size", (app2.winfo_width(), app2.winfo_height()) == (910,660),
      f"{app2.winfo_width()}x{app2.winfo_height()}")
check("and normal: a state left out of the file reads as normal", app2.state() == "normal",
      app2.state())
app2.destroy()

print("\n[5] an off-screen position is refused and the window is centred")
app,_ = make({"gui": {"windowGeometry": "900x700+9000+8000"}}, "offscreen.json")
check("centred instead", abs(app.winfo_x() - CX) <= 4, str(app.winfo_x()))
app.destroy()

print("\n[6] multi-monitor: a second screen to the LEFT (negative X)")
# Each monitor's work area, since round 130 (R6-6): the window must have its
# title strip on ONE of them, not merely touch the rectangle round them all.
# test_window_rules [6] runs the same rule on the desks the review drew.
app,_ = make({"gui": {}}, "multi.json")
app._monitor_areas = lambda: [(-1920, 0, 1920, 1040), (0, 0, 1920, 1040)]   # left + primary
check("a window on the left monitor is reachable",
      app._geometry_is_reachable(900, 700, -1600, 100))
check("far beyond every screen is not",
      not app._geometry_is_reachable(900, 700, 5000, 100))
check("title bar above all screens is not",
      not app._geometry_is_reachable(900, 700, 100, -50))
check("120px still visible is allowed",
      app._geometry_is_reachable(900, 700, 1800, 100))
check("a 70px sliver is not",
      not app._geometry_is_reachable(900, 700, 1850, 100))
app._monitor_areas = lambda: [(0, 0, 1920, 1040)]           # that monitor unplugged
check("the same left-monitor spot is now refused",
      not app._geometry_is_reachable(900, 700, -1600, 100))
here = winplace_module.monitor_areas(app)
check("this machine's monitors are listed, each a work area with a size",
      here and all(w > 0 and h > 0 for _, _, w, h in here), here)
app.destroy()
# The same rule as a function of the desk, with no window at all (round 73, C3).
from stepbuilder import winplace
two = [(-1920, 0, 1920, 1040), (0, 0, 1920, 1040)]
check("winplace: reachable on the left monitor", winplace.geometry_is_reachable(two, 900, 700, -1600, 100))
check("winplace: a 70px sliver is not", not winplace.geometry_is_reachable(two, 900, 700, 1850, 100))
check("winplace: above every screen is not", not winplace.geometry_is_reachable(two, 900, 700, 100, -50))

print("\n[7] maximized: the NON-maximized rect is what gets saved")
app,p = make({"gui": {}}, "zoom.json")
app.geometry("870x630+240+140"); app.update()
app.state("zoomed"); app.update()
app._save_config()
# The window writes the LOCAL file now; the tracked one is defaults only.
local = p.with_name(p.stem + ".local" + p.suffix)
g = json.loads(local.read_text(encoding="utf-8"))["gui"]
check("state saved as zoomed", g.get("windowState") == "zoomed", str(g.get("windowState")))
check("geometry is the restored rect, not the maximized one",
      g.get("windowGeometry") == "870x630+240+140", str(g.get("windowGeometry")))
app.destroy()
app2 = StepBuilderApp(p); app2.deiconify(); app2.update()
check("reopens maximized", app2.state() == "zoomed", app2.state())
app2.destroy()

print("\n[7b] a window sized to the whole screen while state() still says normal")
# The second filter in winplace.normal_geometry, and the one nothing measured:
# maximizing arrives as a <Configure> that can still be seen while state()
# reports "normal", so without it the MAXIMIZED rect is recorded as the normal
# one - and un-maximizing on the next run gives back a screen-sized window that
# is not maximized. Every case above sizes the window well under the screen, so
# the filter never had to do anything. Measured 2026-09-22: with it removed,
# this is what bites (mutation winplace-maximized-rect-remembered).
small = (860, 620, 200, 100)
check("a window well under the screen IS the normal geometry",
      winplace.normal_geometry(_Fake("normal", *small, SW, SH)) == "860x620+200+100",
      winplace.normal_geometry(_Fake("normal", *small, SW, SH)))
check("one as wide and as tall as the screen is not, though state() says normal",
      winplace.normal_geometry(_Fake("normal", SW, SH, 0, 0, SW, SH)) is None,
      winplace.normal_geometry(_Fake("normal", SW, SH, 0, 0, SW, SH)))
check("and the slack is what decides: a window inside it still counts",
      winplace.normal_geometry(_Fake(
          "normal", SW - winplace.NEAR_SCREEN_WIDTH_SLACK - 1,
          SH - winplace.NEAR_SCREEN_HEIGHT_SLACK - 1, 0, 0, SW, SH)) is not None)
check("just outside it does not",
      winplace.normal_geometry(_Fake(
          "normal", SW - winplace.NEAR_SCREEN_WIDTH_SLACK,
          SH - winplace.NEAR_SCREEN_HEIGHT_SLACK, 0, 0, SW, SH)) is None)
check("and a window that says it is zoomed never gives a geometry at all",
      winplace.normal_geometry(_Fake("zoomed", *small, SW, SH)) is None)

print("\n[8] a garbled value falls back to centring instead of crashing")
check("winplace.parse_geometry reads Tk's form, negative coordinates included",
      winplace.parse_geometry("900x700+-1600+120") == (900, 700, -1600, 120))
check("and refuses the rest", all(winplace.parse_geometry(b) is None for b in
      ("nonsense", "900x700", "", None, "1x1+abc+def", "900x700-10-10")))
for bad in ("nonsense", "900x700", "", "1x1+abc+def", "900x700-10-10"):
    a,_ = make({"gui": {"windowGeometry": bad}}, "bad.json")
    check(f"{bad!r} -> centred", abs(a.winfo_x() - CX) <= 4, f"x={a.winfo_x()}")
    a.destroy()

print("\n[9] a first run on a small screen keeps Generate and the status line on it (round 130, R6-7)")
# The window asks for about 910 px of client. Until round 130 that was its
# height on any screen, the top clamped to 0: on a 1366x768 screen the bottom
# 142 px - progress, Generate, the status line - lay under the screen's edge
# (review 23.10.2026). Centred in a 1366x768 work area now, the window is no
# taller than it and the log, the row that grows, gives the room back: the
# real window is measured here, its button and its status line inside it.
app,_ = make({"gui": {}}, "small.json")
winplace_module.center_on_primary(app, FIRST_W, work=(0, 0, 1366, 768))
app.update()
client_bottom = app.winfo_rooty() + app.winfo_height()
check("the window fits a 1366x768 work area, frame included",
      app.winfo_y() >= 0 and app.winfo_height() <= 768 - FRAME and client_bottom <= 768,
      f"+{app.winfo_y()}, client {app.winfo_height()}, bottom {client_bottom}")
button_bottom = app.generate_button.winfo_rooty() + app.generate_button.winfo_height()
check("Generate lies inside the window, not cut off by its edge",
      app.generate_button.winfo_ismapped() and button_bottom <= client_bottom,
      f"button bottom {button_bottom}, client bottom {client_bottom}")
app.destroy()

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
