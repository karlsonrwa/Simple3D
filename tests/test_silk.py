# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, out_dir, fails, check

"""Silkscreen path as a real package import (exercises `from .colors import`),
plus layer filtering, flat mode, warnings and the area cross-check."""
import json, sys

from stepbuilder import core           # package import, not a bare module

OUT = out_dir("silk")

base = json.loads((ROOT / "demo/ap-214/demo.json").read_text())

def square(x, y, s, layer):
    """CCW square, area s*s, tagged with a layer."""
    return {"vertices": [[x, y, 0.0], [x + s, y, 0.0], [x + s, y + s, 0.0], [x, y + s, 0.0]],
            "area": s * s, "layer": layer}

def ring(x, y, outer, inner, layer):
    o = outer / 2.0; i = inner / 2.0
    return {"vertices": [[x-o, y-o, 0], [x+o, y-o, 0], [x+o, y+o, 0], [x-o, y+o, 0]],
            "holes": [[[x-i, y-i, 0], [x+i, y-i, 0], [x+i, y+i, 0], [x-i, y+i, 0]]],
            "area": outer*outer - inner*inner, "layer": layer}

def build(name, **kw):
    d = json.loads(json.dumps(base))
    d["format"] = "simple3d"; d["format_version"] = 3
    d["silkscreen"] = {
        "thickness": 0.025,
        "top": [square(20, 20, 4, "REF DES/SILKSCREEN_TOP"),
                ring(40, 30, 6, 3, "BOARD GEOMETRY/SILKSCREEN_TOP"),
                square(60, 20, 2, "COMPONENT VALUE/SILKSCREEN_TOP")],
        "bottom": [square(30, 40, 3, "REF DES/SILKSCREEN_BOTTOM")],
        "warnings": ["zero width: text on REF DES/SILKSCREEN_TOP at (1.0, 2.0) - skipped"],
    }
    jf = OUT / f"{name}.json"; jf.write_text(json.dumps(d))
    logs = []
    res = core.generate(step_dir=ROOT/"demo/step_files", json_file=jf,
                        output_dir=OUT, output_name=name,
                        log=lambda m: logs.append(m), **kw)
    return res, logs

print("\n[1] silkscreen builds (package import reaches `from .colors import`)")
res, logs = build("silk_solid")
check("4 solids built", res.silkscreen_solids == 4, str(res.silkscreen_solids))
check("none skipped", res.silkscreen_skipped == 0, str(res.silkscreen_skipped))
txt = (OUT/"silk_solid.step").read_text(errors="replace")
check("silkscreen_top part present", "silkscreen_top" in txt)
check("silkscreen_bot part present", "silkscreen_bot" in txt)

print("\n[2] Allegro's declared areas are reproduced (arc/convention check quiet)")
area_warn = [m for m in logs if "differ from the area" in m]
check("no area disagreement", not area_warn, str(area_warn))
match = [m for m in logs if "match Allegro's areas" in m]
check("area agreement reported for both sides", len(match) == 2, str(match))

print("\n[3] warnings from the JSON reach the log with a colouring prefix")
warn = [m for m in logs if m.startswith("warning:") and "zero width" in m]
check("zero-width warning re-logged with prefix", len(warn) == 1, str(warn))

print("\n[4] layer exclusion")
res2, logs2 = build("silk_filtered",
                    silk_layers_off={"REF DES/SILKSCREEN_TOP", "REF DES/SILKSCREEN_BOTTOM"})
check("2 of 4 polygons left out", res2.silkscreen_solids == 2, str(res2.silkscreen_solids))
dropped = [m for m in logs2 if "left out by layer" in m]
check("both sides report the drop", len(dropped) == 2, str(dropped))

print("\n[5] a layer name that matches nothing changes nothing")
res3, _ = build("silk_nomatch", silk_layers_off={"NO SUCH LAYER"})
check("still 4 solids", res3.silkscreen_solids == 4, str(res3.silkscreen_solids))

print("\n[6] silkscreen switched off")
res4, logs4 = build("silk_off", silk_top=False, silk_bottom=False)
check("0 solids", res4.silkscreen_solids == 0, str(res4.silkscreen_solids))
check("warnings still logged when legend is off",
      any("zero width" in m for m in logs4), "warning lost")

