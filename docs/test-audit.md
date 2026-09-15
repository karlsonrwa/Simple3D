# Test audit, 2026-09-15 — does the suite check anything?

Same question, same method as the GnssSim audit of the same day: reading a test
cannot answer it, because every test looks purposeful. The evidence is a
**mutation** — break the code the test claims to protect, run the test, see
whether it fails. A test that still passes is theatre; a whole feature whose
severance leaves the set green is worse, because nothing was written at all.

The method, written down for reuse, is the memory note `test-audit-playbook`
(with the harness bundled as the `test-audit` skill).

## What was measured

| | |
|---|---|
| Tree | branch `feature/copper-pads` at `cbba9f7`, with the uncommitted working-tree changes in place |
| Baseline | `python tests/run_all.py` — **29/29 jobs pass in 218 s** (25 test suites + 4 mechanical SKILL/docs checks); `test_bend.py` is 158 s of that |
| Assertions | **1198** PASS/FAIL lines across the 25 suites, measured by running each one (`test_bend` 220, `test_gui` 144, `test_variant_path` 137, `test_pads` 95, `test_emit` 90; `test_mech` produces none) |
| Mutations | **27 distinct**, each matched exactly once in the source, applied to bytes, restored in a `finally` and the file's SHA-256 compared afterwards. The tree was byte-identical to its backup after every round. |
| Result | **16 caught, 11 survived** |

Nothing was changed in the repository by this audit except the two files of
this report.

## The findings

### 1. The silkscreen curve machinery is exercised by no test data at all

Three mutations survive `test_silk.py`:

- every silkscreen arc replaced by its chord (`_wire_from_vertices.make` never
  takes the arc branch);
- the side an arc bulges to inverted (`_arc_bulges_left`);
- the per-polygon area comparison in `build_silkscreen` turned off.

The reason is one measured fact: **every silkscreen polygon in every test is a
square or a square ring, and every vertex radius is 0.0.** `test_silk.py`
writes four polygons by hand (`square()`, `ring()`); `demo/ap-214/demo.json`
and all four files under `tests/fixtures/` carry no `silkscreen` key at all.

So `_pick_convention`'s sixteen readings, `_arc_bulges_left`, `_arc_geometry`
and `_arc_edge` — the most reasoned-about part of `legend.py`, settled by
measurement on a real board at 0.0004 % — never run on a curve here. And
`test_silk [2]`, the "areas match Allegro's" check, compares a square whose
area the test itself wrote (`"area": s * s`) against the square that was built
from the same four corners.

Worth adding: one polygon with a real radius, and its area taken from Allegro
rather than computed in the test. Neither golden corpus covers it either - the
seven STEP cases are the same demo and rigid-flex boards, which carry no
silkscreen at all.

### 2. The shared-part cache is covered by nothing

`ModelCache.labels_for` returns one imported label set per distinct STEP model,
so ten identical resistors cost one solid. Severing it — every refdes
re-imports its model — leaves **all fourteen geometry suites green**, the C++
volume/entity regression included.

`test_mech.py` is the suite that claims it. Its comment says "Inspect the
assembly tree + count solids to prove the part is shared", it prints
`solids in shape: N`, and the verdict is

```python
ok = (res.components_placed == 2 and not res.components_skipped
      and "symbols_top_mech_test" in txt and "symbols_bot_mech_test" in txt)
```

— the solid count is printed and never compared. Three of the five tags it
prints YES/no for (`CR2032_MECH1`, `CR2032_MECH2`, `cap_D8x10mm`) are likewise
not in the verdict. `test_mech.py` is also the one suite that does not go
through `_support.check`: measured, it prints **zero** PASS/FAIL lines against
the suite's 1198, and its whole result is the one `ok` above.

### 3. The SKILL exporter is not executed by anything, and four of five semantic mutations in it survive

Half of the product is SKILL, and no test runs it. What the suites do instead
is keep a Python transliteration in `tests/skill_transliterations.py` and test
that, plus grep the `.il` sources for shapes. That is a reasonable design — but
it is only as good as the link between the copy and the original, and these
mutations measured how strong that link is:

| mutation in `skill/` | caught by |
|---|---|
| `s3dLayerIsNegative`: `neg = t` → `neg = nil` (nothing is a negative layer) | nothing |
| `s3dDrillXY`: the offset applied with the opposite sign | nothing |
| `s3dBoxesMeet`: the separating-axis result inverted | nothing |
| `s3dJsonMerge`: the recursive branch replaced by "take the override whole" | nothing |
| `s3dJsonQuote`: the control-character branch removed | nothing |
| `simple3d.il`: `--brd-name` renamed to `--board-name` | `test_launcher.py [6]` |
| `simple3d.il`: `s3dConfigRead` renamed | `test_config_merge.py`, `tools/skill_checks.py` |

