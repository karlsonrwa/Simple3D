# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, out_dir, fails, check

"""The window's settings section, read and written with no window at all.

Round 72 (plan C2) put the `gui` section behind one table, settings.GUI_KEYS,
and two functions that walk it. Until then every one of these rules could only
be exercised through a live Tk window (tests/test_gui.py still does that for
the widgets' side); here they are checked on the functions directly, which is
also where a new key's row gets its first test.
"""
import copy
import json
import os
import stat
import sys

from stepbuilder import settings
from stepbuilder.settings import (
    GUI_KEYS, SUPERSEDED_KEYS, GuiSettings, load_gui_settings, save_gui_settings,
    local_config_path, RIM_CREAM, RIM_CUSTOM, RIM_SAME,
)
from stepbuilder.colors import DEFAULT_LAYER_COLORS, DEFAULT_SILK, DEFAULT_THEME
from stepbuilder.core import DEFAULT_FLAT_HEIGHT
from stepbuilder.bend import DEFAULT_NEUTRAL_FACTOR, DEFAULT_SLICE_ANGLE

OUT = out_dir("settings")
SHIPPED = json.loads((ROOT / "simple3d_config.json").read_text(encoding="utf-8"))


def pair(name: str, base, local=None):
    """Write a base file (and a local one) under OUT; return the base path."""
    cfg = OUT / f"{name}.json"
    loc = local_config_path(cfg)
    if base is None:
        cfg.unlink(missing_ok=True)
    else:
        cfg.write_text(base if isinstance(base, str) else json.dumps(base, indent=1),
                       encoding="utf-8")
    if local is None:
        loc.unlink(missing_ok=True)
    else:
        loc.write_text(local if isinstance(local, str) else json.dumps(local, indent=1),
                       encoding="utf-8")
    return cfg


def gui_of(cfg):
    return json.loads(local_config_path(cfg).read_text(encoding="utf-8"))["gui"]


print("\n[1] the table describes exactly the shipped section")
shipped_keys = {k for k in SHIPPED["gui"] if not k.startswith("_comment")}
table_keys = {k.name for k in GUI_KEYS}
check("every shipped gui key has a row, and no row lacks a shipped key",
      table_keys == shipped_keys,
      f"only in table {table_keys - shipped_keys}, only in file {shipped_keys - table_keys}")
check("every row names a distinct GuiSettings field",
      {k.field for k in GUI_KEYS} == set(GuiSettings.__dataclass_fields__)
      and len({k.field for k in GUI_KEYS}) == len(GUI_KEYS))
check("the superseded keys are not rows", not set(SUPERSEDED_KEYS) & table_keys)

print("\n[2] an empty, missing or malformed section gives the defaults")
s, base_problem, local_problem = load_gui_settings(pair("empty", {"gui": {}}))
check("no problems", base_problem is None and local_problem is None,
      (base_problem, local_problem))
check("board mode solid", s.board_mode == "solid")
check("no anchor, default neutral and slice",
      s.fold_anchor is None and s.fold_neutral == DEFAULT_NEUTRAL_FACTOR
      and s.fold_slice_angle == DEFAULT_SLICE_ANGLE)
check("layer colours are the defaults, as a copy",
      s.layer_colors == DEFAULT_LAYER_COLORS and s.layer_colors is not DEFAULT_LAYER_COLORS)
check("no folders, no layers off, normal window",
      s.step_dirs == [] and s.layers_off == set() and s.window_geometry is None
      and s.window_state == "normal")
check("flat height default", s.silk_flat_height == DEFAULT_FLAT_HEIGHT)
check("the legend from the drawn layers (round 112)", s.silk_source == "drawn", s.silk_source)
check("rim is Same as board", s.rim_choice == RIM_SAME)
s2, _, _ = load_gui_settings(pair("nope", {"gui": "not an object"}))
check("a section that is not an object reads as empty", s2 == s)
s3, problem, _ = load_gui_settings(pair("missing", None))
check("a missing base file is a problem, and still the defaults",
      problem is not None and "not found" in problem and s3 == s, problem)
