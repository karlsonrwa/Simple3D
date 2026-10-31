# Record: the checks R2-9 named, each held to the product, and the Variants.lst parser measured (31.10.2026, round 118)

Evidence for R2-9 of the 23.10.2026 review, open in both rounds. The claim it tested was "the tests check what is said of them; there are no checks that cannot fail". The reviewer named five places: (a) `test_variant_path` [3] worked a parseString rebuild out of a literal; (b) [9] ran eight checks on a model of the cutout list the test defined itself; (c) [7] checked the copy `alternate_line`, and nothing looked at the SKILL fix `symbols = nconc( symbols list( refDes ) )` (s3d_variants.il, both branches); (d) `test_launch_cmd` built its own argument tail, so the quotes `simple3d.il` puts round each path and the interpreter it picks were held by nothing; (e) the copy `parse_variants` did not follow `awaitMoreProperties`, and on a wrapped property block lost a part the SKILL installs. Evidence asked: for every named check, a change to a product file that turns it red.

## The review's three mutations, on the tree as round 117 left it

`build/fix-2026-10-31/r118/k6_today.py` on the 4090, each on a fresh copy:

| | change | the suites it names |
|---|---|---|
| M1 | `list( refDes )` back to `list( nth( 0 subStrings ) )` in both branches | test_variant_path, test_skill_pins: green |
| M2 | the quotes round `--json-dir`'s value dropped from `argTail` | test_launch_cmd, test_skill_pins: green |
| M3 | python before pythonw in `s3dWindowPython` | test_launch_cmd red since round 114 (`skill-window-python-order`) |

## Allegro's own parser, asked

`tools/probes/probe_translit.il` (`s3dProbeTranslitVariants`) points `s3dVariantFilePath` at each file of `tests/fixtures/variants` in turn (`putd`, put back after), calls the real `gdsysGetVariantInfo` in Allegro 25.1 headless and prints the variant table in name order; `tools/skill_answers.py` writes it into `tests/fixtures/skill_answers.json` (83 cases before, the 83 unchanged, 103 now). The files are kept byte for byte by `.gitattributes` (`-text`): Capture writes CRLF, the review's cases were LF. Every run was started directly with the owner's desktop watched: no new window, nothing left running.

