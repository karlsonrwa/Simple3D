"""The silkscreen's fill kinds against Allegro's own artwork (round 111).

    python tools/silk_artwork.py [--board input/my_test_board2.brd] [-o build/silk-artwork]

What R2-13 of the 28.10.2026 review asked for: a board with an unfilled
rectangle, unfilled shapes and cross-hatched shapes on a silkscreen layer,
the Gerber Allegro makes of it, and the exporter's polygons compared with
that Gerber. Three steps, all headless, all on copies:

1. s3dProbeSilkCases (tools/probes/probe_silkfill.il) draws the cases on
   BOARD GEOMETRY/SILKSCREEN_BOTTOM of a copy of the board - that layer is
   empty on my_test_board2 - creates two films holding that layer alone,
   S3D_SILKB with an undefined line width of 0.05 and S3D_SILKB0 with the
   default 0, saves the copy as silkcases.brd and runs the exporter on it;
2. Allegro's `artwork` batch writes each film, in RS274X millimetres at five
   decimals (art_param.txt beside the copy: without one it falls back to
   Gerber 6x00 in inches at 1 mil, apertures outside the file - measured
   30.10.2026);
3. gerbonara - not anything of ours - reads each Gerber into primitives, the
   intermediate's polygons are rebuilt with the vertex reading
   stepbuilder/legend.py measured, and both are drawn case by case on a 5 um
   grid: the ink of each, the difference both ways, the agreement.

Needs Allegro (licensed on this machine, so this runs here, not on the
4090) and gerbonara with numpy (the default python here has both). The board
is the owner's, so the copy and everything made from it stay under build/.
The record of a run is docs/records/silk-fill-artwork-2026-10-30.md.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from run_probe import find_allegro, run as run_probe  # noqa: E402
from skill_export import allegro_env, allegro_home  # noqa: E402

PROBE = ROOT / "tools" / "probes" / "probe_silkfill.il"
EXPORTER = ROOT / "makeVariant3dIntermediates.il"
ARTWORK = Path(r"D:\Cadence\SPB_25.1\tools\bin\artwork.exe")
FILMS = ("S3D_SILKB", "S3D_SILKB0")
ART_PARAM = (
    "DEVICE-TYPE           GERBER_RS274X\n"
    "OUTPUT-UNITS          METRIC\n"
    "FILM-SIZE             240000 160000\n"
    "FORMAT                3.5\n"
    "ABORT-ON-ERROR        NO\n"
    "SCALE                 1\n"
    "SUPPRESS-LEAD-ZEROES  YES\n"
    "SUPPRESS-TRAIL-ZEROES NO\n"
    "SUPPRESS-EQUAL        YES\n"
    "UNDEF-APT-CONT        NO\n")

H = 0.005          # mm per pixel
MARGIN = 0.5
SIZE = 4.0
# The lower-left corners of the 4 mm squares s3dProbeSilkCases draws - the
# two lists are kept by hand, so a case moved there must move here.
CASES = {
    "A unfilled rectangle": (2.0, 2.0),
    "C unfilled, width 0": (14.0, 2.0),
    "E cross-hatch 45": (2.0, 9.0),
    "F cross-hatch 45+135": (8.0, 9.0),
    "G solid": (14.0, 9.0),
    "H cross-hatch 0+90, void": (20.0, 9.0),
}


# --- 1 and 2: the probe and the artwork ----------------------------------------

def make_cases(board: Path, out: Path, allegro: Path) -> Path:
    os.environ["S3D_PROBE_OUT"] = str(out).replace("\\", "/")
    console = run_probe(PROBE, "s3dProbeSilkCases", board, out, allegro,
                        preload=[EXPORTER], home=allegro_home(None))
    saved = out / "silkcases.brd"
    if not saved.exists():
        sys.exit(f"the probe saved no silkcases.brd; its console is {console}")
    return console


def artwork(board: Path, film: str, out: Path) -> Path:
    """One film's Gerber, made in a folder of its own beside a copy."""
    folder = out / f"art_{film}"
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(board, folder / board.name)
    (folder / "art_param.txt").write_text(ART_PARAM, encoding="ascii")
    r = subprocess.run([str(ARTWORK), "-f", film, board.name], cwd=folder,
                       capture_output=True, text=True, errors="replace", timeout=600,
                       env=allegro_env(allegro_home(None)))
    art = folder / f"{film}.art"
    log = folder / "photoplot.log"
    warnings = [line.strip() for line in log.read_text(encoding="utf-8", errors="replace").splitlines()
                if "WARNING" in line] if log.exists() else []
    print(f"  artwork -f {film}: exit {r.returncode}, {art.stat().st_size if art.exists() else 0} bytes"
          + "".join(f"\n    {w}" for w in warnings))
    if not art.exists():
        sys.exit(f"artwork wrote no {art.name}; see {log}")
    return art


