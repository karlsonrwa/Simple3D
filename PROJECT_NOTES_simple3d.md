# Simple 3D export — project notes / handoff

Working memo for the "File → Export → Simple 3D" toolchain. Keep updated as work proceeds.
Companion to `PROJECT_NOTES_eskd.md` (same user, same Allegro install).

---

## READ THIS FIRST — state as of 2026-07-23

The rest of this memo is a round-by-round record, oldest first, and it is long.
Everything needed to pick the work up is here. Read a dated round only when you
need the reasoning behind a specific decision; the round headings say what each
one settled.

### Where things are

| | |
|---|---|
| Repo (this working copy) | `D:\Projects\AI\Claude\Test` — branch `main` |
| The user's install | `d:/Projects/OrCAD/Scripts/Simple3D/` — files are copied there by hand |
| Allegro SKILL reference | `D:\Projects\AI\Claude\SKILL\skill_doc\` — `skill/DOC/FUNCS/*.txt` is the useful part, plus `skill_db_attributes.txt` |
| `exportJson` (reference implementation) | `D:\Projects\AI\Claude\exportJson` — juulsA's ibom exporter; its silkscreen traversal and text handling were the model for ours |

Three pieces ship: `makeVariant3dIntermediates.il` (reads Allegro, writes JSON),
`simple3d.il` (menu item + launcher), `stepbuilder/` (Python + OpenCASCADE,
writes the STEP). Plus `simple3d_config.json`, which holds **every** user
setting and is read by both halves. Only `S3D_ScriptDir` remains in SKILL
source, because the config is found relative to it.

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
- **Area agreement is necessary, not sufficient.** It cannot see compensating
  errors (two caps inverted opposite ways) or geometry faithfully reproduced
  from a source that is itself wrong (a mitred join). Both were caught by
  rasterising a face to text with `BRepClass_FaceClassifier` — cheap, and the
  first thing to reach for when a shape looks wrong but the numbers agree.
- **The settings file may only be written if it was understood at load AND at
  save.** Two separate rounds of data loss came from getting this wrong.

### Not verified outside Allegro

- Per-segment path conversion producing round joins on a live board. The SKILL
  side warns if a path yields fewer polygons than it has segments.
- Runtime and the 400-polygon clip batch size on a dense board.

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
| 8 | mechanical symbols + `NO_STEP_EXPORT` (user, 2026-07-23) | done in round 11; **extended in round 19 and confirmed live 2026-07-24** to mechanical symbols that carry a STEP model (`PKGDEF_STEP_FILE`) but have **no refdes** — they were silently dropped by the refdes gate before, now they export (`axlStepGet` on a mechanical instance returns the mapping; no `sym->definition` fallback needed). Export list comes from the design, the variant table only subtracts, so a symbol Variants.lst does not mention is exported in every variant. `NO_STEP_EXPORT` excludes outright and is logged by refdes — **confirmed live 2026-07-24: `axlDBGetProperties` sees the property and marked symbols are excluded.** |
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
ones. Run all four after any scripted edit — they live in scratch
(`skill_checks.py`, `check_arity.py`) and are still not in the repo, which is now
a standing suggestion three rounds old.
