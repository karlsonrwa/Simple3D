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
changed it so the trail stays followable. Last revised: round 10 (2026-07-22).

Delivered files (as of 2026-07-18; the `exportstep_fixes.il` overlay was folded
into `makeVariant3dIntermediates.il` in round 4 and no longer exists):
- `exportstep_fixes.il` v1.1 — SKILL overlay (thickness, addIndent, mfr_pn, pre-flight).
- `simple3d.il` v1.0 — File→Export→Simple 3D menu, pcb→cad, launches prefilled GUI.
- `stepbuilder/` — Python package: core.py, colors.py, gui.py, __main__.py.
- `simple3d_config.json` — added round 10: silkscreen layer lists + ink settings.

| # | requirement | status |
|---|---|---|
| 1 | mask thickness in board | done; core.total_board_thickness: board+both masks. Verified 1.104. Limitation: mask layers count only if named `SOLDERMASK*` (round 2 decision) — a stackup naming them otherwise contributes 0.0 silently. |
| 2 | colour dropdown in GUI | done; colors.py: 8 themes from XML, dropdown + swatch. |
| 3 | simple3d.il menu, pcb→cad, dated name, prefill | done; anchor 3d_export_ui; --dated-name accumulating _ |
| 4 | symbols_top/bot, unique names `refdes_<jsonname>` | **PARTIAL** — groups and shared parts done (part = model file). The `refdes_<jsonname>` instance naming this requirement asks for was **removed in round 8** as over-complication, so no reference designator survives into the STEP at all. The requirement itself was never withdrawn: either restore the naming or amend requirement 4. |
| 5 | minimise size / reuse | done; surfacecurve.mode=0 (~49% smaller) + one shared part per model |
| 6 | MFRPN in json | **DISABLED in round 8** — property attachment proved unreliable in practice. Every branch is commented out, not deleted, in both `.il` files and all three `.py` files, marked `MFRPN DISABLED (kept for future)`. Nothing writes or reads `mfr_pn` now. |
| 7 | silkscreen export (user, 2026-07-22) | done in round 10; `format_version: 2`. Filled polys from `axlPolyFromDB`, clipped to outline−cutouts, extruded 25 µm into `silkscreen_top`/`silkscreen_bot` parts. Layers + ink settings in `simple3d_config.json`. GUI checkbox + White/Black dropdown. Variant-independent by requirement. **Round 10a**: first live run skipped every polygon (vertex list carries no closing edge, and `poly->segments` returns the source centreline for line-derived polys) — both fixed, awaiting a re-run. |

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

## Update 2026-07-22 (round 10) — silkscreen export

Branch `feature/silkscreen-export`. User requirements for this round, verbatim
in intent: variant A of the options memo; silkscreen of components absent from a
variant must **not** be removed (the bare board is manufactured once for every
assembly variant, so its legend is physically there regardless); ink 25 µm as a
config parameter; GUI checkbox plus a two-item White/Black colour dropdown; silk
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
visible. Each side is one compound, one label, one colour. Documented as a
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
GUI smoke test (config path, wrap mode, both checkboxes, colour box greying out
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