# --- 3: both drawn on one grid ----------------------------------------------

class Grid:
    def __init__(self, x0, y0, x1, y1):
        import numpy as np
        self.np = np
        self.x0, self.y0 = x0, y0
        nx = int(round((x1 - x0) / H))
        ny = int(round((y1 - y0) / H))
        self.X, self.Y = np.meshgrid(x0 + (np.arange(nx) + 0.5) * H,
                                     y0 + (np.arange(ny) + 0.5) * H)
        self.ink = np.zeros_like(self.X, dtype=bool)

    def window(self, xa, ya, xb, yb):
        ny, nx = self.X.shape
        i0 = max(0, int(math.floor((xa - self.x0) / H)) - 1)
        i1 = min(nx, int(math.ceil((xb - self.x0) / H)) + 1)
        j0 = max(0, int(math.floor((ya - self.y0) / H)) - 1)
        j1 = min(ny, int(math.ceil((yb - self.y0) / H)) + 1)
        return slice(j0, j1), slice(i0, i1)

    def put(self, sl, mask, dark):
        if dark:
            self.ink[sl] |= mask
        else:
            self.ink[sl] &= ~mask

    def stroke(self, x1, y1, x2, y2, width, dark=True):
        """A round aperture swept from (x1, y1) to (x2, y2)."""
        np = self.np
        r = width / 2.0
        sl = self.window(min(x1, x2) - r, min(y1, y2) - r, max(x1, x2) + r, max(y1, y2) + r)
        X, Y = self.X[sl], self.Y[sl]
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        if L2 < 1e-18:
            d2 = (X - x1) ** 2 + (Y - y1) ** 2
        else:
            t = np.clip(((X - x1) * dx + (Y - y1) * dy) / L2, 0.0, 1.0)
            d2 = (X - (x1 + t * dx)) ** 2 + (Y - (y1 + t * dy)) ** 2
        self.put(sl, d2 <= r * r, dark)

    def fill(self, rings, dark=True):
        """Even-odd fill of closed point rings, outer and holes together."""
        np = self.np
        pts = np.concatenate([np.asarray(r) for r in rings])
        sl = self.window(pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max())
        X, Y = self.X[sl], self.Y[sl]
        inside = np.zeros_like(X, dtype=bool)
        for ring in rings:
            ring = np.asarray(ring)
            xa, ya = ring[:, 0], ring[:, 1]
            xb, yb = np.roll(xa, -1), np.roll(ya, -1)
            for k in range(len(ring)):
                if ya[k] == yb[k]:
                    continue
                cond = (ya[k] > Y) != (yb[k] > Y)
                xint = xa[k] + (Y - ya[k]) * (xb[k] - xa[k]) / (yb[k] - ya[k])
                inside ^= cond & (X < xint)
        self.put(sl, inside, dark)


def arc_points(x1, y1, x2, y2, cx, cy, clockwise):
    """A Gerber arc as points; start == end is the full circle (G75)."""
    r = math.hypot(x1 - cx, y1 - cy)
    a1 = math.atan2(y1 - cy, x1 - cx)
    a2 = math.atan2(y2 - cy, x2 - cx)
    sweep = (a1 - a2) if clockwise else (a2 - a1)
    if sweep <= 1e-12:
        sweep += 2 * math.pi
    if clockwise:
        sweep = -sweep
    n = min(20000, max(8, int(abs(sweep) * r / (H / 4.0)) + 1))
    return [(cx + r * math.cos(a1 + sweep * i / n), cy + r * math.sin(a1 + sweep * i / n))
            for i in range(n + 1)]


def draw_gerber(grid: Grid, prims) -> None:
    from gerbonara import graphic_primitives as gp
    for p in prims:
        if isinstance(p, gp.Line):
            grid.stroke(p.x1, p.y1, p.x2, p.y2, p.width, p.polarity_dark)
        elif isinstance(p, gp.Arc):
            pts = arc_points(p.x1, p.y1, p.x2, p.y2, p.cx, p.cy, p.clockwise)
            for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
                grid.stroke(xa, ya, xb, yb, p.width, p.polarity_dark)
        elif isinstance(p, gp.Circle):
            grid.stroke(p.x, p.y, p.x, p.y, 2.0 * p.r, p.polarity_dark)
        elif isinstance(p, gp.ArcPoly):
            # gerbonara's own segment walk, arcs cut to a quarter of a pixel
            grid.fill([list(p.approximate_arcs(max_error=H / 4.0).outline)], p.polarity_dark)
        else:
            sys.exit(f"a primitive this comparison does not draw: {type(p).__name__}")


