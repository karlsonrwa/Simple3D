# Record: a shape's fill on the silkscreen, against Allegro's own artwork (30.10.2026, round 111)

Evidence for the 28.10.2026 review's R2-13: the exporter never read a shape's `fill` (`nil` unfilled, `t` solid, a list of `axlFill` a cross-hatch - `axlDbidDoc`, SHAPE attributes), and `axlPolyFromDB` "by default" treats a cross-hatch as solid. The reviewer asked for "a board with unfilled rect and shape and a hatched shape on SILKSCREEN layers, matching the Gerber; or reading fill with a message; or a limitation in README". This file is the first of the three; the code reads `fill` since round 111, and README names what is still left out.

Made with Allegro X Venture 25.1 S050 (`allegro -nograph`, the `artwork` batch of the same install), gerbonara 1.6.3 and numpy 2.5.2 under Python 3.14 on the owner's machine. Everything runs on copies of the owner's boards, under `build/`, which is not in git.

## How to repeat

    python tools/silk_artwork.py

1. `s3dProbeSilkCases` (`tools/probes/probe_silkfill.il`) draws the cases below on `BOARD GEOMETRY/SILKSCREEN_BOTTOM` of a copy of `input/my_test_board2.brd` (29.5 x 23 mm; that layer is empty on it), creates two films holding that layer alone - `S3D_SILKB` with an undefined line width of 0.05 mm and `S3D_SILKB0` with the default 0 - saves the copy as `silkcases.brd` and runs the exporter on it.
2. Allegro's `artwork -f <film> silkcases.brd` writes each film. With no `art_param.txt` beside the board it falls back to Gerber 6x00 in inches at 1 mil (`FORMAT 5.3`), apertures outside the file; the tool writes one with `DEVICE-TYPE GERBER_RS274X`, `OUTPUT-UNITS METRIC` (`MILLIMETERS` is answered `Unrecognized UNITS`) and `FORMAT 3.5`.
3. gerbonara reads each Gerber into primitives; the intermediate's polygons are rebuilt with the vertex reading `stepbuilder/legend.py` measured (every rebuilt polygon within 0.5 % of the area Allegro wrote beside it); both are drawn case by case on a 5 um grid, a 5 mm box around each 4 mm square.

## The cases, and what Allegro made of them

| case | made with | Allegro's object |
|---|---|---|
| A unfilled rectangle, 2..6 x 2..6 | `axlDBCreateRectangle( box nil layer )` | objType `"polygon"`, `fill` nil, `isRect` t, 4 `line` segments of width 0 |
| B unfilled shape, boundary width 0.2, 8..12 x 2..6 | `axlDBCreateShape( path(0.2) nil layer )` | refused: nil |
| C unfilled shape, boundary width 0, 14..18 x 2..6 | `axlDBCreateShape( path(0) nil layer )` | objType `"polygon"`, `fill` nil, 4 segments of width 0 |
| D unfilled circle r 2, width 0.15, at 22, 4 | `axlDBCreateShape( axlPathStartCircle(...) nil layer )` | refused: nil |
| B2 as B, 8..12 x 15..19 | `axlDBCreateOpenShape` + `axlDBCreateCloseShape` | refused: nil |
| E cross-hatch 45 deg, line 0.1 / spacing 0.5, boundary 0.15, 2..6 x 9..13 | `axlDBCreateShape( path(0.15) (list hatch45) layer )` | objType `"shape"`, `fill` a list of one `axlFill` |
| F cross-hatch 45 + 135 deg, 8..12 x 9..13 | as E with two `axlFill` | `"shape"`, two `axlFill` |
| G solid, 14..18 x 9..13 | `axlDBCreateShape( path(0) t layer )` | `"shape"`, `fill` t |
| H cross-hatch 0 + 90 deg with a round void r 0.8, 20..24 x 9..13 | open shape, `axlDBCreateVoidCircle`, close | `"shape"`, two `axlFill`, one void |

An unfilled shape with a boundary width could not be made three ways, and `axlChangeWidth` "does not support" a shape's border, so in Allegro 25.1 every unfilled outline has width 0. On the nine boards of `input/` none has one with a width, on any layer (the survey below).

