# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, OUT, fails, check
from _support import keep_windows_off_screen

# Before the first Tk(): the window is built on a desktop of its own and never
# shown on the user's (round 94).
_OFF_SCREEN = keep_windows_off_screen()
if _OFF_SCREEN:
    print(f"note: the windows are shown on this desktop - {_OFF_SCREEN}")

"""The window's rules that need no screen (round 130, the review's batch 7).

The real StepBuilderApp, built and asked - never clicked, never measured on a
screen, no clipboard, no child process: a build is a bridge that starts
nothing, or WorkerBridge with a stand-in for multiprocessing.Process. So this
suite runs where test_gui and test_geom cannot judge - the 4090's session 0,
where generated clicks and window geometry do not work - and the rows of the
mutation table that hold these rules are proved there.

  [1] launch flags are for one run (R6-4)        [6] where the window opens (R6-6, R6-7)
  [2] the board theme by name (R6n-6)            [7] one queue per build (R6-12, R6n-5)
  [3] the layer list during a build (R6-11)      [8] the checks that could not fail (R6-9)
  [4] Reset colors and "other" (R6-15)           [9] a STEP file takes its name complete (R6-14)
  [5] closing while a build runs (R6-14)
"""
import ctypes
import dataclasses
import json
import multiprocessing
import shutil
import sys
import time
import types
from pathlib import Path

import stepbuilder.__main__ as M
import stepbuilder.gui as G
import stepbuilder.settings as S
import stepbuilder.winplace as W
import stepbuilder.worker_bridge as WB
from stepbuilder.colors import DEFAULT_LAYER_COLORS

TMP = OUT / "window rules"
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
SHIPPED = (ROOT / "simple3d_config.json").read_text(encoding="utf-8")

# Message boxes answer from this table and say they were asked.
ANSWER = {"askokcancel": False}
ASKED = []
for _name in ("showerror", "showwarning", "showinfo", "askokcancel", "askyesno"):
    setattr(G.messagebox, _name,
            lambda *a, _n=_name, **k: ASKED.append(_n) or ANSWER.get(_n))


def fresh(name, local=None):
    d = TMP / name
    d.mkdir()
    cfg = d / "simple3d_config.json"
    cfg.write_text(SHIPPED, encoding="utf-8")
    loc = d / "simple3d_config.local.json"
    if local is not None:
        loc.write_text(json.dumps(local, indent=2), encoding="utf-8")
    return cfg, loc


def gui_of(loc):
    return json.loads(loc.read_text(encoding="utf-8")).get("gui", {}) if loc.exists() else {}


def pump(app, secs):
    end = time.time() + secs
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def log_lines(app):
    return app.log_view.get("1.0", "end").strip().splitlines()


def close(app):
    """Close the way the window does, with no build to ask about."""
    app._bridge = FakeBridge()
    app._on_close()


class FakeBridge:
    """A bridge that starts nothing: what the window asks of one."""

    def __init__(self, alive=False):
        self._alive, self.closed = alive, False

    @property
    def alive(self):
        return self._alive

    def start(self, settings):
        self._alive = True
        return True

    def drain_once(self):
        pass

    def cancel(self):
        self._alive = False
        return True

    def close(self):
        self._alive, self.closed = False, True


def through_launcher(argv, during=None):
    """The launcher's --gui path, the window looked at, then closed as a user
    closes it: (exit code, what the window held)."""
    seen = {}
    original = G.StepBuilderApp.mainloop

    def look(self, n=0):
        pump(self, 0.3)
        if during:
            during(self)
        seen.update(theme=self.theme.get(), steps=self.step_dirs(), top=self.silk_top.get(),
                    copper=self.exposed_copper.get(), log=log_lines(self))
        close(self)
    G.StepBuilderApp.mainloop = look
    try:
        code = M.main(argv)
    finally:
        G.StepBuilderApp.mainloop = original
    return code, seen


print("[1] launch flags are for this run only (review 23.10.2026, R6-4)")
# --help says so, and until round 130 the close wrote whatever the flags had
# set: one hand-run launch replaced the remembered folders and options for good.
cfg, loc = fresh("flags", {"gui": {"stepDirs": ["D:/my/lib"], "boardColor": "Red"}})
code, seen = through_launcher(["--gui", "--config", str(cfg), "--step-dir", "D:/oneoff/lib",
                               "--color", "Blue", "--no-silkscreen", "--exposed-copper"])
