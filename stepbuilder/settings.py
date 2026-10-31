"""The settings pair - the shipped defaults and this installation's local file -
and the window's section of it, read and written without a widget in sight.

`simple3d_config.json` beside the package is tracked by git and holds the
shipped defaults, for both halves of the tool (the SKILL side reads
`allegro`, `silkscreen` and `settings`; the window reads `gui`).
`simple3d_config.local.json` beside it is gitignored and holds whatever this
installation does differently; it is the ONLY file the window writes. Both
halves read the pair merged, key by key, the local one on top - and the
SKILL side's `s3dJsonMerge` has to agree with `merge_config` here about what
"on top" means (tests/test_config_merge.py runs both over the same cases).

The `gui` section is described ONCE, in `GUI_KEYS`: the key's name in the
file, its field on `GuiSettings`, what an absent key means, and - where the
file's shape is not the program's - how to read it and how to write it.
`load_gui_settings` and `save_gui_settings` walk that table, so adding a
setting is one row plus the widget that shows it. Every key is read through
`Key.read`, so a value the window cannot hold never reaches it (round 107).
The two migrations (`stepDir` -> `stepDirs`, `debugLayers` -> `boardMode`)
are done in each file before the two are merged (`_migrated`), and the saver
drops the old keys.

Rounds 72 (plans C1, C2). Importing this module loads neither OpenCASCADE
nor Tk: the three default numbers (`DEFAULT_FLAT_HEIGHT`,
`DEFAULT_NEUTRAL_FACTOR`, `DEFAULT_SLICE_ANGLE`) come from defaults.py, which
needs neither (round 80). The merge and the reader above the table are what
another tool would copy.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .colors import (BOARD_THEMES, DEFAULT_LAYER_COLORS, DEFAULT_SILK, DEFAULT_THEME,
                     SILK_COLORS, parse_hex)
from .defaults import DEFAULT_FLAT_HEIGHT, DEFAULT_NEUTRAL_FACTOR, DEFAULT_SLICE_ANGLE

# Every user-facing setting lives in ONE file, simple3d_config.json, shared with
# the SKILL side - which is why it sits next to the package rather than in the
# home directory. The launcher passes its path with --config; run standalone,
# the package's own folder is the documented install layout.
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "simple3d_config.json"

# The rim (board edge) choices, as the file stores them - the label IS the value.
RIM_SAME = "Same as board"
RIM_CREAM = "Cream (dielectric)"
RIM_CUSTOM = "Custom..."

# How the board body is built; the window pairs these with its labels. The
# list itself is build.BOARD_MODES, which generate validates against.
from .build import BOARD_MODES as BOARD_MODE_KEYS  # noqa: E402
# Where the legend comes from; build.SILK_SOURCES is what generate validates.
from .build import SILK_SOURCES  # noqa: E402


# --------------------------------------------------------------------------- #
# the pair
# --------------------------------------------------------------------------- #

def merge_config(base: dict, over: dict) -> dict:
    """*base* with *over* laid on top, key by key, nested dicts merged.

    Anything that is not a dict is REPLACED whole - a list from the local file
    wins entirely, which is the only reading that lets it shorten one. Presence
    of the key decides, never its truthiness: false is a setting, and a test
    like `if value:` would drop exactly the overrides that switch things off.
    """
    out = dict(base)
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_config(out[key], value)
        else:
            out[key] = value
    return out


def local_config_path(config_path: Path) -> Path:
    """simple3d_config.json -> simple3d_config.local.json, beside it.

    The tracked file holds the shipped defaults; this one holds whatever this
    installation does differently, and it is the ONLY one the window writes.
    That is what keeps an update from either conflicting with your model
    folders or overwriting them - and keeps your absolute paths, and the
    position of your window, out of every commit.
    """
    config_path = Path(config_path)
    return config_path.with_name(config_path.stem + ".local" + config_path.suffix)


def read_config_file(path: Path, missing_ok: bool = False) -> tuple[dict, str | None]:
    """(document, problem). *problem* is None only when the file read cleanly.

    The distinction matters more than it looks: treating "could not read" as
    "empty" is what let a save write a document containing nothing but the
    "gui" section, destroying the silkscreen layer lists and the Allegro
    settings alongside it. Nothing may be written unless the existing file
    was understood first.

    missing_ok is for the LOCAL file: not having one is the ordinary state
    of a fresh clone, not a problem to report and certainly not a reason to
    refuse to write one.

    Read as utf-8-sig, so a file an editor saved with a BOM still parses -
    that alone is enough to make json.loads fail on otherwise valid JSON.
    """
    path = Path(path)
    if not path.exists():
        return {}, None if missing_ok else f"settings file not found: {path}"
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return {}, f"cannot read {path}: {exc}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return {}, f"{path.name} is not valid JSON: {exc}"
    if not isinstance(data, dict):
        return {}, f"{path.name} does not hold a JSON object"
    return data, None


# --------------------------------------------------------------------------- #
# the window's section
# --------------------------------------------------------------------------- #

@dataclass
class GuiSettings:
    """The `gui` section as the program holds it - plain values, no Tk.

    Every field is what its key's `Key.read` made of the file's value: a flag
    is a bool, a choice one of its names, a text a string, whatever the file
    held (until round 107 the simple keys carried the file's value as it was,
    and the window's Tk variables were left to coerce it). `board_mode` is the
    KEY ("solid"), not the dropdown's label.
    """

    step_dirs: list[str]
    z_datum: str
    theme: str
    rim_choice: str
    rim_custom: str
    silk_top: bool
    silk_bottom: bool
    silk_color: str
    silk_flat: bool
    silk_flat_height: float
    layers_off: set[str]
    silk_source: str
    minimize: bool
    build_full: bool
    board_mode: str
    layer_colors: dict[str, tuple[int, int, int]]
    ignore_soldermask: bool
    fold_bends: bool
    fold_anchor: tuple[float, float] | str | None
    fold_neutral: float
    fold_slice_angle: float
    exposed_copper: bool
    mask_openings: bool
    window_geometry: str | None
    window_state: str
    json_file: str
    output_dir: str


@dataclass(frozen=True)
class Key:
    """One `gui` key.

    `load(raw, section)` turns what the file holds into what the program
    holds; `save(value)` is the reverse. Neither is needed for a key whose
    file shape is its program shape: `read` then checks the value against
    the key's `choices`, or against its default's type. `launcher_owned` keys
    describe the board being exported rather than a preference: when Allegro
    supplied them they are not written back, or every export of a different
    board would rewrite the file and lose to the next export anyway.
    `last_wins` keys are a record of the last window rather than a choice -
    where it stood, the paths picked last - so a close writes them over
    whatever another window left there without a word (save_gui_settings).
    """

    name: str
    field: str
    default: object = None
    load: Callable | None = None
    save: Callable | None = None
    launcher_owned: bool = False
    choices: tuple[str, ...] = ()
    last_wins: bool = False

    def read(self, raw, section: dict):
        """What the program holds for the file's *raw*: the key's own `load`
        when it has one; else one of `choices`, a flag for a flag's default,
        a string for a string's - and the default for anything else, which
        unreadable_keys names for the log. Until round 107 a key without a
        `load` went to the window as the file had it: a flag "maybe" stopped
        the window opening, a board colour with no swatch built in the
        default with nothing said (review 28.10.2026, R6-1, R6-2)."""
        if self.load is not None:
            return self.load(raw, section)
        if self.choices:
            return _load_choice(raw, self.choices, self.default)
        if isinstance(self.default, bool):
            return _load_flag(raw, self.default)
        if isinstance(self.default, str):
            return raw if isinstance(raw, str) else self.default
        return raw


# What a hand-edited file may hold for a flag besides true and false.
_FLAG_WORDS = {"true": True, "yes": True, "on": True, "1": True,
               "false": False, "no": False, "off": False, "0": False}


def _load_flag(raw, default):
    # 0 and 1, and the words above in any case, read as the flag they mean -
    # the window's Tk variable used to take them so, and a file that worked
    # must keep working; anything else is the default.
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int) and raw in (0, 1):
        return bool(raw)
    if isinstance(raw, str):
        return _FLAG_WORDS.get(raw.strip().casefold(), default)
    return default


def _load_choice(raw, choices, default):
    # In any case and padding, given back as the table spells it: a datum
    # written "Bottom" stopped the window opening (review 23.10.2026, R6-8).
    if isinstance(raw, str):
        wanted = raw.strip().casefold()
        for choice in choices:
            if choice.casefold() == wanted:
                return choice
    return default


def _migrated(gui):
    """One file's `gui` section with its superseded keys read into the keys
    that replaced them, where that file does not hold the new key itself.

    Done per FILE, before the pair is merged. Done on the merged section, as
    until round 107, the shipped file's own `stepDirs` ([]) and `boardMode`
    ("solid") came first, so a stepDir or debugLayers in the LOCAL file -
    where the shipped file's comment sends your settings - was never read,
    and the close dropped it (review 28.10.2026, R6-4). Within one file the
    new key wins.
    """
    if not isinstance(gui, dict):
        return gui
    out = dict(gui)
    if "stepDir" in out and "stepDirs" not in out:
        single = str(out["stepDir"]).strip()
        out["stepDirs"] = [single] if single else []
    if "debugLayers" in out and "boardMode" not in out:
        out["boardMode"] = "inspect" if out["debugLayers"] else "solid"
    return out


def _gui_section(base: dict, local: dict) -> dict:
    """The pair's `gui` section as the window reads it: each file migrated,
    then the two merged, the local one on top; {} when it is not an object."""
    files = [{"gui": _migrated(doc["gui"])} if "gui" in doc else {} for doc in (base, local)]
    section = merge_config(*files).get("gui")
    return section if isinstance(section, dict) else {}


def _load_step_dirs(raw, section: dict) -> list[str]:
    # stepDirs (a list) is the shape. A stepDir (a single string) of a config
    # written before multi-folder support became one in its own file before
    # the merge (_migrated), so that setting survives the upgrade; the saver
    # then drops it - see there for why it is not mirrored back.
    if isinstance(raw, list):
        return [str(d).strip() for d in raw if str(d).strip()]
    return []


def _load_flat_height(raw, section: dict) -> float:
    try:
        return abs(float(raw))
    except (TypeError, ValueError):
        return DEFAULT_FLAT_HEIGHT


def _load_layers_off(raw, section: dict) -> set[str]:
    return set(raw) if isinstance(raw, list) else set()


def _load_board_mode(raw, section: dict) -> str:
    # debugLayers, the previous shape of this setting - a single boolean
    # meaning "inspect" - became a boardMode in its own file before the merge
    # (_migrated), so an existing config keeps working; dropped on save.
    if isinstance(raw, str) and raw in BOARD_MODE_KEYS:
        return raw
    return "solid"


def _load_layer_colors(raw, section: dict) -> dict[str, tuple[int, int, int]]:
    colors = dict(DEFAULT_LAYER_COLORS)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key in colors:
                try:
                    colors[key] = parse_hex(str(value))
                except ValueError:
                    pass
    return colors


def _load_anchor(raw, section: dict):
    # Anything unreadable falls back to the default rather than stopping the
    # load: these are hand-edited numbers in a file nothing validates.
    if isinstance(raw, str) and raw.strip().lower() == "auto":
        return "auto"
    if (isinstance(raw, (list, tuple)) and len(raw) >= 2
            and all(isinstance(v, (int, float)) for v in raw[:2])):
        return (float(raw[0]), float(raw[1]))
    return None


def _load_neutral(raw, section: dict) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_NEUTRAL_FACTOR
    return value if 0.0 <= value <= 1.0 else DEFAULT_NEUTRAL_FACTOR


def _load_slice_angle(raw, section: dict) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_SLICE_ANGLE
    return value if 0.5 <= value <= 90.0 else DEFAULT_SLICE_ANGLE


def _load_geometry(raw, section: dict) -> str | None:
    return raw if isinstance(raw, str) else None


def _load_window_state(raw, section: dict) -> str:
    return "zoomed" if raw == "zoomed" else "normal"


def _save_anchor(value):
    # Written back as read, so a hand-edited anchor survives a run.
    return list(value) if isinstance(value, tuple) else value


# In the order they are WRITTEN: a key the local file does not hold yet is
# appended in this order, and the file is diffed by people.
GUI_KEYS: tuple[Key, ...] = (
    Key("stepDirs", "step_dirs", None, _load_step_dirs),
    Key("zDatum", "z_datum", "top", choices=("top", "bottom")),
    # The window's closed lists: a colour the dropdown cannot show is not one
    # it can build (the command line's --color takes r,g,b; the window does not).
    Key("boardColor", "theme", DEFAULT_THEME, choices=tuple(BOARD_THEMES)),
    Key("boardEdge", "rim_choice", RIM_SAME, choices=(RIM_SAME, RIM_CREAM, RIM_CUSTOM)),
    Key("boardEdgeCustom", "rim_custom", ""),
    Key("silkscreenTop", "silk_top", True),
    Key("silkscreenBottom", "silk_bottom", True),
    Key("silkColor", "silk_color", DEFAULT_SILK, choices=tuple(SILK_COLORS)),
    Key("silkscreenFlat", "silk_flat", False),
    Key("silkscreenFlatHeight", "silk_flat_height", DEFAULT_FLAT_HEIGHT, _load_flat_height),
    # Exclusions rather than inclusions: a layer this build has never seen must
    # default to ON, or a layer that appears on a new board would go missing.
    Key("silkscreenLayersOff", "layers_off", None, _load_layers_off, sorted),
    # Where the legend comes from: the drawn silkscreen layers, or Allegro's
    # AUTOSILK copy of them - one or the other (review 23.10.2026, R2-7).
    Key("silkscreenSource", "silk_source", SILK_SOURCES[0], choices=SILK_SOURCES),
    Key("minimizeFileSize", "minimize", True),
    Key("buildFullBoard", "build_full", True),
    Key("boardMode", "board_mode", None, _load_board_mode),
    Key("layerColors", "layer_colors", None, _load_layer_colors,
        lambda colors: {k: "#%02X%02X%02X" % v for k, v in colors.items()}),
    Key("ignoreSoldermask", "ignore_soldermask", False),
    Key("foldBends", "fold_bends", True),
    Key("foldAnchor", "fold_anchor", None, _load_anchor, _save_anchor),
    Key("foldNeutral", "fold_neutral", DEFAULT_NEUTRAL_FACTOR, _load_neutral),
    Key("foldSliceAngle", "fold_slice_angle", DEFAULT_SLICE_ANGLE, _load_slice_angle),
    # The copper pads as surfaces on the outer faces (round 85). Off by
    # default: a picture wants them, a mechanical check does not need them.
    Key("exposedCopper", "exposed_copper", False),
    # The mask openings as surfaces in the dielectric's colour - every
    # padstack's opening and every opening drawn on the mask layers - what
    # the pads leave of them when both are on, whole on their own.
    Key("maskOpenings", "mask_openings", False),
    # Where the window was, so the next run comes up in the same place - on the
    # same monitor, which is the point on a multi-screen desk.
    Key("windowGeometry", "window_geometry", None, _load_geometry, last_wins=True),
    Key("windowState", "window_state", None, _load_window_state, last_wins=True),
    # The board being exported is not a setting: see Key.launcher_owned.
    Key("jsonFile", "json_file", "", launcher_owned=True, last_wins=True),
    Key("outputDir", "output_dir", "", launcher_owned=True, last_wins=True),
)

# Keys read ONLY to migrate a file written by an older build, and removed from
# the local file on save. Mirroring them would leave two keys meaning one
# thing forever: the new key always wins, so a hand edit of the old one does
# nothing and is silently overwritten on the next close. This is not the
# "preserve keys we do not understand" rule below - that protects keys
# belonging to someone else; these are ours and superseded, and dropping them
# is the migration.
SUPERSEDED_KEYS = ("stepDir", "debugLayers")
# ...and the key each one migrates into.
SUPERSEDED_BY = {"stepDir": "stepDirs", "debugLayers": "boardMode"}


def merge_layers_off(remembered: set[str], shown, unticked: set[str]) -> set[str]:
    """The silkscreen exclusions after the panel had its say.

    *remembered* is what the file excluded (and what earlier boards in this
    window added); *shown* are the layers the panel has rows for, *unticked*
    the rows that are off. A shown layer follows its tick; a layer the panel
    does not show keeps whatever *remembered* said. Taking the unticked rows
    alone, as the window did until round 95, dropped every exclusion for a
    layer the board on screen does not carry - so MANUFACTURING/AUTOSILK_TOP,
    switched off once, came back on the next board that has it (review
    23.10.2026, R6-3).
    """
    return (set(remembered) - set(shown)) | set(unticked)


def _same_in_file(raw, form) -> bool:
    """Is *raw* (as the file holds it) the file form *form*? Case, a number
    written as a string and a flag written as a word do not count as a
    difference."""
    if isinstance(raw, dict) and isinstance(form, dict):
        return raw.keys() == form.keys() and all(_same_in_file(raw[k], form[k]) for k in raw)
    if isinstance(form, bool) and not isinstance(raw, bool):
        # "no" or 0 for a false default is that default, not unreadable.
        return _load_flag(raw, None) is form
    if isinstance(raw, str) and isinstance(form, str):
        return raw.strip().casefold() == form.strip().casefold()
    if isinstance(raw, str) and isinstance(form, (int, float)) and not isinstance(form, bool):
        try:
            return float(raw) == float(form)
        except ValueError:
            return False
    return raw == form


def unreadable_keys(config_path: Path) -> list[str]:
    """One sentence per `gui` key whose value the window could not use.

    Such a value falls back to the default in the window, as it always did -
    a hand-edited file must not stop the window opening. What changed in round
    95 is that it is SAID (the window logs these lines) and that the file keeps
    the value until the window itself changes that setting (save_gui_settings,
    `loaded`); before, the close replaced it with the default without a word
    (review 23.10.2026, R6-2). A value counts as unreadable when its key's
    key's `read` gives the default although the file does not hold the
    default. Since round 107 that is every key (the flags, choices and texts
    had no loader and were never named, review 28.10.2026, R6-1, R6-2), and a
    dict is judged entry by entry: a layer colour that does not parse is
    named by its kind, a kind this build does not know is left alone.
    """
    config_path = Path(config_path)
    base, _ = read_config_file(config_path)
    local, _ = read_config_file(local_config_path(config_path), missing_ok=True)
    section = _gui_section(base, local)
    local_gui = local.get("gui") if isinstance(local.get("gui"), dict) else {}
    notes = []

    def note(name, raw, held_locally):
        where = local_config_path(config_path) if held_locally else config_path
        notes.append(f"{name} = {json.dumps(raw, ensure_ascii=False)} in {Path(where).name} "
                     f"could not be read; the default is used, and the file keeps the value "
                     f"until you change that setting here")

    for key in GUI_KEYS:
        if key.name not in section:
            continue
        raw = section[key.name]
        fallback = key.read(key.default, {})
        form = key.save(fallback) if key.save else fallback
        if isinstance(raw, dict) and isinstance(fallback, dict):
            mine = local_gui.get(key.name)
            mine = mine if isinstance(mine, dict) else {}
            for kind, value in raw.items():
                if (kind in fallback and key.read({kind: value}, section)[kind] == fallback[kind]
                        and not _same_in_file(value, form[kind])):
                    note(f"{key.name}.{kind}", value, kind in mine)
            continue
        if key.read(raw, section) != fallback:
            continue
        if _same_in_file(raw, form):
            continue
        note(key.name, raw, key.name in local_gui)
    return notes


def load_gui_settings(config_path: Path) -> tuple[GuiSettings, str | None, str | None]:
    """(settings, base problem, local problem): the pair merged, `gui` decoded.

    A section that is missing or not an object gives the defaults, exactly as
    a window with nothing loaded holds them.
    """
    config_path = Path(config_path)
    base, base_problem = read_config_file(config_path)
    local, local_problem = read_config_file(local_config_path(config_path), missing_ok=True)
    section = _gui_section(base, local)
    values = {}
    for key in GUI_KEYS:
        raw = section.get(key.name, key.default)
        values[key.field] = key.read(raw, section)
    return GuiSettings(**values), base_problem, local_problem


# What _without_shipped gives for a value the shipped file holds as it is.
_SHIPPED = object()


def _without_shipped(value, shipped):
    """What of *value* differs from the shipped *shipped*, or _SHIPPED when
    none of it does. A dict is compared entry by entry (layerColors), so a
    colour set back to the shipped one leaves the local file like any key."""
    if isinstance(value, dict) and isinstance(shipped, dict):
        rest = {k: v for k, v in value.items() if shipped.get(k) != v}
        return rest if rest else _SHIPPED
    return _SHIPPED if value == shipped else value


def _replaced(name: str, held, written) -> str:
    """The sentence for a value a close wrote over (save_gui_settings)."""
    return (f"{name}: the file held {json.dumps(held, ensure_ascii=False)}, "
            f"this window wrote {json.dumps(written, ensure_ascii=False)}")


def save_gui_settings(config_path: Path, values: GuiSettings, *,
                      paths_from_launcher: bool, loaded_cleanly: bool,
                      loaded: GuiSettings | None = None) -> list[str]:
    """Write the `gui` section into the LOCAL settings file.

    The tracked file is never written. It holds the shipped defaults, it is
    under version control, and the window rewrites its settings every time it
    closes - a combination that guarantees a conflict on every update and
    someone else's window position in every commit. What this writes is
    simple3d_config.local.json beside it, which is gitignored and merged over
    the defaults on read.

    Read-modify-write rather than a fresh document: the local file is
    hand-editable too, and someone may have pinned a key in it that this build
    knows nothing about. The section is merged into, not replaced, for the
    same reason one level down.

    NOTHING is written unless both files were understood when the window
    loaded (`loaded_cleanly`) AND the local file reads cleanly now. An earlier
    version treated an unreadable file as an empty one and cheerfully wrote
    back a document holding only "gui", which is exactly how a user's settings
    file came back with every other section gone; and a file that was
    unreadable at load and repaired meanwhile would be overwritten with the
    defaults the widgets fell back to. A file that cannot be WRITTEN is still
    ignored silently: a read-only install directory must not turn closing the
    window into an error dialog.

    ONLY WHAT DIFFERS FROM THE SHIPPED DEFAULT is kept. Writing the whole
    section would pin every key at whatever this installation happened to have
    on the day, and an improved default upstream could never reach it again -
    half of what the split was for. Setting a value back to the shipped one
    REMOVES it here rather than freezing today's default forever. Keys the
    base does not mention are kept as they are: they are either ours and new,
    or someone else's and none of our business.

    ONLY WHAT THIS WINDOW CHANGED is written, when *loaded* - the settings as
    the window read them at start-up - is given; the window always gives it. A
    key whose value is still the loaded one keeps whatever the local file holds
    NOW. Writing every key, as the window did until round 95, rewrote the file
    from the values read at start-up: a hand edit made while the window was
    open, everything the first of two windows changed, and a value the loader
    could not read were all lost on close (review 23.10.2026, R6-1, R6-2).
    A dict goes one entry at a time: only the layer colours the window
    changed, into the dict the file holds now - written whole, as until round
    107, the later of two windows undid the other's colours and a colour
    edited by hand while the window was open (review 28.10.2026, R6-3).
    Without *loaded* every key is written, as before.

    Returns one sentence per value this close wrote over: a setting the
    window changed that the files changed too while it was open - by hand, or
    by another window that closed first. The window's value is written, the
    later of two choices; the sentence keeps what the file held, for the
    window to show where it will be read, since its log closes with it
    (R6-3). A `last_wins` key - the window's place, the last paths picked -
    is a record of the last window and is written over without a sentence.
    """
    if not loaded_cleanly:
        return []
    config_path = Path(config_path)
    target = local_config_path(config_path)
    data, problem = read_config_file(target, missing_ok=True)
    if problem is not None:
        return []
    creating = not target.exists()
    section = data.get("gui")
    if not isinstance(section, dict):
        section = {}
    # A superseded key in either file means the key that replaced it was
    # migrated at load: it is written even if the window left it alone, or the
    # setting would live only in the old key - which this save drops from the
    # local file, and which the next shipped file no longer carries.
    base_now, base_problem = read_config_file(config_path)
    base_now_gui = base_now.get("gui") if base_problem is None else None
    old_keys = set(section) | (set(base_now_gui) if isinstance(base_now_gui, dict) else set())
    migrated = {SUPERSEDED_BY[old] for old in SUPERSEDED_KEYS if old in old_keys}
    for old in SUPERSEDED_KEYS:
        section.pop(old, None)
    # The pair as it is NOW, read as at load: a value that moved since the
    # window loaded was changed somewhere else meanwhile. Not judged when
    # either file does not read now.
    now, now_base, now_local = load_gui_settings(config_path)
    if now_base is not None or now_local is not None:
        now = None
    replaced = []
    for key in GUI_KEYS:
        if key.launcher_owned and paths_from_launcher:
            continue
        value = getattr(values, key.field)
        written = key.save(value) if key.save else value
        if loaded is None or key.name in migrated:
            section[key.name] = written
            continue
        before = getattr(loaded, key.field)
        there = getattr(now, key.field) if now is not None else before
        if isinstance(value, dict):
            changed = [k for k in value if value[k] != before.get(k)]
            if not changed:
                continue
            current = section.get(key.name)
            merged = dict(current) if isinstance(current, dict) else {}
            shown = key.save(there) if key.save else there
            for k in changed:
                if there.get(k) not in (before.get(k), value[k]):
                    replaced.append(_replaced(f"{key.name}.{k}", merged.get(k, shown.get(k)),
                                              written[k]))
                merged[k] = written[k]
            section[key.name] = merged
            continue
        if written == (key.save(before) if key.save else before):
            continue
        if not key.last_wins and there not in (before, value):
            replaced.append(_replaced(key.name, section.get(
                key.name, key.save(there) if key.save else there), written))
        section[key.name] = written

    base, problem = read_config_file(config_path)
    base_gui = base.get("gui") if problem is None else None
    if isinstance(base_gui, dict):
        kept = {}
        for name, value in section.items():
            if not name.startswith("_comment") and name in base_gui:
                value = _without_shipped(value, base_gui[name])
                if value is _SHIPPED:
                    continue
            kept[name] = value
        section = kept
    data["gui"] = section
    # A note for whoever opens the file wondering what it is. Written only
    # when the file is being created, so it cannot fight a hand edit (until
    # round 107 any file without one got it, review 23.10.2026, R6-18).
    if creating:
        data.setdefault(
            "_comment",
            "Local settings for this installation. Overrides simple3d_config.json "
            "key by key and is not tracked by git, so an update never touches it. "
            "Delete a key here to go back to the shipped default.")
    # Written to a temporary file and renamed into place, so it is never
    # left half written if the process dies mid-save.
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        os.replace(tmp, target)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        return []           # nothing was written over, so nothing to say
    return replaced
