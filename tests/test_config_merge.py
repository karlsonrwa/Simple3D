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

"""The settings file, and the local one on top of it.

Two halves read the pair - SKILL for allegro/silkscreen/settings, Python for
gui - and they have to agree about what "on top" means. The SKILL merge is
transliterated here and both are run over the same cases.
"""
import json, re, sys

from stepbuilder.gui import _merge_config

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(name)


def skill_merge(base, over):
    """s3dJsonMerge, in Python.

    Objects merge; anything else is replaced whole. Presence of the key
    decides, never truthiness - false is a setting, not an absence.
    """
    if not isinstance(over, dict) or not isinstance(base, dict):
        return over
    out = dict(base)
    for key, value in over.items():
        out[key] = skill_merge(base[key], value) if key in base else value
    return out


print("\n[1] the two implementations agree")
cases = [
    ({}, {}),
    ({"gui": {"a": 1}}, {}),
    ({"gui": {"a": 1}}, {"gui": {"a": 2}}),
    ({"gui": {"a": 1, "b": 2}}, {"gui": {"b": 3}}),
    ({"gui": {"a": 1}}, {"settings": {"x": True}}),
    ({"gui": {"dirs": ["a", "b"]}}, {"gui": {"dirs": ["c"]}}),
    ({"gui": {"on": True}}, {"gui": {"on": False}}),
    ({"gui": {"a": {"deep": 1, "keep": 2}}}, {"gui": {"a": {"deep": 9}}}),
    ({"gui": {"a": {"deep": 1}}}, {"gui": {"a": "not an object any more"}}),
    ({"gui": "not an object"}, {"gui": {"a": 1}}),
]
for base, over in cases:
    p, s = _merge_config(base, over), skill_merge(base, over)
    check(f"{base} + {over}", p == s, f"python {p} vs skill {s}")

print("\n[2] what the merge has to guarantee")
merged = _merge_config({"gui": {"stepDirs": ["d:/shipped"], "silkColor": "White"},
                        "settings": {"exportFullBoard": True}},
                       {"gui": {"stepDirs": ["d:/mine"]}})
check("the local path wins", merged["gui"]["stepDirs"] == ["d:/mine"])
check("a default it does not mention survives", merged["gui"]["silkColor"] == "White")
check("and so does a whole section", merged["settings"]["exportFullBoard"] is True)

off = _merge_config({"settings": {"exportFullBoard": True}},
                    {"settings": {"exportFullBoard": False}})
check("false is an override, not an absence",
      off["settings"]["exportFullBoard"] is False)

short = _merge_config({"gui": {"stepDirs": ["a", "b", "c"]}},
                      {"gui": {"stepDirs": ["a"]}})
check("a list is replaced whole, so it can be shortened",
      short["gui"]["stepDirs"] == ["a"])

print("\n[3] the SKILL source says the same thing")
src = (_ROOT / "makeVariant3dIntermediates.il").read_text(encoding="utf-8")
check("the merge exists", re.search(r"procedure\(\s*s3dJsonMerge", src))
check("a key is found by comparing strings, not by assoc",
      re.search(r"procedure\(\s*s3dJsonEntry", src))
found = len(re.findall(r"s3dConfigRead\(", src))
check("both readers go through the merged config", found >= 2, str(found))
check("the local name is derived rather than spelled out twice",
      re.search(r"procedure\(\s*s3dLocalConfigFile", src)
      and src.count('".local.json"') == 1)
launcher = (_ROOT / "simple3d.il").read_text(encoding="utf-8")
check("the launcher reads it too", "s3dConfigRead( S3D_ConfigFile )" in launcher)

print("\n[4] where the tool is installed, with no path written down")
# It cannot live in the config - it is what FINDS the config - and it cannot be
# a literal either: this file is tracked, so a path in it is one installation's
# path shipped to everyone and overwritten in every working copy by the next
# update. Two sources, and an honest refusal when neither answers.
check("SIMPLE3D_DIR is read first", 'axlGetVariable( "SIMPLE3D_DIR" )' in launcher)
check("the load path is the second source",
      "get_filename( piport )" in launcher
      and re.search(r"s3dFolderOf\(\s*S3D_LoadedFrom\s*\)", launcher))
check("and it is captured at load, the only moment it exists",
      re.search(r"^S3D_LoadedFrom = nil\n^errset\( S3D_LoadedFrom = get_filename",
                launcher, re.M))
check("no absolute path is left in the file",
      re.search(r'^S3D_ScriptDir = ""$', launcher, re.M)
      and not re.search(r'^S3D_ScriptDir = "[a-zA-Z]:', launcher, re.M))
check("the folder is cut by scanning, not by parseString",
      re.search(r"procedure\(\s*s3dFolderOf", launcher)
      and "parseString" not in launcher[launcher.index("procedure( s3dFolderOf"):
                                        launcher.index("procedure( s3dResolveScriptDir")])
check("and the config path follows it",
      re.search(r"wasDefault[\s\S]{0,600}?S3D_ConfigFile = strcat\(", launcher))
check("resolved BEFORE the settings are read, or it would read the wrong file",
      launcher.index("errset( s3dResolveScriptDir() )")
      < launcher.index("\ns3dLoadSettings()"))
check("the export refuses to run when it is still unknown",
      re.search(r'when\(\s*S3D_ScriptDir == ""[\s\S]{0,600}?return\(\s*nil\s*\)', launcher))

# The same rule for the tracked config: no machine's paths in it.
cfg = json.loads((_ROOT / "simple3d_config.json").read_text(encoding="utf-8"))
check("the shipped config names no model folder", cfg["gui"]["stepDirs"] == [],
      str(cfg["gui"]["stepDirs"]))
check("and no value in it looks like an absolute path",
      not [v for v in json.dumps(cfg).split('"')
           if re.match(r"^[a-zA-Z]:[/\\]", v)],
      str([v for v in json.dumps(cfg).split('"') if re.match(r"^[a-zA-Z]:[/\\]", v)]))

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
