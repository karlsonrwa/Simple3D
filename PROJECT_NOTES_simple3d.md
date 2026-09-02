# Simple 3D export — project notes / handoff

Working memo for the "File → Export → Simple 3D" toolchain. Keep updated as work proceeds.
Companion to `PROJECT_NOTES_eskd.md` (same user, same Allegro install).

---

## READ THIS FIRST — state as of 2026-09-02

The rest of this memo is a round-by-round record, oldest first, and it is long.
Everything needed to pick the work up is here. Read a dated round only when you
need the reasoning behind a specific decision; the round headings say what each
one settled.

### Where things are

| | |
|---|---|
| Repo (this working copy) | `D:\Projects\AI\Claude\Simple3D` — branch `main` (renamed from `Test` on 2026-08-02) |
| The user's install | `d:/Projects/OrCAD/Scripts/Simple3D/` — files are copied there by hand |
| Allegro SKILL reference | `D:\Projects\AI\Claude\SKILL\skill_doc\` — `skill/DOC/FUNCS/*.txt` is the useful part, plus `skill_db_attributes.txt` |
| `exportJson` (reference implementation) | `D:\Projects\AI\Claude\exportJson` — juulsA's ibom exporter; its silkscreen traversal and text handling were the model for ours |
| The structure, written down | `ARCHITECTURE.md` in the repo — files, dependencies, the pipeline stage by stage, the intermediate's shape, and which pieces are monoliths / reusable / glue (round 70, 2026-09-02) |
| The split plans | `REFACTORING_PLANS.md` in the repo — five monoliths, the order to take them apart, what each step needs green before and after. Done as of round 74 (2026-09-02): Step 0, Plans A, B and C; each row says what it left. Next: D (SKILL; the export half checked headless by `tools/skill_export.py`, the menu half by the user), then E |
| The golden corpora | `tools/golden.py` → `build/golden.json` (local, gitignored): 7 STEP cases; `--check` after every Python refactoring step. `tools/skill_export.py` → `build/skill_golden/` (round 75): the SKILL exporter run headless on every `input/*.brd`; `--check` after every SKILL step. `tests/_support.py` is the one preamble every suite imports (round 71) |

Three tools grew out of this project and now have repositories of their own.
Nothing here depends on them, and no copy of their code belongs in this tree:

| | |
|---|---|
| `step2html` | `D:\Projects\AI\Claude\step2html` — a STEP assembly to one self-contained WebGL HTML file. Split out 2026-07-30; a stale pre-split copy sat in `tools/step_to_html.py` here until 2026-08-02 |
| `3dproperties` | `D:\Projects\AI\Claude\3dproperties` — STEP library tooling: inventory table, headless Inventor merge, before/after visual report |
| `checkBase` | `D:\Projects\AI\Claude\checkBase` — cross-checks the CIS component tables against the 3D, OLB and PDF files. Written 2026-08-02 as `tools/check_base.py` in this repo by mistake, moved out the same day |

Three pieces ship: `makeVariant3dIntermediates.il` (reads Allegro, writes JSON),
`simple3d.il` (menu item + launcher), `stepbuilder/` (Python + OpenCASCADE,
writes the STEP — since round 73 `core.py` is the sequence of a build's
stages and `contour.py`, `errors.py`, `intermediate.py`, `settings.py`,
`stackup.py`, `board.py`, `legend.py`, `models.py`, `stepdoc.py`, `build.py`,
`reporting.py`, the `bend/` package and - since round 74, beside `gui.py` -
`winplace.py`, `widgets/layers_panel.py` and `worker_bridge.py` hold the
rest; `ARCHITECTURE.md` has the file table). Plus `simple3d_config.json`, the shipped defaults, and the
gitignored `simple3d_config.local.json` beside it, which is the only one the
window writes; both halves read the pair merged. **No absolute path is left in
any tracked file** (round 59): where the tool is installed comes from the
Allegro variable `SIMPLE3D_DIR` or from the folder `simple3d.il` was loaded
from, and `S3D_ScriptDir` is now `""` in source.

### What works, verified on the user's real boards

- Board solid at true finished thickness, cutouts, drill holes, component STEP
  models placed from the Allegro STEP mapping table.
- **Silkscreen**, `format_version: 2`. Collected as filled polygons
  (`axlPolyFromDB`, text via `axlText2Lines`, paths converted a segment at a
  time so joins are round), clipped to outline minus cutouts, built as thin
  solids or flat surfaces, either or both sides, White or Black.
- **The vertex-radius sign convention is settled by measurement**, not by
  reading the docs: `axis / positive-sits-left / first-radius-closes`. The JSON
  carries each polygon's own `area` from Allegro and the reader scores all
  eight candidate readings against it. Do not "simplify" that away — it is what
  proved the geometry correct, and it will catch a different Allegro version.
- Mechanical components and `NO_STEP_EXPORT`, both by rule rather than by
  special case: the export list comes from the design and the variant table only
  subtracts from it.

### Load-bearing decisions that look like they could be simplified, but cannot

- **Do not fuse the SOLID legend.** Measured at 154% of the file size. But DO
  union the FLAT faces — measured smaller, and required, because coplanar
  coincident faces flicker. Same word, opposite results (rounds 10g, 12).
- **Fold before the fuse, never after** (rounds 36 and 38). The layer-colored
  board colors the face objects `fuse_keeping_faces` hands back, and folding a
  shape replaces every face in it. And a fused board is several thicknesses at
  once inside a bend area that crosses a zone boundary, which no single pair of
  cylinders can carry — so every mode now folds per layer. Same reason the rim
  color asks "is this wall vertical" in the panel's own frame: after a 90° fold,
  half the board's flat faces are vertical.
- **Measure an OCC volume with the iterative overload** (round 38).
  `VolumeProperties_s(shape, props)` is 1.5% light on B-spline faces, which is
  enough to condemn geometry that is exactly right. Pass `(shape, props, 1e-5,
  False, False)` — in the tests too.
- **Area agreement is necessary, not sufficient.** It cannot see compensating
  errors (two caps inverted opposite ways) or geometry faithfully reproduced
  from a source that is itself wrong (a mitred join). Both were caught by
  rasterising a face to text with `BRepClass_FaceClassifier` — cheap, and the
  first thing to reach for when a shape looks wrong but the numbers agree.
- **The settings file may only be written if it was understood at load AND at
  save.** Two separate rounds of data loss came from getting this wrong.
- **A new code path must be checked against the requirement table above, not
  just against the old code's tests.** Round 34: the per-layer stackup emission
  was written without requirement #1 — silkscreen and paste mask excluded from
  the body — which `calculateBoardThickness` had honoured since round 2. It put
  four extra 0.025 sheets into a plain board and drew the legend twice, once as
  characters and once as a sheet covering the whole board. **It survived two
  rounds of testing because the rigid-flex test board carries no silkscreen or
  paste layers at all.** When a rule lives in one function and a second function
  is written to do the same job, the rule does not follow it; and a test corpus
  of one board shape will not notice.

### Not verified outside Allegro

- **The drill offset** (round 69). `s3dDrillXY` is transliterated and tested,
  and the geometry was confirmed by rebuilding from a hand-edited intermediate,
  but nothing has re-exported `bone-a2` from Allegro yet. What to look for: the
  four PLS-4 holes come out at `y = 0` rather than `y = 0.375`, as clean
  half-circles in the bottom edge.
- Per-segment path conversion producing round joins on a live board. The SKILL
  side warns if a path yields fewer polygons than it has segments.
- Runtime and the 400-polygon clip batch size on a dense board.
- **Bends fold correctly on the user's real board** (round 36b: probe, export,
  and a build here from the exported intermediate), and the user has confirmed
  it bends in the right places. Since round 37 the held piece is the one
  containing **the origin**, by convention — Allegro's own anchor point never
  reaches the database.
- **Bends are built on true cylindrical surfaces** (round 38, branch
  `feature/bend-mapper`): revolved where the strip is a prism, otherwise the
  outline is wrapped onto the cylinder, with the 7.5° facets left as a fallback
  that a real board no longer reaches. Both bends of flex-b2 wrap; all five of
  flex3-a0 do since round 41.

### Seven traps that cost a round each — do not rediscover them

- **A checker's own text is part of the input it reads back** (round 68).
  `s3dPreflight` ran `python -c "... ; print('S3D_OK')"` and scanned the captured
  output for `S3D_OK`. Python 3.13+ echoes the source line of a `-c` command in
  a traceback, so the *failure* output contains the success sentinel, the check
  passed itself, and the GUI was launched under `pythonw` — no console — to die
  invisibly. Written `print('S3D' '_OK')` now: same output, sentinel unspellable
  by the source. Same class as round 61's `IsDone` with zero solids and round
  14a. Also: **`python` is a name, not a program.** Installing anything that
  ships a Python (node.js, via Chocolatey, into the *machine* PATH) can put a
  different interpreter in front of the one the packages are in — so the check
  now prints `sys.executable` and the version, and an interpreter is pinned by
  full path in `allegro.python` / `allegro.pythonw` in the local config.

- **A command line handed to `cmd /c` must not begin with a quote** (round 43,
  and it is what round 5 misdiagnosed). cmd strips the first and the last quote
  of the line, so `"python" ... --json-dir "d:/my board/cad"` loses its quoting
  and the spaced path is split. Begin with a bare word — `start`, `cmd`, `cd` —
  and every quote inside survives. `s3dLaunch` and `s3dPreflight` both rely on
  this, together with `start ""` (empty window title) and `start /D` for the
  working directory. **Do not chain with `&&`**: a chain binds to the OUTER
  shell, so if `system()` wraps the line in a cmd of its own the `/D` is
  silently lost and `-m stepbuilder` stops resolving. `tests/test_launch_cmd.py`
  holds all of this, including the negative control.

- **A per-design cache in SKILL outlives the design** (round 42). The `.il`
  files load once per Allegro session, so any global built with
  `unless( G ... )` is still holding the previous board when the next one is
  exported. Everything of that kind must be reset at the top of
  `makeVariant3dIntermediates`; four globals are, and two of them only since
  round 42. **A global filled from the config is the same trap** — its default
  must be restored *before the config is even looked for*, or a board exported
  without one inherits the last board's setting (round 61, `S3D_NegativeLayers`).

- **`tconc` is destructive, and a list built once and reused is SHARED**
  (round 61). `cuts = cadr( edgeCuts )` is an alias; appending to it leaves the
  addition in the caller's list for the next export. The first file written was
  right and every one after it carried one more copy of every through-hole. When
  exactly one of several outputs is wrong, **ask what order they were written
  in** — and copy anything a loop is going to append to.

- **A boolean can report success and have produced nothing** (round 61).
  `BRepAlgoAPI_Cut` with two coincident prisms in the tool compound returns
  `IsDone() == True` and a non-null COMPOUND holding **0 solids**, so a board
  that checks only those two things accepts an empty result and writes a STEP
  with no board in it. `core.has_solid` is the test; use it after every board
  boolean, as `bend.py`'s `_is_empty` already did.

- **`BRepBuilderAPI_MakeWire` drops edges it cannot join, and still reports
  `IsDone`** (round 41). It joins at `Precision::Confusion`, a hard 1e-7 that
  no argument can widen, and past it starts a second wire instead of failing;
  `IsDone()` comes back true as soon as any later edge closes a loop. A solid
  that came out of a boolean has edges meeting only to its own vertex
  tolerance — 2.8e-7 on the real board — so the wrap hit this on every bend
  with a fillet or a sliver in it, and the only symptom was `the solid built
  from them is not valid` followed by facets. `wire_on` now makes one explicit
  vertex per junction and builds each edge on the vertices its neighbours
  share. **Raising the sewing tolerance does nothing** — the gap is upstream.
- **Allegro's flat pattern is laid out at k = 0** (round 41). A BEND_AREA is
  `angle × radius` exactly, and flex3-a0 proves this is the material budget and
  not merely a keep-out: two 180° areas 0.0001 mm apart close a ring to 0.5 µm
  at k = 0 and fall 0.61 mm short at k = 0.5. The default `foldNeutral` is
  still **0.5**, the physically right place for a symmetric flex; a board whose
  bends are laid edge to edge needs `--fold-neutral 0`, and the log now says so
  by name when two strips collide.

### Working method that has paid off repeatedly

Ask for the actual exported JSON. Reasoning from the SKILL documentation
produced three wrong rounds on the arc-sign question; the user's file settled it
in one, because the two round caps of a single stroke carry opposite signs and
that is visible in six lines of data. When a doc sentence admits two readings,
get the data.

## Environment (established)

- Allegro PCB Editor **24.1**, user tests live, gives console output / screenshots.
  (This line read 17.4 until round 21. The user moved to 24.1 at round 4 and every
  live confirmation since — rounds 9, 19, 20 — was on 24.1; `simple3d.il` has said
  24.1 all along. Round 8 spotted the contradiction and left it "pending
  confirmation", where it sat for thirteen rounds.)
- SKILL scripts live in `d:\Projects\OrCAD\Scripts\`.
- Project tree: `root\rev\pcb` (brd lives here, = cwd for SKILL) and `root\rev\cad`.
  Folder case varies — must match case-insensitively.
- Design units must be **mm** (the JSON is unitless and assumed mm downstream).
- Related earlier work: `myNcCutouts` writes circles onto `BOARD GEOMETRY/CUTOUT`
  (UNFILLED shapes only — SPMHDB-185) specifically so this 3D export sees milltab holes.

## The toolchain

```
File → Export → Simple 3D  (new SKILL: simple3d.il)
   └─ makeVariant3dIntermediates( <rev>/cad )     -> <design>.json
   └─ launch python GUI, prefilled                -> <brd>_simple_DD_MM_YYYY.step
```

Three moving parts:
1. `simple3d.il` — NEW. Menu item, config (default model dir, default color), path
   resolution (pcb -> cad), launches the exporter and then the GUI.
2. `makeVariant3dIntermediates.il` — existing (juulsA/exportStep). Takes the output dir
   as its **first argument** and `createDir`s it, so redirecting JSON to `cad` needs no
   patch — just the right argument.
3. `stepbuilder/` — Python port of StepBuilder.cpp (OCP / OpenCASCADE). Already written
   and verified against the C++ original (identical entity counts, bbox, volume).

## Upstream code facts (verified by reading the source)

- `makeVariant3dIntermediates( dir [, pcbColor] )`. `dsnName = axlCurrentDesign()`,
  `variantName = lowerCase( dsnName )`, `fileName = dir + "/" + variantName + ".json"`.
  The `name` field in the JSON == variantName, and the Python port currently derives the
  output STEP filename from it — must become an explicit parameter.
- With a `Variants.lst` in cwd it writes **one JSON per variant** named
  `<design>_<variant>.json`. Without it, one JSON with all symbols.
- `calculateBoardThickness()` returns `(top_mask, board, bottom_mask)` from
  `axlXSectionGet(nil 'all)`, summing CONDUCTOR + DIELECTRIC + PLANE into `board`.
- Component STEP mapping comes from `axlStepGet(nil nil sym)` — the stock Allegro
  STEP Package Mapping table, not a custom one.

### Known defects in the upstream .il (NOT yet fixed)

- `getVariantInfo()` is called but the procedure is defined as `gdsysGetVariantInfo()`.
- `addIndent()` is used ~8 times and is **not defined anywhere in the file** — external dep.
- `makeSlot` calls `makeCircle( x y drillSizeWidth )`; `makeCircle` takes 2 args.
- **MASK classification is broken**: `if layer->name == "SOLDERMASK_TOP" then top else bottom`.
  Every other MASK layer (SOLDERMASK_BOTTOM, PASTEMASK_*, possibly SILKSCREEN_*) falls into
  the `else` and **overwrites** `bottomSoldermaskThickness` (plain `=`, not `+=`), so the
  bottom mask ends up being whichever MASK layer happened to come last in the stackup.
  This must be fixed by name whitelist for requirement #1.
- Leftover `printf("i am here")` in `boardGeometryParseSegment`.
- **`boundp` misuse (x2)**: `makePcb` does `if( boundp('cuts) then ... else ...)`, but `cuts`
  is a formal parameter — always bound, even when nil. The `else` branch is therefore dead
  code. It contains `"thickness": 1.67` as a bare scalar (not the `{board: ...}` object the
  reader expects), so it was never valid anyway. Same pattern with `boundp('alternateParts)`
  (a `let` local) in `makeVariant3dIntermediates`. With no cutouts, `cuts` = nil and the
  live branch does `buildString( car(nil) ...)` — needs checking on a real cutout-less board.

### addIndent — confirmed missing

Used 8x, defined nowhere in the repo (the repo contains exactly one .il), and **not** an
Allegro/SKILL built-in (absent from skill_api_index). Inferred signature from usage and from
demo.json's formatting: `addIndent( t_string [, x_levels ] )` -> prefixes every line with
x_levels tabs (default 1). Must be written.

## Python port — fixes already applied

Cache mapping per-component (was per-STEP-file, first-wins); pathlib instead of hardcoded
`\`; no `cin.get()` (exit codes); sRGB color (`--legacy-color` restores old); free-shape
diff instead of `for i=2`; single-walk file index; always `edges[0]` as outline; checked
ReadFile/Write status; error on open contours.

Not yet done: soldermask thickness is read from JSON and ignored.

## Settled: "No module named stepbuilder"

**Closed — kept because the reasoning still explains the launcher's shape.**
`python -m stepbuilder` failed on the user's machine because the `-m` form needs
the *parent* of the package on `sys.path`, and Allegro's `shell()` launches with
cwd = the design dir. Settled by `S3D_ScriptDir` plus a `cd /d` into it in the
generated bat, so the interpreter always starts from the install folder. No
packaging (pyproject / console script) was needed.

(Round 9 recorded this as settled; the heading here still said "Open issue" for
nine rounds afterwards, which is the exact failure mode round 18 named — a
statement true when written and never revisited. Corrected in round 21.)

## Requirements (user, 2026-07-18)

1. Board thickness = dielectrics + planes + conductors + soldermask (both sides).
   Silkscreen and paste mask excluded. Example 2-layer: 1.464 + 0.045 + 0.045 + 0.025 +
   0.025 = 1.604.
2. Color dropdown in the GUI, colors from `Allegro3DCanvasPreferences.xml`.
3. `simple3d.il`: menu item, config (default model dir + default color), JSON to `cad`,
   launch GUI prefilled. Output name `<brd>_simple_DD_MM_YYYY.step`, `_` appended on collision.
4. Assembly: `symbols_top` / `symbols_bot` sub-assemblies at top level, unique names
   `refdes_<jsonname>`.
5. Minimise STEP file size; reuse component geometry.
6. Maintain this memo.

## Allegro3DCanvasPreferences.xml — what's in it

Path on user's machine: **unknown, need to confirm**.

8 FixedThemes: `Black, Blue, Dark_green, Green, Purple, Red, White, Yellow`.
`CustomThemes` is empty. `ActiveTheme = Dark_green`.

The color the user perceives as "board color" is the **soldermask** entry, and it is
semi-transparent (alpha 165/166) over the dielectric:

| theme | soldermask RGBA | dielectric RGB |
|---|---|---|
| Black | 0,0,0,166 | 253,255,215 |
| Blue | 37,93,171,166 | 253,255,215 |
| Dark_green | 26,89,36,165 | 253,255,215 |
| Green | 64,216,87,166 | 253,255,215 |
| Purple | 170,0,255,166 | 253,255,215 |
| Red | 207,11,31,166 | 253,255,215 |
| White | 255,255,255,166 | 253,255,215 |
| Yellow | 255,170,0,166 | 26,89,36 (!) |

Note Yellow's dielectric differs — looks like a preset quirk.

`Z0Position`: `Z0Layer = "TOP Conductor"`, `LayerPosition = "UPPER"`. So Allegro's own 3D
canvas puts z=0 at the **top of the top copper**, i.e. *below* the top soldermask. The
Python port currently also has z=0 at board top with top components at z=0 — consistent.
Adding mask thickness therefore raises the question of which side of z=0 it goes.

## Decisions (user, 2026-07-18)

- **Menu anchor found**: File → Export contains `MENUITEM "3D...", "3d_export_ui"`.
  Insert "Simple 3D" next to it via `axlUIMenuFind( nil "3d_export_ui")`.
- **Python**: 3.12.0, on the machine; console window is acceptable (no need for pythonw).
- **`axlCurrentDesign()`** returns the bare name, no path, no extension: `"my_test_board"`.
  So JSON stem == `lowerCase(dsnName)`, and STEP name = `<json stem>_simple_DD_MM_YYYY.step`.
  With variants the stem is already `<design>_<variant>`, which gives the requested
  `board_variant_simple_DD_MM_YYYY.step` for free.
- **Z axis**: parts sit **on the mask**, not on the copper — real pads carry solder that
  lifts the part to mask level. So: board = full 1.604 stack, top parts on the top mask
  face, bottom parts on the bottom mask face. GUI gets **two radio buttons** for where z=0
  lives: top side or bottom side of the board.
  - z0 = top: board spans 0 .. -T; top parts at 0, bottom parts at -T.
  - z0 = bottom: board spans +T .. 0; top parts at +T, bottom parts at 0.
- **Color**: no transparency, pure soldermask RGB. Colors **hardcoded** in the script
  (no runtime XML read).
- **Board edge (rim)**: separate color, exposed as a setting with documented values —
  same as board / cream dielectric / user-defined RGB.
- **Filename**: `board_simple_18_07_2026.step`. On collision the underscore **accumulates**
  (`board_simple_18_07_2026_.step`, `__`, ...) — deliberate, sorts better.
- **Variants**: export **all** of them, one STEP per variant.
- **Naming**: use the **MfrPN** user property (present on every component) as the part name.
  If a component lacks it -> warn and abort **without writing the JSON**.
- **Component colors**: mandatory, must be preserved — this is the point of the exercise.
- **`write.surfacecurve.mode = 0`**: worth trying; user will evaluate on several boards.

## Resolved 2026-07-18 (round 2)

### Stackup (real 2-layer board)

`axlXSectionGet(nil 'all)` fields:
`objType readOnly prop number position name layerType conductor mfg constraint thickness
tolPlus tolMinus layerId material fillinMaterial negativeArtwork unusedPin unusedVia
embedded embeddedAttach conductivity dielectricConst width lossTangent shield freqDepFile
etchFactor diffCouplingType diffSpacing`

```
nil                 nil          0.0     <- surface (air), name is nil
SILKSCREEN_TOP      MASK         0.025   excluded
PASTEMASK_TOP       MASK         0.025   excluded
SOLDERMASK_TOP      MASK         0.025   -> topMask
TOP                 CONDUCTOR    0.045   -> board
nil                 DIELECTRIC   0.964   -> board   (unnamed!)
BOTTOM              CONDUCTOR    0.045   -> board
SOLDERMASK_BOTTOM   MASK         0.025   -> botMask
PASTEMASK_BOTTOM    MASK         0.025   excluded
SILKSCREEN_BOTTOM   MASK         0.025   excluded
nil                 nil          0.0
```
=> `(0.025  1.054  0.025)`, total **1.104**.

**SILKSCREEN and PASTEMASK are also layerType "MASK"** — this is what made the upstream
`if name == "SOLDERMASK_TOP" then top else bottom` wrong. Classify soldermask by name
(`SOLDERMASK*`), side by `position` relative to the outermost conductor.

Dielectric pseudo-layers have `name` = nil. Any `%s` on it throws
("format spec. incompatible with data") — always guard, use `%L` when dumping.

### CORRECTION: my earlier boundp claim was wrong

`x = 'unbound` genuinely **unbinds** a variable in SKILL, and the upstream author uses that
idiom deliberately (`( cuts 'unbound )`, `( holes 'unbound )`). A formal parameter can
receive `'unbound` and be unbound. So `boundp` upstream is *correct*, and the
`"thickness": 1.67` branch is **not dead** — it is reachable and broken:
`create3dIntermediateFormat` leaves `cuts` as `'unbound` when `cadr(edgeCuts)` is nil, so a
board with no cutouts AND no through-hole pins emits a bare scalar thickness that the
reader rejects. Fixed by testing the value, not the binding.
(`boundp('alternateParts)` *is* always t — plain `let` local, no `'unbound` init. Minor.)

### addIndent reconstructed and verified

`addIndent( t_string [x_levels=1] )` -> prefix every line with x_levels tabs. Modelled in
Python; the resulting `makePcb` output matches `demo/ap-214/demo.json` **byte-for-byte**.
So the reconstruction is right — and the author clearly *has* the function, it just never
made it into the repo.

### MFRPN — DISABLED 2026-07-19 (see round 8)

**Now commented out end to end** (property read proved unreliable in practice;
kept in the source, disabled, for a future re-enable). The notes below describe
the intended design for whoever restores it.

Lives on the **component definition**, not the instance (F4: "Properties attached to
component definition -> MFRPN = SP3030-01E"). Access `sym->component->compdef`. Comes in
via the netlist, so parts not on the schematic do not have it. F4 also shows
`PKGDEF_STEP_FILE` on the symbol definition — that is what `axlStepGet` reads; no need to
parse it by hand.

Policy: check only components that would actually be exported (refdes + STEP mapping), log
every refdes that did not make it into the export.

### Menu

`File -> Export` contains `MENUITEM "3D...", "3d_export_ui"` — anchor for `axlUIMenuFind`.

## Delivered so far

- `exportstep_fixes.il` **v1.1** — overlay over the upstream file (addIndent, getVariantInfo
  alias, calculateBoardThickness, makePcb, symbolReturn3DElements + `mfr_pn`, MFRPN
  helpers, `s3dCheckMfrPn` pre-flight). Paren-balanced per procedure; **not yet run in
  Allegro**.

## Code review 2026-07-18 (all delivered code)

### Python (executable -> tested)
Fixed during review, regression against the C++-verified reference stays green
(5054 entities, V=12073.309477):
- **Cutouts batched into one boolean Cut** (compound tool). The per-cutout loop was
  quadratic; measured **11x faster at 120 drill holes**, identical volume. Matters because
  the exporter emits every through-hole as a cutout contour.
- **Open-wire detection**: `wires.Length()>1` only caught *fragmented* contours; a single
  open wire sailed through MakeFace into silent garbage. Now `wire.Closed()` after
  ConnectEdgesToWires (verified: True/False on closed/open test wires).
- IsDone/IsNull checks on MakeFace, Cut; writer.Transfer return checked.
- Edge tests pass: no-cutout board, open contour, unknown primitive, missing STEP file
  (skip+report), component without mapping (skip+report).
- GUI threading model reviewed: worker touches only the queue, all tk mutations on the
  main loop via after(). Known nit: closing the window mid-generation kills the daemon
  thread abruptly — acceptable.
- ruff + py_compile clean.

### SKILL (not executable here -> hardened by cross-checking)
Every builtin cross-checked against three sources: addeskd_v30.il (proven on the user's
machine), upstream .il (produced demo.json), skill_api_index. Replaced everything not
confirmed by at least one:
- `pairp` -> `p && listp(p)` (listp: 3x in addeskd_v30)
- `reverse` -> tconc accumulation (tconc: 16x upstream); note `tconc(nil nil)` seeds the
  list with a nil placeholder, stripped via `cdr(car(...))`
- `foreach(mapcar ...)` -> `mapcar(lambda ...)` (upstream idiom)
- 3-arg `if` -> `if(... then ... else ...)` everywhere (neither source uses the 3-arg form)
Confirmed-good: parseString, buildString, substring(start,len), upperCase, strlen, errset,
defvar, boundp, xCoord/yCoord, case with string keys, string `==`.
Paren balance: file 0, every procedure closes. parseString's empty-line collapsing
documented in addIndent (harmless: generator never emits empty lines, byte-verified).

## Open questions

- [ ] Shape of `axlDBGetProperties` entries — (name . value) or (name value)? Both handled,
      but wants confirming on a real component.
- [ ] Board rim color default (same as board / cream / custom).

## STATUS: requirement table — LIVING, keep current

First written 2026-07-18, when all six were implemented. Unlike the dated round
entries below, this table is **not** a historical snapshot: revise a row in place
whenever a later round changes that requirement's state, and name the round that
changed it so the trail stays followable. Last revised: round 17 (2026-07-23).

Delivered files (as of 2026-07-18; the `exportstep_fixes.il` overlay was folded
into `makeVariant3dIntermediates.il` in round 4 and no longer exists):
- `exportstep_fixes.il` v1.1 — SKILL overlay (thickness, addIndent, mfr_pn, pre-flight).
- `simple3d.il` v1.0 — File→Export→Simple 3D menu, pcb→cad, launches prefilled GUI.
- `stepbuilder/` — Python package: core.py, colors.py, gui.py, __main__.py.
- `simple3d_config.json` — added round 10: silkscreen layer lists + ink settings.

| # | requirement | status |
|---|---|---|
| 1 | mask thickness in board | done; core.total_board_thickness: board+both masks. Verified 1.104. Limitation: mask layers count only if named `SOLDERMASK*` (round 2 decision) — a stackup naming them otherwise contributes 0.0 silently. |
| 2 | color dropdown in GUI | done; colors.py: 8 themes from XML, dropdown + swatch. |
| 3 | simple3d.il menu, pcb→cad, dated name, prefill | done; anchor 3d_export_ui; --dated-name accumulating _ |
| 4 | symbols_top/bot, unique names `refdes_<jsonname>` | **PARTIAL** — groups and shared parts done (part = model file). The `refdes_<jsonname>` instance naming this requirement asks for was **removed in round 8** as over-complication, so no reference designator survives into the STEP at all. The requirement itself was never withdrawn: either restore the naming or amend requirement 4. |
| 5 | minimise size / reuse | done; surfacecurve.mode=0 (~49% smaller) + one shared part per model |
| 6 | MFRPN in json | **DISABLED in round 8** — property attachment proved unreliable in practice. Every branch is commented out, not deleted, in both `.il` files and all three `.py` files, marked `MFRPN DISABLED (kept for future)`. Nothing writes or reads `mfr_pn` now. |
| 7 | silkscreen export (user, 2026-07-22) | **done and confirmed on the user's boards** (rounds 10–12). `format_version: 2`; polygons carry Allegro's own area and the reader resolves the vertex-radius reading against it (settled: axis / positive-sits-left / first-radius-closes). Solid or flat, per side, White/Black, clipped to outline−cutouts. Flat faces are unioned; solid ones deliberately are not. |
| 8 | mechanical symbols + `NO_STEP_EXPORT` (user, 2026-07-23) | done in round 11; **extended in round 19 and confirmed live 2026-07-24** to mechanical symbols that carry a STEP model (`PKGDEF_STEP_FILE`) but have **no refdes** — they were silently dropped by the refdes gate before, now they export (`axlStepGet` on a mechanical instance returns the mapping; no `sym->definition` fallback needed). Export list comes from the design and the variant table only subtracts — but since **round 52** it subtracts on the refdes alone: a symbol with a refdes that the variant does not install is dropped even if it is mechanical, and only a symbol with NO refdes is outside the variant system. `NO_STEP_EXPORT` excludes outright and is logged by refdes — **confirmed live 2026-07-24: `axlDBGetProperties` sees the property and marked symbols are excluded.** |
| 10 | silkscreen layers chosen in the GUI (user, 2026-07-23) | done in rounds 14-17; `format_version: 3`. Every polygon carries its layer, the panel offers what the JSON contains, exclusions are persisted, a side switched off greys its layers. Zero-width objects reported by layer and position. Console colored by severity via `axlUIWPrint` — no green severity exists. |
| 11 | multi-stackup + bent flex (user, 2026-07-25) | **multi-stackup done in round 26**; `format_version: 5`. Zones read from the design with their own outline and stackup thickness, fused into one board, components placed on their own zone's surface, zones aligned on the shared conductor core. Fixed two live defects on the way (see round 26). **Bends deliberately NOT done** — the data is available but folding is a separate effort of comparable size to the whole tool, and the bend parameters live in an undocumented `IDX_BEND_TYPE_INFO` property. Board is exported flat. |
| 9 | one settings file (user, 2026-07-22) | done in round 10h. `simple3d_config.json` holds every user setting, read by both halves; only `S3D_ScriptDir` stays in SKILL source, for bootstrap. Rounds 12–13 fixed two ways the GUI could damage it. |

### Verification done here
- Core geometry still bit-for-bit vs C++ (V=12073.309477, 5054 ents) with mask zeroed.
- Mask thickness: board 1.036 -> 1.096 with 0.03+0.03 demo masks; z_datum top/bottom both correct.
- Assembly tree: board -> PCB / symbols_top / symbols_bot, shared part across 3 instances.
- CLI single / dated-name collision / batch variants all pass.
- GUI rendered under Xvfb: color dropdown+swatch, rim dropdown, z radios, checkboxes;
  Generate works; --gui prefill launch fills paths + color.

### NOT verifiable here (user must confirm in Allegro)
- `getWorkingDir()` — not in the project API reference. simple3d.il has a load-time
  self-test that prints exactly what to edit (s3dDesignDir) if it fails.
- `axlUIMenuInsert` actually placing the item (idiom copied from working addeskd_v30).
- `axlDBGetProperties` entry shape for MFRPN read (both shapes handled).
- End-to-end: menu click -> JSON in cad -> GUI opens prefilled -> STEP written.
- `--gui` process detaching cleanly via `cmd /c start`.

## Update 2026-07-18 (round 4)

- **Overlay dropped.** exportstep_fixes.il is gone; all fixes + addIndent + MFRPN
  helpers are now folded directly into makeVariant3dIntermediates.il with a credit
  header and inline "FIX (simple3d)" / "NEW (simple3d)" markers. Two SKILL files now:
  makeVariant3dIntermediates.il + simple3d.il.
- **Fixes now inline in the rewritten file:** removed printf("i am here"); getVariantInfo
  -> gdsysGetVariantInfo; calculateBoardThickness (soldermask-only, by position); makePcb
  no-cuts branch emits real thickness object (was bare 1.67); makeSlot makeCircle(x y d)
  -> makeCircle(list(x y) d); symbolReturn3DElements emits mfr_pn. JSON output modelled
  in Python and parses valid.
- **Version bump:** 17.4 -> 24.1 everywhere (user now on 24.1).
- **Stale-path bug FIXED.** prefill_jobs now always overrides config-remembered paths and
  resets _job_jsons; output_dir passed through from launcher. Reproduced the exact bug
  (board A config + board B launch) and confirmed B's paths win. This was the "json points
  to previous board, 3D contains previous board" report.
- Core geometry still matches C++ (V=12073.309477); minimize on/off 106K/238K.

### Still user-verified only
- The rewritten makeVariant3dIntermediates.il running clean in Allegro 24.1 (balance OK here).
- calculateBoardThickness on 24.1 -> expect (0.025 1.054 0.025).

## Update 2026-07-18 (round 5) - spaces in paths

> **Superseded by round 43.** The fix below works, but the diagnosis under it —
> "start eats the first quoted token as the window title" — is not what was
> actually breaking the spaced path. It was cmd's own quote-stripping rule, and
> once that is understood the batch file is unnecessary. Both `.bat` files are
> gone since round 43; read that round before believing this one.

- **Bug:** a design path with a space (".../my test1/A1/cad") broke the launch.
  Root cause was `cmd /c start "Simple3D" /D "dir" "python" ... --json-dir "path with space"`:
  start eats the first quoted token as the window title and the quote nesting
  collapses, so the spaced path was split -> python got a truncated json-dir ->
  "Input file does not exist".
- **Fix (SKILL):** s3dLaunch now writes the full command into a one-shot
  `_simple3d_launch.bat` (outfile/fprintf/close, all proven builtins) and runs
  `cmd /c start "" "that.bat"`. cmd reads the quoted args from the file natively;
  no nesting through start. Verified the generated bat preserves the spaced path
  (shlex parse: --json-dir kept whole).
- **Fix (Python, defensive):** GUI._generate now filters to real files and, if
  none, raises a clear error naming the path instead of the generic
  "input file does not exist". Python itself already handled spaced paths fine
  when args arrive intact (CLI batch test with "/tmp/my test1/.../cad" and even a
  spaced OUTPUT dir both pass).
- Note: if S3D_ScriptDir or the model lib dir themselves contain spaces, they are
  quoted in the bat too, so they are fine.

## Update 2026-07-18 (round 6) - variants, console, rim, JSON tagging

Root cause of "Export complete! but no file": a Variants.lst from ANOTHER project
sat in the working folder. gdsysGetVariantInfo returned tables with 0 keys, the
variant foreach ran zero times, no JSON written, "Export complete!" still printed
(it lives after the loop, only in the variant branch). Confirmed: user's
gdsysGetVariantInfo -> (table:variantTable table:alternateParts), car is a TABLE
not a list, 0 variants.

Fixes:
1. **Wrong-Variants.lst detection.** variantSymbolList is a table (always truthy,
   length() N/A), so count keys by iterating. variantCount==0 -> clear error
   "belongs to a different project, delete/replace/remove it". Prints
   "N variant(s) parsed" always.
2. **Recursive mkdir** (s3dMakeDirs): createDir does one level; walk segments,
   skip the "d:" drive token. Verified segmentation in Python.
3. **outfile guard + post-write confirm**: writes "writing -> path", "wrote path",
   or errors if the file is absent after close. (User's outfile probe returned a
   port and wrote fine, so writing itself was never the issue - it was the empty
   variant loop.)
4. **Console window closes** (point 1): s3dLaunch writes a .bat that does
   `start "" pythonw ... argtail` and exits, so the cmd window closes and pythonw
   has no console. New setting S3D_PythonW (default "pythonw"). Python side wraps
   the GUI in a crash handler that writes simple3d_crash.log + a dialog, since
   pythonw would otherwise hide a startup crash.
5. **JSON format marker** (point 2): every intermediate gets
   "format":"simple3d","format_version":1. core.is_simple3d_json() checks it;
   GUI prefill + CLI --batch filter globbed *.json to only tagged files and log
   the ignored ones. core._reserved excludes format/format_version from the
   component loop. Foreign Variants.lst-style json is now ignored, not built.
6. **Rim color bug** (point 3): _top_and_bottom_faces classified by z-position,
   but a straight board's side walls have z_com == mid exactly, so `>= mid` swept
   them into "top" and the rim color landed on a flat face. Replaced with
   _rim_faces() classifying by NORMAL: vertical walls (|normal_z|<0.5) = rim,
   curved cutout walls included. Verified: 4 walls plain, 5 with a hole, flats
   excluded; cream rim + green board both present as distinct colors.

Full consolidated regression: 7/7 pass. Core geometry still == C++ 12073.309477.
ruff: only E501 line-length (cosmetic), no F-code (functional) issues.

### Still user-verified only (Allegro 24.1)
- The two SKILL files loading and running clean (balance OK, builtins all proven).
- pythonw path correct on the user's machine (or set S3D_PythonW).
- The wrong Variants.lst: user should delete/replace it - the script now says so.

## Update 2026-07-18 (round 7)

1. **Colored log** (point 1): tk Text tags - warning #d9791e (orange), error
   #8b0000 (dark red), success green. _append_log auto-detects severity from the
   message prefix (warning/ignored/error/traceback); done->success, error->error
   tagged explicitly in the drain. Rendered under Xvfb: orange "Ignored..." line
   confirmed. Detection unit-tested (6/6).
2. **ncroute_path** (point 2): DECIDED to document, not implement. A route path
   is an open centerline + tool width, not a closed boundary; turning it into a
   solid needs offset-by-half-width + rounded ends + corner handling = a lot of
   fragile geometry for a "simple" tool. README now says: draw non-plated slots
   as a CLOSED contour on BOARD GEOMETRY/CUTOUT. calculateBoardThickness got a
   comment noting single-stackup only.
3. **Multi-stackup** (point 3): no reliable detection API in the reference (no
   zone/stackup field on the xsection layer struct; conductor-count heuristic
   false-positives on normal multilayer, so reverted). Documented as unsupported
   limitation in README + a NOTE comment in calculateBoardThickness.
4. **Bilingual README** (point 4): full EN + RU - why it exists, full install
   (Python, cadquery-ocp, file layout, ilinit), every setting explained, GUI
   table, assembly structure, thickness formula, limitations, CLI. Has a
   changelog section; update it on future changes. Lives at
   stepbuilder-py/README.md (422 lines).

Core regression still V=12073.309477. ruff F-codes clean.

### Still user-verified only (Allegro 24.1)
- makeVariant3dIntermediates.il + simple3d.il load/run clean (balance OK).
- Rim color on a real board with cutouts.
- Colored log appearance on the user's Windows tk theme.

## Review 2026-07-19 (full code + README review)

### Real bugs found and FIXED
1. **Stale job queue** (gui): _job_jsons was cached at prefill; Browse to a
   different json (or manual edit) changed only the field -> Generate built the
   OLD queue. Fixed by REMOVING the cached state entirely: core.resolve_json_jobs
   resolves jobs from the field at Generate time (dir -> filtered glob, file ->
   marker check). Field is always the truth. Tested: prefill folder A, browse to
   file B -> builds exactly B.
2. **Variant names collapsed under --brd-name** (gui + CLI): base = brd_name or
   jf.stem gave every variant the same name (differing only by collision _),
   contradicting the README. Fixed: len(jobs)>1 -> jf.stem (design_variant);
   brd_name applies to a single json only. Tested: board_base/_top keep names;
   single json keeps original-case brd_name.
3. **Duplicated dated-name logic** (gui + __main__ copies) -> one shared
   core.dated_output_name. Collision test passes.
4. **JSON marker double-indent** (SKILL): embedded tab + writer per-line tab
   made format_version/name indent 2. Removed embedded tabs; modeled output is
   uniformly indented and valid.

### README review (verified against code)
- Removed stale S3D_DefaultModelDir rows (setting no longer exists - the cad
  fallback is now the design's own folder).
- Flags lists were missing --batch and --quiet; added (EN+RU) with a note on
  the new --brd-name semantics for variants.
- Changelog entry added (bilingual).
- Verified accurate: settings table (8/8 match simple3d.il), install layout,
  folder-resolution section, filename rationale, thickness formula, GUI table,
  limitations (ncroute_path, multi-stackup, UNC noted in s3dMakeDirs comment).

### Regression: 8/8 (core V=12073.309477, rim=4 walls, resolver, dated
### collision, minimize halves). F-lint clean, SKILL balance 0 both files.

## Update 2026-07-19 (round 8) — one folder, MFRPN off, PCB naming, flat symbols

Packaging (prior round, recorded here): the whole project is now one
self-contained folder, `d:/Projects/OrCAD/Scripts/Simple3D/`. `S3D_ScriptDir`,
both `load()` lines and every install path point at it. `S3D_ModelLibDir`
(`d:/Projects/OrCAD/CIS/3D`) stays outside — it is the shared component library.
The two READMEs were merged into one bilingual file, disclaimer kept.

Four changes this round (user request):

1. **MFRPN commented out everywhere, kept for future.** Property attachment was
   unreliable and not everyone needs it, so every MFRPN branch is disabled (not
   deleted) with a `MFRPN DISABLED (kept for future)` marker:
   - `makeVariant3dIntermediates.il`: `S3D_MfrPnProp`, `s3dPropCI`,
     `s3dGetMfrPn`, `s3dJsonEscape` procedures commented out; the `mfr_pn` read
     and its JSON field emission commented (the `"},\n"` that closes
     `step_mapping` already carries the trailing comma, so the JSON stays valid).
   - `s3dCheckMfrPn` is **kept** but only its no-model half now runs — it still
     returns `(nilMfrPnSlot noModelList)` so `simple3d.il` reads `cadr` for the
     no-model report. The MFRPN accumulation branch is commented with a `t`
     placeholder in the `then` clause.
   - `simple3d.il`: `S3D_StrictMfrPn` setting and the MFRPN pre-flight block
     commented; the **no-3D-model** pre-flight (useful, non-MFRPN) is retained.
   - Python: `core.generate`'s `name_instances_with_mfr_pn` param + docstring,
     the `mfr_pn` tracking, and `BuildResult.missing_mfr_pn` commented;
     `__main__` `--mfr-pn-in-name` arg + kwarg + warning commented; GUI var,
     checkbox, kwarg, warning, and config load/save lines commented. The GUI
     "Minimise file size" checkbox stays (now the only one in that row).
2. **Board part named `PCB_<json_stem>`** (was a bare `PCB`, which some viewers
   showed as `PCB_1`). `json_stem` is the same identifier already used for the
   output `.step` filename and the assembly root, so all three are unique and
   consistent per board — importing several boards no longer lets one board's
   PCB substitute another's. (`core.py`, one line + rationale comment.)
3. **Symbols tree flattened.** Removed the per-refdes wrapper sub-assembly and
   the `refdes_<board>` instance naming (over-complication). Under
   `symbols_top`/`symbols_bot` the shared model part is now added **directly**
   as an instance carrying its STEP file's own name; identical footprints still
   share one solid. (`core.py`, placement loop rewritten.)
4. **GUI swatch moved.** The board-color swatch was pushed to the right edge by
   the expanding grid column; it now sits in a small frame beside its dropdown
   (`ttk.Frame` + `pack`), directly to the right of the combobox.

README updated to match (EN+RU): assembly-structure tree + bullets, PCB naming
note, MFRPN rows removed from settings/GUI tables, `--mfr-pn-in-name` dropped
from both flag lists, tree comments de-MFRPN'd, changelog entry added.

### Verified here
- All three `.py` files `py_compile` clean; no active (uncommented) `mfr`
  reference remains in Python.
- SKILL: no active call to any commented procedure remains (only benign unused
  `noMfrPn`/`mfrPn` locals and the intentional empty return slot in
  `s3dCheckMfrPn`). Paren-balance delta unchanged by the edits in both `.il`
  files (identical before/after), i.e. the commenting is paren-neutral.

### NOT verified here (user must confirm live in Allegro)
- The STEP tree actually showing model parts directly under `symbols_*` with
  their STEP-file names, and the board part as `PCB_<board>` — CAF instancing
  and how a given viewer labels repeated instances is review-only here.
- GUI layout (swatch beside the dropdown) — no display available; code review only.
- SKILL still loads/runs cleanly and the no-model pre-flight still fires.

### Pre-existing, flagged (not touched)
- The Environment block at the top says Allegro **17.4**, but later sections and
  `simple3d.il` say **24.1** — stale top line, left as-is pending confirmation.
- `demo/ap-214/demo.json` still carries old `mfr_pn` fields; harmless (the core
  no longer reads them). Regenerating it needs Allegro.

## Update 2026-07-21 (round 9) — GUI threading, batch isolation, Python pre-flight

Started as a full-repo review; four of its findings were then fixed, and the
SKILL fixes cost two live-debug cycles that are worth recording (below).

### Fixed — Python

1. **GUI read Tk variables from the worker thread.** `_generate` called
   `self.step_dir.get()` and seven more, including `_rim_color()`, on the
   background thread. That enters the Tcl interpreter off the main thread:
   `RuntimeError: main thread is not in main loop` on a non-threaded Tcl, a data
   race on a threaded one. **The round-7 review at line ~246 above missed this**
   — it checked that the worker performs no tk *mutations* and stopped there;
   the reads were never considered. Fixed with a frozen `BuildSettings`
   dataclass (`gui.py:43`) filled by `_snapshot()` (`gui.py:306`) on the main
   thread in `on_generate`, and passed into the worker. Frozen also means a
   widget edit mid-build can no longer change the build in flight.
   `_snapshot()` calls `_rim_color()`, so the early color validation still
   happens before the thread starts.
2. **One bad variant aborted the whole GUI batch.** The per-job loop had no
   try/except, so the first `StepBuilderError` cancelled every remaining
   variant — while the CLI counted the failure and carried on. Two entry points
   over one core disagreed. Fixed at `gui.py:375-...`: per-job try/except
   (`StepBuilderError` for clean text, bare `Exception` with traceback for the
   unexpected), a `failures` list, `", N failed"` appended to the summary, and
   all-jobs-failed reported as an error instead of a green "Done: 0 file(s)".
3. **Log severity moved to the source.** `Could not find X` was rendered plain
   because the GUI infers severity from a prefix list. Rather than add a pattern,
   `core` now labels its own lines: `warning: could not find X` (`core.py:572`)
   and `warning: <ref> has no step_mapping, skipped` (`core.py:563`). The
   `"could not find"` special case was then removed from the GUI list, which is
   now two named tuples (`gui.py:38-39`). **Side effect worth knowing:** the CLI
   prints the same strings, so its output changed — both lines now carry a
   `warning:` marker they did not have before. Nothing in the repo parses it.
   Still uncolored by design: `if not roots` (`core.py:605`) logs nothing at
   all, to avoid one line per component for a single missing STEP file.

### Fixed — SKILL

4. **The GUI could fail to start with no message anywhere.** It is launched
   detached (`start`) and normally through `pythonw.exe`, which has no console:
   a missing Python or a missing `cadquery-ocp` killed it instantly and the user
   saw the JSON appear and nothing else. New `s3dPreflight` (`simple3d.il:266`)
   runs the interpreter **once, synchronously**, capturing stdout+stderr to a
   file, and reports in the Allegro console **leading with the good news** — the
   JSON is fine, only the viewer failed. Success is a printed sentinel
   (`S3D_OK`), not an empty log: some installs write deprecation warnings to
   stderr on a successful import.
5. **Mojibake in that report.** cmd's "is not recognized as an internal or
   external command" is localised *and* emitted in the OEM codepage (866 on a
   Russian Windows); the Allegro console renders it as garbage, and re-encoding
   it in SKILL is not practical. Instead the bat flags the case with an ASCII
   marker — `if errorlevel 9009 echo S3D_NOEXE` (`simple3d.il:294`) — and the
   report prints our own English text for it, never the captured bytes.
   Python's own tracebacks are ASCII and are still shown verbatim.
6. **`s3dLaunch` was a silent no-op on a read-only `S3D_ScriptDir`.** `when(port
   ...)` with no else. Now reports and prints a ready-to-paste manual launch
   command (`simple3d.il:368`). The sibling file already had the right pattern
   (`makeVariant3dIntermediates.il:979` errors when `outfile` returns nil) — it
   had simply never propagated here.
7. **Variant "alternate parts" were silently dropped from the export.** Reported
   from a real board (`PAG30N .../C0/PCB/Variants.lst`): two
   `*WARNING* (axlStepGet): Invalid database id argument - nil` lines per run.
   A Variants.lst variant holds a `base` refdes list plus optional per-component
   parameter overrides:
   ```
   ("BNO"
       (base (A1 C1 ... ZQ3) )
       (C43 VALUE="12pF" JEDEC_TYPE="CAPC100X50X55L25N" TOL="1" )
       (C44 VALUE="12pF" ... )
   )
   ```
   Those C43/C44 entries are components installed in that variant with
   overridden parameters. They reached `symbolReturn3DElements` through
   `append( variantSymbolList[variant] alternateParts[variant]~>? )`.

   **Root cause: `gdsysGetVariantInfo`'s own Variants.lst parser.** Note this
   procedure is defined **in this same file** (~line 176), not an external API —
   an earlier claim in this round that it was an undocumented Allegro function is
   corrected below. When it parses an alternate-part line it computes `refDes`
   correctly and keys `parts[refDes]` by it, but then appends the wrong thing to
   the variant's symbol list:
   ```skill
   subStrings = parseString( temp "\\\\" )        ; REASSIGNED to property chunks
   ...
   parts[refDes] = partProperties                 ; correct
   symbols = nconc( symbols list( nth( 0 subStrings ) ) )   ; <- first PROPERTY token
   ```
   So `variantTable["BNO"]` carried two bogus `VALUE=12pF` entries instead of
   `C43`/`C44`. The bug is duplicated in both parser branches — the single-line
   and the multi-line-properties path. Fixed to `list( refDes )` in both.

   **`~>?` was innocent.** `alternateParts[variant]` is a table keyed by refdes
   (`printf( "%L\n" cadr( gdsysGetVariantInfo() )["BNO"] )` → `table:parts`), and
   `~>?` over it returns those keys, so the append *was* delivering `C43`/`C44` —
   which is exactly why the capacitors were placed correctly all along. With the
   parser fixed, `variantSymbolList[variant]` holds every installed refdes on its
   own, so the append is now redundant and would duplicate them; dropped. The
   dead `boundp('alternateParts)` test went with it (the "Minor" from round 2).
   `alternateParts` remains available for what it is actually for — per-part
   property overrides, which a 3D export does not need.

   **Three wrong turns worth recording, since two were mine and one was avoidable
   only by looking:**
   1. Guessed the cause was symbol-vs-string in `axlDBFindByName`. Wrong.
   2. On seeing `table:parts`, concluded `~>?` yielded property tokens and the
      append was broken. Also wrong — it yielded keys.
   3. Then concluded the append was *unnecessary* and dropped it, which — before
      the parser fix — would have removed C43/C44 from the export entirely. The
      user's own observation ("the capacitors are placed regardless") is what
      contradicted the story and forced reading the parser instead of guessing at
      it. The procedure was local and readable the whole time.

   **Kept from the wrong attempts, because they earn their keep:**
   - the refdes guard at `makeVariant3dIntermediates.il:739`, which turns an
     unresolvable refdes into `Simple 3D: <ref> - not found in the design,
     skipped.` instead of an opaque `axlStepGet` warning plus a silent drop. It
     is what made the junk visible by name in the first place. Confirmed live: a
     deliberately inserted `VT100` is reported correctly.
   - the `unless( stringp( refDes ) ...)` coercion, now purely defensive.

### SKILL prog/let — two runtime errors, both self-inflicted

Adding `return()` to those procedures broke the export twice in the user's
Allegro before it worked. Both rules are absent from `skill_api_index` and from
`skill_doc` (which covers the `axl*` API and DB attributes only) but are visible
in the example scripts under `skill_doc/skill/`:

- **`return()` is legal only inside `prog`**, never `let` → *"return can only be
  used within a prog"*. Cadence's own example annotates it:
  `prog( (fw position) ; need to do this since have a return`.
  Note this was **pre-existing and latent**: the `return( nil )` in the "no
  design is open" branch sat in a `let` from the start and had simply never been
  reached, because the menu implies an open design.
- **`prog` var lists take bare symbols only** — the `(var value)` init form is
  `let`-only syntax → *"local vars must be symbol"*.
- **`prog` returns nil unless an explicit `return()` runs.** The body's last
  value is not the result, unlike `let`. So `s3dExportCommand`'s trailing `t`
  had to become `return( t )`, or a fully successful export would report nil.

`s3dExportCommand`, `s3dPreflight` and `s3dLaunch` are now `prog`. The
pre-flight call is additionally wrapped in `errset` (`simple3d.il:214`): a fault
inside the diagnostic must degrade to "check skipped, launching anyway" rather
than replacing the diagnosis with a SKILL trace — which is exactly what happened
twice during this round.

A static checker was written (paren balance + `return` outside `prog` + init
forms in a `prog` var list) and self-tested by reintroducing both bugs into a
copy; it caught both. It currently lives in scratch, not in the repo — worth
adding if SKILL edits continue.

### Corrections to the 2026-07-20 repo review

- **Withdrawn:** the claim that `makePcb`'s `if( boundp( 'cuts ) ...)` has no
  `else`, and therefore that an all-SMD board breaks. The `else` is at
  `makeVariant3dIntermediates.il:886` and emits a proper thickness object; the
  round-2 correction above (line ~188) already explains why `boundp` is right
  here. The finding was made from a truncated grep window.
- **Reframed:** the soldermask-name finding. Gating on a `SOLDERMASK` prefix is
  the deliberate design recorded in round 2, not an oversight. It remains an
  **undocumented limitation** — a stackup whose mask layers are named otherwise
  (`SM_TOP`) silently contributes 0.0 to thickness — and belongs in the README
  limitations list.
- **Confirmed, still open:** `boundp('alternateParts)` is always t (already
  noted at line ~197 as "Minor"); the flattened symbols tree still contradicts
  requirement #4, which was never withdrawn.

### New lead — thickness may not need to be hand-rolled

`axlXSectionGet( nil 'thickness )` returns, per the Allegro SKILL reference,
*"provided stackup thickness in user units ... **This is the total thickness
with masks**"*. `calculateBoardThickness()` sums the stackup by hand and decides
mask inclusion by name — i.e. re-implements this, with the naming fragility
above. The three components are still needed separately for the JSON, but the
API value is an authoritative cross-check. Not acted on: the open question is
what to do when the two disagree (trust the API, warn, or both).

### Verified here
- `py_compile` clean on all four `.py`; no Tk access remains inside `_generate`
  (checked by grep over the method body).
- Every `core` `log()` literal mapped through the actual `_append_log` logic:
  two warnings colored, four neutral lines untouched.
- Both `.il` files: paren balance 0/0, and every `return()` now sits in a `prog`
  (static checker, which was itself verified against deliberately broken copies).
- Every `axl*` call in both `.il` files exists in `skill_api_index` (16/16), and
  every `->attribute` resolves against `skill_db_attributes` or the function's
  own doc page (`axlStepGet`, `axlXSectionGet`). `gdsysGetVariantInfo` is not in
  the index — **because it is defined in `makeVariant3dIntermediates.il` itself**
  (~line 176), not an Allegro API at all. An earlier draft of this round called
  it an undocumented external dependency that an Allegro upgrade might remove;
  that was wrong, and it cost time in item 7 above: the parser whose behaviour
  was being guessed at was sitting in the same file.

### Confirmed live by the user (Allegro 24.1, 2026-07-21)
- **Pre-flight, missing-package branch:** with the `stepbuilder` package absent,
  the console report is correct — the JSON-is-fine preamble followed by Python's
  own (ASCII) ImportError. This is the third `cond` branch, the one that prints
  the captured text verbatim.
- **Implied by the above, and the point of the two failed attempts before it:**
  the report printed to completion and the command ended cleanly, so
  `s3dPreflight`'s `prog` body, the sentinel scan, and `s3dExportCommand`'s
  `unless( pyOk ) return( nil )` all execute. The `let` → `prog` conversion works
  on a live path, not just on paper.

- **Pre-flight, interpreter-not-found branch:** a bad `S3D_Python` (`_python`)
  now reports adequately. This is the `S3D_NOEXE` path, i.e. the encoding fix
  works: cmd's localised OEM-codepage message is no longer printed, our own
  English text is.

### How the success path terminates (asked 2026-07-21, worth writing down)

**Nothing is printed after the GUI closes, by design.** The GUI is launched
detached — `s3dLaunch` writes a bat whose body is `start "" pythonw ...`, so
`system()` returns as soon as cmd exits, long before the window is even drawn.
`s3dExportCommand` then hits `return( t )` and the SKILL command is over; it
holds no handle on the Python process and cannot report on it. The last console
line of a successful run is `Simple 3D: launching GUI (-m stepbuilder --gui ...)`.

Consequence for verification, correcting what an earlier draft of this round
said: `return( t )`'s value goes to Allegro's interactive-command dispatcher and
is displayed nowhere, so it cannot be observed by watching the console. It does
not need to be. It is the statement immediately after that `printf`, so seeing
the "launching GUI" line and a window appear with no `*Error*` already proves
the `prog` body ran to the end — through `s3dLaunch`'s own `return( t )` — and
that the conversion is sound on the success path too.

### NOT verified here (user must confirm in Allegro)
- GUI: the batch-isolation path (queue several variants, break the second — the
  rest should build and the summary should end `, 1 failed`).
- Log colors on the user's Windows tk theme.

### Doc debt found while reading this memo

**Fixed in this round:**
- The requirement table claimed req 4 done with `instance=refdes_json, +MFRPN
  flag` and req 6 done via `exportstep_fixes writes mfr_pn` — both undone in
  round 8. Rows 4 and 6 now read PARTIAL and DISABLED with the reason and the
  round that changed them. The table's heading now states explicitly that it is
  a living table, not a dated snapshot like the round entries — that ambiguity
  is what let it drift for two rounds. Row 1 also gained the `SOLDERMASK*`
  naming limitation.
- The "Delivered files" list under it still named `exportstep_fixes.il`;
  annotated in place with the round-4 fate of the overlay.

**Still outstanding:**
- Line ~411 puts the README at `stepbuilder-py/README.md` (422 lines); it is at
  the repo root and roughly 700 lines. Inside a dated round entry, so left as
  written — but it is a live pointer, and it is wrong.
- The "Open issue: No module named stepbuilder" section (line ~80) was settled by
  `S3D_ScriptDir` + `cd /d` in the generated bat. Reads as open; is not.
- "Verification done here" (line ~295) records the tree as `board -> PCB /
  symbols_top / symbols_bot`; the board part became `PCB_<json_stem>` in round 8.
  Genuine historical record of what was checked that day, so left alone.

## Update 2026-07-22 (round 10) — silkscreen export

Branch `feature/silkscreen-export`. User requirements for this round, verbatim
in intent: variant A of the options memo; silkscreen of components absent from a
variant must **not** be removed (the bare board is manufactured once for every
assembly variant, so its legend is physically there regardless); ink 25 µm as a
config parameter; GUI checkbox plus a two-item White/Black color dropdown; silk
outside the board must be clipped; a settings file for which layers are
silkscreen, as exportJson has.

### The design, and why

**Stroke-to-region is Allegro's job, not ours.** A silkscreen line is a
centreline plus a width; a filled outline is what 3D needs. `axlPolyFromDB`
does that conversion natively (`?endCapType 'ROUND`, and `?line2poly t` for an
`r_path`), including glyphs and curves, so nothing is offset or stroked by hand
and the result matches what goes to the Gerber. Text goes through
`axlText2Lines` first — that is verbatim the idiom in the axlText2Lines docs
("You can convert a r_path to an o_polygon by using axlPolyFromDB using its
?line2poly t option"). True-type text has no `textBlock` and converts directly,
which is also how exportJson tells the two apart.

**Same primitive vocabulary as the outline.** Each polygon is emitted as
`segment` / `arc` / `circle` objects — exactly what `build_contour()` already
parses — so the Python side needed no new geometry reader, only face+prism
assembly. Preferred source is `poly->segments` (line/arc segment dbids carrying
an explicit centre, radius and direction: no guesswork); `poly->vertices` is the
documented fallback for polys a boolean synthesised.

**One sweep, not per-symbol.** With only the silk layers visible,
`axlAddSelectAll` returns symbol-owned figures as well as loose ones — which is
exactly why exportJson has to filter on `elem->parent->refdes`. Here both are
wanted, so one pass per side covers component legends and free board geometry.
Visibility and find filter are snapshotted and restored per the programming
model in the `axlVisibleDesign` docs.

**Clipping in SKILL, not Python.** `axlPolyOperation(silk, outline−cutouts,
'AND)`. Batched at 400 polys: the API's own docs warn about time and memory past
~10000 polys, and a batch also contains a failure. That API is documented
"provided as-is ... may fail", so a failed batch keeps its geometry **unclipped**
with a warning rather than dropping legend that is almost certainly on the
board. Rectangular boards with no cutouts get a bbox fast path.

**Silk solids are deliberately NOT fused.** Thousands of overlapping thin prisms
would cost minutes of OCCT time with a real chance of failing, and buy nothing
visible. Each side is one compound, one label, one color. Documented as a
limitation in the README.

### Files touched
- `makeVariant3dIntermediates.il` — new SILKSCREEN section (~700 lines):
  a small purely-functional JSON reader (`s3dJson*`), config loading
  (`s3dSilkConfig`), polygon→primitive emission (`s3dPolyElements`,
  `s3dArcElement`, `s3dVerticesToElements`), collection (`s3dCollectSilkPolys`,
  `s3dPolysFromDbid`), clipping (`s3dBoardPoly`, `s3dClipPolys`), streaming
  writer (`s3dWriteSilkscreen`). `format_version` 1 → 2.
  `makeVariant3dIntermediates( dir [pcbColor] [configFile] )`.
- `simple3d.il` — `S3D_ConfigFile`, `S3D_DefaultSilkColor`, both passed on.
- `simple3d_config.json` — new.
- `core.py` — `build_silkscreen`, `_silk_face`, `silkscreen`/`silk_color`
  parameters, two new `BuildResult` counters.
- `colors.py` — `SILK_COLORS` (White 242, Black 26 — printed ink is never a pure
  255/0, and pure white next to a white mask disappears), `resolve_silk_color`.
- `gui.py`, `__main__.py` — checkbox, dropdown + swatch, `--no-silkscreen`,
  `--silk-color`, config persistence, log line.

### Bug fixed in passing
`create3dIntermediateFormat` did `car( stepModelPlacements )` on the still-
unbound marker when no component had a STEP mapping. Latent before; with
silkscreen a bare board is a legitimate export, so it is now guarded.

### Verified here (Python + transliteration, no Allegro)
- End-to-end on the demo board: 5 silk solids built, the deliberately-open
  contour skipped with a warning instead of killing the build, `silkscreen_top`
  and `silkscreen_bot` present in the STEP, `--no-silkscreen` → 0 solids.
- Geometry exact, not approximately: ring polygon (10×10 outer, 6×6 hole)
  volume 1.6 mm³ = 64 mm² × 0.025 to 6 dp; round-capped stroke 0.100785 mm³
  against the analytic `(20×0.2 + π×0.01) × 0.025`. Holes really are voids.
- Z placement: top ink 0.0000 … 0.0250, bottom −1.1210 … −1.0960 — on the outer
  faces, growing away from the board.
- The SKILL JSON reader transliterated to Python and run against the real
  `simple3d_config.json`: every field matches the `json` module. Eight valid
  shapes (compact, pretty, escapes, exponents, nested arrays, empty containers,
  true/false/null) all match; eight malformed inputs all terminate — none hangs.
- The vertices-fallback arc math run through OCCT: CCW circle, CW circle and a
  quadrant-split round-capped stroke all reproduce their analytic areas exactly
  (12.566370614, 12.566370614, 10.785398163). This pins the sign convention and
  the alpha/beta/ccw emission, which mirrors `makeArc`.
- Paren balance 0 on both `.il` files; all four `.py` files compile.

### NOT verified here (user must confirm in Allegro)
- That `axlAddSelectAll` over silk layers really returns symbol-owned figures on
  a live board (inferred from exportJson's `elem->parent->refdes` filter).
- `poly->segments` being populated on polys from `axlPolyFromDB` — the docs list
  it as a polygon attribute; if it comes back nil the vertices fallback runs,
  which is the tested path anyway.
- The **sign convention of the vertex radius**. The doc's wording ("positive the
  arc is to the left") is read as centre-on-the-left ⇒ CCW. Verified
  self-consistent and exact through OCCT, but only Allegro can confirm the sign
  itself means that. If arcs come out bulging the wrong way, flip the `f_r > 0.0`
  test in `s3dArcElement` — that one line is the whole convention. This only
  matters if `poly->segments` is unavailable.
- Runtime on a dense board (collection + clipping), and whether the 400-poly
  batch size needs tuning.
- Whether `axlPolyOperation` copes with the design's actual polygon count.

## Update 2026-07-22 (round 10a) — every silk contour arrived open

First run on a real board (`my_test_board-a0`): **13 of 13 polygons skipped**,
`Contour is open (start and end do not meet within 1e-05)`, top and bottom
alike. The board itself built fine, so the failure was specific to the
silkscreen path.

### Cause: the vertex list has no closing edge

`axlPolyFromDB`'s documentation says the vertex list "always describes a closed
shape". Read as "the first point is repeated at the end" — it is not. Every
polygon therefore lost its last edge and reached the STEP builder open.

The evidence was in exportJson all along and I read past it: both routines that
build geometry out of `poly->vertices` — `ttfVerticesToSvgPath` and the TTF
branch of `textToSvgPath` — append an explicit `"Z"` after the vertex loop.
They have to, for exactly this reason. **When two readings of a doc sentence are
possible, working code that already uses the same attribute settles it.**

Fix: `s3dVerticesToElements` emits a closing segment from the last vertex back
to the first, guarded on the two ends actually being apart (> 1e-6), so a list
that *does* repeat its first point cannot gain a degenerate edge.

### Also removed: the poly->segments path

`s3dPolyElements` used to prefer `poly->segments` and fall back to vertices.
That preference is wrong here. For a polygon built from a line, or from an
`r_path` with `?line2poly`, "Path describing boundary of shape" hands back the
**source centreline** — an open path — not the widened outline. So on a board
whose legend is mostly lines and text, that path produced open contours too.
`s3dPolyElements` is now vertices-only, which is the representation
`axlPolyFromDB` actually documents for a polygon and the one exportJson reads.

This retires the round-10 open question about whether `poly->segments` is
populated: it is not the right source either way.

### New: the area cross-check settles the arc-sign question by itself

An arc rebuilt on the **wrong side of its chord still closes**, so the contour
check cannot see it — which is why the round-10 note listed the vertex-radius
sign convention as unverifiable here. It is verifiable, cheaply: every polygon
now carries Allegro's own `poly->area` (documented, net of holes) into the JSON,
and `build_silkscreen` compares the built face against it, warning once per side
with the worst offender and naming `s3dArcElement`.

Measured on a round-capped stroke: correct arcs match the declared area exactly;
flipping the sign convention still builds a closed face but comes out 4.6% off
and trips the warning. So if the sign is wrong on real geometry, the log says so
in plain words instead of the user noticing bulges by eye.

### Diagnostics
`build_contour`'s open-contour error now reports the gap and both endpoints
(`Gap 0.707107 between (0.0000, 0.5000) and (-0.5000, -0.0000)`). A gap that
size is obviously a missing edge; a gap near 1e-5 would have meant tolerance.
The original message could not tell the two apart — which is why this round
started with a guess instead of a reading.

### Verified here
- The un-closed element list reproduces the user's error verbatim, and the new
  message names a 0.707 mm gap.
- With the closing edge: builds, and the area check stays quiet.
- Sign convention deliberately inverted: still builds, area check fires at 4.6%.
- Glyph with a counter (outer ring + hole): builds.
- Earlier checks all still pass (circle/capsule areas exact, demo board 5 solids,
  z placement, paren balance, py_compile).

### Still open
- Only 10 top / 3 bottom polygons came out of a real board, which is few for a
  legend with reference designators. Could be genuine (axlPolyOperation merging
  overlapping strokes into few connected regions) or could mean the layer list
  did not match. The Allegro console prints the counts before and after
  clipping — that pair distinguishes the two, and has not been seen yet.

## Update 2026-07-22 (round 10b) — the arc reading moved to Python, decided by area

Second live run: contours now close (13 solids built), but the area check I had
added in 10a fired on almost everything, with two distinct signatures:

- top: 8 of 10, built **smaller** than declared by up to 6.5%;
- bottom: 3 of 3, built 11.3024 mm2 against 1.45453 declared — 677% **larger**.

Small-and-smaller is the exact signature the controlled flip test produced
(-4.6%). Large-and-larger is what happens when a polygon with big arcs is
rebuilt on the wrong side and turns into a petal shape instead of a disc. Both
point the same way: the vertex-radius sign is being read backwards.

### Why guessing again was the wrong move

Two readings of the doc sentence are defensible ("positive: the arc is to the
left" — the arc bulges left of travel, centre on the RIGHT? or the centre is on
the left?), and there is a *second*, independent ambiguity next to it: each
vertex carries the radius of the edge reaching it, and the list does not repeat
its first point, so the first vertex's radius either describes the closing edge
or nothing at all. Four combinations, one guess per round trip.

### What was done instead

The vertex list now goes into the JSON raw — `[x, y, signed_radius]` per point —
and Python resolves the reading itself, scoring all four combinations against
the areas Allegro reported and keeping the one that reproduces them. The winner
is logged in words; every polygon is then verified individually under it.

This is the right split of responsibility, and it should have been the design in
round 10: **the side that can measure the answer is the side that should decide.**
SKILL has the database but no way to check a reconstruction; Python has an
area oracle for every polygon and was throwing it away.

Two side benefits: the JSON is much smaller (one line per vertex instead of a
five-line primitive object), and the SKILL side lost `s3dArcElement`,
`s3dSegmentElement`, `s3dVerticesToElements`, `s3dPolyElements` and
`s3dDistance` — about 120 lines of geometry that no longer exists to be wrong.

Arcs are now built through three points (start, arc midpoint, end) with
`GC_MakeArcOfCircle`, so there is no alpha/beta/sense bookkeeping left either.
Polygon arcs never cross a quadrant, so every one is a minor arc and its
midpoint is unambiguous.

### The counts were fine after all

Round 10a flagged "10 top / 3 bottom is few". Console shows 12 and 12 before
clipping, 10 and 3 after. `axlPolyOperation` takes *sets* of polygons, so
overlapping members of the input come back merged — a cluster of touching
strokes becomes one region. The reduction is a union, not a loss. Nothing to fix.

### Also fixed
`*WARNING* (axlSetFindFilter): Options are ignored for onButtons -
"DYNTHEMALS"` on every export was ours: `axlGetFindFilter` reports DYNTHEMALS
among the on-buttons and `axlSetFindFilter` refuses to take it back. It is now
dropped from the list before restoring.

### Verified here
- Convention recovery: a shape described once geometrically, emitted as if
  Allegro used each of the four conventions in turn; the reader picks each one
  back out, builds all polygons, and issues no warning. Capsule and circle areas
  come back at 3.6e-15 and 5.3e-15 from truth.
- The streaming writer transliterated and its output parsed as JSON across six
  shapes: both sides populated, empty top, empty bottom, both empty, two holes
  on one polygon, and a polygon with no area key. All parse, all counts right,
  and the assembled file builds end to end.
- The area check demonstrably fires when it should: a polygon given a wrong
  declared area is reported at 142.9%.
- Old-format JSON (baked `outline` primitives) still builds — back-compat kept.
- Paren balance 0, py_compile clean, demo board unchanged at 5 solids.

### Still user-verified only
- Which of the four readings the real board actually uses. The log now states
  it; worth recording here once seen, because it settles the doc question for
  good.

## Update 2026-07-22 (round 10c) — the sign is measured against the centre, not travel

Third live run: silkscreen is in the model, but line ends are drawn as "two
half-circles toward the centre of the line" instead of one semicircle, and some
90-degree corners come out as external corners where a fillet belongs.

That symptom is specific. A round cap is split at its quadrant into two quarter
arcs; both bulging inward is what "two half-circles toward the centre" is. And
it was not uniform — some geometry looked right. **A uniformly wrong sign cannot
produce a partly-correct result**, so the model of the sign was incomplete, not
merely inverted.

### The reading that fits

Taking the doc sentence literally: "positive - the arc is to the left of **the
y-axis**". Not the direction of travel — the vertical through the arc's **own
centre**. The sentence next to it is what makes this coherent: arcs never cross
a quadrant, and quadrants are measured from the centre, so every arc lies wholly
on one side of its centre's vertical, and the sign names that side.

The two rules differ exactly where a shape doubles back. For one stroke with a
round cap at each end, walked clockwise:

```
travel  -> [+0.5, 0, +0.5, +0.5, 0, +0.5]     both caps the same sign
axis    -> [+0.5, 0, -0.5, -0.5, 0, +0.5]     the caps split
```

So reading AXIS data with the TRAVEL rule leaves one cap correct and inverts the
other — the reported symptom, exactly.

### Why the area check did not catch it

Measured: AXIS data read as TRAVEL gives 10.500000 against a true 10.785398 —
off 2.65%, which does exceed the 0.5% tolerance and would have warned. But note
**both TRAVEL polarities give the same 10.500000**: flipping polarity swaps
which cap is inverted and the total is unchanged. Area is blind to that swap.
It can separate TRAVEL from AXIS, but never the two polarities of a doubling-back
shape from each other. Worth remembering before trusting area as an oracle for
anything else.

(The GUI log for this run was not captured — the Allegro console was pasted
twice — so whether the warning fired is unknown. The numbers say it should have.)

### What was done

AXIS is now a third dimension of the convention search: 8 candidates instead of
4, all scored, no early exit (two readings can both land inside tolerance on a
gently curved sample, and taking the first to pass would pick by list order).
The sample now prefers small arc-bearing polygons — only arcs discriminate, and
the cheap ones say it as clearly as the expensive ones.

The AXIS side test reduces to one term. For the candidate that bulges left, the
arc midpoint is one radius from the centre along the left normal, so its x
offset from the centre is exactly `rad * nx`: the arc sits left of its own centre
iff `nx < 0`.

The log now spells the winning reading out in words, e.g. "positive radius means
the arc sits left of its centre, first radius closes".

### Verified here
- Signs each rule writes for the same physical stroke differ as shown above.
- All 8 combinations round-trip: data emitted as each is recovered and rebuilt
  to 3.6e-15 of the true area.
- Cross-check: AXIS data read as TRAVEL is 2.65% off under either polarity;
  read as AXIS it is exact.
- Writer output still parses across six shapes; old-format JSON still builds;
  demo board unchanged.

### Open
Which rule the real board uses is still unconfirmed — AXIS is a hypothesis that
fits the symptom, not a measurement. Asked the user for the JSON so the eight
candidates can be scored against real vertex data and real areas offline,
instead of one candidate per round trip.

## Update 2026-07-22 (round 10d) — SETTLED: the sign rule, measured

The user supplied `my_test_board-a0.json`. That closed the question by
measurement instead of by another round trip.

### The answer

**AXIS / positive-sits-left / first-radius-closes.** A positive radius means the
arc lies to the LEFT of the vertical through its own centre; the first vertex's
radius describes the closing edge back to it. The doc sentence "the arc is to
the left of the y-axis" meant exactly what it said, and "y-axis" is the one
through the arc's centre — not the direction of travel.

Scored over the board's own polygon areas, every candidate at once:

```
                              top        bottom
('axis',   True,  True )    0.0004%     0.0000%   <-- correct
('axis',   True,  False)    1.3083%    25.9491%
('travel', True,  False)    3.9257%   625.1500%
('travel', False, True )    5.2343%   651.0991%
('travel', True,  True )    5.2343%   651.0991%
('travel', False, False)    6.5430%   677.0483%
('axis',   False, False)    9.1604%    83.6356%
('axis',   False, True )   10.4690%    57.6865%
```

The residual 0.0004% is the JSON's `%f` rounding of the area to six decimals,
not geometry: per-polygon absolute differences are 3e-7 to 4.6e-7 mm2 on all 13.

Note the last line of the table: 677.0483% is verbatim the number in the round
10b failure report. The whole diagnosis chain reconciles.

### Confirmed by hand, on the raw data, before running anything

Top polygon #0 is a plain stroke, width 0.15, round caps:

```
[3.910, 2.850, +0.075]   left cap, centre (3.985, 2.850) -> arc lies LEFT
[3.985, 2.775, +0.075]   left cap                        -> arc lies LEFT
[6.515, 2.775,  0.000]
[6.590, 2.850, -0.075]   right cap, centre (6.515, 2.850) -> arc lies RIGHT
[6.515, 2.925, -0.075]   right cap                        -> arc lies RIGHT
[3.985, 2.925,  0.000]
```

The two caps of one stroke carry OPPOSITE signs. Under TRAVEL they would be
identical. That single observation decides between the rules, and it is visible
in six lines of the file — which is why asking for the file was worth more than
any further reasoning from the documentation.

Its area: `2.53 x 0.15 + pi x 0.075^2 = 0.397171`, against `"area": 0.397171`.

### And confirmed by looking at it

Rasterising the faces under both readings (BRepClass_FaceClassifier over a
grid) reproduces all three of the user's complaints under TRAVEL and none under
AXIS:

- the round cap comes out cut back on one side instead of a clean semicircle;
- the L-shaped stroke loses the fillet at its right-angle turn;
- the bottom stadium ring loses its hole entirely and becomes a blob — which is
  what a 677% area error looks like.

Worth keeping as a habit: area agreement is necessary, not sufficient. Two
inverted caps can cancel. Rasterising a face to text is cheap and catches what
a scalar cannot.

### Change

`('axis', True, True)` is now first in `_CONVENTIONS`, so a legend of nothing but
straight lines — where all readings tie — resolves to the reading known to be
correct. The search is kept: it costs one pass over a handful of small polygons,
it is what established this, and it will report in the log if another Allegro
version ever disagrees.

### Requirement 7 status
Silkscreen is geometrically correct on a real board: 13 of 13 polygons match
Allegro's own areas, no polygons skipped. Remaining unknowns are operational
(runtime on a dense board, clip batch size), not correctness.

## Update 2026-07-22 (round 10e) — the mitre was Allegro's, not ours

With the sign rule settled, the model still showed square outer corners on some
turns and round ones on others. Two screenshots of different places on the same
board, one of each.

### It is in the source polygon, and it is measurable

The reconstruction is faithful — all 13 polygons match Allegro's own areas to
3e-7..4.6e-7 mm2 — so the corner is square in what `axlPolyFromDB` returned.
Scanning the user's JSON for right-angle corners between two straight edges:

```
10 CONVEX 90-degree corners with no arc at all
top #9, corner (19.975, 8.225):
    centreline corner (19.900, 8.150), half width 0.075
    diagonal offset = 0.106066 = 0.075 * sqrt(2)   <- a textbook mitre
```

`axlPolyFromDB` called on a whole line/cline MITRES the joins between its
segments. A plot sweeps a round aperture along the path, so the artwork - and
Allegro's own 3D - has a round join of radius w/2 there.

The corners that DID come out round are junctions of two separate lines, where
the round END caps overlap. That is the whole inconsistency: not two kinds of
error, but one kind of geometry (a mitred path join) sitting next to correct
geometry (overlapping caps).

### Fix: convert a path one segment at a time

Each segment then gets its own round caps, and the union of overlapping stadiums
IS a round join. The documentation says the same from the other side: of
`?line2poly` it notes "typically one poly is returned for each segment in the
r_path" - which is exactly why text, which goes through that path, never showed
the problem. Shapes and rects are still converted whole; they are boundaries
already, with nothing to sweep.

Nothing is merged in SKILL: the Python side draws a compound of overlapping
solids anyway, and with clipping on `axlPolyOperation` unions them as a side
effect of the AND.

### Verified here
Rendering the corner both ways (BRepClass_FaceClassifier over a grid), from the
real polygon versus the same two centrelines converted per segment: the mitre
is square, the per-segment union is round. Regression suite unchanged.

### Note for next time
The area oracle cannot see this class of defect at all - a mitred polygon is
perfectly consistent with its own reported area. Two things it is blind to are
now known: compensating errors (two caps inverted the opposite way, round 10c)
and faithful reproduction of geometry that is itself not what we want (this
round). Both were caught by looking at a picture. Rasterising a face to text
costs nothing and should be the first move whenever a shape "looks wrong" but
the numbers agree.

### NOT verified here
That per-segment conversion actually works on a live board: whether
`axlPolyFromDB` accepts a segment dbid and picks up the width from its parent
path. If a segment fails to convert, its piece of the line disappears and no
area check can notice, so the SKILL side now warns when a path yields fewer
polygons than it has segments. Needs a re-export to confirm.

## Update 2026-07-22 (round 10f) — "unbound variable - cuts" on an all-SMD board

A second board failed before writing anything:

```
Simple 3D: silkscreen polygons - top 143, bottom 0
Simple 3D: after clipping - top 35, bottom 0
*Error* eval: unbound variable - cuts
```

Silkscreen was fine. This is the upstream `cuts` defect the memo has carried
since round 1 as "needs checking on a real cutout-less board" — now checked, by
a board that has one.

### The fault

`create3dIntermediateFormat` declares `( cuts 'unbound )`, which in SKILL really
does leave the variable unbound. It gets a value from only two places: the
cutouts from `makePcbContour`, and the through-hole pins from
`symbolReturnPinHoles`. A board with **no CUTOUT shape and no through-hole pins**
— an ordinary all-SMD board — satisfies neither, so `cuts` is still unbound at

```skill
pcb = makePcb( thicknesses edges cuts pcbColor )
```

and passing it evaluates it. Nothing is written; the export dies before
`outfile`.

### The second half of the same bug

`makePcb` then chooses its branch with `if( boundp( 'cuts ) ...)` — but `cuts` is
its own **formal parameter**, so boundp is t whenever the call succeeds at all.
The no-cuts branch was dead code, and had the caller merely passed nil the
with-cuts branch would have run on nil and emitted

```
"edges": [ [ ...outline... ],
	 ]
```

a trailing comma, i.e. not JSON. Verified by transliterating both branches:
old behaviour → `Expecting value: line 22 column 2`; fixed → parses, one edges
array. So the crash was hiding a second defect that would have produced a
corrupt file instead of an error.

Both fixed: the call site passes nil when unbound, and `makePcb` tests the
value. `makePcbContour` had the same asymmetry (it guarded `cuts` but not
`edges`) and now guards both, with a message rather than a fault.

### Note
This is the third time in this feature that a defect was reachable only through
a data shape nobody had exported yet (no closing edge, mitred joins, now no
cuts). The pattern: the code was written against one board. Worth trying
deliberately degenerate inputs — no cutouts, no holes, no bottom silkscreen, no
components — rather than waiting for a board to supply them.

### Verified here
- Both branches transliterated and parsed: with cuts → 2 edges arrays, without →
  1; the old boundp path → invalid JSON, as predicted.
- A cutout-free, hole-free board with silkscreen built end to end through the
  real reader: 1 silk solid, areas matched, STEP written.
- Balance 0, full Python suite clean.

## Update 2026-07-22 (round 10g) — silkscreen file size, measured

User: 1619918 bytes without silkscreen, 4115593 with. Asked what can be done
and at what cost. Measured rather than guessed — four representations of the
same 150-polygon legend, "Minimise file size" on unless noted:

| representation | bytes | vs default | seconds |
|---|---|---|---|
| solids (current) | 2191456 | 100% | 0.5 |
| solids, minimise OFF | 5768921 | 263% | 0.8 |
| flat faces | 566370 | **26%** | 0.1 |
| boolean-fused per side | 3377048 | **154%** | 1.4 |

Through the real `generate()` on the same data: silkscreen adds 2261572 bytes as
solids and 651082 flat — 28.8%.

### Fusing is counterproductive, and now we know

Round 10 called fusing "minutes of solver time for nothing visible" and skipped
it on those grounds. The measurement is worse than that guess: it makes the file
**larger** (154%). A boolean union replaces analytic planes and cylinders with
general surfaces, and after clipping the strokes barely overlap, so there is
little interior geometry to remove. The reasoning in round 10 was right for the
wrong reason — it is not merely not worth it, it is actively harmful. Recorded
so nobody proposes it again as an optimisation.

### Why flat is such a large win

A V-vertex polygon as a prism costs V+2 faces (top, bottom, one wall per edge);
as a surface it costs one. Everything under a face — surfaces, edge loops,
oriented edges, curves, points — scales with it.

Placed at the ink's OUTER surface (`z + thickness`), not on the board face, so
it cannot z-fight with the board in a viewer. That is the only subtlety; the
rest is a straight trade of solidity for size.

### Delivered
`silk_flat` through core / GUI checkbox ("Flat (about 1/4 the size)") / CLI
`--flat-silkscreen`, persisted in the GUI config, disabled together with the
silkscreen checkbox. Default OFF: solids are the honest representation, and the
size is the user's call to make.

README gained a "Silkscreen file size" section in both languages with the table
above and three levers in order of effect: Flat; dropping `REF DES/SILKSCREEN_*`
from the config layer list (reference designators are usually most of a legend,
and this also shrinks the JSON); and turning silkscreen off for working exports.

### Verified here
Both paths built end to end through `generate()`; GUI smoke test confirms the
default, the snapshot value, and that the checkbox greys out with the feature.
Full suite clean.

## Update 2026-07-22 (round 10h) — four requests: flat on the surface, per-side, one config, log wrap

### 1. Flat legend sits ON the board face
Was `z + thickness` (standing off it, inherited from the solid path). Now `z`.
A zero-thickness legend that floats 25 um above the board was incoherent; the
user was right. Measured: flat z-range now 0.0 .. 0.0, solid still 0.0 .. 0.025.

The reason it was offset in the first place was z-fighting, and that risk is now
real: two coplanar faces can flicker in a viewer that resolves depth per pixel.
Documented in both README languages and in the docstring, with solid mode as the
answer if it shows up. Not worth pre-empting with an epsilon nobody asked for.

### 2. Two side checkboxes
`generate()` lost `silkscreen: bool` and gained `silk_top` / `silk_bottom`. The
GUI has "Silkscreen  [x] Top  [x] Bottom"; both off is the old "off". CLI keeps
`--no-silkscreen` (both) and adds `--no-silk-top` / `--no-silk-bottom`.
Verified: both=14 solids, top only=10, bottom only=4, none=0.

### 3. ONE settings file
Settings used to live in three places: `simple3d.il` source, the GUI's own
`~/.stepbuilder.json`, and `simple3d_config.json`. Now one file with four
sections - `allegro` (SKILL side), `gui` (Python side), `silkscreen` and
`settings` (the exporter).

What made this work cleanly: **the launcher stopped forwarding settings**. It
used to pass `--step-dir`, `--color`, `--silk-color`; now it passes only
`--config` and what is derived from the design (json dir, output dir, board
name). The GUI reads its own section from the same file, so there is no second
copy to drift. `S3D_ModelLibDir`, `S3D_DefaultColor` and `S3D_DefaultSilkColor`
are gone from the SKILL source entirely.

`S3D_ScriptDir` stays in source, and has to: the config is found relative to the
project folder, so the folder must be known before the config can be read. That
is the whole bootstrap, and it is now stated as such at the top of simple3d.il.

The GUI's save is read-modify-write on the whole document, not a fresh one -
losing the silkscreen layer lists on window close would be far worse than
forgetting a path. Verified by round trip: GUI writes `gui`, the `allegro`,
`silkscreen` and `settings` sections survive byte-identical, the SKILL JSON
reader still parses the result, and reopening the GUI restores what was saved.

`s3dLoadSettings()` re-reads on every export as well as at load, so config edits
apply without reloading the SKILL files. The menu label is the exception and
says so - the menu is built at load time.

### 4. Log wrapping
`wrap="none"` -> `wrap="word"`. Build messages carry full paths and OCCT errors
and ran off the right edge with no horizontal scrollbar to reach them.

### Verified here
Per-side counts; flat and solid z-ranges; config round trip in both directions;
GUI smoke test (config path, wrap mode, both checkboxes, color box greying out
when both sides are off); full suite clean. One scratch test still called
`generate(silkscreen=...)` and was updated to the new API - worth remembering
that renaming a keyword silently breaks callers that pass it by name.

## Update 2026-07-22 (round 10i) — UnboundLocalError in the GUI launcher

The GUI would not start:

```
File "...\stepbuilder\__main__.py", line 46, in _gui_prefill
    app = StepBuilderApp(Path(args.config) if args.config else None)
UnboundLocalError: cannot access local variable 'Path' where it is not
associated with a value
```

### Cause

`_gui_prefill`'s `except` handler contained `from pathlib import Path` — a
leftover, since `Path` is imported at module level. **Binding a name anywhere
inside a function makes it local for the entire function**, so that one line in
a branch that normally never runs turned every earlier use of `Path` into an
UnboundLocalError. It was harmless for as long as nothing in the `try` block
used `Path`; round 10h added exactly that use, and the function stopped working
at its first line.

Fix: delete the redundant import. The module-level one was always there.

### The same trap, one more place

An AST scan of the package for function-local imports of names that are already
module-level found `_rim_faces()` re-importing `TopoDS`. Currently harmless —
the import sits at the top of the function, before any use — but it becomes the
identical failure the moment a line is added above it. Removed, with the reason
written next to the remaining local imports (which are genuinely lazy: those
names are NOT module-level).

The scan is a five-line AST walk and worth keeping in mind as a check whenever
this file grows: a local import is safe only when the module level does not
already provide the name.

### The test gap that let it through

Every existing test either drives `core` or constructs `StepBuilderApp`
directly. `_gui_prefill` — the entry point the Allegro launcher actually calls,
and the only code path with the crash-handler wrapper around it — was never
executed by anything. Its own `except` block then swallowed the error into a
dialog, so it could only ever be found by a user.

Added `test_launcher.py`: stubs `StepBuilderApp` so no window opens, then runs
the full launcher command line, the standalone form without `--config`, the
silkscreen flags, the legacy flags, and an unknown flag; plus five assertions on
what actually reached the app. It fails loudly on this bug.

### Verified here
Launcher suite 10/10, shadow scan clean, the real GUI constructs and reports its
config path and wrap mode, full suite unchanged.

## Update 2026-07-22 (round 10j) — silkscreenFlatHeight

Round 10h moved the flat legend onto the board face and flagged coplanar
z-fighting as a documented risk rather than pre-empting it. It happened: the
user reports flicker where a flat legend meets the board. Their call: a
`silkscreenFlatHeight` parameter, 1 um default.

Added as `gui.silkscreenFlatHeight`, plumbed through `build_silkscreen`
(`flat_offset`, signed per side like `thickness`), `generate()`
(`silk_flat_height`), the GUI and `--silk-flat-height`.

### Why `gui` and not `settings`

`settings.silkscreenThickness` is read by SKILL and travels into the JSON, so
changing it needs a re-export from Allegro. This one is a viewing correction -
you reach for it precisely when a viewer flickers - and forcing a full re-export
for a micron would be poor. In `gui` it is read by the Python side directly:
edit the file, press Generate. Documented next to `silkscreenThickness` in the
README so the pair is findable together.

### The bug this nearly walked into

`_save_config` replaced `data["gui"]` wholesale, so ANY key the running build
did not know about was deleted when the window closed - including a
hand-added `silkscreenFlatHeight`, and including the requested comment. The
file is meant to be hand-edited; that is a real defect, not a hypothetical.
Now merged into the existing section instead. Verified: a `_comment_*` key
written by hand survives a GUI save.

That is the same reasoning already applied one level up (preserving `allegro`,
`silkscreen`, `settings`) - it simply had not been applied *within* `gui`.

### The comment
JSON has no comments, so the request is honoured with a sibling key,
`_comment_silkscreenFlatHeight`, which both readers ignore and the merge now
preserves. It states what the distance is, that it is NOT the ink thickness,
and that 0.005-0.01 is the thing to try if a micron does not clear the viewer's
depth buffer.

### Verified here
Flat top +0.001, flat bottom -0.001 (sign follows the side), 0.01 honoured,
solid unchanged at 0.0 .. 0.025; GUI loads the value, snapshots it, and
preserves the comment across a save; full suite and shadow scan clean.

## Update 2026-07-22 (round 11) — mechanical symbols in, NO_STEP_EXPORT out

Branch `mech-export`. Two requirements from the user's F4 dumps:

1. Mechanical components (`Component Class: MECHANICAL`, e.g. a MOLEX connector
   with a real `PKGDEF_STEP_FILE` but no electrical connections) are in the
   schematic and in Variants.lst, yet never reach the export.
2. A symbol carrying `NO_STEP_EXPORT` must be excluded even when Variants.lst
   lists it, and the log must name the symbol AND the reason.

### The reversal that fixes (1)

The export list WAS the parsed variant list:

```skill
symbols = variantSymbolList[variant]
```

so a symbol `gdsysGetVariantInfo` did not hand back could not be exported at
all - there was no other path into the loop. Whether the parser drops
mechanical entries, or Allegro writes them somewhere the state machine does not
reach, could not be determined from here and **does not need to be**: the list
now comes from `axlDBGetDesign()->symbols` and the variant table only ever
subtracts.

The rule that falls out of that is the useful one:

- refdes mentioned by the variant table, but not in THIS variant -> not
  installed, skip;
- refdes the table never mentions -> not variant-controlled, export it in every
  variant.

Mechanical parts are the second case whether or not they appear in the file, so
the fix holds under either explanation. Deliberately keyed on "the variant
table has never heard of it" rather than on `Component Class == MECHANICAL`:
the general rule covers mechanical parts and anything else the variant
machinery does not track, and needs no list of blessed classes.

### (2) NO_STEP_EXPORT

Read with `axlDBGetProperties`, testing for the NAME's presence - it is a flag
with no value, so anything value-based would miss it. Property names come back
as symbols, hence the `%L` coercion (the idiom the disabled MFRPN helper
already used). Checked on the symbol instance, where the F4 dump shows it, and
also on the component and its definition, so it can be attached once to drop
every fiducial.

The earlier MFRPN trouble is not evidence against this: that was about which
object carries the property, which is exactly why three levels are checked.

Excluded symbols are also filtered out of the `s3dCheckMfrPn` "no 3D model"
pre-flight list, which otherwise reported deliberate exclusions as missing
models - the user's FID1/FID2/FID3 were in that list for precisely that reason.

### Also removed: a lookup that could not succeed

`symbolReturn3DElements` took a refdes STRING and resolved it with
`axlDBFindByName( 'refdes ... )` -> component instance -> `->symbol`. Two
lookups, each able to return nil, for a symbol the caller already had in hand.
It now takes the dbid (a string is still accepted, three lines, keeps the old
call shape). One fewer way for a part to vanish between the design and the JSON.

### Verified here
The selection logic transliterated and run over a decision table: mechanical
part exported in every variant both when Variants.lst lists it and when it does
not; an uninstalled part stays out of its variant and appears in the other; a
NO_STEP_EXPORT symbol is excluded in all five configurations INCLUDING when the
variant lists it, and the log names it every time; refdes matching is
case-insensitive in both directions; a symbol with no refdes is skipped. Paren
balance and the rest of the suite unchanged.

### NOT verified here
That `axlDBGetProperties` reports NO_STEP_EXPORT on a live symbol - the whole
point of the three-level check is that the level it lives on is the uncertain
part. If a marked symbol still comes through, the per-symbol log line will be
absent, which says immediately that the property was not seen rather than that
the filter misfired.

## Update 2026-07-23 (round 12) — config destroyed on close; flat faces flicker

Three reports against the merged build. The first two are one defect.

### The settings file came back holding only "gui"

`_read_config_file` returned `{}` for a file it could not read, and
`_save_config` then merged the gui section into that empty document and wrote
it. So any failure to READ the config turned into silent destruction of it -
`allegro`, `silkscreen` and `settings` gone - and the empty path fields
(report 1) are the same failure seen from the other side.

The comment above `_save_config` described preserving the other sections, and
the code defeated it two lines later. Guarding the merge inside `gui` last
round was the same mistake one level down, and this one was already latent
then: fixing a symptom at one level does not make the level above it right.

Now `_read_config_file` returns `(document, problem)` and **nothing is written
unless the file was understood**: missing, unparsable, not an object - each
refuses the save and leaves the file alone. Read as `utf-8-sig`, because a BOM
from an editor is enough on its own to make `json.loads` fail on otherwise
valid JSON. Written through a temp file plus `os.replace`, so a crash cannot
truncate a file that now carries the SKILL side's settings too.

The GUI also states, on every start, which settings file it used:
`Settings loaded from <path>`, or a warning naming the problem and saying the
file will not be saved. That line is what was missing - "why is this field
empty" had no answer anywhere on screen.

### Flat silkscreen blended where solid did not

Measured on the user's board: of 8 polygon pairs with overlapping bounding
boxes, 5 overlap by real area - 0.16 mm2 double-counted across the top side.
Silkscreen strokes genuinely overlap. As solids that is harmless
interpenetration; as flat faces it is two coincident coplanar faces at one z,
which no depth buffer can order.

Flat faces are now boolean-unioned per side (general fuse +
`ShapeUpgrade_UnifySameDomain`). Measured on that board's 117 top faces: 0.08 s,
117 faces -> 112, area 209.4717 -> 209.3116 (exactly the double count), STEP
599 kB -> 548 kB.

**This contradicts round 10g without contradicting its measurement.** Fusing the
SOLID legend cost 154% of the file size, because a solid union builds side walls
and swaps analytic surfaces for general ones. A coplanar union of faces only
removes geometry. Same word, opposite result - which is why it was worth
measuring again instead of citing the old number as settled.

Whole-board sizes now: no silkscreen 98,731; solid 2,661,832; flat 754,698.

### A test bug worth recording
The first flat-vs-solid comparison reported sizes six bytes apart. The loop
built a kwargs dict and never passed `**kw`, so both runs were solid. Two runs
that agree that closely are not a result, they are a symptom - check the
harness before the code.

### Verified here
Config: a valid file keeps all four sections and the hand-written comment; a BOM
parses; broken JSON, a truncated file, a JSON array and a missing file each
leave the file untouched and report a problem. Both modes build the user's
board. Full suite and shadow scan clean.

## Update 2026-07-23 (round 13) — stepDir wiped after a config warning; path churn

### 1. The save guard was on the wrong moment

Round 12 refused to write a config the GUI could not read. It re-read the file
at save time and refused if THAT failed. But what gets written comes from the
WIDGETS, and the widgets are populated at LOAD time - so:

- open: config unreadable -> warning, widgets hold defaults;
- the user repairs the file while the window is open (exactly what was asked of
  them last round);
- close: the save-time re-read succeeds, the guard passes, and the defaults are
  written over the repaired file. `stepDir` comes out `""`.

Which is what happened: their file had `allegro`, `silkscreen` and `settings`
intact - proof the save read it successfully - and an empty `stepDir`.

The fix is one condition, but the lesson is the shape of it: **a guard has to
be on the same moment as the data it is guarding.** The data was loaded at
startup; the guard was checking the file at shutdown. Now the save requires the
file to have been understood BOTH at load and at save.

### 2. jsonFile / outputDir were being recorded as settings

They are not settings. They come from Allegro for one board, they are
overwritten by the next export of a different board, and they made a settings
file churn on every run. `prefill_jobs` now marks that the paths came from the
launcher, and the save leaves those two keys alone in that case. A standalone
run - where the user actually picked them in the window - still records them.

`stepDir` is the opposite case and stays: a model library is stable across
boards, which is exactly what a setting is.

### Verified here
The wipe sequence reproduced end to end (unreadable at open, repaired mid-
session, closed) - stepDir survives and all four sections survive. An Allegro
export leaves jsonFile and outputDir untouched while still saving a real
preference changed in the same session. A standalone run still remembers both.
Full suite clean.

## Update 2026-07-23 (round 14) — silkscreen layers chosen in the GUI

Branch `silk_multiple_choice`. The user was tired of rewriting the config to
change which layers the legend uses.

### The constraint that shaped it

The GUI runs AFTER the export. By the time the window is up, the JSON exists and
the polygons are collected, so "tick layers in the GUI" cannot drive collection.
Only two designs are possible: collect everything and filter at build time, or
ask before collecting (a SKILL form in Allegro).

Chose the first. The second puts a modal dialog in front of every export and
still cannot change the choice without re-exporting, which is the actual
complaint.

### Division of labour, now explicit

- `simple3d_config.json` says which layers are **collected** — that still costs
  Allegro time, so an expensive layer left out of the lists is still the way to
  avoid paying for it.
- The GUI says which of the collected layers are **built** — free, per press of
  Generate.

`format_version` 3: every silkscreen polygon carries `"layer"`. The array stays
flat, so a reader that ignores the key builds the whole legend, and a
version-2 file is never filtered (there is nothing to match on).

### Two things that needed care

**Grouping had to happen at collection, not after.** A polygon has no layer of
its own and text loses even its dbid once `axlText2Lines` has vectorised it, so
elements are bucketed by `elem->layer` inside the existing sweep. Still one
sweep per side - sweeping once per layer would multiply the visibility churn for
nothing.

**Clipping had to move per layer.** `axlPolyOperation` unions overlapping
polygons, so clipping a whole side at once returned regions merged across layers
with no layer left to speak of. `s3dClipGroups` clips each group separately;
groups that clip to nothing are dropped, so a layer entirely off the board does
not appear in the GUI as an empty choice.

### The GUI

Checkbuttons in a scrolled canvas, grouped Top/Bottom, each row showing the
polygon count - that number is what explains a large file, and it is the thing
you want before deciding. Not a multi-select Listbox: a highlighted row reads as
"current item", a tick reads as "included", and included is the question.

The list is built from the JSON that will be built, not from the config, so it
cannot offer a layer that would do nothing; with several variants queued it is
their union. A `trace_add` on the JSON field with a 400 ms debounce covers
typing, pasting, Browse and the Allegro prefill in one place.

**Exclusions are persisted, not inclusions** (`gui.silkscreenLayersOff`). A
layer appearing on a board for the first time then defaults to ON. Storing
inclusions would make a new layer silently missing - data present, geometry
absent, nothing on screen to say why.

The save only overwrites the remembered exclusions when a list has actually been
shown, so opening an old layerless JSON does not wipe them.

### Verified here
Layer listing and counts; filtering drops exactly the right polygons; an unknown
layer name changes nothing; version-2 polygons are never filtered; the GUI lists
every layer, honours the remembered exclusions, defaults an unseen layer to on,
All/None work, the new exclusion is saved and the other config sections survive;
a layerless JSON leaves the exclusions alone. Writer transliteration extended
with the layer key and an empty group - all seven shapes still parse. Full suite
and shadow scan clean.

## Update 2026-07-23 (round 14a) — a silent silkscreen failure, made loud

Board `my_test_board2`: the JSON came out with no `"silkscreen"` key at all, and
the user reasonably read that as "silkscreen not found".

### Reading the console

```
Simple 3D: collecting silkscreen...
Simple 3D: 22 symbol(s) are not listed in any variant ...
```

The line that should sit between those two — `silkscreen polygons - top N,
bottom N` — is missing, and so is the new per-layer breakdown. Both print
unconditionally right after collection. So execution left `s3dMakeSilkscreen`
between the two `s3dCollectSilkByLayer` calls and the count: it raised, and

```skill
errset( silk = s3dMakeSilkscreen( s3dSilkConfig( configFile ) ) )
```

swallowed it whole. `format_version: 3` in the file proves the new code was
loaded, so this is not a stale install.

### The defect is the errset, not whatever raised

That bare `errset` was added in round 10 so a silkscreen fault could not cost
the user the board export. The intent was right and the execution was not: it
turned every possible silkscreen error into an empty legend with **nothing on
the console at all**. There is no way to tell that from "this board has no
silkscreen", which is exactly the confusion it produced.

Two changes, both about making a failure survivable AND visible:

- The call site now uses `errset( expr t )`, whose second argument prints the
  SKILL error, and reports in its own words that the legend is missing while
  the board is fine. A swallowed error is worse than a loud one.
- `s3dCollectSilkByLayer` wraps the conversion of EACH element, so one object
  the converter cannot handle costs that object rather than the whole side. The
  first failure names the object type and its layer; the rest are counted.

I could not determine the root cause from here - it needs the message that was
being swallowed. The per-element guard covers the likely case (a single object
on `MANUFACTURING/AUTOSILK_TOP`, a layer new to this config, that
`s3dPolysFromDbid` cannot convert); if something bigger is wrong, the next run
prints it.

### Also found: string literals broken by a real newline

`s3dWriteVertexList` had `fprintf( p_port "," <newline> " )` — a printf format
split across two source lines by heredoc escaping in an earlier round. Harmless
(a literal newline inside the string emits the same bytes as `\n`) but invisible
in review and one careless edit away from mattering. Added `check_strings.py`
to the scratch suite: it walks the source and flags any string literal that runs
across a line break. Two found, both from the same cause, both fixed.

**Lesson worth keeping:** heredocs through the Bash tool mangle backslash
escapes often enough that generated SKILL needs a mechanical check afterwards.
Paren balance was already checked; string literals now are too.

## Update 2026-07-23 (round 14b) — the swallowed error, named

The reporting added in 14a paid for itself on the first run:

```
*Error* eval: undefined function - s3dCollectSilkPolys
Simple 3D: ERROR - silkscreen collection failed (message above).
```

`s3dCollectSilkPolys` was renamed to `s3dCollectSilkByLayer` in round 14. The
DEFINITION was renamed; the two call sites in `s3dMakeSilkscreen` were not,
because the scripted patch that was supposed to update them did not match and
said nothing. `s3dClipPolys` -> `s3dClipGroups` and the two `length()` ->
`s3dGroupCount()` in the same block were missed the same way. Fixed with the
editor rather than a script, and verified by reading the block back.

### Why nothing caught it

SKILL resolves function names at CALL time, so a file with a stale call loads
without complaint. Paren balance was clean, the string check was clean, and
every Python test passed - none of them execute SKILL. The only thing that
could have caught it is a check on the SKILL sources themselves.

`check_calls.py` now does that: it collects every `procedure( name(` definition
across both .il files and flags any call to a project-shaped name (`s3d*`,
`make*`, `add*`, `symbolReturn*`, ...) that is defined nowhere, ignoring
Allegro's `axl*` and the SKILL builtins that match those shapes. Verified by
reintroducing the exact bug: it reports the line and exits 1.

**Three mechanical checks on the SKILL sources now, and each exists because
something got past the previous two:** paren balance, string literals broken by
a real newline, and calls to undefined procedures. Run all three after any
scripted edit.

### The wider lesson, worth stating plainly
Scripted find-and-replace over source that fails to match is silent by default.
Every one of these three rounds traces back to a patch that did not apply and
did not say so. When a replacement must apply, either use the editor, or make
the script fail loudly on a miss - and then verify by reading the result, not
by trusting the exit code.

## Update 2026-07-23 (round 15) — layer panel: wheel scrolling, two columns

Two refinements to the panel from round 14, both reported after live use.

### The wheel only worked on the scrollbar

Binding `<MouseWheel>` to the canvas is not enough: the pointer is almost always
over a Checkbutton or the inner frame, and those consume the event before the
canvas sees it. Binding every child would work but the list is rebuilt on every
JSON change, so the bindings would have to be re-applied each time.

Instead the panel grabs the wheel with `bind_all` on `<Enter>` and releases it
on `<Leave>`, so the wheel scrolls the layer list while the pointer is inside it
and behaves normally everywhere else in the window. `<Button-4>`/`<Button-5>`
are bound too - X11's wheel encoding, harmless on Windows.

Guarded against scrolling a list that already fits: without the check the canvas
rubber-bands a short list out of view, which looks broken.

### Bottom beside Top, not under it

Each side now gets its own column in the inner frame. Two short columns fit
where one long list scrolled, and the two sides stay comparable at a glance.
Columns are allocated only to sides that actually have layers, so a top-only
board leaves no gap.

One hazard this introduced and closed immediately: `_layers_inner` now manages
its children with `grid`, and the "no layer information" label in the same
container was still using `pack`. Tkinter refuses both managers in one
container. They never coexist (the label path returns early, and every refresh
destroys the children first), but that is an accident of control flow rather
than a guarantee, so the label moved to `grid` as well.

### Verified here
Two columns on the same grid row with the right layers in each; 24 layers
overflow the 96 px panel and the wheel moves the view down and back exactly;
a short list does not move; grab/release leaves no stray bindings; the
empty-state label renders without a geometry-manager clash. Full suite and all
three SKILL checks clean.

## Update 2026-07-23 (round 16) — side switches grey their layers; zero-width objects reported

### Switching a side off now greys its layers

They stayed live and clickable, so you could edit a selection that had no
effect. The layer rows are now kept per side as `(layer, var, widget)` triples,
and `_update_silk_row` sets widget STATE only - the variables are never touched,
so the ticks are exactly as they were when the side comes back, and they are
what gets saved either way.

All / None follows the same rule and skips a greyed side. Changing ticks the
user cannot see the effect of, and then persisting them, is the same defect from
the other direction.

### Zero-width lines and text

A line with no width, or text whose text block has zero pen width, has nothing
to plot with - Allegro's own artwork cannot draw it either. `axlPolyFromDB` does
not object: it returns nil, or a degenerate polygon that fails much later with a
message about geometry rather than about width. So it was being dropped
silently, or blamed on the wrong thing.

`s3dZeroWidth` checks before conversion: for text, the text block's
`photoWidth`; otherwise the figure's `width`, falling back to the per-segment
widths of a path. Deliberately conservative - a shape is a filled area and
true-type text is a filled outline, so neither can be zero-width, and a path
with no segments to inspect is not accused of anything.

Reported by layer AND position, which is what makes it actionable:

```
Simple 3D: WARNING - zero width: text on REF DES/SILKSCREEN_TOP at (12.500, 4.000) - skipped, it cannot be plotted.
```

The messages also travel into the JSON under `silkscreen.warnings` and are
re-logged by the Python side with a `warning:` prefix, which the GUI colors
orange. Two reasons: the Allegro console has usually scrolled past by the time
anyone looks at the model, and the GUI is where the result is judged. They are
logged even when silkscreen is switched off - the object is wrong in the board
regardless of what this build draws.

A module-level accumulator (`S3D_SilkWarnings`) rather than a return value:
the collector already returns layer groups, and threading a second channel
through it and through the clipper would obscure both for the sake of a message.
Cleared per export, not per side, so both sides report together.

### Verified here
Greying: both sides on leaves everything enabled; switching bottom off disables
only its boxes; tick states are byte-identical before and after; None skips the
disabled side; switching back on re-enables. Warnings: carried through the JSON,
logged with the prefix that colors them, and still logged with silkscreen off.
Writer transliteration extended to emit the warnings array - all seven JSON
shapes still parse. Full suite and all three SKILL checks clean.

## Update 2026-07-23 (round 17) — severity coloring in the Allegro console

The user pointed at a Cadence forum thread on coloring SKILL output. The link
returns 403 to a fetch, but the answer is in the local reference:
`axlUIWPrint( r_window [s_msg_level] t_format [args] )`.

### What the API actually offers

Five levels, and that is the whole set:

| level | effect |
|---|---|
| `'info0` | informational, not journalled |
| `'info1` | informational (the default) |
| `'warn` | warning color, `*WARNING*` prefix |
| `'error` | red, `*Error*` prefix, beeps |
| `'fatal` | beeps; behaviour beyond that not documented here |

So orange warnings and red errors are available and now used. **Green is not.**
There is no "success" severity, so a completed export prints in the ordinary
color; the GUI log already shows its own completion line in green, and that is
where the result is judged. Said plainly in the README rather than approximated
with something that is not green.

### How it is wired

One wrapper, `s3dSay( s_level t_message )`, with `s3dWarn` and `s3dErr` over
it - so the decision about HOW to print lives in exactly one place, and adding
a green route later (if the forum has one) is a one-line change.

Two details in it that matter:

- The message is passed as a `%s` ARGUMENT, never as the format string. A layer
  name or path containing a per-cent sign would otherwise be read as a
  conversion.
- It falls back to `printf` when `axlUIWPrint` is unavailable or refuses. A
  message must not be lost to the attempt at coloring it.

Messages no longer spell their own severity: Allegro adds `*WARNING*` /
`*Error*`, and saying it twice reads as a mistake. `Simple 3D: warning - no such
layer` became `Simple 3D: no such layer`.

17 messages converted: 14 in makeVariant3dIntermediates.il, 3 in simple3d.il.
`print( "Export complete!" )` also became a proper printf - `print` quotes its
argument and adds no newline, which is for dumping values, not for talking to a
person.

### The patch script asserted every replacement

After three rounds lost to scripted find-and-replace that missed silently, this
one counts each anchor, asserts exactly one match, and writes nothing unless
every replacement applied. That is the shape these scripts should have had all
along, and it is cheaper than the editor for seventeen sites.

### Verified here
All three SKILL checks clean on both files; no warning or error printf remains;
the full Python suite unchanged.

### NOT verified here
That `axlUIWPrint(nil ...)` lands in the scrolling command window rather than a
one-line status area - the reference says a nil window "dumps output to main
window", which is where the existing `*WARNING*` lines appear, so it should. If
the messages turn up somewhere less useful, the wrapper is the single place to
change back.

## Update 2026-07-23 (round 18) — README audit against the code

Asked to check the README against reality. Mechanical claims were compared
programmatically (`audit_readme.py` in the scratch dir); prose was read.

### What the audit checks

CLI flags in `__main__.py` vs flags named in the README, both directions; every
key of the shipped `simple3d_config.json` mentioned somewhere; every key the
README names actually existing; shipped files present in the layout listing;
`format_version` as written by the exporter; the four assembly labels produced
by `core` vs documented; and the two defaults (ink thickness, flat height).

It found four things, two of them its own fault. Worth recording both kinds:

- **False positive**: `--mfr-pn-in-name`, which is commented out. The scanner
  was reading disabled lines. Fixed to strip comments - a disabled flag is not
  a flag.
- **False positive**: `silkscreen` reported as an unknown config key; it is a
  top-level SECTION. Fixed by naming the four sections.

### Four real defects, fixed

1. **The silkscreen intro described solid mode as if it were the only mode.**
   Written before Flat existed and never revisited: "extruded into thin solids
   that sit on the outer face". Now says filled regions are built either as
   solids or as flat surfaces, and points at the checkbox.
2. **The config snippet looked like the whole file.** It shows `silkscreen` and
   `settings`; the file has four sections. Now labelled as two of four, with a
   pointer to *Settings* for the others.
3. **"Silkscreen solids are not fused" no longer told the whole truth.** True
   of solid mode, and the opposite of what flat mode now does - flat faces ARE
   unioned, and must be, or coplanar overlaps flicker. The limitation now says
   which mode it is about and states the flat case beside it.
4. **`silkscreenLayersOff` was documented but absent from the shipped config.**
   It only appeared after the GUI first saved. A user reading the file to learn
   what it holds would not have seen it. Added as `[]` with a comment key
   explaining why exclusions are stored rather than inclusions.

Plus one omission that was not a wrong statement but a gap: **the changelog
stopped at 2026-07-22**. Everything from rounds 11-17 - mechanical symbols,
NO_STEP_EXPORT, per-side control, flat mode and its height, the settings
consolidation and the two data-loss fixes under it, the layer chooser,
zero-width reporting, console severity coloring - was undocumented for users.
One entry added covering all of it, in both languages.

The GUI table also listed its rows in an order the window does not use (layers
before Color/Flat, which share the Top/Bottom row). Reordered.

### The pattern in all four

Every one is a statement that was TRUE WHEN WRITTEN and was not revisited when
the behaviour around it changed. None of them is a typo or a misunderstanding.
That is the failure mode documentation actually has, and it is why the
mechanical audit is worth keeping: it cannot catch prose that went stale, but it
pins down every claim that can be enumerated, which leaves less prose to read.

**Whenever a behaviour changes, grep the README for the old behaviour, not just
for the feature name.**

### Verified here
Audit clean in both directions; the config parses in both readers and still has
four sections; the GUI loads the new key; layer, config-save and config-safety
suites unchanged.

## Update 2026-07-23 (round 18a) — install advice from before the repository

The user asked what the "most common install mistake is nesting `stepbuilder\`
one level too deep" warning is still for, now that the whole tool is one repo.
Nothing: it described handing the Python package over as a separate archive,
where unpacking could produce `stepbuilder\stepbuilder\`. Clone or unpack the
repository and its root already IS the install layout - there is nothing to
assemble and nothing to double-nest.

Same era, same paragraph: the tree annotated `stepbuilder\` as "the FOLDER, not
its contents", which was advice about what to copy.

Replaced with what can actually go wrong now:

- the folder may be named anything and live anywhere, so long as
  `S3D_ScriptDir` and both `load()` lines name the folder holding the two `.il`
  files;
- downloading the repo as a ZIP from GitHub wraps everything in
  `Simple3D-main\`, so either unpack its contents or point `S3D_ScriptDir` at
  the wrapper - the failure is the two disagreeing.

The verification step gained a second half worth having: the log line
`Settings loaded from …` proves the CONFIG was found too, not just the package,
and the config now carries every setting.

`PROJECT_NOTES_simple3d.md` added to the tree listing - it is in the repo, so a
listing claiming to be the repo root should show it, marked as not needed to
run.

### Note to self
This is the third documentation defect of exactly one kind: a statement that was
true when written, about an arrangement that has since been replaced. The
mechanical audit cannot see these - it checks that names exist, not that advice
still applies. The user found this one by reading. Worth re-reading the
Installation and Why-this-exists sections whenever the shape of the project
changes, since those describe context rather than API and nothing checks them.

## Update 2026-07-24 (round 19) — mechanical symbols with a STEP model but no refdes

User reported a symbol (a CR2032 holder) whose F4 shows only `Symbol name:
CR2032` and `PKGDEF_STEP_FILE = CR2032.step` on the **symbol definition**, with
**no reference designator**. Asked whether it exports. It did not, and it failed
silently.

### Root cause — two refdes gates

1. **Selection.** `s3dSymbolsToExport` iterated `axlDBGetDesign()->symbols` under
   `when( sym->refdes ...)`, so a symbol with `refdes == nil` (docs, confirmed:
   *"Reference designator nil if no associated component (for example,
   mechanical)"*, `skill_db_attributes.txt`) was skipped — not counted, not
   logged.
2. **Naming.** Even admitted, `symbolReturn3DElements` keyed the JSON by
   `sym->refdes`, coercing nil to the string `"nil"`. Several no-refdes symbols
   would collapse onto one duplicate JSON key; `json.load` keeps only the last,
   silently dropping the rest.

### The fix — SKILL only, Python untouched

- **New `s3dHasStepModel( sym )`** — `errset( axlStepGet( nil nil sym ) )` and
  test `->step_name`. This is self-selecting: FORMAT/DRAFTING/plain-graphic
  symbols have no STEP association and return nil, so no symbol-type filter is
  needed. `PKGDEF_STEP_FILE` on the symdef IS what `axlStepGet` reports (round 8
  fact, re-confirmed against the `axlStepGet` doc page).
- **Selection gate** widened to `when( refdes || s3dHasStepModel( sym ) )`. The
  short-circuit keeps the extra probe off refdes-bearing symbols, so their path
  and runtime are unchanged. Both `known[upperCase(refdes)]` lookups are now
  guarded with `refdes &&` (else `upperCase(nil)` throws), and the NO_STEP_EXPORT
  message falls back to `sym->name` when there is no refdes. A no-refdes
  mechanical is by definition "untracked" — the variant table keys on refdes —
  so it exports in every variant, exactly the round-11 principle.
- **Synthetic key** in `symbolReturn3DElements`: `sprintf(nil "%s_MECH%d"
  sym->name S3D_MechSeq)` → `CR2032_MECH1`, `CR2032_MECH2`, … `S3D_MechSeq` is a
  module var reset at the top of `create3dIntermediateFormat` (per variant),
  same pattern as `S3D_SilkWarnings`. Keys are unique, readable in logs, and
  cannot collide with a real refdes.

**Why Python needs no change:** the JSON key is only a dict key + a log label;
the instance in the tree is named after its STEP file, not the key (round 8
flattening, `core.py:1167-1236`). Verified: the synthetic keys do NOT appear in
the STEP; `cap_D8x10mm` (the model file) does.

### Verified here
- Three mechanical SKILL checks (paren balance, strings broken across a real
  newline, calls to undefined project procedures) clean on both `.il` files. The
  checker was self-tested against injected defects — it catches all three; it is
  in scratch as `skill_checks.py` (still not committed to the repo — the standing
  suggestion from round 14b to add it holds).
- `core.generate` on a synthetic board with two no-refdes mechanical entries
  (`CR2032_MECH1` top, `CR2032_MECH2` bottom, same model): both placed, one under
  `symbols_top` and one under `symbols_bot`, part shared, STEP written.

### Confirmed live by the user (Allegro, 2026-07-24)
- **The mechanical export works end to end.** The CR2032-style symbol with a
  `PKGDEF_STEP_FILE` and no refdes now exports. This settles the one uncertainty
  the change carried: `axlStepGet( nil nil <mechanical instance> )` *does* return
  the mapping, so the `sym->definition` fallback was not needed and is not in the
  code. The instance path (`axlStepGet` with an instance rather than a symdef)
  behaves the same for a mechanical symbol as for an ordinary component.

## Update 2026-07-24 (round 20) — GUI wording, HEX label, NO_STEP_EXPORT confirmed, quick-start

Small round on user feedback after the round-19 export landed.

- **`NO_STEP_EXPORT` confirmed live.** The user reports it "works perfectly", so
  the last standing live-verification item on it is closed: `axlDBGetProperties`
  does see the property and marked symbols are excluded. Removed from the
  "Not verified outside Allegro" list at the top and marked confirmed in the
  requirement-8 row. (Nothing else in that list changed.)
- **GUI: `Board edge` → `Board edge color`.** The dropdown sets a color, so the
  label now says so (`gui.py` `_build_ui`).
- **GUI: an explicit `HEX color` label** now sits directly left of the custom
  rim-color entry, and greys out in step with the field via
  `rim_hex_label.state(["disabled"])` in `_update_rim_entry` — same greying
  discipline as the silk layer rows in round 16, so a user cannot mistake the
  disabled `#RRGGBB` field for something to fill in. Verified: `py_compile`
  clean and the `ttk.Label.state()` toggle sets/clears the disabled flag. Full
  App not instantiated (no display here) — layout is code-review only, as in
  round 8.
- **New `QUICKSTART.md`** — a short, Russian, history-free how-to: menu path, the
  Input/Options fields, the output name, and the load-bearing rules (thickness,
  mechanical parts, `NO_STEP_EXPORT`, variants, silkscreen). The full bilingual
  README stays the reference; this is the one-screen version the user asked for.

## Update 2026-07-24 (round 21) — full project review

Whole-repo review: ~9000 lines (2 SKILL files, 4 Python, 3 docs, the config).

### The finding that changes the top of this memo: Tk RUNS HERE

Every GUI change since round 8 was recorded as "code review only, no display
available". That is **wrong on Windows** — `tkinter` needs no X server, and
`tk.Tk()` comes up (8.6.13) in this environment. Twenty-two GUI assertions now
run for real: the round-20 HEX label greys and ungreys on the actual widget,
`_rim_color` resolves all four cases, the **two config data-loss regressions
(rounds 12-13) are executable tests** rather than prose, and `_snapshot` is
confirmed frozen and complete.

**Stop writing "GUI not verifiable here."** It is. `test_gui.py` in scratch is
the harness; it copies the config first so the repo's file is never written.

### One real defect, in round 19's own code

`s3dSymbolsToExport` built the NO_STEP_EXPORT message with
`label = if( refdes then refdes else sym->name )` and passed it to `%s`. `%s` on
nil throws ("format spec. incompatible with data"), which would kill the whole
export from inside a log line. `symbolReturn3DElements` guards the identical
read three hundred lines away (`if( sym->name then sym->name else "MECH" )`) —
so the hazard was known and the guard simply was not carried across. Now
`"(unnamed symbol)"`. Low likelihood (`name` is documented `string`, not
`string/nil`), but the branch exists precisely for symbols in odd states.

### A fourth mechanical SKILL check: call arity

The class of defect it catches already happened here (`makeSlot` called
`makeCircle( x y d )`; `makeCircle` takes 2). Nothing looked for it. `check_arity.py`
reads every `procedure(` signature — honouring `@optional`/`@key`/`@rest` — and
compares each call's positional count. Clean on both files; re-injecting the
historical `makeCircle` bug reproduces the report.

**It found one thing first, and it was wrong:** `headList( parts n - 1 )` looked
like 4 arguments. SKILL uses infix arithmetic inside argument lists, so that is
two. The checker learned about infix; the code was right. Recorded because the
same shape (`nth( n - 1 parts )`) is used elsewhere and will trip the next
person reading it.

### What was verified, not just read

- **Core geometry still matches the C++ reference exactly**: 12073.309477 and
  5054 entities, with masks zeroed as that baseline was originally measured.
  (Run with masks live it is 12743.166893 — the whole difference is board area x
  0.06 mm of mask. A future run should zero them before comparing, or it will
  look like drift.)
- Silkscreen exercised **as a package import**, which the mechanical test did not
  do: `core` reaches `from .colors import SILK_COLORS` only on that path. 20
  assertions — areas reproduced, layer exclusion, flat mode smaller than solid
  and unioned without warning, JSON warnings re-logged with the coloring prefix
  even when the legend is switched off, one bad polygon skipped not fatal.
- **Config contract across the SKILL/Python boundary**: every key each side reads
  exists in the shipped file, all four sections and both `_comment_` keys survive
  a save. Every flag the launcher passes (`--config --json-dir --output-dir
  --brd-name --dated-name`) exists in the GUI parser — worth checking because
  `_gui_prefill` uses `parse_known_args`, which swallows an unknown flag in
  silence.
- Docs audited mechanically again; **no findings** after two scanner fixes of its
  own (the README writes flags as `` `--z-datum {top,bottom}` ``, argument inside
  the backticks, so anchoring on a closing backtick missed sixteen of them; and it
  was reading commented-out Python again — the exact round-18 false positive).

### Doc debt finally paid

Two live pointers the memo had been carrying for many rounds, both in the
orientation sections rather than a dated round, so both fair game:

- **"## Open issue: No module named stepbuilder"** — settled back in round 9 by
  `S3D_ScriptDir` + `cd /d`, still headed "Open issue" nine rounds later.
- **Environment said Allegro 17.4** — the user moved to 24.1 at round 4 and every
  live confirmation since has been on 24.1. Round 8 spotted it and left it
  "pending confirmation"; it sat for thirteen rounds.

Both are the failure mode round 18 named. The lesson there was about the README;
it applies to this memo just as much, and this memo is the thing a new session
reads first.

### `.gitignore` had no Allegro section

Stock Python template, so `allegro.jrl`, `dangling_lines.rpt` and `signoise.run/`
showed up as untracked noise in every session — and the tool's own scratch files
(`_simple3d_launch.bat`, `_simple3d_preflight.bat/.txt`, the config `.tmp`) were
not ignored either, in a folder the tool writes to. Added, and verified that no
tracked file became ignored.

### Deliberately not changed
- The `--gui` prefill flags (`--step-dir --json-dir --json-file --output-dir
  --config`) are undocumented in the README. They are launcher plumbing that a
  user never types. Noted, not "fixed" — adding five internal flags to a user
  manual is noise. Say so if you disagree.
- `.claude/` is still untracked. Harness settings, not project files; the user's
  call whether it belongs in the repo.
- The round-9 note that the README is "at `stepbuilder-py/README.md`, 422 lines"
  is still wrong (repo root, now 1100). It sits inside a dated round entry, and
  this memo's convention is that those are historical record.

## Update 2026-07-24 (round 22) — several model folders, as an ordered search path

User: models sometimes have to come from more than one folder. Asked how to do
it in the interface.

### The design question was precedence, not the widget

`rglob` was already recursive, so subfolders of one root worked. What was needed
was *disjoint* roots — a shared company library plus a project-local folder. And
the moment there are two, the real question is which one wins.

`StepFileIndex` already answered it accidentally: `dict.setdefault` over the
walk, so first-wins — but the order `rglob` walks in is arbitrary, so a
duplicate filename resolved **unpredictably and in silence**. The change makes
the roots an explicit ordered list, so precedence becomes *declared* rather than
accidental, and a name found in more than one root is now reported with the path
that won. A silently substituted model is otherwise something you discover in
the CAD viewer.

Chosen (user picked both recommendations): **ordered search path, first match
wins**, and **report the shadowed name**.

### Interface: one folder per line

The "STEP files" row became a 3-line `tk.Text` instead of an `Entry`. Reasons,
in the order they mattered: the order has to be *editable*, and editing text
beats any pair of ▲▼ buttons; pasting several paths at once works; it stays the
same idiom as the other two path rows (free text + a button); the window grows
by two lines instead of gaining four buttons. **Add...** appends rather than
replaces — replacing would make adding a second folder mean retyping the first.

A listbox with Add/Remove/▲▼ was the alternative, and is the better answer only
if hand-typed paths should be impossible. They already are possible in the JSON
and Output rows, so forbidding them here would be inconsistent.

### Two ordering traps hit while building it

1. **`_load_config()` runs BEFORE `_build_ui()`.** The old `step_dir` was a
   `StringVar` created in `__init__`, so loading it early was fine; a Text
   widget does not exist yet at that point. Fixed by making `step_dirs()` /
   `set_step_dirs()` buffer into `_pending_step_dirs` while `_step_text` is
   None, and flushing when the widget is built. Order-independent, rather than
   moving the two calls and hoping nothing else depended on the order.
2. **`argparse` maps `--step-dir` to the same dest as the positional
   `step_dir`.** One clobbers the other. The optional now carries an explicit
   `dest="extra_step_dirs"`.

### Shape of it
- `core.StepFileIndex(roots, log=...)` takes a str/Path or a sequence; missing
  roots are warned about and skipped, and only having none left is fatal. One
  mistyped entry out of four must not cost the build.
- `find()` now falls back to `Path(name).name`, so a mapping carrying a path
  component ("subdir/model.step") resolves instead of missing a file that is
  sitting right there. Latent before; more likely with several libraries.
- `gui.stepDirs` (list) is the config key; `gui.stepDir` is still read when
  `stepDirs` is absent and is kept equal to the first entry, so an older build
  of the tool still opens with a usable library rather than an empty field.
- CLI: the positional folder accepts a `;`-separated list, `--step-dir` adds
  more, both flattened in order with duplicates dropped.
- **SKILL is untouched.** It never passed the model folder — that has come from
  the config since round 10h.

### Verified here
- 17 index assertions: precedence follows list order and flips when the order
  does, union across roots, recursion within one, shadowed name reported once
  with the winner, missing root warns and continues, all-missing raises with the
  paths named, single str/Path still works, path-component lookup.
- GUI suite now 31 assertions: append, duplicate refused, blank lines and
  padding dropped, snapshot carries a tuple, `stepDirs` written with `stepDir`
  in step, a legacy `stepDir`-only config loads, an empty `gui` section does not
  crash.
- End-to-end through the real CLI with two folders holding the same filename:
  the log names the winner, and swapping the order swaps it. `;` form works.
  Missing folder warns and still writes the STEP; all-missing fails with both
  paths in the message.
- Core geometry regression still 12073.309477 / 5054 entities.
- Docs audit clean, after it caught one genuine drift of its own: the docs
  called the button "Add…" (U+2026) while the widget says "Add..." — the same
  three ASCII dots as the neighbouring "Browse...". Docs now match the widget.

## Update 2026-07-24 (round 23) — the window reopens where you left it

User asked where the window appears and whether the position could be
remembered, especially across monitors, centring on the main screen for a first
run.

### Measured first, rather than guessed

`geometry()` was never called, so Tk placed the window at its own default:
**+160+157** from the top-left of the primary display, identically every launch
— and on a multi-monitor desk always on the primary, wherever you had it last.
Natural size 1038x876. (Tk runs here, per round 21, so this was measured.)

### Multi-monitor is the whole difficulty

`winfo_screenwidth/height` describe the **primary display only**. A window
legitimately sitting on a second monitor is off-screen by those numbers — which
is precisely the case being supported, so validating against them would defeat
the feature. `_virtual_screen()` asks Windows for the whole virtual desktop via
`ctypes` + `GetSystemMetrics(76..79)` (`SM_[XY]VIRTUALSCREEN`,
`SM_C[XY]VIRTUALSCREEN`); a monitor left of the primary gives a **negative
origin**, which is why the saved X can be negative and must not be treated as
corrupt. Falls back to the Tk primary metrics if that call is unavailable, so
it degrades to single-monitor behaviour instead of failing.

The restore is *validated*, not trusted: `_geometry_is_reachable` requires the
title bar not to be above every screen and at least 120x40 of the window to
intersect the desktop. The case that matters is closing on a second monitor
that is then unplugged — restoring those coordinates puts the window somewhere
invisible with no way to drag it back, which reads as the program failing to
start. Refused positions centre on the primary and say so in the log.

### Two things that only showed up once it was tested

1. **Maximizing was recorded as a normal geometry.** `<Configure>` fires during
   the transition while `state()` can still report `"normal"`, so the maximized
   rect was stored as the restored one — reopening then un-maximizing would give
   a screen-sized window that is not maximized. `_remember_geometry` now also
   rejects a rect as large as the screen. Belt and braces, deliberately.
2. **Closing left a pending `after`.** `_drain_queue` reschedules itself every
   100 ms; on `destroy()` the last one fired against a dead widget and Tk
   printed `invalid command name "..._drain_queue"`. Invisible under `pythonw`,
   console noise under `python`. `_on_close` now cancels both it and the layer
   refresh. Found because the test harness closes windows in a loop — a real
   defect surfaced by a test artifact, which is worth the note.

### A testing trap worth remembering
The first version of these tests used `withdraw()`, as the earlier GUI tests do,
and **six assertions failed against correct code**: on an unmapped window
`winfo_x/width` report the requested size, not where the window is, and
`geometry()` returns the requested size with the set position. Placement can
only be asserted on a **mapped** window (`deiconify()`), so `test_geom.py` maps
them. The probe that settled it printed what `_center_on_primary` actually
computed — `1038x876+441+102`, exactly right — which is how the code was
cleared and the test blamed.

### Verified here
22 placement assertions: centred on a first run and not at Tk's default; a saved
reachable position restored exactly; a full close-and-reopen round trip; an
off-screen position refused and centred; a simulated dual-monitor layout (left
monitor, negative X) accepted, the same spot refused once that monitor is
"unplugged", a 120px sliver allowed and a 70px one not; maximized saving the
restored rect and reopening maximized; five malformed values falling back to
centring. Plus: closing three windows through the real `_on_close` path with no
Tk noise. All other suites and the geometry regression unchanged.

## Update 2026-07-25 (round 24) — `stepDir` removed, and what the question exposed

User asked why the config carried both `stepDirs` and `stepDir`, then pushed
harder: why keep it at all, given that pulling from origin overwrites the config
anyway?

### The compatibility key was not worth it

Round 22 wrote `stepDir` back on every save, kept equal to `stepDirs[0]`, so an
older build of the tool run against a new config would still find a library.
That bought a narrow scenario and cost a permanent duplicate: `stepDirs` always
wins, so hand-editing `stepDir` does nothing and is silently overwritten on the
next close. The user asking the question **is** the evidence that it misleads.

Now: `stepDir` is read once, to migrate a settings file written before
multi-folder support, and `_save_config` **removes** it. After one close the
file holds one key. Explicitly noted in the code that this is not a breach of
the "preserve keys we do not understand" rule from rounds 12-13 — that rule
protects keys belonging to someone else; this one is ours and superseded, and
dropping it *is* the migration.

### The premise was wrong, and the truth is worse — NOT ACTED ON

"Pulling from origin overwrites the config" — measured, it does not. Git aborts
the whole pull:

```
error: Your local changes to the following files would be overwritten by merge:
	simple3d_config.json
Aborting
```

Settings survive; **the update does not arrive at all**. And this is not an edge
case: the GUI rewrites the config on every window close, and since round 23
`windowGeometry` changes on literally every session, so the file is always dirty.
For anyone who follows the README ("clone the repository, its root already is
the layout"), `git pull` will fail on this file every single time.

**The real fix, offered and deferred by the user (only `stepDir` was wanted):**
ship `simple3d_config.default.json` as a template, gitignore the live
`simple3d_config.json`, create it from the template when missing. Migration
hazard to state in the changelog when it is done: untracking a file means the
commit deletes it, so an existing clone either loses the file on pull (the app
recreates it) or refuses to merge if it is modified. Rough once, clean after.

This is now the largest known defect in the project. It is not in the code —
it is in how the tool is shipped.

### Verified here
GUI suite extended: `stepDir` gone from the file after a save; an old
`stepDir`-only config migrates into `stepDirs`, drops the key, leaves other
sections untouched, and the setting survives a reopen. All other suites and the
geometry regression unchanged. The docs audit needed a `MIGRATION_ONLY` set —
a key read only to migrate is deliberately absent from the shipped config, and
flagging that as an error would push it back in.

## Update 2026-07-25 (round 25) — models stored inside the .brd

Started from a user observation: "at some point the STEP files seem to end up
inside the board itself". True, and it has consequences.

### What the reference says

`axlPurge3DModelMapDataInDesign` states it outright: once 3D models are mapped,
"a data attachment is created in the design for each unique 3D model", and that
function removes "all 3D model attachments from the design database". Confirmed
live on Allegro **24.1** (`ALLEGRO_DESIGN_WAS_LAST_SAVED` → `allegro 24.1 S009`),
so this is not a 25.1-only behaviour.

Attachments are reachable through the generic API — `axlGetAllAttachmentNames`,
`axlGetAttachment`, `axlIsAttachment`, `axlCreateAttachment`, `axlSetAttachment`,
`axlDeleteAttachment`. The whole 3DX SKILL API is three functions and none of
them touches models: `axl3DXGet/SetDesignOption` are about via plating only.

### Naming, and the investigation that is now closed

Ids are `3D:<original file name>/ACIS`, e.g. `3D:SWITRONIC_IT-1187.step/ACIS`.
**The original filename is recoverable from the id** — which is what the shipped
feature uses.

The rest was an attempt, at the user's suggestion, to extract those copies and
hand them over for self-conversion. It got all the way and was then dropped on
the evidence. Recorded so nobody spends the afternoon again:

- **Container**: 31-byte ASCII header `1;<uncompressed size>;A;0;0;<64-bit hash>;`,
  NUL padding to offset 256, then a **zlib** stream (`78 9c`) that inflates to
  exactly the declared size. Payload is **`ACIS BinaryFile`** — `.sab`, binary
  ACIS. Verified on both models (40024 and 126569 bytes, both exact).
- **`axlGetAttachment( id 'string )` truncates** at the first NUL, which is the
  byte right after the header — hence 31/32 characters against sizes of 6904 and
  20934. That truncation is a property of the SKILL string, not of the export.
- **`axlGetAttachment( id 'file )` returns a stub record** — `(objType
  "attachment" dataFormat file)`, no id, no size, no data — but **writes the
  complete file anyway**. Twenty copies of each model were sitting in `%TEMP%`
  as `#T*.tmp` (plus one `.sat`), one per call across the probe runs. The side
  effect works; only the return value is broken. Allegro's 31-character id limit
  is NOT the cause: a 36-character id returned full metadata under `'string`.
- **Dropped because the output is not usable**: the user tried the extracted
  `.sab` files — Inventor will not open them, SolidWorks reports the file as
  faulty. And OCP has no ACIS reader at all (checked: STEP, IGES, STL, glTF,
  VRML and nothing else; ACIS import in OCCT is a commercial component).

**Two premature conclusions along the way, both mine.** First: "impossible,
ACIS is unreadable" — wrong framing, the user's proposal only needed the bytes
handed over, not read. Second: "impossible, the data is truncated" — wrong
reading, the temp files showed the payload comes out in full. The lesson is the
one this memo keeps relearning: check the artefact on disk before concluding
from a return value.

### What shipped instead

The useful half, and it is small. The export now writes the embedded model list
into the intermediate (`embedded_models`, `format_version` 3 → 4), and the
reader cross-references it against the models it could not find on disk. A
component missing for that reason is now named, with the fix spelled out:
export from the 3DX canvas, take the missing files out of that export, drop them
in a folder listed under STEP files, run again.

Before this the log said only `could not find X.step`, which does not
distinguish "this model exists nowhere" from "it is in the board, just not on
your disk" — and only the second has a remedy.

`embedded_models` is a new TOP-LEVEL key, so it had to go into `core._reserved`
as well, or the reader walks it as a component. The comment above `_reserved`
already warned about exactly this; a test now covers it.

README documents the mechanism in both languages — deliberately without the
container format, which is internal detail a user cannot act on. It lives here
instead.

### Verified here
16 assertions on the cross-check: named with guidance when missing AND embedded;
silent when missing but not embedded (the plain warning still fires); silent
when embedded but present; silent and crash-free on a format_version 3 file with
no such key; empty list handled; matching done on the bare filename so a mapping
carrying a path still resolves; and `embedded_models` not walked as a component.
The two new SKILL procedures were transliterated to Python and run against the
REAL attachment ids from the user's board — correct filenames, valid JSON — plus
six edge cases (no models, no attachments, a different suffix, no suffix, bare
prefix, a name containing a quote → skipped rather than emitting broken JSON).
All four SKILL checks, every other suite, the geometry regression and the docs
audit are clean.

## Update 2026-07-26 (round 36) — bends, folded

Requirement 11's other half, deferred since round 26. `format_version` 7, a new
`stepbuilder/bend.py`, a GUI checkbox and `--flat`. **Not yet run on a real
board** — see "What is still owed" at the end.

### The model: rigid panels and a faceted strip

OCC can transform a solid and it can cut one; it has nothing that deforms a
solid along a curve. So a bend is:

- the panel before it — untouched;
- the strip the board curls in — cut into rigid slices, each hinged at its own
  leading edge and rotated by the angle the arc has reached there, so every
  slice's leading edge sits exactly on the true arc and the error is one-sided
  (7.5°/slice, chords 0.2% of the radius inside the true surface);
- the panel after it — one exact rigid transform, no approximation at all.

The transform for a piece hinged at flat position `v`, in the plane across the
bend, is **slide then turn**: translate back along the bend direction by
`v - arc_start`, then rotate about the cylinder axis. Sliding first is what
makes the flat material the bend eats *disappear into the arc* instead of
stretching the board. The same formula covers the slices and the far panel
(`v = arc_end`, full angle), which is why they cannot drift apart.

**Slices are cut with a deliberate overlap.** Rotating a straight slice about
its leading edge opens a wedge on the outside of the bend and an overlap on the
inside; without the extra `max(0.02, t·Δφ)` mm the pieces would touch along a
line and the fuse would not make a solid. Cost measured: **+0.07%** of volume on
a 40×10 strip, +0.035% on the rigid-flex test board.

### Everything is cut in the FLAT frame

Every region is a set of half-plane constraints in flat XY, applied before any
transform. That is what makes a chain composable: bend *k*'s transform is
`M(k-1) · F(k)` with `F(k)` written in flat coordinates, so a second bend is
simply carried by the first. Cutting in the folded frame would need the
constraints re-derived per bend and would not survive a third.

### What the fold is applied to, and where

- **solid** — the fused board, once.
- **layers** — each layer part, **before** `fuse_keeping_faces`. The colors are
  keyed on the face objects the fuse hands back and folding replaces every face
  in a shape; fold first and the two steps do not fight. Verified: the volume is
  identical to `solid` to the last decimal.
- **inspect** — each layer part. Measured **0.25% heavier** than the other two,
  because the layers are never fused and the slice overlaps fan into each other
  at a bend. Flat, all three agree exactly. Documented rather than fixed.
- **silkscreen** — same cut, `fuse=False` (round 10g's 154% still holds).
- **components** — `fold.transform_at(x, y) * component_transform(...)`. The
  part is placed flat and then carried, exactly like the board, so it cannot
  drift off the surface it was placed on. A component inside a bend area is
  placed on the curve and reported.

### The rim color would have painted most of the board

`_rim_faces` calls a face rim when its normal is horizontal. After a 90° fold
the tail's top and bottom faces ARE vertical, so the naive test grabs them:
measured **five times the rim area** on the test strip. Fixed by asking the
question in the panel's own frame — `FoldPlan.flat_frame(point)` finds the
region by trying each inverse and keeping the one whose flat bounds the result
lands in, then the normal is judged there. The folded rim then has the same area
as the flat one to within the faceting (an annular sector about a mid-thickness
neutral axis has exactly the area of the flat strip it came from — worth knowing
as a check).

### Decisions that are conventions, not data

- **The largest piece is held.** Every combination of sides is tried (2^n, n is
  one or two on a real board), the outline is clipped to each, biggest survivor
  wins. "The first bend's larger side" would pick differently the moment a
  second bend crossed it.
- **The developed width is measured from the bend area**, not derived from
  radius × angle. The bend area is trimmed to the design outline and is what
  Allegro itself thinks bends. When the two disagree by more than a quarter the
  log says so and the drawn area wins. The slice angles are interpolated across
  the strip rather than derived from the neutral radius, so the last slice meets
  the finished angle exactly either way.
- **The radius is measured from the LOCAL stack** — the zone the bend line is
  in, found by point-in-polygon. Taking the board's own top face would put the
  cylinder axis 2.05 mm out on the test board. Tested: the same bend in the flex
  zone lands 2.05 mm below where the board-wide fallback puts it.

### IDX_BEND_TYPE_INFO is emitted RAW and parsed in Python

The property carries the angle, the inner side and the order, and it is in
neither the API index nor the DB attribute reference. So SKILL emits the string
verbatim (plus name, line endpoints, radius from `axlGetBendInnerRadius`, and
the measured width) and Python parses it. A field spelled differently by another
Allegro version can then be fixed **without a re-export**, and the string is in
the intermediate where it can be read. The parser keeps unknown keys, handles
units (`2.5000 MILLIMETERS`, and 100 MILS is not 100 mm), and an explicit JSON
field always wins over the raw string.

### Verified here, and how

60+ assertions in `tests/test_bend.py`. The numbers are worked out from the bend
by hand first — for a 90° top-side fold, a flat point `(v, z)` past the strip
lands at `x = arc_start + (z_axis - z)`, `z = z_axis + (v - arc_end)` — and the
geometry is required to match: the far panel's height, the outside of the bend,
the held end not moving, volume preserved to within the overlap, both fold
directions, the chain of two, a component's exact landing point, all three
stitchings, and an end-to-end build where a capacitor 20 mm out on the tail is
found at the position the fold predicts. Full suite 18/18.

`s3dBendsJson` cannot run here, so it is **transliterated line for line** and
its output required to be JSON this module reads back — including a bend name
containing a quote, a missing radius, a missing property, a bend with no line,
and no bends at all. Same method as the round-34 filter and the round-28
escaper. `s3dSpanAcross` is transliterated too and checked on a diagonal bend,
where measuring in x or y would give 4/sqrt(2) times the wrong answer.

**Three of my own expectations were wrong and the code was right** every time —
each was the same class of slip (forgetting that the arc lifts the panel by the
axis height, or that the flex surface is 0.075 above the core, not on it). The
lesson is the one the memo already carries in another form: write the expected
number from the geometry, then read the failure as a question about which of the
two is wrong, not as a defect report.

### Two mechanical checks widened

The probes under `tools/probes/` are SKILL too, and one with an unbalanced paren
fails at load **in a live Allegro session** — a round trip with the user, not a
test run. Both `skill_checks.py` and `check_arity.py` now check them, each
against its own definitions (pooling them with the shipped files would let a
probe's procedure satisfy a call in the exporter).

`tests/test_mech.py` and `tests/test_regression_geometry.py` were importing
`core` as a bare module rather than as part of the package. That works until
`core` reaches sideways to a sibling — `from .bend import ...` — and then it is
an ImportError deep inside `generate()`. `test_silk.py` already carried a
comment about this; the other two now do too.

## Update 2026-09-02 (round 75) — the exporter runs headless; the SKILL half has a golden corpus

The round-74 report said Plan D would need the user in Allegro after every
step, and that I do not run Allegro myself. The user's reply: look at the
other projects, you learned to run everything yourself there. They were
right. `AllegroBaseStructure` has driven Allegro unattended since its dump
work:

    allegro -nograph -s <ABSOLUTE .scr path> <copy of the board>

with a script of `skill load("…")`, `skill errset( fn(…) t )`, `exit`. Two
rules travel with it: the `-s` path must be absolute (a relative one is
resolved against the DESIGN's folder, and Allegro then sits in its command
loop with no window to say why - the trap that once produced "Allegro cannot
be driven from a shell" over there), and never `-safe` (it drops the site
configuration, where the licence server is named).

### What was done

- **`tools/skill_export.py`** - the exporter headless, and a golden corpus for
  it. `--record` exports every `input/*.brd` through a throwaway copy (the
  original is never opened or locked; a `Variants.lst` beside it travels
  with the copy) into `build/skill_golden/<board>/`, with the Allegro console
  saved beside the JSON; `--check` exports again and diffs, `-o` does one
  board. It loads `makeVariant3dIntermediates.il` alone and calls
  `makeVariant3dIntermediates(dir, color, config)` with the shipped config,
  the way `s3dExportCommand` does - not `simple3d.il`, whose job is the menu
  item, the meter and the Python launch.
- **Recorded, then checked twice** - `--record` and a `--check` right after
  it: seven boards, 7 intermediates, 132 s for the set, no difference.
  The headless export of `Cadence_Demo.brd` is byte-identical to the
  `cadence_demo.json` the user exported from the menu (83041 lines, 0 differ).

| board | size | export | wrote |
|---|---|---|---|
| `Cadence_Demo.brd` | 13.6 MB | 20 s | `cadence_demo.json` |
| `flex-b2.brd` | 2.7 MB | 19 s | `flex-b2.json` |
| `flex2-a0.brd` | 2.6 MB | 18 s | `flex2-a0.json` |
| `flex3-a0.brd` | 2.4 MB | 18 s | `flex3-a0.json` |
| `my_test_board-a0.brd` | 31.4 MB | 20 s | `my_test_board-a0.json` |
| `my_test_board2.brd` | 1.1 MB | 19 s | `my_test_board2.json` |
| `variants_test-b0.brd` | 1.9 MB | 18 s | `variants_test-b0.json` |

(Start-up is ~10 s of each; SPB 25.1, `D:\Cadence\SPB_25.1\tools\bin\allegro.exe`.)

### What it changes for Plan D

Every D step is closed the way A–C were: `--record` at the step's start (or
the existing record), the change, `--check`. What still needs a person is what
a script cannot see: the menu item, the meter and the GUI launch in
`simple3d.il`. The plan rows say so now instead of "user verification
required"; the boards used are the seven in `input/` and no others - the
user asked for exactly that.

### What to remember

- **"I cannot run X" needs a date.** The limit was true before the
  AllegroBaseStructure work found the absolute-path trap, and it survived in
  this project's memo and in my own notes long after it stopped being true.
  A limit written down should say what was tried and when, so the next
  reader can tell a finding from a habit.
- **The corpus is only as honest as its inputs.** The record is made with
  the shipped `simple3d_config.json`, not the user's local overlay, so it
  does not depend on one machine's settings - and it is byte-identical to
  the user's own export anyway, which says the overlay changes nothing the
  exporter writes on that board.

## Update 2026-09-02 (round 74) — Plan C complete: the window is a window

The same day again, after round 73's write-up: C3–C6, six commits, each one
plan step (C4 is two: the assertions first, then the move), each closed by
`tests/run_all.py` green, `golden.py --check` with no difference, and a dry
run on a scratch copy of the package pyflaked and its copied suites run
before anything touched the working tree. Nothing a STEP file contains
changed; one thing the launcher does changed, and it is in the CHANGELOG.

### What was done

- **C3** `winplace.py`: where a window opens and where it was, as functions
  of any `tk.Tk` - the virtual desk, `geometry_is_reachable(virtual, …)`,
  `parse_geometry`, centre / restore / the normal-geometry filter - with the
  four numbers named (120×40 px must stay visible; the near-screen slack).
  No tkinter import. The window keeps thin methods, so `test_geom` [6]'s
  stand-in desk (`app._virtual_screen = lambda: …`) still steers the answer.
- **C4, first commit** - `test_gui` [7f]: the round-15/16 behaviours of the
  silkscreen layer panel had never been asserted. Now they are: one row per
  layer per side with its polygon count, a refresh keeps the ticks, a layer
  excluded in the config starts unticked and a new one ticked, a side that
  is off greys its rows without touching them, All/None act on live sides
  only, the wheel is grabbed on Enter and released on Leave, the unticked
  layers reach the config as exclusions.
- **C4, second commit** - `widgets/layers_panel.py`: `LayersPanel(ttk.LabelFrame)`
  with `refresh(found, layers_off)`, `current_layers_off`, `set_all`,
  `update_sides`, `grab_wheel`/`release_wheel`. The window keeps
  `_layer_vars` / `_layer_rows` as properties onto the panel and passes
  `_side_wanted` in; freeze/thaw still walks the panel's children. The docs
  audit reads the `widgets/` package too, since the "Layers" frame the
  quick-start names lives there now. Two dead imports (`json`, `re`) went.
- **C5** `worker_bridge.py`: `WorkerBridge(on_log=, on_progress=, on_done=,
  on_error=, on_crash=)` - `alive`, `start`, `drain_once`, `check_alive` (a
  death is a crash unless `cancelled`), `cancel`, `close`; `crash_advice(code)`
  is the text, `ACCESS_VIOLATION` the number; no tkinter. The window keeps the
  `after` loop and gains `_on_progress/_on_done/_on_error/_on_crash`, the
  only places widgets are touched; it imports neither `multiprocessing` nor
  `queue`. `test_gui` [9] pokes the bridge, [9b] drives one with no window.
- **C6** one `build_parser()` in `__main__.py` for the headless CLI and the
  `--gui` window (positionals `nargs="?"`; a *window only* group for
  `--config/--json-dir/--json-file/--output-dir`; `--gui` with positionals,
  or the headless form without them, is a parser error). `parse_known_args`
  is gone: a flag the launcher passes that the parser does not know is an
  error with a message, not something dropped. `_open_window(args)` calls
  the new public `set_theme`. `tests/test_launcher.py` is the 21st suite: the
  shipped launcher line (`simple3d.il:634-639`) against a stand-in window,
  the standalone form, the by-hand flags, the refusals, the headless parse,
  and [6] - every `--flag` in `simple3d.il` is one the parser knows.

`gui.py`: 1184 lines, was 1419 before C3 and ~1500 in round 70; beside
it `winplace.py` 138, `widgets/layers_panel.py` 178, `worker_bridge.py` 143.
`python tests/run_all.py`: **26/26 in 189 s**. Plans A, B and C are
complete; M5 (the SKILL exporter) is the monolith left.

### What to remember

- **Two flags shared a `dest` with two positionals.** With the positionals
  made optional (`nargs="?"`) for the `--gui` form, `--json-file` and
  `--output-dir` mapped to the same attributes as `json_file` and
  `output_dir` - and argparse writes a positional's default LAST, so the
  flag's value was wiped and the window got `output_dir=None`. The dry run's
  stand-in window caught it in test [1] before the real tree was touched.
  The `--step-dir` flag had carried an explicit `dest` for the same reason
  since round 8, with a comment; the comment was right and I did not read
  it first. Both window flags carry `dest=` now.
- **A red job is a question, not a verdict.** C4b's full run was 24/25: the
  docs audit checks the quick-start's frame names against `gui.py` verbatim
  and the "Layers" frame had moved into `widgets/`. The audit was right and
  the code was right; the audit's idea of "the window" was one file. It
  reads the package now, the commit carries the fix, and the step was not a
  failed step - reading the one red line is what settled that.
- **Assert the behaviour, then move it.** C4 is two commits because the
  panel's behaviours had no test that named them; the move was then checked
  by a test written against the old code, not against the new one's idea of
  itself. The same order as Step 0 for the regression test.
- **A word count is not a name check.** C3 kept `import re` in `gui.py`
  because "re" appeared as a word in comments ("re-run"); pyflakes said
  unused in the next step and both `json` and `re` turned out dead already.
  pyflakes answers "is this name used"; a regex over the text does not.
- **`git status` can say M over an empty diff.** `winplace.py` was written
  LF and converted to CRLF by hand; with `core.autocrlf=true` the content is
  identical (`git diff --quiet` exit 0) but the index's stat cache said
  modified until `git add` refreshed it. Not a change - check with `diff`
  before believing `status`.
- **`--gui` refuses positionals.** A decision, written down: the three
  positionals are the headless form's; the launcher never passes them, and
  accepting them with `--gui` would mean a second way to say `--step-dir`
  and `--json-file`. `parser.error` with a message that names the flags.

## Update 2026-09-02 (round 73) — Plan A complete: core.py is a sequence of stages

The same day again, after round 72's write-up: A3–A10, 9 commits, each
one plan step, each closed by `tests/run_all.py` green, `golden.py --check`
with no difference and, since this round, a dry run on a scratch copy of the
package pyflaked BEFORE a suite run was spent on it. Nothing a STEP file
contains changed.

### What was done

- **A3** `stackup.py` (the stackup arithmetic, no OCC) and `reporting.py`
  (`LogFn`, `ProgressFn`, the no-ops - every stage module needs them and none
  may import core for them).
- **A4** `board.py` (the board body, `_rim_faces`; `_face_from_wires` to
  `contour.py`), then `layer_solids` - THE zones×layers walk, once, for the
  fused board and the inspect build alike.
- **A5** `legend.py` (the silkscreen half; the docs audit now reads
  `DEFAULT_FLAT_HEIGHT` from there).
- **A6** `models.py` (`StepFileIndex`, `component_transform`, the XCAF label
  helpers, `_sanitize`) and `ModelCache.labels_for`, the read-once block of the
  component loop as a method that says "missing" / "unreadable" once per
  file. The loop in `generate` is placement only.
- **A7** `stepdoc.py`: `StepDocument` (app, doc, both tools, the named root)
  and `write(path, minimize_size)`, with the writer setting that halves the
  file set where it has to be.
- **A8** `build.py`: `BuildOptions`, the nineteen options once; `from_settings`
  for the window, `from_args` for the CLI; `generate(options=...)` or the old
  keywords. The meaning of each option moved out of `generate`'s docstring.
- **A9** `generate` → `_prepare_stackups` (→ `_Stack`), `_plan_fold`,
  `_build_board`, `_build_legend`, `_place_components`, `StepDocument.write`;
  every segment body verbatim, each stage unpacking the names it reads at its
  top. `generate` is 90 lines with its docstring, down from 646.
  `test_modes.py` [6] asserts the progress values never go backwards (they
  were asserted nowhere) and calls two stages alone.
- **A10** `board_mode` validated against `build.BOARD_MODES` (an unknown mode
  used to fall through to the plain solid, silently); the whole-board batch
  rule is `intermediate.batch_jobs`, called by the worker and by the CLI's new
  `--no-full-board`; `test_variant_path.py` [8] tests it by behaviour.

- **B5, the five extractions** (later the same day): `_map_strip` is
  `_Frame` (the cylinder and the map into its parameter space),
  `_edge_curves` / `_sampled`, `_wire_on`, `_face_on` / `_walls`,
  `_sewn_solid` / `_expected_volume`, and a 131-line sequence (was 414)
  that keeps `give_up` and its first-reason rule. One commit each, each
  closed by the full suite; all five were first applied to a full dry copy
  and the copied fold suite run against it - [17e], the loose corner, green
  at every stage. Plans A and B are complete.

`core.py`: 724 lines, was 2587 in round 70. `python tests/run_all.py`:
**25/25 in 186 s**.

### What to remember

- **A dry run on a copy has to be rooted at the copy.** `stepbuilder` has no
  `__init__.py`, so it is a namespace package: with both the repository and
  the copy on `sys.path`, `stepbuilder.core` resolves to whichever portion is
  FIRST - and `tests/_support.py` puts the repository first. The A4b "matches
  the golden record on a dry copy" check had measured the working tree. Since
  A6 the dry checks pin `sys.path = [copy] + everything-not-Simple3D` and
  assert `core.__file__` is under the copy; since A9 the copy carries `tests/`
  and `demo/` too, so its own `_support` roots the paths and a copied suite
  runs against the copy.
- **Dry-run, pyflakes, then the suite.** pyflakes on the copy caught
  `_open_wire_detail` missing from `legend.py`'s imports (A5) - the same error
  path A1 lost - before anything ran; and A9's generated preamble put an
  unused `thickness = stack.thickness` into the legend stage because the word
  appeared in a string literal. Both cost seconds instead of a 3-minute run.
- **Read one `sed` range at a time.** Two ranges printed back to back read as
  one file, and I "found" `--dated-name` carrying `--fold-neutral`'s help text.
  The fix I wrote for it failed its own assertion, which is how I learned the
  bug did not exist. A replacement that asserts its match is a check on the
  reading, not only on the writing.
- **Do not edit a shell script bash is running.** The stage script for B5
  was edited (a `set -o pipefail` added) while its first run was in
  progress; bash reads the file as it goes, hit the shifted bytes and
  reported a syntax error AFTER the useful work had finished. The log said
  25/25; the exit code said 2. Read the log, and write scripts before
  starting them.
- **`generate`'s five stages take `(data, stack, fold, options, document, …)`**
  and return what the next needs; the `_Stack` dataclass is what the stackup
  stage settles. A9 changed no line inside the segments, so the round-26 to
  round-67 reasoning in their comments still reads in place.

## Update 2026-09-02 (round 72) — the first moves: contour, the intermediate, settings, the bend package

Same day as rounds 70 and 71. 19 commits since round 69, each one plan
step, each closed by `tests/run_all.py` green and `tools/golden.py --check`
with no difference. Nothing a STEP file contains changed; `git diff` of the
golden corpus says so seven times over, and the fold suite's 300 random
layouts say it for the plan.

### What was done

- **A1** `stepbuilder/contour.py` (the contour primitives → wire / polygon,
  the round-63 arc reading in one place) and `stepbuilder/errors.py`
  (`StepBuilderError`, since three modules raise it). The `core`↔`bend`
  cycle is gone; `import stepbuilder.bend` leaves `core` unloaded.
- **A2** `stepbuilder/intermediate.py`: `Intermediate` parses a file once and
  answers every question about it; `resolve_jobs` hands parsed intermediates
  to the worker and the CLI batch, and `generate` accepts one. Measured: one
  `json.loads` for resolve + generate. `RESERVED` lives there; the exporter's
  NOTE and `test_variant_path.py` [8] point at it.
- **C1–C2** `stepbuilder/settings.py`: the pair (merge / read / local path)
  and the `gui` section as ONE table, `GUI_KEYS` — name, field, default,
  load, save — walked by `load_gui_settings` (both migrations are the `load`
  of the key that superseded them) and `save_gui_settings` (only what
  differs). The window keeps one `var.set` per field. A 24-scenario snapshot
  of what the window loads from eight settings files and the bytes it writes
  back is byte-identical before and after. `tests/test_settings.py` is the
  20th suite and the first place those rules are checked without Tk.
- **B1–B6** `stepbuilder/bend/` is a package: `constants`, `info`, `regions`
  (one `_Piece` mixin where `_Region` and `_Strip` had two copies of
  `holds`), `pieces`, `cut`, `strip_revolve`, `strip_wrap` (moved whole; the
  five extractions are still to do), `plan` (`FoldPlan`, and `plan_fold` with
  its seven closures lifted into module functions with explicit arguments)
  and `apply` (`apply_plan`, `_fuse_all`). `__init__` defines nothing.
- **B7** the magic numbers named in `bend/constants.py`, each with the reason
  that used to sit beside it (`FLAT_FRAME_MARGIN`, `BAND_REACH`, `SEAM_TOL`,
  `SEAM_WARN`, `DOUBLE_CLAIM_WARN`, `CLAIM_GRID`, `SLIVER_RATIO`,
  `FACE_POLY_PER_CURVE`, `DRAWN_AREA_TOL_*`, `SLICE_OVERLAP_MIN`, `SAMPLE_*`,
  `LENGTH_PROBE_STEPS`, `SEW_TOL`); the literals replaced by the names.
- **`tools/python_names.py`**, the fourth mechanical check in `run_all`:
  pyflakes over the package, the tests and the tools, kept to undefined
  names and redefinitions. See below for why it had to exist.

Order, where it differs from the plan's: `cut.py` before `strip_revolve.py`
(the revolve needs `_plane_face`), `strip_wrap.py` before `apply.py` (apply
needs both constructions), so that no module ever imported from `__init__`.

`python tests/run_all.py`: **25/25 in 186 s**. Every commit is on `main`,
nothing pushed.

### What to remember

- **Moved code loses its names.** Twice today a function moved verbatim left
  a name behind: `_open_wire_detail` out of `core`'s re-export while an error
  path in `core` still called it (reached only by an open silk contour, so no
  test), and `MIN_ANGLE` inside `_map_strip`, which swallows its failures
  into "faceted" — the fold suite reported it one full run later, as a wrong
  build. `pyflakes` finds both in a second. It is a check now, and the last
  three moves were dry-run on a scratch copy of the package and pyflaked
  BEFORE a suite run was spent on them.
- **A `git add` of a path already gone from the index aborts the chain.**
  `git add -A stepbuilder/bend.py stepbuilder/bend/ && git commit` — the
  first path had been staged as deleted earlier, `git add` said "pathspec did
  not match" and the `&&` never reached the commit; the next step's edits
  then landed on top of an uncommitted one. Recovered from the index, which
  still held the earlier stage. Check `git log -1` after every commit
  command, and never chain a `git add` of a deleted path.
- **A full run beside other work takes twice as long**, and `run_all`'s
  output is buffered until it exits — an empty result file after seven
  minutes was not a hang, it was contention with the dry runs. Look at the
  test-output folders' timestamps before deciding anything is stuck.
- **`demo/ap-214/demo.json` has no format marker** (finding 15 in
  ARCHITECTURE.md): the window and the worker refuse the repository's own
  demo board; only `generate()` called directly builds it. Not changed — the
  marker is Plan E's business.
- **`settings.py` imports OCP** for three default numbers (G5 in the plans
  names the fix). The merge and the reader above the table need neither.

## Update 2026-09-02 (round 71) — Step 0: the net before the first move

Same day as round 70, the first work off `REFACTORING_PLANS.md`. Nothing that a
STEP file contains changed; what changed is whether the suite can tell.

### What was done

- **0.1 The regression test can fail.** `tests/test_regression_geometry.py`
  now `check()`s the volume (to 1e-4) and the entity count and exits 1 on
  either. The 5054-vs-5038 question was settled by *building* the same board
  at seven commits (`git archive <commit> stepbuilder demo | tar -x` into a
  scratch folder — no checkout, the working tree untouched): 5077 at the first
  Python rewrite (`1c5d46b`), 5054 from `3ad1617` through `a402fff` — the
  number round 21 wrote down — and 5038 since `687ea3f`, round 63's "read an
  arc by its two ends". Volume 12073.309477 at all seven. So the count is a
  property of the writer, it moved when the arc construction moved, and nobody
  noticed because nothing looked. 5038 is pinned, with that history in the
  docstring.
- **0.2 One preamble.** `tests/_support.py` holds the paths, `fails`,
  `check()`, `rect()`, `read_step()`, `volume()` (the iterative integrator),
  `bbox()`, `count_solids()`, `entity_count()`. Twenty scripts import it. The
  edit was a script with every replacement asserted (152 of them); the suites'
  own assertions were not touched. Two integrators became one: on the
  regression board they differ by 1.3e-8 mm³, so the plain suites lost
  nothing. A deliberate `check("x", False)` was run through the import to see
  that it reaches the exit code — the failure being fixed is exactly a `fails`
  list that is not the one `sys.exit` reads, and a suite that rebinds
  `fails = []` would recreate it (`_support` is where that line must not be).
- **0.3 A golden corpus.** `tools/golden.py` builds `demo` in the three
  stitchings and the fold suite's rigid-flex board (now a fixture,
  `tests/fixtures/rigidflex.json`) in the three stitchings and flat — 7 cases,
  18 s — and records volume, box, solids, entities, placed/skipped and the
  warning count in `build/golden.json`; `--check` rebuilds and compares
  (volume and box to 1e-6, the rest exact). Each case runs in a child process
  so an OCCT access violation costs one case, not the corpus. `--with-local`
  would add `failed/` and `input/`; **not run** — those are the user's designs
  and the plan says ask first (it also needs `--step-dir` at their library).
- **0.4** `_layer_region` imports only `BRepAlgoAPI_Common` locally; the
  module-level `BRepAlgoAPI_Cut` is no longer shadowed inside the function.
- **0.5** `colors.as_fraction` deleted (never called); the `for … : pass` in
  `audit_docs.py` deleted; `.claude/launch.json` deleted — it pointed at
  step2html's preview server, a leftover from before that tool moved out.

`python tests/run_all.py`: **23/23 in 188 s**. `tools/golden.py --check`: no
difference against its own record. Nothing committed — the user commits on
request; 0.1–0.5 are separable by file if they want one commit each.

### What to remember

- **Settle a number by measuring, not by reading.** The memo carried 5054 for
  three rounds after it had become 5038; each mention was copied from the one
  before. Seven builds at seven commits took two minutes.
- **A line-ending pass does not know whose file it is.** Converting the files
  this round wrote to CRLF (the working copy's convention under
  `core.autocrlf=true`) also converted `.claude/settings.local.json`, the
  user's own, because the list came from `git status`; put back. Filter by
  what you edited, not by what is untracked.
- **The golden corpus is local.** `build/golden.json` is gitignored, so it is
  a yardstick for this machine and this refactoring, not a fixture. Rebuild it
  (without `--check`) only when a step *deliberately* changes what a file
  contains — and say so in the memo, as with the entity count.

## Update 2026-09-02 (round 70) — full review, the structure written down, split plans

Asked for: read everything, review all the code, say which pieces are monoliths
and which could be reused, draw the structural and functional pictures, and plan
the split. Read in full, not scanned: both `.il` files, the six Python modules,
all 22 test scripts, the three tools, the hand test, the eleven probes, the
config, this memo end to end, README, QUICKSTART and CHANGELOG (English halves).
**No code was changed** — this round documents and plans.

### What came out

- **`ARCHITECTURE.md`** — the three pieces and the one boundary, a dependency
  graph, the pipeline as one flowchart from the menu item to the STEP, the
  intermediate's shape as the reader sees it, every SKILL global with when it is
  reset, and the monolith / reusable / glue classification, file by file and
  function cluster by function cluster.
- **`REFACTORING_PLANS.md`** — five monoliths (`core.generate` 646 lines,
  `bend.plan_fold` 428, `bend._map_strip` 381, `gui.StepBuilderApp` ~1500, the
  exporter as one 3925-line file), a plan for each, a Step 0 that has to come
  first, a format_version 9 plan for the intermediate's flat namespace, and the
  order to do it all in. Every step names the tests that must be green before
  and after it and what "done" means.

### Baseline, measured

`python tests/run_all.py` under 3.12: **23/23 green in 277 s** — the fold suite
alone is 176 s now, which is why the "~55 s" figure this memo used to carry is
out of date. The C++ geometry regression reproduces 12073.309477 mm³ exactly.
Its write statistics say **5038 entities** where round 21 recorded 5054; the
test never asserted the entity count, so nothing has said which is right or
when it moved. Left as a question for Step 0.1 of the plans, not answered here.

### Findings (the list lives in ARCHITECTURE.md §6; the ones worth a sentence)

1. **`tests/test_regression_geometry.py` cannot fail.** It prints `MATCH` or
   `DRIFT` and exits 0 either way; `run_all` reads exit codes. The one test that
   compares against the C++ original has been decorative since it was written.
   Same class as round 68's sentinel and round 61's `IsDone`: a check that
   reports success on evidence it never examined.
2. **Strings reach the JSON unescaped** in five places of the writer — the
   refdes and `step_name` in `symbolReturn3DElements`, the zone name, the silk
   layer name, the warning text and the variant name — while `s3dJsonQuote`
   exists and is used everywhere else. A backslash in a STEP mapping entry (a
   path, say) breaks the whole intermediate. Latent; plan D4.
3. **The upstream procedures leak locals as globals.** `gdsysGetVariantInfo`
   assigns a dozen names it never declares, `makeSlot` seven, `makePcb` rebinds
   its *caller's* `pcbColor` under SKILL's dynamic scoping, and
   `create3dIntermediateFormat`'s `name`, `pcb`, `outFile`, `outPort`, `lines`
   land in `makeVariant3dIntermediates`' own `let` by accident. Nothing reads
   them afterwards, which is the only reason it works. The four mechanical
   checks do not look for this; plan D1 adds the fifth.
4. **Two rules for requirement #1.** `calculateBoardThickness` gates on the
   `SOLDERMASK` name (round 2), `s3dLayerInBody` on position + SILK/PASTE
   (round 34). A plain board whose mask is named `SM_TOP` is one thickness in
   *Solid* and another in *Solid colored layers*. Plans D5/E2.
5. **`input/` was untracked and not ignored** — 57 MB of the user's boards one
   `git add -A` from the public remote, while `failed/` beside it carries a
   comment saying exactly why such files must be ignored. Fixed in this round.
6. The `core`↔`bend` import cycle (hidden by local imports), three copies of the
   `generate()` argument list, the GUI's config keys named twice, four full
   parses of the intermediate per Generate, the visibility-snapshot idiom copied
   five times across the exporter and the probes, and `core.py:395` carrying the
   very `UnboundLocalError` trap `_rim_faces` documents. All in the plans.

### Also changed

- README: "Nothing temporary is written next to your board" softened — the
  pre-flight log is written and deleted (round 43 says so; the README overstated
  it). Both halves. The two new documents are listed under *What is where*.
- CHANGELOG entry, both languages. `.gitignore`: `input/`.
- Memory: the round, the test-that-cannot-fail lesson, and the SKILL scoping
  fact, each as its own note.

### What to remember

**A review's first deliverable is the baseline.** The suite was green, and one
of its 23 jobs was incapable of being anything else. Before trusting a green
run as the safety net for a refactoring, read the exit path of every test.

**Read what the tests transliterate.** Nine SKILL procedures exist twice — once
in SKILL, once as a Python copy inside a test — and those copies are the only
executable specification the SKILL side has. They are scattered across seven
files; plan F2 gathers them.

## Update 2026-08-21 (round 69) — the hole is not always at the pad

The user put `bone-a2.json` and its STEP in `input/` with two screenshots: the
board in Allegro's own 3D and the same board in Inventor. Same outline, same
five round holes, and the four PLS-4 holes along the bottom edge visibly
different — half-circles cut into the edge in Allegro, keyholes sitting just
above it in ours. Their own diagnosis, and it is right: **the padstack has a
drill offset and we were ignoring it.**

### What the data says

| | |
|---|---|
| the four PLS-4 circles in the intermediate | `x = 2.19, 4.73, 7.27, 9.81`, all `y = 0.375`, `r = 0.5` |
| the board's bottom edge | `y = 0` (outline bbox `x 0…12`, `y 0…21`) |
| X5, the `HDRV4W64P254_4X1_1016X254H854` header | placed at **`y = 0.0`** |
| Padstack Editor → Drill Offset | *Offset from padstack origin to hole*: **x = 0.3750**, y = 0 |

So the pads sit 0.375 mm inboard and the drill line is the board edge itself.
Both files agreed on 0.375 — the intermediate and the STEP built from it are
perfectly consistent — which is exactly why it read as a rendering difference
rather than a geometry one.

### The mechanism

`symbolReturnPinHoles` branches on `padstack->usage == "Slot"`:

- the **slot** branch calls `makeSlot`, which had, inline, `drillOffset =
  padstack->drillOffset` … `rotateXY( (x y) (x+dx y+dy) pin->rotation )`;
- the **round-hole** branch did `hole = makeCircle( pin->xy … )`.

Two branches of one `if`, and only one of them knew the drill can sit off the
pad. `s3dDrillXY( pin padstack )` is that arithmetic, once; `makeSlot` now calls
it instead of carrying its own copy, so the two cannot drift apart again. The
offset is in the **padstack's** frame, so it is rotated by `pin->rotation`
before being added — for these pins that is 270°, which turns `(+0.375, 0)` into
`(0, −0.375)` and lands every drill exactly on `y = 0`.

### The 0.375 mm, as a picture

A circle of `r = 0.5` cut by the edge at `y = 0`:

| centre | mouth in the edge | how far it reaches inboard |
|---|---|---|
| at the **pad**, `y = 0.375` | 0.661 mm | 0.875 mm — a keyhole |
| at the **drill**, `y = 0` | 1.000 mm | 0.500 mm — a half-circle |

Rebuilt from a hand-edited intermediate to confirm the whole chain: the four
`r = 0.5` cylinders move from `y = 0.375` to `y = 0.0` and the bottom edge
becomes what Allegro draws.

### What this does and does not touch

Only padstacks that actually carry an offset. Everything else returns
`pin->xy` unchanged — deliberately the same object rather than a rotation by
zero, so an exact coordinate does not pick up sin/cos noise. Component
placement, pads and silkscreen are unaffected: they are about the pad, and the
pad has not moved.

### The lesson

**Agreement between two of your own files is not evidence.** The JSON said
0.375, the STEP said 0.375, and the check that would have caught it was against
neither — it was against the third thing, Allegro's own 3D. When output and
intermediate agree and the picture still disagrees, the intermediate is
measuring the wrong feature, not reporting the right one badly.

And: **when one branch of an `if` knows something the other does not, the
knowledge is living in a place instead of in a function.** The slot branch had
been right about this since the upstream code; the round-hole branch beside it
never was.

## Update 2026-08-21 (round 68) — the pre-flight check passed itself

The user installed node.js. Simple 3D then did **nothing**: press Export, a
console window flashes, no 3D window, and no message anywhere saying the
packages were missing. Two separate faults, and the second one is the
interesting one.

### 1. Which Python

The node.js setup's *Tools for Native Modules* step runs Chocolatey, which
installed **`C:\Python314`** (Python 3.14.7) on 2026-08-20 20:57 — into the
**machine** PATH, which Windows composes **before** the per-user one. So
`python` and `pythonw`, which is what `S3D_Python` / `S3D_PythonW` default to,
stopped meaning the interpreter this tool's packages are in:

| on PATH | version | OCP | tkinter |
|---|---|---|---|
| `C:\Python314` (new, machine PATH) | 3.14.7 | **no** | yes |
| `…\Programs\Python\Python312` | 3.12.0 | **yes** (cadquery-ocp 7.9.3.1.1) | yes |
| `…\Programs\Python\Python311` | 3.11.4 | no | yes |

Nothing was uninstalled. A different interpreter answered to the same name.
Fixed on their machine by pinning `allegro.python` / `allegro.pythonw` to the
3.12 **full paths** in `simple3d_config.local.json` — the gitignored local file,
never a tracked one.

### 2. Why it was silent — the check forged its own sentinel

`s3dPreflight` exists precisely to stop this: run the interpreter once,
synchronously, capture stdout+stderr, and report an `ImportError` in the Allegro
console instead of letting `pythonw` (which has no console) die where nobody can
see it. It ran. It **passed**. Then the GUI was launched and died silently on the
very error the check had just been handed.

Success was signalled by the check printing `S3D_OK`, and the scan looked for
that string anywhere in the captured log. **From Python 3.13 the interpreter
keeps the text of a `-c` command and echoes the offending source line in the
traceback**:

```
Traceback (most recent call last):
  File "<string>", line 1, in <module>
    import stepbuilder.core, tkinter; print('S3D_OK')
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
ModuleNotFoundError: No module named 'OCP'
```

The success sentinel is *in the failure output*, because the sentinel is part of
the source line that failed. Verified both ways on this machine: 3.12 prints the
traceback with no source echo, 3.14 echoes it and the log contains `S3D_OK`.

**A sentinel must not be forgeable by the output it is scanning.** The fix is one
character of whitespace: `print('S3D' '_OK')`. Two adjacent literals concatenate
at compile time, so the process still prints `S3D_OK` while the source text
cannot contain it. `tests/test_launch_cmd.py` case [3] now asserts the sentinel
is **absent** from a failing log — which is vacuous on 3.12 and earlier, so case
[5] also asserts the split form in `simple3d.il` itself, version-independently.

This is the same class as round 14a and round 61's `IsDone`-with-no-solids: a
check that reports success on the evidence it was built to reject.

### 3. What else changed, all in the same direction

- **The check prints which interpreter answered** — `sys.executable` and the
  version, `-u` and before the imports so it is in the log on the failing run
  too. `python` is a name; PATH decides what it means today, and from inside
  Allegro there was no way to see which one you got. That one line is the whole
  of this diagnosis.
- **The advice was stale.** It said "the paths at the top of `simple3d.il`",
  which round 59 removed. It now names `allegro.python` / `allegro.pythonw` in
  `simple3d_config.local.json`, shows the shape, and prints the values in force.
- **`pip install cadquery-ocp` became `<that python.exe> -m pip install …`** —
  bare `pip` is the same ambiguity that caused this.
- **A blocking `axlUIConfirm`** on a failed pre-flight. The console line was
  correct and complete and can be closed, scrolled past, or simply not looked
  at; the failure it describes looks from the outside exactly like nothing
  happening. `errset`-wrapped, and Allegro's own `noconfirm` disables it.
- **The fail-open path says so out loud.** If the check itself errors the export
  still launches — right, a broken check must not block a working setup — but it
  now warns on the status line and says in the console that `pythonw` has no
  console to fail in, so the silent no-op cannot return through that door.
- README and QUICKSTART, both halves: a second Python can shadow yours, and how
  to pin the one you meant.

### The lesson worth carrying

**A checker's own text is part of the input it will read back.** Sentinels,
markers and delimiters have to be built so the failure path cannot emit them —
and a language runtime is allowed to start quoting your source at you in a minor
release. The check had been right for a year and was falsified by a Python
upgrade, not by a change to it.

## Update 2026-08-15 (round 67) — a folded panel painted with the board edge colour

The user's board came back with the whole LCD stiffener panel — 2398 mm² of flat
face, most of what you see from that side — in the colour they had chosen for the
board **edge**.

### The mechanism

`_rim_faces` asks "is this wall vertical" **in the frame the face was built in**,
because after a fold half the board's flat faces stand vertical and half its
walls do not. That much has been right since round 36. The frame comes from
`flat_frame`, which tried each region's inverse and kept the first whose
footprint the un-folded point landed in.

A **wrong** region's inverse is a rotation about a different axis, and it does
not fail — it answers. That panel's top face came back at **z = 31.08** through
`BEND_3 slice 8/24`, on a board 1.63 mm thick. In that frame the panel stands
vertical, so it was rim, so it was painted.

### The fix, and why it was free

Two tests, both of which were available all along:

- **The un-folded point has to land back IN the board.** The plan now carries the
  two faces of the flat board, and a region whose inverse misses that band by
  more than a millimetre is not the frame this face came from. z = 31.08 against
  0 … −1.63 is not a near miss.
- **Panels are tried before slices.** A slice is a facet of a bend, only ever
  real geometry when a bend could not be built exactly; it stays in `regions` to
  answer "where does this point end up" and must not outrank the panel a face
  actually belongs to.

| | before | after |
|---|---|---|
| total rim area | 4359.4 mm² | **2022.5** |
| largest rim face | 2398.5 mm² (the panel) | 153.9 mm² |

What is left is side walls at mid-thickness (z ≈ −0.70 on a board whose faces are
0 and −1.63) plus the panel's own edges at z ≈ 20.05 — which is what a rim is.

### Two things about how this one was found

**A wrong inverse does not fail, it answers.** Whenever something is identified
by trying candidate transforms and taking the first that fits, the fit test has
to be strong enough to exclude the wrong candidates. Here the missing test cost
one comparison and the information for it was already in hand.

**Ask which mode before measuring.** The first report said *Solid colored
layers*. Two probes went into proving that the layered colouring was correct —
which it is: the panel's faces trace to COVERLAY_INNER2 and STIFFNER_INNER1, and
there is no large base-coloured face anywhere on the board. All true, all
useless, because the build was **solid** mode with a board-edge colour set. The
same picture has a different explanation per mode, and the mode is one question.

## Update 2026-08-14 (round 66) — the k a board can take, and a tolerance that changed jobs

Two things, both raised by the user looking at the model rather than at a log.

### "Can such bends always turn up at k = 0.5?"

Yes, and structurally rather than by bad luck. Allegro lays its bend areas out at
**k = 0** — the drawn area IS the inner arc — so at any higher k every strip is
wider than the designer allowed, by `θ·k·t`. Two areas collide as soon as their
clearance is less than the sum of the two growths measured in one direction. On a
board whose areas were laid edge to edge that is certain, not possible.

Three degrees, all of which this project has now met: the strips **graze** (a
pinched piece, round 64), they **overlap** (a bend refused, the ring in the test
corpus), or the panel between them **vanishes**.

So the build now answers the question the user actually has — *what is the
largest foldNeutral THIS board takes cleanly* — by bisecting: ten trial cuts
between 0 and the chosen factor, and **only when there is trouble to explain**.
About a second against a build measured in minutes.

```
note: this board's bend areas are laid out at k = 0, as Allegro draws them, and
      the tightest pair on it takes foldNeutral up to 0.36. At the current 0.50
      the strips reach each other and the piece between them had to be repaired.
      foldNeutral 0 reproduces the drawing exactly; 0.36 is as physical as this
      layout allows.
```

It is **advice, not trouble**, so it got its own severity: `note:` lines are blue
in the window, beside orange warnings and dark red errors. The bend-area notes
that already existed pick it up too, which is right — same kind of line.

Getting the number needed the chain and the clash filter to be callable for a
trial factor rather than only for the chosen one. Both are functions of k now;
one copy of the arithmetic, which was the whole point — a ceiling computed by a
second, slightly different formula would be worse than none.

**Worth keeping from the same conversation**, because it is not obvious:

- Each bend takes **its own** inner surface, for the axis and for the developed
  length alike. Verified: on a synthetic S, `inner=bottom` puts the axis at
  `bottom − R` and `inner=top` at `top + R`; on the real board BEND_1 sits at
  −6.912 and BEND_2 at +4.713.
- `inner_side` is a property of the MATERIAL's faces, not of the world. After a
  180° fold the board is upside down, so its own "top" faces down — which is why
  a *bottom-then-top* pair is **not** an S and does not come back to its plane.
- **k barely moves where a panel lands.** A 180° bend does not move it at all:
  the strip grows symmetrically about the bend line, so `u_final = lo + hi − u =
  2·(bend line) − u` and the width cancels. Measured on all four 180° bends —
  0.000 shift. Only bends that are not 180° move, and those do accumulate along
  a chain: the CONN arm's 180° → 200° → 45° gives 0.000 → 0.189 → 0.346 mm.
  What k really changes is **how much of the board is arc rather than flat**:
  +5.214 mm of material over the six bends.

### A tolerance that quietly changed jobs

The user: a rounded arm end comes out visibly polygonal. Not the bend — every
strip on that board is a true cylinder — the faceting was in the **edge**.

`contour_points` samples an arc into **eight chords**, and its docstring said, in
so many words, that a chord approximation "is not merely acceptable but the
point" — because its answers were areas and containment tests. **Round 62 made
the same function decide real geometry** (the pieces are cut from it) and nobody
went back to the tolerance. On this outline — 48 segments, 22 arcs at r = 3, 4, 9
and 14 — that is **67 µm of flat per chord** on the largest corner.

`_cut_into_pieces` now takes the outline as the intermediate writes it and builds
the face with `core.build_contour`, arcs intact; the flattened copy goes on doing
the job it was accurate enough for. Nothing in the wrap needed changing —
`_map_strip` already turns a circular edge into an exact ellipse in the
cylinder's parameter space, and carries a note saying it had to, because sampling
a relief notch as a spline used to throw the whole solid away. `_face_poly` had
to learn to sample, since taking the vertices of a wire that is no longer
polygonal cuts a rounded corner off entirely.

Pieces now carry 7 circular edges on the held panel and 2–3 per arm strip where
they carried none; they still tile the outline exactly (19484.35 against
19484.29 mm²); the folded body is 22390.560 mm³ against the 22388.679 the board
is made of, +0.008%.

**The lesson, and it has cost two rounds now:** when code is repurposed, its
tolerances come along without being re-read. The docstring even said what the
old purpose was. Round 64's pinch and this round's facets are the same mistake
seen twice — a number chosen for classification deciding geometry.

### One more trap, for the record

Comparing a fresh build against a STEP written **before the user re-exported the
board** showed a 289 mm³ loss that did not exist. The board file had changed
under the reference. Re-measure the baseline from the current input, never from a
file on disk whose provenance is a few messages back.

## Update 2026-08-14 (round 65) — the legend printed on zones that are not printed on

The user fixed the coverlay in the board itself rather than in the config —
"так правильнее" — re-exported, and found the next thing: the legend appears
over `CONN_FLEXI_STIFFENER`, `FLEXI_STIFFENER` and `LCD_FLEXI_STIFFENER`, and
the cross section says those stackups have no silkscreen.

### Where the statement was lost

A cross section assigns mask and coating layers **per stackup** — the rigid-flex
guide even walks through it: *"For the Primary stackup, deselect the Coverlay
and adhesive masks"*. So a board says "no legend on the stiffener zones" by
leaving the silkscreen layer out of those stackups.

`s3dLayerInBody` drops SILK/PASTE layers before the stackup is measured, and
rightly — requirement #1 from round 2, silkscreen is printed ON the board, not
part of it. But dropping the layer threw away the only record that it had ever
been there, and the reader then had nothing to go on: the legend was placed at
one z for the whole board and clipped only to the outline.

Confirmed in the data: of the four stackups, only PRIMARY carries
`SOLDERMASK_TOP/BOTTOM` at all; the three flex ones carry no masks. None carries
a silkscreen layer, because the exporter had already removed them.

### The fix, in both halves

**`format_version: 8`** — each stackup gains
`"silkscreen": {"top": bool, "bottom": bool}`, filled in while the SILK/PASTE
layers are being dropped. Side by **position**, not by name: a layer outside the
outermost conductor on the top side is a top-side layer whatever it is called,
so `SILKSCREEN_TOP`, `SILK_TOP` and "Silk Screen Top" all answer the same
without a list of spellings.

**`clip_silk_to_zones`** drops a legend polygon whose centre lands on a zone
whose stackup is not printed on that side. Three deliberate choices:

- A polygon on a **printed** zone wins outright, so a glyph straddling a
  boundary stays with the side that has a legend.
- A polygon on **no zone at all** is kept. It is not the legend's job to be a
  second outline clip.
- An intermediate with **no `silkscreen` key anywhere** is not clipped at all.
  It cannot say, so nothing is assumed, and every file already on disk behaves
  exactly as before.

Measured on the re-exported demo board (standing in the flag, since the user's
file predates it): top 1379 → 1365, dropped 10 over `CONN_FLEXI_STIFFENER` and
4 over `FLEXI_STIFFENER`; bottom 908 → 892, all 16 over
`LCD_FLEXI_STIFFENER` — exactly the three zones named.

### Still open, and worth doing next

The legend is placed at ONE z for the whole board — `board_top_z` /
`board_bottom_z` — while each zone has its own faces. On this board the flex
sits 0.49 mm below the rigid top, so a legend on a flex zone floats above its
own surface. The same grouping this round introduced is what a per-zone height
would be built on.

## Update 2026-08-14 (round 64) — the stack datum, a pinched piece, and what a coverlay shape means

Three things the user found by putting our build beside Allegro's own 3D, in the
order they were fixed.

### The stack datum: every stackup was measured from its own first conductor

The exporter puts z = 0 at each stackup's **first conductor**. That is a common
datum only while every stackup's first conductor is the same physical layer. On
Cadence's demo it is not — the flex is an INNER pair:

| layer | PRIMARY | FLEXI1 |
|---|---|---|
| INNER1 | −0.5208 | **0.0000** |
| INNER2 | −0.8058 | **−0.2850** |

The same copper, 0.5208 mm apart, and the same offset for both, so a pure shift.
The flex tails left the rigid board near its top face instead of out of its
middle, taking every bend axis, zone height and component on a tail with them.

`align_stackups` makes the stackup with the most conductors the reference and
slides the others until the conductors they share line up. Nothing shared →
report it and keep the exporter's answer. It runs **after** `drop_soldermask`,
because `restack` re-derives z from the first conductor and would undo it.
Boards whose stackups already agree measure 0 and are untouched — which is the
entire existing corpus, and why 22/22 stayed green.

Flex zones now sit at −0.490 … −1.140 inside the rigid 0 … −1.630. Board
thickness 1.630 where it read 1.661.

### A piece the boolean pinched, and the sliver that ate a layer

The wedge between BEND_6 and BEND_4 was missing. Its piece came out of the cut
**pinched**: a zero-width slit 19 mm long, because the outline's edge and the
strip's edge are collinear there. Area right, `_double_claimed` 0, `_seam_gap` 0
— only `BRepCheck_Analyzer` called it invalid. A prism on such a face is
unusable: 2 of 57 layer parts intersected it where 8 should have.

`ShapeFix` splits it. Two traps came with that:

- **Keep every fragment's polygon**, not just the largest. `region_at` uses it,
  and the anchor landing on the smaller half is a coin toss — test [7b0] found
  it immediately.
- **Drop the slivers the repair leaves.** A 0.085 mm² chip beside the 15.42 mm²
  wedge took the whole **173.763 mm³** dielectric of that arm to zero: prismed,
  a sliver is a degenerate solid, and the fuse of the folded pieces then
  produced nothing at all. Under a hundredth of the piece goes, with the area
  in the log.

| | volume | vs the 22679.233 mm³ the board is made of |
|---|---|---|
| wedge lost | 22673.364 | −5.869 |
| repaired, sliver kept | 22505.518 | **−173.715** |
| repaired, sliver dropped | 22679.467 | **+0.234** |

`apply()` no longer returns a null shape in silence: a fuse that yields nothing
keeps the pieces as a compound and says so. That silence is *how* a whole layer
disappeared — the part simply measured zero.

### What a shape on a coverlay layer means — settled, by Cadence

Searched the whole shipped doc tree (`D:\Cadence\SPB_25.1\doc\`). **One**
sentence in the entire set addresses it, in the 3D Canvas guide:

> "The coverlay layers are interpreted as negative shapes by 3D canvas.
> **Coverlays specified as positive shapes are not rendered in 3D canvas.**"
> — *Changing Color of Coverlay Layers*, Allegro X 3D Canvas User Guide 25.1

So the default is right — coverlay shapes are openings, which is what
`settings.negativeLayers` already says — and Cadence itself confirms the other
kind of board exists, and that its own 3D **omits the layer** there. The demo
board is that kind: its coverlay shapes total 5255.9 mm² against 2364 mm² of
flex zone, and read as openings they delete the coverlay from the arms and keep
it nowhere useful.

**No data test can tell the two apart.** The tempting rule — "if subtracting the
shapes leaves nothing, they must be material" — is exactly the round-27 case on
the user's own board, where `COVERLAY_TOP` had a shape matching the FLEX1 zone
outline and it was a genuine opening, a flex tail with its contacts exposed.
Same signature, opposite meaning. So the list stays the decision, and what the
build owes the user is to say when it matters: a negative layer whose openings
leave nothing of it in a zone is now a **warning that names the layer and the
setting**, not a line of routine chatter.

## Update 2026-08-14 (round 63) — the picture beside Allegro's, and three faults

The user built the demo board and put our result next to Allegro's own 3D. The
arms were wrong: two floated clear of the board, one was never bent. Three
separate faults, and none of them would have been found by any check we had.

### 1. What `alpha`, `beta` and `ccw` mean on an arc — settled by measurement

They **bound** the arc; `ccw` says which **end the contour enters it by**, not
which way the sweep runs. Both halves read it as a direction, which turns a 90°
corner into the 270° arc the long way round.

The proof is joint continuity — a contour has to close:

| contour | worst joint, old reading | new reading |
|---|---|---|
| board outline | 5.657 mm | **0.000** |
| FLEXI | 19.799 mm | **0.000** |
| CONN_FLEXI | 12.728 mm | **0.000** |
| the other five | 0.000 | 0.000 |

and every affected arc came out at 270° where the design draws 90°.

**The board body was safe all along**: `ConnectEdgesToWires` reorders and
reverses edges as it likes, and `GC_MakeArcOfCircle`'s sense flag only reverses
the parametrisation, so OCC got the right span anyway. `contour_points` did not,
so every question about a zone's SHAPE was answered from a self-intersecting
polygon — FLEXI read as 2676 mm² against its true 1240. With the fix the zones
tile the board exactly: 19484 mm² of zones against a 19481 mm² outline.

### 2. Which side of a strip a piece is on has to be asked at the seam

`side_of` judged by the piece's extent, with a nearest-vertex tie-break. The
main board is wide enough to have material on **both** sides of a strip's
infinite band, so BEND_1's near edge was sewn to the FAR panel: the strip bent
about its far edge and slid the wrong way, and the arm came away from the board
by 23.8 mm. The two pieces touch, so the closest point between them lies on the
shared edge, and that edge is one of the strip's two sides — exact and local.

Note what hid it: for a **180°** bend the far panel still lands correctly
(rotating 180° about the far edge after sliding forward equals rotating 180°
about the near edge after sliding back), so only the curved ribbon flew off.

### 3. The cutters were placed from the origin, not from the board

`_slab` ran half the board's diagonal either side of `n * lo` — the foot of the
bend's near plane **measured from (0, 0)**. `_band_face` did the same. On this
board BEND_1's foot is at (16.9, −17.2) while the arm it cuts is at (140, 90):
163 mm along the bend line against a 102 mm half-span, so the cutter missed the
board completely and the bend was built out of nothing. **Silently** — an empty
cut is indistinguishable from a shape that is not in that region.

Any board drawn away from the origin loses bends this way, the further out and
the more diagonal the worse. Both cutters now take their across-extent from the
shape they are cutting.

### Measured, same board, same settings

| | volume | vs flat |
|---|---|---|
| flat | 22679.233 mm³ | |
| folded, before | 22535.752 mm³ | 99.37% — BEND_1 missing |
| folded, all three fixed | 22673.364 mm³ | **99.97%**, six bends on true cylinders |

### `_seam_gap`, and why it exists

A fold is CONTINUOUS: both edges of every strip have to land where the piece on
that side puts them. Two points per strip, checked on every build, warned about
if it fails. **It is the only check that would have caught fault 2** — the volume
was right, no region was claimed twice, every suite passed, and the model was
still broken. Round 62 added the "nothing claimed twice" invariant for the same
reason; this is the other half of it.

### What to remember

**Put the two pictures side by side.** Three faults, one screenshot. Volume,
area and continuity all agreed with each other and all agreed the model was
fine; only the shape said otherwise.

**"Sized from the shape, placed from the origin" is a whole class.** Both
cutters had it. Anything that builds a helper solid from a bounding box should
be read with that question in mind.

## Update 2026-08-14 (round 62) — the fold, rebuilt on pieces instead of half-planes

The user put `cadence_demo.json` in `failed/` — Cadence's own rigid-flex demo
board, 7 zones, 6 bends, three arms leaving the middle in three directions — and
`plan_fold` died with `KeyError: 1`. Three faults came out of it, each hiding
the next.

### 1. The crash: a containment test that was not antisymmetric

`contains(outer, inner)` asked only whether one strip lies beyond another
**along that one's normal**. Nothing makes that a partial order. BEND_5 at
(93, −49) and BEND_1 at (143, 93) have near-perpendicular normals and sit 135 mm
apart measured one way, 66 mm the other — both far past either strip, so **each
contained the other**:

```
[1] BEND_5  above=[0,2,3]  parent=3
[3] BEND_4  above=[0,2]    parent=2
[2] BEND_1  above=[1]      parent=1      cycle: 1 → 3 → 2 → 1
```

The loop then walked `sorted(key=len(above))`, which assumes a parent always has
fewer ancestors than its child — true only of a transitive relation — and
reached a bend whose parent had not been placed. Note what the KeyError saved
us from: `ancestry()` walks `parent` with `while k is not None`, so a cycle
reached that way is an **infinite loop**, and a hang in a GUI build is worse
than a crash.

### 2. A real bend thrown away

BEND_2 was being dropped as "cannot be read". It and BEND_1 are both on the
FLEXI arm, **perpendicular to each other** at a corner, 33.9 mm between centres,
sharing no material. The clash test compared two *bands* along one normal and
saw 9.19 mm between strips 8.3 and 9.9 mm wide. A strip is a **rectangle** — as
wide as its developed length, as long as its bend line — so the test is now a
separating-axis test over the four edge directions. Touching still counts as
separated, which is the ring case. All six bends fold now.

### 3. What the first two were hiding: the model itself

With the crash fixed the board built — and the folded body weighed **114.7% of
the flat one**. A fold cannot add material. Sampling the outline at 1 mm:

| | |
|---|---|
| claimed by exactly one region | 15026 points |
| claimed by two | 3051 |
| claimed by three | 1976 |

and worse, **MAIN_PCB — the held panel — fell inside "panel after BEND_5"**.
A region was an intersection of half-planes, and a half-plane crosses the whole
board: "beyond BEND_5", whose normal is diagonal, sweeps across the LCD arm
180 mm away and over the main board too.

**Bounding every panel by every other bend was tried and is worse.** Double
claiming goes to zero and 42.7% of the board then belongs to no region at all —
two arms that each lie beyond the other are excluded from both. Neither reading
is a tuning question: half-planes cannot say which ARM a point is on.

### The rebuild

Which arm a point is on is **connectivity**. So `_cut_into_pieces` cuts the flat
outline by the bend strips with OCC and the connected faces that fall out are
the panels — 7 panels and 6 strips on this board, in 0.14 s. From there:

- The **held** piece is the one the anchor lands on (nearest, if the anchor is
  off the board — the origin often is).
- A **walk outwards** folds each strip away from whichever side is already
  placed. No containment, no parent tree, no ordering, no cycle possible: a
  piece is placed when it is reached.
- A strip's neighbour may be **another strip** — a flex rolled into a ring is
  two 180° areas meeting along a line with no panel between them — and the walk
  crosses those the same way.
- A bend is oriented **per bend**, by the side the walk arrives from, instead of
  once globally against the anchor.
- A piece nothing reaches is an **island**: left where it is, named in the log.

One trap inside it: a band is infinite across its own direction, so
`outline AND band` comes back in several pieces — BEND_5's band also clips the
LCD arm. Only the piece the bend **line** is in is that bend's strip.

Measured, same board, same settings:

| | volume | z extent | STEP entities |
|---|---|---|---|
| flat | 22679.233 mm³ | −1.66 … −0.05 | 18211 |
| folded, half-planes | 26012.911 mm³ (114.7%) | −24.05 … 105.96 | 107193 |
| folded, pieces | 22535.457 mm³ (**99.4%**) | −24.03 … 20.62 | 31850 |

The overlap is measured on every build now and warned about if it is ever not
zero. It should not be — but silence is what made this cost a round.

### The legend, folded piece by piece

The full build with silkscreen had not finished in 23 minutes. `apply()` cut the
**whole legend compound** — 2287 polygons, tens of thousands of faces — against
every region in turn, and none of the cheap rejections could fire because that
compound's bounding box covers the entire board. Folded one glyph at a time, a
glyph is a millimetre across: it lands in one piece, is rejected by every other
on its bounding box, and needs no boolean at all unless it straddles a bend.
`_cut_to_region` now takes the region rather than its face, caches the piece
bounding box, and skips the boolean entirely when the shape is wholly inside the
piece — which needs `_crosses`, because four corners inside a polygon does not
mean the box is (a piece with a notch in it).

**The whole board, folded, with both legends: 107 seconds.** 2287 silkscreen
solids, 1.96M STEP entities, 95 MB. Against "not finished in 23 minutes".

### Also

- A stackup layer whose drawn shapes lie entirely outside a zone — a stiffener
  that is only on the flex arms — produced an **empty part** rather than none:
  `IsNull()` does not catch an empty compound, the round-61 lesson in a second
  place. Skipped now, with a line saying where.
- `point_on_polygon` is new. Half-planes had EPS for a board corner or the seam
  between two pieces; polygons need the same allowance spelled out, and without
  it `transform_at` at a corner of the board returned the identity.
- The stackup read was **cross-checked against the user's `Cadence_Demo.tcfx`**:
  every named layer of PRIMARY matches to the micron. The exporter is reading
  the cross-section correctly; nothing in this round was a stackup problem.

### What to remember

**A model that cannot represent the answer will produce a confident wrong one.**
Both the cycle and the double-claiming were the same mistake seen twice: a bend
line treated as a cut across the whole board rather than a segment on one arm.
The crash was the lucky part — it made someone look.

**Check the invariant, not just the tests.** Every existing suite passed on the
half-plane model; the board it could not describe was not in the corpus, and no
test asserted "no piece of the board is claimed twice". That check is now in
`plan_fold` itself.

## Update 2026-08-11 (round 61) — the whole-board file had no board in it

The user put two intermediates from one board in `failed/`: `8231-a2.json` (the
whole board) and `8231-a2_bom.json` (the variant). The variant built normally;
the full board built **without the board body**, and said nothing about it.

### What the data said, before any code was read

The two files differ in exactly three things: the `full_board` marker, the
`name`, and `pcb.edges` — **26 contours against 24**. Every component section is
byte-identical, so the variant list had removed nobody. And:

```
edges[24] == edges[22]        the slot at x 2.5..3.0,  y 13.6..15.4
edges[25] == edges[23]        the slot at x 26.0..26.5, y 13.6..15.4
```

Byte-identical repeats, at the end of the list. Measured through
`make_board_geometry`:

| input | solids | volume |
|---|---|---|
| the full board as delivered (26) | **0** | 0.0 |
| the variant (24) | 1 | 724.1812 mm³ |
| the full board minus the two repeats | 1 | 724.1812 mm³ |
| the variant plus **one** repeat | **0** | 0.0 |

So one duplicated cutout anywhere in the list erases the entire body, and the
deduplicated full board is the variant to the last digit.

### Why the duplicate is there — a destructive append on a shared list

`makeVariant3dIntermediates` calls `makePcbContour( dsn )` **once** and hands the
result to every `create3dIntermediateFormat` of the run. That routine did:

```
when( cadr( edgeCuts )  cuts = cadr( edgeCuts ) )    ; an ALIAS, not a copy
...
tconc( cuts symbolReturnPinHoles() )                 ; tconc appends IN PLACE
```

`tconc` mutates the structure it is given, so each export left its pin holes in
the caller's list and the next export started with them already there. The
comment above it said "reset base board contour"; nothing was reset.

**The consequence is bigger than the reported symptom.** The variants are
written in a loop and the whole-board file last, so:

| file | pin-hole copies |
|---|---|
| variant 1 | 1 — correct |
| variant 2 | 2 |
| … | … |
| whole board | n+1 |

This board has one variant, which is why only the full-board file was wrong. **A
board with two variants would have had a broken second variant and a working
first one**, which is a far more confusing thing to be handed. The arithmetic
also matches exactly: this design has two through-hole pins, both on slot
padstacks, and `symbolReturnPinHoles` returns them as ONE string, so one leaked
append = the two extra contours, 24 → 26.

`edges` (`car( edgeCuts )`) is only ever read, so the outline was never affected.

Fixed by copying: `foreach( baseCut car( cadr( edgeCuts ) ) ... )` builds a fresh
tconc per export.

### Why nothing said a word — `IsDone()` and `IsNull()` both pass

`BRepAlgoAPI_Cut` with two coincident prisms in the tool compound returns
`IsDone() == True` and a shape that is **not null** — a COMPOUND with **0 solids
and 0 faces**. The board path checked exactly those two things, so an empty
result was accepted as a board and the STEP was written with components, legend
and nothing else. Confirmed at the minimum: board minus a compound holding the
same slot prism twice, and nothing survives.

`bend.py` had already learned this — `_cut_to_region` calls `_is_empty` after
every `Common` — but `core.py`'s board path had not.

Two guards now, on the Python side:

- **`board_cutouts( contours, log )`** returns `edges[1:]` with exact repeats
  dropped and a line in the log. Exact only: cutouts that merely *overlap* are
  ordinary and OCC handles them, so a near-miss (`r=1.0` vs `r=1.0000001`) is
  kept. This is what makes the intermediates already on people's disks build.
- **`has_solid( shape )`** after the board's boolean, and after both stackup
  fuses, whose `IsNull()` tests could be fooled the same way. A boolean that
  produces nothing is now a `StepBuilderError` naming `pcb.edges`, not a silently
  missing part.

### The rest of the review

- **`S3D_NegativeLayers` had no default to be restored to** — the round-42 trap,
  still live. `S3D_ExportFullBoard` right beside it carried the restore and a
  comment explaining why; the negative-layer list did not, so a board whose
  config named `negativeLayers` left that list in place for every board exported
  afterwards in the same Allegro session, and a coverlay would be read as
  material or as an opening depending on what had been exported before it. Now
  `S3D_NegativeLayersDefault` exists and is restored.
- **Both restores moved above the `isFile( t_file )` branch.** Restoring inside
  the branch that parses the config covered "the key was removed from the file"
  but not "there is no config file at all" — that case kept the previous board's
  values. They now sit with the local defaults at the top of `s3dSilkConfig`.
- **The `format_version` audit check has been repaired.** Round 60 found it had
  never run — the exporter writes the line inside a SKILL string, so the file
  says `\"format_version\": 7` and the regex anchored on a bare quote. It runs
  now, and the README states the version (and that every older one still builds).
- Checked and left alone: every other `tconc` site (all of them build their own
  structure), `s3dSymbolsToExport` (reads the variant table, mutates nothing),
  the silkscreen structure that is likewise collected once and shared (read
  only), `worker.py`'s per-job failure isolation, `resolve_json_jobs`,
  `output_stem`. `pyflakes` over `stepbuilder/`, `tests/` and `tools/` is clean.

### Tests

- `tests/test_dupcuts.py`, new: which contours `board_cutouts` keeps, the board
  volume with and without the repeats, the error when a boolean genuinely leaves
  nothing, `has_solid` on a real solid and on an empty compound, and the
  per-layer path.
- `tests/test_variant_path.py` section [9] transliterates `tconc` and runs a
  whole session through both versions — the aliased one reproducing 1, 2, 3
  copies across three files, the copied one giving all three the same list — plus
  a source check that the alias is gone. The negative control matters here: it
  is the only way to be sure the model is of the bug and not of the fix.
- 22/22 green in 60 s.

### What this round is worth remembering for

**Ask for the file.** Two JSONs from one board settled a "why does this board
fail" question before any code was opened, because the difference was 26 against
24 and the two extra entries were byte-identical to two others. The standing
lesson from the arc-sign rounds, again.

**A boolean that reports success can still have produced nothing.** `IsDone()`
is not "it worked", and `IsNull()` is not "it is empty". Count the solids.

**A list computed once and reused is shared, and SKILL's list operations are
destructive.** The first consumer sees the truth; everything after it sees the
accumulation. When exactly one of several outputs is wrong, ask what order they
were written in.

## Update 2026-08-07 (round 60) — the docs claimed a control did nothing

The user, reading QUICKSTART: "Body stitching acts only on multi-stackup /
rigid-flex" — **but it acts on an ordinary board too.** They are right, and it
has been true since **round 33 (2026-07-25)**, which made the ordinary case a
case rather than an exception: a board with no zones gets its outline as one
implicit zone on its single stackup, and all three modes apply. `test_plain_modes.py`
has asserted exactly that ever since, and it passes. Only the documentation was
never updated.

**The claim had been copied into four places**, which is why it survived: the
README table, both halves of QUICKSTART, `_comment_boardMode` in
`simple3d_config.json`, the `--board-mode` help in `__main__.py`, and the
`board_mode:` paragraph of `generate()`'s docstring. All corrected, each also
gaining the one caveat that IS true — the two non-solid modes need the stackup
layers, so a pre-format_version-6 intermediate warns and falls back to one solid.

**Why `tools/audit_docs.py` did not catch it, and still would not.** It checks
that *names* line up: CLI flags both directions, config keys, GUI labels
verbatim, the assembly labels, two defaults. Every one of those passed here,
because "Body stitching" existed, `boardMode` existed and the modes were spelled
right. What was wrong was a **claim about scope**, and nothing mechanical can
tell a true claim from a false one. So the rule is procedural rather than
automated: **when a fix widens or narrows where a feature applies, grep for the
old scope wording — in the docs, in the config comments and in every `help=`
string — before closing the round.** That is what round 33 skipped.

One hole in the audit was found while reading it and is worth knowing rather
than fixing blind: its `format_version` check greps the `.il` for
`"format_version"`, but the exporter writes that text escaped
(`\"format_version\": 7`), so the regex never matches and the check has never
run. Left as it is for now — it is a real gap, not a false pass.

### Everything else the sweep turned up

Checked the rest of README + QUICKSTART against the code, control by control and
claim by claim. Wrong, and fixed:

- The ZIP-install note still told the reader to point **`S3D_ScriptDir`** at the
  wrapper folder. That variable was emptied in round 59; it is `SIMPLE3D_DIR` now.
- `settings.negativeLayers` was documented in the config as matched **"as a
  prefix"**. `s3dLayerIsNegative` walks the whole string — substring, over the
  name *and* the layerFunction. The README already said substring; the config
  comment did not.
- "finds the design's `rev/cad` folder" omitted the fallback: with no `cad`
  sibling the JSON is written beside the `.brd`, and `s3dResolveCadDir` says so
  in the console.
- The variant paragraph ended "absent from the list, it is not — whatever
  `NO_STEP_EXPORT` says", which reads as a contradiction of the sentence two
  paragraphs above and leaves out the one property that *does* override absence.
  The rule, from the code: `NO_STEP_EXPORT` → the variant list → unless
  `ALWAYS_STEP_EXPORT`.
- "Three consequences:" over a list of four.
- "20 test suites" — there are 18, plus the three mechanical checks, 21 jobs in
  `run_all.py`.
- `--step-dir` and the `;`-separated `STEP_DIR` were undocumented (the audit
  exempts them as launcher plumbing; they are usable from the command line).

Not wrong, checked and left: the eight board themes, the two silk colors, the
control-by-control window table, `DEFAULT_FLAT_HEIGHT` 0.001, the thickness
example, the assembly node names, the mechanical-part rule, the two rejected
`Variants.lst` shapes, the rim greying out outside *Solid*.

**QUICKSTART is ~9% shorter** for more content: the reasons moved out to the
README, which is where they were already written in full. 21/21 suites green.

## Update 2026-08-05 (round 59) — the last paths out, and a review of the whole

The user, on reading round 58: if there is an env variable now, **why are the
absolute paths still in the .il files?** Fair, and the answer was "because I
left a fallback", which is not good enough - a fallback in a tracked file is
still one installation's path shipped to everyone.

**Six places held one, and only one of them mattered.** `simple3d.il` had the
`S3D_ScriptDir` literal (the real one), two `load()` examples and the
`SIMPLE3D_DIR` example in comments; `simple3d_config.json` had `gui.stepDirs`;
`tools/s3d_userprop_test.il` had a `load()` example. The literal is now `""`,
the config ships `[]`, and the examples say `d:/Tools/Simple3D` - obviously an
example rather than someone's disk.

**Two sources, in order, and a refusal.** `SIMPLE3D_DIR` first, because someone
who sets it means it. Then the folder this file was loaded from, captured at
load with `get_filename( piport )` - core-SKILL names this project has not
verified, so it is wrapped in `errset` and can only ever be the SECOND answer.
When neither answers, the export prints what to set and stops: it would not
find its own Python package anyway, and every later failure would be less
obvious than this one. `s3dFolderOf` cuts the folder by SCANNING for the last
separator rather than with `parseString`, for the round-47b reason - parseString
collapses separators and would turn a UNC path into a relative one.

### What the review turned up

Read: everything that changed since round 53, plus a pass over the load-time
statements of both `.il` files (they define and assign, nothing else - the
round-54 rule holds). Two real findings, both fixed:

- **The local settings file was accumulating the WHOLE `gui` section.** It
  worked, but it pinned every key at whatever the installation had on the day,
  so an improved default upstream could never reach it again - which is half of
  what splitting the file was for. It now writes **only what differs from the
  shipped default**, which also means setting a value back to the default
  removes it from the local file rather than freezing today's value forever.
- **`_freeze_inputs` could be entered twice**, and the second entry would record
  "disabled" as the state to restore - leaving the window dead after the build.
  Nothing reaches it today (a second Generate cannot start while a worker is
  alive), and the guard is one comparison.

Everything else came back clean: 21 suites, pyflakes over `stepbuilder`,
`tools` and `tests`, the four SKILL checks, the docs audit, and a grep for
TODO/FIXME markers (none outside a comment about `\uXXXX`).

### The one-time step for an existing install

The tracked config no longer names a model folder, so an installation that
copies the new file over the old one and has no local file yet will have to
set **STEP files** once in the window. Closing it writes
`simple3d_config.local.json`, and it never has to be done again.

## Update 2026-08-05 (round 58) — settings out of the tracked file

The user, thinking about pulling updates from GitLab: the absolute paths - the
model library and where the scripts live - sit in files git tracks, and an
update would walk over them.

**The problem was bigger than the two lines, and saying so was the useful part
of the answer.** `simple3d_config.json` is not merely a tracked file with a path
in it: **the window rewrites it on every close** - window geometry, last paths,
colours. A tracked file that the tool itself edits every session conflicts on
every update whatever the user does, and every commit carries someone's window
position. Their own workflow hid it: they hand-copy into an install, so the file
git sees is not the file the window writes. The moment that copy step ran the
other way, their settings would go.

### What was built (their choice of the five offered)

**A local file over the tracked one.** `simple3d_config.json` = shipped
defaults, still tracked, still the thing that gets improved. `simple3d_config.
local.json` = this installation's overrides, gitignored. Merged on read, key by
key, local winning; **the window writes only the local file**. Both halves merge
identically - `s3dJsonMerge` in SKILL, `_merge_config` in Python - and
`tests/test_config_merge.py` runs the two over the same ten cases and compares
them, because a merge that disagrees between the halves is a setting that
applies in one and not the other.

Three decisions inside it:

- **Objects merge; anything else is replaced whole.** A list that could only be
  extended is a list you cannot shorten - the local file has to be able to say
  "only this one folder".
- **Presence of a key decides, never truthiness.** JSON `false` parses to nil in
  the SKILL reader, so `when( value ... )` would silently drop exactly the
  overrides that switch something off. Same trap as `defineAlwaysExportProp`
  two rounds ago, and it now has a test each side.
- **The "never write a file you did not understand" rule had to be said twice.**
  The window now validates one file and writes a different one, so a local file
  hand-edited into invalid JSON needed its own guard - it holds the user's
  settings, and overwriting it with whatever the widgets happen to show is the
  exact failure the original rule exists to prevent. Refusing on the BASE file
  too is deliberate: with it unreadable the widgets hold defaults, and writing
  those as local overrides would mask the base permanently once repaired.

**And `S3D_ScriptDir` from the Allegro environment**: `axlGetVariable(
"SIMPLE3D_DIR" )`, read in the user's own `pcbenv/env`, with the literal left as
the fallback so an install that works keeps working. It cannot move into the
config - it is what finds the config - and a SKILL file cannot ask where it was
loaded from, at least not through anything in the verified API list. The
resolution had to move ABOVE the `s3dLoadSettings()` call, which meant moving
that call: reading the settings before the folder is settled reads the wrong
file.

### The tests moved, and that was the point

Four suites asserted that settings land in the tracked file. They now assert the
opposite, which is the stronger claim: **the tracked file is byte-identical
after a save**. Two of them also needed the leftover local file deleted at
start-up - it survives a run, and a fixture that quietly inherits the previous
run's answer is worse than one that fails.

**Not verified in Allegro yet**: the SKILL merge and `SIMPLE3D_DIR` on a live
board. The Python half and both merges are covered by tests; 21 suites green.

## Update 2026-08-04 (round 57) — the window while it works

The user: pressing Generate leaves every control available, and they should not
be; and there should be a Cancel, or the button should at least change.

**Why it mattered more than it looked.** `_snapshot()` freezes the settings the
moment Generate is pressed - deliberately, so a later edit cannot change a build
in flight. The window then left every control live, which made that safety
invisible: you could change the board color mid-build and watch the old one come
out. `_set_busy` was disabling the children of one frame, which was the Generate
button and nothing else.

**The freeze remembers, it does not assume.** Half this window is greyed out by
its own rules at any moment - the rim color outside *Solid*, a side's silkscreen
layers when that side is off, the layer swatches in *Solid*. Re-enabling
everything at the end would switch those back on, so each widget's own `state`
is recorded and restored exactly. Measured on the real window: 51 controls, 6 of
them already not-normal, all 51 restored byte for byte.

Two things stay live on purpose: the **log**, which is what you read while you
wait, and the action button.

**Disabled is not always a look.** The user came back with the two widgets that
proved it: a `tk.Canvas` swatch keeps its colour whatever its state, and a
`tk.Text` refuses edits while keeping its white field - so the colour squares
and the STEP-paths box went on looking live in a window that had greyed out
around them. Both are now dimmed by hand and restored from what was recorded:
the swatches to `INACTIVE_SWATCH`, the same grey the window already uses for a
swatch that does not apply, and the paths field to whatever the THEME says a
disabled entry looks like (`style.lookup("TEntry", ..., ["disabled"])`) rather
than to a grey picked to match this Windows and no other. The swatches also lose
their hand cursor, and their click handlers ask a `_busy` flag, since a Canvas
has no state to refuse with.

**One button, two jobs.** Cancel beside a live-looking Generate would have been
the second confusing thing, so the button relabels. Cancelling is
`Process.terminate()` - a real kill, because OCCT spends minutes inside a single
boolean and nothing in there checks a flag. What it costs is said in the log
rather than hidden: a file being written at that moment can be left half
finished. `_check_worker_alive` had to learn about it too, or a deliberate kill
would have been reported as a crash, with the access-violation advice attached.

`tests/test_gui.py` [9] pins all of it headless, including a stand-in worker for
the cancel path: spawning a real one from a test re-imports the test module on
Windows and re-runs the file.

**Not verified in the real window yet** - it is Tk, tested headless, and the
last word is the user's.

## Update 2026-08-04 (round 56) — the whole board, beside the variants

The user, right after round 54 landed: with a `Variants.lst` present there must
still be a way to get **every** component except `NO_STEP_EXPORT`. Same need as
`ALWAYS_STEP_EXPORT` and a different scale - that property answers it part by
part, this answers it for the board at once.

**Where the control had to go, and why not the window.** The filtering happens
in SKILL, before Python starts: what a variant does not install is not in the
JSON, so no checkbox in the window can bring it back. The user asked for a knob
in the dialog and got one, but it is a different knob - see below.

**The export path already existed.** It is the no-variant branch:
`s3dSymbolsToExport( nil nil )` -> `<design>.json`. It simply was not reached
with a variant table present. So the change is that branch running again after
the variant loop, under `settings.exportFullBoard` (default true), which is
about six lines.

Three details that are not obvious:

- **The name.** `<design>.json` cannot collide with `<design>_<variant>.json`,
  and it is the name the no-variant export already uses. It also retires the
  round-47 nuisance where a stale `<design>.json` from an older export sat in
  the folder and was quietly built as an extra STEP: that file is now written
  every time and means something.
- **The marker, not the name.** The file carries `"full_board": true` and the
  window reads that. Telling the two apart by filename is a guess - a variant
  may be called anything, including something that reproduces the design name.
  `core.py`'s `_reserved` tuple gained the key, per the comment in the SKILL
  writer that says every top-level key must be listed there or the reader walks
  it as if it were a component.
- **`create3dIntermediateFormat` takes the flag as an ARGUMENT**, not off a
  global. A global read at write time is the round-42 shape: it would describe
  whatever the previous call set, the moment this one forgot to.

**The knob in the window is honest about what it does.** *Build the full-board
file too* decides whether a queued FOLDER includes that file in the batch. It
cannot ignore variants, so it does not claim to. And a file the user pointed at
directly is built regardless, with a log line saying so: a checkbox that
silently refuses the one file you selected is worse than one that appears to do
nothing.

`S3D_ExportFullBoard` is reset to its default **before** the config is read,
which `S3D_NegativeLayers` beside it is not: these files load once per session,
so a key deleted from the config would otherwise leave the last board's value in
place. Round 42 again.

`tests/test_variant_path.py` [8] pins the SKILL side by source and the reader by
behaviour - four real files, one marked, one variant, one written before the key
existed, one not ours at all.

**Not verified in Allegro yet**: that the extra file appears on a board with
variants. The Python half is verified by test.

## Update 2026-08-04 (round 55) — the README halved, the changelog moved out

The user: the README is very long, the quick-start too short, and a person using
the tool has no reason to read how it was built. So the README was rewritten at
**1004 lines against 2079**, bilingual as before.

**What came out:** the measurements kept as evidence for decisions already made
(the silkscreen size table, "117 faces -> 112 in 0.08 s", per-layer volumes on
the test board), the checks-and-tests section, the zero-width diagnostics in
detail, the C++ porting history, the three bend constructions written out one by
one. **What stayed: every "why".** Parts sit on the mask because solder lifts
them there; zones align on copper or the board tears at every boundary; the
solid legend is not fused because fusing makes the file *larger*; the variant
list governs anything with a refdes because a refdes is what makes a part
nameable in it; `k = 0` for a ring because Allegro draws bend areas at the inner
arc; the anchor is the origin because Allegro's own anchor point never reaches
the file.

**The changelog moved to `CHANGELOG.md`** rather than into this memo. They are
different documents: a changelog answers "what changed in the version I just
copied", which a user needs; this memo answers "why, and what was tried", which
only work *on* the tool needs. Folding one into the other would have buried it
in five thousand lines.

`tools/audit_docs.py` is what made the swap safe rather than hopeful: the first
draft dropped 17 config keys and a default, the audit named all 18, and they
went back in as a compact block. The short README was checked by temporarily
standing in for the real one, so the audit ran against it exactly as it will
from now on.

## Update 2026-08-04 (round 54) — ALWAYS_STEP_EXPORT, and where a property lives

Round 52 left a case with no answer, and the user found it: **pads for soldering
wires**. They carry a refdes, they carry a STEP model shaped like the pad, they
are not in the BOM and therefore in no variant — and since round 52 that means
they are exported nowhere. But a draughtsman wants them visible, especially on a
board with no silkscreen. The only way out was to put them in a variant's BOM,
which is wrong on the drawing that matters.

**No rule can fix this, and it is worth being clear why.** A wire pad and a
MOLEX housing (`A1`/`A2`, round 49) are the same object in the database: refdes,
STEP model, no BOM line, named in no variant. The housing must vanish with its
connector; the pad must not. The difference is intent, and intent has to be
written down. So: a property.

### The property is not Allegro's, and that changed the design

I assumed `NO_STEP_EXPORT` was ours and that whatever created it would serve
again. **It is one of Allegro's own** — the user corrected this, and their
`axlDBGetPropDict('user)` shows ten user properties, none of them ours. So
`ALWAYS_STEP_EXPORT` had to be *created* before it could be attached at all: not
from the Properties dialog, not from SKILL, not at all.

`tools/s3d_userprop_test.il` was written for the user to run by hand before any
of this was coded — **the only file in the project that writes to the design**,
and it says so in its header. On their live board it answered every question in
one go: the dictionary took the name, `axlDBAddProp` was accepted, and
`axlDBGetProperties` handed it back on the symbol. Allegro also printed,
unprompted, the sentence the documentation had already promised:

> *WARNING* (axlDBAddProp): Adding Boolean property "ALWAYS_STEP_EXPORT",
> despite 'nil' being provided as the value. To make the property 'False'
> instead, call axlDBDeleteProp() to remove it.

which is why the property is BOOLEAN and why presence is the whole test — and
why "un-mark" is a delete, not a false. The user then confirmed the part that
mattered most: with the dictionary entry in place, the property attaches
**correctly from Allegro's own Properties dialog**, arriving as true.

### Where it is created, and why in two places

The user asked for it at load of `simple3d.il`. That is done — and it is also
done at the top of every export, because **a property dictionary belongs to a
DESIGN, not to the installation** (`axlDBGetPropDict`: "entries in the current
design"). Defining it once at startup would reach only the board that happened
to be open at that moment; a board opened afterwards would have the export
reading a property nothing could attach. Both calls read the dictionary and
return when the entry is there.

A design-open trigger would be tidier still, but the supported trigger names
have to be read from a live session (`axlTriggerSet(nil nil)`) and this project
does not bet on unverified names — round 47 lost that bet on `axlDirName`.

`allegro.defineAlwaysExportProp` (default true) turns the creation off entirely,
because **creating a dictionary entry modifies the board** and someone will not
want every design they open marked as changed. The export still reads the
property wherever it is already defined; reading was never the part that wrote.

### The rule

`s3dAlwaysStepExport` mirrors `s3dNoStepExport` exactly — symbol, component,
compdef — so marking a library part covers every instance on every board. In the
cond it is tested **last**, in the variant branch's `&&` chain: never outranks
always, and the property read is reached only for a symbol the variant was about
to drop. The console reports the kept ones by count and variant, and
`probe_variants.il` now prints them by name beside the dropped ones.

`tests/test_variant_path.py` grew four decision cases and a [6b] block that pins
the SKILL side: created as BOOLEAN, called at load AND at export, switch honours
a literal `false` (the JSON reader maps `false` to nil, so presence has to be
tested with `s3dJsonHas` - a plain truthiness test would read "off" as "unset"
and turn it back on).

### And then it did not work, for a reason this file already warned about

The user reloaded, opened a board, exported - and `axlDBGetPropDict('user)` still
did not list the property. The cause:

```
prog( ( dict ( found nil ) name made )
```

**prog locals are bare symbols.** The `(var value)` init form is `let`-only, and
prog rejects the whole procedure with "local vars must be symbol" - at CALL
time, so the file loads clean. Both call sites wrapped it in `errset`, so the
failure was silent and the export looked entirely normal. `s3dPreflight`, a
hundred lines above in the same file, carries a comment about exactly this trap.

Three things came out of it, and the fix is the least of them:

- **`errset` around a call must not swallow the diagnosis.** Both sites now
  report a fault, which is possible to tell from a legitimate nil because errset
  returns nil ONLY on error - a real nil comes back as `(nil)`.
- **`tools/skill_checks.py` grew a fourth check**: every `prog(` has its local
  list read, and an init form in it fails the file. It carries a **self-test**
  that runs before the real files - a known-bad fragment must be caught, a
  known-good one must not, and a `let` with the same form must not, since there
  it is legal. A check written after the escape it should have prevented is
  worth nothing unless it is proven to fire.
- The suite's own assertion "it is defined at load time" then failed on the
  reworded call site, which is the test doing its job; it now pins both call
  sites by position, that neither swallows a failure, and that the locals are
  bare.

### Then it crashed the editor, and what that settled

Installed, the batch made Allegro crash on startup, repeatedly, offering to
recover a `.sav`. The load-time call went out immediately - and so did the OTHER
load-time action the same batch had added, round 53's `pcreCompile` for the
control-character scan, which is now compiled on first use. Not because either
was proven guilty: because with two new load-time statements and no way to run
SKILL here, leaving one in would have wasted the user's next attempt.

**The rule taken from it is blunt and worth keeping: loading these files defines
procedures and sets variables, and does nothing else.** A tool that can stop the
editor from starting cannot be debugged from. `tests/test_variant_path.py` pins
it - no call to `s3dEnsureAlwaysProp` after `axlCmdRegister`, and the regex
compiled lazily.

The user then supplied the likely cause, and it is worth writing down because it
is a property of their Allegro rather than of this code: **started from its own
icon, the editor sometimes comes up on an empty placeholder instead of the
previous board.** The API answers every question about it, and editing it
produces errors that make no sense. That is almost certainly what the load-time
version was writing a property dictionary entry into.

So `s3dRealDesign()` now asks the only question that separates the two: is there
a **drawing file on disk** behind this design (`axlGetDrawingName` +`isFile`)?
A name proves nothing; `axlCurrentDesign` answers for the placeholder too. It
guards the property creation, and the export command now refuses such a design
outright with a message naming what it is - previously it would have gone on to
export a board that is not there.

### The open trigger, now that its name is known

`axlTriggerSet(nil nil)` in the user's session: **open save close exit menu
xprobe select window xsection**. So `s3dOpenTrigger` is registered on `open`,
TriggerClear-then-Set like the menu one, and the property is defined as soon as
a board is opened rather than after the first export. Registering a trigger at
load is not doing work - it asks to be called later, when the database is in a
state to be written to - so it does not breach the rule above.

The trigger takes one argument (the documentation: a function of any other shape
is simply not called), keeps its work to a dictionary read, and is wrapped in
`errset` so it cannot stop a board from opening.

**Verified live by the user, all of it.** In order: the property appeared at
export time; they attached it to the symbol they wanted through Allegro's own
Properties dialog; the part then came through in a variant that does not list
it; and after the trigger was added, the `open` trigger and the refusal to
export a design with no board file behind it were confirmed too.

Round 52's rule is confirmed by the same session from the other side: the
problem the user brought - solder pads vanishing from every variant - **is** the
refdes rule doing exactly what it was built to do, on a real board.

## Update 2026-08-04 (round 53) — full review, and all seven findings fixed

A read of the shipped code as it stands: `simple3d.il` and `core.py` end to end,
`worker.py`, `__main__.py`, the config and queue halves of `gui.py`, the
export rule and JSON writer of `makeVariant3dIntermediates.il`, plus pyflakes
over the whole Python side and the docs audit. Seven findings, all fixed in this
round. The two that mattered:

**1. A model file that was present but unusable took the whole board down.**
`core.py` treated a MISSING file gently - log, `missing_step_files`, carry on -
but raised `StepBuilderError` when `ReadFile`, `Transfer` or the free-shape diff
failed. So one file locked by another application, one zero-byte copy, one
dialect OCCT declines, and the export of that board was over. Against the
project's own rule, written three feet away in the same file: *one malformed
glyph must not cost the whole board.* Now the three failures are caught
(including anything OCCT throws), reported with the reason and the path, and the
component is skipped like a missing one.

They land in a **new** `unreadable_step_files`, deliberately not in
`missing_step_files`: `_report_embedded_only` tells the user to recover the model
from the board's own copy, which is exactly wrong advice for a file that is
sitting right there. `tests/test_index.py` [9] builds a board with one good model
and one junk file and pins all of it - board built, good part placed, bad part
skipped, listed as unreadable and NOT as missing.

**2. `s3dJsonQuote` escaped four characters and needed six.** `"`, `\`, tab and
newline were handled; a carriage return - or any other control character - went
into the file raw, and JSON forbids those in a string. One of them anywhere in
any name makes the WHOLE intermediate unparsable, with an error that names JSON
rather than the name carrying it.

CR is now escaped. The rest could not be: `\u00XX` needs the character's code,
and **`charToInt` is not in the local API reference**, which is exactly the bet
round 47 lost on `axlDirName`. PCRE is used elsewhere in this file, so it is
known to work here - so any other control character is detected with
`pcreCompile( "[\x01-\x08\x0b\x0c\x0e-\x1f]" )` and replaced by a space, with a
console warning naming the string. The pattern deliberately excludes tab,
newline and CR so the warning cannot fire for characters that ARE handled, and
it is asked **once per string**, not once per character: the per-character form
would run on every ordinary character of every name on a dense board.
`tests/test_quote.py` now walks 0x01-0x1f and requires the document to parse.

The other five, each a line or two: the GUI's queue drain reschedules in a
`finally` (anything escaping it stopped the window updating for the rest of the
session - no log, no progress, no completion, while the build ran on); a failed
`getWorkingDir()` now produces the same sentence the load-time self-test prints
instead of `parseString` failing on nil (and it is an `if`, not a `return` -
`return` is prog-only, and the trap is documented in this very file);
`headList` -> `s3dHeadList` and `addIndent` -> `s3dAddIndent`, because SKILL has
one global namespace and **the upstream script calls `addIndent` without
defining it**, so that name belongs to something else on the machine and load
order decides whose wins; `_gui_prefill`'s docstring listed 6 of the 13 flags it
takes; and `s3dResolveCadDir` carried its header comment twice, in two
redactions.

pyflakes is now clean across `stepbuilder`, `tools` and `tests` - it was 25
lines of known noise, which is the state in which a real warning goes unread.
The only shipped-code entry was `bend.py`'s `stack_at`, rebound rather than
shadowed. 20/20 suites green.

**Not verified in Allegro yet**: the two SKILL changes (the control-character
path and the nil-working-directory message). Neither is on the ordinary route -
the first needs corrupt data, the second a different Allegro - but both are new
code in a file that only Allegro can run.

## Update 2026-08-03 (round 52) — the variant rule, settled on the refdes

The user brought a third case and decided the rule with it. `A4` on their board:
a MOLEX housing, **refdes, a component in the netlist, compdef class
`MECHANICAL`, a `PKGDEF_STEP_FILE`, no `NO_STEP_EXPORT`** — so round 49's third
test fired and it rode into every variant. Their decision, stated twice:

> если у символа есть рефдес и в папке есть список вариантов, то смотрим
> список. Если компонент есть — проверяем `NO_STEP_EXPORT`. Если в списке
> рефдеса нет — не экспортируем вне зависимости от свойства.

So the rule is now **one question: does the symbol have a refdes?**

| | |
|---|---|
| refdes + variant list | the list governs it, mechanical or not. Installed and unmarked → exported; installed and marked → not; absent → not, whatever the property says |
| refdes, no `Variants.lst` | only `NO_STEP_EXPORT` |
| no refdes | only `NO_STEP_EXPORT`, always — it can never be named in a list |

**This is not as much of a reversal as it looks.** Round 49's first test was "no
logical component", and the docs settle that it is the same condition written
longer: `refdes` is *"nil if no associated component (for example, mechanical)"*
(`skill_db_attributes.txt`, Symbol Instance Attributes). What is dropped is
tests 2 and 3 — symbol type and compdef class — and with them the idea that a
part can be told apart from the variant system by what it IS. It can be told
apart by whether it is **nameable** there, which is the property that actually
decides whether the file's silence means anything.

**What it costs, stated before it was done and accepted:** `A1`/`A2` on
`variants_test-b0` are not among the 33 refdes that file lists (round 49 counted
them in the seven extras), so they will now be dropped from the `ALL` variant.
If a housing must survive a variant that does not list it, the variant list is
where to say so.

`s3dIsMechanical` **stays**, unused by the export and marked as diagnostic:
`probe_variants.il` is the only thing that can answer "what kind of part is
this", and after this change that question is more likely to be asked, not less.
The probe grew a second table — mechanical parts that DO carry a refdes, i.e.
exactly the ones whose behaviour changed — and its "dropped" line no longer
exempts them.

Two messages were quietly wrong the moment the rule moved, and both are fixed:
the stub guard said the export would leave "a board with only its mechanical
parts" (now: only the symbols with no refdes), and the foreign-file guard said
it would write "one copy of the WHOLE board per variant name" — under this rule
a foreign file installs nothing of this board, so it would write one STRIPPED
board per name. A guard whose message describes the previous rule is a guard
nobody can act on.

`NO_STEP_EXPORT` is still tested first. The user put the variant first; the
outcomes are identical either way (both lead to "not exported"), and testing the
property first is what keeps `FID2 - NOT exported: the symbol carries the
NO_STEP_EXPORT property` in the console for a part that is also uninstalled.
Confirmed with them: the property is attached **to the placed symbol**
(`Properties attached to symbol`), which `axlDBGetProperties(sym)` reads — no
`sym->definition` fallback is needed, though the STEP properties beside it do
live on the symbol definition.

One guard was added that the old rule did not need: the subtraction now tests
`t_variant` as well, the same condition `installed` is built under. A variant
table with no variant named fills that table with nothing, which used to drop a
few components and would now drop **every** one of them. No caller does it —
both call sites pass a variant — so it costs one comparison and removes a silent
catastrophe.

`tests/test_variant_path.py` [6] was rewritten: ten cases including the two the
old rule got wrong, plus source greps that now assert `!s3dIsMechanical(sym)` is
**absent** from the cond. 20/20 suites green.

**Confirmed live in round 54**, from the other side and on a real board: the
problem the user brought that round - solder pads with a refdes, no BOM line and
no mention in any variant, vanishing from every variant file - is this rule
doing exactly what it was built to do. `ALWAYS_STEP_EXPORT` is the deliberate
way back out of it.

## Update 2026-08-02 (round 51) — the two component groups get the board name too

The user: the board-name postfix reaches the board body and the silkscreen, but
not the component assemblies. Correct, and it was one line — `group_for()` in
`core.py` named its group with the bare `side` string, so every export in
existence carried a `symbols_top` and a `symbols_bot`. `PCB_<stem>` got its
postfix in round 8 and `silkscreen_top_<stem>` in round 10; the groups were
added earlier than both and were simply never revisited.

Now `_sanitize(f"{side}_{json_stem}")`, the same expression the legend uses —
which also gives the group names the sanitising they never had. The reason is
the round-8 reason unchanged: two boards imported into one CAD session collide
on any name that is not per board, and a group is exactly as substitutable as a
part.

Worth noticing about the test that did not catch it: `test_mech.py` asserted
`"symbols_top" in txt`, a **substring** of the correct name, so it passed both
before and after. It now asks for `symbols_top_mech_test`, which fails on either
half of the change being reverted. A containment test on a name that is a prefix
of the right answer cannot tell the two apart.

README, both languages: the assembly tree shows `symbols_top_<board>` /
`symbols_bot_<board>`, and the bullet that used to single out the board part now
states the rule for every top-level node. `tools/audit_docs.py` looks for the
bare labels as substrings, so it stayed green on its own; 20/20 suites pass.

**Not verified in Allegro yet** — this is a rename in the STEP tree, so it wants
one live export opened in CAD to confirm the two groups read as expected.

## Update 2026-07-27 (round 50) — the variant that changes a part, not the list

Round 49 confirmed live: `R1 R2 R3 R4 R8` gone, `A1`/`A2` kept as mechanical.
The next question was the other shape a `Variants.lst` can take - a variant that
**overrides properties on individual components** - and the user put such a file
in `My Test Board`. Two variants, `LSM` and `BNO`, and after `BNO`'s base list:

```
(C43 VALUE="12pF" JEDEC_TYPE="CAPC100X50X55L25N" TOL="1" )
(C44 VALUE="12pF" JEDEC_TYPE="CAPC100X50X55L25N" TOL="1" )
```

**It is handled, and the new rule is what makes it matter.** Traced through the
parser line by line rather than assumed:

- the line matches `propertyStart` (`^\t\t\(`), so it is read in
  `awaitEndCondition` - exactly where such a block sits, after `base` closes and
  before the variant does;
- `refDes` comes from token 0 with the parser's character class stripped ->
  `C43`, and `symbols = nconc( symbols list( refDes ) )` puts it in **that
  variant's** installed list. That line is the 2026-07-22 fix: it used to append
  `nth( 0 subStrings )` after `subStrings` had been reassigned to the property
  chunks, i.e. `VALUE="12pF"` instead of the refdes;
- the "does this block end on this line" test compares the last chunk against
  `")\n"`, which holds because `parseString` splits on **spaces only** - the
  trailing newline stays attached to the closing paren. That is also why
  `strcmp( line "\t\t(base\n" )` works at all.

So a component that a variant only *re-specifies* counts as installed there, and
under round 49's rule it is exported in that variant and **dropped in the other
one** - which is right, and was invisible before, when everything unmentioned
was exported everywhere.

`tests/test_variant_path.py` [7] transliterates that branch on the real line
from the user's file: the refdes must come out `C43` and not `VALUE="12pF"`, and
a block that continues onto the next line must not be read as finished.

### One thing the parser leaves behind

Splitting on spaces means a line ending in `" )"` yields a bare `"\n"` token,
which survives the character-class strip (it has no `\n` in it) and lands in the
variant's symbol list. It can never match a refdes, so it has never changed an
export - but it did add one to `variant list covers N of M`. `s3dIsRefdesToken`
now filters tokens with no alphanumeric in them, in both tables.

## Update 2026-07-27 (round 49) — the variant rule, inverted back on purpose

The user built a board FOR this: `variants_test-b0.brd` in `My Test Board`, with
its own `Variants.lst` - one variant `ALL`, 33 refdes, **space**-separated (the
other files on that disk use commas; the parser handles both). The exported JSON
carried **40** components. The seven extra: `R1 R2 R3 R4 R8` and `A1 A2`.

### Where it broke, precisely

`2026-07-22`. The comment is still in the source:

> was `symbols = variantSymbolList[variant]`, i.e. the parsed variant list WAS
> the export list, so a symbol the parser did not return could not be exported
> at all - which is how mechanical components went missing.

That fixed mechanical parts and broke this. The replacement rule was *subtract
only a refdes the table mentions SOMEWHERE*, and a component the file never
names - `R3` - is then not variant-controlled and rides into every variant. Both
readings are defensible; both are wrong on the other case.

### What separates R3 from a bracket

Not whether the file mentions it. **Whether the part comes from the schematic at
all.** `s3dIsMechanical` now answers that, three reads, each in an `errset`:

1. **no logical component** (`sym->component` is nil) - a symbol placed in the
   layout that the netlist has never heard of. A part that is not in the
   schematic cannot be in a variant list generated from it, so its absence there
   says nothing. This is the one that covers "the designer dropped something on
   the board that will never be in a variant";
2. **symbol type** `MECHANICAL` - an `.osm` placed directly;
3. **compdef class** `MECHANICAL` (`sym->component->compdef->class`, confirmed in
   `skill_db_attributes.txt`: *Component classification*) - a placed part with a
   refdes and no BOM line. `A1`/`A2` on the test board are MOLEX housings
   sitting exactly on `XP1`/`XP2`.

Everything else with a refdes obeys the list: installed -> exported, absent ->
dropped. With no variant table at all, nothing is dropped, exactly as before.

`NO_STEP_EXPORT` is unchanged and still wins over all of it - it is the answer
for a mechanical part that must not be in the model at any time.

### And the stub now stops the export

Under the old rule an empty variant list exported everything; under this one it
would export a board with only its mechanical parts. Both are wrong, so
`s3dVariantFit` raises on it rather than picking a wrong answer quietly.

`probe_variants.il` prints, per variant, the refdes it would DROP, and a table of
everything outside the variant system with **which of the three tests fired** -
`in netlist / symbol type / compdef class` - so a part that is kept or dropped
can be traced to the reason instead of guessed at.
`tests/test_variant_path.py` [6] pins the six cases.

**Not verified in Allegro yet**: that `A1`/`A2` really do come back mechanical
by one of the three tests. If they do not, they will appear in the probe's
"dropped" line, and the fix is theirs to choose - a `MECHANICAL` class on the
compdef, or `NO_STEP_EXPORT` if they should never be in the model.

## Update 2026-07-27 (round 48) — the variant list that is not this board's

Reported straight after 47b: the path resolves now, and the 3D **still** carries
components that should not be on the board. It is not the subtraction rule -
that works. It is the file.

### What is actually on the user's disk

Looked, rather than asked. `find d:/Projects/OrCAD -iname Variants.lst` returns
**twelve** files across unrelated projects, and they are **two files copied
around**: `md5 2c47440f…` in seven projects and `md5 949a3de5…` in five.

- `949a3de5` is a **stub**: one variant called `"dummy"` whose base list is
  literally `( )`.
- `2c47440f` is a real-looking list whose "variants" are part-number groupings
  (`"CC0603KRX7R9BB104"`, `"C other"`, `"DA DD"`, `"VD"`, `"VT"`, `"X"`) - and
  it is the SAME list of refdes in every project that carries it, so in all but
  at most one of them it describes a different board.

### Why either one exports the whole board

The export's rule is *the variant table only subtracts, and only for a refdes it
KNOWS* - which is what makes mechanical parts work (round 19) and must not
change. Both files defeat it from the other side:

- the stub knows **nothing**, so `known[refdes]` is false for everything and
  nothing is ever subtracted;
- another project's file knows plenty, **none of it on this board**, with the
  same result.

Either way every component lands in every variant file, under real-looking
variant names. Round 6's check does not fire: it catches a file that parses into
ZERO variants, and both of these parse into one or twelve.

### s3dVariantFit

Asked once, before the variant loop, and it does not change what is exported:

- **no refdes known at all** -> a warning naming the file: nothing can be
  subtracted, every component goes into every variant file, this is what a stub
  does, replace it or delete it.
- **known refdes, none placed here** (and the board does have refdes) ->
  `error()`, the same shape round 6 uses: the file belongs to a different
  project, it would write one copy of the whole board per variant name, and
  nothing downstream could tell.
- otherwise -> `variant list covers N of M placed component(s)`, which is the
  line that makes a half-matching file visible too.

`probe_variants.il` grew section 2b with the same three numbers, and
`tests/test_variant_path.py` [5] pins the three branches plus the call site.

## Update 2026-07-27 (round 47b) — Variants.lst is read from beside the board

The user settled the question the round below leaves open: **Variants.lst always
lives in the same folder as the `.brd`.** So the bare-name read was simply
wrong, not merely fragile, and it is fixed rather than documented.

`s3dDesignFolder()` cuts the folder off `axlGetDrawingName()` (the full drawing
path; `axlCurrentDesign` gives the NAME only), and `s3dVariantFilePath()`
appends `Variants.lst` to it. Both places that used to bind the bare name now
call it: `gdsysGetVariantInfo`'s own `let` and `makeVariant3dIntermediates`'s.
When the drawing path cannot be read it falls back to the bare name, i.e. to the
old behaviour, so an Allegro that does not answer `axlGetDrawingName` is no
worse off.

**The folder is found by SCANNING for the last separator, not with
`parseString`.** parseString collapses consecutive separators, so a UNC path
`\\server\share\boards\x.brd` would come back as the relative `server/share` -
the limitation `s3dMakeDirs` right above it still carries and this one must not.
The character scan keeps the leading slashes, the drive letter and mixed
separators exactly as they came.

The no-variant branch now also prints the path it tried. "No variant information
present" alone cannot be told apart from "your Variants.lst was not found", and
those want different things done about them.

`tests/test_variant_path.py` transliterates both helpers the way
`test_quote.py` does `s3dJsonQuote`: local path, UNC, mixed separators, a bare
drive root, a name with no folder, and the root case that must not produce
`//Variants.lst`. It also greps the SKILL source so that a
`( variantFile "Variants.lst" )` binding coming back fails the suite - that
binding IS the bug.

## Update 2026-07-27 (round 47) — Variants.lst: what the path actually is

Asked whether the variant export still works. **Nothing in rounds 43–46 touched
it** — `git log -L 3230,3336:makeVariant3dIntermediates.il` puts the last change
to that region at `599b4f5`, well before this session — so it is not a
regression from any of this work. The path, written down because it has three
quiet ways of looking broken:

1. **The trigger is `isFile("Variants.lst")` — a BARE NAME**, so it resolves
   against Allegro's working directory (`getWorkingDir()`), the same directory
   the exporter derives `rev/cad` from. **Not** next to the `.brd` unless those
   coincide, and not in `cad`. `gdsysGetVariantInfo` opens it the same way. A
   board opened from elsewhere therefore exports as if it had no variants, with
   only the console line `No variant information present! Exporting all
   components!` to say so.
2. **A Variants.lst from another project parses into zero variants**, and that
   is a hard `error()` with the "delete or replace it" message (round 6). The
   count has to be obtained by iterating the table - it is always truthy and
   `length` does not apply.
3. **Nothing deletes old intermediates.** A `<design>.json` left in `cad` by an
   earlier no-variant run stays there, is still tagged `"format": "simple3d"`,
   and the GUI - which resolves every tagged json in the folder at Generate time
   - builds it alongside the variant files. So the symptom of a stale file is an
   EXTRA STEP containing every component, not a missing one.

Otherwise the path is as designed: one JSON per variant, `<design>_<variant>`
lower-cased, into `cad`; silkscreen collected once outside the loop (the bare
board is manufactured once for every assembly variant); the export list taken
from the DESIGN with the variant table only subtracting.

### `tools/probes/probe_variants.il`

New read-only probe that answers all three at once: the working directory and
whether Variants.lst is in it, where the board file actually is and whether the
file is there instead, what the parser makes of it, which refdes each variant
installs against how many symbols would really be exported, and the filenames
that would be written.

Two things came out of writing it, both worth keeping:

- **It calls into the exporter on purpose** (`gdsysGetVariantInfo`,
  `s3dSymbolsToExport`) - a diagnostic that re-implemented what it reports on
  would be worthless. `skill_checks.py` checks each probe against its OWN
  definitions, so it now honours a `; REQUIRES: <file>.il` marker line and pools
  that file's definitions for that probe alone. Explicit, so the dependency is
  visible at the top of the probe where whoever loads it will read it.
- **The first draft called `axlDirName`, which does not exist.** Caught by
  scanning every `axl*` call in the repo against the local API index - and worth
  noting that the check the project already has could not: `PROJECT_RE` only
  matches our own prefixes, so an invented `axl*` name reads as a builtin.
  `axlCurrentDesign` returns the NAME only; the full path is
  `axlGetDrawingName`. The same scan over the shipped files came back clean
  apart from `axlGetParam`, which IS real (it is in the HTML docs, just not in
  the extracted 957-name index) and is wrapped in `errset` anyway.

## Update 2026-07-27 (round 46) — full review, and the docs caught up

A read of the code as it stands after rounds 43–45. **Nothing was found in the
geometry or the logic**; everything below is either a doc statement that had
gone stale or one dead line. Recording what was checked and came out clean is
half the point of the round — so it is not all re-checked next time.

### What was actually read, and what was only scanned

Honest about the difference, because "reviewed" means different things here:

- **Read in full:** `core.py` (2256 lines), `worker.py`, `__main__.py`,
  `simple3d.il`, and of `bend.py` the plan, the strip geometry, the prism test
  and the property parsers. Of `gui.py`, everything that carries state -
  `__init__`, config load/save, the worker plumbing, the snapshot - the
  widget-layout half was skimmed.
- **Scanned mechanically, not re-read:** `makeVariant3dIntermediates.il` (3336
  lines) - unchanged since round 42's full read, so it got the four mechanical
  checks plus targeted greps for the two trap classes it has a history of.
  `tests/` and `tools/` got pyflakes and a run.

### Found and fixed

1. **`gui.py` imported `traceback` and never used it.** Dead since the build
   moved into a child process in round 40 - the traceback is formatted in
   `worker.py` now and arrives as text. One line, removed.
2. **README: "all 18 suites, about 50 s".** 19 and ~55 s since round 43. Both
   language halves.
3. **README: "`cadquery-ocp` … (~165 MB). It is the only dependency."**
   Misleading twice over: it declares **VTK** as a hard dependency, and the
   three together are **~470 MB on disk** - measured here as 91 MB of bindings,
   63 MB of OCCT libraries and ~315 MB of VTK. The sentence now says so. This is
   the same measurement the standalone-exe question turned up earlier in the
   session, and it is worth having in the README rather than only in a chat.
4. **"How it works" had no pre-flight and no progress meter in it** - the
   diagram jumped from writing the JSON to the window appearing, which is
   exactly the several seconds a user now watches a progress form during. Added
   as its own step, in both halves and in `QUICKSTART.md`.
5. **Nothing said the model lookup ignores case** (round 45). Added to "Models
   the board carries a copy of", both halves.

### Checked and clean - do not re-derive

- **No `return()` inside a `let()`** in either `.il`. That is the round-9 trap
  (SKILL's `return` is legal only in a `prog`), and it is now scanned for
  mechanically rather than by eye.
- **Round 42's per-design resets are still in place**: `S3D_RigidFlexShapes`
  and `S3D_BendLines` at the top of `makeVariant3dIntermediates`,
  `S3D_MechSeq` and `S3D_SilkWarnings` one level down.
- **`FoldPlan.chain` really is the 4-tuple its annotation claims.** `plan_fold`
  builds `kept` as 6-tuples and `plan.chain = [(b, n, p, h) for b, n, p, h, _, _
  in kept]` narrows it, so `in_bend_area` and `describe` unpack correctly. It
  reads like a defect on the way past; it is not.
- **The `_check_worker_alive` race is benign.** A child can exit with code 0
  while its "done" message is still in the pipe; the check marks `_finished` and
  returns, and the next drain (100 ms later) still delivers the message and
  re-enables the window. Traced rather than assumed.
- **pyflakes is clean** on the shipped package apart from `bend.py:915`, which
  is the deliberate `stack_at = None` / conditional `def stack_at` pattern.
- No bare `except:`, no mutable default arguments, and the config save's
  two-condition rule (understood at load AND at save) is intact.

## Update 2026-07-27 (round 45) — model names, case-folded

Asked by the user: were `.step` and `.STEP` two different files? For the model
search, yes — and not only the extension. `StepFileIndex` keyed its dict on
`path.name` and looked up with `dict.get(name)`, so **the whole name was
compared exactly**, while the two sides come from different places: the name
being looked for comes from Allegro's STEP mapping table, typed by hand, and
the file on disk is named by whoever supplied the library. Windows itself
cannot hold two files in one folder that differ only in case, so there was
nothing to disambiguate — only a model missing from the assembly and a log line
saying "could not find model.step".

`find` now falls back to a lower-cased index when both exact lookups miss, and
`_note_case` says which file it used (capped at ten lines, like the
shadowed-name report — a library spelled the other way throughout would
otherwise print one line per component). **Exact match is tried first and always
wins**, and the folded index is filled first-wins in the same root order, so
nothing that resolved before resolves differently, and the ambiguity that only a
case-SENSITIVE filesystem can present resolves by declared precedence.

Checked while there, so it does not get re-investigated: `Path.glob` is
**case-insensitive on Windows** in 3.12 (`case_sensitive=None` means "follow the
platform"), so `glob("*.json")` in `resolve_json_jobs` already picks up a
`.JSON`, and `rglob("*")` in the index never filtered by extension at all. The
exact-dict lookup was the only case-sensitive step in the chain.

`tests/test_index.py` [8] covers it: the extension in another case, the whole
name in another case, exact beating folded, a name that differs by more than
case still missing, and the cap on the report.

## Update 2026-07-27 (round 44) — the 25 micron ledge on flex2-a0

Reported from the user's own export: *"около BEND_1 появляется ступенька на
основной шлейф, она выступает на 0.025158 мм. В проекте платы всё хорошо, дуга
непрерывная."* It was real, it was ours, and the number came out of the code to
the micron.

### What it was

The board's right edge runs **straight** at x = 6.93 up to y = 6.057 and then
**curves outward** along an arc (centre 11.9344, 6.0001, R = 5.0047). BEND_1's
strip at k = 0.5 spans y ∈ [5.074, 6.5045] — so the curve starts *inside the
bend area* and has reached 0.0252 mm past the straight part by the far edge of
the strip.

`_revolve_strip` builds a bend as one cross-section revolved about the axis,
which is exact and cheap **when the strip is the same shape at every station**.
That was tested by volume: section area × strip width against the strip's
volume, within `PRISM_TOLERANCE` = 0.2%. For this strip the whole bulge is

    0.0252 mm x 0.45 mm x 0.29 mm ~ 0.0022 mm3   =  0.04% of the strip

— comfortably inside the tolerance. So the strip was declared straight, the
section taken a quarter of the way in (where the edge is still at 6.93) was
revolved through the whole 97°, and the curve was **dropped**. Where the bend
ended and the flat board resumed at 6.9551, the model stepped by 0.0252 mm.

Measured, by instrumenting the test on the real board:

| strip | volume | section × width | miss | x-max near lo / hi |
|---|---|---|---|---|
| BEND_1 (w 1.4306) | 0.23257 | 0.23247 | **0.044%** | 6.9300 / 6.9484 |
| BEND_2 (w 4.5490) | 0.73927 | 0.73922 | **0.007%** | 9.6500 / 9.6500 * |
| BEND_6 (w 4.8669) | 1.24353 | 1.42355 | 14.5% | 9.6500 / 10.2065 |

\* BEND_2's box is equal at those two stations but not at the strip's own end —
it was off by 0.0165 mm, a second ledge nobody had noticed yet. BEND_6 was the
only one the volume test ever caught.

### The fix

A volume test cannot see a feature this small; a **length** test can. After the
volume check passes, `_spans_alike` now also requires the cross-section to span
what the strip itself spans, along the bend line and in z, to within
`PRISM_SPAN_TOLERANCE` = 1 µm. Compared in the strip's own frame (the bend line
turned onto X) so a diagonal bend is not mistaken for a taper, with
`BRepBndLib::AddOptimal` because `Bnd_Box` pads by the shape's tolerance and
follows curved edges properly — a vertex-by-vertex comparison would miss a bulge
whose apex is mid-arc.

Nothing extra is built for it: the section is already in hand and the two boxes
cost nothing next to the booleans around them. Build time on flex2-a0 is
unchanged at ~15 s.

**Result on the real board:** BEND_1 and BEND_2 now fall through to the wrap and
come out as **true cylinders** — not facets — and the material comes back
(+0.0018 mm³ over the whole board; +0.0010 mm³ in the corner past x = 6.9315,
which is where the ledge was). BEND_3/4/5 are still revolved, BEND_6 still
wrapped. The `miss` the new test reports for BEND_1 is **0.025158 mm** — the
user's number exactly.

### The regression test

`test_bend.py` [11b]: the demo board with a 0.5 × 0.03 mm ear on its far edge,
placed wholly inside the bend area. The ear is 0.008% of the strip's volume, so
it is squarely under the old tolerance. The fold turns about an axis parallel to
y, so the ear's y is untouched: material past y = 80 exists in the result if and
only if the ear survived. **Verified to fail on the old behaviour** — with
`PRISM_SPAN_TOLERANCE` set toothless the ear measures 0.000000 mm³ — which is
the only thing that makes such a test worth having.

### Still open, noticed while measuring

The same board folded weighs **184.756 mm³ against 184.246 mm³ flat**, +0.28%.
Folding should preserve volume exactly (a strip of thickness t wrapped at k =
0.5 has volume θ·t·(r + t/2), the same as its flat developed length × t), and
this fix moves it by only 0.002. So something else adds half a cubic millimetre
when the board is folded — most likely pieces overlapping by a hair at the band
boundaries. Not investigated, not related to the ledge.

## Update 2026-07-27 (round 43) — the launcher, without a batch file

Branch `fix/launch-without-bat`. Both `.bat` files are gone. `s3dLaunch` and
`s3dPreflight` each hand cmd a single line now; the only file either one still
writes is the pre-flight log it reads back and deletes.

### What the batch file was actually working around

Round 5 blamed `start`: a design path with a space arrived at Python split in
two, and the reading at the time was that start had taken the first quoted token
as its window title. Writing the command into a file fixed the symptom, so the
diagnosis was never revisited — for 38 rounds.

It was the wrong culprit. Four shapes measured through `os.system` (the C
runtime's `system()`, the closest stand-in available for SKILL's), with a space
in both the script folder and the design folder:

| line | result |
|---|---|
| `start "" /D "dir" "python" … --json-dir "…/my design dir"` | argv whole, cwd right |
| the same behind a second `cmd /c` | argv whole, cwd right |
| `"python" … --json-dir "…/my design dir"` | **fails** — syntax error from cmd |
| `cmd /c cd /d "dir" && "python" …` | runs, in the **wrong** directory |

The rule is cmd's, not start's: **a `/c` command line that begins with a quote
has its first and last quote stripped.** Begin with a bare word and every quote
inside is delivered untouched. `start ""` — the empty title — disposes of
start's own title parsing, so what looked like one hard problem was one cmd rule
plus one missing argument.

The fourth row is the reason `/D` is used rather than the more obvious
`cd /d … &&`: a chain binds to the **outer** shell. If SKILL's `system()` puts a
cmd of its own in front of the string, `cd /d "dir"` runs in a subshell that
exits immediately and the interpreter starts in Allegro's working directory,
where `-m stepbuilder` does not resolve. `start /D` is carried to the child
process itself and survives either nesting depth. Redirection does not have the
problem — the child inherits the handles — so the pre-flight can still capture
stdout and stderr with a plain `> "log" 2>&1`.

The user confirmed the launch form in a live Allegro session before any code was
touched, which also settles two things the local tests could not: `system()`
passes the string through intact, and forward slashes are fine in `/D` (the GUI
came up, so `-m stepbuilder` resolved, so the working directory really was set).

### The two procedures now

```
s3dLaunch     cmd /c start "" /D "<S3D_ScriptDir>" "<pythonw>" <argTail>
s3dPreflight  cmd /c start /B /WAIT "" /D "<S3D_ScriptDir>" "<python>"
                  -c "import stepbuilder.core, tkinter; print('S3D_OK')" > "<log>" 2>&1
```

`/B` keeps the pre-flight console-less, `/WAIT` keeps it synchronous. Everything
else about it is unchanged: same sentinel, same log file in the design folder,
same three remedy lines.

Two things went with the files:

- **The `S3D_NOEXE` marker**, which was an `if errorlevel 9009` line in the bat.
  It cannot be expressed without a file or a chain, and a chain is exactly what
  must not be used here. It existed to keep cmd's localised "command not found"
  message — OEM codepage, mojibake in the Allegro console — out of the report.
  The replacement classifies by **who spoke**: the log is echoed only when it
  carries `Traceback` or `Error`, which is Python answering in ASCII; anything
  else, including an empty log, is reported in our own English words and the
  bytes are never printed. That is strictly less dependent on Windows' locale
  than the marker was.
- **The "launcher could not be created" branch** in `s3dLaunch`. A read-only
  `S3D_ScriptDir` — Program Files, a network share — could not launch the GUI at
  all before, because the bat was written there. Nothing is written there now,
  so the failure mode and its error path are both gone.

### `tests/test_launch_cmd.py`

New suite, registered in `run_all.py`, Windows-only (it prints a skip line
elsewhere). It transliterates both command shapes the way `test_quote.py`
transliterates `s3dJsonQuote`, and runs each **twice** — as written and behind an
extra `cmd /c` — so nesting-independence is a test and not an assumption. It
covers argv, the working directory, the sentinel, a real `ModuleNotFoundError`
reaching the log, and the **negative control**: the quoted-first form must fail.
That last case is the whole reason the `start` prefix exists, and without a test
it is the first thing a future tidy-up would remove. A fifth check greps
`simple3d.il` itself, so changing the shape in the source without changing the
suite fails the run.

### A progress meter, because Export looked like a no-op

Reported the same round: *"нажимаю экспорт, и ничего не происходит"*. The
export reads the board, writes the JSON and starts Python before any window
appears — seconds on a real board — and **Allegro's own green Ready light stays
green through all of it**.

There is **no API for that light**. Searched the whole index (2600+ entries) and
all 872 `DOC/FUNCS/*.txt`: nothing for Ready/Busy, and `axlUIControl` is canvas
inquiry only. What Allegro does give is `axlMeterCreate` / `axlMeterUpdate` /
`axlMeterDestroy` — its own progress form, title plus one ~28-character line,
with an optional Stop button. `s3dMeterOn/Step/Off` wrap them; the export names
four stages (20 / 70 / 95).

Three decisions in there worth keeping:

- **Stop is not enabled.** Nothing in the sequence can be interrupted once it is
  running — `makeVariant3dIntermediates` is a single call — and a button that
  stops nothing is worse than no button.
- **Every call is wrapped in `errset`.** The meter is a courtesy; a release
  without it, or a form that refuses to open, must not fail an export that would
  otherwise work.
- **`s3dMeterOn` destroys a stale meter before creating its own.** SKILL has no
  unwind-protect, so a hard error inside the export leaves the form on screen;
  this clears it at the next export. Every exit path of `s3dExportCommand` calls
  `s3dMeterOff` — including the pre-flight's refusal, which is easy to miss.

Not per-variant, and nothing inside `makeVariant3dIntermediates`: the long pole
is one variant's own silkscreen work, so per-variant ticks would buy almost
nothing, and the messages in there go through raw `printf` rather than `s3dSay`,
so there is no single funnel to hook. If finer progress is ever wanted, that
funnel is the thing to build first.

### The console still blinks — and it is not Python

Reported with the above. `pythonw.exe` is a **GUI-subsystem** binary: it never
allocates a console, so nothing that flashes can be it. The flash is
**`cmd.exe`**, a console-subsystem binary — when a GUI process (Allegro) starts
it, Windows creates a console window for it, which closes when cmd exits. It
predates this round: the batch file was run through `cmd /c` too.

**`system()` always goes through a shell — settled by probe, do not re-open
this.** Two probes in the user's live Allegro console:

- `system("echo probe > <path>")` → the file appeared. Redirection is a shell
  feature, so `system()` hands the string to cmd.
- `system("pythonw -c \"import time;time.sleep(4)\"")` — no `cmd /c` from us at
  all → **a console window still appeared**. pythonw cannot be its owner, so
  cmd is in the chain whatever we write.

**Therefore the console cannot be removed through `system()`, and `system()` is
the only door.** Checked the alternatives before concluding: no `ipc*` and no
exec function anywhere in the index; `axlRunBatchDBProgram` is for Allegro batch
programs that want the database; and the plugin family (`axlDllOpen` /
`axlDllSym`) is **not** a general FFI — an exported function must have the
signature `long f(AXLPluginArgs*, AXLPluginArgs*)` and be built against
Cadence's `axlplugin.h` with their toolchain, so `ShellExecute` cannot simply be
called. Shipping a compiled DLL to remove a console flash is out of proportion.

### What the console actually costs, and why it stays

Measured: two appearances per export, and the first is not a flash.

| | command | window visible |
|---|---|---|
| pre-flight | `python -c "import stepbuilder.core, tkinter"` | **1.78 s** — it sits there |
| launch | `start ""`, cmd exits at once | ~0.1 s |

1.7 s of that 1.78 is importing OCP. It is paid on every export for a diagnosis
that is needed rarely, and the reason it must be a separate process is that
[`__main__.py`](stepbuilder/__main__.py) imports `from .gui import
StepBuilderApp` **outside** the `try` that catches startup failures — so under
pythonw a broken OCP kills the process silently, with no dialog and no log.

The cheaper design was offered and **declined by the user (2026-07-27)**: move
that import inside the `try` so Python reports its own broken install by dialog,
and reduce the SKILL pre-flight to `-c "import sys"` (0.06 s — a blink). It
would have made every export ~1.7 s faster. The user prefers the full check with
its diagnosis printed in the Allegro console. **Do not propose it again without
new information.**

### Not verified outside Allegro

The user confirmed the launch line opens the window. Still to check on a live
export: the meter itself (`axlMeterCreate` is documented but has never run in
this project), no `_simple3d_*.bat` left in either folder, a board whose path
contains a space, and the two pre-flight failure branches (a bad `"python"` in
the config → the English not-found text; a renamed `stepbuilder/` → Python's own
ImportError echoed).

## Update 2026-07-27 (round 42) — full review, and the docs brought up to date

A read of every source file in the project (~10 000 lines: both `.il`, the six
Python modules, `tools/`, the suites, the config). The code is in good shape;
four defects came out of it, three of them silent.

### 1. `--brd-name` did nothing without `--dated-name`

`base` was computed and then only used on the dated path, so
`--brd-name X` alone produced a file named after the JSON. Reproduced on the
demo board. The launcher always passes both, which is why it was never seen.

The naming rule now lives in **one** function, `core.output_stem` — the
docstring of `dated_output_name` had claimed exactly that ("shared so the rule
cannot drift"), and it had drifted anyway because only *half* the rule was in
there. `__main__.py` and `worker.py` both call it. Covered by test `[7e]`.

### 2. Two per-design caches survived into the next board

`S3D_RigidFlexShapes` and `S3D_BendLines` are built once and then guarded with
`unless( S3D_... )`. The SKILL files load once per Allegro session, so
exporting board A and then board B reused **A's** shapes and bend lines — as
dbids into a database that may not even be open. Nothing would say so; the JSON
would simply describe the wrong board. `S3D_MechSeq` and `S3D_SilkWarnings`
are already reset per export, so this was an omission rather than a decision.
Both are now cleared at the top of `makeVariant3dIntermediates`.

### 3. The doc audit rubber-stamped renamed controls

`tools/audit_docs.py` checked a QUICKSTART label by its **first word** against
an allow-list. So "Ignore soldermask layers" kept passing after the widget was
renamed to "Do not include soldermask layers" — both start with a word that was
on the list. It now matches the whole string against `gui.py` + `colors.py`,
with two named exceptions for prose shorthand (`Custom…`, `White/Black`).
Verified by renaming the label back and watching it fail.

### 4. Documentation that had gone stale

Found by reading, not by the audit — which only checks what it can mechanise:

- `simple3d_config.json`, the file users actually edit: `_comment_foldBends`
  still said "the fold is faceted, not exact" (wrong since round 38),
  `_comment_boardMode` said the GUI calls it "Board" (it says *Body
  stitching*), `_comment_ignoreSoldermask` named a checkbox that had been
  renamed, and `_comment_foldNeutral` still called the bend area a cross-check.
- README: a `debugLayers` row documented as current when the key is
  migration-only; the settings table's section column wrong from
  `negativeLayers` onward, so eight `gui` keys appeared to be `settings` ones;
  the GUI table missing **Body stitching** and the soldermask checkbox
  entirely; the install tree missing `bend.py` and `worker.py`; "about 40 s"
  for a 50 s suite; the probe list missing `probe_bend.il`; the changelog entry
  for round 36 still describing the fold as faceted.
- Both halves updated, plus the round-41 K-factor material and a new changelog
  entry, in English and Russian.

### Noted, not changed

- **`colors.as_fraction` is dead** — defined, named in the module docstring,
  and called nowhere; `core.py` writes `rgb[0] / 255.0` inline in five places.
- **Thirteen `MFRPN DISABLED` comment blocks** across six files, carried since
  round 18. They document a deliberate decision and say how to re-enable it, so
  they are not litter, but they are the largest block of commented-out code in
  the project.
- `board_mode` is not validated in `core.generate`; an unknown string silently
  builds a plain solid. Both callers restrict it (argparse choices, a
  read-only combobox), so it is unreachable from the shipped paths.

### Verified here

18/18 green, twice in a row (test `[7e]` empties its own directory - it writes
a .step to exercise the collision suffix, and the first version of it passed
once and then failed on the second run). `--brd-name` checked all three ways on
the demo board: bare, with `--dated-name`, and neither. The doc audit passes and
was checked to fail on a renamed label.

## Update 2026-07-26 (round 41) — flex3-a0, the ring, and one OCC tolerance

A third real board, **flex3-a0**: three zones, five bends, two of them 180° in
a row forming a closed ring. It exposed **two independent defects**, and every
symptom the user reported traces to one or the other.

### 1. Allegro folds at k = 0, and this board proves it

Round 37 measured that a BEND_AREA is drawn at the inner arc, `angle × radius`,
with no thickness term, and concluded it was a keep-out region rather than a
material budget. **This board settles it the other way.** BEND_4 and BEND_5 are
both 180° at r = 0.7954, lines 2.500 mm apart, areas 2.4999 mm across each:

| | length | two of them | vs the 5.000 mm the board has |
|---|---|---|---|
| drawn area, `θR` | 2.4988 | 4.9977 | closes the ring to **0.5 µm** |
| `k = 0.5`, `θ(R + kt)` | 2.8051 | 5.6102 | **0.61 mm short of material** |

A designer does not put two 180° areas 0.0001 mm apart by accident, and
2π × 0.7954 = 4.9977 against a 5.000 mm span is not a coincidence either. **The
flat pattern was laid out to a model in which a bend consumes its inner arc**,
i.e. k = 0. At the shipped default of 0.5 the two strips overlap by 0.305 mm,
BEND_5 is refused, and the ring cannot close. `--fold-neutral 0` folds all five
exactly. Same story at the other end of the board: BEND_3's strip overshoots the
FLEX/STIFFENER2 boundary (y = 37.98) by 0.076 mm at k = 0.5 and stops **on** it
at k = 0 — the bend area was drawn to fit the zone.

The default is **left at 0.5**, which is the physically right place for the
neutral axis of a symmetric flex; it is `foldNeutral` / `--fold-neutral` and the
user decides. What changed is that the log now says which of the two it is:

```
warning: bends BEND_5 and BEND_4 both want to fold the same material - 2.805 mm
  and 2.805 mm of it with their lines only 2.500 mm apart - ...
  their drawn bend areas do not overlap - Allegro draws them at the inner arc,
  2.500 mm each on average - so this is the neutral factor, now 0.50: at 0.00
  the two strips meet exactly (foldNeutral in the config, --fold-neutral ...)
```

Two off-by-an-epsilon bugs fell out of the same board, both where strips
**exactly meet** — which is what a ring is, and what nothing had ever been:

- the overlap test counted touching as overlapping (`< phalf + EPS` where it
  wanted `< phalf - EPS`), so even at k = 0 the ring was refused;
- `contains()` wanted strictly more than `ohalf`, so neither ring bend contained
  the other, both became roots, and the panel behind the first swallowed the
  second — the tail came back facing the wrong way.

### 2. `BRepBuilderAPI_MakeWire` drops edges it cannot join, and says IsDone

This is the one that was making bends "криво строиться". Symptom: BEND_1 and
BEND_3 faceted every layer with `the solid built from them is not valid`, and
BEND_3 built 2 of its 17 pieces and faceted 15.

Traced with `TopExp::MapShapesAndAncestors`: **the sewn shell had free edges** —
`{2: 13, 1: 2}` for BEND_1, `{2: 8, 1: 4}` for BEND_3 — so it was not closed and
the two cylinder faces came back `BRepCheck_UnorientableShape`. Raising the
sewing tolerance from 1e-6 to 1e-3 changed nothing, which ruled sewing out. The
faces were **missing edges before they were sewn**: 5 edges added to the wire, 4
in the wire; 4 added, 2 in the wire.

Why: the wrap rebuilds every outline edge from its own 2D curve, so consecutive
edges' surface points agree only as well as the FLAT solid's vertices did —
measured **2.8e-7 and 1.5e-7** on this board, perfectly legal there because the
shared vertex carries a tolerance that covers it. `BRepBuilderAPI_MakeWire`
joins edges at `Precision::Confusion`, a hard **1e-7** that nothing can widen,
and past it **it does not report a failure**: it starts a second wire, and
`IsDone()` returns true again as soon as some later edge closes a loop, having
silently dropped the rest.

Fix in `wire_on`: one explicit `TopoDS_Vertex` per junction, placed between the
two curve ends with tolerance `gap/2 + 1e-7`, and each edge built on the
vertices its neighbours share (`MakeEdge(curve2d, surface, V1, V2, p1, p2)`).
The wire is then connected by **topology** and no tolerance decides anything.
The edge count is checked afterwards regardless — that check alone would have
turned a week of "not valid" into one line.

**Do not replace this with a bigger sewing tolerance.** The gap is upstream of
the sewing.

### Was it the stiffener?

The user's guess — the bend area overlaps the stiffener — is only half right and
was not the cause. BEND_3's strip does cross into STIFFENER2 at k = 0.5 (by
0.076 mm, see above), which splits the layer into several disjoint solids, one
of them a 0.0765 mm sliver. But the sliver is legitimate geometry and wraps
exactly now; and **BEND_1 is 0.4 mm clear of any stiffener** and failed for the
same reason. What the stiffener actually correlates with is *small features* —
slivers, 1 mm fillets, 45° chamfers — which is where a loose corner is most
likely to be the shortest edge and get dropped.

### Verified here

flex3-a0 in all three board modes × k = 0.5 and k = 0: six builds, exit 0.
Before: 4 bends planned, 2 faceted, `built in more than one way (15 faceted,
2 wrapped)`, 52797 STEP entities. After, at k = 0.5: **every bend exact or
wrapped, no facets, no mixed-build warning**, 35581 entities. At k = 0: all five
bends fold, all exact, the ring closes.

Two new test sections. **[7c]** the ring: two 180° bends whose areas touch —
refused at k = 0.5 with the neutral-factor advice, folded at k = 0, tail back in
its own plane shortened by exactly the material the loop ate, loop standing 2R+T
above the board. **[17e]** an outline with one corner deliberately loose by
4e-7 — twice what OCC joins by itself, inside the vertex tolerance, so the flat
solid is valid. Checked against the old code: it fails with the field's own
message, `faceted at 7.5 deg per slice - the solid built from them is not
valid`. 18/18 suites green.

## Update 2026-07-26 (round 40) — the crash, caught and contained

### It reproduces, and the missing variable was the slice angle

The user's console run ended silently right after
`BEND_6: faceted at 5 deg per slice`. **5**, not 7.5 - they had edited
`DEFAULT_SLICE_ANGLE` in their copy, and my attempt to match it by patching
`bend.DEFAULT_SLICE_ANGLE = 5.0` at runtime **did nothing**: the value is
captured in a function's default argument at import time. Five reproduction
attempts in round 39 all ran at 7.5.

With the angle passed properly:

| | 7.5 deg | 5 deg |
|---|---|---|
| `solid` | builds | **exit code -1073741819** |
| `layers` | builds | **exit code -1073741819** |
| `inspect` | builds | builds |

`-1073741819` is `0xC0000005`, an access violation. It happens in
`fuse_keeping_faces` / `fuse_and_unify` - `inspect` fuses nothing, which is
exactly why the user's "not stitched" build came out. Narrowed further: **all 41
folded layer parts are valid solids** at both angles (`BRepCheck_Analyzer`), and
folding them one at a time is clean. It is the boolean over the combination that
dies, and the finer BEND_6 is sliced the more likely it is.

Nothing to fix in the geometry, then - the input is valid by every test OCC
offers. What can be fixed is that it took the window with it.

### The build runs in a child process now

`stepbuilder/worker.py`: `BuildSettings` (moved out of `gui.py`, because the
child must not import tkinter) and `run_jobs`, which the window starts as a
`multiprocessing.Process` and talks to over a `multiprocessing.Queue`. The
message protocol is the one the drain loop already understood.

`_check_worker_alive` then turns a dead child into a message: the exit code, the
words "access violation inside OpenCASCADE" when it is that one, and what
actually gets a board through - `Not stitched`, or a coarser `foldSliceAngle`.
Verified on the crashing configuration: the window stays up, says "The build
crashed", and keeps the log up to the last thing it was doing.

**Windows spawns rather than forks, so the child re-imports `__main__`.**
`stepbuilder/__main__.py` has the `if __name__ == "__main__"` guard already and
now calls `freeze_support()`; a scratch script of mine without the guard forked
bombed instantly, which is the lesson in one line.

Closing the window mid-build now terminates the child instead of leaving it
grinding on a file nobody is waiting for.

### The progress bar shows the build, not the last 5% of it

It only ever moved on component placement, which is the last second of a
two-minute build. `core.generate` now reports coarse phases - reading 2%, board
10%, legend 60%, components 75-95%, writing 96%, done 100% - and the label goes
into the status line. Measured on flex2-a0: the bar sits at 10% "Building the
board" for 40 seconds, which is honest, where before it sat at 0 and then jumped.

`ProgressFn` takes an optional third argument (the label); the call is wrapped
so a two-argument callback from anywhere else still works.

### flex2.stp, the designer's prototype, against the board

| feature | prototype | board |
|---|---|---|
| bend | r 0.700, 97 deg | BEND_1 r 0.7, 97 |
| bend | r 8.000, 32 deg | BEND_2 r 8, 32 |
| bend | r 10.000, 24 deg | BEND_3 r 10, 24 |
| bend | r 3.000, 37 deg | BEND_4 r 3, 37 |
| bend | r 0.500, **172 deg** | BEND_5 r 0.5, **180** |
| bend | r 2.000, **120 deg** | BEND_6 r 2, **130** |
| **roll** | **r 6.000, 294 deg** | nothing |

Every radius the designer used is in the board, so the transfer was mostly
right. Two angles were rounded up (172 to 180, 120 to 130), and - the one that
matters - **the prototype's seventh feature, a 294 degree roll at r = 6, has no
counterpart in the board at all.** In the prototype the rounded end of the tail
is a flat panel carried by that roll; in the board a 4.87 mm bend area at
y = 38.8 sits on top of the rounded end, so the r = 5 and r = 6.4 outline arcs
fall INSIDE the bend and the fold is asked to curve the round part itself. That
is the "разновеликое скругление", and it is why both this exporter and Allegro's
own 3D fail there.

## Update 2026-07-26 (round 39) — flex2-a0, and a bend nobody can build

A second real board: **flex2-a0**, six bends including a 180° at r=0.5 and a
130° at r=2.0 - the roll-up case. Five of the six build entirely on true
cylinders. The sixth is the one the user already knew was wrong.

### The bend that cannot be built, measured

BEND_6 crosses the round stiffener at the top of the board. Of its sixteen
layer pieces, nine build and **seven refuse**, all with "the solid built from
them is not valid". The reason is in the outline inside that bend area:

```
BEND_6: band 36.367..41.233, turn 2.269 rad, neutral radius 2.145
wire:  Line, Line, Circle(r=5.000 = 2.33 rad), Line,
       Circle(r=6.400 = 2.98 rad), Circle(r=6.400 = 2.98 rad), Line, ...
```

The board's own edge curves on a 5-6.4 mm radius **inside a bend that rolls it
onto 2.1 mm**. Wrapped, those arcs become ellipses spanning 133° and 171° of the
cylinder each - the material is being asked to curve two ways at once at a scale
larger than the bend itself. Allegro's own 3D canvas tears the same board in the
same place, which is the same statement from the other side.

**A tempting check that does not work:** "warn when an arc inside the bend area
is larger than the bend radius" flags BEND_1 (ratio 8.9) and BEND_5 (7.8) too,
and both of those build all seven pieces perfectly. Curvature alone does not
predict it. Rule refused; the honest test is to build it and see.

### So the handling is: build what builds, and say which bend did not

Already true per piece - that is why the user's "not stitched" build came out.
What was missing was a legible report, so `FoldPlan.summary()` now says:

```
warning: BEND_6: built in more than one way (7 faceted, 9 wrapped). A bend that
only partly builds usually means its bend area does not match the board there -
worth checking in Allegro.
```

A bend that comes out UNEVEN is the signal. A bend that is entirely faceted is
just an unusual shape; a bend where some layers are exact and some are not is a
bend area that does not fit its board.

### The GUI vanished, and I could not make it

The user's "solid colored layers" run closed the window with no message. Five
reproductions on the same machine, same board, same settings: `layers`, `solid`,
`inspect`; the CLI; the GUI's own worker thread; and under `pythonw` where the
GUI actually runs. All completed - 40 s, 485 MB peak. So the crash is not in
the code path as such, and hunting it further from here is guesswork.

What it means for the design: **a hard crash in OCC kills the process, and the
build runs in a WORKER THREAD, so the window disappears with nothing written
anywhere.** Isolating the build in a subprocess would turn any such crash into a
line in the log - proposed, not built, because it is a real change to a working
GUI and the user should decide.

Asked of the user: run the same build from a console (`python -m stepbuilder
... --board-mode layers`) so whatever OCC prints on the way down is captured.

### `foldSliceAngle` is a setting now

The user had edited `DEFAULT_SLICE_ANGLE = 7.5` to 5.0 **in their installed copy
of bend.py**, which is how the difference showed up in the first place. It is a
config key and a CLI flag now, so nobody has to edit source to change it.

**Their install is a hand-copied tree and they edit it.** Diffing it against the
repo took one command and settled what was actually running - do that first,
before reproducing anything.

### A self-inflicted one worth keeping

Editing README.md with `Get-Content -Raw | ... | Set-Content -Encoding utf8`
destroyed the Russian half: PowerShell 5.1 reads with the ANSI codepage, so the
UTF-8 bytes came back as cp1251 mojibake and were written out again as UTF-8.
Recovered by inverting the mapping byte by byte (cp1251 has undefined slots that
pass through as raw code points, so the strict codec cannot do it alone). Same
family as the heredoc trap: **do not round-trip a file through PowerShell.** Use
the editor, or Python with the encoding named on both ends.

## Update 2026-07-26 (round 38) — the mapper, on branch `feature/bend-mapper`

Round 37 left the exact bend refusing every piece of the real board. This round
is the general construction the user proposed, in the reduced form our shapes
allow, and **it now wraps every piece of both bends on flex-b2.**

### The one property everything rests on

In the cylinder's own PARAMETER space - angle across the bend, distance along it
- the bend map is **affine**: `angle = (distance across) / neutral radius`, and
the distance along is untouched. An affine map takes a line to a line and a
circle to an ellipse and bends nothing. So the flat outline is carried into that
space and the two faces of the bent strip are built ON the cylinder, exactly,
whatever the outline does.

The user's algorithm proposed discretising every edge and refitting splines.
That is not needed and, as it turned out, not safe (below). What IS needed:

- **the same 2D outline serves both cylinders**, inner and outer - one curve,
  two radii - which is what keeps them in registration;
- **a ruled wall per boundary edge** (`BRepFill.Face_s`), which is a radial
  plane where the edge ran along the bend, a plane at constant distance where it
  ran across, and the ruled surface between two helices where it ran at an
  angle - which is what it physically is;
- sew, make a solid, check it.

Everything the input analysis in the proposal would have done - is it a sheet,
how thick, where is the neutral surface - we already know, because we build the
solid ourselves. The only precondition left is that the piece is **a prism
standing on a flat face**, which is checked by measurement: top area x thickness
must equal its volume.

### Four defects, each found by measurement on the real board

**1. Sampled splines are not safe next to a straight edge.** Fitting a relief
notch through 39 points puts a wiggle of nanometres at its ends, where it meets
the straight edge it was cut into; OCC then calls the wire self-intersecting and
throws the solid away. **Every FLEX2 layer of the real board failed exactly
there.** Fixed by mapping circles analytically to ELLIPSES - closed form, no
wiggle - which is the case that matters, since notches, fillets and drill holes
are all circles. Splines remain only for whatever is neither line nor circle.

**2. OCC's default volume integrator is wrong on B-spline faces.** A wrapped
solid measured **1.5% light** through `VolumeProperties_s(shape, props)`, and
that sent every piece back to the facets - a defect in the MEASUREMENT, not in
the geometry. The iterative overload `(shape, props, 1e-5, False, False)` agrees
with the closed form to 2e-6. The test suite's own `volume()` helper had the
same bug and now uses the overload too.

**3. A bend does not conserve volume per layer, and must not.** The map
multiplies volume by `r / rho`, so a layer above the neutral surface is
compressed and one below is stretched. Measured on the stiffener zone: 0.937 for
the top coverlay, 1.000 for the dielectric at the core, 1.063 for the bottom
coverlay - symmetric about the middle, which is the bend being isometric. The
check now asks for `volume x r_mid / rho`, which is exact for a prism; asking
for the flat volume back rejected every layer but the one at the core.

**4. In `solid` mode the fold ran after the zones were fused**, so a bend area
that reaches across a zone boundary - 0.16 mm into the stiffener on this board -
gave a piece with two thicknesses, which is not something that can be wrapped
onto one pair of cylinders. Solid mode now folds each LAYER and fuses
afterwards, like the layer-colored mode, and the fuse gives the same solid.

Plus: a layer that arrives as several disjoint solids (a stiffener the bend area
clips at both ends is two) is wrapped piece by piece rather than sewn into one
impossible shell.

### Measured on flex-b2

| | before (facets) | after (wrapped) |
|---|---|---|
| BEND_2 | faceted | 16 of 16 layer pieces wrapped |
| BEND_1 | faceted | 7 of 7 wrapped |
| solid build | 9.8 s, 6429 kB | 14.6 s, 7316 kB |
| volume | 3501.52 | 3499.91 |

The volume difference is the isometry: the stack is not symmetric about the
bend's neutral surface once the stiffener reaches into the bend area, so a few
tenths of a percent is expected and is in the right direction. `solid` and
`layers` agree to 0.001 mm3.

### Kept: the revolve, and the facets

Three constructions, tried in order - revolve, wrap, facets - and the log says
which each bend got, once per bend per way, with the REASON when it falls back
(`the piece is not a prism standing on a flat face`, `the solid built from them
is not valid`, ...). The revolve stays because it is cheaper and gives six faces
where the wrap gives ten; the facets stay because something will eventually turn
up that neither takes, and a board that folds roughly beats an export that dies.

### Verified
18/18. New sections: the wrap against the revolve on a shape both can build
(they agree to **2.7e-15** - two independent constructions of the same solid),
a relief notch, a hole through the bend area, the isometry (a thin layer above
the neutral axis loses exactly `r/rho`), and a slanted cut still falling back to
the facets with its reason printed.

## Update 2026-07-26 (round 37) — the anchor, the K factor, and true cylinders

### Allegro's 3D anchor: found, understood, and unusable

`Setup - Anchor 3D View` (command `anchor 3d view`, `allegro.men:618`) asks for
a point and prints *"Using (1.9900 1.1600) as anchor for 3D viewing"*. Its
messages (`share/pcb/text/spmha2.xml`, ids 119-123) define it exactly as the
piece that stays in plane: *"Pick a point within the design outline"*, *"Point
cannot be inside a bend"*.

The property it goes to is **`ANCHOR_POINT_3D_VIEWER`** — found in the property
name table inside `allegro.exe`, since it is in no reference. It is declared
(`axlDBGetPropDictEntry`: `dataType "UNITS_ARRAY"`, `objects ("designs"
"layouts")`, `readOnly t`) and **it is never given a value**: empty in
`axlDBGetProperties` immediately after setting the anchor, absent from
`design->prop->??` (which lists only properties that have one), still nothing
after a save and a reopen, and not in any of the 27 attachments. `3DX_BENDS`,
the promising-looking one, holds the 3D canvas's per-bend slider state:
`{"format_version":1,"visual_bends":[{"name":"BEND_1","value":0.0}]}`.

Four probe rounds to conclude "the data is not there". Worth it — the
alternative was a heuristic nobody could check.

**So the anchor is a convention: the origin.** `gui.foldAnchor`, default
`[0, 0]`, documented in the README, the quick start and the config. It answers
one question per bend, which side is held, and that is a signed distance - so
it need not be inside the outline, and the origin sitting exactly on a corner
costs nothing. `"auto"` still holds the largest piece. The Allegro property is
read opportunistically (`data["anchor"]`), so a version that starts filling it
in wins automatically.

**The anchor decides the SHAPE of the fold, not just its position.** With it in
the middle of the test board, two tails swing off a held centre; at the origin,
the same two bends are a chain and the board swings as one. The relative
geometry is identical - it is a rigid motion of the whole assembly - which is
why the user's "it bends in the right places" verdict survived the change.

### K factor

`gui.foldNeutral`, default 0.5. It sets the material a bend consumes:
`angle x (radius + k x thickness)`. k = 0 reproduces Allegro's own bend area
exactly, which is the round-36b finding restated: their drawn area is the inner
arc, not a bend allowance.

### True cylinders, and why the real board does not get them

The bend map sends (u along the bend, v across it, z) to (u, angle, radius):
**u is untouched, v becomes the angle, z becomes the radius**. So if the strip
is the same shape at every v, the bent strip is exactly its cross-section
**revolved** about the bend axis - `BRepPrimAPI_MakeRevol`, six faces, two of
them true cylinders, no sewing and no repair. Measured on a test strip: volume
identical to the flat one to nine decimals (the faceted path costs +0.07% in
deliberate slice overlap), 6 faces against 50, and the rim area exactly the flat
perimeter times the thickness.

The precondition is checked by **measurement, not topology**: one cross-section
times the strip width must equal the strip's volume, with the section taken a
quarter of the way in, where a taper shows. Anything else - a taper, a hole, a
zone boundary, a fillet - fails it and falls back to the facets, per shape and
per bend, with one log line each way.

**On the user's real board it never fires, and the reason is structural.** The
board outline carries **relief notches** - half circles of r = 0.5 centred on
each END of the bend line, cut so the flex does not tear - and they sit inside
the bend area:

```
outline vertices inside BEND_2's band (y 11.2185..12.5415):
  (0.0000, 11.3800) (0.1913, 11.4181) (0.3536, 11.5264) (0.4619, 11.6887)
  (0.5000, 11.8800) ...  (15.5000, 11.8800) ... (16.0000, 11.3800)
```

That is a notch at each end of a 16 mm bend line, exactly on the bend line's own
y. There is also a zone boundary (STIFFENER2 ends at y = 11.38) 0.16 mm inside
the band, so the per-zone layer solids are partial in v as well. Every one of
the 37 layer solids fails the prism test, most by a wide margin.

**Do not "fix" this by loosening the tolerance.** The notches are real geometry
0.5 mm across; revolving through them would fill them in. The honest conclusion
is that the revolve is a fast path for simple strips and that a real flex board
needs the general construction - map each face's boundary onto the cylinder -
which is the next piece of work. The insight that makes that tractable is
already proven here: the map is an axis scaling in the cylinder's PARAMETER
space, so a line stays a line, an arc becomes an ellipse and a spline stays a
spline; nothing needs discretising except ruled side walls over slanted edges.

### A defect the exact path introduced, caught by the rim test

With true cylinders in the model, `_rim_faces` painted the inside and outside of
every bend as rim - it treated any curved face as a side wall. Measured: 77.7
mm2 of "rim" where the strip's rim is 40. A cylinder is now told apart by its
AXIS, in the panel's own frame: a drill runs through the board, a bend runs
along it.

### Verified
18/18. The bend suite grew to 17 sections: the anchor (default, "auto", an
explicit point, one outside the board), the K factor against three values
including Allegro's k = 0, the exact construction (cylindrical faces, volume to
1e-6, the outside of the bend exact), and the fallback (a notch cut at the end
of a bend line is noticed, the bend is faceted, and the notch survives with its
wall intact). The real board still folds: volume 3501.52 against 3501.32 flat,
both arms away, five zones, no boolean failures.

## Update 2026-07-26 (round 36b) — the live half, and what it corrected

The user ran `probe_bend.il` and the export on **flex-b2** the same day. Three
things came back: the data path is right, and two pieces of it were wrong.

### What the probe settled

- **The bend group is `BEND_GROUP`**, named exactly as `axlGetBends()` names the
  bend, with **four** members: the `BEND_AREA` shape, the `BEND_LINE` path, and
  a `PACKAGE KEEPOUT/ALL` plus a `VIA KEEPOUT/ALL` shape (both carrying
  `IDX_EXCLUDE`). Reading by layer name picks the two that matter and ignores
  the keepouts. The group route works; the order-pairing fallback never fired.
- **A bend line's `->group` and `->groups` are nil**, exactly as a zone
  outline's are. Through the group is again the only way to keep the
  association.
- **The whole property**, at last:
  `TYPE=CircularBend, INNER_SIDE=TOP, INNER_ANGLE=28.2600, INNER_RADIUS=2.5000
  MILLIMETERS, ORDER=0, CREATE_VKO=1, VKO_OSIZE=0.0000 MILLIMETERS,
  CREATE_PKO=1, PKO_OSIZE=0.2490 MILLIMETERS`. The tail that was elided is just
  the keepout settings from the Create Bend Area form. Nothing needed for
  folding was hiding in it.

### Defect 1: property names are SYMBOLS, and this memo already said so

Every bend exported with `info: null` and the console said each one carried no
`IDX_BEND_TYPE_INFO` — while the probe printed it. `car(entry)` on an
`axlDBGetProperties` pair is a **symbol**, so `== "IDX_BEND_TYPE_INFO"` is false
however plainly the property is there.

`s3dObjectHasProp` has carried the fix since round 5, with a comment saying
"property names come back as symbols, hence the %L coercion" — and the new code
was written without looking at it. The value lookup is now `s3dPropValue`,
sharing that coercion, and both places use it. **The mechanical checks cannot
see this class of defect**: the call is well formed, the arity right, the name
defined. Only a live board or reading the neighbouring function would.

### Defect 2: Allegro's bend area is drawn at the INNER radius

The bend area came out **1.2337 mm** across for a 28.26° bend with R = 2.5.

| candidate | value |
|---|---|
| angle x inner radius | **1.2331** |
| angle x neutral radius (2.5 + 0.365/2) | 1.3232 |

It is the inner arc to within the rounding of its own four-decimal coordinates,
and there is no thickness term in it at all. So the BEND_AREA is the region to
keep vias and packages out of, **not a bend allowance**. Round 36 had decided
"the measured area wins over the computed length" — which would have folded 7%
too little material on every bend, and would have raised its disagreement note
on every board with a thin radius. Now the neutral-axis length is folded and the
drawn area is only checked against the inner arc, with a note when it is neither.

Also confirmed from the same shapes: the bend area is **symmetric about the bend
line** to four decimals (0.6168 one side, 0.6169 the other), which is the
documentation's "the bend line represents the midpoint of the bend", measured.

### Defect 3: the real board is not a chain, it is a tree

The two bends are at y = 11.88 (x 0..16) and y = 23.6 (x 25..41), folding
**opposite arms off the middle of the board** — one up, one down (`INNER_SIDE`
TOP and BOTTOM respectively). Neither lies beyond the other, and round 36's
chain check rejected the second one outright.

Rewritten as a tree: a bend is a child of every bend whose moving side wholly
contains it and takes the innermost of those as its parent; bends on different
arms are all children of the held panel. Only genuinely **overlapping strips**
are refused now, and the refusal drops that bend alone rather than everything
past it. Each strip and each moving panel also carries its ancestors'
constraints, so a bend line that spans only part of the board's width cannot
claim material on the far side of its parent.

### Verified on the real board, here

`flex-b2.json` as exported, with the two property strings pasted in from the
probe (which is what the fixed exporter will now write), built through
`generate()`:

- Both bends fold. The **held panel is the middle**, `12.62 < y < 22.86`, which
  is what a person would hold.
- Each bend picks up the **flex** stack through point-in-polygon: 1.323 mm of
  material folded, which is 28.26° x (2.5 + 0.365/2) exactly.
- No note about the bend area, no boolean failure, no warning except the
  pre-existing zero-width silkscreen text.
- Volume 3500.85 folded against 3501.32 flat — **0.013% apart**, and in the
  direction of losing a hair rather than inventing material.
- The board's extent goes from y −2.50..32.00, z −2.65..16.86 flat to
  y 1.30..31.08, z −6.35..20.27 folded: both arms swung away, one up, one down.
- `solid` and `layers` agree to 0.002%.

Still not looked at in CAD by a human — the numbers say the fold is right, but
whether the two arms end up where the product needs them is a question for the
model on screen.

### Left open

- The half-plane model is **sound on this board** but is still a half-plane
  model: a bend line that does not span the board's width at that point relies
  on there being no material out to the sides, which is true here (the bend
  area is trimmed to the outline and reaches both edges) and is not guaranteed
  in general. The proper fix is connectivity — cut the flat outline by the bend
  strips and walk the resulting faces as a graph. Not needed yet.
- `flex-b2.json` is the only real rigid-flex intermediate there is, and it lives
  outside the repo in the user's project. Copying it in as a fixture would make
  the fold regression-testable against real geometry forever; it is the user's
  design data, so it is their call.

## Update 2026-07-25 (round 26) — multi-stackup / rigid-flex

Requirement 11 (user): support multi-stackup, and bent flex boards. Bends were
scoped out for now — they need zones first, and folding is a whole other
problem. Multi-stackup is done.

### Round 7's "no reliable detection API" was wrong

It said there is no zone/stackup field on the xsection struct and fell back to a
conductor-count heuristic, which false-positived and was reverted. The API was
there the whole time; it just was not read far enough:

```
axlXSectionGet( nil 'stackups )        -> ("STIFFENER1" "FLEX" "STIFFENER2")
axlXSectionGet( <name> 'all )          -> that stackup's layers
axlXSectionGet( <name> 'thickness )    -> its exact total
design->groups, type "ZONE_GROUP"      -> the zones
zone->stackup                          -> which stackup a zone uses
zone->groupMembers                     -> the zone outline polygon
axlZoneAccess( 'point xy )             -> the zone containing a point
```

### Two defects this exposed in shipped code

1. **`axlXSectionGet( nil 'thickness )` returns ONE stackup's thickness on a
   rigid-flex board** — 0.49 on the test board, which is STIFFENER1, not the
   board. `calculateBoardThickness` calls exactly that, so such a board was
   exported as a 0.49 mm slab everywhere, with 2.44 mm and 0.365 mm zones both
   silently wrong.
2. **The `SOLDERMASK*` name gate (round 2) reports zero on a flex stackup.**
   There is no SOLDERMASK layer there at all — coverlay, adhesive and stiffener
   sit outside the conductors instead. Hand-summing FLEX gives 0.215 against a
   true 0.365. The new code splits by POSITION relative to the outermost
   conductors, never by name.

### The load-bearing measurement: zones share the copper, not the surface

| stackup | above | core | below | total |
|---|---|---|---|---|
| FLEX | 0.075 | **0.215** | 0.075 | 0.365 |
| STIFFENER1 | 0.200 | **0.215** | 0.075 | 0.490 |
| STIFFENER2 | 2.125 | **0.215** | 0.100 | 2.440 |

Identical cores, wildly different totals. **Zones butt against each other at the
conductor stack**; a stiffener grows outwards from it, mostly upwards. Aligning
top faces — the obvious first guess — would tear the board apart at every zone
boundary. This is why a zone is emitted as three numbers and not as one
thickness, and it is not stated anywhere in the reference: it came out of the
probe data.

### Where the zone outline actually is

`zone->shapeBoundary` is **nil on every zone of a real board**, despite the
reference calling it the boundary. The outline is `car( zone->groupMembers )` —
a polygon on RIGID FLEX/ZONE_OUTLINE.

Sweeping that subclass directly finds the same polygons, but their `->group` and
`->groups` are nil, so that route cannot say which zone an outline belongs to.
**Going through the group is the only way to keep the association.** A fallback
sweep was written into the probe and is deliberately NOT in the shipped code.

Worth the note: a zone outline is an ordinary polygon carrying the same
line/arc segments as the board outline, so `boardGeometryParseSegment` reads it
unchanged. Nothing new had to be written for zone geometry.

### Shape of it
- SKILL: `s3dStackupProfile` (above/core/below by conductor position),
  `s3dZoneList`, `s3dZonesJson`; `symbolReturn3DElements` now emits the
  component's `"zone"` from `axlZoneAccess('point xy)`. `format_version` 4 → 5,
  new top-level `"zones"` (and therefore into `core._reserved` — third time
  that rule has mattered).
- Python: `zone_levels()` computes each zone's two faces off the shared core and
  applies the datum shift; `_zone_solid()` fuses the zone prisms;
  `component_transform` takes `zone_levels` and places a part on its own zone's
  surface, falling back to the board surface when the zone is unknown.
- Zones are **fused**, not left as a compound: the outlines are trimmed against
  each other and overlap slightly (0.14 mm on the test board), so a compound
  would carry doubled geometry along every seam. Four zones make this cheap —
  the opposite of the silkscreen case, where fusing thousands of prisms was
  measured and rejected.
- Cutouts on the zone path get a 0.01 mm margin past both faces. The
  single-stackup path keeps its exact extents deliberately: that is what the
  C++-verified regression measures.

### Verified here
19 assertions built from the REAL zone data of the user's board: the three
profiles reproduce the API totals exactly; all cores equal; datum top and bottom
both land the right face on zero; every zone shares one core top; the built
volume matches the sum of the zones (slightly under, which is the fused overlap
— the right direction); a part on the stiffener sits exactly 2.05 mm above one
on the flex, and an unknown zone falls back to the board surface; and an
ordinary board produces no multi-stackup log and its old volume. All other
suites, the four SKILL checks, the docs audit and the C++ geometry regression
(12073.309477 / 5054 entities) unchanged.

### Not done, and why
Bends. The data is all there — bend lines are paths on RIGID FLEX/BEND_LINE
whose `segments[0]->startEnd` gives real endpoints (so a diagonal bend reads
fine), `axlGetBends()`/`axlGetBendInnerRadius()` name them and give the radius,
and everything else lives in an **undocumented** property:

```
IDX_BEND_TYPE_INFO = "TYPE=CircularBend, INNER_SIDE=TOP, INNER_ANGLE=28.2600,
                      INNER_RADIUS=2.5000 MILLIMETERS, ORDER=0, ..."
```

It appears in neither the API index nor the DB attribute reference, so its
format would have to be parsed by hand and trusted across versions. Folding
itself is the larger cost: bending solids, carrying components into the rotated
frame, deciding what silkscreen does across a bend. Comparable in size to the
whole current tool. Zones first was the right order — bends fold zones.

### Side finding, closing an old question
`axlDBGetProperties` entries are `(name value)` — a two-element list, not a
dotted pair. Open in this memo since 2026-07-18 and visible plainly in the probe
output: `((FIXED t) (IDX_BEND_TYPE_INFO "TYPE=..."))`. Both shapes are still
handled in `s3dObjectHasProp`, which is fine, but the question is settled.

## Update 2026-07-25 (round 27) — per-layer build, on branch `feature/per-layer-stackup`

Round 26's zone prisms were still wrong, and the user caught it by comparing
against Allegro's own export: at the stiffener height Allegro has **86.763 mm2**
where our prism put **171.761**, and the board body came to 598.85 mm3 against
268.47. A zone is not a uniform slab.

### Third rigid-flex reference, and it is the good one

`D:\Projects\AI\Claude\Allegro_DOC\algroRigidFlex\` — 14 HTML pages on zones,
stackups, bend areas and the Mask Layer Site File. Extracted to text in scratch.
This is where the polarity answer came from; the `axl*` reference does not have
it. See also [[allegro-rigidflex-docs]].

### Layers, not zones

Each stackup layer now carries its own extent and its own drawn shapes:

- **no shapes** → spans the whole zone (conductors, dielectric). The user
  confirmed independently: Inventor shows Allegro's dielectric as exactly four
  bodies, one per zone.
- **positive shapes** → the material IS those shapes, clipped to the zone,
  `voids` becoming holes (ADHESIVE_TOP has 7, STIFFENER_TOP and ADHESIVE_TOP2
  six each).
- **negative shapes** → the shapes are OPENINGS; material is the zone minus
  them.

### Polarity: three wrong answers before the right one

1. **`negativeArtwork`** — reads **nil on every layer** of a real board. It is
   about film generation. Do not reach for it again.
2. **"everything is positive"** — my reading of the shape geometry, and wrong.
   The user built it and saw the coverlay come out inverted.
3. **The right source is `layerFunction`** — the IPC-2581 Layer Function Type
   the Mask Layer Site File assigns, per the rigid-flex docs: *"The assignment
   of IPC Layer Function Type as defined by IPC-2581."*

The convention: coverlay / soldermask / pastemask are drawn as **openings**;
stiffener / adhesive / epoxy are drawn as **material**. Matching the user's own
notes (`Adhesive_top - pos, Coverlay_top - neg, Stiffener_top - pos`).

**The geometry said so all along and I read it backwards.** COVERLAY_TOP has a
shape matching the FLEX1 zone outline exactly. As material that would be the
only coverlay patch on a board needing it everywhere; as an *opening* it is a
flex tail with its contacts exposed, which is completely ordinary. Likewise the
six small COVERLAY_TOP shapes sit exactly in the six voids of STIFFENER_TOP —
windows through both, not islands of coverlay.

Implemented as `settings.negativeLayers` (substring match against the layer name
AND its function), defaulting to COVERLAY / SOLDERMASK / PASTEMASK, because this
is fabricator convention rather than something the database states outright.

### Layer ORDER: use the list, never `position`

`layer->position` **duplicates** (6 is both SOLDERMASK_TOP and the dielectric,
10 is both SOLDERMASK_BOTTOM and the bottom surface) and is not monotonic - it
indexes the combined "All Stackups" view. The order `axlXSectionGet(<name>
'all)` returns IS the physical order, checked line by line against the
cross-section editor.

Round 26's `s3dStackupProfile` compared positions and put SOLDERMASK_TOP inside
the core: **the total still matched**, so nothing looked broken, but the core -
the datum every zone aligns on - sat 0.025 mm low on one stackup. The kind of
defect a sum check cannot see.

Also: `axlXSectionGet(nil 'all)` returns the ALL-STACKUPS union (13 entries,
2.54) while `axlXSectionGet(nil 'thickness)` returns ONE stackup's 0.49. `nil`
is internally inconsistent on a multi-stackup board; never use it there.

### Fusing: measured, and the opposite of the silkscreen result

34 layer solids, non-overlapping zones so any loss would show:

| | size | faces | volume |
|---|---|---|---|
| compound | 564,659 | 204 | 711.7258 |
| fused | **144,509** | 142 | 711.7258 |

**25.6%**, volume identical to nine decimals. Stacked layers share large
coplanar faces and each solid costs its own product definition in AP214. The
silkscreen fuse came to 154% because thousands of thin prisms barely touch after
clipping - same word, opposite result, for the second time in this project.

`BRepAlgoAPI_BuilderAlgo` was tried first: it computes the boolean but leaves
the pieces as separate solids (18 out, one expected). The multi-argument
`BRepAlgoAPI_Fuse` plus `ShapeUpgrade_UnifySameDomain` is what works.

### Layer inspection build
`gui.debugLayers` / `--debug-layers` / a checkbox. Every layer stays its own
part named `<zone>__<layer>`, colored from a 12-entry contrasting palette keyed
on the layer NAME so one sheet keeps one color across zones. Cutouts applied
per layer. About 10x the file size; off by default. This is what let the user
see the inverted coverlay.

### Live confirmation
Ran on the real board. The stiffener level now reads **86.763 mm2, matching
Allegro exactly**; board body 389.2 against Allegro's 394.1 (was 598.9 vs
268.5).

### Verified here
19 assertions on negative/positive polarity (including the transliterated SKILL
matcher against all twelve real layer names), 12 on the inspection build, 12 on
the per-layer build, plus every earlier suite, the four SKILL checks, the docs
audit and the C++ geometry regression.

Three failures along the way were all in the tests, not the code: a wrong
`GetColor` signature, arithmetic using 2.44 where the built stack was 2.39, and
a hardcoded snapshot field count. The last is now a set of field NAMES, so it
says which field is missing instead of "16 != 15".

### "Ignore soldermask layers" (user, 2026-07-25)

A GUI checkbox, `gui.ignoreSoldermask`, `--ignore-soldermask`. The mask is left
out of the board however the design defines it, **and the rest of the stack
closes up toward the core** by exactly the thickness removed, each side
independently.

Two things worth keeping:

- **Removing a layer is not enough on its own.** The survivors keep their old
  heights and a gap opens where the mask was. `restack()` re-runs the same walk
  the exporter does - sum everything outside the top conductor, then hang each
  layer off that - which settles them toward the core. Verified on the real
  STIFFENER2: the top half drops exactly 0.025, the bottom half rises exactly
  0.025, the core does not move, and no gap opens at either copper face.
- **Decided at BUILD time, not at export.** Same principle as the silkscreen
  layer chooser (round 14): the exporter collects everything, the GUI decides
  what to build, so toggling needs no re-export.

A layer counts as soldermask if `SOLDERMASK` survives in its name or its IPC
function once non-alphanumerics are stripped, so `SOLDER_MASK_TOP` and a layer
named `SM_TOP` with function "Solder Mask" both match. The plain-board path
takes the same decision on `pcb.thickness`, since there the mask is two numbers
rather than two layers.

### Nested zones: there is no such thing — CORRECTION

Recorded here earlier as "Allegro supports it, this does not", deferred. **That
premise was wrong.** From `Creating_Multi-Stackup_Zones_in_the_Design_Drawing`:

> "**Zones cannot be overlapped or nested.** If a zone is added and
> intersects/overlaps with an existing zone, the newer zone will be trimmed to
> the existing zone boundary."

So what looks like a nested zone is, in the database, a **trimmed outline**: the
newer zone is cut to the older boundary and the outer one keeps a hole. They
reach us as disjoint polygons, which is why a flat list of zones is not merely
adequate but correct. The user confirmed nested-looking zones build properly.

Nothing to implement. The small overlaps we measured (0.14 mm at seams) are the
deliberate manufacturing overlap left by the trim, and the fuse absorbs them.

### Still open on this branch
- Bends are not folded; the board is exported flat.
- **Area not covered by any zone is not built.** Same doc page: *"Any area
  within the DESIGN_OUTLINE that does not have a zone is defaulted to the
  Primary Stackup."* `_stackup_board` walks zones only, so a board whose zones
  do not tile the whole outline gets a hole there. The test board's four zones
  evidently cover it, which is why this has not shown. The fix is to build
  `design outline − union of zone outlines` with the Primary stackup; the
  awkward part is identifying Primary, which this board does not have (its
  three stackups are all zone-assigned).
- Whether `layerFunction` alone is enough to decide polarity without the name
  list - `probe_func.il` was written to answer that and has not been run yet.

## Update 2026-07-25 (round 35) — four window nits

- **Dropdown widths cut to the longest entry.** Measured rather than guessed:
  the board theme was 16 characters wide for a 10-character `Dark_green`, the
  silk color 10 for `White`. Now 11 and 6. The rim (18 for
  `Cream (dielectric)`), Z datum (16 for `Bottom of board`) and stitching (21
  for `Solid colored layers`) were already at or near their minimum and barely
  moved.
- **A first run opens at a fixed 908 px wide** (`FIRST_RUN_WIDTH`), against a
  natural request of 1158. Board options keeps its natural width - it has
  weight 0 - so the squeeze lands on the silk column, and widening the window
  gives it straight back. A remembered geometry still wins over this.
- **Display swatches and picker swatches no longer look alike.** The board
  theme and the silk ink only REPORT what a dropdown chose; the rim and the six
  layer kinds OPEN a chooser. Pickers are now raised with a 2 px border and take
  the hand cursor, display squares are flat with a hairline. A picker that is
  currently inert - rim outside Custom, layer swatches in Solid - drops back to
  flat, so "looks like a button" and "is a button" stay the same thing.
- **The rim controls grey outside Solid**, which is the opposite of what was
  asked and the right way round: `generate()` has ignored the rim color in the
  other two stitchings since round 29, because they decide every face
  themselves. The user's phrasing had it inverted; said so and implemented the
  version that matches the code.

### Verified
Live window: first run 908x844, the five dropdowns at 11/18/16/21/6, rim
dropdown readonly in Solid and disabled in the other two, pickers raised only
while live, display squares never raised. Tests extended for the picker relief
and the rim state; the geometry suite needed its centring expectation moved
from the natural width to FIRST_RUN_WIDTH.

## Update 2026-07-25 (round 34) — silkscreen and paste were in the body

Round 33 made a plain board emit its cross section as a `Primary` stackup so
Body stitching would apply there. It emitted **every** entry
`axlXSectionGet(... 'all)` returns, which on an ordinary board includes
SILKSCREEN_TOP/BOTTOM and PASTEMASK_TOP/BOTTOM. Result on the user's
my_test_board-a0: nine layers where there should be five, and a stated
thickness of **1.204 mm against the board's real 1.104** - exactly four extra
0.025 sheets.

**This is requirement #1, from 2026-07-18**: dielectrics + planes + conductors
+ soldermask both sides, silkscreen and paste mask excluded.
`calculateBoardThickness` has honoured it since round 2; the per-layer emission
was written without it.

Two distinct wrongs, not one:
- the legend is already exported as its own geometry from the `silkscreen`
  section, so keeping it in the stack drew it **twice**, and the stack copy was
  a sheet over the whole board rather than the characters printed on it - which
  is what the user described as "a plane instead of elements";
- paste mask is a stencil aperture definition and is not on the finished board
  at all.

`s3dLayerInBody` now drops both before anything is measured, so the z walk
closes the survivors up against the core and no gap is left. Thickness is the
sum of what is kept rather than the API's `'thickness`, which counts
everything.

**Why it hid for two rounds:** the rigid-flex test board's three stackups carry
no silkscreen or paste entries at all, so every check up to here passed. It
took a plain board to show it.

**It covers rigid-flex too, by construction**: `s3dStackupJson` is the only
emitter and both call sites - the named stackups and the Primary fallback - go
through it, with the filter as its first act. Asked directly, and checked
rather than asserted: a flex stack carrying paste and legend loses exactly
those four and keeps coverlay, adhesive, stiffener and soldermask.

The markers were shortened from SILKSCREEN/PASTEMASK/SOLDER_PASTE to just
**SILK** and **PASTE** while checking that: a design naming a layer `PASTE_TOP`
and setting no `layerFunction` would have slipped through the long forms.
Nothing else in a cross section contains either string - not coverlay,
adhesive, stiffener, soldermask, conductor or dielectric - so the short test
cannot over-match, and `SOLDERMASK` is explicitly checked not to be caught.

Verified by transliterating the filter against the user's actual Primary: 9
layers -> 5, total 1.104 matching `pcb.thickness` exactly, top copper still at
z=0, no gaps. Plus a check that SOLDERMASK is not swept up by the SOLDER_PASTE
test.

## Update 2026-07-25 (round 33) — stitching on plain boards, and two labels

### Body stitching used to do nothing unless the board was rigid-flex
The setting was there on every board and silently ignored on most of them.
Fixed by making the ordinary case a case rather than an exception:

- **SKILL**: a board with no named stackups now emits its cross section anyway,
  under the name Allegro itself uses for the default - `Primary`. `nil` is safe
  as the query there ONLY because there are no named stackups; on rigid-flex,
  `nil 'all` returns the combined "All Stackups" view, which is no real stackup
  (round 27). `s3dStackupJson` took the name and the query as one argument, so
  it now takes them separately.
- **Python**: with one stackup, no zones and a non-solid mode, the board outline
  becomes one implicit zone and every mode works everywhere. Plain "Solid" still
  takes the single-prism path - that is what the C++ regression measures.
- An intermediate written before format_version 6 has no layers to stitch by,
  and now **says so** instead of quietly building a plain solid.

Verified: on a plain 2-layer board all three modes give the same volume and the
same 1.104 mm Z extent; "Not stitched" separates it into layer parts; the old
JSON warns and falls back.

### Two labels
- **Silk White was 242, not 255**, on the reasoning that printed ink is never
  pure and pure white vanishes against a white mask. The user pointed out it
  reads plainly grey beside the window's white entry fields - and the swatch is
  meant to show what you get. Now 255. The 13 points never saved the
  white-on-white case anyway. Black stays at 26: a true zero renders as a hole
  rather than a surface in several viewers, and nothing looks wrong about it.
- "Ignore soldermask layers" -> **"Do not include soldermask layers / (check
  total thickness!)"**, two lines. `ttk.Checkbutton` takes a newline in its text
  and lays it out on two lines (46 px against 23), no wraplength needed.

### The heredoc trap, fourth time in three rounds
A scripted edit carrying `
` was mangled again, and this time it asserted on
its fourth substitution - which meant the file was never written and the three
earlier substitutions were lost with it. Accidentally atomic, but only by luck.
**Anything containing a backslash goes through the editor, not a Bash heredoc.**

## Update 2026-07-25 (round 32) — two console/layout nits

- **Ten `axlDBGetShapes` warnings per export, gone.** The layer shapes were
  asked for by name, once per stackup layer, so every conductor, the dielectric
  and the soldermask - never drawn on the RIGID FLEX class - produced
  `*WARNING* No match for subclass name`. Now the whole class is fetched once
  and grouped by subclass: a miss cannot happen, because a layer absent from
  the table simply has no shapes. Also 1 query per export instead of 11 per
  stackup. Verified by transliterating the grouping against the real shape list
  from the user's board - the 4 layers that warned are exactly the 4 with no
  shapes.
- **Widening the window now grows Silk, not Board.** Both columns had weight=1
  and split the slack evenly, which only padded Board options with blank space:
  it is a fixed set of dropdowns and swatches. Board is weight=0 now, so it
  stays at its natural 638 px at any window width, and the silk layer list -
  a column of names that really are long enough to clip - takes everything
  else. Measured 1204..1900 px wide: Board 638 throughout, Layers 522 -> 1218.

## Update 2026-07-25 (round 31) — the round-30 suggestions, and one spelling

User declined the preset picker (a mock-up, `picker_demo.py`, was built and
shown first - it stays in scratch), asked for a **Reset colors** button, and
took the rest of the round-30 list.

### Done
- **Reset colors**, at the end of the swatch row so its scope is unambiguous:
  those swatches, back to Allegro's material defaults. The board theme and the
  rim have their own controls and are left alone. Greys with the swatches.
- **Board and Silk side by side**, not stacked.
- **Z = 0 at is a dropdown**, one row instead of a row of its own. The variable
  still holds "top"/"bottom", so the config and every caller are untouched.
- **"Minimise file size" → "Compact STEP (reuse component geometry)".** Two
  controls both saying *size* and meaning different things is what prompted
  this; the silk one keeps the wording the user chose.
- **The whole Silk group greys when both sides are off**, not just the layer
  rows. The two side checkboxes are deliberately left live - they are how it
  comes back.

### The layout numbers, because the first attempt was worse than what it replaced

| | width | height |
|---|---|---|
| stacked (round 30) | 1038 | 1004 |
| side by side, first try | **1635** | 814 |
| side by side, long rows wrapped | **1204** | 844 |

Side by side buys 160 px of height but costs width, and the first attempt cost
far too much of it: Board options alone asked for 923 px because the stitching
dropdown, six swatches and the Reset button shared one line. Moving the swatches
to their own row, and "Make surface" to its own, brought the group to 654 and
the window to 1204x844 - comfortable on 1080p, where 1004 tall was not.

**Measure the request, not the appearance.** `winfo_reqwidth` on each frame
found the 923 immediately; the rendered window looked fine because it had been
restored to a saved geometry and was simply clipping.

### colour -> color, everywhere
User asked which is right in standard American English. It is **color /
colors / colored**; "colour" is British. The project was mixed: config keys and
Python identifiers were already American (`layerColors`, `board_color`), while
every UI label, comment and doc sentence was British. 237 replacements across
10 files, none in identifiers that anything external depends on. OCCT and
tkinter were never a risk - `Quantity_Color`, `XCAFDoc_ColorTool`,
`colorchooser` are American already, so a blind `colour`->`color` could not
collide with them.

## Update 2026-07-25 (round 30) — the window regrouped

User's list, after using round 29 live. All done.

### What changed
- **One "Options" block became "Board options" and "Silk options"**, after
  Input. The old block held the board and the legend in one list, so two
  unrelated halves of the window read as one set of settings.
- **The rim color is a picker, not a typed hex string.** Same idiom as every
  other color in the window, and it cannot be handed a value that does not
  parse. Greyed until Custom, like the field it replaces. `boardEdgeCustom`
  still stores `#RRGGBB`, so existing configs are untouched.
- **"Body stitching"**: Solid / Solid colored layers / Not stitched.
- **"Not stitched" now uses the SAME per-kind palette** as the colored mode
  instead of the contrast palette round 29 gave it. The user asked for this and
  it is the better answer: switching between the two now changes how the board
  is put together and nothing else, so the two pictures are comparable. The
  contrast palette (`LAYER_PALETTE`, `layer_color`, `_layer_order`) is gone.
- **"Flat (about 1/4 the size)" → "Make surface (minimum file size)"**.
- **"Minimise file size" stands on its own** between the groups and the log: it
  shrinks the whole file, component models included, so it belongs to neither
  group.
- Silk layers stay a nested LabelFrame, now "Layers", with a separator above it.

### Measured after the rework
Groups land in order (Input 8, Board options 224, Silk options 414 with Layers
nested at 72 inside it, Log 666). **Natural window height grew 876 -> 1004**,
which is worth knowing: on a 1080p screen a first run now centres a window that
nearly fills the height. Not fixed, listed below as a suggestion.

### Suggestions put to the user (not implemented)
1. Board options and Silk options side by side instead of stacked, or the silk
   Layers panel down from 96 px to ~72 - either buys back the 128 px.
2. "Minimise file size" and "Make surface (minimum file size)" both say size and
   mean different things; one of them could be reworded.
3. Board color is 8 fixed themes while the rim and the layers are free pickers.
   One idiom would be better than two.
4. "Z = 0 at" is two radios on a row of its own; a dropdown would save a row.
5. Silk options could grey wholesale when both Top and Bottom are off, the way
   the layer list already does per side.

### The audit earned its keep again
It caught the quick-start still naming an "Options" frame and a "HEX color"
control, both gone. Two of its own rules needed widening for the new window -
the group whitelist and the control list - which is the maintenance this kind
of check costs and is still cheaper than re-reading the prose.

## Update 2026-07-25 (round 29) — three board modes, color per layer kind

User asked whether the board could be ONE solid and still show a color per
layer on its rim, the way Inventor shows it. It can, and the answer is a single
line of the pipeline.

### UnifySameDomain is the thing that destroys it

It is what makes the ordinary build small - it merges the coplanar faces every
layer interface leaves behind - and merging them is exactly what welds the
stack into one surface. Measured on the real STIFFENER2, eleven layer solids:

| | solids | faces |
|---|---|---|
| compound | 11 | 66 |
| fuse + UnifySameDomain | 1 | **11** |
| fuse only | **1** | **47** |

So: fuse, skip the unify, color the faces. Volume identical, one solid on
re-import, 11 distinct face colors survive the STEP round trip.

**Which face came from which layer is taken from the boolean's own history**
(`BRepAlgoAPI_Fuse.Modified`), not from geometry. A z-band lookup would be
ambiguous the moment two zones put different layers at the same height, which
is the normal case.

### Cost, measured with ONE writer and all three colored

| mode | size | |
|---|---|---|
| solid (fuse+unify, one color) | 12,589 | |
| **layers** (fuse, color per face) | **59,475** | 472% of solid, 67% of inspect |
| inspect (separate parts) | 88,769 | |

The first attempt at this comparison was wrong and worth remembering: `solid`
and `inspect` were written with `STEPControl_Writer` (geometry only) and
`layers` with `STEPCAFControl_Writer` (colors + structure), which made the new
mode look 159% of a compound it was actually cheaper than. **Compare like with
like, or do not compare.**

### Three modes, one dropdown

`gui.boardMode` = solid / layers / inspect, replacing the `debugLayers` boolean
added in round 27 (read once for migration, then dropped from the file - same
pattern as `stepDir`). A dropdown rather than more checkboxes because the three
are alternatives: "inspect + layer colors" ticked together would have to mean
something, and it does not.

Beside it, a row of six clickable swatches - copper, base, coverlay, adhesive,
stiffener, soldermask - opening the stdlib `colorchooser`. Greyed rather than
hidden outside `layers` mode: a row that appears and disappears makes the
window jump.

**The defaults are Allegro's own material colors**, read off the test board's
`3DX_APPEARANCE` attachment during the round-25 investigation
(`3d_color_outer_conductor_material` 0xB87333, `_dielectric_` 0xFCFFD6,
`_coverlay_` 0xF29440, `_soldermask_` 0x1A5924). So a layer-colored export
looks like the same board does in Allegro's canvas rather than like an
arbitrary palette. Adhesive and stiffener have no Allegro entry; grey and FR4
green.

Layer kind is decided by type first, name second: a conductor is a conductor
whatever it is called, while everything outside the core is a MASK layer and
only its name distinguishes coverlay from adhesive.

### Both non-solid modes now ignore the board and rim colors
They have already decided every color on the board. A whole-shape color
applied over the top would either be ignored or, worse, win - and paint the
stack one color, which is the one thing those modes exist to avoid. Says so in
the log rather than silently.

### Three self-inflicted stumbles, all caught by tests
- `TopTools_ListIteratorOfListOfShape` does not exist in these bindings;
  `TopTools_ListOfShape` is directly iterable in Python.
- `make_board_layer_parts` returned the layer NAME where the color code needed
  the layer DICT (type and function decide the kind). Now carries the dict.
- **A scripted edit to the test file replaced nothing and said so only because
  the next run showed the block missing.** Then the anchor with `\n` in it
  failed to match at all, because the heredoc mangled the backslash - the same
  trap as round 14a and round 28, twice in two rounds. Rewrote it line-wise
  with an assertion. *Anchor on text with no backslashes, and assert.*

## Update 2026-07-25 (round 28) — full review of the branch

~920 lines added across 8 files. Every suite, all four SKILL checks, the docs
audit and the C++ geometry regression clean before and after.

### The one that mattered: a name collision the arity checker caught

Adding a JSON escaper, I called it **`s3dJsonStr` - a name already taken** by the
JSON READER's string parser (`s3dJsonStr( t_txt x_i )`, round 10, which is how
`simple3d_config.json` is read). SKILL takes the last definition, so all six of
my one-argument calls would have gone to the two-argument reader, breaking both
the new emission and config loading.

`check_arity.py` reported it immediately: *"s3dJsonStr( 1 args ) but defined to
take 2"*. Renamed to `s3dJsonQuote`. **This is the second time that checker has
paid for itself, and the first time it caught something before it ever ran.**
Nothing else in the toolchain would have: paren balance was clean, the string
check was clean, every Python test passed, and SKILL resolves names at call
time so the file would have loaded happily.

### Fixed
- **Unescaped names in the intermediate.** Layer, stackup and zone names went
  into the JSON verbatim. One quote or backslash in any of them breaks the whole
  file - not one entry, the export. `s3dJsonQuote` now handles quote, backslash,
  tab and newline, and returns `null` for a non-string. Verified by
  transliteration against the `json` module on 9 hostile inputs plus the real
  layer names. Note the round-25 model-name path still SKIPS such names rather
  than escaping them; it could now be upgraded to use this.
- **Dead code**: `s3dStackupProfile` survived the round-27 rewrite but nothing
  calls it - the per-layer emission does its own walk. Removed. Its lesson lives
  on in `s3dConductorSpan`, which is used.

### Reviewed and found sound
- Zone/stackup/layer plumbing, the negative-layer path, `restack`,
  `drop_soldermask`, the inspection build, and the `format_version` 5 compat
  path (`zone_levels` / `_zone_solid` are still reachable for a v5 file - not
  dead).
- GUI: three checkboxes fit the row with room to spare (right edge 601 px in a
  1038 px window, measured, not eyeballed).
- Component placement, silkscreen, cutouts and the rim path all behave the same
  in the debug build, where `pcb_label` is None; every use of it is guarded.

### Noted, not changed
- The inspection build cuts each layer separately, so a dense board costs
  cutouts x layer-parts booleans. Fine for inspection, which is what it is for.
- `restack` trusts `thickness` to be present. The exporter always emits it; a
  hand-edited intermediate could raise KeyError.

### The heredoc trap, again
Writing the escaper's test through a Bash heredoc mangled the backslashes and
produced a Python SyntaxError - the round-14a lesson, arriving while testing an
escaper. Written to a file instead.

### The four mechanical SKILL checks now
Paren balance; string literals broken by a real newline; calls to procedures
defined nowhere; call arity. Each exists because something got past the previous
ones. Run all four after any scripted edit.

**They are in the repository now** (2026-07-25), with the whole Python suite:
`tools/` for the checks and the docs audit, `tests/` for the fourteen suites,
`tools/probes/` for the read-only Allegro diagnostics, and
`python tests/run_all.py` for all seventeen in about forty seconds. Output goes
to a gitignored `build/test-output/`. Until then they lived only in a session
scratchpad, so a new session began with no way to tell whether a change had
broken anything — a standing suggestion since round 14b, and one that mattered
the moment the next piece of work was going to be bends.

**Two mistakes worth keeping from the move itself:**

- Three suites wrote into their own directory rather than a subfolder, so the
  first commit carried sixteen generated `.step` and `.json` files into
  `tests/`. The path rewrite matched `Path(__file__).parent / "` and those
  three said `Path(__file__).parent` with nothing after it.
- **`git status --short` collapses an untracked directory to one line.** `??
  tests/` looked clean and was hiding all sixteen. Use
  `--untracked-files=all` before committing a new directory, and re-run the
  suite afterwards to prove the tree stays clean.
