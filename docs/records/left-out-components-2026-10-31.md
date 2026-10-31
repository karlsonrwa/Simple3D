# Record: the components a missing model leaves out are named (31.10.2026, round 122)

At the owner's «Да, R3-3»: R3-3 of the 23.10.2026 review (a missing model is skipped and named by its file only: the refdes go into `components_skipped`, the log has "could not find X.step", the CLI and the window print counts; open in both rounds; to clear: "on the same input, the window's and the CLI's log name U9 and R77").

## Measured before the fix

On the 4090, `build/fix-2026-10-31/r122/repro.py`: the demo board with U9 and R77 on `NOT_THERE.step` (in no folder), C2 and C3 on `broken.step` (on disk, not a STEP file) and R1-R15 on one shared missing model, through `core.generate()`, the CLI (`stepbuilder.__main__.main`) and the window's worker (`worker.run_jobs` with a list for a channel, no Tk):

- generate(): 1 placed, 19 in `components_skipped`; the log's warnings `could not find NOT_THERE.step`, `broken.step could not be read (locked, empty, or not a STEP file OCCT accepts): <path>`, `could not find SHARED_MISSING.step`; no line naming any of the 19.
- CLI: exit 0, the same lines and `2 STEP file(s) not found`, `1 STEP file(s) are on disk but could not be read (see above)`.
- Window: the same lines, `demo.step: 2 STEP missing`, `demo.step: 1 STEP file(s) on disk could not be read (see the log)`, and last `Done: 1 file(s), 1 component(s) placed`.

## The fix

- `stepbuilder/core.py`, `_place_components`: the refdes each unusable model leaves out are collected, and after the loop one line per model names them, in refdes order (`_refdes_order`: the runs of digits as numbers, C2 before C10), the first `LEFT_OUT_SHOWN` = 20 and a count of the rest: `warning: NOT_THERE.step not found - 2 component(s) left out: R77, U9`, `warning: broken.step could not be used - 2 component(s) left out: C2, C3`. The window and the CLI both show the build's own log, so the line is in both.
- `stepbuilder/__main__.py`: the summary adds `warning: N component(s) left out of the model (named above)`.
- `stepbuilder/worker.py`: the per-file summary adds `<file>: N component(s) left out (named above)`, and the last line `…, N left out`.
- README (both halves), *When a model is not in the assembly*.

## After

The same input on the 4090 (`repro_after`): generate(), the CLI and the window's worker each logged

    warning: NOT_THERE.step not found - 2 component(s) left out: R77, U9
    warning: broken.step could not be used - 2 component(s) left out: C2, C3
    warning: SHARED_MISSING.step not found - 15 component(s) left out: R1, R2, … R15

the file lines before them unchanged; the window's last line was `Done: 1 file(s), 1 component(s) placed, 19 left out`. The cap is held by test_embedded's 25 on one model (the first 20, then "and 5 more").

Rows 446 -> 454: core-left-out-not-collected, core-left-out-not-said, core-left-out-text-order, core-left-out-uncapped, core-left-out-unusable-called-missing, cli-left-out-not-counted, worker-left-out-not-counted, worker-done-says-placed-only, all on test_embedded. The 56 rows on core.py, worker.py and __main__.py and of test_embedded: 56 of 56 caught. run_all 32/34 in 88 s, the two window suites with the FAILs session 0 always gives them.

## Held by

`test_embedded` [9]: the review's input and more (U9/R77 on a missing model, C2/C3 on an unusable one, 25 refdes on a shared missing model given out of order): the three lines exactly, in generate()'s log, in the CLI's output and in the window worker's log; the CLI's count; the window's per-file count and its last line. Red first on the old code: 7 FAIL.