print("\n[7] flat mode: faces unioned, file smaller")
res5, logs5 = build("silk_flat", silk_flat=True)
check("flat built 4", res5.silkscreen_solids == 4, str(res5.silkscreen_solids))
solid_sz = (OUT/"silk_solid.step").stat().st_size
flat_sz = (OUT/"silk_flat.step").stat().st_size
check(f"flat smaller than solid ({flat_sz} < {solid_sz})", flat_sz < solid_sz)
check("no merge failure warning",
      not [m for m in logs5 if "could not merge" in m], str(logs5[-3:]))

print("\n[8] one bad polygon is skipped, not fatal")
d = json.loads(json.dumps(base))
d["format"] = "simple3d"; d["format_version"] = 3
d["silkscreen"] = {"thickness": 0.025,
                   "top": [square(20, 20, 4, "L1"), {"vertices": [[0, 0, 0]], "area": 1.0, "layer": "L1"}],
                   "bottom": []}
jf = OUT/"silk_bad.json"; jf.write_text(json.dumps(d))
logs6 = []
res6 = core.generate(step_dir=ROOT/"demo/step_files", json_file=jf, output_dir=OUT,
                     output_name="silk_bad", log=lambda m: logs6.append(m))
check("good polygon still built", res6.silkscreen_solids == 1, str(res6.silkscreen_solids))
check("bad one counted as skipped", res6.silkscreen_skipped == 1, str(res6.silkscreen_skipped))
check("skip reported as a warning",
      any(m.startswith("warning:") and "skipped" in m for m in logs6), str(logs6[-2:]))

print("\n[9] the legend stops at zones whose stackup carries no silkscreen")

# A cross section assigns its mask and coating layers PER STACKUP, so a
# rigid-flex board says "no legend on the stiffener zones" by leaving the
# silkscreen layer out of those stackups. The exporter used to drop that layer
# - it is not body material - and with it the statement, after which the legend
# was printed over every zone alike. `stackup.silkscreen` carries it now.


def sq(x0, y0, x1, y1):
    return [{"type": "segment", "start": [x0, y0], "end": [x1, y0]},
            {"type": "segment", "start": [x1, y0], "end": [x1, y1]},
            {"type": "segment", "start": [x1, y1], "end": [x0, y1]},
            {"type": "segment", "start": [x0, y1], "end": [x0, y0]}]


def glyph(cx, cy):
    return {"layer": "REF DES/SILKSCREEN_TOP",
            "vertices": [[cx - 1, cy - 1, 0], [cx + 1, cy - 1, 0],
                         [cx + 1, cy + 1, 0], [cx - 1, cy + 1, 0]]}


ZONES = [{"name": "RIGID", "stackup": "P", "contour": sq(0, 0, 50, 50)},
         {"name": "STIFF", "stackup": "S", "contour": sq(50, 0, 100, 50)}]
PRINTED = {"P": {"thickness": 1.0, "layers": [], "silkscreen": {"top": True, "bottom": False}},
           "S": {"thickness": 1.0, "layers": [], "silkscreen": {"top": False, "bottom": False}}}
POLYS = [glyph(10, 10), glyph(25, 25), glyph(75, 25), glyph(90, 40), glyph(200, 200)]

said = []
kept = core.clip_silk_to_zones(POLYS, PRINTED, ZONES, "top", said.append)
check("glyphs on the printed zone stay", sum(1 for p in kept if p in POLYS[:2]) == 2)
check("glyphs on the bare zone go", not any(p in kept for p in POLYS[2:4]),
      len(kept))
check("a glyph on no zone at all is left alone", POLYS[4] in kept)
check("and the log names the zone and the count",
      any("STIFF carries no silkscreen" in m and "(2)" in m for m in said), said)

check("the bottom side is judged on its own flag",
      len(core.clip_silk_to_zones(POLYS, PRINTED, ZONES, "bottom", lambda m: None)) == 1,
      len(core.clip_silk_to_zones(POLYS, PRINTED, ZONES, "bottom", lambda m: None)))

# An intermediate written before the key says nothing about it, and then
# nothing is clipped - the legend goes everywhere, exactly as it used to.
OLD = {"P": {"thickness": 1.0, "layers": []}, "S": {"thickness": 1.0, "layers": []}}
check("an older intermediate is not clipped at all",
      len(core.clip_silk_to_zones(POLYS, OLD, ZONES, "top", lambda m: None)) == len(POLYS))
