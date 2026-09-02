"""Run the SKILL exporter headless, and keep its output as a golden corpus.

    python tools/skill_export.py input/Cadence_Demo.brd -o build/skill-out
    python tools/skill_export.py --record          every input/*.brd -> build/skill_golden/
    python tools/skill_export.py --check           export again, compare to the record

What golden.py is for the Python half, this is for the SKILL half: every
refactoring step of makeVariant3dIntermediates.il (Plan D) is closed by
`--check` saying the intermediate JSON it writes has not changed, on every
board in input/. The boards there are the only ones used - they are the
user's, gitignored, and the corpus beside them (build/) is gitignored too.

HOW ALLEGRO IS DRIVEN (round 75; learned in the AllegroBaseStructure repo)

    allegro -nograph -s <ABSOLUTE script path> <board>

opens no window and exits when the script says `exit`. Two rules, each of
which cost an afternoon over there:

  * The `-s` path must be absolute. Allegro resolves a relative one against
    the DESIGN's directory, finds nothing, and sits in its command loop with
    no window to say so - which looks exactly like "Allegro cannot be run
    from a shell". It can.
  * The board is copied to a scratch folder first and Allegro is pointed at
    the copy: the original is never opened, never locked, never saved over.
    `-readonly` would say the same with a modal notice - one more thing to
    go wrong unattended. A Variants.lst beside the board travels with it,
    because the exporter looks for it beside the board and nowhere else.

The script loads makeVariant3dIntermediates.il alone (the loader of the nine
parts under skill/ since round 76) - not simple3d.il, whose
job is the menu item, the pre-flight and the Python launch - and calls
makeVariant3dIntermediates(dir, color, config) the way s3dExportCommand does,
with the shipped simple3d_config.json (not the user's local overlay: the
corpus must not depend on one machine's settings). errset around the call so
a SKILL error still reaches `exit` instead of a session that never ends; the
console goes to <stem>.allegro.txt beside the JSON, and that is where a
failed export explains itself.

`-safe` is never passed: it drops the site configuration, which is where the
licence server is named, and the run dies with "No licenses available".
"""

from __future__ import annotations

import argparse
import difflib
import filecmp
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORTER = ROOT / "makeVariant3dIntermediates.il"
CONFIG = ROOT / "simple3d_config.json"
INPUT = ROOT / "input"
GOLDEN = ROOT / "build" / "skill_golden"
ALLEGRO_CANDIDATES = (
    Path(r"D:\Cadence\SPB_25.1\tools\bin\allegro.exe"),
    Path(r"D:\Cadence\SPB_24.1\tools\bin\allegro.exe"),
)
TIMEOUT = 900          # seconds per board; the 31 MB one takes well under that


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


def export(brd: Path, out_dir: Path, allegro: Path, *, quiet: bool = False) -> list[Path]:
    """Export one board's intermediate(s) into out_dir; the JSON paths written.

    Returns [] when nothing was written; the console transcript is in
    out_dir/<stem>.allegro.txt either way.
    """
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="s3dexport_"))
    try:
        copy = work / brd.name
        shutil.copy2(brd, copy)
        variants = brd.with_name("Variants.lst")
        if variants.exists():
            shutil.copy2(variants, work / "Variants.lst")
        scr = work / "run.scr"
        # ASCII on purpose: a path with a non-ASCII byte is a different
        # problem, and this file must never be the thing that fails.
        scr.write_text(
            f'skill load("{slashes(EXPORTER)}")\n'
            f'skill errset( makeVariant3dIntermediates("{slashes(out_dir)}" '
            f'list(0.0 0.4 0.0) "{slashes(CONFIG)}") t )\n'
            "exit\n", encoding="ascii")
        cmd = [str(allegro), "-nograph", "-s", slashes(scr), slashes(copy)]
        before = {p.name for p in out_dir.glob("*.json")}
        t0 = time.time()
        if not quiet:
            print(f"  {brd.name} ({brd.stat().st_size / 1e6:.1f} MB) ...", end="", flush=True)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT,
                               errors="replace")
            console = (r.stdout or "") + (r.stderr or "")
            rc: int | str = r.returncode
        except subprocess.TimeoutExpired as exc:
            console = ((exc.stdout or b"").decode("utf-8", "replace")
                       + (exc.stderr or b"").decode("utf-8", "replace"))
            rc = f"TIMED OUT after {TIMEOUT}s"
        dt = time.time() - t0
        (out_dir / f"{brd.stem}.allegro.txt").write_text(console, encoding="utf-8")
        written = sorted(p for p in out_dir.glob("*.json")
                         if p.name not in before or p.stat().st_mtime >= t0 - 1)
        if not quiet:
            names = ", ".join(p.name for p in written) or "NOTHING"
            print(f" exit {rc} in {dt:.0f}s -> {names}")
            if not written:
                tail = "\n".join(console.splitlines()[-15:])
                print("    allegro said:\n" + "\n".join("    | " + l for l in tail.splitlines()))
        return written
    finally:
        shutil.rmtree(work, ignore_errors=True)


