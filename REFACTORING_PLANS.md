# Simple 3D — plans for taking the monoliths apart

Companion to [ARCHITECTURE.md](ARCHITECTURE.md), which names five monoliths:

| id | unit | lines |
|---|---|---:|
| M1 | `core.generate` | 646 |
| M2 | `bend.plan_fold` | 428 |
| M3 | `bend._map_strip` | 381 |
| M4 | `gui.StepBuilderApp` | ~1500 |
| M5 | `makeVariant3dIntermediates.il` as one file | 3925 |

plus the cross-cutting items (the intermediate's flat namespace, the test
harness, the argument plumbing) that no single monolith owns. This is the order
to do it in and what "done" means for each step. Written 2026-09-02 (round 70);
**Step 0 was done the same day (round 71)** — its status is under its table.
Nothing past Step 0 has been started.

---

## 0. Ground rules for every plan

1. **No behaviour change inside a step.** Every step is either a move, a rename
   with a compatibility import, or a fix that a test already pins. A step that
   changes what a STEP file contains is not a refactoring step and does not
   belong in these plans.
2. **Green before, green after.** `python tests/run_all.py` (23 jobs, ~5 min
   under Python 3.12 — the only interpreter here with OCP) before the step and
   after it. `--quick` (the non-OCCT suites, under a minute) is for iterating,
   not for closing a step.
3. **A golden corpus beside the suite.** Before the first move, build the
   repository's own inputs once and record volume, bounding box, solid count
   and the STEP entity count for each: `demo/ap-214/demo.json` in all three
   stitchings, the fold suite's rigid-flex board (`tests/fixtures/rigidflex.json`),
   and — with the user's
   agreement, since they are their designs — `failed/8231-a2.json`,
   `failed/cadence_demo.json` (folded, all modes) and `input/bone-a2.json`.
   Compare after every step: `python tools/golden.py --check`. Volume through
   `tests/_support.volume` — the iterative integrator, the way the suites
   measure — so the corpus and the tests are the same numbers. The C++
   regression alone is not enough: it is a plain board with no zones, no
   bends and no legend.
4. **Small commits, one step each**, in the user's hands (they commit on
   request). A step that touches both halves of the tool is two steps.
5. **The SKILL side cannot be run here.** Every SKILL step ends with the four
   mechanical checks green *and* a transliterated test where one exists, and is
   marked "not verified in Allegro" until the user has exported a board with it.
6. **Read the tolerances of anything you move.** Round 66's lesson: a helper
   repurposed for a new caller carries its old constants with it.
7. **Keep the user's settings out of tracked files** throughout — the local
   config, `SIMPLE3D_DIR`, `input/`, `failed/`.

### Step 0 — prerequisites, before any monolith is touched

| # | change | proves |
|---|---|---|
| 0.1 | `tests/test_regression_geometry.py`: `sys.exit(0 if match else 1)`, and assert the entity count too (the memo's 5054 against today's 5038 — settle which is right, record it) | the baseline can fail |
| 0.2 | `tests/_support.py`: one `check()`, one `_ROOT`/`_OUT` preamble, one `volume()` (iterative overload), one `read_step()`; each suite imports it | the next nineteen edits are one edit |
| 0.3 | `tools/golden.py`: build the corpus in rule 3, write `build/golden.json`, `--check` compares within 1e-6 (volume) / exact (counts) | every later step has a yardstick |
| 0.4 | `core.py:395`: import only `BRepAlgoAPI_Common` locally | closes the `UnboundLocalError` trap |
| 0.5 | delete `colors.as_fraction`; fix the `for … : pass` in `audit_docs.py`; point `.claude/launch.json` at nothing or at this repo | noise gone before the diff gets large |

`input/` is already ignored (done in round 70).

**Status 2026-09-02 (round 71): 0.1–0.5 done**; `run_all.py` 23/23 in 188 s,
`golden.py --check` no difference. Nothing committed.

- **0.1** — the count was settled by building the same board at seven
  commits (`git archive` into a scratch folder): 5077 at the first Python
  rewrite (`1c5d46b`), **5054** from `3ad1617` through `a402fff` (the memo's
  round-21 number), **5038** since `687ea3f` (round 63, an arc read by its
  two ends) — the volume 12073.309477 at every one of them. The count is a
  property of the writer; the test pins 5038 with that history in its
  docstring and exits 1 on either drift.
