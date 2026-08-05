# Paths are derived from this file's own location, so the suite runs from
# wherever the repository is checked out. Anything a test writes goes to
# build/test-output/, which is gitignored.
import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parent.parent
_OUT = _ROOT / "build" / "test-output"
_OUT.mkdir(parents=True, exist_ok=True)
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

"""Real GUI tests: Tk runs headless on Windows, so the widgets can be exercised.

Uses a COPY of simple3d_config.json so the repo's file is never written.
"""
import json, shutil, sys

ROOT = _ROOT
sys.path.insert(0, str(ROOT))                 # so `stepbuilder` is importable
from stepbuilder.gui import StepBuilderApp, RIM_CUSTOM, RIM_SAME, RIM_CREAM

TMP = _OUT / "cfgtest"
TMP.mkdir(exist_ok=True)
cfg = TMP / "simple3d_config.json"
shutil.copy(ROOT / "simple3d_config.json", cfg)
# The window writes the LOCAL file, which survives the run. Copying a fresh
# base while leaving it behind would start every run from the last one's
# leftovers - and it does not fail loudly, it just quietly answers a different
# question than the one each case asks.
for stale in TMP.glob("*.local.json"):
    stale.unlink()

fails = []
def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(name)

app = StepBuilderApp(cfg)
app.withdraw()

print(chr(10) + "[1] rim colour picker greys unless Custom")
app.rim_choice.set(RIM_SAME); app._update_rim_swatch()
check("swatch greyed on 'Same as board'",
      app._rim_swatch.cget("bg") == "#d9d9d9", app._rim_swatch.cget("bg"))
app.rim_choice.set(RIM_CUSTOM); app.rim_custom.set("#40D857"); app._update_rim_swatch()
check("swatch shows the colour on Custom",
      app._rim_swatch.cget("bg") == "#40d857", app._rim_swatch.cget("bg"))
app.rim_custom.set("nonsense"); app._update_rim_swatch()
check("an unparsable stored value does not crash the swatch",
      app._rim_swatch.cget("bg") == "#ffffff", app._rim_swatch.cget("bg"))
app.rim_choice.set(RIM_CREAM); app._update_rim_swatch()
check("greys again on Cream", app._rim_swatch.cget("bg") == "#d9d9d9")
# the picker looks like a button only while it is one
app.rim_choice.set(RIM_CUSTOM); app.rim_custom.set("#40D857"); app._update_rim_swatch()
check("picker is raised when live", app._rim_swatch.cget("relief") == "raised",
      app._rim_swatch.cget("relief"))
app.rim_choice.set(RIM_SAME); app._update_rim_swatch()
check("picker is flat when it does nothing", app._rim_swatch.cget("relief") == "flat")
check("a display swatch is never raised", app._swatch.cget("relief") == "flat")
check("the silk swatch is never raised", app._silk_swatch.cget("relief") == "flat")
app.rim_custom.set("#40D857")

print("\n[2] rim colour resolution")
app.rim_choice.set(RIM_SAME)
check("Same as board -> None", app._rim_color() is None)
app.rim_choice.set(RIM_CREAM)
check("Cream -> (253,255,215)", app._rim_color() == (253, 255, 215), str(app._rim_color()))
app.rim_choice.set(RIM_CUSTOM); app.rim_custom.set("#40D857")
check("#40D857 -> (64,216,87)", app._rim_color() == (64, 216, 87), str(app._rim_color()))
app.rim_custom.set("")
check("Custom with empty field -> None (no crash)", app._rim_color() is None)
app.rim_custom.set("nonsense")
try:
    app._rim_color(); check("bad hex raises ValueError", False, "no raise")
except ValueError:
    check("bad hex raises ValueError", True)

print("\n[3] the tracked file is never written; settings go to the local one")
# The tracked file holds the shipped defaults and is under version control,
# while this window rewrites its settings every time it closes - a combination
# that guaranteed a conflict on every update and someone else's window position
# in every commit. It writes simple3d_config.local.json instead, which is
# merged over the defaults on read.
raw_before = cfg.read_text(encoding="utf-8")
before = json.loads(raw_before)
local_cfg = cfg.with_name(cfg.stem + ".local" + cfg.suffix)
app.rim_choice.set(RIM_CUSTOM); app.rim_custom.set("#123456")
app._save_config()
check("the tracked file is byte-identical",
      cfg.read_text(encoding="utf-8") == raw_before)
