"""How the legend's area check sees a board (round 113).

    python tools/silk_areas.py BOARD.json [BOARD.json ...]

What R2-8 of the 23.10.2026 review asked for: a tolerance for "this polygon
came out as Allegro drew it" grounded in the measured rounding of the
coordinates, and shown on the boards. Every legend polygon of each
intermediate that carries Allegro's `area` is rebuilt by stepbuilder's own
code (legend._silk_face, OCP faces) under each of the eight readings of its
arcs, and its disagreement with that area is measured in shares of its
rounding margin, legend._area_margin: sqrt(2) x perimeter x the grid the
vertices sit on, plus the area's last digit.

Per board side it prints the grid, the right reading's largest share, for
every other reading how many polygons it puts past the margin (0 means the
per-polygon check alone could not see it) and its largest share, how many
readings the pick's eight-polygon sample leaves within the margin (more than
one sends the pick to the whole side), and the reading the pick lands on.

Needs OCP, so it runs where the suites run (the 4090 here). The boards are
the owner's: read their intermediates in place and keep what this prints
under build/. The record of a run is
docs/records/silk-area-rounding-2026-10-31.md.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from stepbuilder import legend  # noqa: E402

RIGHT = (legend.RULE_AXIS, True, True)


def shares(polygons: list, convention, step: float) -> list[float]:
    """Each polygon's miss of Allegro's area, in shares of its margin."""
    out = []
    for polygon in polygons:
        declared = abs(float(polygon["area"]))
        try:
            face = legend._silk_face(polygon, 0.0, convention)
            area, margin = legend._face_area(face), legend._area_margin(face, step)
        except Exception:                      # a reading that does not build
            area = margin = None
        out.append(float("inf") if area is None or margin is None
                   else abs(area - declared) / margin)
    return out


def side_report(name: str, side: str, polygons: list) -> None:
    polys = [p for p in polygons if p.get("vertices") and p.get("area")
             and abs(float(p["area"])) > 1.0e-6]
    if not polys:
        return
    started = time.perf_counter()
    step = legend._coordinate_step(polygons)
    right = shares(polys, RIGHT, step)
    print(f"\n{name} {side}: {len(polys)} polygons with an area, grid "
          f"{legend._step_text(step)} mm; the right reading uses at most "
          f"{max(right):.3f} of the margin")
    for convention in legend._CONVENTIONS:
        if tuple(convention) == RIGHT:
            continue
        s = shares(polys, convention, step)
        past = sum(1 for x in s if x > 1.0)
        print(f"   {legend._describe_convention(convention):70s} past the margin on "
              f"{past:4d}, at most {max(s):9.3f}")
    curved = [p for p in polys
              if any(abs(float(v[2])) > 1.0e-9 for v in p["vertices"] if len(v) > 2)]
    sample = sorted(curved or polys, key=lambda p: len(p["vertices"]))[:8]
    close = [c for c in legend._CONVENTIONS
             if legend._worst_share(sample, 0.0, c, step)[0] <= 1.0]
    said = []
    picked = legend._pick_convention(polygons, 0.0, said.append, side, step)
    print(f"   the eight-polygon sample leaves {len(close)} reading(s) within the margin"
          f"{' - the whole side decides' if len(close) > 1 and curved else ''}; "
          f"the pick: {'the right reading' if tuple(picked) == RIGHT else 'WRONG ' + str(picked)}"
          f"{'; ' + said[0] if said else ''}  ({time.perf_counter() - started:.1f} s)")


def main(paths: list[str]) -> int:
    if not paths:
        print(__doc__)
        return 2
    for path in paths:
        board = json.loads(Path(path).read_text(encoding="utf-8"))
        silk = board.get("silkscreen") or {}
        for side in ("top", "bottom"):
            side_report(Path(path).stem, side, silk.get(side) or [])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