- **0.2** — `tests/_support.py`: `ROOT`, `OUT`, `out_dir`, `fails`, `check`,
  `rect`, `read_step`, `volume` (iterative), `bbox`, `count_solids`,
  `entity_count`. All twenty scripts import it — 152 asserted replacements,
  the suites' own assertions untouched; `test_mech.py` keeps its own `ok`
  (it never had a `check`). The two integrators agree to 1.3e-8 mm³ on the
  regression board, so the plain suites lost nothing by switching.
- **0.3** — `tools/golden.py`, 7 cases in 18 s: `demo` in the three
  stitchings, the rigid-flex fixture in the three stitchings and flat; each
  case in its own process so an OCCT access violation costs one case. The
  record is `build/golden.json`, gitignored like everything under `build/`.
  `--with-local` adds `failed/` and `input/` — **not run**: the user's word
  first, and a `--step-dir` pointing at their model library.
- **0.4** — `_layer_region` imports only `BRepAlgoAPI_Common` locally.
- **0.5** — `colors.as_fraction` gone, the `for … : pass` gone,
  `.claude/launch.json` deleted (it pointed at step2html's preview server;
  this tool has no dev server).

---

## Plan A — M1: `core.generate` → a package of stages

### Target shape

```
stepbuilder/
  contour.py       build_contour, WIRE_TOLERANCE, _open_wire_detail,
                   contour_points, polygon_area, clip_halfplane,
                   point_in_polygon, point_on_polygon           (from core + bend)
  errors.py        StepBuilderError — contour, bend and core all raise it, so it
                   cannot live in any of them                   (added by A1)
  intermediate.py  Intermediate: one parse per file; .is_simple3d, .is_full_board,
                   .silkscreen_layers, .components, .metadata; _validate;
                   resolve_json_jobs, output_stem, dated_output_name
  stackup.py       restack, drop_soldermask, align_stackups, stackup_levels,
                   zone_levels, _is_soldermask, _is_conductor
  board.py         _layer_region, layer_solids (ONE zones×layers walk),
                   make_board_layer_parts, fuse_keeping_faces, fuse_and_unify,
                   _zone_solid, board_cutouts, _cut_out, make_board_geometry,
                   has_solid, _rim_faces
  legend.py        the arc conventions, _wire_from_vertices, _face_from_wires,
                   _silk_face, _pick_convention, build_silkscreen,
                   _merge_coplanar, _face_area, clip_silk_to_zones, _silk_point
  models.py        StepFileIndex, _same_root, component_transform, _rotation,
                   ModelCache (the read-once-per-model logic), _report_embedded_only
  stepdoc.py       StepDocument: XCAF app/doc, shape+color tools, _set_color,
                   _sanitize, named parts/groups, write(minimize)
  build.py         BuildOptions (the 22 keywords as one dataclass, from BuildSettings
                   or from argparse), BuildResult, generate() as ~80 lines of
                   orchestration calling the stages
  core.py          re-exports everything above for one release, with a
                   DeprecationWarning-free shim (tests import from core today)
```

`generate()` keeps its signature for a release so that `worker.py`,
`__main__.py` and every test keep working; internally it builds a
`BuildOptions` and runs the stages.

### Steps

