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
| Tree | commit `cbba9f7` (then the tip of `feature/copper-pads`, merged into `main` on 2026-09-17), with the uncommitted working-tree changes in place |
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

## The second pass, 17 September 2026 (round 89)

The day after the repair above, another project found two faults in the
harness the audit had run with: Python validates a `.pyc` by the source's
(mtime, size), so a replacement of the same length written in the same
second can leave healthy bytecode answering for a broken source - or broken
bytecode outliving the restore; and a mutation that shadows a line with an
early `return` above it applies correctly but leaves the original in place,
invisible to any leftover check. Both are handled by the shared harness
now (`~/.claude/skills/test-audit/mutate.py`, purged caches, `-B`, a refusal
of any replacement containing its original), and the whole audit was run
again with it, on a copy of the tree, before the branch was merged.

| | |
|---|---|
| Tree | `03bc47e` (the round-88 tree) for the 27, the round-89 tree for the 21 new; the whole table once more at the merge |
| Harness | the shared one, copied into the repository as `tools/mutate.py` (lock under `build/`, otherwise as shared) |
| Refused at once | 3 - `strips-never-overlap`, `seam-gap-zero`, `pad-offset-ignored`: each shadowed its line with an early `return` above it. Rewritten so the replacement removes the original |
| The 27, first run | 20 caught, 7 "survived" |
| Of the 7 | 6 were the spec, not the tests: the five SKILL mutations and `arc-steps-3` named suites written before `test_skill_pins.py` existed (the five) or left `test_bend.py` out (the one). Against the suites that claim them: all 6 caught, `test_skill_pins` in 0.2 s. The 7th, `silk-area-check-silenced`, was never a finding and is dropped; `arc-steps-3-bend` is folded into `arc-steps-3` |
| New mutations | 21: 19 from a reading of rounds 86-88's code and tests (11 caught on the first run, 8 survived - `double-claimed-always-zero`, `drawn-parts-at-copper-height`, `pick-convention-first-wins`, `skill-sweep-finds-nothing`, `skill-boxes-meet-callsite-inverted`, `skill-filter-no-lines`, `readme-count-unstated`, and `audit-count-never-stale`, which measures a tool property no suite claims and is not in the table), plus one per fix of the round |
| Result | **48 entries, 48 caught** |

What the eight survivors said, and what closed each:

- **`double_claimed` had never been seen failing** - the same shape as
  `seam_gap` in finding 4: five uses in `test_bend [7b2]`, every one
  `== 0.0`. [7d] now makes one panel of the Z fold claim the whole outline
  and requires 80% back, past the 2% threshold.
- **The third height was measured by nothing.** `test_pads [6]` read the
  windows' and the copper's z through `_placement`; the drawn openings'
  parts do not go through it, so 3h collapsed onto 2h passed. The lift
  handed to `build_exposed` is read now.
- **The convention search never had to move.** The measured reading is
  first in the list on purpose, and every sample let it win, so a "search"
  returning the first candidate passed `test_silk [10]`. The sample with
  every radius negated has to move the winner to the mirror reading.
- **The copper sweep was pinned by its tokens.** `found = nil` (the
  selection thrown away), the box match applied backwards at its call site,
  and "lines" dropped from the find filter all survived with every token of
  `test_pads [8]` in place. `test_skill_pins [5b]` pins the statements that
  decide; the behaviour itself is the SKILL golden corpus, which needs
  Allegro.
- **The docs audit's count loop had no floor.** A phrase drifting out of its
  regex left one fewer thing to compare and said nothing; README must state
  the count once per language now.

Two more smells were fixed without a mutation to show for them: `test_mech`
derived the model's solid count from the build under test (it comes from the
model file now), and `test_bend [7b3]` indexed a list that a failure empties,
so the suite raised instead of failing. And three were left as they are, with
the reason on record: `silk_demo.json`'s six polygons are the ones that tell
the readings apart, a bias in the sample and not in the oracle; the
`check(..., True)` in `test_dupcuts` is the except-arm of a must-raise pair;
the two bounds on `SHARED_STRIP_RATIO` restate a measurement, and the
behaviour beside them is pinned.

The table is permanent: `tests/mutations.json`, one `{id, file, old, new,
suites, why}` per fault, applied by `tools/mutate.py` to a copy of the tree
(20-30 minutes for all 48), and `tests/test_mutations.py` - the 27th suite in
`run_all` - asks in a fraction of a second whether each entry could still be
applied: the file exists, `old` occurs exactly once, `new` differs and does
not contain `old`, no entry is left applied, every suite it names exists. A
refactor that breaks a pattern fails the round it happens in, not at the end
of the next full pass.