check("the flags reach the window", code == 0 and seen["steps"] == ["D:/oneoff/lib"]
      and seen["theme"] == "Blue" and seen["top"] is False and seen["copper"] is True, seen)
g = gui_of(loc)
check("and the close keeps what the settings held for each of them",
      g.get("stepDirs") == ["D:/my/lib"] and g.get("boardColor") == "Red"
      and "silkscreenTop" not in g and "silkscreenBottom" not in g and "exposedCopper" not in g, g)
cfg, loc = fresh("flags_then_changed", {"gui": {"boardColor": "Red"}})
code, seen = through_launcher(["--gui", "--config", str(cfg), "--color", "Blue"],
                              lambda app: app.set_theme("Yellow"))
check("a setting changed in the window after the launch is the user's, and is kept",
      gui_of(loc).get("boardColor") == "Yellow", gui_of(loc))
cfg, loc = fresh("no_flags", {"gui": {"boardColor": "Red"}})
code, seen = through_launcher(["--gui", "--config", str(cfg)], lambda app: app.set_theme("Purple"))
check("with no flags a change is saved as before", gui_of(loc).get("boardColor") == "Purple", gui_of(loc))
# The window's place and the paths it was pointed at are not a flag's: a
# window centred at the launch and closed where it was keeps that place.
loaded = S.load_gui_settings(cfg)[0]
launched = dataclasses.replace(loaded, step_dirs=["D:/oneoff/lib"], window_geometry="908x700+10+10",
                               window_state="zoomed", json_file="D:/rev/a.json", output_dir="D:/rev/3d")
out = S.without_launch_overrides(dataclasses.replace(launched), launched, loaded)
check("the window's own place and its paths are no flag's: kept as they are",
      out.step_dirs == loaded.step_dirs
      and (out.window_geometry, out.window_state, out.json_file, out.output_dir)
      == ("908x700+10+10", "zoomed", "D:/rev/a.json", "D:/rev/3d"),
      (out.step_dirs, out.window_geometry, out.window_state, out.json_file, out.output_dir))

print("\n[2] the board theme is one of the window's, by name in any case (review 28.10.2026, R6n-6)")
# The command line's --color takes r,g,b and #rrggbb; the window has themes.
# Until round 130 any name went into the theme as given, and the build took
# the default colour for "255,0,0" - and for "blue" - with nothing said.
cfg, loc = fresh("rgb", {"gui": {"boardColor": "Red"}})
taken = {}
code, seen = through_launcher(["--gui", "--config", str(cfg), "--color", "255,0,0"],
                              lambda app: taken.update(color=app._snapshot().board_color))
check("an r,g,b colour leaves the theme as it was", seen["theme"] == "Red"
      and taken["color"] == G.BOARD_THEMES["Red"], (seen["theme"], taken))
check("and the log says why, naming the themes",
      any(l.startswith("warning: --color 255,0,0") and "Dark_green" in l for l in seen["log"]), seen["log"])
check("and the settings keep their colour", gui_of(loc).get("boardColor") == "Red", gui_of(loc))
cfg, loc = fresh("lower", {})
code, seen = through_launcher(["--gui", "--config", str(cfg), "--color", "blue"],
                              lambda app: taken.update(color=app._snapshot().board_color))
check("a theme in another case is that theme", seen["theme"] == "Blue"
      and taken["color"] == G.BOARD_THEMES["Blue"], (seen["theme"], taken))

print("\n[3] the layer list waits for the build's end (review 23.10.2026, R6-11)")
# The refresh is put off 400 ms after the JSON field changes. A path typed and
# Generate pressed at once landed it mid-build: the rebuilt rows came up live
# and the silkscreen group was switched back on under a build that had
# already taken its settings.
board = TMP / "layers.json"
board.write_text(json.dumps({
    "format": "simple3d", "format_version": 7, "name": "layers", "pcb": {},
    "silkscreen": {"top": [{"layer": "SILK_A"}, {"layer": "SILK_B"}], "bottom": [{"layer": "SILK_C"}]}}),
    encoding="utf-8")
