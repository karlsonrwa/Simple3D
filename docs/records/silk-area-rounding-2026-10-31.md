# Record: the legend's area check against the rounding of the coordinates (31.10.2026, round 113)

Evidence for R2-8 of the 23.10.2026 review, open in both rounds: the fixed tolerance `AREA_TOLERANCE = 0.005` of `stepbuilder/legend.py` had no source. Four correct polygons of Cadence's demo board came out 0.506-0.555 % off the area Allegro reported and were called distorted, while a wrong reading of the arcs stayed within 0.32 % on every polygon of variants_test-b0's top and would have passed. The reviewer asked for "a tolerance justified by the measured rounding of the coordinates, shown on those four polygons and on variants_test-b0's top". This file is that.

Made with the intermediates the exporter wrote on 30-31.10.2026 (Allegro X Venture 25.1, `format_version` 12) for the nine boards in `input/`, and 8231-a2's from the first review package (`format_version` 7); `stepbuilder` at round 113 under Python 3.11.6 with cadquery-ocp 7.9.3.1.1 on the 4090. The boards are the owner's: their intermediates and everything made from them stay under `build/`, which is not in git.

## How to repeat

    python tools/silk_areas.py <intermediate.json> [...]

Every legend polygon that carries Allegro's `area` is rebuilt by `stepbuilder`'s own code (`legend._silk_face`, an OCP face) under each of the eight readings of its arcs, and its disagreement with that area is measured in shares of its margin, `legend._area_margin`. Per side the tool prints the grid, the right reading's largest share, how many polygons each other reading puts past the margin and its largest share, how many readings the pick's eight-polygon sample leaves within the margin, and the reading the pick lands on.

## What Allegro hands over

The exporter writes, for each polygon, `axlPolyFromDB`'s vertex list and Allegro's own `poly->area`. The two are not the same figure. On the demo board, whose vertices all sit on a 0.001 mm grid, the second of the four is a stroke 0.8 mm long and 0.203 mm wide with round ends, its centreline at y = -0.003:

    [[89.129, -0.003, 0.1015], [89.231, -0.104, 0.1015], [90.031, -0.104, 0.0],
     [90.132, -0.003, -0.1015], [90.031, 0.098, -0.1015], [89.231, 0.098, 0.0]]   area 0.194765

The arcs keep the true radius, 0.1015, but the straight sides, which belong at -0.1045 and 0.0985, come back at -0.104 and 0.098: 0.202 apart. Allegro's area is that of the exact figure, 0.8 × 0.203 + π × 0.1015² = 0.1947655. The polygon rebuilt from the vertices has 0.1937635, 0.514 % less. Another copy of the same stroke on the board, standing upright at x = 70.104, has its sides at 70.0025 and 70.2055, which come back at 70.002 and 70.205, 0.203 apart. Allegro reports the same 0.194765 for it, and it is rebuilt within 0.0008 %. Of the 22 polygons with that area on the demo's top, this one is the worst. The other three of the four are a 1.0 mm stroke of the same width, its sides 0.202 apart as well, and two AUTOSILK polygons whose edge Auto Silkscreen cut off straight at x = 100.33. The four and the twin are in `tests/fixtures/silk_rounding.json`, and `test_silk` [16] reads the mechanism off them.

## The margin

Let u be the grid step. A written coordinate is within u/2 of the exact one, so a vertex is within u/√2 of where it belongs. A polygon's area is the shoelace area of its vertices plus, for each arc, the segment between the arc and its chord. To first order:

- the shoelace part changes by at most the sum of the chord lengths × u/√2 (its derivative with respect to a vertex is half the vector between the two neighbours, turned by 90°);
- a segment of radius r over an arc of angle θ changes with its chord c by dS/dc = r sin²(θ/2) / cos(θ/2), and the chord changes by at most √2 u;
- so per unit of outline length a straight edge contributes at most 0.71 u, a quarter arc (chord r√2: r u from the shoelace, r u from the segment, over a length of πr/2) 4/π = 1.27 u, and a smaller arc something in between, growing with θ. Polygon arcs never cross a quadrant (Allegro's documentation of the vertex list, quoted in `legend.py`), so 90° is the largest.

The margin is therefore √2 × perimeter × u, which covers 1.27 with room, plus the half of the last digit the area is written with (`%f`, six decimals: 0.5e-6 mm²). The terms of second order are at most n u²/4 for n vertices: for the stroke above, 6 vertices on 2.24 mm of outline at u = 0.001 mm, 0.05 % of its margin.

The grid is read from the data, not asked of Allegro: `legend._coordinate_step` takes the coarsest of 1, 0.1 ... 0.000001 mm that every vertex coordinate of the side sits on. A vertex list comes back rounded to the board's accuracy. A coarser grid than that only means that every vertex happens to sit on it as well, which makes the margin looser than it could be, never tighter than the rounding. That happens on two sides here, both at 0.01 mm: circle-a0's top (2 polygons) and my_test_board-a0's bottom (3), whose top is at 0.001. The intermediates need no re-export.

## The ten boards

`tools/silk_areas.py`, 31.10.2026 15:15, the 4090. "Weakest wrong reading": the one that puts the fewest polygons past the margin.

| board | side | polygons | grid, mm | right reading, largest share | weakest wrong reading: past the margin on (largest share) | sample leaves within | pick |
|---|---|---:|---:|---:|---|---:|---|
| 5988-a1 | top | 9 | 0.0001 | 0.200 | axis, positive left, first radius unused: 5 (1038) | 1 | right |
| 5988-a1 | bottom | 18 | 0.0001 | 0.121 | the same: 4 (4497) | 1 | right |
| cadence_demo | top | 1379 | 0.001 | 0.322 | the same: 196 (1184) | 1 | right |
| cadence_demo | bottom | 908 | 0.001 | 0.209 | the same: 27 (14.9) | 1 | right |
| circle-a0 | top | 2 | 0.01 | 0.000 | every one: 2; the closest, axis, positive right, unused (1.32) | 1 | right |
| flex-b2 | top | 2 | 0.0001 | 0.007 | axis, positive left, unused: **0** (0.007), the same two shapes | 2 | right, by the whole side |
| flex2-a0 | top | 1 | 0.0001 | 0.074 | every one: 1; the closest, travel, positive left, closes (72.1) | 1 | right |
| flex2-a0 | bottom | 4 | 0.0001 | 0.041 | axis, positive left, unused: 1 (447) | 1 | right |
| flex3-a0 | bottom | 24 | 0.0001 | 0.200 | the same: 4 (39.0) | 1 | right |
| my_test_board-a0 | top | 10 | 0.001 | 0.000 | axis, positive left, unused: **0** (0.610) | 2 | right, by the whole side |
| my_test_board-a0 | bottom | 3 | 0.01 | 0.000 | travel, positive left, unused: 2 (33.5) | 1 | right |
| my_test_board2 | top | 80 | 0.0001 | 0.200 | axis, positive left, unused: 10 (39.0) | 1 | right |
| variants_test-b0 | top | 18 | 0.0001 | 0.200 | the same: 4 (1.64) | 2 | right, by the whole side |
| variants_test-b0 | bottom | 85 | 0.0001 | 0.200 | the same: 40 (3082) | 1 | right |
| 8231-a2 | top | 167 | 0.0001 | 0.195 | the same: 36 (1874) | 1 | right |
| 8231-a2 | bottom | 12 | 0.0001 | 0.134 | the same: 5 (59.6) | 1 | right |

2 722 polygons in all. The right reading uses at most 0.322 of its margin (the demo's top); the four of the finding use 0.18, 0.32, 0.32 and 0.13 of it, the twin 0.000 (`build/fix-2026-10-31/r113/shares4.py`). On fourteen of the sixteen sides every wrong reading also misses some polygon by more than its margin, so the per-polygon check alone would name it. On the other two only the comparison between readings tells them apart: flex-b2's top, where the two readings build the same two shapes (neither polygon has an arc on its first vertex), and my_test_board-a0's top, where the reading that leaves the first radius unused stays within 0.61 of the margin on all ten polygons while the right one fits them exactly.

## The pick's second look

`_pick_convention` scores the eight readings on the eight smallest arc-bearing polygons of a side and takes the closest. On variants_test-b0's top as the review saw it, with both legend sources, those eight carry no arc on their first vertex, so "first radius closes" and "unused" scored the same to the last digit (0.2831 of the margin) and list order chose between them; four of the eighteen polygons tell them apart, by 1.64 margins. Since round 113, when the sample leaves more than one reading within the margin, every arc-bearing polygon of the side decides between those (three sides of the table). With round 112's default the top's legend is the nine PACKAGE GEOMETRY polygons, and two of the four that decide are among its eight smallest, so the sample alone settles it there; `test_silk` [16] keeps the eighteen as the review had them, lists the wrong reading first, and requires the right one.

## The builds, before and after

`build/fix-2026-10-31/r113/builds.py`, the nine boards of `input/`, flat board, solid legend, no models, both legend sources; round 112's code (`e76a911`) against round 113's:

- Cadence_Demo, drawn layers: `warning: 2 of 689 silkscreen_top polygons still differ from the area Allegro reported (worst: 0.194765 vs 0.193763 mm2, 0.5%).` became `silkscreen_top: 689 polygon(s) match Allegro's areas to within rounding to a 0.001 mm grid`. AUTOSILK: `2 of 676 ... (worst: 0.059681 vs 0.060012 mm2, 0.6%)` became `676 polygon(s) match`.
- The other eight boards: the same verdict as before on every side, the line now naming the grid. flex-b2, flex2-a0 and flex3-a0 build no legend solid, before and after alike.
- Time, on the demo board (`timing.py`, three builds in each tree, alternating; `timing2.py`, every log line timestamped): `build_silkscreen` took 1.65-1.71 s in both, the top 0.62-0.65 s and the bottom 1.01-1.05 s. The whole build varied between 9.0 and 12.2 s in either tree, all of the spread in writing the STEP (6.4-8.7 s), which the round does not touch.

## What it cannot see

- An area is one number per polygon. A wrong arc whose two possible sides enclose less than the margin, such as a small arc in a large polygon, cannot be seen by it. Which way an arc bulges is settled by the comparison between readings over the whole side, not by this check.
- A wrong reading can turn an outline into a face OCP calls invalid (`BRepCheck_Analyzer`), and the area OCP gives such a face is no measure of the figure: under AXIS / positive left / first radius unused, one polygon of 5988-a1's top comes out at -2.763368 mm² where the signed analytic sum (`build/fix-2026-10-31/r113/areas.py`) has 2.763368; under TRAVEL / positive left / unused, circle-a0's two polygons at 11.407 where it has 1.517. Such a face is named by the check all the same, which is right, since it is geometry that did not survive; but two of the table's catches come from it. By the analytic areas the weakest wrong reading would stay within the margin on circle-a0's top (0.23 of it) and on my_test_board-a0's bottom (0.16), so there too it is the comparison between readings that rules it out (the right one uses 0.000 of its margin on both). The faces and the sums above are `build/fix-2026-10-31/r113/why.py`'s; the two ways of measuring give the right reading the same largest share on all sixteen sides (`margin.py` against the table).

## Before: the fixed 0.5 %

The same tool's numbers in shares of 0.5 % of each polygon's area: the four of the demo at 1.01-1.11 (named), the wrong reading of variants_test-b0's top at 0.64 at most (passed). `build/fix-2026-10-31/r113/redgreen.py` shows both through the calls the code had before the round: on `e76a911` the four give `no reading ... reproduces ... (best is off by 0.6% ...)` and `4 of 4 top polygons still differ`, a 4 mm square 1.05 margins off is accepted, variants_test-b0's top under the wrong reading gives `18 polygon(s) match`, and with that reading listed first the pick takes it.