_, _, lp = load_gui_settings(pair("badlocal", {"gui": {}}, "{ half"))
check("an unparsable local file is a problem of its own", lp is not None and "JSON" in lp, lp)

print("\n[3] the two migrations")
s, _, _ = load_gui_settings(pair("m1", {"gui": {"stepDir": " d:/legacy "}}))
check("stepDir becomes a one-entry stepDirs, stripped", s.step_dirs == ["d:/legacy"], s.step_dirs)
s, _, _ = load_gui_settings(pair("m2", {"gui": {"stepDir": "d:/old", "stepDirs": ["d:/new", " "]}}))
check("stepDirs wins when both exist, blanks dropped", s.step_dirs == ["d:/new"], s.step_dirs)
s, _, _ = load_gui_settings(pair("m3", {"gui": {"debugLayers": True}}))
check("debugLayers true -> inspect", s.board_mode == "inspect")
s, _, _ = load_gui_settings(pair("m4", {"gui": {"debugLayers": True, "boardMode": "layers"}}))
check("a valid boardMode wins over debugLayers", s.board_mode == "layers")
s, _, _ = load_gui_settings(pair("m5", {"gui": {"boardMode": "bogus"}}))
check("an unknown mode falls back to solid", s.board_mode == "solid")
s, _, _ = load_gui_settings(pair("m6", {"gui": {}}, {"gui": {"stepDir": "d:/from/local"}}))
check("the migration also reads the local file", s.step_dirs == ["d:/from/local"])

print("\n[4] hand-edited values that do not parse fall back, never fail")
s, _, _ = load_gui_settings(pair("g1", {"gui": {
    "foldNeutral": "abc", "foldSliceAngle": 200, "silkscreenFlatHeight": -0.01,
    "layerColors": {"copper": "zzz", "unknown": "#000000", "base": "#010203"},
    "silkscreenLayersOff": "notalist", "windowGeometry": 12, "windowState": "sideways",
    "foldAnchor": " AUTO "}}))
check("neutral outside 0..1 or unreadable -> default", s.fold_neutral == DEFAULT_NEUTRAL_FACTOR)
check("slice angle outside 0.5..90 -> default", s.fold_slice_angle == DEFAULT_SLICE_ANGLE)
check("flat height is made positive", s.silk_flat_height == 0.01)
check("a bad colour keeps the default, an unknown kind is ignored, a good one applies",
      s.layer_colors["copper"] == DEFAULT_LAYER_COLORS["copper"]
      and "unknown" not in s.layer_colors and s.layer_colors["base"] == (1, 2, 3))
check("layers off must be a list", s.layers_off == set())
check("geometry must be a string", s.window_geometry is None)
check("window state is normal unless exactly zoomed", s.window_state == "normal")
check("anchor 'auto' in any case and padding", s.fold_anchor == "auto")
s, _, _ = load_gui_settings(pair("g2", {"gui": {"foldAnchor": [1, 2.5, 9], "foldNeutral": 1,
                                                 "windowState": "zoomed", "foldSliceAngle": 0.5}}))
check("anchor list -> tuple of two floats", s.fold_anchor == (1.0, 2.5))
check("neutral 1 (an int) is accepted", s.fold_neutral == 1.0)
check("zoomed is remembered", s.window_state == "zoomed")
check("slice angle at the bound is accepted", s.fold_slice_angle == 0.5)
s, _, _ = load_gui_settings(pair("g3", {"gui": {"foldAnchor": [1], "foldNeutral": 1.5}}))
check("a one-element anchor is no anchor", s.fold_anchor is None)
s, _, _ = load_gui_settings(pair("g3s", {"gui": {"silkscreenSource": " AutoSilk "}}))
check("the legend source in any case and padding, spelled as the table spells it",
      s.silk_source == "autosilk", s.silk_source)