cfg, loc = fresh("race", {"gui": {"stepDirs": ["D:/lib"], "outputDir": str(TMP)}})
app = G.StepBuilderApp(cfg)
pump(app, 0.2)
app._bridge = FakeBridge()
app.json_file.set(str(board))
app.on_generate()
pump(app, 0.8)
check("0.8 s into the build the silkscreen group is still greyed",
      app._busy and str(app.silk_box.cget("state")) == "disabled"
      and str(app.silk_flat_check.cget("state")) == "disabled"
      and app.layers.buttons[0].instate(["disabled"]),
      (app._busy, str(app.silk_box.cget("state")), str(app.silk_flat_check.cget("state"))))
check("and no layer row was rebuilt live",
      not any(str(b.cget("state")) == "normal" for side in app._layer_rows.values() for _, _, b in side),
      [(n, str(b.cget("state"))) for side in app._layer_rows.values() for n, _, b in side])
app._update_silk_row()
check("and the silkscreen row's own update leaves a frozen group alone",
      str(app.silk_box.cget("state")) == "disabled" and str(app.silk_flat_check.cget("state")) == "disabled",
      (str(app.silk_box.cget("state")), str(app.silk_flat_check.cget("state"))))
app._bridge._alive = False
app._set_busy(False)
pump(app, 0.2)
rows = sorted(n for side in app._layer_rows.values() for n, _, _ in side)
check("when the build ends the list the field asked for comes, live",
      rows == ["SILK_A", "SILK_B", "SILK_C"]
      and all(str(b.cget("state")) == "normal" for side in app._layer_rows.values() for _, _, b in side)
      and str(app.silk_box.cget("state")) == "readonly", rows)
close(app)

print("\n[4] Reset colors resets the swatches there are (review 23.10.2026, R6-15)")
# "other" has no swatch, and in the two layer-coloured modes it is painted:
# a layerColors.other set by hand was reset there with nothing to show it.
cfg, loc = fresh("reset", {})
app = G.StepBuilderApp(cfg)
pump(app, 0.2)
for mode in ("layers", "inspect", "solid"):
    app.board_mode.set(G._mode_label(mode))
    app._on_mode_changed()
    app.layer_colors["other"] = (1, 2, 3)
    app.layer_colors["copper"] = (4, 5, 6)
    app._reset_layer_colors()
    check(f"{mode}: other keeps its colour", app.layer_colors["other"] == (1, 2, 3), app.layer_colors["other"])
    if mode != "solid":
        check(f"{mode}: and a live swatch is reset", app.layer_colors["copper"] == DEFAULT_LAYER_COLORS["copper"],
              app.layer_colors["copper"])
        check(f"{mode}: and the log says every colour went back",
              log_lines(app)[-1] == "Layer colors reset to the Allegro material defaults", log_lines(app)[-1])
close(app)

print("\n[5] closing while a build runs asks first (review 23.10.2026, R6-14)")
# It used to stop the build without a word.
for answer in (False, True):
    cfg, loc = fresh(f"close_{answer}", {})
    app = G.StepBuilderApp(cfg)
    pump(app, 0.2)
    fake = FakeBridge(alive=True)
    app._bridge = fake
    app._set_busy(True)
    ASKED.clear()
    ANSWER["askokcancel"] = answer
    app._on_close()
    try:
        there = bool(app.winfo_exists())
    except Exception:
        there = False
    check(f"the question is asked; answered {answer}, the window "
          f"{'closes and the build is stopped' if answer else 'stays and so does the build'}",
          ASKED == ["askokcancel"] and fake.closed is answer and there is (not answer), (ASKED, fake.closed, there))
    if there:
        fake._alive = False
        app._set_busy(False)
        close(app)
ANSWER["askokcancel"] = False
cfg, loc = fresh("close_idle", {})
app = G.StepBuilderApp(cfg)
pump(app, 0.2)
ASKED.clear()
close(app)
check("with no build running nothing is asked", ASKED == [], ASKED)

print("\n[6] where the window opens (review 23.10.2026, R6-6, R6-7)")
# R6-6: the title strip must lie on ONE monitor's work area. Until round 130
# any overlap with the rectangle round all of them counted, and monitors need
# not fill it - the review's three desks below, a window left where no screen
# shows it. The fourth is the control: side by side, the window on the right.
DESKS = {"diagonal": [(0, 0, 1920, 1080), (1920, 1080, 1920, 1080)],
         "tall right": [(0, 0, 1920, 1080), (1920, 0, 2560, 1440)],
         "lowered right": [(0, 0, 1920, 1080), (1920, 600, 1920, 1080)],
         "side by side": [(0, 0, 1920, 1080), (1920, 0, 1920, 1080)]}