`test_neg.py [1]` is the clearest case of the first kind. It opens with

```python
def is_neg(name, func=None, keys=NEG):
    probe = ((func or "").upper() + " " + (name or "").upper())
    return any(k.upper() in probe for k in keys if k)
```

and then makes fourteen assertions about `is_neg` — 14 of the suite's 19 — a
function defined three lines above, which nothing connects to `skill/s3d_stackup.il:170`. The suite
prints `[1] транслитерация s3dLayerIsNegative на реальных слоях`; what it
actually tests is itself. (Its sections [2] and [3] are real: they build
geometry and measure volumes.)

The two mutations that *were* caught show the pattern worth copying:

- `test_launcher.py [6]` pulls **every** `--flag` out of `simple3d.il` with a
  regex and asks the real `build_parser()` whether it knows them. One check,
  and the whole cross-language seam is pinned.
- `tools/skill_checks.py` catches a call to a procedure defined nowhere.

The same trick would pin most of the rest: `test_drill_offset.py` already
greps `makeSlot`'s and `symbolReturnPinHoles`' bodies for the call to
`s3dDrillXY` — what is missing is one assertion tying the *arithmetic* in
`skill/s3d_geometry.il` to the Python copy it is mirrored by.

### 4. `seam_gap` — the fold suite's only "does it join up" oracle can be blinded

`stepbuilder/bend/plan.py:seam_gap` is used nine times in `test_bend.py`, every
one of them as `seam_gap(plan) < 1e-6`, and **no case in the suite expects it
to be large**. Making it `return 0.0` leaves all 220 of the suite's assertions green.

This is not the same as saying the fold is untested — the same suite caught
both other bend mutations (`_strips_overlap` made to return `False`, arcs
sampled 3 times instead of 8), and it takes 62 independent volume/bbox
measurements. It is `seam_gap` itself that has never been shown able to report
a failure. One case with a deliberately mis-sewn plan, asserting a gap in
millimetres, would fix that.

### 5. Small things, found by reading

- `tests/test_zones.py:100` — `check("empty zones list behaves as no zones", True)`.
  The condition is a literal; the board above it was built with the `zones` key
  *removed*, which is a different case from an empty list.
- `README.md:792` and `README.md:1590` say "23 test suites". There are 25.

## What holds

Said plainly, because a list of findings on its own is misleading: 16 of 27
mutations were caught, and every severance of a whole feature except the model
cache was caught by the suite that claims it.

- **`test_pads.py [4]`** is the best test in the repository. The oracle is
  Allegro's own reported pad polygon per pin, stored in
  `tests/fixtures/pads_demo.json`, and one further assertion checks that the
  *sample itself* covers a mirrored pin, a turned one, a through one and a
  SHAPE — the case-coverage check most suites do not make.
- **`test_emit.py [4]`** greps the real exporter source with *negative*
  structural assertions ("no line glues a value between quote characters"),
  which is a source grep that cannot be satisfied by accident.
- **Exit paths** are all wired through `_support.fails`; the round-70 defect
  (`MATCH`/`DRIFT` printed, exit 0 either way) has not come back, and
  `_support.py` documents why.
- The four mechanical SKILL checks do real work: renaming a procedure in
  `simple3d.il` was caught by `skill_checks.py` within a second.
- `python tools/golden.py --check` is green today: 7 cases, no difference against
  `build/golden.json`, 16 s. It is worth knowing that `run_all.py` does not
  run either golden corpus, so both are only as current as the last hand run.

## The mutations, in full

Caught (16): `board-dedup-off`, `has-solid-always-true`, `restack-above-zero`,
`soldermask-unrecognised`, `zone-levels-no-shift`, `arc-steps-3`,
`merge-config-flat`, `reachable-always`, `pads-mask-data-ignored`,
`pads-never-built`, `legend-never-built`, `strips-never-overlap`,
`dupcut-warning-silenced`, `pad-offset-ignored`, `skill-launcher-flag-renamed`,
`skill-config-not-read`.

Survived (11): `silk-arc-side`, `silk-arcs-as-chords`,
`silk-area-comparison-off`, `silk-area-check-silenced`, `model-cache-off`,
`seam-gap-zero`, `skill-nothing-is-negative`, `skill-drill-offset-sign`,
`skill-boxes-meet-inverted`, `skill-control-chars-kept`,
`skill-merge-not-recursive`.