s, _, _ = load_gui_settings(pair("g3t", {"gui": {"silkscreenSource": "both"}}))
check("a legend source that is neither falls back to the drawn layers", s.silk_source == "drawn",
      s.silk_source)
check("neutral above 1 -> default", s.fold_neutral == DEFAULT_NEUTRAL_FACTOR)

print("\n[5] what a save writes, and when it writes nothing")
cfg = pair("s1", SHIPPED, {"gui": {"stepDir": "d:/old", "debugLayers": True,
                                    "_comment_mine": "hi", "someoneElses": 5,
                                    "silkColor": "Black"},
                           "other": {"k": 1}, "_comment": "kept as is"})
s, bp, lp = load_gui_settings(cfg)
s.rim_choice, s.rim_custom = RIM_CUSTOM, "#123456"
s.layers_off = {"SILK_X", "SILK_A"}
s.layer_colors = dict(s.layer_colors, copper=(1, 2, 3))
s.fold_anchor = (3.0, 4.0)
s.json_file, s.output_dir = "c:/x/b.json", "c:/x/out"
save_gui_settings(cfg, s, paths_from_launcher=False, loaded_cleanly=True)
doc = json.loads(local_config_path(cfg).read_text(encoding="utf-8"))
g = doc["gui"]
check("the base file is untouched",
      json.loads(cfg.read_text(encoding="utf-8")) == SHIPPED)
check("the superseded keys are dropped", not set(SUPERSEDED_KEYS) & set(g), sorted(g))
check("a stranger's key, a comment and another section survive",
      g.get("someoneElses") == 5 and g.get("_comment_mine") == "hi" and doc["other"] == {"k": 1}
      and doc["_comment"] == "kept as is")
check("a value equal to the shipped default is not written", "zDatum" not in g and "foldBends" not in g)
check("a local value that still differs from the shipped one stays", g.get("silkColor") == "Black")
check("what differs is written, in the file's shapes",
      g["boardEdge"] == RIM_CUSTOM and g["boardEdgeCustom"] == "#123456"
      and g["silkscreenLayersOff"] == ["SILK_A", "SILK_X"]
      and g["layerColors"]["copper"] == "#010203" and g["foldAnchor"] == [3.0, 4.0])
check("the paths are written when the user picked them",
      g["jsonFile"] == "c:/x/b.json" and g["outputDir"] == "c:/x/out")
# The shipped base carries stepDirs: [] and boardMode "solid", and a local
# file's old keys still win over them: each file is migrated before the two
# are merged (review 28.10.2026, R6-4; until round 107 this check said the
# old local stepDir was "simply dropped" - the finding itself).
check("with the shipped base, an old local stepDir is written as stepDirs",
      "stepDir" not in g and g.get("stepDirs") == ["d:/old"]
      and g.get("boardMode") == "inspect", sorted(g))
legacy = pair("s1_legacy", {"gui": {"stepDir": "d:/legacy/lib"}, "settings": {"keepMe": 1}})
ls, _, _ = load_gui_settings(legacy)
save_gui_settings(legacy, ls, paths_from_launcher=False, loaded_cleanly=True)
lg = gui_of(legacy)
check("against a legacy base the migrated list is written as stepDirs",
      lg.get("stepDirs") == ["d:/legacy/lib"] and "stepDir" not in lg, sorted(lg))
check("and the legacy base file itself is untouched",
      json.loads(legacy.read_text(encoding="utf-8")) == {"gui": {"stepDir": "d:/legacy/lib"},
                                                          "settings": {"keepMe": 1}})
s.silk_color = SHIPPED["gui"]["silkColor"]
save_gui_settings(cfg, s, paths_from_launcher=False, loaded_cleanly=True)
check("set back to the shipped value, a local key is REMOVED rather than pinned",
      "silkColor" not in gui_of(cfg), sorted(gui_of(cfg)))

