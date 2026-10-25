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

ALLEGRO RUNS WITH A HOME OF ITS OWN (round 100)

With the user's HOME every `-nograph` session loads the user's
pcbenv\\allegro.ilinit - the INSTALLED tools, Simple 3D among them, before
this tree's code - and writes their pcbenv (allegro.mru, directory= in
allegro.ini). And here the user's HOME is D:\\Projects\\OrCAD, which the
owner has closed to me altogether (11.10.2026). So HOME is `--home`, by
default build/allegro-home (gitignored): its pcbenv holds an allegro.ini with
only the licence lines (base_license, option_licenses) and an env of
`source $TELENV` plus the units a design without a board takes. Without the
licence lines Allegro says "No licenses available" and exits, so the runner
refuses before starting it; a HOME under D:\\Projects\\OrCAD is refused too.
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
HOME = ROOT / "build" / "allegro-home"
OFF_LIMITS = Path(r"D:\Projects\OrCAD")


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


def off_limits(path: str) -> bool:
    """Whether `path` - a Windows or an MSYS spelling - is OFF_LIMITS or under
    it. Judged on the string alone: Path.resolve() would open the folder to
    find out, and even that is touching it (round 100)."""
    norm = os.path.normcase(str(path).replace("/", "\\"))
    if norm.startswith("\\") and len(norm) > 2 and norm[2:3] == "\\":    # \d\Projects -> d:\Projects
        norm = norm[1] + ":" + norm[2:]
    root = os.path.normcase(str(OFF_LIMITS))
    return norm == root or norm.startswith(root + "\\")


def allegro_home(explicit: str | None) -> Path:
    """The HOME Allegro runs with: never the user's, never under OFF_LIMITS,
    and one whose pcbenv\\allegro.ini names the licences."""
    if explicit and off_limits(os.path.abspath(explicit)):
        sys.exit(f"refused: {explicit} is under {OFF_LIMITS}, which this tool must not touch")
    home = Path(os.path.abspath(explicit)) if explicit else HOME
    ini = home / "pcbenv" / "allegro.ini"
    lines = ini.read_text(encoding="utf-8", errors="replace").splitlines() if ini.is_file() else []
    if not any(line.split("=", 1)[0].strip() == "base_license" for line in lines):
        sys.exit(f"no licence lines in {ini}: give the runner a HOME of its own - a pcbenv with an "
                 "allegro.ini holding base_license and option_licenses, and an env of "
                 "source $TELENV and the units (see the docstring)")
    return home


def allegro_env(home: Path, environ=None) -> dict:
    """The environment Allegro runs with - this process's (or *environ*) with
    HOME its own and nothing that leads into OFF_LIMITS: here the user's
    MAGICK_HOME and POTRACE_PATH do, and two entries of PATH (measured
    25.10.2026), and Windows looks for DLLs along PATH."""
    env = {}
    for key, value in (os.environ if environ is None else environ).items():
        if key.upper() == "PATH":
            value = os.pathsep.join(p for p in value.split(os.pathsep) if not off_limits(p))
        elif any(off_limits(p) for p in value.split(os.pathsep) if p):
            continue
        env[key] = value
    env["HOME"] = str(home)
    return env


def export(brd: Path, out_dir: Path, allegro: Path, home: Path = HOME, *,
           quiet: bool = False) -> list[Path]:
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
                               errors="replace", env=allegro_env(home))
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


def record(allegro: Path, home: Path) -> int:
    if GOLDEN.exists():
        shutil.rmtree(GOLDEN)
    failed = []
    for brd in boards():
        if not export(brd, GOLDEN / brd.stem, allegro, home):
            failed.append(brd.name)
    n = len(list(GOLDEN.glob("*/*.json")))
    print(f"\nrecorded {n} intermediate(s) from {len(boards())} board(s) into {GOLDEN}")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


def check(allegro: Path, keep: Path | None, home: Path) -> int:
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
            export(brd, out, allegro, home)
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
    ap.add_argument("--home", default=None,
                    help="HOME for Allegro (default build/allegro-home; never the user's)")
    args = ap.parse_args(argv)
    allegro = find_allegro(args.allegro)
    home = allegro_home(args.home)
    print(f"allegro: {allegro}  HOME={home}")
    if args.record:
        return record(allegro, home)
    if args.check:
        return check(allegro, Path(args.keep) if args.keep else None, home)
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
        if not export(brd, Path(args.out) / brd.stem, allegro, home):
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
