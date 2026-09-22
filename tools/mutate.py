"""Mutation audit: break the code a test claims to protect, run the test, see.

    python tools/mutate.py                       # every row of tests/mutations.json
    python tools/mutate.py --changed             # only what the uncommitted changes touch
    python tools/mutate.py --changed HEAD~3      # ...since some other revision
    python tools/mutate.py pads- skill-          # rows whose id contains a piece
    python tools/mutate.py --list --changed      # show the selection, run nothing
    python tools/mutate.py --spec build/rows.json # a table kept somewhere else
    python -u tools/mutate.py > build/run.log    # -u, or the log arrives at the end

Each mutation is {id, file, old, new, suites, why}: `file` and every suite are
paths from the repository root (`tests/test_pads.py`, `tools/skill_checks.py`).
`old` must occur exactly once in the file, or the mutation is refused (an
unasserted replacement proves nothing).  A suite is CAUGHT when its exit code
is non-zero with the mutation in place; a mutation is caught when any of its
suites catches it.  An `id` on the command line selects every row whose id
contains it.

Nothing here ever writes into the working tree.  Every worker owns a private
COPY of it under build/mutants/run-<time>-<pid>/w<i>/ and breaks that; the
copies run in parallel; the mutated file is restored from the bytes read before
the write and the restore is proved by SHA-256.  A killed run leaves a folder
under build/ and nothing else.

WHAT A COPY IS.  The tree minus IGNORE and --exclude, plus DATA: the files the
suites read from outside version control, named one by one.  A copy has only
what is under version control plus what you deliberately give it - that is
the point: a check that passes only thanks to something the developer's tree
happens to hold (a settings file, a stale extract) fails on the copy, where it
should.  Here DATA is empty: every fixture the suites read is tracked, and
the boards under input/ and failed/ are read by no suite.

Why copies (2026-09-21, BaroSim, 212 mutations): the in-place design this
file had until round 90 needed a lock file, a leftover check, a bytecode purge
and a rule that nobody edits while it runs, and still cost four accidents in
one week - two hours of edits silently reverted by a background run, an `if
False:` left behind by a killed run, an hour lost to a stale .pyc of the same
length, a mutated line that failed five tests.  On copies the full table went
from 26.6 min in place to 6.5-6.8 min on 4-8 copies, and two mutations that
had counted as "caught" turned out to survive: one lived in a branch dead
behind a flag, one was caught only by the developer's gitignored settings
file.

This file is the shared harness of the test-audit skill
(~/.claude/skills/test-audit/mutate.py, as of 2026-09-22) with a few lines of
its own: the default table is tests/mutations.json, the default root is this
repository, the copies live under build/ (this repository's one scratch
folder), neither input/ and failed/ nor the window's own settings file travels
into a copy, and a suite already red on the clean copy makes the rows naming
it UNPROVEN rather than silently "survived" (trap 8).  The cheap sentinel that
proves this job is still asking its questions is tests/test_mutations.py.

----------------------------------------------------------------------------
Traps this harness handles, each of which has cost a real run:

1. CRLF.  Read and write BYTES; translate the pattern to the file's own ending.
   In text mode every multi-line pattern matches zero times and the run
   reports "refused" instead of an answer.
2. STALE BYTECODE.  Python validates a .pyc from the source's (mtime, size), so
   a same-length replacement written in the same second is invisible to it -
   or the mutated bytecode outlives the restore.  A copy is made without any
   __pycache__ and the children run with -B, so there is nothing to go stale.
3. A REPLACEMENT THAT DOES NOT REMOVE THE ORIGINAL (an early `return` shadowing
   the line).  Still refused: `old` staying in the file makes the check of the
   restore meaningless and the mutation ambiguous.
4. A MUTATION LEFT IN THE WORKING TREE by some other tool or a hand edit: the
   copies would inherit it and the baseline would go red for a reason that is
   not the suite's.  Checked once at start - the replacement present AND the
   original absent; the replacement alone is usually a substring of the
   healthy line.
5. CONSOLE ENCODING.  PYTHONUTF8=1 and PYTHONIOENCODING=utf-8 for the child, or
   one non-ASCII FAIL line kills it on a cp1251 console.
6. A REFUSED MUTATION IS NOT A PASS: the pattern stopped matching because the
   file was refactored, and the rule has had no proof since.  Counted as
   unproven and named at the end.
7. A SUITE THAT NEVER FINISHES.  A mutation can turn a decoder into an endless
   loop, or - here, round 90 - make the window reach a modal message box,
   which sat for 31 minutes at 2 % CPU with the whole run's output buffered
   behind it.  Each suite gets three times its baseline plus two minutes (or
   --timeout); past that its whole process tree is killed and the row is
   HUNG: not a verdict, listed with the unproven, so the row is given a suite
   that fails cleanly instead.
8. A SUITE ALREADY RED ON THE CLEAN COPY.  The baseline is run so that a red
   suite is not asked - it could not answer.  But a row whose every suite is
   red, or whose green suites stay green while a red one is skipped, has NOT
   survived: it is unproven, and it says so (round 90: a launch deadline of
   8 s went red on a loaded machine and two rows read "survived" for a reason
   that had nothing to do with the tests).
----------------------------------------------------------------------------
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "tests" / "mutations.json"
PY = sys.executable
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1",
           PYTHONIOENCODING="utf-8")
# What never travels into a copy.  Add a project's heavy inputs with --exclude.
# The window's own settings file stays out too: a copy has only what is
# under version control, so a check that passes only thanks to what the
# developer's window remembered fails here, where it should.  input/ and
# failed/ are the user's boards (gitignored, 180 MB); .claude/ is the
# session's permission file; *.jrl, *.rpt and signoise.run are what a
# headless Allegro leaves beside demo.brd.
IGNORE = ("__pycache__", "*.pyc", ".git", "work", "build", "dist",
          ".pytest_cache", "node_modules", ".venv", "venv",
          "input", "failed", ".claude", "*.egg-info",
          "simple3d_config.local.json", "*.jrl", "*.rpt", "signoise.run")
# What the suites read outside version control, given to every copy by name
# (paths relative to the root).  Nothing here: every fixture is tracked.
DATA: tuple = ()
HUNG = None                      # the exit code of a suite that never finished


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_source(path: Path) -> tuple:
    """The file as text with newlines normalised, and whether it had CRLF."""
    data = path.read_bytes()
    return data.decode("utf-8").replace("\r\n", "\n"), b"\r\n" in data, data


def copy_tree(root: Path, dst: Path, exclude: tuple = (), data: tuple = ()) -> int:
    """Copy `root` into `dst` minus IGNORE and `exclude`, plus DATA and `data`;
    the number of files.

    copytree copies with copy2, so mtimes survive: anything a suite builds
    afterwards (a DLL, a cache) is newer than every source.
    """
    ignore = shutil.ignore_patterns(*IGNORE, *exclude)
    shutil.copytree(root, dst, ignore=ignore, symlinks=True)
    for rel in (*DATA, *data):
        src = root / rel
        if src.is_file():
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst / rel)
    return sum(1 for p in dst.rglob("*") if p.is_file())


def missing_data(root: Path, data: tuple = ()) -> list:
    return [rel for rel in (*DATA, *data) if not (root / rel).is_file()]


def kill_tree(proc: subprocess.Popen) -> None:
    """The child and everything it started."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True)
    else:
        proc.kill()