### What is still not covered, after the second pass

- The eleven transliterations pinned by name only, and `run_all` running
  neither golden corpus, are as they were on 15 September.
- The failure branch of `s3dCollectExposed`'s polygon operations (round 89)
  has never executed: no board reaches it. Its statements are pinned.
- A mirrored pin on a padstack with a drill offset: the pad's hole and the
  board's hole follow different rules and no test can say which is
  Allegro's, because no board on hand has such a padstack (README, *Known
  limitations*).

## The third pass, 22 September 2026 (round 90): the table proved on copies

On 21 September the mutation work in BaroSim and step2html settled a rule
this repository's harness did not yet follow: mutate a private COPY of the
tree, never the tree. The in-place design - a byte snapshot restored after
every fault - needed a lock file, a leftover check, a bytecode purge and a
rule that nobody edits while it runs, and still cost four accidents in one
week elsewhere. And it measured the developer's tree, which holds files a
clone does not: two BaroSim rows that had counted as caught for a week
survived on a copy, one of them caught only by the developer's gitignored
settings file. A copy has only what is under version control plus what the
runner deliberately gives it, and that is the honest place to run.

| | |
|---|---|
| Harness | `tools/mutate.py` is the shared harness of the `test-audit` skill as step2html took it the day before: each worker owns a copy of the tree under `build/mutants/run-<time>-<pid>/w<i>/`, made without `.git`, `build/`, `input/`, `failed/`, `.claude/`, bytecode or `simple3d_config.local.json`; the copies run in parallel, longest suites first; the mutated file is restored from the bytes read before the write and the restore is proved by SHA-256; `--changed [REV]` selects the rows whose file, suite or table entry differ from a revision, the check for the day; ids select rows by substring. The lock, the leftover check on every start, the bytecode purge and the edit ban are gone with the design that needed them; what stays is the check that the WORKING tree carries no mutation, since the copies inherit whatever it has |
| Table | the 48 rows of the second pass, their suites named as paths from the root (`tests/test_pads.py`, `tools/skill_checks.py`), which is what `--changed` compares with git's own paths |
| Sentinel | `tests/test_mutations.py` gained two sections: the copy a worker makes carries every file and every suite a row names, byte for byte, no bytecode and none of what must stay out; and `--changed` picks by the file, the suite and the row, nothing else. 257 checks in about a second |
| The 48 on copies | **48 of 48 caught**; 127 files per copy (the 126 tracked files plus `_occt.py`; the harness prints the total over the four copies, 508), copied in 0.2 s; 878 s of wall for 2382 s of suite runs on four copies, measured beside two full suite runs and four agents starting (the fold suite 254 s in the baseline and 310-337 s per row, against 160 s alone) |

What the copies said: nothing that the tree had hidden. No row of this table
borrows its power from the environment - the repository root has no local
settings file, and every fixture the suites read is tracked - which is a fact
about the table that only a copy can state. Two things about running it: with
its output redirected to a file Python buffers the whole log until the end,
so start it with `-u` when the progress is to be watched; and a full run at
this size is about fifteen minutes of wall on a busy machine, the fold
suite's six rows being most of it.

### The table grown: one row per decision the suites claim

step2html had shown the day before what a table of 48 misses: written one
row per decision its suites claimed, 65 of the first 150 rows survived, every
survivor a weak test. So four agents (opus, in parallel, each owning a
disjoint set of suites and targeting only the modules those suites claim,
never editing code, the table or anything shared) read their suites for the
nine smells, wrote rows, ran them on copies with the harness, fixed every
weak test in their own files and re-ran the row; the coordinator merged the
rows with a script that re-checks each against the final tree (id new, file
and suites exist, `old` once, `new` removes it). The machine was shared all
the while with two other projects' mutation runs, so the fold suite cost
260-2 125 s per run instead of 160 and the fold agent ran 15 of the 26 rows
it wrote.