One survivor is not a finding: `silk-area-check-silenced` turned off the
warning in `_pick_convention`, which `test_silk.py` never reads — a mutation
aimed at something the suite does not claim. It is listed so the count is
honest.

Nothing was fixed in the pass above; the audit was asked for, not the
repair. The repair came next, and is recorded below.

## What was done about it, 15 September 2026

Every finding above is closed, and each repair was measured the way the
finding was: the mutation is made again, the suite is run, and the assertion
that bites is named. The ten mutations that survived the audit are all caught
now. `python tests/run_all.py` is 30/30 in 235 s; the suite count is 26.

| finding | what closed it | what bites when the mutation is made again |
|---|---|---|
| 1, silkscreen arcs | `tests/fixtures/silk_demo.json` — six arc-bearing legend polygons of Cadence's demo board with Allegro's own `poly->area` for each; `test_silk [10]`-`[12]` | `silk-arcs-as-chords`: 10 assertions, worst polygon off by 36.3%. `silk-arc-side`: 9, worst 72.7%. `silk-area-comparison-off`: 3, the doctored polygon goes unreported |
| 2, the shared part | `tests/test_mech.py` rewritten: it goes through `_support.check` at all now, and compares a 2-copy board with a 5-copy one | `model-cache-off`: 5 assertions — the model is read 2 and 5 times instead of once, and the solid bodies written go 6 → 11 and 6 → 26 |
| 3, the SKILL seam | `tests/test_skill_pins.py` (new suite), `tools/probes/probe_translit.il`, `tools/skill_answers.py`, `tests/fixtures/skill_answers.json` | all four: two independent assertions each — the pinned statement is gone from the `.il`, and the derived check disagrees |
| 4, `seam_gap` | `test_bend [7d]`: a panel carried a known distance off its strip, and two panels swapping transforms | `seam-gap-zero`: 6 assertions, three displacements in mm and their threshold |
| 5, the small ones | `test_zones [5]` builds the empty-zones board it was claiming about; the counts are corrected AND `tools/audit_docs.py` now derives them from `run_all.py` | breaking the number back to 23 is a finding in the docs audit within a second |

Two things are worth saying beyond the table.

**The SKILL side is now executed, not only read.** The audit's third finding
was the serious one: the Python copies in `tests/skill_transliterations.py`
were worth whatever their link to the original was worth, and the link was
absent. It is now two links, because either alone can rot:

- `test_skill_pins [1]`-`[5]` read the `.il` and compare the statements that
  carry each procedure's meaning, character for character after comments and
  layout are normalised away. Where the meaning can be *derived* it is derived
  rather than matched: the sign of the drill offset is read out of the source
  and the copy is run to see whether it agrees, and the control-character class
  is read out of `s3dCtrlCharPattern` and compared with the copy's predicate
  over every code point.
- `test_skill_pins [7]` compares each copy with what Allegro's own interpreter
  answered. `tools/probes/probe_translit.il` calls the five procedures in a
  real headless Allegro over 59 fixed cases; `tools/skill_answers.py` turns
  that run into `tests/fixtures/skill_answers.json`, the same kind of oracle as
  `pads_demo.json`. Measured on Allegro 25.1, 26 s: **all 59 agree.**

  The probe found one thing on its own: `sprintf "%c"` is not available in this
  SKILL, so a control character cannot be built that way — but the `\b` and
  `\f` string escapes are, and both come back as `"a b"`, so the branch the
  audit's mutation deleted really does run.

`[6]` closes the loop the other way: every `# mirrors` line in
`skill_transliterations.py` must name a procedure that exists in `skill/`, and
every procedure the audit found unpinned must be pinned. A copy added later
with no pin fails there rather than going quietly unwatched. The `# mirrors`
lines were rewritten into one machine-readable form to make that readable at
all: `# mirrors skill/<file>.il: proc[, proc ...]  -- prose`.

**`test_neg.py` no longer tests itself.** Its fourteen assertions about
`is_neg` now run the shared transliteration, which `test_skill_pins` pins to
`skill/s3d_stackup.il:170`.

### What is still not covered

Said plainly, because a list of repairs reads as a clean bill otherwise.

- The other eleven transliterations are pinned by `[6]` only in the sense that
  the procedure they name exists. `s3dVariantFit`, `gdsysGetVariantInfo`'s
  states, `s3dSymbolsToExport` and the rest have no statement-level pin and no
  recorded answer from Allegro. The machinery for both is now in place -
  another case in `probe_translit.il` and another `pin(...)` call - so this is
  work, not a missing idea.
- `run_all.py` still runs neither golden corpus, so both remain as current as
  the last hand run.
- `silk-area-check-silenced` remains what it was: a mutation aimed at something
  no suite claims.