for desk, (w, h, x, y), want in (("diagonal", (908, 640, 2100, 200), False),
                                 ("tall right", (908, 640, 400, 1200), False),
                                 ("lowered right", (908, 640, 2100, 200), False),
                                 ("side by side", (908, 640, 2100, 200), True)):
    got = W.geometry_is_reachable(DESKS[desk], w, h, x, y)
    check(f"{desk}: a {w}x{h} window at +{x}+{y} is {'reachable' if want else 'not'}", got is want, got)
check("the title strip must fit: 39 px from a monitor's bottom is not enough",
      not W.geometry_is_reachable([(0, 0, 1920, 1040)], 900, 700, 100, 1001)
      and W.geometry_is_reachable([(0, 0, 1920, 1040)], 900, 700, 100, 1000))
check("and be 120 px wide: a 70 px sliver at either side is not enough",
      not W.geometry_is_reachable([(0, 0, 1920, 1040)], 908, 640, -838, 100)
      and not W.geometry_is_reachable([(0, 0, 1920, 1040)], 908, 640, 1850, 100)
      and W.geometry_is_reachable([(0, 0, 1920, 1040)], 908, 640, -788, 100)
      and W.geometry_is_reachable([(0, 0, 1920, 1040)], 908, 640, 1800, 100))


class FakeRoot:
    """What center_on_primary asks of a window."""

    def __init__(self, req_height):
        self.req, self.calls = req_height, []

    def update_idletasks(self):
        pass

    def winfo_reqheight(self):
        return self.req

    def winfo_screenwidth(self):
        return 9999

    def winfo_screenheight(self):
        return 9999

    def geometry(self, g=None):
        self.calls.append(g)


class FakeUser32:
    """Two monitors as EnumDisplayMonitors and GetMonitorInfoW give them, each
    with a taskbar, so its work area is not the monitor."""

    MONITORS = {1: ((0, 0, 1920, 1080), (0, 0, 1920, 1040)),
                2: ((1920, 200, 3200, 1640), (1920, 200, 3200, 1600))}

    def __init__(self):
        def info(handle, pointer):
            monitor, work = self.MONITORS[handle]
            got = pointer._obj
            for rect, (left, top, right, bottom) in ((got.rcMonitor, monitor), (got.rcWork, work)):
                rect.left, rect.top, rect.right, rect.bottom = left, top, right, bottom
            return 1
        self.GetMonitorInfoW = info          # a function, so the code can set its argtypes

    def EnumDisplayMonitors(self, _dc, _clip, each, _data):
        for handle in self.MONITORS:
            each(handle, None, None, 0)
        return 1


# Windows stood in for: the fallback, the rectangle round all monitors, would
# be FakeRoot's 9999 x 9999 screen.
real_windll = ctypes.windll
ctypes.windll = types.SimpleNamespace(user32=FakeUser32())
try:
    listed = W.monitor_areas(FakeRoot(910))
finally:
    ctypes.windll = real_windll
check("monitor_areas lists each monitor's work area, the taskbar left out",
      listed == [(0, 0, 1920, 1040), (1920, 200, 1280, 1400)], listed)
here = W.monitor_areas(FakeRoot(910))
check("and on this machine the primary's work area is one of them",
      W.primary_work_area(FakeRoot(910)) in here, (W.primary_work_area(FakeRoot(910)), here))


