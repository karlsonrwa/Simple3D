"""The settings pair - the shipped defaults and this installation's local file.

`simple3d_config.json` beside the package is tracked by git and holds the
shipped defaults, for both halves of the tool (the SKILL side reads
`allegro`, `silkscreen` and `settings`; the window reads `gui`).
`simple3d_config.local.json` beside it is gitignored and holds whatever this
installation does differently; it is the ONLY file the window writes. Both
halves read the pair merged, key by key, the local one on top - and the
SKILL side's `s3dJsonMerge` has to agree with `merge_config` here about what
"on top" means (tests/test_config_merge.py runs both over the same cases).

Nothing in here touches a widget. Round 72, plan C1: moved verbatim out of
gui.py so that the window's config code can be tested, and reused, without
tkinter.
"""

from __future__ import annotations

import json
from pathlib import Path


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