def boards() -> list[Path]:
    found = sorted(INPUT.glob("*.brd"))
    if not found:
        sys.exit(f"no *.brd in {INPUT}")
    return found


def record(allegro: Path) -> int:
    if GOLDEN.exists():
        shutil.rmtree(GOLDEN)
    failed = []
    for brd in boards():
        if not export(brd, GOLDEN / brd.stem, allegro):
            failed.append(brd.name)
    n = len(list(GOLDEN.glob("*/*.json")))
    print(f"\nrecorded {n} intermediate(s) from {len(boards())} board(s) into {GOLDEN}")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


def check(allegro: Path, keep: Path | None) -> int:
    if not GOLDEN.exists():
        sys.exit(f"no record at {GOLDEN}; run --record first")
    work = keep or Path(tempfile.mkdtemp(prefix="s3dcheck_"))
    drift: list[str] = []
    try:
        for brd in boards():
            golden_dir = GOLDEN / brd.stem
            if not golden_dir.exists():
                drift.append(f"{brd.name}: not in the record (recorded before it was added?)")
                continue
            out = work / brd.stem
            export(brd, out, allegro)
            expected = sorted(p.name for p in golden_dir.glob("*.json"))
            got = sorted(p.name for p in out.glob("*.json"))
            if expected != got:
                drift.append(f"{brd.name}: files {expected} -> {got}")
                continue
            for name in expected:
                a, b = golden_dir / name, out / name
                if filecmp.cmp(a, b, shallow=False):
                    continue
                la = a.read_text(encoding="utf-8", errors="replace").splitlines()
                lb = b.read_text(encoding="utf-8", errors="replace").splitlines()
                diff = list(difflib.unified_diff(la, lb, "golden/" + name, "now/" + name, lineterm="", n=1))
                changed = sum(1 for l in diff if l[:1] in "+-" and not l.startswith(("+++", "---")))
                drift.append(f"{brd.name}/{name}: {changed} line(s) differ\n" + "\n".join(diff[:40]))
    finally:
        if keep is None:
            shutil.rmtree(work, ignore_errors=True)
    if drift:
        print("\nDRIFT against the record:")
        for d in drift:
            print("  " + d.replace("\n", "\n    "))
        return 1
    print(f"\nno difference against {GOLDEN} ({len(boards())} boards)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("boards", nargs="*", help=".brd files to export (default: none)")
    ap.add_argument("-o", "--out", default="build/skill-out", help="where the JSON goes")
    ap.add_argument("--record", action="store_true", help="export every input/*.brd into build/skill_golden/")
    ap.add_argument("--check", action="store_true", help="export again and compare to the record")
    ap.add_argument("--keep", default=None, help="with --check: keep the fresh exports in this folder")
    ap.add_argument("--allegro", default=None, help="path to allegro.exe")
    args = ap.parse_args(argv)
    allegro = find_allegro(args.allegro)
    print(f"allegro: {allegro}")
    if args.record:
        return record(allegro)
    if args.check:
        return check(allegro, Path(args.keep) if args.keep else None)
    if not args.boards:
        ap.print_help()
        return 2
    rc = 0
    for b in args.boards:
        brd = Path(b)
        if not brd.exists():
            print(f"no such board: {brd}")
            rc = 1
            continue
        if not export(brd, Path(args.out) / brd.stem, allegro):
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
