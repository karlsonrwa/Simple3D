# Record: legend objects that come out with nothing, or with a piece missing (31.10.2026, round 117)

Evidence for R2-5 of the 23.10.2026 review, open in both rounds. The claim it tested was "an object that could not be turned into a polygon is named in the log; 0 kinds of objects lost silently". It did not hold: `axlPolyFromDB` answers nil when "it cannot get the polys" (its reference page), every call to it sat in an `errset`, and the collector named an object only when the converter raised an error - the first one alone, on the console only. The reviewer's transliteration had 4 of 6 objects end with no polygon and no message, and pointed at flex3-a0, whose console said "a silkscreen line has 4 segment(s) but produced only 3 polygon(s)" while its JSON carried no warning. They asked for "a message with the layer and the place for every object without a polygon, in the console and in the JSON, on a board with such an object".

Every run below was Allegro 25.1 headless on a scratch copy, started directly (`tools/run_probe.py`, no `cmd`, no console), with the owner's desktop watched by `build/fix-2026-10-31/r116/watch.py`: no new visible window in any of them, nothing left running.

## The nine boards: none has such an object

`s3dProbeSilkLost` (`tools/probes/probe_silkfill.il`) runs the exporter's own sweep over the shipped silkscreen layers and its own converter on each object it finds, as the export does:

| Board | Objects | Zero width | Converted | No polygon | Part missing | Errors | Polygons |
|---|---:|---:|---:|---:|---:|---:|---:|
| 5988-a1 | 30 | 2 | 28 | 0 | 0 | 0 | 58 |
| Cadence_Demo | 1311 | 6 | 1305 | 0 | 0 | 0 | 3405 |
| circle-A0 | 8 | 0 | 8 | 0 | 0 | 0 | 8 |
| flex-b2 | 30 | 1 | 29 | 0 | 0 | 0 | 31 |
| flex2-a0 | 24 | 2 | 22 | 0 | 0 | 0 | 22 |
| flex3-a0 | 40 | 0 | 40 | 0 | 0 | 0 | 64 |
| my_test_board-a0 | 24 | 0 | 24 | 0 | 0 | 0 | 32 |
| my_test_board2 | 97 | 0 | 97 | 0 | 0 | 0 | 214 |
| variants_test-b0 | 436 | 0 | 436 | 0 | 0 | 0 | 551 |
| **all** | **2000** | **11** | **1989** | **0** | **0** | **0** | **4385** |

"Part missing" there still compared counts, as the exporter did. `s3dProbeStrokes` asks the exact question instead: each stroke on its own (a line's segment, a vectorised text's r_path), the way the converter converts it, over the legend, the drawn mask openings and the copper paths on ETCH, the two that share the converter:

| Board | Legend: lines and texts / strokes / empty | Mask openings | Copper paths |
|---|---|---|---|
| 5988-a1 | 30 / 68 / 0 | 23 / 23 / 0 | 28 / 28 / 0 |
| Cadence_Demo | 1308 / 3197 / 0 | 8 / 52 / 0 | 2077 / 5520 / 0 |
| circle-A0 | 8 / 8 / 0 | 23 / 23 / 0 | 38 / 40 / 0 |
| flex-b2 | 30 / 35 / 0 | 0 / 0 / 0 | 74 / 268 / 0 |
| flex2-a0 | 24 / 31 / 0 | 0 / 0 / 0 | 31 / 92 / 0 |
| flex3-a0 | 40 / 64 / 0 | 0 / 0 / 0 | 133 / 1078 / **1** |
| my_test_board-a0 | 24 / 32 / 0 | 82 / 82 / 0 | 12 / 18 / 0 |
| my_test_board2 | 97 / 213 / 0 | 51 / 51 / 0 | 93 / 163 / 0 |
| variants_test-b0 | 436 / 551 / 0 | 54 / 54 / 0 | 128 / 224 / 0 |
| **all** | **1997 / 4199 / 0** | **241 / 285 / 0** | **2614 / 7431 / 1** |

The one empty stroke is the line the reviewer quoted, and it is copper, not legend: a path on ETCH/BOTTOM at (4.960, 3.830), whose third of four segments is an arc from (5.6099, 3.9801) to (5.6100, 3.9802) about (5.6099, 3.9802), radius 0.0001 mm (one database unit), a quarter turn, 0.3 wide. The converter is shared, and its message called every line "silkscreen".

## The objects, made

None of the boards having one, `s3dProbeLostCases` makes them on a copy of my_test_board2 (millimetres, accuracy 4: one database unit is 0.0001), on BOARD GEOMETRY/SILKSCREEN_BOTTOM, which is empty there:

| Case | What | `axlPolyFromDB`, whole | The converter, per stroke |
|---|---|---:|---:|
| K1, K2, K5 | a path that is one quarter arc of radius 1, 2, 5 database units, 0.3 wide | 0 | 0 |
| L1, L2, L5 | the same arc as the corner of an L, 2 mm along and 2 mm up | 2 | 2 (the arc gives none) |
| M1, M2, M3 | "TT 18" in a text style with the font Arial, 1.5 high: by name on the bottom and the top, and in an `axlTextOrientation` | 4 | 4 |
| M0 | "VF 18" in text block 1, the control | 0 | 6, but skipped: zero width |