check("the local file was created", local_cfg.exists())
local = json.loads(local_cfg.read_text(encoding="utf-8"))
check("the edited value is in the local file",
      local["gui"]["boardEdgeCustom"] == "#123456",
      str(local["gui"].get("boardEdgeCustom")))
check("and the file says what it is", "_comment" in local)

# Read back through a fresh window: the merge is what the tool actually sees.
app_m = StepBuilderApp(cfg); app_m.withdraw()
check("the local value wins on read", app_m.rim_custom.get() == "#123456",
      app_m.rim_custom.get())
check("a default the local file does not mention still arrives",
      app_m.silk_color.get() == before["gui"]["silkColor"], app_m.silk_color.get())
app_m.destroy()

# The sections the SKILL half reads live in the base file and stay there.
after = json.loads(cfg.read_text(encoding="utf-8"))
check("all four sections survive", sorted(after) == sorted(before),
      f"{sorted(before)} -> {sorted(after)}")
check("silkscreen layer lists intact", after["silkscreen"] == before["silkscreen"])
check("allegro section intact", after["allegro"] == before["allegro"])
check("settings section intact", after["settings"] == before["settings"])
comments = [k for k in before["gui"] if k.startswith("_comment")]
check(f"comment keys kept in the defaults ({len(comments)})",
      all(k in after["gui"] for k in comments))

print("\n[4] a config that was unreadable at load is never written")
bad = TMP / "broken.json"
bad.write_text("{ this is not json", encoding="utf-8")
raw_before = bad.read_text(encoding="utf-8")
app2 = StepBuilderApp(bad); app2.withdraw()
check("load flagged a problem", app2._config_problem is not None)
app2._save_config()
check("broken file left byte-identical", bad.read_text(encoding="utf-8") == raw_before)
app2.destroy()

print("\n[4b] a LOCAL file that will not parse is never written over either")
# The same rule as the base file, and it has to be said twice because the
# window now writes a different file from the one it validates first. A local
# file someone hand-edited into invalid JSON holds their settings: overwriting
# it with what the widgets happen to show would destroy exactly the file the
# rule exists to protect.
pair_base = TMP / "pair.json"
pair_local = TMP / "pair.local.json"
pair_base.write_text(json.dumps({"gui": {"silkColor": "Black"}}), encoding="utf-8")
pair_local.write_text("{ half an edit", encoding="utf-8")
raw_local = pair_local.read_text(encoding="utf-8")
app5 = StepBuilderApp(pair_base); app5.withdraw()
check("the base still loads", app5._config_problem is None, str(app5._config_problem))
check("the broken local one is reported", app5._local_problem is not None)
app5._save_config()
check("and left byte-identical", pair_local.read_text(encoding="utf-8") == raw_local)
app5.destroy()

# Repaired, it applies and is written normally.
pair_local.write_text(json.dumps({"gui": {"silkColor": "White"}}), encoding="utf-8")
app6 = StepBuilderApp(pair_base); app6.withdraw()
check("a repaired local file loads", app6._local_problem is None)
check("and overrides the base", app6.silk_color.get() == "White", app6.silk_color.get())
app6.destroy()

print("\n[5] STEP folders: ordered multi-line search path")
app.set_step_dirs(["d:/lib/a", "d:/lib/b"])
check("reads back in order", app.step_dirs() == ["d:/lib/a", "d:/lib/b"], str(app.step_dirs()))
app.add_step_dir("d:/lib/c")
check("Add appends at the end", app.step_dirs()[-1] == "d:/lib/c", str(app.step_dirs()))
app.add_step_dir("d:/lib/a")
check("Add refuses a duplicate", app.step_dirs().count("d:/lib/a") == 1, str(app.step_dirs()))
app._step_text.delete("1.0", "end")
app._step_text.insert("1.0", "  d:/one  \n\n\n   \nd:/two\n")
check("blank lines and padding dropped", app.step_dirs() == ["d:/one", "d:/two"],
      str(app.step_dirs()))
check("snapshot carries a tuple", isinstance(app._snapshot().step_dirs, tuple))

