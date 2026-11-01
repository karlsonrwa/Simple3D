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
# The window and the panels it is built from (widgets/, round 74): a frame
# the quick-start names may live in either.
gui_py = "\n".join(p.read_text(encoding="utf-8") for p in
                   [ROOT / "stepbuilder/gui.py",
                    *sorted((ROOT / "stepbuilder/widgets").glob("*.py"))])
# The flat-legend default lives in legend.py since round 73 (plan A5).
defaults_py = (ROOT / "stepbuilder/defaults.py").read_text(encoding="utf-8")
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
settings_py = (ROOT / "stepbuilder/settings.py").read_text(encoding="utf-8")
read_keys = ({k for k in re.findall(r'gui\.get\(\s*"(\w+)"', uncommented(gui_py))}
             | {k for k in re.findall(r'Key\(\s*"(\w+)"', uncommented(settings_py))}
             | {k for k in re.findall(r'section\.get\(\s*"(\w+)"', uncommented(settings_py))})
missing = read_keys - real_keys - MIGRATION_ONLY
if not read_keys:
    note("GUI keys", "no gui key reads found at all - the check ran on nothing")
for k in sorted(missing):
    note("GUI reads a key absent from the shipped config", k)

# ---- format_version -------------------------------------------------------
# The exporter is nine parts under skill/ since round 76; read them as one.
il = "\n".join(q.read_text(encoding="utf-8", errors="replace")
               for q in sorted((ROOT / "skill").glob("s3d_*.il")))
# The exporter writes this line INSIDE a SKILL string, so the quotes are
# escaped: \"format_version\": 7. Anchoring on a bare quote matched nothing and
# this check silently never ran - found in round 60, left open, fixed in 61.
m = re.search(r'\\?"format_version\\?"\s*:\s*(\d+)', il)
if not m:
    note("format_version", "no `\"format_version\": N` line in skill/ - this check "
                           "ran on nothing")