save_gui_settings(cfg, s, paths_from_launcher=True, loaded_cleanly=True)
g = gui_of(cfg)
check("paths from Allegro are not a setting: left as the file had them",
      g["jsonFile"] == "c:/x/b.json" and g["outputDir"] == "c:/x/out")
s.json_file = "c:/other.json"
save_gui_settings(cfg, s, paths_from_launcher=True, loaded_cleanly=True)
check("and a changed path is not written over them either",
      gui_of(cfg)["jsonFile"] == "c:/x/b.json")

before = local_config_path(cfg).read_bytes()
save_gui_settings(cfg, s, paths_from_launcher=False, loaded_cleanly=False)
check("nothing is written when the load had a problem",
      local_config_path(cfg).read_bytes() == before)
local_config_path(cfg).write_text("{ broken now", encoding="utf-8")
save_gui_settings(cfg, s, paths_from_launcher=False, loaded_cleanly=True)
check("nor over a local file that no longer parses",
      local_config_path(cfg).read_text(encoding="utf-8") == "{ broken now")
check("no temporary file is left behind",
      not local_config_path(cfg).with_suffix(".json.tmp").exists())

cfg2 = pair("s2", SHIPPED)
s, _, _ = load_gui_settings(cfg2)
save_gui_settings(cfg2, s, paths_from_launcher=False, loaded_cleanly=True)
doc = json.loads(local_config_path(cfg2).read_text(encoding="utf-8"))
check("a fresh local file gets the explanatory comment", "_comment" in doc
      and "not tracked by git" in doc["_comment"])
check("and, with nothing changed, only the empty-string paths and no other key",
      set(doc["gui"]) <= {"jsonFile", "outputDir"}, sorted(doc["gui"]))

print("\n[6] the keys land in table order, and a round trip is exact")
cfg3 = pair("s3", {"gui": {}})
s, _, _ = load_gui_settings(cfg3)
s.step_dirs = ["d:/a", "d:/b"]
s.z_datum, s.theme, s.rim_choice, s.rim_custom = "bottom", "Blue", RIM_CUSTOM, "#ABCDEF"
s.silk_top, s.silk_bottom, s.silk_color, s.silk_flat = False, False, "Black", True
s.silk_flat_height, s.layers_off = 0.005, {"L2", "L1"}
s.minimize, s.build_full, s.board_mode = False, False, "inspect"
s.layer_colors = dict(s.layer_colors, base=(9, 8, 7))
s.ignore_soldermask, s.fold_bends = True, False
s.fold_anchor, s.fold_neutral, s.fold_slice_angle = "auto", 0.25, 5.0
s.window_geometry, s.window_state = "800x600+10+20", "zoomed"
s.json_file, s.output_dir = "j.json", "out"
save_gui_settings(cfg3, s, paths_from_launcher=False, loaded_cleanly=True)
written = list(gui_of(cfg3))
check("every key written (the base has no gui to diff against)",
      set(written) == {k.name for k in GUI_KEYS}, sorted(set(written) ^ {k.name for k in GUI_KEYS}))
check("in the order of the table", written == [k.name for k in GUI_KEYS], written)
back, _, _ = load_gui_settings(cfg3)
check("and reading it back gives the same settings", back == s,
      {f: (getattr(s, f), getattr(back, f)) for f in GuiSettings.__dataclass_fields__
       if getattr(s, f) != getattr(back, f)})

print("\n[7] settings.py is what the window uses")
src = (ROOT / "stepbuilder/gui.py").read_text(encoding="utf-8")
check("the window loads through the table", "settings.load_gui_settings(" in src)
check("and saves through it", "settings.save_gui_settings(" in src)
check("no gui.get(...) reads of the section remain in the window",
      'gui.get("' not in src)
check("the rim labels come from settings", src.count('"Same as board"') == 0
      and settings.RIM_SAME == "Same as board")