So a true-type text converts, whole, to its four outlines: the reviewer's example ("TrueType text, if axlPolyFromDB gives nil for it") does not lose anything on 25.1. Such a text carries `textStyle` and no `textBlock`, which is how the converter already sends it to `axlPolyFromDB` whole. Two things the reference says otherwise, both measured here: `axlDBCreateTextStyle` takes its height in user units, not "in database units" (at 15000 for 1.5 mm it made the style, and the text was refused: "Text line is outside of the extents"), and `axlDBGetTextStyle()` without an argument is refused ("too few arguments (1 expected, 0 given)"); `axlDBGetTextStyle( nil )` lists the styles.

## Before and after, on that copy

The same probe, exporting the copy with `makeVariant3dIntermediates` at the end (`build/fix-2026-10-31/r117/tt/` before the change, `after/` after it):

Before. The console said, of the six paths, "a silkscreen line has 1 segment(s) but produced only 0 polygon(s)" and "a silkscreen line has 3 segment(s) but produced only 2 polygon(s)", with no layer and no place, and printed four of the six: Allegro's console leaves out a warning identical to the one just before it (K1 came right after K2, L2 right after L5, and those two are missing; the probe's own two sweeps show the same, 6 lines of 12). The summary counted one object skipped, the zero-width text. The JSON's `silkscreen.warnings` held that text alone.

After. The console and `silkscreen.warnings` both hold seven lines, each naming its object:

```
no polygon: path on BOARD GEOMETRY/SILKSCREEN_BOTTOM at (5.850, 16.850) - left out, as Allegro converts it to no polygon
no polygon: path on BOARD GEOMETRY/SILKSCREEN_BOTTOM at (2.850, 16.850) - left out, as Allegro converts it to no polygon
zero width: text on BOARD GEOMETRY/SILKSCREEN_BOTTOM at (12.000, 19.967) - skipped; Allegro's artwork draws it only at a film's undefined line width
part missing: path on BOARD GEOMETRY/SILKSCREEN_BOTTOM at (11.850, 15.850) - 1 of its 3 segment(s) gave no polygon and is left out: 2 (an arc of radius 0.0001)
no polygon: path on BOARD GEOMETRY/SILKSCREEN_BOTTOM at (8.850, 16.850) - left out, as Allegro converts it to no polygon
part missing: path on BOARD GEOMETRY/SILKSCREEN_BOTTOM at (19.850, 15.850) - 1 of its 3 segment(s) gave no polygon and is left out: 2 (an arc of radius 0.0005)
part missing: path on BOARD GEOMETRY/SILKSCREEN_BOTTOM at (15.850, 15.850) - 1 of its 3 segment(s) gave no polygon and is left out: 2 (an arc of radius 0.0002)
```

then "the legend leaves out 7 object(s) in whole or in part, each named above; the window's log repeats them". Each line names a place, so none is left out as a repeat: every "part missing" line was printed all three times it was said. The polygons of the two JSONs are identical, 84 on top and 11 on the bottom after clipping: the change is in what is said, not in what is drawn.

## The change (`skill/s3d_silk.il`)

- `s3dStrokePolys` converts a list of strokes one at a time and returns the polygons with the strokes that gave none. A line, an unfilled outline and a vectorised text go through it; a line or a text with no stroke converted is still converted whole, as before.
- `s3dPolysFromDbid` reports a piece missing (`s3dStrokesLost`: the object's layer and place, the number of each lost stroke and, for a segment, `s3dStrokeSize`'s "an arc of radius ..." or "a line ... long"). It no longer says "silkscreen": the drawn mask openings and the copper under them share it.
- `s3dCollectSilkByLayer` names every object left with nothing to draw, "no polygon" or "conversion error", with its layer and place. The first-failure-named-the-rest-counted rule is gone.
- `s3dReportLoss` puts each message on the console and, given the export state, into `silkWarnings`, which go into the JSON; without it (the openings, the copper) on the console only.
- `s3dMakeSilkscreen` writes the silkscreen object whenever there is a message, polygons or not.

Held by `test_skill_pins` [5b3] (the statements, red against the old code: 14 checks failed), `test_silk` [8b] (a silkscreen object with only messages builds nothing and logs both, word for word) and eight new rows in `tests/mutations.json`, with round 111's `silk-unfilled-drawn-whole` rewritten for the new branch.

Not changed, and in README's Known limitations: of the drawn mask openings, an object that converts to nothing is still left out without a word, and one that raises an error is only counted on the console; the copper under them that converts to nothing is counted there, not named.

## To run it again

```
set S3D_PROBE_OUT=<folder>
python tools/run_probe.py --with-exporter tools/probes/probe_silkfill.il s3dProbeSilkLost input/<board>.brd
python tools/run_probe.py --with-exporter tools/probes/probe_silkfill.il s3dProbeStrokes input/<board>.brd
python tools/run_probe.py --with-exporter tools/probes/probe_silkfill.il s3dProbeLostCases input/my_test_board2.brd
```

Each writes `<design>.silklost.txt`, `<design>.strokes.txt` or `lostcases.lost.txt` into the folder; the last also saves the copy as `lostcases.brd` and exports it beside them.