| # | move | tests that must exist before | done when |
|---|---|---|---|
| A1 | `contour.py`: move `build_contour` and the five polygon helpers out of `core`/`bend`; both import from it | `test_bend.py` [10], [10a]; `test_dupcuts.py` | the `core`↔`bend` cycle is gone (`python -c "import stepbuilder.bend"` before `core` works) — **done, round 72**: moved verbatim, `errors.py` added for the exception, both modules re-export; `import stepbuilder.bend` leaves `core` unloaded (asserted); 23/23, golden unchanged |
| A2 | `intermediate.py`: `Intermediate` class wrapping one `json.loads`; `is_simple3d_json`/`is_full_board`/`silkscreen_layers` become thin wrappers; `worker` and `gui` call the class | `test_variant_path.py` [8]; `test_gui.py` layer list; `test_embedded.py` [6] (`_reserved`) | one parse per file per Generate; the `_reserved` tuple lives in one place with the SKILL comment pointing at it — **done, round 72**: `resolve_jobs` returns parsed `Intermediate`s and `generate` accepts one (a path still works and parses for itself); `RESERVED` in `intermediate.py`, the exporter's NOTE and `test_variant_path.py` [8] point at it; measured one `json.loads` for resolve + generate; 23/23, golden unchanged |
| A3 | `stackup.py`: move the six pure functions | `test_nomask.py`, `test_layers.py` [0], `test_zones.py` [2] | `core.stackup_levels is stackup.stackup_levels` |
| A4 | `board.py`: move the board builders; write `layer_solids(pcb, stackups, zones, shift, cutouts_per_layer: bool)` and have `make_board_layer_parts` and `_stackup_board` both use it | `test_layers.py`, `test_modes.py`, `test_plain_modes.py`, `test_neg.py`, `test_dupcuts.py` [5] | one zones×layers walk; golden corpus unchanged |
| A5 | `legend.py`: move the silkscreen half | `test_silk.py` | unchanged areas in the log lines |
| A6 | `models.py`: `StepFileIndex`, `component_transform`, and the model-reading loop as `ModelCache.labels_for(step_name)` returning `(labels, problem)` | `test_index.py` [1-9], `test_mech.py`, `test_zones.py` [4] | the component loop in `generate` is placement only |
| A7 | `stepdoc.py`: the XCAF document and the writer | `test_modes.py` `inspect()` reads colours back; regression | entity counts unchanged in the golden file |
| A8 | `build.py`: `BuildOptions` dataclass; `worker._run` and `__main__.main` construct it once; `generate(**kw)` accepts the old keywords by building it | `test_gui.py` [8] (snapshot fields) extended to `BuildOptions.from_settings` | the argument list exists in one place |
| A9 | `generate` body → `_prepare_stackups`, `_plan_fold`, `_build_board`, `_build_legend`, `_place_components`, `_write`; each takes the context and returns what the next needs | everything above | `generate` under 100 lines; every stage callable alone in a test |
| A10 | `board_mode` validated (raise on an unknown string) and the CLI `--batch` gains `--no-full-board` to match the GUI rule (a small behaviour *addition*, documented) | new case in `test_variant_path.py` [8] | GUI and CLI agree |

Risks: the folded layer-coloured path depends on face identity through the
fuse (fold before fuse); keep A4 and A9 from reordering those calls. `phase()`
progress values are asserted nowhere — add one test that the phases are
monotonic before A9.

---

## Plan B — M2 + M3: `bend.py` → a package

### Target shape

```
stepbuilder/bend/
  __init__.py     public names: Bend, FoldPlan, plan_fold, plan_from_json, DEFAULT_*
  constants.py    EPS, MIN_ANGLE, DEFAULT_*, LogFn - each with its reason  (added by B1;
                  B7's home for the rest of the magic numbers)
  info.py         parse_bend_info, info_length, info_number, Bend, bend_from_dict,
                  bends_from_json
  regions.py      _Piece (face_box + holds, shared), _Region(_Piece), _Strip(_Piece),
                  _slice_trsf, _bbox, _extent, _is_empty
  pieces.py       _polygon_face, _band_face, _faces_of, _face_poly, _piece_face,
                  _touching, _closest_point, _cut_into_pieces
  plan.py         plan_fold split into: chain_at(), strips_overlap(), readable(),
                  _walk(panels, strips, held) -> carried/labels/regions,
                  _neutral_ceiling(), _double_claimed, _seam_gap, _overlap_note,
                  _anchor_signs, _anchor_point; plan_from_json
  cut.py          _cut_to_region, _crosses, _slab, _plane_face
  strip_revolve.py  _spans_alike, _revolve_strip, _prism_of, PRISM_* constants
  strip_wrap.py   _map_strip split into: CylinderFrame (to2d, rho, surfaces),
                  edge_to_2d(edge, frame) -> curves (lines, ellipses, splines),
                  wire_on(surface, curves, corners), build_walls(...),
                  sew_and_check(...), expected_volume(...)
  apply.py        FoldPlan.apply (the compound-by-child path and the piece path),
                  _fuse_all, summary/_note_build/describe
```

`stepbuilder/bend.py` becomes `stepbuilder/bend/__init__.py`; every `from
stepbuilder.bend import X` in the tests keeps working because `__init__`
re-exports.

### Steps

