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
setting is one row plus the widget that shows it. The two migrations
(`stepDir` -> `stepDirs`, `debugLayers` -> `boardMode`) are the `load` of
the key that superseded them, and the saver drops the old keys.

Rounds 72 (plans C1, C2). Importing this module imports core and bend for
three default numbers (`DEFAULT_FLAT_HEIGHT`, `DEFAULT_NEUTRAL_FACTOR`,
`DEFAULT_SLICE_ANGLE`), and with them OpenCASCADE; the merge and the reader
above the table need neither, and are what another tool would copy.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .bend import DEFAULT_NEUTRAL_FACTOR, DEFAULT_SLICE_ANGLE
from .colors import DEFAULT_LAYER_COLORS, DEFAULT_SILK, DEFAULT_THEME, parse_hex
from .core import DEFAULT_FLAT_HEIGHT

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

    Simple keys carry the file's value as read (the window's Tk variables
    coerce it, as they always did); the others are what their `Key.load` made
    of it. `board_mode` is the KEY ("solid"), not the dropdown's label.
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
    minimize: bool
    build_full: bool
    board_mode: str
    layer_colors: dict[str, tuple[int, int, int]]
    ignore_soldermask: bool
    fold_bends: bool
    fold_anchor: tuple[float, float] | str | None
    fold_neutral: float
    fold_slice_angle: float
    window_geometry: str | None
    window_state: str
    json_file: str
    output_dir: str


@dataclass(frozen=True)
class Key:
    """One `gui` key.

    `load(raw, section)` turns what the file holds into what the program
    holds; it sees the whole section so a superseded key can be migrated.
    `save(value)` is the reverse. Neither is needed for a key whose file
    shape is its program shape. `launcher_owned` keys describe the board
    being exported rather than a preference: when Allegro supplied them they
    are not written back, or every export of a different board would rewrite
    the file and lose to the next export anyway.
    """

    name: str
    field: str
    default: object = None
    load: Callable | None = None
    save: Callable | None = None
    launcher_owned: bool = False


def _load_step_dirs(raw, section: dict) -> list[str]:
    # stepDirs (a list) is the shape. stepDir (a single string) is what a
    # config written before multi-folder support holds; it is read ONCE so
    # that setting survives the upgrade, and the saver then drops it - see
    # there for why it is not mirrored back.
    if isinstance(raw, list):
        return [str(d).strip() for d in raw if str(d).strip()]
    single = str(section.get("stepDir", "")).strip()
    return [single] if single else []


def _load_flat_height(raw, section: dict) -> float:
    try:
        return abs(float(raw))
    except (TypeError, ValueError):
        return DEFAULT_FLAT_HEIGHT


def _load_layers_off(raw, section: dict) -> set[str]:
    return set(raw) if isinstance(raw, list) else set()


def _load_board_mode(raw, section: dict) -> str:
    # debugLayers was the previous shape of this setting: a single boolean
    # meaning "inspect". Read once so an existing config keeps working, and
    # dropped on save.
    if isinstance(raw, str) and raw in BOARD_MODE_KEYS:
        return raw
    return "inspect" if section.get("debugLayers") else "solid"


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
    Key("zDatum", "z_datum", "top"),
    Key("boardColor", "theme", DEFAULT_THEME),
    Key("boardEdge", "rim_choice", RIM_SAME),
    Key("boardEdgeCustom", "rim_custom", ""),
    Key("silkscreenTop", "silk_top", True),
    Key("silkscreenBottom", "silk_bottom", True),
    Key("silkColor", "silk_color", DEFAULT_SILK),
    Key("silkscreenFlat", "silk_flat", False),
    Key("silkscreenFlatHeight", "silk_flat_height", DEFAULT_FLAT_HEIGHT, _load_flat_height),
    # Exclusions rather than inclusions: a layer this build has never seen must
    # default to ON, or a layer that appears on a new board would go missing.
    Key("silkscreenLayersOff", "layers_off", None, _load_layers_off, sorted),
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
    # Where the window was, so the next run comes up in the same place - on the
    # same monitor, which is the point on a multi-screen desk.
    Key("windowGeometry", "window_geometry", None, _load_geometry),
    Key("windowState", "window_state", None, _load_window_state),
    # The board being exported is not a setting: see Key.launcher_owned.
    Key("jsonFile", "json_file", "", launcher_owned=True),
    Key("outputDir", "output_dir", "", launcher_owned=True),
)

# Keys read ONLY to migrate a file written by an older build, and removed from
# the local file on save. Mirroring them would leave two keys meaning one
# thing forever: the new key always wins, so a hand edit of the old one does
# nothing and is silently overwritten on the next close. This is not the
# "preserve keys we do not understand" rule below - that protects keys
# belonging to someone else; these are ours and superseded, and dropping them
# is the migration.
SUPERSEDED_KEYS = ("stepDir", "debugLayers")


def load_gui_settings(config_path: Path) -> tuple[GuiSettings, str | None, str | None]:
    """(settings, base problem, local problem): the pair merged, `gui` decoded.

    A section that is missing or not an object gives the defaults, exactly as
    a window with nothing loaded holds them.
    """
    config_path = Path(config_path)
    base, base_problem = read_config_file(config_path)
    local, local_problem = read_config_file(local_config_path(config_path), missing_ok=True)
    section = merge_config(base, local).get("gui")
    if not isinstance(section, dict):
        section = {}
    values = {}
    for key in GUI_KEYS:
        raw = section.get(key.name, key.default)
        values[key.field] = key.load(raw, section) if key.load else raw
    return GuiSettings(**values), base_problem, local_problem


def save_gui_settings(config_path: Path, values: GuiSettings, *,
                      paths_from_launcher: bool, loaded_cleanly: bool) -> None:
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
    """
    if not loaded_cleanly:
        return
    config_path = Path(config_path)
    target = local_config_path(config_path)
    data, problem = read_config_file(target, missing_ok=True)
    if problem is not None:
        return
    section = data.get("gui")
    if not isinstance(section, dict):
        section = {}
    for old in SUPERSEDED_KEYS:
        section.pop(old, None)
    for key in GUI_KEYS:
        if key.launcher_owned and paths_from_launcher:
            continue
        value = getattr(values, key.field)
        section[key.name] = key.save(value) if key.save else value

    base, problem = read_config_file(config_path)
    base_gui = base.get("gui") if problem is None else None
    if isinstance(base_gui, dict):
        section = {name: value for name, value in section.items()
                   if name.startswith("_comment")
                   or name not in base_gui or base_gui[name] != value}
    data["gui"] = section
    # A note for whoever opens the file wondering what it is. Written only
    # when the file is being created, so it cannot fight a hand edit.
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
