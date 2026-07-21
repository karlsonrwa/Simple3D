# Simple 3D export — project notes / handoff

Working memo for the "File → Export → Simple 3D" toolchain. Keep updated as work proceeds.
Companion to `PROJECT_NOTES_eskd.md` (same user, same Allegro install).

## Environment (established)

- Allegro PCB Editor **17.4**, user tests live, gives console output / screenshots.
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
1. `simple3d.il` — NEW. Menu item, config (default model dir, default colour), path
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
`\`; no `cin.get()` (exit codes); sRGB colour (`--legacy-color` restores old); free-shape
diff instead of `for i=2`; single-walk file index; always `edges[0]` as outline; checked
ReadFile/Write status; error on open contours.

Not yet done: soldermask thickness is read from JSON and ignored.

## Open issue

`python -m stepbuilder` -> "No module named stepbuilder" on the user's machine. Cause is
almost certainly cwd/layout (the `-m` form needs the *parent* of the package on sys.path),
which will also bite when Allegro's `shell()` launches it with cwd = the design dir.
Fix direction: proper packaging (pyproject + console script) or an explicit-path launcher.
Must be settled as part of task 3, since the SKILL script has to invoke it reliably.

## Requirements (user, 2026-07-18)

1. Board thickness = dielectrics + planes + conductors + soldermask (both sides).
   Silkscreen and paste mask excluded. Example 2-layer: 1.464 + 0.045 + 0.045 + 0.025 +
   0.025 = 1.604.
2. Colour dropdown in the GUI, colours from `Allegro3DCanvasPreferences.xml`.
3. `simple3d.il`: menu item, config (default model dir + default colour), JSON to `cad`,
   launch GUI prefilled. Output name `<brd>_simple_DD_MM_YYYY.step`, `_` appended on collision.
4. Assembly: `symbols_top` / `symbols_bot` sub-assemblies at top level, unique names
   `refdes_<jsonname>`.
5. Minimise STEP file size; reuse component geometry.
6. Maintain this memo.

## Allegro3DCanvasPreferences.xml — what's in it

Path on user's machine: **unknown, need to confirm**.

8 FixedThemes: `Black, Blue, Dark_green, Green, Purple, Red, White, Yellow`.
`CustomThemes` is empty. `ActiveTheme = Dark_green`.

The colour the user perceives as "board colour" is the **soldermask** entry, and it is
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
- **Colour**: no transparency, pure soldermask RGB. Colours **hardcoded** in the script
  (no runtime XML read).
- **Board edge (rim)**: separate colour, exposed as a setting with documented values —
  same as board / cream dielectric / user-defined RGB.
- **Filename**: `board_simple_18_07_2026.step`. On collision the underscore **accumulates**
  (`board_simple_18_07_2026_.step`, `__`, ...) — deliberate, sorts better.
- **Variants**: export **all** of them, one STEP per variant.
- **Naming**: use the **MfrPN** user property (present on every component) as the part name.
  If a component lacks it -> warn and abort **without writing the JSON**.
- **Component colours**: mandatory, must be preserved — this is the point of the exercise.
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
- [ ] Board rim colour default (same as board / cream / custom).

## STATUS: requirement table — LIVING, keep current

First written 2026-07-18, when all six were implemented. Unlike the dated round
entries below, this table is **not** a historical snapshot: revise a row in place
whenever a later round changes that requirement's state, and name the round that
changed it so the trail stays followable. Last revised: round 9 (2026-07-21).

Delivered files (as of 2026-07-18; the `exportstep_fixes.il` overlay was folded
into `makeVariant3dIntermediates.il` in round 4 and no longer exists):
- `exportstep_fixes.il` v1.1 — SKILL overlay (thickness, addIndent, mfr_pn, pre-flight).
- `simple3d.il` v1.0 — File→Export→Simple 3D menu, pcb→cad, launches prefilled GUI.
- `stepbuilder/` — Python package: core.py, colors.py, gui.py, __main__.py.

| # | requirement | status |
|---|---|---|
| 1 | mask thickness in board | done; core.total_board_thickness: board+both masks. Verified 1.104. Limitation: mask layers count only if named `SOLDERMASK*` (round 2 decision) — a stackup naming them otherwise contributes 0.0 silently. |
| 2 | colour dropdown in GUI | done; colors.py: 8 themes from XML, dropdown + swatch. |
| 3 | simple3d.il menu, pcb→cad, dated name, prefill | done; anchor 3d_export_ui; --dated-name accumulating _ |
| 4 | symbols_top/bot, unique names `refdes_<jsonname>` | **PARTIAL** — groups and shared parts done (part = model file). The `refdes_<jsonname>` instance naming this requirement asks for was **removed in round 8** as over-complication, so no reference designator survives into the STEP at all. The requirement itself was never withdrawn: either restore the naming or amend requirement 4. |
| 5 | minimise size / reuse | done; surfacecurve.mode=0 (~49% smaller) + one shared part per model |
| 6 | MFRPN in json | **DISABLED in round 8** — property attachment proved unreliable in practice. Every branch is commented out, not deleted, in both `.il` files and all three `.py` files, marked `MFRPN DISABLED (kept for future)`. Nothing writes or reads `mfr_pn` now. |

### Verification done here
- Core geometry still bit-for-bit vs C++ (V=12073.309477, 5054 ents) with mask zeroed.
- Mask thickness: board 1.036 -> 1.096 with 0.03+0.03 demo masks; z_datum top/bottom both correct.
- Assembly tree: board -> PCB / symbols_top / symbols_bot, shared part across 3 instances.
- CLI single / dated-name collision / batch variants all pass.
- GUI rendered under Xvfb: colour dropdown+swatch, rim dropdown, z radios, checkboxes;
  Generate works; --gui prefill launch fills paths + colour.

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
6. **Rim colour bug** (point 3): _top_and_bottom_faces classified by z-position,
   but a straight board's side walls have z_com == mid exactly, so `>= mid` swept
   them into "top" and the rim colour landed on a flat face. Replaced with
   _rim_faces() classifying by NORMAL: vertical walls (|normal_z|<0.5) = rim,
   curved cutout walls included. Verified: 4 walls plain, 5 with a hole, flats
   excluded; cream rim + green board both present as distinct colours.

Full consolidated regression: 7/7 pass. Core geometry still == C++ 12073.309477.
ruff: only E501 line-length (cosmetic), no F-code (functional) issues.

### Still user-verified only (Allegro 24.1)
- The two SKILL files loading and running clean (balance OK, builtins all proven).
- pythonw path correct on the user's machine (or set S3D_PythonW).
- The wrong Variants.lst: user should delete/replace it - the script now says so.

## Update 2026-07-18 (round 7)

1. **Coloured log** (point 1): tk Text tags - warning #d9791e (orange), error
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
- Rim colour on a real board with cutouts.
- Coloured log appearance on the user's Windows tk theme.

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
4. **GUI swatch moved.** The board-colour swatch was pushed to the right edge by
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
   `_snapshot()` calls `_rim_color()`, so the early colour validation still
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
   Still uncoloured by design: `if not roots` (`core.py:605`) logs nothing at
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
  two warnings coloured, four neutral lines untouched.
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
- Log colours on the user's Windows tk theme.

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