print("\n[6] config: stepDirs written, the superseded stepDir is removed")
app.set_step_dirs(["d:/first", "d:/second"])
app._save_config()
saved = json.loads(local_cfg.read_text(encoding="utf-8"))["gui"]
check("stepDirs written as a list", saved["stepDirs"] == ["d:/first", "d:/second"],
      str(saved.get("stepDirs")))
check("stepDir gone from the file", "stepDir" not in saved,
      f"still present: {saved.get('stepDir')!r}")

print("\n[7] an old stepDir-only config migrates once, then the key is gone")
legacy = TMP / "legacy.json"
legacy.write_text(json.dumps({"gui": {"stepDir": "d:/legacy/lib"},
                              "settings": {"keepMe": 1}}), encoding="utf-8")
app3 = StepBuilderApp(legacy); app3.withdraw()
check("single stepDir becomes a one-entry list",
      app3.step_dirs() == ["d:/legacy/lib"], str(app3.step_dirs()))
app3._save_config()
legacy_local = legacy.with_name(legacy.stem + ".local" + legacy.suffix)
written = json.loads(legacy_local.read_text(encoding="utf-8"))
check("migrated into stepDirs", written["gui"]["stepDirs"] == ["d:/legacy/lib"],
      str(written["gui"].get("stepDirs")))
check("old key dropped from what is written",
      "stepDir" not in written["gui"], str(written["gui"].keys()))
# The old key stays in the base file, because nothing writes that file any
# more. Harmless: it is migrated again on every read and stepDirs wins.
check("the legacy file itself is untouched",
      json.loads(legacy.read_text(encoding="utf-8"))["settings"] == {"keepMe": 1})
app3.destroy()
app3b = StepBuilderApp(legacy); app3b.withdraw()
check("setting survives the reopen", app3b.step_dirs() == ["d:/legacy/lib"],
      str(app3b.step_dirs()))
app3b.destroy()
empty = TMP / "empty.json"
empty.write_text(json.dumps({"gui": {}}), encoding="utf-8")
app4 = StepBuilderApp(empty); app4.withdraw()
check("no key at all -> empty list, no crash", app4.step_dirs() == [], str(app4.step_dirs()))
app4.destroy()

print(chr(10) + "[7b] board mode + layer colours")
from stepbuilder.gui import _mode_key, _mode_label
app.board_mode.set(_mode_label("layers"))
check("mode round-trips through the label", _mode_key(app.board_mode.get()) == "layers")
check("snapshot carries the key, not the label", app._snapshot().board_mode == "layers")
app._update_layer_swatches()
check("swatches show their colour in 'layers'",
      app._swatches["copper"].cget("bg") == "#%02x%02x%02x" % app.layer_colors["copper"],
      app._swatches["copper"].cget("bg"))
app.board_mode.set(_mode_label("solid")); app._update_layer_swatches()
check("swatches greyed in any other mode",
      app._swatches["copper"].cget("bg") == "#d9d9d9", app._swatches["copper"].cget("bg"))
app.board_mode.set(_mode_label("layers"))
app.layer_colors["copper"] = (1, 2, 3)
app._save_config()
g = json.loads(local_cfg.read_text(encoding="utf-8"))["gui"]
check("boardMode saved as the key", g["boardMode"] == "layers", str(g.get("boardMode")))
check("layerColors saved as hex", g["layerColors"]["copper"] == "#010203",
      str(g["layerColors"].get("copper")))
check("superseded debugLayers dropped", "debugLayers" not in g, str(list(g)))
app5 = StepBuilderApp(cfg); app5.withdraw()
check("colour survives a reopen", app5.layer_colors["copper"] == (1, 2, 3),
      str(app5.layer_colors["copper"]))
check("mode survives a reopen", _mode_key(app5.board_mode.get()) == "layers")
app5.destroy()
legacy2 = TMP / "old_debug.json"
legacy2.write_text(json.dumps({"gui": {"debugLayers": True}}), encoding="utf-8")
app6 = StepBuilderApp(legacy2); app6.withdraw()
check("old debugLayers=true migrates to inspect",
      _mode_key(app6.board_mode.get()) == "inspect", app6.board_mode.get())
app6.destroy()

print(chr(10) + "[7d] folding flex bends")
check("on by default - a board with bend areas is meant to be seen folded",
      app.fold_bends.get() is True)