| scope (agent) | rows run | caught as the suites were | caught after the fixes | dropped, with a measurement | in the table |
|---|---:|---:|---:|---:|---:|
| board: zones, layers, modes, plain modes, no-mask, negative, cutouts, regression → `board`, `stackup`, `contour`, `stepdoc`, `colors`, the board stages of `core` | 45 | 38 | 44 | 1 | 44 |
| pads, silkscreen, models: pads, silk, mech, embedded, index → `pads`, `legend`, `models`, the legend / pads / placement stages of `core` | 65 | 47 | 62 | 3 | 62 |
| SKILL, launcher, settings, reader, window: quote, emit, drill offset, skill pins, launch cmd, launcher, variant path, config merge, settings, gui, geom, and the mechanical checks → `skill/*.il`, `simple3d.il`, `settings`, `winplace`, `worker_bridge`, `intermediate`, `__main__`, the docs the audit reads | 54 | 26 of 48 | 53 | 1 | 53 |
| fold: test_bend → `bend/*`, `core._plan_fold` | 15 | 10 | 13 | 1, and 1 open | 13 |
| **together** | **179** | **121** | **172** | **6** | **220 with the 48** |

**What the survivors said.** Fifty-one rows survived their first run. Six of
them were not findings: four equivalent mutants (an arc's parameter range
unwrapped by `GC_MakeArcOfCircle` itself, the ccw flag of a pad arc that
moves a snap point by 6.7e-16 mm², the anchor sign that `_walk` re-decides
at the seam - every transform identical to the last digit over five plan
shapes -, and a "printed zone wins" rule reachable only with overlapping
zones, which no fixture has), one aimed at a phrase no check claims, and one
that stays open below. **Forty-five were weak tests, and every one was fixed
the same day, in the suite that claims the behaviour, and proved by the row
biting afterwards.** By kind:

- *Checks that could not fail.* "layerFunction still wins" was true because
  the fixture's name classified it anyway (`test_modes [1]`); "the fold is
  one solid" was `volume > 0 and not IsNull()`, which a heap of three
  satisfies (`test_bend [3]`); "and it says so once" asked for a phrase both
  constructions print (`test_bend [17]`); the pre-flight dialog was checked
  by the word `axlUIConfirm` anywhere in the file, and a comment three lines
  above the call carries it (`test_launch_cmd [5]`); the third height was
  the lift *argument*, never a z (`test_pads [6]`).
- *Oracles never seen to fail.* `_neutral_ceiling`'s note was never read;
  the flat legend's merge was judged by file size alone.
- *Fixtures that could not tell.* Every stackup on hand is masked on both
  sides or neither, so `mask_sides` could answer for the other side; the
  fold stub in `test_pads [3]` was a z translation, which commutes with both
  factors of a placement; the demo's symbol angle is 0; `wide_hold` is wide
  in x, not in the bend's own direction, so its held piece stopped at the
  band and an extent answered correctly by luck; both legend sides were
  switched off together, so the per-side loop was never entered; the two
  masked zones of `test_pads [9]` sit at the same z.
- *Decisions nothing claimed.* The whole of `component_transform` - rotation
  order, offset frame, the symbol angle, the flip, the face a bottom part
  rests on, the zone's own surface (`test_mech [3]` now, the arithmetic
  written out on paper); the one line of `_prepare_stackups` that reaches
  `align_stackups`; the datum's *position* in the plain-board modes; thirteen
  SKILL procedures pinned by name only (`test_skill_pins [5c]`-`[5f]`, and
  `[6]` now requires every mirrored procedure to be pinned by a statement,
  so a copy added later cannot go unwatched); `s3dResolveCadDir`, the
  pcb → cad rule (`test_launch_cmd [6]`); `winplace`'s near-screen filter
  (`test_geom [7b]`); a strip the revolve refuses, so the wrap's own volume
  check finally runs (`test_bend [17c]`).
- *Suites that raised instead of failing.* A non-closing pad wire took
  `test_pads` down with a traceback; the batch rule's `said[-1]` in
  `test_variant_path` raised on exactly the failure it exists for; three
  board rows are still caught by the suite raising (`test_dupcuts [2]`,
  `test_modes [4]`, `test_plain_modes [2]`), honest non-zero exits that stop
  the suite at that point - noted, not changed.
- *The checking machinery itself*, three defects: `tools/audit_docs.py`'s
  `format_version` check accepted the loose forms the README uses for the
  HISTORY ("11 has no vias"), so dropping the exporter to 11 passed - it now
  requires the `format_version: N` form once per language and compares
  every occurrence; `test_gui [9]` reached a modal message box under one
  mutation and sat for 31 minutes at 2 % CPU with the run's whole output
  buffered behind it - stubbed, and "nothing was shown" asserted; and
  `test_launch_cmd`'s 8 s deadline for a detached `start` went red on the
  clean copy of a loaded machine, so two rows read "survived" for a reason
  that had nothing to do with the tests - 40 s now, and the harness reports
  such rows as UNPROVEN rather than survived (trap 8 in its docstring),
  with a timeout of three times a suite's baseline plus two minutes past
  which the suite's process tree is killed and the row is HUNG (trap 7).

