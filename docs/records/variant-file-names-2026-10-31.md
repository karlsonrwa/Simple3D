# Record: every variant a file of its own (31.10.2026, round 120)

At the owner's «Да, R2-10»: R2-10 of the 23.10.2026 review ("Full" and "FULL" parse as two variants and are written to one file, the second over the first; open in both rounds; to clear: "a run with such a Variants.lst: two files or a message"). Every run below was Allegro 25.1 headless, started directly, the owner's desktop watched: no new window from any of them, nothing left running.

## Measured before the fix

**SKILL and Windows** (`build/fix-2026-10-31/r120/probe_names.il`, a scratch probe, and the folder it wrote into):

- `lowerCase` and `upperCase` change the Latin letters only. Cyrillic in cp1251 ("Полный", "ПОЛНЫЙ", "ёлка", "ЁЛКА") and the same words in UTF-8 came back byte for byte as they went in.
- NTFS folds case for Cyrillic as for Latin: `outfile` on "brd_full" then "brd_FULL" made one file, and so did "brd_Полный" with "brd_ПОЛНЫЙ" and "brd_ёлка" with "brd_ЁЛКА". Each file held the second name.
- `outfile` answered nil for a name with `?` `*` `<` `>` `|` `/` `\` or `"`. It answered a port for "brd_a:b": the folder then held an empty file `brd_a`, and the text was in its streams `b.json` and `c.json` (`dir /r`). No listing shows them.
- `%L` prints a byte beyond ASCII inside a string as three octal digits (`"\317\316..."`).

**The real export** (`tools/skill_export.py`, five copies of input/variants_test-b0.brd, each with a Variants.lst beside it, CRLF, cp1251; `build/fix-2026-10-31/r120/scenes/`, `export_before/`):

| Variants | Parsed | Written |
|---|---|---|
| "Full" (8 refdes), "FULL" (4), "ALT" (3) | 3 | `_alt`, `_full` holding Full's 8; FULL's lost, and "export complete - 3 variant(s) written" |
| "Полный" (8), "ПОЛНЫЙ" (4) | 2 | one file, named with "ПОЛНЫЙ", holding Полный's 8 |
| "Rev:A" (8), "Rev:B" (4) | 2 | an empty `variants_test-b0_rev`, both variants in its streams; the window would find only the whole board |
| "OK" (8), "A/B" (4) | 2 | `_ok`, then `outfile() returned nil ... (check the folder exists and the path/permissions)`; no whole-board file |
| "Full" (8), "Full" (4) | 1 | `_full` holding the later's 4; the earlier lost, nothing said |

Allegro's own variant support, reading the same files as the board opened, did no better: it wrote `var-full.rpt` for "Full" and again for "FULL", and on the Cyrillic names, the colon and the slash it stopped with SPMHSK-7 and SPMHSK-9 errors of its own.

The parser of round 119 on two more fixture files: v20 ("Full" twice) gave one variant, the later; v21 (the Cyrillic twins in cp1251) gave both, byte for byte.

## The fix

- `s3dFileNameSafe` (skill/s3d_variants.il): every character no Windows file name takes, `\ / : * ? " < > |` and the control characters, becomes `_`. Cadence's own translator does the same with the variant names of a Capture design.
- `s3dVariantFileName`: the design and the made-safe variant, lower-cased. This is the one place a variant's file name is made; the writer and the check both ask it.
- `s3dVariantFileClashes`: which variants would share a file. lowerCase cannot say (it leaves Cyrillic as it is, and Windows does not), so the file system is asked. In a folder made fresh beside the export, one small file is made per variant, in the order the export writes them, each carrying its variant's name; a name that finds its file there already shares it with the variant written in it. Only what was made is deleted, the folder after it.
- `makeVariant3dIntermediates` (skill/s3d_export.il) asks before it writes anything and refuses on any answer, naming the variants and the file they would share. The loop takes its file name from `s3dVariantFileName`. A variant whose name was made safe is said in the console and in the file's `warnings`, which the window's log repeats. The folder is no longer lower-cased with the name.
- `gdsysGetVariantInfo` notes the line each variant's name stands on and, once the file is shut, refuses a name given to two variants, naming both lines. An error with the port still open would have kept Variants.lst locked for the session.

## After

The same five scenes (`export_after/`):

| Variants | Written | Said |
|---|---|---|
| "Full", "FULL", "ALT" | nothing | `variants would share a file: "FULL" and "Full" both go to variants_test-b0_full.json`, then why, and "Rename one of each pair in Capture" |
| "Полный", "ПОЛНЫЙ" | nothing | `"ПОЛНЫЙ" and "Полный" both go to variants_test-b0_ПОЛНЫЙ.json` |
| "Rev:A", "Rev:B" | `_rev_a` (8), `_rev_b` (4), the whole board | a warning per variant, in the console and in each file's `warnings` (read back by the window's own `Intermediate.read`) |
| "OK", "A/B" | `_ok` (8), `_a_b` (4), the whole board | a warning for A/B |
| "Full" twice | nothing | `gives one name to two variants: "Full" (lines 2 and 9)` |

No `simple3d-name-check` folder was left in any of them.

The probe of the transliterations (`tools/probes/probe_translit.il`) asked the fixed code: all 108 answers of round 119 the same; 24 more (v20 "error", v21 unchanged; `s3dFileNameSafe` 9, `s3dVariantFileName` 4, `s3dVariantFileClashes` 9 asked of the real file system in build/probe-names, the Cyrillic twins of v21 among them, and nothing left behind). `tools/skill_answers.py` now reads the run byte for byte (latin-1) and reads `%L`'s octal escapes. Fixture 108 -> 132.

The user's two Variants.lst hold one variant each, "BOM": no name twice and no shared file (the parser's and the check's copies, held to Allegro's answers).

## Held by

`test_skill_pins` [5d] (the parser's new statements), [5f] (the three procedures; the export's call before its loop, its refusal, the loop's name; the class of s3dFileNameSafe read out of the SKILL and run beside the copy's on every character from 1 to 255), [7] (the copies against Allegro's 132 answers; the clash copy asks the real file system as the SKILL does); `test_variant_path` [12] (the file closed before the parser refuses), [15] (the clash cases with what each gives, the Cyrillic twins among them; the export asks before it writes and an answer stops it), [16] (a name twice and three times). Red first, on HEAD's product with the new tests: test_skill_pins 18 FAIL, test_variant_path 3 FAIL.

Rows 430 -> 440: skill-variant-clash-not-asked, -clash-not-refused, -name-twice-unsaid (caught by test_skill_pins and by test_variant_path on its own), -clash-fs-not-asked, -file-name-not-shared, -folder-lowercased-again, -name-colon-kept, -name-made-safe-unsaid, -clash-check-left-behind, -name-twice-not-noted (test_skill_pins). The older skill-variants-error-as-format took a line the parser's new error holds too; one line of context makes it s3dVariantFit's alone again. On the 4090 the 75 rows on the two SKILL files and of the two suites: 75 of 75 caught; the three of test_variant_path on its own: 3 of 3. run_all 32/34 in 87 s, the two window suites.

## Not changed

Allegro's own variant reports (`var-<name>.rpt`, written as the board opens) are Allegro's: they still collide and fail on such names. A board whose own name holds a character no file name takes cannot exist, so the design half of the name is not made safe.