print("\n[8] a close writes what the window changed and leaves the rest as the file has it")
# The independent review of 23.10.2026 (R6-1, R6-2, R6-3): a close rewrote every
# gui key from the values read at start-up, so a hand edit made while the window
# was open, everything the first of two windows changed, a value the loader
# could not read and an exclusion for a layer the shown board does not carry
# were all lost. tests/test_gui.py [R] runs the same cases through a real close.


def window_save(cfg, values, loaded):
    """What the window's close does since round 95: it hands over what it loaded."""
    try:
        save_gui_settings(cfg, values, paths_from_launcher=False, loaded_cleanly=True,
                          loaded=loaded)
    except TypeError:   # a build without `loaded` rewrites every key - what these checks catch
        save_gui_settings(cfg, values, paths_from_launcher=False, loaded_cleanly=True)


ext = pair("w1", SHIPPED, {"gui": {"stepDirs": ["D:/lib/old"]}})
s0, _, _ = load_gui_settings(ext)
s = copy.deepcopy(s0)
s.window_geometry = "900x700+10+10"
local_config_path(ext).write_text(json.dumps({"gui": {
    "stepDirs": ["D:/lib/new", "D:/lib/old"], "foldNeutral": 0, "boardColor": "Red"}}),
    encoding="utf-8")
window_save(ext, s, s0)
g = gui_of(ext)
check("a hand edit made while the window was open survives its close",
      g.get("stepDirs") == ["D:/lib/new", "D:/lib/old"] and g.get("foldNeutral") == 0
      and g.get("boardColor") == "Red", g)
check("and what the window did change is written", g.get("windowGeometry") == "900x700+10+10", g)

two = pair("w2", SHIPPED, {"gui": {}})
s0, _, _ = load_gui_settings(two)
first, last = copy.deepcopy(s0), copy.deepcopy(s0)
first.theme, first.fold_bends = "Blue", False
last.silk_color = "Black"
window_save(two, first, s0)
window_save(two, last, s0)
g = gui_of(two)
check("two windows: the one closed last keeps what the first one changed",
      g.get("boardColor") == "Blue" and g.get("foldBends") is False
      and g.get("silkColor") == "Black", g)

red = pair("w3", SHIPPED, {"gui": {"boardColor": "Red"}})
s0, _, _ = load_gui_settings(red)
s = copy.deepcopy(s0)
s.theme = SHIPPED["gui"]["boardColor"]
window_save(red, s, s0)
check("a value the window sets back to the shipped one is still removed",
      "boardColor" not in gui_of(red), gui_of(red))

typed = pair("w4", SHIPPED, {"gui": {"stepDirs": "D:/models/lib", "foldAnchor": "10,20",
                                      "silkscreenLayersOff": "MANUFACTURING/AUTOSILK_TOP"}})
s0, _, _ = load_gui_settings(typed)
check("a value the loader cannot read still falls back in the window",
      s0.step_dirs == [] and s0.layers_off == set() and s0.fold_anchor is None)
window_save(typed, copy.deepcopy(s0), s0)
g = gui_of(typed)
check("and is left in the file as it was, not erased",
      g.get("stepDirs") == "D:/models/lib" and g.get("foldAnchor") == "10,20"
      and g.get("silkscreenLayersOff") == "MANUFACTURING/AUTOSILK_TOP", g)
unreadable = getattr(settings, "unreadable_keys", None)
notes = unreadable(typed) if unreadable else []
check("the keys that could not be read are named, for the log",
      all(any(name in note for note in notes)
          for name in ("stepDirs", "foldAnchor", "silkscreenLayersOff")), notes)
check("the shipped file has nothing unreadable in it",
      unreadable is not None and unreadable(pair("w5", SHIPPED)) == [],
      unreadable(pair("w5", SHIPPED)) if unreadable else "no unreadable_keys")