def json_ring(vertices):
    """An intermediate polygon's vertex list as points, read AXIS /
    positive-sits-left / first-radius-closes (stepbuilder/legend.py, the
    reading measured on Allegro 24.1 and checked here against each area)."""
    pts = [(float(v[0]), float(v[1])) for v in vertices]
    rad = [float(v[2]) if len(v) > 2 else 0.0 for v in vertices]
    ring = []
    for i in range(len(pts)):
        p0, p1 = pts[i - 1], pts[i]          # vertex i's radius is the edge reaching it
        r = rad[i]
        if abs(r) < 1e-9:
            ring.append(p0)
            continue
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        chord = math.hypot(dx, dy)
        if chord < 1e-12:
            continue
        R = max(abs(r), chord / 2)
        h = math.sqrt(max(0.0, R * R - chord * chord / 4))
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        nx, ny = -dy / chord, dx / chord                 # left normal of travel
        left = ((nx < 0.0) == (r > 0.0)) if abs(nx) > 1e-12 else (r > 0.0)
        s = 1.0 if left else -1.0
        cx, cy = mx - s * h * nx, my - s * h * ny        # the centre opposite the bulge
        a0 = math.atan2(p0[1] - cy, p0[0] - cx)
        sweep = math.atan2(p1[1] - cy, p1[0] - cx) - a0
        while sweep > math.pi:
            sweep -= 2 * math.pi
        while sweep < -math.pi:
            sweep += 2 * math.pi
        k = max(8, int(abs(sweep) * R / (H / 4)) + 1)
        ring.extend((cx + R * math.cos(a0 + sweep * j / k), cy + R * math.sin(a0 + sweep * j / k))
                    for j in range(k))
    return ring


def shoelace(ring):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1])) / 2.0


def compare(art: Path, intermediate: Path, side: str = "bottom") -> list[tuple]:
    from gerbonara import GerberFile
    from gerbonara.utils import MM
    gerber = GerberFile.open(str(art))
    prims = [p for obj in gerber.objects for p in obj.to_primitives(unit=MM)]
    polys = json.loads(intermediate.read_text(encoding="utf-8"))["silkscreen"][side]
    rings_of, off = [], 0
    for poly in polys:
        outer = json_ring(poly["vertices"])
        holes = [json_ring(h) for h in poly.get("holes", [])]
        area = abs(shoelace(outer)) - sum(abs(shoelace(h)) for h in holes)
        if abs(area - float(poly["area"])) > 0.005 * abs(float(poly["area"])) + 1e-6:
            off += 1
        rings_of.append([outer] + holes)
    print(f"  {art.name}: {len(prims)} primitive(s); {intermediate.name}: {len(polys)} {side} "
          f"polygon(s), {off} rebuilt more than 0.5 % off Allegro's own area")
    rows = []
    for name, (x0, y0) in CASES.items():
        box = (x0 - MARGIN, y0 - MARGIN, x0 + SIZE + MARGIN, y0 + SIZE + MARGIN)
        g, j = Grid(*box), Grid(*box)
        draw_gerber(g, prims)
        for rings in rings_of:
            xs = [p[0] for p in rings[0]]
            ys = [p[1] for p in rings[0]]
            if max(xs) >= box[0] and min(xs) <= box[2] and max(ys) >= box[1] and min(ys) <= box[3]:
                j.fill(rings)
        np, px = g.np, H * H
        both = np.count_nonzero(g.ink & j.ink)
        either = np.count_nonzero(g.ink | j.ink)
        rows.append((name, np.count_nonzero(g.ink) * px, np.count_nonzero(j.ink) * px,
                     np.count_nonzero(j.ink & ~g.ink) * px, np.count_nonzero(g.ink & ~j.ink) * px,
                     both / either if either else 1.0))
    return rows


def print_rows(rows) -> None:
    print(f"    {'case':26s} {'Gerber, mm2':>11s} {'export, mm2':>11s} {'export only':>11s} "
          f"{'Gerber only':>11s} {'agreement':>9s}")
    for name, g, j, jo, go, agree in rows:
        print(f"    {name:26s} {g:11.4f} {j:11.4f} {jo:11.4f} {go:11.4f} {agree * 100:8.2f}%")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--board", default=str(ROOT / "input" / "my_test_board2.brd"))
    ap.add_argument("-o", "--out", default=str(ROOT / "build" / "silk-artwork"))
    ap.add_argument("--allegro", default=None)
    args = ap.parse_args(argv)
    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    t0 = time.time()
    console = make_cases(Path(args.board), out, find_allegro(args.allegro))
    made = [line for line in console.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.startswith("case ") or "zero width" in line]
    print("\n".join("  " + line for line in made))
    for film in FILMS:
        art = artwork(out / "silkcases.brd", film, out)
        print_rows(compare(art, out / "silkcases.json"))
    print(f"done in {time.time() - t0:.0f} s; everything is under {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
