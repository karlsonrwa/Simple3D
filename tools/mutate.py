"""Mutation audit: break the code a test claims to protect, run the test, see.

    python tools/mutate.py tests/mutations.json [--root DIR] [--no-baseline] [id ...]

The table tests/mutations.json is the permanent record of what the suite has
been shown to catch (rounds 88-89); tests/test_mutations.py checks, in a
fraction of a second, that every pattern in it still matches its file exactly
once - a refactor that breaks a pattern is a finding in the same round, not at
the end of the next full pass. This file is the shared harness of the
`test-audit` skill, copied here so the repository is self-contained; the lock
file lives under build/ (gitignored), everything else is as shared.

RUN IT ON A COPY of the tree, never on a working tree with edits in flight: it
restores a byte snapshot after every mutation, so any edit made meanwhile is
silently reverted, and a killed run leaves the mutation applied. Make the copy
with robocopy from PowerShell (Git Bash rewrites `/E` into a path):

    robocopy <repo> D:\...\copy /E /XD .git build input failed __pycache__ /XF *.pyc

and not under a folder called `build`, `work` or `dist`: purge_bytecode skips
those names, so a copy there would keep its stale bytecode (trap 2 below).

Each mutation is {id, file, old, new, suites, why}. `old` must occur exactly
once in the file, or the mutation is refused (an unasserted replacement proves
nothing). The file is restored from the original bytes in a finally block and
its SHA-256 is compared afterwards; the run stops if a restore ever fails.

A suite is CAUGHT when its exit code is non-zero with the mutation in place.
Every suite is run once on the clean tree first (baseline) - a suite that is
already red cannot answer anything.

----------------------------------------------------------------------------
Four traps this harness handles, each of which has cost a real run.  They are
here rather than in a note because a note does not stop the next one.

1. CRLF.  Read and write BYTES, and translate the pattern to the file's own
   ending.  In text mode every multi-line pattern matches zero times and the
   run reports "refused" instead of an answer.

2. STALE BYTECODE.  Python validates a .pyc from the source's (mtime, size).
   A replacement of the same LENGTH written within the same second changes
   neither - and several mutations are same-length on purpose, because the
   comment gets padded to keep the alignment.  Then either the mutation never
   takes effect (the suite runs healthy bytecode and the run says SURVIVED for
   code that was never broken), or the MUTATED bytecode outlives the restore
   and answers for the source in every later run.  Both were reproduced on
   2026-09-16; the second cost an hour, because inspect.getsource() reads the
   .py and showed correct code while dis.dis() showed the mutation.
   The fix: purge every __pycache__ before the baseline, and run children with
   -B and PYTHONDONTWRITEBYTECODE so nothing is cached during the run at all.

3. A REPLACEMENT THAT DOES NOT REMOVE THE ORIGINAL.  Shadowing a line with an
   early `return` above it leaves the original in place, so a killed run leaves
   a mutation that no leftover-check can see.  Refused here.

4. A KILLED RUN.  It never reaches the finally, so the mutation stays applied.
   A lock file makes a second run refuse to start, and every run checks first
   for a mutation left behind by a previous one.  The test that works is
   "the replacement is present AND the original is absent": a replacement is
   usually a SUBSTRING of the healthy line, so looking only for the replacement
   gives false positives.
----------------------------------------------------------------------------
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Defaults to wherever you run it from, so the file needs no editing per
# project; pass --root DIR to override.
ROOT = Path.cwd()
PY = sys.executable
LOCK_NAME = "mutate.lock"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_source(path: Path) -> tuple[str, bool]:
    """The file as text, and whether it uses CRLF.  Always via bytes."""
    text = path.read_bytes().decode("utf-8")
    return text, "\r\n" in text


def for_file(pattern: str, crlf: bool) -> str:
    return pattern.replace("\n", "\r\n") if crlf else pattern


def purge_bytecode(root: Path) -> int:
    """Delete every __pycache__ under root.  See trap 2 in the module docstring."""
    gone = 0
    for cache in root.rglob("__pycache__"):
        if any(part in ("work", ".git", "build", "dist") for part in cache.parts):
            continue
        shutil.rmtree(cache, ignore_errors=True)
        gone += 1
    return gone


def child_env() -> dict:
    """No bytecode written, and UTF-8 out, so one Cyrillic FAIL line cannot
    kill a child on a cp1251 console."""
    return dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")


def run_suite(name: str) -> tuple[int, str]:
    script = ROOT / "tests" / name if name.startswith("test_") else ROOT / "tools" / name
    if not script.exists():                     # a path given relative to ROOT
        script = ROOT / name
    done = subprocess.run([PY, "-B", str(script)], capture_output=True, text=True,
                          cwd=str(ROOT), env=child_env(),
                          encoding="utf-8", errors="replace")
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def refuse_invisible(muts: list) -> list:
    """Mutations whose replacement keeps the original text.  See trap 3."""
    bad = []
    for m in muts:
        if m["old"] in m["new"]:
            bad.append(m["id"])
    return bad


def left_behind(muts: list) -> list:
    """Mutations that look like they are still applied in the tree.  Trap 4."""
    dirty = []
    for m in muts:
        path = ROOT / m["file"]
        if not path.exists():
            continue
        text, crlf = read_source(path)
        old, new = for_file(m["old"], crlf), for_file(m["new"], crlf)
        if new in text and old not in text:
            dirty.append(f"{m['file']}: {m['id']} looks applied")
    return dirty


def main(argv: list[str]) -> int:
    global ROOT
    if "--root" in argv:
        at = argv.index("--root")
        ROOT = Path(argv[at + 1]).resolve()
        del argv[at:at + 2]

    spec = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    skip = "--no-baseline" in argv
    wanted = {a for a in argv[1:] if not a.startswith("--")}
    muts = [m for m in spec if not wanted or m["id"] in wanted]
    if not muts:
        print("no mutation matches")
        return 2
    print(f"root: {ROOT}")

    invisible = refuse_invisible(muts)
    if invisible:
        print("REFUSED - the replacement does not remove the original, so a\n"
              "killed run would leave it in the tree unnoticed (trap 3):")
        for mid in invisible:
            print("   ", mid)
        return 2

    dirty = left_behind(spec)
    if dirty:
        print("a previous run seems to have left a mutation applied:")
        for line in dirty:
            print("   ", line)
        print("Restore those lines before running again.")
        return 3

    lock = ROOT / "build" / LOCK_NAME
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists():
        print(f"{lock} exists: a run is already in flight. It restores every\n"
              "file it touches, so nothing in the tree may be edited until it\n"
              "finishes. If no run is actually going, delete the file.")
        return 3
    lock.write_text(f"pid {os.getpid()}\n", encoding="utf-8")
    print("!! the tree is being rewritten and restored: do not edit it "
          "until this finishes")
    try:
        return _run(muts, skip)
    finally:
        lock.unlink(missing_ok=True)


def _run(muts: list, skip: bool) -> int:
    purged = purge_bytecode(ROOT)
    if purged:
        print(f"cleared {purged} __pycache__ directories so no stale bytecode "
              "can answer for the source")

    suites = sorted({s for m in muts for s in m["suites"]})
    base = {}
    if skip:
        print("=== baseline skipped by request ===")
        base = {s: 0 for s in suites}
    else:
        print("=== baseline (clean tree) ===")
        for s in suites:
            t0 = time.time()
            code, _ = run_suite(s)
            base[s] = code
            print(f"  {s:34} exit={code}  {time.time() - t0:5.1f}s"
                  + ("   <-- ALREADY RED" if code else ""))

    results = []
    for m in muts:
        path = ROOT / m["file"]
        original = path.read_bytes()
        before = hashlib.sha256(original).hexdigest()
        text, crlf = read_source(path)
        old, new = for_file(m["old"], crlf), for_file(m["new"], crlf)
        n = text.count(old)
        if n != 1:
            print(f"\n[{m['id']}] REFUSED: `old` occurs {n} times in {m['file']}")
            # Not a pass.  A pattern that stopped matching - usually because the
            # file was refactored - means the rule it stood for has had no proof
            # since that refactor.
            results.append((m["id"], "REFUSED", "pattern no longer matches"))
            continue
        print(f"\n[{m['id']}] {m['file']}: {m['why']}")
        caught, detail = [], []
        try:
            path.write_bytes(text.replace(old, new).encode("utf-8"))
            assert sha(path) != before, "the write changed nothing"
            for s in m["suites"]:
                if base[s]:
                    print(f"  {s:34} skipped (already red)")
                    continue
                t0 = time.time()
                code, out = run_suite(s)
                bit = "CAUGHT" if code else "survived"
                if code:
                    caught.append(s)
                else:
                    detail.append(s)
                fails = [l.strip().encode("ascii", "replace").decode("ascii")
                         for l in out.splitlines()
                         if l.strip().startswith("FAIL") or "  FAIL" in l]
                print(f"  {s:34} exit={code} {bit}  {time.time() - t0:5.1f}s"
                      + (f"   {fails[0][:70]}" if fails else ""))
        finally:
            path.write_bytes(original)
            assert sha(path) == before, f"RESTORE FAILED for {path}"
        results.append((m["id"], "caught" if caught else "SURVIVED",
                        ",".join(caught) or "none of " + ",".join(m["suites"])))

    print("\n=== summary ===")
    for mid, verdict, where in results:
        print(f"  {mid:28} {verdict:9} {where}")
    unproven = [r[0] for r in results if r[1] != "caught"]
    if unproven:
        print(f"\n{len(unproven)} of {len(results)} unproven: "
              + ", ".join(unproven))
        print("A REFUSED mutation is not a pass - it is a rule with no evidence.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