good = pair("w6", SHIPPED, {"gui": {"stepDirs": ["d:/x"], "foldAnchor": "auto",
                                     "silkscreenLayersOff": [], "foldNeutral": "0.5"}})
check("nor does a readable hand edit", unreadable is not None and unreadable(good) == [],
      unreadable(good) if unreadable else "no unreadable_keys")
s = copy.deepcopy(s0)
s.step_dirs = ["d:/chosen"]
window_save(typed, s, s0)
check("a value the window then changes is written as chosen",
      gui_of(typed).get("stepDirs") == ["d:/chosen"], gui_of(typed))

merge = getattr(settings, "merge_layers_off", None)
check("exclusions for layers the panel does not show are kept",
      merge is not None and merge({"MANUFACTURING/AUTOSILK_TOP", "SILK_B"},
                                  ["SILK_A", "SILK_B", "SILK_C"], {"SILK_B"})
      == {"MANUFACTURING/AUTOSILK_TOP", "SILK_B"})
check("a shown layer follows its tick: unticked joins, ticked leaves",
      merge is not None and merge({"AUTO", "SILK_B"}, ["SILK_A", "SILK_B"], {"SILK_A"})
      == {"AUTO", "SILK_A"})
check("with no rows shown the remembered set stands",
      merge is not None and merge({"X"}, [], set()) == {"X"})

print("\n[9] one colour at a time, a key changed twice, every key read, old keys in the local file")
# The review's second round (28.10.2026). R6-3: layerColors was written as one
# dict, so of two windows the later one's colours won and a colour edited by hand
# while the window was open was undone; and a hand edit of a key the window then
# changed too lost to it without a word. R6-1, R6-2: a key with no loader went to
# the window as the file had it - a flag "maybe" stopped the window opening, a
# board colour it has no swatch for built in the default with nothing in the log.
# R6-4: stepDir / debugLayers in the LOCAL file were never migrated, because the
# shipped file's own stepDirs / boardMode came first. tests/test_gui.py [R] runs
# the same cases through a real close.


def window_save_notes(cfg, values, loaded):
    """window_save, and what it says about values it wrote over (round 107)."""
    notes = save_gui_settings(cfg, values, paths_from_launcher=False, loaded_cleanly=True,
                              loaded=loaded)
    return notes if isinstance(notes, list) else []


two = pair("x1", SHIPPED, {"gui": {}})
s0, _, _ = load_gui_settings(two)
a, b = copy.deepcopy(s0), copy.deepcopy(s0)
a.layer_colors = dict(a.layer_colors, copper=(1, 2, 3))
b.layer_colors = dict(b.layer_colors, stiffener=(4, 5, 6))
window_save(two, a, s0)
window_save(two, b, s0)
lc = gui_of(two).get("layerColors", {})
check("two windows: each keeps the colour it changed",
      lc.get("copper") == "#010203" and lc.get("stiffener") == "#040506", lc)
check("and only the changed colours are in the local file", set(lc) == {"copper", "stiffener"}, lc)

hand = pair("x2", SHIPPED, {"gui": {}})
s0, _, _ = load_gui_settings(hand)
s = copy.deepcopy(s0)
s.layer_colors = dict(s.layer_colors, copper=(1, 2, 3))
local_config_path(hand).write_text(json.dumps({"gui": {"layerColors": {"stiffener": "#010101"}}}),
                                   encoding="utf-8")
window_save(hand, s, s0)
lc = gui_of(hand).get("layerColors", {})
check("a colour edited by hand while the window was open survives its close",
      lc.get("stiffener") == "#010101" and lc.get("copper") == "#010203", lc)

back = pair("x3", SHIPPED, {"gui": {"layerColors": {"copper": "#010203", "base": "#020304"}}})
s0, _, _ = load_gui_settings(back)
s = copy.deepcopy(s0)
s.layer_colors = dict(s.layer_colors, copper=DEFAULT_LAYER_COLORS["copper"])
window_save(back, s, s0)
check("a colour set back to the shipped one leaves the local file, the others stay",
      gui_of(back).get("layerColors") == {"base": "#020304"}, gui_of(back))