check("the snapshot carries it", app._snapshot().fold_bends is True)
app.fold_bends.set(False)
app._save_config()
g = json.loads(local_cfg.read_text(encoding="utf-8"))["gui"]
check("saved to the config", g["foldBends"] is False, str(g.get("foldBends")))
app7 = StepBuilderApp(cfg); app7.withdraw()
check("and survives a reopen", app7.fold_bends.get() is False)
app7.destroy()
# A config written before this existed must not silently start exporting flat.
legacy3 = TMP / "no_fold_key.json"
legacy3.write_text(json.dumps({"gui": {"boardColor": "Red"}}), encoding="utf-8")
app8 = StepBuilderApp(legacy3); app8.withdraw()
check("an older config with no key at all defaults to folding",
      app8.fold_bends.get() is True)
app8.destroy()
app.fold_bends.set(True)

print(chr(10) + "[7c] the rim controls only mean anything in Solid")
for mode, want in (("solid","readonly"),("layers","disabled"),("inspect","disabled")):
    app.board_mode.set(_mode_label(mode)); app._on_mode_changed()
    check(f"edge dropdown {want} in {mode}",
          str(app._rim_box.cget("state")) == want, str(app._rim_box.cget("state")))
app.board_mode.set(_mode_label("solid")); app._on_mode_changed()

print(chr(10) + "[7e] what the output file is called - one rule for both halves")
from stepbuilder.core import output_stem
NAMES = TMP / "names"
# Emptied first: the collision check below writes a .step, and a leftover from
# the previous run would make the FIRST dated name collide instead.
shutil.rmtree(NAMES, ignore_errors=True)
NAMES.mkdir()
one = NAMES / "board_a0.json"
# The rule the launcher relies on: the exporter lower-cases the filename, and
# --brd-name is what puts the board's own capitals back.
check("nothing given -> the JSON's own name is used",
      output_stem(one, NAMES) is None, str(output_stem(one, NAMES)))
check("a board name names the file, WITHOUT a date",
      output_stem(one, NAMES, brd_name="Board_A0") == "Board_A0",
      str(output_stem(one, NAMES, brd_name="Board_A0")))
dated = output_stem(one, NAMES, brd_name="Board_A0", dated=True)
check("with a date it is <brd>_simple_DD_MM_YYYY",
      dated.startswith("Board_A0_simple_") and len(dated.split("_")) == 6, str(dated))
(NAMES / f"{dated}.step").write_text("", encoding="utf-8")
check("and a second build the same day gets a trailing _",
      output_stem(one, NAMES, brd_name="Board_A0", dated=True) == dated + "_",
      str(output_stem(one, NAMES, brd_name="Board_A0", dated=True)))
# Several variants: one brd_name handed to all of them would collide, so each
# json's own stem (design_variant) has to win.
check("several variants ignore the board name and use their own stem",
      output_stem(one, NAMES, brd_name="Board_A0", several=True) is None
      and output_stem(one, NAMES, brd_name="Board_A0", several=True,
                      dated=True).startswith("board_a0_simple_"),
      str(output_stem(one, NAMES, brd_name="Board_A0", several=True, dated=True)))

print("\n[8] snapshot is complete and frozen")
snap = app._snapshot()
# Names, not a count: a bare number says "16 != 15" when a field is added and
# nothing about which one is missing.
EXPECTED = {"step_dirs","json_file","output_dir","z_datum","board_color",
            "rim_color","silk_top","silk_bottom","silk_color","silk_flat",
            "silk_flat_height","silk_layers_off","minimize","board_mode",
            "layer_colors","ignore_soldermask","fold_bends","fold_anchor",
            "fold_neutral","fold_slice_angle","brd_name","dated_name",
            "build_full_board"}
got = set(snap.__dataclass_fields__)
check("snapshot carries exactly the expected fields", got == EXPECTED,
      f"missing {EXPECTED-got}, unexpected {got-EXPECTED}")
try:
    snap.minimize = False; check("frozen", False, "mutation allowed")
except Exception:
    check("frozen (mutation refused)", True)

print("\n[9] the window is inert while a build runs")
# Pressing Generate used to leave every control live: paths, colors and
# checkboxes could be changed under a build that had already taken its snapshot,
# and Generate could be pressed again. What must NOT happen when it ends is the
# opposite mistake - re-enabling controls the window greys out by its own rules
# (the rim color outside Solid, a side's silk layers when that side is off).


