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

## STATUS: all six requirements implemented (2026-07-18)

Delivered files:
- `exportstep_fixes.il` v1.1 — SKILL overlay (thickness, addIndent, mfr_pn, pre-flight).
- `simple3d.il` v1.0 — File→Export→Simple 3D menu, pcb→cad, launches prefilled GUI.
- `stepbuilder/` — Python package: core.py, colors.py, gui.py, __main__.py.

| # | requirement | status |
|---|---|---|
| 1 | mask thickness in board | core.total_board_thickness: board+both masks. Verified 1.104. |
| 2 | colour dropdown in GUI | colors.py: 8 themes from XML, dropdown + swatch. |
| 3 | simple3d.il menu, pcb→cad, dated name, prefill | done; anchor 3d_export_ui; --dated-name accumulating _ |
| 4 | symbols_top/bot, unique names | done; part=model file, instance=refdes_json, +MFRPN flag |
| 5 | minimise size / reuse | surfacecurve.mode=0 (~49% smaller) + one shared part per model |
| 6 | MFRPN in json | exportstep_fixes writes mfr_pn; z_datum parts sit on mask |

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
