# Record: a JSON the reader does not know is refused, by name (31.10.2026, round 121)

At the owner's «Да, R3-2»: R3-2 of the 23.10.2026 review (`Intermediate.validate` checks neither `"format"` nor `"format_version"`; the CLI's one file goes past `resolve_jobs`; open in both rounds; to clear: "all four inputs give a StepBuilderError naming the version or the format, in generate() and in the CLI with one file"; round 2 added a fifth input, a file with neither key).

## Measured before the fix

On the 4090, `build/fix-2026-10-31/r121/repro.py`: the demo board (`demo/ap-214/demo.json`) with the keys set as named, through `core.generate()`:

| Input | generate() |
|---|---|
| format_version 99, 13, 0, "abc", true, 12.0 | built, no error, no warning |
| `"format": "kicad"` | built |
| neither key (the demo file as committed), no version, no marker | built |
| format_version 12 and 1 (controls) | built |

Every one of the twelve wrote a STEP of 2503 entities. The CLI given one file (`python -m stepbuilder demo/step_files <file> <out>`) wrote `demo.step` with exit code 0 for version 99, for "kicad" and for the file with neither key. The window's queue (`resolve_jobs`, `window_queue.py`) took every file that carried the marker (versions 0, 12, 99, "abc") and passed over only the two without it.

The reader never reads the number: what a file holds is told by its keys. The first exporter (1c5d46b, 19.07.2026) already wrote `"format": "simple3d"` and `"format_version": 1` together, so every file an exporter wrote has both; `demo/ap-214/demo.json`, from the upstream project, has neither (ARCHITECTURE finding 15).

## The fix

- `stepbuilder/intermediate.py`: `FORMAT_VERSION = 12`, the version this release's SKILL writes. `validate()`, the one place every build passes (the window, a batch, the CLI's one file), first refuses:
  - a file whose `"format"` is not `"simple3d"`: `JSON is not a Simple 3D intermediate: its "format" is 'kicad', not 'simple3d'` / `it carries no "format" marker`;
  - a `format_version` that is not an integer (`true` and `12.0` included): `JSON's format_version is 'abc'; the exporter writes a whole number from 1 to 12`;
  - one newer than `FORMAT_VERSION`: `JSON is format_version 99, newer than this stepbuilder reads (1 to 12): a newer exporter wrote it…`;
  - one below 1: `JSON's format_version is 0, which no exporter wrote (1 to 12)`.
- `demo/ap-214/demo.json` gets `"format": "simple3d"` and `"format_version": 1`, the first exporter's two keys.
- README (both halves) says what is refused and where.

## After

The same twelve inputs on the 4090 (`repro_after`; repro.py now drops the keys it means to drop, since the demo carries both): the ten refused, each with its message and no STEP written; versions 12 and 1 built. The CLI given one file: version 99, "kicad" and neither key each exit 1 with `error (<file>.json): …`, no STEP. The window's queue still takes a file that carries the marker; its build calls the same `generate()`, so it stops on the same message, which the worker's loop logs as `error (<file>): …` and, when it was the only job, reports as "All 1 job(s) failed" (read in stepbuilder/worker.py, unchanged; not run through the window).

The demo board, old code on the old file (`git archive` of bcc5403) and new code on the new, each the first build of a fresh process: DATA identical, 2546 lines, 104 148 bytes each. The control, the old code built again in a third process, differed from the first from line 2180 on, the style section (366 lines), with every line before it equal and the same colouring (`build/render/step_style_diff.py`: 6 styled items, the same pairs). The first comparison, against a file built as the fifth build of its process, had differed in the assembly-usage ids too ('13' against '1'): those count builds per process.

Two suites built boards of the demo's name and pcb alone, without the marker, and were refused (`test_mech`, `test_index`; run_all 30/34 until they carried it). They now carry the marker and version 1 as the exporter writes them; the 22 rows on the two suites: 22 of 22 caught.

Rows 440 -> 446: reader-format-not-asked, reader-newer-version-built, reader-version-zero-built, reader-version-true-built, reader-version-float-built, reader-newest-drifts, each caught by test_variant_path. The 34 rows on intermediate.py and of test_variant_path: 33 of 34 caught, the 34th (intermediate-brd-name-dated-only) names test_gui alone, red in session 0, unproven as before. run_all 32/34 in 91 s, the two window suites.

## Held by

`test_variant_path` [17]: `FORMAT_VERSION` equal to the `"format_version": N` the SKILL writes; the demo board carrying its keys; the ten refusals with the words each message must hold; every version from 1 to 12 taken; `generate()` refusing version 99 and "kicad" without writing a STEP; the CLI given each alone exiting 1 with `error (<file>):`. Red first on the old reader: 16 FAIL.