def run_suite(copy: Path, suite: str, limit: float = 1200.0) -> tuple:
    """(exit code, seconds, output) of one suite run inside `copy`; the exit
    code is HUNG when the suite did not finish within `limit` seconds."""
    script = copy / suite
    if not script.exists():
        return 2, 0.0, f"no such suite: {suite}"
    started = time.monotonic()
    proc = subprocess.Popen([PY, "-B", str(script)], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, cwd=str(copy), env=ENV,
                            encoding="utf-8", errors="replace")
    try:
        out, _ = proc.communicate(timeout=limit)
    except subprocess.TimeoutExpired:
        kill_tree(proc)
        out, _ = proc.communicate()
        return HUNG, time.monotonic() - started, out or ""
    return proc.returncode, time.monotonic() - started, out or ""


def left_behind(root: Path, spec: list) -> list:
    """Mutations that look applied in the WORKING tree (trap 4)."""
    dirty = []
    for m in spec:
        path = root / m["file"]
        if not path.exists():
            continue
        text, _crlf, _data = read_source(path)
        if m["new"] in text and m["old"] not in text:
            dirty.append(f"{m['file']}: {m['id']} looks applied")
    return dirty


def mutate_once(copy: Path, m: dict, base: dict, limits: dict) -> tuple:
    """Apply `m` in `copy`, run its suites there, put the file back.

    Returns (verdict, id, seconds, detail); verdict is "caught", "SURVIVED",
    "REFUSED", "HUNG" or "UNPROVEN".  Raises RuntimeError if the restore did
    not reproduce the original bytes - the copy is then unfit for further jobs.
    """
    path = copy / m["file"]
    if not path.exists():
        return "REFUSED", m["id"], 0.0, f"no such file: {m['file']}"
    text, crlf, original = read_source(path)
    digest = sha(original)
    hits = text.count(m["old"])
    if hits != 1:
        return "REFUSED", m["id"], 0.0, f"`old` occurs {hits} times in {m['file']}"
    mutated = text.replace(m["old"], m["new"])
    if crlf:
        mutated = mutated.replace("\n", "\r\n")
    spent, caught, hung, unasked, fails = 0.0, [], [], [], ""
    try:
        path.write_bytes(mutated.encode("utf-8"))
        for suite in m["suites"]:
            if base.get(suite):
                unasked.append(suite)            # already red on the clean tree (trap 8)
                continue
            code, seconds, out = run_suite(copy, suite, limits.get(suite, 1200.0))
            spent += seconds
            if code is HUNG:
                hung.append(suite)
                continue
            if code:
                caught.append(suite)
                # The first FAIL line names the assertion that bit; a suite
                # that died on a SystemExit has no FAIL line and its reason
                # is the last thing it printed - show that, not "exit 1".
                lines = [l.strip() for l in out.splitlines() if "FAIL" in l]
                last = [l.strip() for l in out.splitlines() if l.strip()]
                fails = (lines[0] if lines else
                         f"exit {code}: {last[-1]}" if last else f"exit {code}")[:110]
                break                            # one suite is enough
    finally:
        path.write_bytes(original)
        # A file compiled into something the suites load (a C source into a
        # host DLL) may have been built from the mutant: drop what the copy
        # built under work/ so the next job rebuilds it.
        if path.suffix in (".c", ".h", ".cpp", ".ld"):
            shutil.rmtree(copy / "work", ignore_errors=True)
    if sha(path.read_bytes()) != digest:
        raise RuntimeError(f"{m['file']} was not restored in {copy}")
    if caught:
        return "caught", m["id"], spent, f"{caught[0]}: {fails}"
    if hung:
        return "HUNG", m["id"], spent, f"{hung[0]} never finished - not a verdict"
    if unasked:
        return "UNPROVEN", m["id"], spent, (
            f"{', '.join(unasked)} already red on the clean copy, not asked - not a verdict"
            + (f"; green in {', '.join(s for s in m['suites'] if s not in unasked)}"
               if len(unasked) < len(m["suites"]) else ""))
    return "SURVIVED", m["id"], spent, "green in " + ", ".join(m["suites"])


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{done.stderr.strip()}")
    return done.stdout