else:
    written = m.group(1)
    # The loose forms this used to accept ("`format_version` 11") are how the
    # README describes the HISTORY - "11 has no vias", "10 draws the copper
    # whole" - so any of them satisfied the check whatever the exporter wrote,
    # and dropping the version to 11 passed (measured 2026-09-22).
    #
    # What the README has to say is which version the exporter writes NOW, in
    # the one form it says it in: "The exporter writes `format_version: 12`",
    # once per language. A floor, like the suite count above: a phrase drifting
    # out of the regex must be a finding, not one fewer thing compared.
    stated = re.findall(r"format_version:\s*(\d+)", readme)
    if len(stated) < 2:
        note("format_version", f"README states the version it is written with "
                               f"{len(stated)} time(s), 2 expected (one per "
                               f"language) - the check ran on less than it should")
    for says in stated:
        if says != written:
            note("format_version", f"exporter writes {written}; README says {says}")
    # And no version above it named anywhere, in any of the three documents
    # (round 124, review 23.10.2026 R8-19: "Needs a JSON written with
    # `format_version` 13" passed, the form above being the only one read).
    for doc_name, doc_text in (("README.md", readme), ("QUICKSTART.md", quick),
                               ("ARCHITECTURE.md", (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8"))):
        for n in re.findall(r"format_version`?\s*:?\s*`?\s*(\d+)", doc_text):
            if int(n) > int(written):
                note("format_version", f"{doc_name} names format_version {n}; the exporter "
                                       f"writes {written}, and no newer one exists")

# ---- assembly labels ------------------------------------------------------
for label in ("symbols_top", "symbols_bot", "silkscreen_top", "silkscreen_bot"):
    if label not in readme:
        note("assembly label undocumented", label)

# ---- defaults -------------------------------------------------------------
# README's own config lines, value for value (round 124, review 23.10.2026
# R8-16: the value was looked for anywhere in README, and a thickness example
# elsewhere held "0.025" whatever the config line said).
thick = cfg["settings"]["silkscreenThickness"]
quoted = re.findall(r'"silkscreenThickness":\s*([\d.]+)', readme)
if len(quoted) < 2:
    note("default", f"README quotes silkscreenThickness {len(quoted)} time(s), 2 expected "
                    f"(one per language) - the check ran on less than it should")
for value in quoted:
    if float(value) != float(thick):
        note("default", f"silkscreenThickness: the config ships {thick}; README quotes {value}")
flat = re.search(r"DEFAULT_FLAT_HEIGHT\s*=\s*([\d.]+)", defaults_py).group(1)
if flat not in readme:
    note("default", f"DEFAULT_FLAT_HEIGHT {flat} not in README")

# ---- shipped files listed -------------------------------------------------
for f in ("makeVariant3dIntermediates.il", "simple3d.il", "skill/", "simple3d_config.json"):
    if f not in readme:
        note("file not in layout listing", f)
# The map of stepbuilder/ in each half against the package itself, both ways
# (round 124, review 23.10.2026 R8-18 and R8n-27: a fixed list, looked for
# anywhere in README, missed surface.py, pads.py, worker.py and _occt.py).
def package_map(text, heading):
    """The module names the code block under *heading* lists for stepbuilder/."""
    m = re.search(rf"^##\s+{heading}\s*$", text, re.M)
    block = re.search(r"```\n(.*?)\n```", text[m.end():], re.S) if m else None
    if not block:
        return None
    body = block.group(1).split("stepbuilder/", 1)[-1]
    return set(re.findall(r"^\s+([A-Za-z_]\w*\.py|[A-Za-z_]\w*/)\s", body, re.M))

package = ({p.name for p in (ROOT / "stepbuilder").glob("*.py") if p.name != "__init__.py"}
           | {p.name + "/" for p in (ROOT / "stepbuilder").iterdir()
              if p.is_dir() and (p / "__init__.py").exists()})
for heading in ("What is where", "Что где лежит"):
    listed_here = package_map(readme, heading)
    if listed_here is None:
        note("layout listing", f"no code block under '## {heading}' - the map check ran on nothing")
        continue
    for name in sorted(package - listed_here):
        note("layout listing", f"'{heading}' does not list stepbuilder/{name}")
    for name in sorted(listed_here - package):
        note("layout listing", f"'{heading}' lists stepbuilder/{name}, which is not there")

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
# ... and the rim labels are settings VALUES, so they live in settings.py.
widget_text = (gui_py + (ROOT / "stepbuilder/colors.py").read_text(encoding="utf-8")
               + (ROOT / "stepbuilder/settings.py").read_text(encoding="utf-8"))
# Compared with the code's string literals WHOLE (round 124, review 23.10.2026
# R8-17): the label pattern took no "(" or "." - so "Compact STEP (...)" and
# every label with brackets was never read - and a label was looked for as a
# substring of the code, so "Do not include soldermask" passed beside the
# widget's "Do not include soldermask layers".
literals = set()
for literal in re.findall(r'"((?:[^"\\\n]|\\.)*)"', widget_text):
    # a label of two lines is named by its first: each line counts whole
    literals.add(literal)
    literals.update(part for part in literal.split("\\n") if part)
read_labels = 0
for label in re.findall(r"\*\*([A-Z][^*\n]*?)\*\*", quick_window):
    lab = label.strip()
    read_labels += 1
    if lab in ("Input", "Board options", "Silk options", "Layers", "Log"):
        if f'text="{lab}"' not in gui_py:
            note("QUICKSTART names a missing frame", lab)
        continue
    if PROSE.get(lab, lab) not in literals:
        note("QUICKSTART names a control absent from the GUI", lab)
if read_labels < 10:
    note("QUICKSTART", f"only {read_labels} bold label(s) read in the window section - "
                       f"the control check ran on less than it should")

for term in ("Board edge color", "Body stitching", "Reset colors",
             "Make surface (minimum file size)", "Fold flex bends", "Generate"):
    if term not in gui_py:
        note("QUICKSTART names a control absent from the GUI", term)
    if term not in quick:
        note("term missing from QUICKSTART", term)

# ---- the suite count, wherever the docs state it --------------------------
# README.md said "23 test suites" for 27 rounds while there were 25: a number
# in prose has nothing holding it (docs/test-audit.md, finding 5). Read the
# real one out of run_all.py and compare with every place that states it.
run_all = (ROOT / "tests/run_all.py").read_text(encoding="utf-8")
n_suites = len(re.findall(r'TESTS\s*/\s*"test_\w+\.py"', run_all))
n_checks = len(re.findall(r'TOOLS\s*/\s*"\w+\.py"', run_all))
arch = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
# The loop below runs over what the regex finds, so a phrase drifting out of
# it ("twenty-six suites") silently left one fewer thing to compare (review of
# 2026-09-17). README states the count once per language and ARCHITECTURE at
# least once; fewer matches is a finding, like the other "ran on nothing" checks.
for doc, text, floor in (("README.md", readme, 2), ("ARCHITECTURE.md", arch, 1)):
    stated_counts = re.findall(
        r"(\d+) (test suites|suites|наборов тестов|набора тестов|набор тестов)", text)
    if len(stated_counts) < floor:
        note("suite count", f"{doc} states the suite count {len(stated_counts)} time(s), "
             f"{floor} expected - the check ran on less than it should")
    for stated, what in stated_counts:
        if int(stated) != n_suites:
            note("stale suite count",
                 f"{doc} says {stated} {what}; run_all.py runs {n_suites}")
check_counts = re.findall(r"the (\d+) checks \+", arch)
# a floor, as for the suites (round 124, R8-20: "the four checks +" left the
# loop below nothing to compare, silently)
if not check_counts:
    note("check count", "ARCHITECTURE.md states the mechanical check count 0 time(s), "
                        "1 expected - the check ran on nothing")
for stated in check_counts:
    if int(stated) != n_checks:
        note("stale check count",
             f"ARCHITECTURE.md says {stated} mechanical checks; "
             f"run_all.py runs {n_checks}")

# ---- the mutation table's size, wherever the docs state it ----------------
# One number, len(tests/mutations.json), in every place that states it (round
# 124, review 23.10.2026 R8-4 and R7n-20: 329 -> 999 in both README halves
# passed, and ARCHITECTURE carried two other numbers). A row dropped from the
# table, or added, now turns this red until the docs say so too.
n_rows = len(json.loads((ROOT / "tests/mutations.json").read_text(encoding="utf-8")))
for doc, text, pattern, floor in (
        # the Russian noun follows the number: 501 поломка, 502 поломки, 500 поломок
        ("README.md", readme, r"tests/mutations\.json, (\d+) (?:faults|поломк[аи]|поломок)", 2),
        ("ARCHITECTURE.md", arch, r"the (\d+) deliberate faults", 1),
        ("ARCHITECTURE.md", arch, r"`tests/mutations\.json` \((\d+) rows", 1)):
    found = re.findall(pattern, text)
    if len(found) < floor:
        note("mutation count", f"{doc} states the table's size in the form /{pattern}/ "
                               f"{len(found)} time(s), {floor} expected")
    for stated in found:
        if int(stated) != n_rows:
            note("stale mutation count", f"{doc} says {stated}; tests/mutations.json has {n_rows} rows")
# Every suite run_all names has to be there, and every suite there has to be
# run: a test file nobody runs is the same kind of nothing as a stale count.
listed = set(re.findall(r'TESTS\s*/\s*"(test_\w+\.py)"', run_all))
present = {p.name for p in (ROOT / "tests").glob("test_*.py")}
for missing in sorted(listed - present):
    note("run_all names a suite that is not there", missing)
for unrun in sorted(present - listed):
    note("a suite nobody runs", unrun)

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