same = pair("x4", SHIPPED, {"gui": {"stepDirs": ["D:/lib/old"]}})
s0, _, _ = load_gui_settings(same)
s = copy.deepcopy(s0)
s.step_dirs = ["D:/lib/old", "D:/lib/added-in-window"]
local_config_path(same).write_text(json.dumps({"gui": {"stepDirs": ["D:/lib/hand-edit"]}}),
                                   encoding="utf-8")
notes = window_save_notes(same, s, s0)
check("a key changed by hand and in the window: the window's value is written",
      gui_of(same).get("stepDirs") == ["D:/lib/old", "D:/lib/added-in-window"], gui_of(same))
check("and what the file held is named, so it can be put back",
      len(notes) == 1 and "stepDirs" in notes[0] and "D:/lib/hand-edit" in notes[0], notes)

clash = pair("x5", SHIPPED, {"gui": {}})
s0, _, _ = load_gui_settings(clash)
a, b = copy.deepcopy(s0), copy.deepcopy(s0)
a.layer_colors = dict(a.layer_colors, copper=(1, 2, 3))
b.layer_colors = dict(b.layer_colors, copper=(9, 9, 9))
window_save_notes(clash, a, s0)
notes = window_save_notes(clash, b, s0)
check("one colour changed in two windows: the later one is written, the earlier named",
      gui_of(clash).get("layerColors", {}).get("copper") == "#090909" and len(notes) == 1
      and "layerColors.copper" in notes[0] and "#010203" in notes[0], notes)

place = pair("x6", SHIPPED, {"gui": {}})
s0, _, _ = load_gui_settings(place)
a, b = copy.deepcopy(s0), copy.deepcopy(s0)
a.window_geometry, a.json_file, a.theme = "800x600+10+10", "d:/a.json", "Blue"
b.window_geometry, b.json_file, b.silk_color = "800x600+500+10", "d:/b.json", "Black"
first_notes = window_save_notes(place, a, s0)
notes = window_save_notes(place, b, s0)
g = gui_of(place)
check("two windows: the last one's place and paths are written without a note",
      first_notes == [] and notes == [] and g.get("windowGeometry") == "800x600+500+10"
      and g.get("jsonFile") == "d:/b.json", (first_notes, notes, g))
check("and each window's other change is kept",
      g.get("boardColor") == "Blue" and g.get("silkColor") == "Black", g)

flags = [k.name for k in GUI_KEYS if isinstance(k.default, bool)]
check("nine flags in the table", len(flags) == 9, flags)
odd = pair("x7", SHIPPED, {"gui": dict({name: "maybe" for name in flags},
                                        boardColor=5, silkColor="Red", zDatum=1,
                                        boardEdge="Purple", boardEdgeCustom=7, jsonFile=None)})
s, _, _ = load_gui_settings(odd)
check("a flag the window cannot read is its default",
      all(getattr(s, k.field) is k.default for k in GUI_KEYS if k.name in flags),
      {k.name: getattr(s, k.field) for k in GUI_KEYS if k.name in flags})
check("so are a board colour, an ink, a datum, a rim and a path it cannot use",
      s.theme == DEFAULT_THEME and s.silk_color == DEFAULT_SILK and s.z_datum == "top"
      and s.rim_choice == RIM_SAME and s.rim_custom == "" and s.json_file == "",
      (s.theme, s.silk_color, s.z_datum, s.rim_choice, s.rim_custom, s.json_file))
named = {note.split(" = ")[0] for note in settings.unreadable_keys(odd)}
check("and every one of them is named for the log",
      named >= set(flags) | {"boardColor", "silkColor", "zDatum", "boardEdge",
                             "boardEdgeCustom", "jsonFile"}, sorted(named))