def changed_paths(root: Path, rev: str) -> set:
    edited = git(root, "diff", "--name-only", rev).splitlines()
    untracked = git(root, "ls-files", "--others", "--exclude-standard").splitlines()
    return {p.strip() for p in edited + untracked if p.strip()}


def spec_at(root: Path, spec_path: Path, rev: str) -> list:
    """The spec as committed at `rev`, or [] when it is not in the repository."""
    try:
        rel = spec_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return []
    done = subprocess.run(["git", "-C", str(root), "show", f"{rev}:{rel}"],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    if done.returncode != 0:
        return []
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError:
        return []


def select_changed(spec: list, changed: set, previous: list) -> list:
    """Rows whose file or any suite changed, or which are new/edited since REV."""
    before = {json.dumps(m, sort_keys=True) for m in previous}
    return [m for m in spec
            if m["file"] in changed or any(s in changed for s in m["suites"])
            or json.dumps(m, sort_keys=True) not in before]


def select(spec: list, pieces: list) -> list:
    """Rows whose id contains any of `pieces`; every row when there are none."""
    return [m for m in spec if not pieces or any(p in m["id"] for p in pieces)]


def parse(argv: list) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("ids", nargs="*", help="only rows whose id contains one of these (default: all)")
    p.add_argument("--spec", default=str(SPEC),
                   help="JSON list of {id, file, old, new, suites, why} (default %(default)s)")
    p.add_argument("--root", default=str(ROOT), help="the project (default: this repository)")
    p.add_argument("--workers", type=int, default=max(2, (os.cpu_count() or 2) // 2),
                   help="copies running at once (default %(default)s: half the logical "
                        "cores; on 4 physical cores 8 copies were 5%% faster than 4 and "
                        "left the machine unusable)")
    p.add_argument("--exclude", action="append", default=[], metavar="PAT",
                   help="glob of names never copied (repeatable), e.g. research or *.pdf")
    p.add_argument("--data", action="append", default=[], metavar="REL",
                   help="a file outside version control the suites read, copied into "
                        "every copy (repeatable; relative to the root)")
    p.add_argument("--changed", nargs="?", const="HEAD", metavar="REV",
                   help="only rows whose file, suite or spec entry differ from REV "
                        "(default HEAD)")
    p.add_argument("--timeout", type=float, default=None, metavar="S",
                   help="seconds a suite may take before it is HUNG "
                        "(default: 3 x its baseline + 120, or 1200 without one)")
    p.add_argument("--list", action="store_true", help="print the selection, run nothing")
    p.add_argument("--keep", action="store_true", help="leave the copies behind")
    p.add_argument("--no-baseline", action="store_true")
    return p.parse_args(argv)


def main(argv: list) -> int:
    args = parse(argv)
    root = Path(args.root).resolve()
    spec_path = Path(args.spec)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    data = tuple(args.data)
    muts = select(spec, args.ids)
    if args.changed is not None:
        changed = changed_paths(root, args.changed)
        muts = select_changed(muts, changed, spec_at(root, spec_path, args.changed))
        print(f"{len(changed)} paths differ from {args.changed}; {len(muts)} of "
              f"{len(spec)} mutations touch them or are new")
    if not muts:
        print("no mutation matches")
        return 0 if args.changed is not None else 2
    if args.list:
        for m in muts:
            print(f"  {m['id']:<44} {m['file']:<36} {', '.join(m['suites'])}")
        return 0

    invisible = [m["id"] for m in muts if m["old"] in m["new"]]
    if invisible:
        print("REFUSED - the replacement keeps the original text (trap 3):", *invisible)
        return 2
    dirty = left_behind(root, spec)
    if dirty:
        print("the working tree carries a mutation, and every copy would inherit it:")
        for line in dirty:
            print("   ", line)
        return 3
    absent = missing_data(root, data)
    if absent:
        print("not here, so the suites that read them will skip (a skip proves nothing):")
        for rel in absent:
            print("   ", rel)

    workers = max(1, min(args.workers, len(muts)))
    run_dir = (root / "build" / "mutants"
               / f"run-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}")
    copies = [run_dir / f"w{i}" for i in range(workers)]
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as copier:
        files = sum(copier.map(
            lambda c: copy_tree(root, c, tuple(args.exclude), data), copies))
    print(f"root: {root}\n{workers} copies under {run_dir}, {files} files, "
          f"{time.monotonic() - started:.1f} s; the working tree is not touched",
          flush=True)

    free: queue.Queue = queue.Queue()
    for c in copies:
        free.put(c)

    def with_copy(job, *rest):
        copy = free.get()
        try:
            return job(copy, *rest)
        except RuntimeError:
            shutil.rmtree(copy, ignore_errors=True)   # unfit: a fresh copy instead
            copy_tree(root, copy, tuple(args.exclude), data)
            raise
        finally:
            free.put(copy)

    suites = sorted({s for m in muts for s in m["suites"]})
    base = {s: 0 for s in suites}
    times = {s: 0.0 for s in suites}
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        if args.no_baseline:
            print("=== baseline skipped by request ===", flush=True)
        else:
            print("=== baseline (clean copies) ===", flush=True)
            for suite, (code, seconds, _out) in zip(suites, pool.map(
                    lambda s: with_copy(run_suite, s, args.timeout or 1200.0), suites)):
                base[suite], times[suite] = (1 if code is HUNG else code), seconds
                print(f"  {suite:<40} exit={'HUNG' if code is HUNG else code}  "
                      f"{seconds:6.1f}s" + ("   <-- ALREADY RED" if code else ""),
                      flush=True)
        limits = {s: (args.timeout if args.timeout else
                      max(300.0, 3 * times[s] + 120.0) if times[s] else 1200.0)
                  for s in suites}
        # Longest suites first, so the tail is not one slow suite started last.
        jobs = sorted(muts, key=lambda m: -max(times.get(s, 0.0) for s in m["suites"]))
        futures = [pool.submit(with_copy, mutate_once, m, base, limits) for m in jobs]
        try:
            for future in concurrent.futures.as_completed(futures):
                verdict, mid, spent, detail = future.result()
                results.append((verdict, mid, spent, detail))
                print(f"  {verdict:<8} {mid:<44} {spent:6.1f}s  {detail}", flush=True)
        except RuntimeError as exc:
            print(f"ERROR {exc}")
            return 3

    if not args.keep:
        shutil.rmtree(run_dir, ignore_errors=True)
    wall = time.monotonic() - started
    work = sum(r[2] for r in results) + sum(times.values())
    caught = [r for r in results if r[0] == "caught"]
    print(f"\ncaught {len(caught)} of {len(results)}; {wall:.0f} s of wall for "
          f"{work:.0f} s of suite runs on {workers} copies")
    unproven = [r for r in results if r[0] != "caught"]
    if unproven:
        print("not proved (a REFUSED, HUNG or UNPROVEN mutation is a rule with no "
              "evidence, not a pass):")
        for verdict, mid, _spent, detail in unproven:
            print(f"  {verdict:<8} {mid}: {detail}")
    return 1 if unproven else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
