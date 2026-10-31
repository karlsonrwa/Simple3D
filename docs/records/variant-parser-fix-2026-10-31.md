# Record: the Variants.lst parser loses no variant and no part (31.10.2026, round 119)

At the owner's «Да, чини», after round 118 measured what the parser (`gdsysGetVariantInfo`, skill/s3d_variants.il - the upstream code) does with the shapes of `tests/fixtures/variants` (`docs/records/tests-that-hold-the-product-2026-10-31.md`). Every run below was Allegro 25.1 headless, started directly, the owner's desktop watched: no new window from any of them, nothing left running (the watcher saw one window of the owner's Chrome open during an export, and named it as not the run's).

## What was lost, and why

`parseString` breaks a line at any white space, so the last piece of a line does not keep its "\n". The parser asked whether a block of alternate-part properties ends on its own line by its last piece being ")\n", which therefore never happened: a one-line block was closed by the line after it - the blank one Capture writes - or, with none, never. Measured with the parser of round 118, five more files added this round:

| File | Shape | Round 118's parser |
|---|---|---|
| v8, v10, v12 | a one-line block with the variant's "\t)" straight after it | the table empty: the variant lost |
| v11 | v10, then another variant | both lost |
| v15 | two one-line blocks, no blank line between them | C44 read into C43's block, lost |
| v16 | a wrapped block whose end is not written the way the parser looks for it (`TOL=1 )`), then "\t)", then another variant | both lost |
| v17 | the same, then another block | C44 lost |
| v18 | a base list with no "\t\t)" of its own | the next variant's lines taken as parts ("NEXT", "base", "R9"), the next variant lost |
| v3, v19 | the refdes alone on the block's first line | the part not installed |

## The fix (`skill/s3d_variants.il`)

- A block closed on its own line ends in ")": the check takes ")" or ")\n".
- A refdes alone on a block's first line opens the block (the "(base" line excepted; it matches the block pattern too), and the lines after it fill it.
- Before the state's own reading: a block still open (`awaitMoreProperties`) when its variant closes or the next block begins ends there, its part installed; a base list still open when its variant closes ends there. The line is then read by the state that knows it. A continuation line begins "\t\t " - the parser's own `newLineEnd` and `newLineWithinProperty` say so - so "\t\t(" is taken as a new block.

The Python copy (`tests/skill_transliterations.py`, `parse_variants` / `alternate_line`) follows statement by statement.

## What the fixed parser answers

All 19 files, Allegro 25.1 (`probe_translit.il`, fixture 103 -> 108 cases): of round 118's 103 answers, 98 are the same and the 5 that change are exactly the lossy ones (v3, v8, v10, v11, v12), each from a loss to the full table; the 5 new files answer v15 TWO: R1 C43 C44, v16 OPEN: R1 C43 and NEXT: R9, v17 OPEN: R1 C43 C44, v18 NOBASECLOSE: R1 R2 and NEXT: R9, v19 ALONE: R1 C43. The copy answers as Allegro did on all 19 (test_skill_pins [7]).

The user's two Variants.lst (input/), asked of round 118's parser (a worktree of e4d86d6) and of round 119's, with temporary copies in the fixture folder, removed after: the same answers from both - BOM: XP1, and BOM: VT1 VT2 VT3 VT4 X1 X2.

## A real export

A copy of input/variants_test-b0.brd with a Variants.lst beside it, CRLF as Capture writes, four variants: FULL (8 refdes), ALT (4 and a one-line block for C2 with "\t)" straight after it), LAST (3), ALONE (2, and a block with C1 alone on its first line). `tools/skill_export.py`:

| | variants parsed | JSON written |
|---|---|---|
| round 118's parser | 2 (`Simple 3D: 2 variant(s) parsed`) | the whole board, `_full` (8 of the listed), `_alt` (A1 C1 C2 R1 XP1) - LAST and ALONE none, nothing said |
| round 119's | 4 | the same three, byte for byte, and `_last` (A2 R2 XP2), `_alone` (A1 C1 R1) |

ALT came through before only by chance: its block was "closed" by the property line of the ALONE variant's block two variants further down, and the two variants between were swallowed. Allegro's own variant support, reading the same file in the same session ("Loading variants.cxt"), made a bill of materials for all four.

## Held by

`test_variant_path` [7] (a one-line block closed on its own line; the refdes appended in all three places a block ends), [12] (without the blank line the variant, and the next, still found), [14] (the ten lossy files with what each holds); `test_skill_pins` [5d] (the new statements pinned), [7] (the copy against Allegro on 19 files). Red first: test_variant_path 12 FAIL on round 118's copy. Rows 425 -> 430: skill-variant-one-line-block-left-open, skill-variant-open-block-swallows-the-rest, skill-variant-open-base-list-swallows-the-next, skill-variant-refdes-alone-opens-nothing (each caught by test_skill_pins's pins), skill-variant-open-block-part-dropped (by those and by test_variant_path [7] on its own; the other four leave test_variant_path green on its own - it asks the copy, which the pins and the recorded answers hold). On the 4090 the 64 rows on s3d_variants.il and of the two suites: 64 of 64 caught. run_all 32/34 in 86 s, the two window suites.

Not in this round: R2-10 of the 23.10.2026 review - two variants whose names differ only in case ("Full", "FULL", v4) parse as two and are written to one file, the second over the first.