What `axlPolyFromDB` gives (areas in mm2):

| case | `axlPolyFromDB( dbid )` | `?xhatch t` | each boundary segment on its own |
|---|---|---|---|
| A, C | 1 polygon, 16.000 - the area | the same | nothing: "Invalid database id argument" for each zero-width segment |
| E | 16.000 | 4.865463, 10 holes | 4 x 0.617671 |
| F | 16.000 | 6.924367, 55 holes | 4 x 0.617671 |
| H | 13.989381 (the void a hole) | 6.684014, 47 holes | 4 x 0.617671 |

## The Gerber

`S3D_SILKB.art`, RS274X, `%FSLAX35Y35*MOMM*%`: the solid G as a region (`G36`/`G37`); every hatch line a stroke of `D10` (round, 0.1); each hatched shape's border its boundary stroked with `D11` (0.15), H's void a full circle of `D11` (`G02` from a point back to it, `G75`); A and C their boundary stroked with `D12` (0.05) - the film's undefined line width. `S3D_SILKB0` (undefined width 0) has no `D12` and no A or C at all; `photoplot.log` says so: `WARNING: rectangle or unfilled shape composed 0 width line found at (2.0000 2.0000)` and `WARNING: rectangle or unfilled shape having Multiple 0 width lines; all will be treated the same as the first.`

So a figure with no width - an unfilled outline, and likewise a line or a text with no pen - is drawn by the artwork at its film's undefined line width, and left out only when that is 0.

## Before: round 110's exporter (`56a24ae`), film S3D_SILKB

| case | Gerber, mm2 | export, mm2 | export only | Gerber only | agreement |
|---|---:|---:|---:|---:|---:|
| A unfilled rectangle | 0.7995 | 0.0000 | 0.0000 | 0.7995 | 0.00 % |
| C unfilled, width 0 | 0.7995 | 0.0000 | 0.0000 | 0.7995 | 0.00 % |
| E cross-hatch 45 | 4.8666 | 16.0000 | 12.3513 | 1.2179 | 21.19 % |
| F cross-hatch 45+135 | 6.9277 | 16.0000 | 10.2902 | 1.2179 | 33.16 % |
| G solid | 16.0000 | 16.0000 | 0.0000 | 0.0000 | 100.00 % |
| H cross-hatch 0+90, void | 6.6841 | 13.9887 | 8.8819 | 1.5773 | 32.81 % |

The hatched shapes came out as their whole area, the outer half of their border missing; A and C were skipped by the exporter's zero-width check ("zero width: polygon on BOARD GEOMETRY/SILKSCREEN_BOTTOM at (2.000, 2.000) - skipped, it cannot be plotted").

## After: round 111

Film S3D_SILKB (undefined line width 0.05):

| case | Gerber, mm2 | export, mm2 | export only | Gerber only | agreement |
|---|---:|---:|---:|---:|---:|
| A unfilled rectangle | 0.7995 | 0.0000 | 0.0000 | 0.7995 | 0.00 % |
| C unfilled, width 0 | 0.7995 | 0.0000 | 0.0000 | 0.7995 | 0.00 % |
| E cross-hatch 45 | 4.8666 | 4.8666 | 0.0000 | 0.0000 | 100.00 % |
| F cross-hatch 45+135 | 6.9277 | 6.9277 | 0.0000 | 0.0000 | 100.00 % |
| G solid | 16.0000 | 16.0000 | 0.0000 | 0.0000 | 100.00 % |
| H cross-hatch 0+90, void | 6.6841 | 6.6841 | 0.0001 | 0.0001 | 100.00 % |

Film S3D_SILKB0 (undefined line width 0): A and C 0.0000 both, agreement 100 %; E to H as above. Every polygon of the intermediate rebuilt within 0.5 % of Allegro's own area. A and C are still skipped, now with "zero width: unfilled shape on BOARD GEOMETRY/SILKSCREEN_BOTTOM at (2.000, 2.000) - skipped; Allegro's artwork draws it only at a film's undefined line width": the exporter reads no films, so it matches the artwork where that width is 0 and lacks the outline where it is not.

