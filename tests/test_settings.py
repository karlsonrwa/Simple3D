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
import json
import sys

from stepbuilder import settings
from stepbuilder.settings import (
    GUI_KEYS, SUPERSEDED_KEYS, GuiSettings, load_gui_settings, save_gui_settings,
    local_config_path, RIM_CUSTOM, RIM_SAME,
)
from stepbuilder.colors import DEFAULT_LAYER_COLORS
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
# The shipped base carries stepDirs: [] (a list), so against it the local
# stepDir is NOT migrated - the window behaves the same, and that is why the
# migration matters only for a base file written before multi-folder support.
check("with the shipped base, an old local stepDir is simply dropped",
      "stepDir" not in g and "stepDirs" not in g, sorted(g))
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

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
