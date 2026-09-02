# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import OUT, fails, check, rect

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

probe, _ = make({"gui": {}}, "probe.json")
SW, SH = probe.winfo_screenwidth(), probe.winfo_screenheight()
NW, NH = probe.winfo_reqwidth(), probe.winfo_reqheight()
probe.destroy()
FIRST_W = StepBuilderApp.FIRST_RUN_WIDTH   # a first run opens at a FIXED width
print(f"screen {SW}x{SH}, natural {NW}x{NH}, first-run width {FIRST_W}")

print("\n[1] first run -> centred on the primary screen")
app,_ = make({"gui": {}}, "first.json")
check("x centred", abs(app.winfo_x() - (SW-FIRST_W)//2) <= 4, f"{app.winfo_x()} vs {(SW-FIRST_W)//2}")
check("y centred", abs(app.winfo_y() - (SH-NH)//2) <= 4, f"{app.winfo_y()} vs {(SH-NH)//2}")
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
check("windowState written", g.get("windowState") == "normal", str(g.get("windowState")))
app.destroy()

print("\n[4] a full round-trip: close here, reopen there")
app,p = make({"gui": {}}, "trip.json")
app.geometry("910x660+333+177"); app.update(); app._save_config(); app.destroy()
app2 = StepBuilderApp(p); app2.deiconify(); app2.update()
check("reopens at the same spot", (app2.winfo_x(), app2.winfo_y()) == (333,177),
      f"+{app2.winfo_x()}+{app2.winfo_y()}")
check("and the same size", (app2.winfo_width(), app2.winfo_height()) == (910,660),
      f"{app2.winfo_width()}x{app2.winfo_height()}")
app2.destroy()

print("\n[5] an off-screen position is refused and the window is centred")
app,_ = make({"gui": {"windowGeometry": "900x700+9000+8000"}}, "offscreen.json")
check("centred instead", abs(app.winfo_x() - (SW-FIRST_W)//2) <= 4, str(app.winfo_x()))
app.destroy()

print("\n[6] multi-monitor: a second screen to the LEFT (negative X)")
app,_ = make({"gui": {}}, "multi.json")
app._virtual_screen = lambda: (-1920, 0, 3840, 1080)      # primary + left monitor
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
app._virtual_screen = lambda: (0, 0, 1920, 1080)           # that monitor unplugged
check("the same left-monitor spot is now refused",
      not app._geometry_is_reachable(900, 700, -1600, 100))
app.destroy()

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

print("\n[8] a garbled value falls back to centring instead of crashing")
for bad in ("nonsense", "900x700", "", "1x1+abc+def", "900x700-10-10"):
    a,_ = make({"gui": {"windowGeometry": bad}}, "bad.json")
    check(f"{bad!r} -> centred", abs(a.winfo_x() - (SW-FIRST_W)//2) <= 4, f"x={a.winfo_x()}")
    a.destroy()

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