The intermediates of the nine boards, exported before and after on the same inputs (`build/fix-2026-10-30/r111/compare_json.py`): 14 files, 8 identical, 6 differing only in the warning's words - 5988-a1 (2 lines and its BOM variant's 2), flex2-a0 (2 and 2), Cadence_Demo (6), flex-b2 (1).

## The nine boards in input/ (survey, `s3dProbeSilkFill`)

No unfilled or cross-hatched figure on any silkscreen, AUTOSILK or soldermask layer of any of them; no unfilled shape with a boundary width on any layer (their unfilled shapes are outlines, cutouts, keepins, MODULES, NCEDIT_SYS, CONSTRAINT REGION, ZONE_OUTLINE); cross-hatched shapes only on ETCH, BOUNDARY and MANUFACTURING/XSECTION_CHART. So no model of these boards changes; the intermediates written before and after differ only in the zero-width warning's words (below).

The films carrying a silkscreen layer, with the undefined line width they draw a zero-width figure at, and the figures with no width the exporter skips (from its warnings):

| board | silkscreen films: undefined width, layers | soldermask films | zero-width figures skipped | printed by Allegro? |
|---|---|---|---|---|
| 5988-a1 | SST 0.1 (REF DES, BOARD GEOMETRY, PACKAGE GEOMETRY /SILKSCREEN_TOP); SSB 0 | SMT, SMB 0 | 2 texts, REF DES/SILKSCREEN_TOP at (9.180, 3.222), (45.180, 3.222) | **yes, at 0.1 mm** (SST) |
| Cadence_Demo | SS_TOP, SS_BOT 0.254 (BOARD GEOMETRY, REF DES, PACKAGE GEOMETRY) | SM_TOP, SM_BOT 0.254 | 1 path, PACKAGE GEOMETRY/SILKSCREEN_TOP at (41.555, 33.120); 5 on MANUFACTURING/AUTOSILK_TOP | **the path yes, at 0.254 mm**; AUTOSILK_TOP is on no film |
| circle-A0 | none | SMT, SMB 0 | none | - |
| flex-b2 | SST, SSB 0 (MANUFACTURING/AUTOSILK, PACKAGE GEOMETRY; also ETCH/WIRE) | SMT, SMB 0 | 1 text, REF DES/SILKSCREEN_TOP at (6.870, 4.577) | no: REF DES is on no film |
| flex2-a0 | none | SMT, SMB 0 | 2 texts, REF DES/SILKSCREEN_TOP and _BOTTOM | no film |
| flex3-a0 | SST, SSB 0 (MANUFACTURING/AUTOSILK, PACKAGE GEOMETRY) | SMT, SMB 0 | none | - |
| my_test_board-a0 | SST, SSB 0.1 (MANUFACTURING/AUTOSILK, BOARD GEOMETRY) | SMT, SMB 0 | none | - |
| my_test_board2 | SST 0 (REF DES, PACKAGE GEOMETRY /SILKSCREEN_TOP) | SMT, SMB 0 | none | - |
| variants_test-b0 | SSB 0.1 (MANUFACTURING/AUTOSILK_BOTTOM, BOARD GEOMETRY/SILKSCREEN_BOTTOM) | SMT, SMB 0 | none | - |

The exporter reads no films, so on 5988-a1 and the demo the Gerber carries ink its model lacks - the README's limitation since round 111. The film lists also show which layers each board's films print at all: on flex-b2, flex3-a0, my_test_board-a0 and variants_test-b0 the silkscreen films carry `MANUFACTURING/AUTOSILK_*` and not `REF DES/SILKSCREEN_*`, while the exporter collects both by default (the window's layer ticks choose).

Four boards (Cadence_Demo, circle-A0, flex-b2, my_test_board-a0) were exported from copies in a folder of their own: the `Variants.LST` in `input/` (28.10.2026) describes another board, and the exporter refuses it beside them ("does not describe this board").