| # | move | tests before | done when |
|---|---|---|---|
| B1 | package skeleton; `info.py`; `regions.py` with the `_Piece` mixin | `test_bend.py` [1], [2], [16] | `_Region.holds is _Strip.holds` (one implementation) — **done, round 72**: `bend.py` became `bend/__init__.py` (git sees the rename), `constants.py` / `info.py` / `regions.py` cut out verbatim, `_Piece` holds the one `face_box` + `holds` (asserted `is`), `_slice_trsf` and the OCC plumbing went with the regions; `__init__` re-exports everything, including the three underscored names `test_bend.py` imports. 24/24, golden unchanged |
| B2 | `pieces.py` | [7c2] (`_cut_into_pieces` with and without curves), [7b0], [7b2] | unchanged — **done, round 72**: `pieces.py` cut out verbatim (the eight functions and the note on why the outline is cut rather than split by half-planes); `__init__` re-exports them; 24/24, golden unchanged |
| B3 | `cut.py` + `apply.py` | [3], [11], [12], [13], [14] | unchanged; `_slab` keeps "sized and placed from the shape" |
| B4 | `strip_revolve.py` | [17], [11b] (the ear) | unchanged — **done, round 72**: `strip_revolve.py` cut out verbatim with `PRISM_TOLERANCE` and `PRISM_SPAN_TOLERANCE`; `MAP_VOLUME_TOLERANCE` stayed beside `_map_strip` for B5; done after B3's first half (`cut.py`) because the revolve needs `_plane_face`; 24/24, golden unchanged |
| B5 | `strip_wrap.py`: first move `_map_strip` whole, then extract `CylinderFrame`, then `edge_to_2d`, then `wire_on`, then walls, then validation — one commit each | [17b], [17c], [17d], [17e] (the loose corner), [7c2] | each extraction leaves [17e] green; `wire_on` still builds edges on shared vertices |
| B6 | `plan.py`: `plan_fold` → the closures become module functions taking explicit arguments: `chain_at(ordered, factor, stack_at, top, bottom, notes)`, `readable(chain, notes)`, `walk(...)`, `neutral_ceiling(...)`; `plan_fold` becomes the sequence | [5], [5b], [6], [7], [7a], [7a1], [7b], [7b1] (300 random layouts), [7c], [7c1], [7d] | `plan_fold` under 120 lines; the k-ceiling uses the same `chain_at`/`readable` (already the point of round 66) |
| B7 | name the magic numbers: `FLAT_FRAME_MARGIN = 1.0`, `BAND_REACH = 10.0`, `SEAM_TOL = 0.05`, `DOUBLE_CLAIM_WARN = 0.02`, `CLAIM_GRID = 2.0`, `SLIVER_RATIO = 0.01`, `FACE_POLY_PER_CURVE = 12`, `SAMPLE_*`, `SEW_TOL = 1e-6`, each with the one-line reason from the code comment | — | no bare literal in a geometric comparison |

Risks: `_map_strip` recurses on disjoint solids and threads `why` through; keep
the first-reason semantics of `give_up`. `plan_fold` mutates `plan.notes` from
inside closures — B6 has to pass `notes` explicitly, and [7c] asserts on their
wording.

---

## Plan C — M4: `gui.StepBuilderApp` → settings, placement, panels, bridge

### Target shape

```
stepbuilder/
  settings.py      merge_config, read_config_file, local_config_path,
                   GUI_KEYS = [(key, default, kind), …]  (one table),
                   GuiSettings.load(path) -> (settings, base_problem, local_problem),
                   GuiSettings.save(path, values, paths_from_launcher)  (only what differs),
                   migrations (stepDir -> stepDirs, debugLayers -> boardMode)
  winplace.py      virtual_screen, geometry_is_reachable, restore/remember for any tk.Tk
  worker_bridge.py WorkerBridge(app): start(settings), drain(), cancel(), alive check,
                   the crash advice text
  widgets/layers_panel.py   the scrolled Top/Bottom checkbox panel with wheel grab
  gui.py           StepBuilderApp: layout + wiring only (~600 lines)
```

### Steps