# R6-7: a first run is centred in the primary monitor's work area and no
# taller than it, frame included. Until round 130 the 910 px the window asks
# for were its height on any screen, the top clamped to 0: 142 px of it under
# a 1366x768 screen's edge. test_geom [9] measures the real window.
for wx, wy, ww, wh in ((0, 0, 1920, 1040), (0, 0, 1366, 728), (0, 0, 1280, 680), (100, 40, 1366, 728)):
    root = FakeRoot(910)
    W.center_on_primary(root, 908, work=(wx, wy, ww, wh))
    size = [c for c in root.calls if c and "x" in c][-1]
    pos = [c for c in root.calls if c and c.startswith("+")][-1]
    cw, ch = (int(v) for v in size.split("x"))
    x, y = (int(v) for v in pos.split("+")[1:])
    check(f"work area {ww}x{wh}+{wx}+{wy}: the window {size}{pos} fits it, frame included",
          ch == min(910, wh - W.FRAME_ALLOWANCE) and wy <= y and y + ch + W.FRAME_ALLOWANCE <= wy + wh
          and x == wx + (ww - cw) // 2, (size, pos))

print("\n[7] one queue per build (review 23.10.2026, R6-12; 28.10.2026, R6n-5)")
# WorkerBridge with a stand-in for the process - no child, so nothing is
# spawned - and a real multiprocessing.Queue made by start(), which this side
# feeds as the child would. Until round 130 one queue served the session: after
# a cancel the drain went on delivering the killed build's lines, and a done it
# had sent ended the NEXT build, whose crash then went unnamed.


class FakeProcess:
    def __init__(self, target=None, args=(), daemon=None):
        self.alive, self.exitcode = False, None

    def start(self):
        self.alive = True

    def is_alive(self):
        return self.alive

    def terminate(self):
        self.alive, self.exitcode = False, -15


events = []
bridge = WB.WorkerBridge(on_log=lambda m: events.append(("log", m)),
                         on_progress=lambda c, t, s: events.append(("progress", s)),
                         on_done=lambda m: events.append(("done", m)),
                         on_error=lambda m: events.append(("error", m)),
                         on_crash=lambda m: events.append(("crash", m[:40])))
WB.multiprocessing = types.SimpleNamespace(Process=FakeProcess, Queue=multiprocessing.Queue)
try:
    def drain(secs, until=None):
        end = time.time() + secs
        while time.time() < end and not (until and until()):
            bridge.drain_once()
            time.sleep(0.02)

    bridge.start(None)
    bridge._queue.put(("log", "hello"))
    bridge._queue.put(("done", "Done: 1 file(s)"))
    drain(2.0, lambda: len(events) >= 2)
    check("a build's lines and its done reach the window", events == [("log", "hello"), ("done", "Done: 1 file(s)")],
          events)
    finished_queue = bridge._queue
    bridge.process.alive = False
    drain(0.1)
    events.clear()
    finished_queue.put(("log", "a late line of the finished build"))
    time.sleep(0.3)
    bridge.start(None)
    bridge._queue.put(("log", "the next build's own"))
    drain(1.0, lambda: len(events) >= 1)
    drain(0.2)
    check("a finished build's late line does not reach the next one",
          events == [("log", "the next build's own")], events)
    bridge.cancel()

    events.clear()
    bridge.start(None)
    old = bridge._queue
    for i in range(5):
        old.put(("progress", (i, 100, f"stage {i}")))
    old.put(("done", "Done: the cancelled build"))
    time.sleep(0.3)                          # the lines are in the pipe now
    bridge.cancel()
    drain(0.5)
    check("after a cancel nothing of the killed build arrives", events == [], events)

    bridge.start(None)
    check("the next build has a queue of its own", bridge._queue is not old)
    bridge.process.alive, bridge.process.exitcode = False, 1     # it dies at once, saying nothing
    drain(0.5)
    check("so the killed build's done ends nothing, and the next one's crash is named",
          [e[0] for e in events] == ["crash"], events)
finally:
    WB.multiprocessing = multiprocessing
    bridge.close()

print("\n[8] the checks that could not fail, made real (review 23.10.2026, R6-9)")
# test_gui held them with a literal True, the flag set a line above, and a
# copy of the colouring rule; here the window's own methods are called.
cfg, loc = fresh("real", {"gui": {"outputDir": "D:/old/out"}})
app = G.StepBuilderApp(cfg)
pump(app, 0.2)
popups = []
real_popup = G.tk.Menu.tk_popup
G.tk.Menu.tk_popup = lambda self, *a, **k: popups.append(a)


class _Click:
    x_root = y_root = 0


try:
    field = app.output_entry if hasattr(app, "output_entry") else next(
        w for w in app._walk() if isinstance(w, G.ttk.Entry))
    app._busy = True
    app._show_edit_menu(_Click(), field)
    busy_popups = len(popups)
    app._busy = False
    app._show_edit_menu(_Click(), field)
finally:
    G.tk.Menu.tk_popup = real_popup
check("the edit menu: none while a build runs, one when it does not", (busy_popups, len(popups)) == (0, 1),
      (busy_popups, len(popups)))
asked_colour = []
import tkinter.colorchooser as _cc  # noqa: E402 - the window imports it where it asks
_saved_ask = _cc.askcolor
_cc.askcolor = lambda *a, **k: asked_colour.append(k.get("title")) or (None, None)
try:
    app.board_mode.set(G._mode_label("layers"))
    app._on_mode_changed()
    app._busy = True
    app._pick_layer_color("copper")
    busy_asks = len(asked_colour)
    app._busy = False
    app._pick_layer_color("copper")
finally:
    _cc.askcolor = _saved_ask
check("a swatch: no colour chooser while a build runs, one when it does not",
      (busy_asks, len(asked_colour)) == (0, 1), (busy_asks, asked_colour))
for text, want in (("  note: BEND_1's bend area is 3.000 mm across", "note"),
                   ("warning: 2 cutout(s) repeat another one exactly", "warning"),
                   ("error (board.json): pcb.edges is empty", "error"),
                   ("Traceback (most recent call last):", "error"),
                   ("Building board geometry", None)):
    app._append_log(text)
    tags = [t for t in app.log_view.tag_names("end-2l linestart") if t in ("note", "warning", "error", "success")]
    check(f"the log colours {text[:40]!r} as {want}", tags == ([want] if want else []), tags)
variants = TMP / "variants"
variants.mkdir()
for n in ("brd_v1", "brd_v2"):
    (variants / f"{n}.json").write_text(json.dumps({"format": "simple3d", "format_version": 12, "name": n,
                                                    "pcb": {}}), encoding="utf-8")
out3d = TMP / "out3d"
out3d.mkdir()
app.prefill_jobs(json_dir=str(variants), output_dir=str(out3d), brd_name="MyBoard", dated_name=True)
check("prefill_jobs fills the fields, the name and the dated rule, and marks the paths as Allegro's",
      app.json_file.get() == str(variants).replace("\\", "/") and app.output_dir.get() == str(out3d).replace("\\", "/")
      and app._brd_name == "MyBoard" and app._dated_name is True and app._paths_from_launcher is True,
      (app.json_file.get(), app.output_dir.get(), app._brd_name, app._dated_name))
close(app)
cfg, loc = fresh("prefill_keep", {"gui": {"outputDir": "D:/old/out"}})
app = G.StepBuilderApp(cfg)
pump(app, 0.2)
app.prefill_jobs(json_dir=str(variants))
check("a launch naming a JSON folder but no output keeps the remembered output (R6-16's promise)",
      app.output_dir.get() == "D:/old/out", app.output_dir.get())
close(app)

print("\n[9] a STEP file takes its name only when complete (review 23.10.2026, R6-14)")
# A build stopped in the middle of the write - Cancel, or the window closed -
# could leave a cut-short .step under the final name. The writer is stood in
# for: it writes the file's first lines and is interrupted.
from stepbuilder import stepdoc  # noqa: E402

written = []


class CutShort:
    def SetColorMode(self, *_):
        pass

    def SetNameMode(self, *_):
        pass

    def Transfer(self, *_):
        return True

    def Write(self, path):
        written.append(path)
        Path(path).write_text("ISO-10303-21;\nHEADER;\n", encoding="ascii")
        raise KeyboardInterrupt("stopped mid-write")


target = TMP / "board.step"
real_writer = stepdoc.STEPCAFControl_Writer
stepdoc.STEPCAFControl_Writer = CutShort
try:
    try:
        stepdoc.StepDocument("board").write(target, True)
    except KeyboardInterrupt:
        pass
finally:
    stepdoc.STEPCAFControl_Writer = real_writer
check("the writer is handed <name>.step.part, not the name", written == [str(target) + ".part"], written)
check("stopped mid-write: nothing under the name, and the part is taken away",
      not target.exists() and not Path(str(target) + ".part").exists(),
      sorted(p.name for p in TMP.glob("board*")))
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402

real = stepdoc.StepDocument("board")
real.shape_tool.AddShape(BRepPrimAPI_MakeBox(1.0, 2.0, 3.0).Shape())
real.write(target, True)
check("the real writer: the file under its name, no part left, and it reads",
      target.exists() and not Path(str(target) + ".part").exists()
      and target.read_text(encoding="ascii", errors="replace").startswith("ISO-10303-21;"),
      sorted(p.name for p in TMP.glob("board*")))

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