check("nor is a board where every zone is printed",
      len(core.clip_silk_to_zones(
          POLYS, {k: {**v, "silkscreen": {"top": True, "bottom": True}}
                  for k, v in PRINTED.items()},
          ZONES, "top", lambda m: None)) == len(POLYS))
check("and a board with no zones at all is untouched",
      len(core.clip_silk_to_zones(POLYS, PRINTED, None, "top", lambda m: None)) == len(POLYS))

print("\n[10] the arc code on real data: Allegro's own polygons and Allegro's own areas")

# Everything above this line is a square with radius 0.0 at every vertex, and
# so is every polygon in demo.json and in the other fixtures - which means the
# arc branch of `_wire_from_vertices`, and with it `_arc_bulges_left`,
# `_arc_geometry` and `_arc_edge`, never ran in this suite at all. Three
# mutations proved it in the audit of 2026-09-15 (docs/test-audit.md): arcs
# replaced by their chords, the bulge side inverted, and the per-polygon area
# comparison switched off all passed. The oracle here is the one the code was
# settled on in the first place: `area` per polygon is Allegro's own
# poly->area, not a number this test computed.

from stepbuilder import legend

fx = json.loads((ROOT / "tests/fixtures/silk_demo.json").read_text(encoding="utf-8"))
SAMPLE = fx["polygons"]

# The sample has to contain the cases or the checks below are vacuous - the
# same coverage check test_pads [4] makes about its pins.
radii = [float(v[2]) for p in SAMPLE for v in p["vertices"] if len(v) > 2]
check(f"{len(SAMPLE)} polygons sampled from Cadence's demo board", len(SAMPLE) >= 6, len(SAMPLE))
check("arcs of both signs are present",
      any(r > 1e-9 for r in radii) and any(r < -1e-9 for r in radii),
      f"{sum(1 for r in radii if r > 0)} positive, {sum(1 for r in radii if r < 0)} negative")
check("a hole whose own boundary is arcs is present",
      any(any(abs(float(v[2])) > 1e-9 for h in (p.get("holes") or []) for v in h)
          for p in SAMPLE))
check("both sides are represented",
      {p["side"] for p in SAMPLE} == {"top", "bottom"}, {p["side"] for p in SAMPLE})
check("a stroke doubling back on itself is present, not only rings",
      any(len(p["vertices"]) >= 12 for p in SAMPLE),
      max(len(p["vertices"]) for p in SAMPLE))

RIGHT = (legend.RULE_AXIS, True, True)


def worst_error(convention, polys=SAMPLE):
    """Largest relative disagreement with Allegro's areas over the sample."""
    worst = 0.0
    for p in polys:
        declared = abs(float(p["area"]))
        try:
            got = legend._face_area(legend._silk_face(p, 0.0, convention))
        except Exception:
            got = None
        worst = max(worst, float("inf") if got is None
                    else abs(got - declared) / declared)
    return worst


err = worst_error(RIGHT)
check(f"every polygon reproduces Allegro's area under the measured reading "
      f"(worst {err * 100:.4f}%)", err < 1.0e-4, err)

# Each polygon on its own line too, so one bad one cannot hide behind the rest.
for p in SAMPLE:
    declared = abs(float(p["area"]))
    got = legend._face_area(legend._silk_face(p, 0.0, RIGHT))
    check(f"  {p['side']} polygon of {len(p['vertices'])} vertices: "
          f"{got:.6f} against Allegro's {declared:.6f} mm2",
          abs(got - declared) / declared < 1.0e-4, f"{got} vs {declared}")

# The search has to land on that reading by itself, which is what says the arc
# side is read the way Allegro means it. Inverting `_arc_bulges_left` leaves
# the areas reproducible - the polarity flag absorbs it - and moves the winner
# here, so the areas alone would not notice.
picked = legend._pick_convention(SAMPLE, 0.0, lambda m: None, "top")
check(f"the search picks the reading measured on a real board {RIGHT}",
      tuple(picked) == RIGHT, picked)

# And the search has to be seen MOVING. RIGHT is listed first on purpose, so
# a "search" that returned the first candidate without scoring would pass
# every check above (measured, review of 2026-09-17). The same polygons with
# every radius negated are a board that means the opposite polarity, and the
# winner has to follow them there - the mirror reading, at zero error.
FLIPPED = [{**p, "vertices": [[v[0], v[1], -float(v[2])] for v in p["vertices"]],
            **({"holes": [[[v[0], v[1], -float(v[2])] for v in h] for h in p["holes"]]}
               if p.get("holes") else {})}
           for p in SAMPLE]