| # | move | tests before | done when |
|---|---|---|---|
| C1 | `settings.py` with `merge_config` and `read_config_file` moved verbatim; `gui` imports them | `test_config_merge.py`, `test_gui.py` [3], [4], [4b] | unchanged — **done, round 72**: plus `local_config_path`; `settings.py` imports neither tkinter nor core (asserted); the window keeps `_merge_config` as an alias and thin wrappers for the two methods; a 24-scenario load/save snapshot (eight settings files × none / edited / launched-from-Allegro) is byte-identical before and after |
| C2 | the key table: `_load_config`/`_save_config` iterate `GUI_KEYS` instead of naming each key twice; migrations as functions | `test_gui.py` [6], [7], [7b], [7d]; `test_geom.py` [3], [7] | adding a setting is one table row — **done, round 72**: `settings.GUI_KEYS` (24 rows, in the order the file is written), `GuiSettings`, `load_gui_settings` / `save_gui_settings` as module functions rather than the class methods sketched above; `RIM_*`, `DEFAULT_CONFIG_PATH` and `BOARD_MODE_KEYS` moved with them (the window asserts its `BOARD_MODES` keys match). The 24-scenario load/save snapshot is byte-identical; new `tests/test_settings.py` (the 20th suite) exercises every rule without a window; `audit_docs.py` reads the key names from the table now. One cost: `settings.py` imports `core` and `bend` for three default numbers, so it is no longer OCP-free — move `DEFAULT_FLAT_HEIGHT`, `DEFAULT_NEUTRAL_FACTOR`, `DEFAULT_SLICE_ANGLE` to a light module if that ever matters (plan G) |
| C3 | `winplace.py` | `test_geom.py` all | unchanged |
| C4 | `widgets/layers_panel.py` | `test_gui.py` layer cases; the round-15/16 behaviours (wheel grab, per-side greying, All/None on live sides) need explicit assertions first — add them | unchanged |
| C5 | `worker_bridge.py` | `test_gui.py` [9] (freeze/thaw, cancel, the fake worker) | `StepBuilderApp` no longer imports `multiprocessing` |
| C6 | `__main__`: one `ArgumentParser` with a `--gui` mode; `_gui_prefill` stops poking `app._update_swatch()` (a public `set_theme`) | new `test_launcher.py` (the round-10i suite that was never committed) | `parse_known_args` gone, an unknown launcher flag is an error |

Risks: the freeze/thaw records widget states by walking the tree — moving the
layer panel into a widget must keep it inside `_walk()`. The settings file is
the user's; C2 must not change what is written (compare the local file
byte-for-byte before/after on the test fixtures).

---

## Plan D — M5: the exporter → several SKILL files and one namespace discipline

SKILL has one global namespace and `load()` only; a "package" is a set of files
loaded in order. The install today is two `load()` lines; it can stay two lines
if `simple3d.il` loads its parts itself.

### Target shape

```
simple3d.il                 the loader: resolves the install folder FIRST (s3dResolveScriptDir
                            moves here from the middle of the file), then load()s the parts
                            below from S3D_ScriptDir, then the menu/trigger/command it has now
skill/s3d_util.il           s3dSay/Warn/Err, s3dMakeDirs, s3dDesignFolder, s3dVariantFilePath,
                            s3dContains, s3dAddIndent, s3dFolderOf, s3dSlashes, s3dHeadList
skill/s3d_json.il           s3dJson* reader, s3dJsonMerge, s3dJsonQuote, s3dConfigRead,
                            s3dLocalConfigFile, s3dCtrlCharPattern
skill/s3d_props.il          s3dObjectHasProp, s3dPropValue, s3dNoStepExport, s3dAlwaysStepExport,
                            s3dEmbeddedModels(+Json), s3dHasStepModel, s3dIsMechanical
skill/s3d_variants.il       gdsysGetVariantInfo, s3dIsRefdesToken, s3dVariantKnownRefdes,
                            s3dVariantFit, s3dSymbolsToExport, s3dCheckMfrPn
skill/s3d_geometry.il       makeLine/Arc/Circle/Slot, rotateXY, s3dDrillXY, boardGeometryParseSegment,
                            s3dContourJson, makePcbContour, symbolReturnPinHoles
skill/s3d_stackup.il        calculateBoardThickness, s3dLayerThk, s3dConductorSpan, s3dLayerIsNegative,
                            s3dLayerInBody, s3dCollectRigidFlexShapes, s3dShapeJson, s3dLayerShapesJson,
                            s3dStackupJson, s3dStackupsJson, s3dZoneList, s3dZonesJson
skill/s3d_bends.il          s3dSweepBendLines, s3dGroupNamed, s3dBendParts, s3dPathEnds, s3dBBoxHas,
                            s3dSpanAcross, s3dBendAreaAt, s3dBendsJson
skill/s3d_silk.il           s3dSilkConfig, s3dZeroWidth, s3dDescribeObject, s3dPolysFromDbid,
                            s3dCollectSilkByLayer, s3dGroupCount, s3dBoardPoly, s3dBBoxInside,
                            s3dClipChunk, s3dClipPolys, s3dClipGroups, s3dMakeSilkscreen,
                            s3dWriteVertexList, s3dWriteSilkPolys, s3dWriteSilkscreen
skill/s3d_export.il         makePcb, symbolReturn3DElements, create3dIntermediateFormat,
                            makeVariant3dIntermediates
```

