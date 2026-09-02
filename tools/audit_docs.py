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
# The exporter writes this line INSIDE a SKILL string, so the quotes are
# escaped: \"format_version\": 7. Anchoring on a bare quote matched nothing and
# this check silently never ran - found in round 60, left open, fixed in 61.
m = re.search(r'\\?"format_version\\?"\s*:\s*(\d+)', il)
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
          "core.py", "contour.py", "errors.py", "intermediate.py", "settings.py",
          "gui.py", "colors.py", "bend.py",
          "__main__.py"):
    if f not in readme:
        note("file not in layout listing", f)

# ---- QUICKSTART claims ----------------------------------------------------
# Every GUI label the quick-start names must exist in gui.py, VERBATIM.
#
# This used to allow a label through on its first word, which meant a renamed
# control kept passing as long as the new name started the same way - and one
# did: the soldermask checkbox was documented as "Ignore soldermask layers"
# long after the widget said "Do not include soldermask layers", because both
# begin with a word that was on the list. Matching the whole string is the
# point of the check.
#
# Two entries are prose shorthand rather than a widget's text and are named
# here so the exception is visible: the quick-start writes the ellipsis
# character where Tk has three dots, and folds a two-item dropdown into one
# "White/Black".
#
# The dropdown CONTENTS live in colors.py, not in gui.py, so both are searched.
#
# Scoped to the section that DESCRIBES THE WINDOW, because bold is bold: once
# the quick-start gained an English half, "**Board thickness**" and
# "**Mechanical parts**" - ordinary emphasis in a prose bullet - read to this
# check as control names that the GUI had lost. The Russian half had carried
# the same shape all along and never tripped it, only because the pattern
# starts at [A-Z]. So the rule is now what it always meant: a control named in
# the window section must exist.
def window_section(text):
    """The '## The window' / '## Окно' blocks, where bold means a control."""
    out = []
    for match in re.finditer(r"^##\s+(The window|Окно)\s*$", text, re.M):
        rest = text[match.end():]
        nxt = re.search(r"^##\s", rest, re.M)
        out.append(rest[:nxt.start()] if nxt else rest)
    return "\n".join(out)

quick_window = window_section(quick)
if not quick_window.strip():
    note("QUICKSTART", "no window section found - the control check ran on nothing")

PROSE = {"Custom…": "Custom...", "White/Black": "White"}
widget_text = gui_py + (ROOT / "stepbuilder/colors.py").read_text(encoding="utf-8")
for label in re.findall(r"\*\*([A-Z][A-Za-z0-9 =/…]+?)\*\*", quick_window):
    lab = label.strip()
    if lab in ("Input", "Board options", "Silk options", "Layers", "Log"):
        if f'text="{lab}"' not in gui_py:
            note("QUICKSTART names a missing frame", lab)
        continue
    if PROSE.get(lab, lab) not in widget_text:
        note("QUICKSTART names a control absent from the GUI", lab)

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