**No defect in the code.** Not one of the 179 mutations showed the Python
or the SKILL doing the wrong thing; two docstrings claim more than the
measurement supports (`stepdoc.write` says the document is empty without
`UpdateAssemblies()`; measured, the board still comes through as a free
shape and the placements are what is lost, 507.10 of 12 073.31 mm³).

**The whole table on copies, with every agent's edit in the tree: 220 of
220 caught, 2 992 s of wall for 10 158 s of suite runs on four copies** -
the fold suite 658 s in the baseline and up to 651 s per row, the machine
shared with two other projects' runs throughout; no row refused, none hung,
none unproven. `run_all` afterwards: 31/31 under cadquery-ocp 7.9 (822 s)
and 31/31 under 8.0 (898 s), on the same loaded machine.

The suites grew by about 1 000 lines: `test_skill_pins` 88 → 186 PASS
lines, `test_mech` 20 → 29, `test_silk` 51 → 62, `test_pads` 108 → 112,
`test_bend` 229 → 234, the board suites 195 → 210, `test_launch_cmd`
25 → 35, `test_geom` 30 → 35; `tests/test_mutations.py` asks its questions
about 220 rows in 945 checks. The four agents' full reports - the inventory
per suite, every row with its FAIL line, the equivalence measurements - are
under `build/agents/<scope>/report.md`, outside the repository.

### What is still not covered, after the third pass

- **An arc through the wrap is not required to stay an arc**
  (`bend-arcs-wrapped-as-splines`, the one open survivor): with the
  `GeomAbs_Circle` branch of `_edge_curves` disabled the notch is fitted as a
  spline and every volume still agrees to 1e-6, because no fixture has the
  relief notch that once made OCC call the wire self-intersecting on the
  real board. A check that the wrapped solid still carries circular or
  elliptical edges would close it; each attempt costs a fold-suite run.
- The eleven fold rows the agent had written but had no machine time to run
  were run later the same day, on four copies of a quiet machine (the fold
  suite 176 s in the baseline): **8 caught as the suite was, 3 survived.**
  Two of the three were weak tests, fixed and re-run: `in_bend_area` ten
  times wide passed because the suite's two points were far from the band -
  `test_bend [8]` now asks a point one and a half half-widths out and one
  nine tenths in; and `flat_frame` with its panels-before-slices sort removed
  passed because no point the suite asked was near a seam - measured over
  72 000 folded points of three plans, 393 get a different frame slices-first,
  up to 0.54 mm off, so [8] now unfolds fifty panel points within half a
  millimetre of the strip and requires each back exactly home. The third,
  the auto anchor holding the SMALLEST piece, is an equivalent mutant of the
  same family as the sign inversion above: the sign search's answer is
  re-decided by `_walk` at every seam, and on six auto-anchored plans (three
  strips, a Z fold, two arms, a 180° tall board) plus the rigid-flex fixture
  every region transform, the held piece and the notes are identical with
  and without it - dropped. Table 220 → 230.
- **Found on the way, not fixed:** `flat_frame` answers with a *panel* for
  a point on the bend surface within about 0.3 mm of a seam (the panel's
  inverse lands it back inside the stack and the panel's footprint still
  holds it), and slices-first would answer with a slice for a panel point
  the same distance out. Neither order is right at both seams; the honest
  rule would take the region whose inverse lands the point nearest the flat
  plane. On the demo board a rim face with its sample point that close to a
  seam has not been seen; the 393 points above are the measurement.
- The pinch repair in `_piece_face` never runs; nothing produces a pinch.
- No board suite exercises the rim colour or `_rim_faces`; the PRIMARY
  stackup preference, `_layer_region`'s failure arms and `build_contour`'s
  guards are claimed by nothing; `_pad_wire`'s self-closing arc,
  `StepFileIndex._same_root`, `models._sanitize` (every fixture name is
  already plain) and a straddling opening over two masked zones at
  *different* heights have no datum.
- **No test executes SKILL.** Everything on that side is a source pin plus a
  Python copy; the thirteen newly pinned procedures have no recorded Allegro
  answer yet (`skill_answers.json` covers five; `probe_translit.il` is where
  a case is added), and the golden corpus still needs Allegro and is not in
  `run_all`. That `S3D_NegativeLayers` and `S3D_ExportFullBoard` must reset
  per export is named by nothing.
- The mirrored pin with an offset drill, the never-executed failure branch
  of `s3dCollectExposed` and `run_all` running neither golden corpus are as
  they were.