`makeVariant3dIntermediates.il` stays for one release as a file that `load()`s
the parts in order, so an `allegro.ilinit` that names it keeps working; the
README then documents the single `load("…/simple3d.il")`.

### Steps

| # | change | checks before | done when |
|---|---|---|---|
| D1 | `tools/skill_checks.py` check #5: an assignment `name = …` inside a `procedure` whose `name` is neither a parameter, nor in the `let`/`prog` list, nor `S3D_*`, nor a `foreach`/`for`/`gets` binding, is reported. Self-test with a known-bad and known-good fragment, like check #4 | — | the leak in 4.1 of ARCHITECTURE.md is a list the tool prints |
| D2 | declare the leaked locals (add them to the `let` lists; `makePcb` gets its own `colorJson`; drop the duplicate `thicknesses`) | D1 green on the result; `test_variant_path.py` [7], [9] (the parser and the copy) | check #5 clean; the four other checks clean |
| D3 | `s3dWithLayersVisible( l_layers l_filter body )` — the visibility snapshot / find filter / `axlAddSelectAll` / restore idiom — used by `s3dSweepBendLines`, `s3dCollectSilkByLayer` and the three probes that carry copies | round 14's DYNTHEMALS note in the helper | one copy |
| D4 | JSON escaping: every string that reaches the file goes through `s3dJsonQuote` (`symbolReturn3DElements` refdes + `step_name`, the zone name, `s3dWriteSilkPolys` layer, `s3dWriteSilkscreen` warnings, the `name` header); `s3dEmbeddedModelsJson` quotes instead of skipping | `test_quote.py`; a new transliterated `test_emit.py` that feeds a refdes and a step name with `"` and `\` through the emitter and `json.loads` the result | no raw `"\"" x "\""` left in the writer |
| D5 | thickness: `pcb.thickness` derived from the `Primary` stackup's kept layers when there is one (the sum `s3dStackupJson` already computes), `calculateBoardThickness` kept only for the rigid-flex `nil 'all` case it was never right for — or dropped with `pcb.thickness` computed by the reader from `stackups` (a format change: see Plan E) | `test_plain_modes.py` [5]; the round-34 numbers (1.104 on the user's board) | one rule for requirement #1 |
| D6 | the file split above, mechanically: cut and paste procedures in their existing order into the eight files; `simple3d.il` gains the loader; both checks pool all files | all four checks over the new file set (`FILES` in both tools becomes a glob); `test_config_merge.py` [3], `test_variant_path.py` source greps updated to the new files | Allegro loads it: **user verification required**, one export on a plain board and one on a rigid-flex board |
| D7 | `create3dIntermediateFormat`: an export-state list `(mechSeq shapes bendLines silkWarnings)` passed down instead of four globals reset in two places | the round-42/61 resets pinned in `test_variant_path.py` [8] | no per-export global left except the config-filled two |
| D8 | the JSON body: build a list of `(key value-string)` pairs and join once, instead of `strcat` with hand-placed commas and the `parseString(body "\n")` re-indent | a transliterated writer test (the round-36 style) that parses the output for: no components, no cutouts, no silk, full board, all four combinations | one place decides commas |

Risks: SKILL resolves names at call time, so a moved procedure that is loaded
after its first caller *runs* is fine but a moved **global** (`S3D_AlwaysExportProp`
read at load by `simple3d.il`) is not — keep every load-time read of a global in
the file that defines it or behind `boundp`. Round 54's rule stands: the loader
defines and assigns, nothing else.

---

## Plan E — the intermediate: `format_version` 9

The flat namespace (components beside metadata) and the two thickness rules are
format problems; they need one coordinated change in both halves.

| # | change | back-compat | tests |
|---|---|---|---|
| E1 | writer emits `"components": { "<refdes>": {…}, … }` and stops writing components at the top level; `format_version: 9` | reader: if `"components"` is present use it, else walk the top level minus `_reserved` (v1–v8 files) | `test_embedded.py` [6] both shapes; a v8 fixture kept in `tests/fixtures/` |
| E2 | `pcb.thickness` becomes optional in v9; the reader computes it from `stackups["Primary"]` (kept layers) when absent; `calculateBoardThickness` retired | v8 files carry it; the reader prefers the stackup when both exist and they disagree by > 1 µm, and says so | `test_plain_modes.py`, `test_nomask.py` [5] |
| E3 | `intermediate.RESERVED` (was `core._reserved` until round 72) deleted once E1 has shipped a release | — | — |

