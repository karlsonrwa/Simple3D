"""Run one read-only SKILL probe against a board in a headless Allegro.

    python tools/run_probe.py tools/probes/probe_pads.il s3dProbePads input/Cadence_Demo.brd
    python tools/run_probe.py PROBE.il PROC BOARD.brd [-o build/probe-out] [--allegro EXE]

The same recipe as tools/skill_export.py (round 75): the board is COPIED to a
scratch folder and Allegro is pointed at the copy, the `-s` script path is
absolute, `-safe` is never passed. The probe file is load()ed, PROC is
called inside errset so a SKILL error still reaches `exit`, and the whole
console goes to <out>/<board stem>.<proc>.txt - which is the result.

Scratch and output stay under the repository's build/ (gitignored), never
the C: drive.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLEGRO_CANDIDATES = (
    Path(r"D:\Cadence\SPB_25.1\tools\bin\allegro.exe"),
    Path(r"D:\Cadence\SPB_24.1\tools\bin\allegro.exe"),
)
TIMEOUT = 900


def slashes(p: Path | str) -> str:
    return str(p).replace("\\", "/")


def find_allegro(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            sys.exit(f"allegro not found at {p}")
        return p
    for p in ALLEGRO_CANDIDATES:
        if p.exists():
            return p
    sys.exit("allegro.exe not found; pass --allegro <path>")


def run(probe: Path, proc: str, brd: Path, out_dir: Path, allegro: Path,
        preload: list[Path] = ()) -> Path:
    """*preload*: .il files load()ed before the probe - the exporter itself
    (makeVariant3dIntermediates.il) when the probe calls its procedures;
    a probe that does and is loaded alone fails at the call, and inside a
    headless session that can look like a hang."""
    # ABSOLUTE, whatever the caller passed: the `.scr` lives under this
    # folder and Allegro resolves a relative `-s` path against the DESIGN's
    # folder, finds nothing, and waits forever with no window to say so.
    # Six "hung" probes on 2026-09-07 were exactly `-o build/probe-out`;
    # every run given an absolute folder finished in 25 s.
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / f"_work_{brd.stem}_{int(time.time())}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        copy = work / brd.name
        shutil.copy2(brd, copy)
        scr = work / "run.scr"
        scr.write_text(
            "".join(f'skill load("{slashes(Path(p).resolve())}")\n' for p in preload)
            + f'skill load("{slashes(probe.resolve())}")\n'
            f'skill errset( {proc}() t )\n'
            "exit\n", encoding="ascii")
        cmd = [str(allegro), "-nograph", "-s", slashes(scr), slashes(copy)]
        t0 = time.time()
        print(f"  {brd.name} ({brd.stat().st_size / 1e6:.1f} MB) {proc} ...", end="", flush=True)
        # The console goes STRAIGHT to the result file, not through a pipe
        # read at the end: a session that hangs then still leaves everything
        # it printed before it stopped, which is the one clue there is. A
        # probe that wants its lines there at once follows each printf with
        # drain( poport ).
        result = out_dir / f"{brd.stem}.{proc}.txt"
        with open(result, "w", encoding="utf-8", errors="replace") as console:
            try:
                r = subprocess.run(cmd, stdout=console, stderr=subprocess.STDOUT,
                                   timeout=TIMEOUT)
                rc: int | str = r.returncode
            except subprocess.TimeoutExpired:
                rc = f"TIMED OUT after {TIMEOUT}s"
        print(f" exit {rc} in {time.time() - t0:.0f}s -> {result}")
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("probe", help="the .il file to load")
    ap.add_argument("proc", help="the procedure to call, without parentheses")
    ap.add_argument("boards", nargs="+", help=".brd files")
    ap.add_argument("-o", "--out", default=str(ROOT / "build" / "probe-out"))
    ap.add_argument("--allegro", default=None)
    ap.add_argument("--with-exporter", action="store_true",
                    help="load makeVariant3dIntermediates.il first, for a probe that "
                         "calls the exporter's procedures (s3dSelectVisibleOn and the like)")
    args = ap.parse_args(argv)
    allegro = find_allegro(args.allegro)
    print(f"allegro: {allegro}")
    preload = [ROOT / "makeVariant3dIntermediates.il"] if args.with_exporter else []
    for b in args.boards:
        brd = Path(b)
        if not brd.exists():
            print(f"no such board: {brd}")
            return 1
        run(Path(args.probe), args.proc, brd, Path(args.out), allegro, preload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
