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

"""Mechanical audit of README.md + QUICKSTART.md against the code."""
import json, re, sys
from pathlib import Path

ROOT = _ROOT
readme = (ROOT / "README.md").read_text(encoding="utf-8")
quick = (ROOT / "QUICKSTART.md").read_text(encoding="utf-8")
main_py = (ROOT / "stepbuilder/__main__.py").read_text(encoding="utf-8")
gui_py = (ROOT / "stepbuilder/gui.py").read_text(encoding="utf-8")
core_py = (ROOT / "stepbuilder/core.py").read_text(encoding="utf-8")
cfg = json.loads((ROOT / "simple3d_config.json").read_text(encoding="utf-8"))

issues = []
def note(kind, msg):
    issues.append(f"[{kind}] {msg}")

def uncommented(text):
    return "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))

# ---- CLI flags, both directions -------------------------------------------
code_flags = set(re.findall(r'"(--[a-z][a-z-]+)"', uncommented(main_py)))
# The README writes flags as `--z-datum {top,bottom}` - the argument lives
# INSIDE the backticks, so anchoring on a closing backtick misses them all.
doc_flags = set(re.findall(r"`(--[a-z][a-z-]+)[ `]", readme))
# The --gui prefill flags are launcher plumbing: Allegro passes them, a user
# never types them. Not part of the documented user-facing CLI.
PREFILL_ONLY = {"--gui", "--step-dir", "--json-dir", "--json-file",
                "--output-dir", "--config"}
for f in sorted(code_flags - doc_flags - PREFILL_ONLY):
    note("flag undocumented", f)
for f in sorted(doc_flags - code_flags):
    note("flag documented but absent", f)

# ---- config keys ----------------------------------------------------------
sections = set(cfg)
keys = {k for s in cfg.values() if isinstance(s, dict) for k in s}
real_keys = {k for k in keys if not k.startswith("_comment")}
for k in sorted(real_keys):
    if k not in readme:
        note("config key undocumented", k)

# keys the GUI reads/writes must exist in the shipped file
gui_keys = set(re.findall(r'gui\.get\(\s*"(\w+)"', gui_py)) | \
            set(re.findall(r'^\s+"(\w+)":', uncommented(gui_py), re.M))
for k in sorted(gui_keys & real_keys):
    pass
# Keys read ONLY to migrate a settings file written by an older build. They are
# deliberately absent from the shipped config - shipping them would recreate the
# duplicate the migration exists to remove.
MIGRATION_ONLY = {"stepDir", "debugLayers"}
# Strip comments first: a DISABLED read is not a read (the same false positive
# the round-18 audit hit with --mfr-pn-in-name).
missing = ({k for k in re.findall(r'gui\.get\(\s*"(\w+)"', uncommented(gui_py))}
           - real_keys - MIGRATION_ONLY)
for k in sorted(missing):
    note("GUI reads a key absent from the shipped config", k)

# ---- format_version -------------------------------------------------------
il = (ROOT / "makeVariant3dIntermediates.il").read_text(encoding="utf-8", errors="replace")
m = re.search(r'"format_version"\s*:\s*(\d+)', il)
if m:
    written = m.group(1)
    if f"format_version: {written}" not in readme and f"format_version` {written}" not in readme \
       and f"format_version`: {written}" not in readme:
        note("format_version", f"exporter writes {written}; README may not say so")

# ---- assembly labels ------------------------------------------------------
for label in ("symbols_top", "symbols_bot", "silkscreen_top", "silkscreen_bot"):
    if label not in readme:
        note("assembly label undocumented", label)

# ---- defaults -------------------------------------------------------------
thick = cfg["settings"]["silkscreenThickness"]
if str(thick) not in readme:
    note("default", f"silkscreenThickness {thick} not in README")
flat = re.search(r"DEFAULT_FLAT_HEIGHT\s*=\s*([\d.]+)", core_py).group(1)
if flat not in readme:
    note("default", f"DEFAULT_FLAT_HEIGHT {flat} not in README")

# ---- shipped files listed -------------------------------------------------
for f in ("makeVariant3dIntermediates.il", "simple3d.il", "simple3d_config.json",
          "core.py", "gui.py", "colors.py", "bend.py", "__main__.py"):
    if f not in readme:
        note("file not in layout listing", f)

# ---- QUICKSTART claims ----------------------------------------------------
# every GUI label the quick-start names must exist in gui.py
for label in re.findall(r"\*\*([A-Z][A-Za-z0-9 =/…]+?)\*\*", quick):
    lab = label.strip()
    if lab in ("Input", "Board options", "Silk options", "Layers", "Log"):
        if f'text="{lab}"' not in gui_py:
            note("QUICKSTART names a missing frame", lab)
        continue
    if lab.split()[0] in ("Generate", "Board", "Silkscreen", "Minimise",
                          "STEP", "JSON", "Output", "Z", "All", "None",
                          "White/Black", "Top", "Bottom", "Body", "Ignore", "Reset", "Compact",
                          "Make", "Fold", "Add...", "Custom…"):
        continue
    note("QUICKSTART label unchecked", lab)

for term in ("Board edge color", "Body stitching", "Reset colors",
             "Make surface (minimum file size)", "Fold flex bends", "Generate"):
    if term not in gui_py:
        note("QUICKSTART names a control absent from the GUI", term)
    if term not in quick:
        note("term missing from QUICKSTART", term)

print(f"README {len(readme.splitlines())} lines, QUICKSTART {len(quick.splitlines())} lines")
print(f"CLI flags: {len(code_flags)} in code, {len(doc_flags)} documented")
print(f"config: {len(sections)} sections, {len(real_keys)} real keys")
if issues:
    print("\nFINDINGS:")
    for i in issues:
        print("  " + i)
else:
    print("\nno findings")
sys.exit(1 if issues else 0)