Order: after Plan A2 (the `Intermediate` class is where the compatibility lives)
and Plan D4/D8 (the writer is data-driven by then).

---

## Plan F — the test harness

| # | change | done when |
|---|---|---|
| F1 | Step 0.2: `tests/_support.py` | every suite imports `check`, `volume`, `read_step`, `rect`, `ROOT`, `OUT` — **done, round 71** |
| F2 | `tests/skill_transliterations.py`: the Python copies of `s3dJsonQuote`, `s3dDrillXY`, `s3dDesignFolder`/`s3dVariantFilePath`, the variant rule, `tconc`, `s3dBendsJson`, `s3dLayerInBody`, `s3dLayerIsNegative`, `skill_merge`, `s3dSpanAcross` in one module, each with a `# mirrors makeVariant3dIntermediates.il:<procedure>` line | the SKILL side has one executable specification file |
| F3 | `run_all.py`: exit code decides pass/fail (it already does); stop grepping stdout for `error`/`Error`, print the tail of a failing job instead | a test whose message contains "error" is not noise |
| F4 | optional: pytest. Each script's `print("\n[n] …")` blocks become functions; `run_all` stays as the entry so the documented command does not change | `python -m pytest tests -q` and `python tests/run_all.py` agree |

---

## Plan G — the small ones

| # | change | where |
|---|---|---|
| G1 | soften "Nothing temporary is written next to your board" to what round 43 says: the pre-flight log is written and deleted (done in round 70) | README, CHANGELOG 2026-07-27 entry left as history |
| G2 | `tools/skill_lex.py` shared by `skill_checks.py` and `check_arity.py` | tools |
| G3 | `_seam_gap`, `_double_claimed` promoted to the plan's public `check()` so a test can call them without the underscore | bend |
| G4 | `s3dExportCommand` stops passing `list(0.0 0.4 0.0)`; `makeVariant3dIntermediates` keeps the optional argument for the CLI-from-console use | simple3d.il |
| G5 | `DEFAULT_FLAT_HEIGHT`, `DEFAULT_NEUTRAL_FACTOR`, `DEFAULT_SLICE_ANGLE` into a light `defaults.py` (re-exported where they are), so `settings.py` stops importing OCP for three numbers (found in C2) | core, bend, settings |

---

## What each extracted piece could serve elsewhere

| piece | after which plan | who else |
|---|---|---|
| `contour.py` (JSON primitives → wire / polygon) | A1 | step2html (reads the same intermediate shapes when given one), AllegroBaseStructure's `board_html.py` |
| `models.py` `StepFileIndex` + `ModelCache` | A6 | 3dproperties (an inventory over a model library with the same case rules) |
| `stepdoc.py` | A7 | 3dproperties `inventor_combine_export`, step2html's writer |
| `winplace.py`, `worker_bridge.py` | C3, C5 | step2html's `gui.py`, which copied both by hand (memory: `step2html-repo`) |
| `settings.py` (tracked defaults + local overrides) | C1 | every tool of this user's that pulls updates (memory: `user-settings-never-in-tracked-files`) |
| `skill/s3d_json.il` | D6 | AllegroBaseStructure's `dump_board.il` writes JSON by hand today |
| `skill/s3d_silk.il` (layer → clipped polygons) | D6 | the same dump, and any Gerber-like export |
| `skill/s3d_variants.il` | D6 | the ESKD toolchain that shares this Allegro install (`PROJECT_NOTES_eskd.md`) |
| `tools/skill_lex.py` + the five checks | D1, G2 | every SKILL project on this machine |

---

## Suggested order

Step 0 → A1, A2 (breaks the cycle, one parse) → C1, C2 (settings out of the
window; no OCC involved, fast to test) → B1–B4 (moves only) → A3–A8 → B5, B6
(the two hard extractions, with the fold suite as the net) → A9, A10 → C3–C6 →
D1–D5 (SKILL discipline, user verification after D2 and D4) → D6–D8 → E → F4.

Each arrow is a green run of `tests/run_all.py` plus `tools/golden.py --check`.