def states():
    out = {}
    for w in app._walk():
        try:
            out[str(w)] = str(w.cget("state"))
        except Exception:
            pass                      # frames, canvases, ttk scrollbars
    return out


# A mode where the layer swatches actually carry colours, so dimming them is
# something to see rather than a no-op: plain Solid greys them by its own rule.
import stepbuilder.gui as gui_mod
app.board_mode.set("Solid colored layers")
app._on_mode_changed()
app.update_idletasks()

before = states()
preset = {k: v for k, v in before.items() if v != "normal"}
check("some controls are already not-normal before the build", len(preset) > 0,
      str(len(preset)))
swatch_bg_before = [str(c.cget("bg")) for c in
                    [app._swatch, app._rim_swatch, app._silk_swatch,
                     *app._swatches.values()]]
text_bg_before = str(app._step_text.cget("bg"))
check("the swatches are showing real colours to begin with",
      len(set(swatch_bg_before)) > 1, str(sorted(set(swatch_bg_before))))

app._set_busy(True)
busy = states()
live = [k for k, v in busy.items() if v == "normal"]
check("nothing is left enabled but the action button", len(live) == 1, str(live))
check("and that button now says Cancel",
      app.generate_button.cget("text") == "Cancel")
check("the log stays readable", app.log_view.winfo_exists()
      and str(app.log_view) not in live)      # disabled Text: read-only, scrollable
check("a swatch click does nothing while busy", app._busy is True)

# The two kinds of widget whose "disabled" has no LOOK. A tk.Text refuses edits
# and keeps its white field; a Canvas swatch keeps its colour whatever its
# state. Both then sit there bright while everything round them greys out, which
# is what the window was reported for.
swatches = [app._swatch, app._rim_swatch, app._silk_swatch, *app._swatches.values()]
check("every swatch is dimmed while busy",
      {str(c.cget("bg")) for c in swatches} == {gui_mod.INACTIVE_SWATCH},
      str(sorted({str(c.cget("bg")) for c in swatches})))
check("and none of them still offers a hand cursor",
      {str(c.cget("cursor")) for c in swatches} == {""})
check("the STEP paths field is greyed, not just read-only",
      str(app._step_text.cget("bg")) != text_bg_before
      and str(app._step_text.cget("state")) == "disabled",
      f"{app._step_text.cget('bg')} / {app._step_text.cget('state')}")

app._set_busy(False)
after = states()
check("the swatches come back to their own colours",
      [str(c.cget("bg")) for c in swatches] == swatch_bg_before,
      str([str(c.cget("bg")) for c in swatches]))
check("and the paths field to its own",
      str(app._step_text.cget("bg")) == text_bg_before)
check("every control comes back exactly as it was", after == before,
      str({k: (before[k], after.get(k)) for k in before if before[k] != after.get(k)}))
check("including the ones that were already disabled",
      all(after[k] == v for k, v in preset.items()))
check("and the button says Generate again",
      app.generate_button.cget("text") == "Generate")

# Cancel with nothing running must be a no-op rather than an error.
app._worker = None
app.on_cancel()
check("cancel with no build running is harmless",
      app.generate_button.cget("text") == "Generate")


# Cancelling a live build, with a stand-in for the process. Not the real thing:
# spawning one from a test on Windows re-imports this module and re-runs the
# whole file. What is checked here is this window's half of it - kill, restore,
# and above all DON'T then report the kill as a crash.
class _FakeWorker:
    def __init__(self):
        self.killed = False
        self.exitcode = -15

    def is_alive(self):
        return not self.killed

    def terminate(self):
        self.killed = True


fake = _FakeWorker()
app._worker = fake
app._set_busy(True)
app.on_cancel()
check("the build is terminated", fake.killed)
check("the window comes back", app.generate_button.cget("text") == "Generate")
check("and says so", app.status.get() == "Cancelled", app.status.get())
check("controls are usable again", states() == before)
# _check_worker_alive runs on the next drain and must stay quiet: a deliberate
# kill has a non-zero exit code, and reporting that as a crash would be a lie
# with a traceback attached.
app._worker, app._finished, app._cancelled = fake, False, True
app._check_worker_alive()
check("a cancelled build is not reported as a crash",
      app.status.get() == "Cancelled" and app._worker is None, app.status.get())

app.destroy()
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