| File | What it is | Allegro 25.1 | the old copy |
|---|---|---|---|
| v1 (CRLF), v9 (LF) | one-line alternate block, a blank line after it | LSM: R1 R2 C1 C43 | the same, with a stray "\n" |
| v2 | the block's properties wrapped onto a second line | LSM: R1 R2 **C43** | LSM: R1 R2 "\n" - **C43 lost** |
| v3 | the refdes alone on the block's first line | LSM: R1 - **C43 not installed** | the same |
| v4 | two variants, names differing in case | FULL: R1; Full: R1 R2 | the same, stray "\n" |
| v5 | a variant with no (base block | BOM: nil | BOM: [] |
| v6 | the user's own alternate line, Capture's shape | A: C1 C2 R1 C43; B: C1 R1 | the same, stray "\n" |
| v7 | a base list over two lines | LONG: C1 C2 C3 R1 R2 | "C3\n", stray "\n" |
| v8 | wrapped over three lines, then a one-line block with "\t)" straight after it | **nil: the variant lost** | W3: R1 C44 |
| v10 | a one-line block with "\t)" straight after it | **nil** | V1 with C43 |
| v11 | v10, then a second variant | **nil: both lost** | both |
| v12 | an alternate part, no base block, "\t)" straight after it | **nil** | V2: C43 |
| v13 | v12 with a blank line after the block | V2: C43 | V2: C43 |
| v14 | a backslash in a name (`X\2`) | BS: R1 X\2 | X2 |

And SKILL's own `parseString` with no break characters: "a b", "a\tb", "a\nb", "a\rb" and "  a   b  " all give ("a" "b"), "" gives nil.

What that says about the parser itself:

- `parseString` breaks at the line end as at a space, so a line's last piece does not keep its "\n": round 52's memo had reasoned that a line ending in " )" leaves a bare "\n" token, and no file here gave one.
- An alternate-part block is closed where its last piece, split at `" `, is ")\n" - which on its own line it never is. Even a one-line block is closed by the line after it, the blank one Capture writes. With the variant's closing "\t)" straight after the block, the machine stays in `awaitMoreProperties` to the end of the file: that variant and every one after it are lost (v8, v10-v12).
- A block whose refdes stands alone on its first line opens nothing (`length( subStrings ) > 1` fails), so the part is not installed (v3).
- The strip class `["\t+\\()]` holds no backslash: in a class `\(` is the paren (v14).
- A CRLF and an LF file answer alike (v1, v9): `gets` gives "\n".

Both of the user's own Variants.lst files (input/) have one variant each, the blank lines, and no alternate block. Whether Capture ever writes v3's or v8's shape is not known; README's Known limitations names both. The parser was not changed in this round.

## What changed (tests only; no product file)

- (a) `test_variant_path` [3]: the rebuild worked out of a literal is a comment now; the check reads `s3dDesignFolder` and finds the scan (`substring( full i 1 )`) and no `parseString`.
- (b) [9]: the model of the cutout list runs the way `create3dIntermediateFormat` hands it on - copied or aliased, read off the source - and the two ends of the list the model has (pin holes starting it when there is no cutout, an unbound list written as nil) are read off the source too. The model's own premise (an alias gives 1, 2, 3 copies of the holes) is folded into the check that depends on the source.
- (c) `test_skill_pins` [5d] pins the fix in both branches, the wrapped branch's statements, and compares the copy's six regexes with the SKILL's `pcreCompile` calls text for text; `test_variant_path` [7] holds the source to the fix as well, and says what the parser does with a one-line block (closed by the line after it).
- (d) `test_launch_cmd` reads `argTail = strcat( ... )` out of `simple3d.il` - the literal pieces as the source spells them, the variables given a spaced config path, cad folder and board name - and runs it through the real `start` into the stand-in; every argument has to arrive whole. A variable it has no value for is named, not guessed.
- (e) `tests/skill_transliterations.py`: `parse_string` (SKILL's own, with no break characters: white space), `alternate_line` and `parse_variants` statement by statement, `awaitMoreProperties` included, the strip class as the SKILL spells it. `test_skill_pins` [7] holds the copy to Allegro's answers on all 14 files and 6 strings; red first (2 FAIL: 9 files wrong, no `parse_string`), and once more on v14 (the backslash). `test_variant_path` [12]: NORMAL and ALT_ONLY carry the blank line Capture writes (they had passed only because the copy closed a block on its own line), the stray-token check is turned round, and the lost variant is a check of its own.

## Verified

- Rows 413 -> 425, one product change per named check: skill-design-folder-via-parsestring (a), skill-cutouts-aliased-again, skill-pin-holes-need-a-cutout, skill-unbound-cuts-written (b), skill-variant-refdes-fix-reverted-one-line, skill-variant-refdes-fix-reverted-wrapped, skill-variant-wrapped-never-closes, skill-variant-wrapped-tabs-kept (c, e), skill-tail-config-unquoted, skill-tail-json-dir-unquoted (the review's M2), skill-tail-output-dir-unquoted, skill-tail-brd-name-unquoted (d). On the 4090, the 75 rows naming test_skill_pins, test_variant_path or test_launch_cmd: 75 of 75 caught, each new one by the check written for it (test_gui red on the clean copy as always in session 0; no row rested on it). M1 alone against test_variant_path: [7]'s source check red.
- run_all 32/34 in 92 s, the two window suites.

## To run it again

```
python tools/run_probe.py --with-exporter tools/probes/probe_translit.il s3dProbeTranslit demo/demo.brd -o <folder>
python tools/skill_answers.py <folder>/demo.s3dProbeTranslit.txt
python tests/test_skill_pins.py
```

A new case is a new `.lst` in `tests/fixtures/variants`: the probe and the table both read the folder.
