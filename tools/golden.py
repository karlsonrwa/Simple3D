"""A golden corpus for the refactoring: build the repository's own inputs,
record what came out, compare after every step.

    python tools/golden.py                build every case, write build/golden.json
    python tools/golden.py --check        build again and compare with build/golden.json
    python tools/golden.py --with-local   add the boards in failed/ and input/ (the
                                          user's own designs; the record stays in
                                          build/, which is gitignored, and so do they)
    python tools/golden.py --step-dir D   where component models are looked for
                                          (repeatable; default demo/step_files)

Recorded per case: volume through the iterative integrator, bounding box,
solid count, STEP entity count, how many components were placed and skipped,
and how many warnings the build logged. Compared: volume and box within 1e-6,
everything else exactly. Ground rule 3 of REFACTORING_PLANS.md: the C++
regression alone is a plain board with no zones, no bends and no legend, so it
cannot see most of what a move could break.

Each case is built in its own process. An OpenCASCADE boolean can take the
process down with an access violation (memory: occ-can-kill-the-process), and
that should cost one case, not the corpus. The measuring code is the suites'
own, imported from tests/_support.py, so the numbers here and the numbers in
the tests are the same numbers.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORD = ROOT / "build" / "golden.json"
WORK = ROOT / "build" / "golden"
MODES = ("solid", "layers", "inspect")
TOL = 1e-6


def corpus(with_local: bool) -> list[dict]:
    """(name, json, board_mode, fold) for every case, repository inputs first."""
    cases = []
    demo = ROOT / "demo" / "ap-214" / "demo.json"
    rigidflex = ROOT / "tests" / "fixtures" / "rigidflex.json"
    for mode in MODES:
        cases.append({"name": f"demo.{mode}", "json": str(demo), "mode": mode, "fold": True})
    for mode in MODES:
        cases.append({"name": f"rigidflex.{mode}", "json": str(rigidflex), "mode": mode, "fold": True})
    cases.append({"name": "rigidflex.solid.flat", "json": str(rigidflex), "mode": "solid", "fold": False})
    if with_local:
        sys.path.insert(0, str(ROOT))
        from stepbuilder.core import is_simple3d_json
        for folder in ("failed", "input"):
            for path in sorted((ROOT / folder).glob("*.json")):
                if not is_simple3d_json(path):
                    continue
                for mode in MODES:
                    cases.append({"name": f"{folder}.{path.stem}.{mode}", "json": str(path),
                                  "mode": mode, "fold": True})
    return cases


def build_one(case: dict, step_dirs: list[str]) -> dict:
    """Run in the child process: build the case and measure the file."""
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tests"))
    from _support import bbox, count_solids, entity_count, read_step, volume
    from stepbuilder import core

    out = WORK / case["name"]
    out.mkdir(parents=True, exist_ok=True)
    logs: list[str] = []
    try:
        res = core.generate(step_dir=step_dirs, json_file=case["json"], output_dir=out,
                            output_name=case["name"], minimize_size=False,
                            board_mode=case["mode"], fold_bends=case["fold"],
                            log=logs.append)
    except Exception as exc:  # noqa: BLE001 - recorded, not handled
        return {"error": f"{type(exc).__name__}: {exc}"}
    shape = read_step(res.output)
    return {
        "volume": round(volume(shape), 9),
        "bbox": [round(v, 9) for v in bbox(shape)],
        "solids": count_solids(shape),
        "entities": entity_count(res.output),
        "placed": res.components_placed,
        "skipped": len(res.components_skipped),
        "warnings": sum(1 for m in logs if m.lower().startswith("warning")),
    }


def build_all(cases: list[dict], step_dirs: list[str], timeout: float) -> dict:
    """Every case in its own process; a crash or a timeout is recorded as such."""
    results = {}
    for case in cases:
        t0 = time.time()
        cmd = [sys.executable, str(Path(__file__).resolve()), "--case", json.dumps(case)]
        for d in step_dirs:
            cmd += ["--step-dir", d]
        try:
            done = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT),
                                  timeout=timeout)
        except subprocess.TimeoutExpired:
            results[case["name"]] = {"timeout": timeout}
            print(f"  {case['name']:34} TIMEOUT after {timeout:.0f}s")
            continue
        line = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""
        if done.returncode != 0 or not line.startswith("{"):
            results[case["name"]] = {"crash": done.returncode,
                                     "tail": (done.stderr or done.stdout)[-400:]}
            print(f"  {case['name']:34} CRASH rc={done.returncode}")
            continue
        rec = json.loads(line)
        results[case["name"]] = rec
        what = (rec.get("error") or
                f"V={rec['volume']:.6f} solids={rec['solids']} ents={rec['entities']} "
                f"placed={rec['placed']} warn={rec['warnings']}")
        print(f"  {case['name']:34} {what}  ({time.time() - t0:.1f}s)")
    return results


def compare(old: dict, new: dict) -> list[str]:
    diffs = []
    for name, want in old.items():
        got = new.get(name)
        if got is None:
            diffs.append(f"{name}: no longer built")
            continue
        for key in sorted(set(want) | set(got)):
            a, b = want.get(key), got.get(key)
            if key == "tail":
                continue
            if key == "volume" and a is not None and b is not None:
                if abs(a - b) > TOL:
                    diffs.append(f"{name}: volume {a:.9f} -> {b:.9f} ({b - a:+.3e})")
            elif key == "bbox" and a is not None and b is not None:
                if any(abs(x - y) > TOL for x, y in zip(a, b)):
                    diffs.append(f"{name}: bbox {a} -> {b}")
            elif a != b:
                diffs.append(f"{name}: {key} {a!r} -> {b!r}")
    for name in new:
        if name not in old:
            diffs.append(f"{name}: new case, not in the record")
    return diffs


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="compare with build/golden.json")
    ap.add_argument("--with-local", action="store_true", help="also failed/ and input/")
    ap.add_argument("--step-dir", action="append", default=[], help="model folder (repeatable)")
    ap.add_argument("--timeout", type=float, default=900.0, help="seconds per case")
    ap.add_argument("--case", help=argparse.SUPPRESS)   # internal: one case, JSON on stdout
    args = ap.parse_args(argv)
    step_dirs = args.step_dir or [str(ROOT / "demo" / "step_files")]

    if args.case:
        print(json.dumps(build_one(json.loads(args.case), step_dirs)))
        return 0

    cases = corpus(args.with_local)
    print(f"golden corpus: {len(cases)} cases, models from {', '.join(step_dirs)}")
    started = time.time()
    results = build_all(cases, step_dirs, args.timeout)
    print(f"built in {time.time() - started:.0f}s")

    if args.check:
        if not RECORD.exists():
            print(f"no record at {RECORD}; run without --check first")
            return 2
        old = json.loads(RECORD.read_text(encoding="utf-8"))
        diffs = compare(old, results)
        if diffs:
            print(f"\n{len(diffs)} difference(s) against {RECORD}:")
            for d in diffs:
                print("  " + d)
            return 1
        print(f"\nno difference against {RECORD} ({len(old)} cases)")
        return 0

    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps(results, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"recorded {len(results)} cases in {RECORD}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