MIRROR = (legend.RULE_AXIS, False, True)
flipped_pick = legend._pick_convention(FLIPPED, 0.0, lambda m: None, "top")
check(f"with every radius negated the search moves to the mirror reading {MIRROR}",
      tuple(flipped_pick) == MIRROR and legend._CONVENTIONS.index(MIRROR) > 0, flipped_pick)
check("which reproduces those areas exactly while the measured reading no longer does",
      worst_error(MIRROR, FLIPPED) < 1.0e-4 and worst_error(RIGHT, FLIPPED) > 0.05,
      (worst_error(MIRROR, FLIPPED), worst_error(RIGHT, FLIPPED)))

# And the oracle has to be able to say no: every other reading is wrong by far
# more than AREA_TOLERANCE on this sample, which makes the win above a
# measurement rather than list order.
others = {c: worst_error(c) for c in legend._CONVENTIONS if tuple(c) != RIGHT}
closest = min(others.values())
check(f"all {len(others)} other readings are off by at least "
      f"{closest * 100:.1f}% (the tolerance is {legend.AREA_TOLERANCE * 100:.1f}%)",
      closest > 10 * legend.AREA_TOLERANCE,
      {legend._describe_convention(c): round(e, 4) for c, e in others.items()})

# The arcs themselves: the same polygons with every radius zeroed is what the
# code would be building if the arc branch were never taken.
CHORDS = [{**p, "vertices": [[v[0], v[1], 0.0] for v in p["vertices"]],
           **({"holes": [[[v[0], v[1], 0.0] for v in h] for h in p["holes"]]}
              if p.get("holes") else {})}
          for p in SAMPLE]
chord_err = worst_error(RIGHT, CHORDS)
check(f"the same polygons as straight chords miss the areas by "
      f"{chord_err * 100:.1f}%", chord_err > 0.05, chord_err)

print("\n[11] the area cross-check is seen saying no")

# [2] above only ever watches it agree, so the comparison itself was never
# seen reporting a difference. One polygon carrying an area Allegro did not
# report has to be named.
good_logs = []
compound, built, skipped = legend.build_silkscreen(
    SAMPLE, 0.0, 0.025, log=good_logs.append, side="top")
check(f"all {len(SAMPLE)} sampled polygons build", (built, skipped) == (len(SAMPLE), 0),
      (built, skipped))
check("and are reported as matching Allegro",
      any("match Allegro's areas" in m for m in good_logs), good_logs)

bent = [dict(p) for p in SAMPLE]
bent[0] = {**bent[0], "area": float(bent[0]["area"]) * 1.25}
bad_logs = []
legend.build_silkscreen(bent, 0.0, 0.025, log=bad_logs.append, side="top")
said = [m for m in bad_logs if "differ from the area Allegro reported" in m]
check("a 25% disagreement on one polygon is reported", len(said) == 1, bad_logs)
check("and the message carries the count and both areas",
      bool(said) and f"1 of {len(SAMPLE)}" in said[0] and "20.0%" in said[0], said)
check("while the agreement line is not printed as well",
      not [m for m in bad_logs if "match Allegro's areas" in m], bad_logs)

print("\n[12] and they go through the whole build")

d = json.loads(json.dumps(base))
d["format"] = "simple3d"; d["format_version"] = 3
d["silkscreen"] = {"thickness": 0.025,
                   "top": [p for p in SAMPLE if p["side"] == "top"],
                   "bottom": [p for p in SAMPLE if p["side"] == "bottom"]}
jf = OUT / "silk_real.json"; jf.write_text(json.dumps(d))
logs7 = []
res7 = core.generate(step_dir=ROOT / "demo/step_files", json_file=jf, output_dir=OUT,
                     output_name="silk_real", log=lambda m: logs7.append(m))
check("every sampled polygon becomes a solid",
      res7.silkscreen_solids == len(SAMPLE), res7.silkscreen_solids)
check("none skipped", res7.silkscreen_skipped == 0, res7.silkscreen_skipped)
check("no area disagreement on either side",
      not [m for m in logs7 if "differ from the area" in m],
      [m for m in logs7 if "differ from the area" in m])

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