fine = pair("x8", SHIPPED, {"gui": {
    "silkscreenTop": "no", "silkscreenBottom": 0, "foldBends": "YES", "exposedCopper": 1,
    "silkscreenFlat": "no", "ignoreSoldermask": " False ",
    "zDatum": "Bottom", "boardColor": "blue", "silkColor": " black ",
    "boardEdge": "cream (dielectric)"}})
s, _, _ = load_gui_settings(fine)
check("a flag written by hand as 0/1, yes/no or true/false, in any case, reads as meant",
      s.silk_top is False and s.silk_bottom is False and s.fold_bends is True
      and s.exposed_copper is True and s.silk_flat is False and s.ignore_soldermask is False,
      (s.silk_top, s.silk_bottom, s.fold_bends, s.exposed_copper, s.silk_flat,
       s.ignore_soldermask))
check("a choice in another case, or padded, reads as its name",
      s.z_datum == "bottom" and s.theme == "Blue" and s.silk_color == "Black"
      and s.rim_choice == RIM_CREAM, (s.z_datum, s.theme, s.silk_color, s.rim_choice))
check("and none of them is reported", settings.unreadable_keys(fine) == [],
      settings.unreadable_keys(fine))

bad = pair("x9", SHIPPED, {"gui": {"layerColors": {"copper": "zzz", "notAKind": "#000000",
                                                   "base": "#fcffd6"}}})
check("a colour of a known kind that does not parse is named by its kind; a kind this "
      "build does not know and the shipped colour in lower case are not",
      [n.split(" = ")[0] for n in settings.unreadable_keys(bad)] == ["layerColors.copper"],
      settings.unreadable_keys(bad))

old_local = pair("x10", SHIPPED, {"gui": {"stepDir": "D:/models/lib", "debugLayers": True}})
s, _, _ = load_gui_settings(old_local)
check("an old stepDir / debugLayers in the LOCAL file wins over the shipped "
      "stepDirs / boardMode", s.step_dirs == ["D:/models/lib"] and s.board_mode == "inspect",
      (s.step_dirs, s.board_mode))
window_save(old_local, copy.deepcopy(s), s)
g = gui_of(old_local)
check("and the close writes them under the new keys and drops the old ones",
      g.get("stepDirs") == ["D:/models/lib"] and g.get("boardMode") == "inspect"
      and "stepDir" not in g and "debugLayers" not in g, g)
s, _, _ = load_gui_settings(pair("x11", {"gui": {"stepDirs": ["d:/shipped"]}},
                                 {"gui": {"stepDir": "d:/old", "stepDirs": ["d:/new"]}}))
check("within one file the new key still wins", s.step_dirs == ["d:/new"], s.step_dirs)

kept = pair("x12", SHIPPED, {"gui": {}, "mine": 1})
s0, _, _ = load_gui_settings(kept)
s = copy.deepcopy(s0)
s.theme = "Blue"
window_save(kept, s, s0)
doc = json.loads(local_config_path(kept).read_text(encoding="utf-8"))
check("a local file that exists without a _comment does not get one",
      "_comment" not in doc and doc.get("mine") == 1, sorted(doc))

ro = pair("x13", SHIPPED, {"gui": {"stepDirs": ["D:/lib/old"]}})
s0, _, _ = load_gui_settings(ro)
s = copy.deepcopy(s0)
s.step_dirs = ["D:/lib/window"]
local_config_path(ro).write_text(json.dumps({"gui": {"stepDirs": ["D:/lib/hand"]}}),
                                 encoding="utf-8")
os.chmod(local_config_path(ro), stat.S_IREAD)
try:
    notes = window_save_notes(ro, s, s0)
finally:
    os.chmod(local_config_path(ro), stat.S_IREAD | stat.S_IWRITE)
check("a local file that cannot be written: nothing is written, and nothing said to be",
      notes == [] and gui_of(ro).get("stepDirs") == ["D:/lib/hand"], (notes, gui_of(ro)))

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
