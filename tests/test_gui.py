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

print("\n[3] config round-trip preserves every section and comment key")
before = json.loads(cfg.read_text(encoding="utf-8"))
app.rim_choice.set(RIM_CUSTOM); app.rim_custom.set("#123456")
app._save_config()
after = json.loads(cfg.read_text(encoding="utf-8"))
check("all four sections survive", sorted(after) == sorted(before),
      f"{sorted(before)} -> {sorted(after)}")
check("silkscreen layer lists intact", after["silkscreen"] == before["silkscreen"])
check("allegro section intact", after["allegro"] == before["allegro"])
check("settings section intact", after["settings"] == before["settings"])
comments = [k for k in before["gui"] if k.startswith("_comment")]
check(f"comment keys kept ({len(comments)})",
      all(k in after["gui"] for k in comments))
check("edited value written", after["gui"]["boardEdgeCustom"] == "#123456",
      after["gui"].get("boardEdgeCustom"))

print("\n[4] a config that was unreadable at load is never written")
bad = TMP / "broken.json"
bad.write_text("{ this is not json", encoding="utf-8")
raw_before = bad.read_text(encoding="utf-8")
app2 = StepBuilderApp(bad); app2.withdraw()
check("load flagged a problem", app2._config_problem is not None)
app2._save_config()
check("broken file left byte-identical", bad.read_text(encoding="utf-8") == raw_before)
app2.destroy()

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
saved = json.loads(cfg.read_text(encoding="utf-8"))["gui"]
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
after = json.loads(legacy.read_text(encoding="utf-8"))
check("migrated into stepDirs", after["gui"]["stepDirs"] == ["d:/legacy/lib"],
      str(after["gui"].get("stepDirs")))
check("old key dropped", "stepDir" not in after["gui"], str(after["gui"].keys()))
check("other sections untouched by the migration", after["settings"] == {"keepMe": 1},
      str(after.get("settings")))
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
g = json.loads(cfg.read_text(encoding="utf-8"))["gui"]
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
g = json.loads(cfg.read_text(encoding="utf-8"))["gui"]
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

app.destroy()
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
