"""The mutation table is still aimed at the code: every pattern in
tests/mutations.json matches its file exactly once, at HEAD, today.

`python tools/mutate.py` is the expensive job: it breaks the code the way
each row says, in a private copy of the tree, runs the suites the row names
and reports which mutations were caught. It is not in run_all - it costs
minutes, not seconds. What IS cheap is asking whether that job is still
asking its questions at all, and it stops asking one the moment the file it
targets is refactored and the `old` text is gone: the harness prints REFUSED
and moves on, and the rule that row stood for has had no evidence since the
refactor. A refusal is not a pass.

So this suite applies none of the table's rows and runs none of its mutants.
Per row it checks what the harness would check before applying it - the file
exists, `old` occurs exactly once, `new` differs and does not contain `old`
(an early `return` shadowing the line leaves the original in place), the
suites it names exist, the id is unique, no path leaves the tree - and then
the harness itself: that a copy made the way a worker makes one carries every
file a row names, byte for byte, and no bytecode, and none of what must stay
out; that `--changed` picks rows by the file, the suite, the row and the files
every suite shares, and asks git only in a tree of its own; and, since round
132, the harness's rules run on sandboxes of their own ([6]: a path out of the
tree refused, no baseline no verdict, a grandchild holding the output, the
previous job's output gone). It fails in the same round as the refactor that
broke the pattern.

Rounds 88 and 89 (2026-09-15 and -17) for the table, round 90 (2026-09-21)
for the copies; the reasoning is in docs/test-audit.md.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from _support import ROOT, check, fails

sys.path.insert(0, str(ROOT / "tools"))
import mutate                                          # noqa: E402

TABLE = ROOT / "tests" / "mutations.json"
# Just under the table's size when this was last raised: half the rows could
# not vanish and still pass. The number only ever grows.
MIN_ENTRIES = 200
FIELDS = ("id", "file", "old", "new", "suites", "why")


def _remove(path: Path) -> None:
    """rmtree, the read-only files git writes under .git/objects included."""
    for p in path.rglob("*") if path.exists() else ():
        try:
            if p.is_file():
                p.chmod(0o666)
        except OSError:
            pass
    shutil.rmtree(path, ignore_errors=True)


def main() -> int:
    print("[1] the table itself")
    check("tests/mutations.json exists", TABLE.is_file())
    if not TABLE.is_file():
        return 1
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    check("it is a list of rows", isinstance(table, list) and all(isinstance(m, dict) for m in table))
    check(f"it holds at least {MIN_ENTRIES} entries (has {len(table)})", len(table) >= MIN_ENTRIES)
    ids = [m.get("id") for m in table]
    check("every id is unique", len(ids) == len(set(ids)),
          sorted({i for i in ids if ids.count(i) > 1}))
    short = [m.get("id", "?") for m in table
             if any(k not in m for k in FIELDS) or not str(m.get("why", "")).strip()]
    check("every row has every field, and says why", not short, ", ".join(short))

    print("[2] every pattern still matches exactly once, and would apply")
    # In a copy tools/mutate.py has broken, the row it applied is there by
    # design: its pattern is gone and it looks left behind, and so may a row
    # beside it on the same file. mutate.py names the row (MUTATING), and the
    # patterns on its file are not counted here - or every row aimed at the
    # harness reads caught by these lines, as all eight did on 02.11.2026
    # (round 132; AllegroBaseStructure's lesson of 29.09.2026).
    applied = os.environ.get("MUTATING", "")
    skipped = next((m.get("file") for m in table if m.get("id") == applied), None)
    if skipped:
        print(f"  note: {applied} is applied in this copy - the patterns on {skipped} are not counted")
    counted = [m for m in table if m.get("file") != skipped]
    sources: dict = {}
    for m in counted:
        mid = m.get("id", "?")
        path = ROOT / m.get("file", "")
        if not check(f"{mid}: {m.get('file')} exists", path.is_file()):
            continue
        if path not in sources:
            # Normalised the way the harness reads it, so a CRLF file and an
            # LF pattern count the same here as there.
            sources[path] = mutate.read_source(path)[0]
        text = sources[path]
        old, new = m["old"], m["new"]
        n = text.count(old)
        check(f"{mid}: old occurs exactly once in {m['file']}", n == 1, f"{n} times")
        check(f"{mid}: new differs from old and removes it", new != old and old not in new)
        check(f"{mid}: new is not already in the file (a leftover of a killed run)",
              not (new in text and old not in text))
    check("and the harness's own leftover check agrees the tree is clean",
          not mutate.left_behind(ROOT, counted))
    check("no row's file or suite leaves the tree - absolute, or through '..' (R7-10)",
          not mutate.outside(ROOT, table), mutate.outside(ROOT, table)[:5])

    print("[3] every suite a row names exists, as a path from the root")
    named = sorted({s for m in table for s in m.get("suites", [])})
    check("at least one suite is named", bool(named))
    for s in named:
        check(f"suite {s} exists", (ROOT / s).is_file() and s.startswith(("tests/", "tools/")))
    covered = sorted({m["file"].split("/")[0] for m in table if "file" in m})
    check("the table reaches the Python half, the SKILL half and the launcher",
          {"stepbuilder", "skill", "simple3d.il"} <= set(covered), ", ".join(covered))

    print("[4] the copy a worker mutates is the tree, minus what can go stale")
    copy = ROOT / "build" / "sentinel-copy"
    shutil.rmtree(copy, ignore_errors=True)
    copied = mutate.copy_tree(ROOT, copy)
    check("the copy has files at all", copied > 50, str(copied))
    wanted = sorted({m["file"] for m in table} | set(named))
    missing = [rel for rel in wanted if not (copy / rel).is_file()]
    check("every file and every suite a row names is in the copy", not missing,
          ", ".join(missing[:5]))
    differ = [rel for rel in sorted({m["file"] for m in table})
              if (copy / rel).is_file()
              and (copy / rel).read_bytes() != (ROOT / rel).read_bytes()]
    check("and each file a row breaks is byte for byte the tree's", not differ,
          ", ".join(differ[:5]))
    stale = [str(p.relative_to(copy)) for p in copy.rglob("*")
             if p.name == "__pycache__" or p.suffix == ".pyc"]
    check("no bytecode travels with it", not stale, ", ".join(stale[:5]))
    heavy = [name for name in (".git", "build", "input", "failed", ".claude",
                               "simple3d_config.local.json")
             if (copy / name).exists()]
    check("neither .git, build/, input/, failed/, .claude/ nor the window's "
          "settings file does", not heavy, ", ".join(heavy))
    for rel in ("tests/_support.py", "tests/skill_transliterations.py",
                "tests/fixtures/rigidflex.json", "tests/fixtures/pads_demo.json",
                "tests/fixtures/silk_demo.json", "tests/fixtures/skill_answers.json",
                "demo/ap-214/demo.json", "demo/step_files/cap_D8x10mm.stp",
                "simple3d_config.json", "makeVariant3dIntermediates.il",
                "README.md", "QUICKSTART.md", "ARCHITECTURE.md", "tools/skill_lex.py"):
        check(f"what the suites read is there: {rel}", (copy / rel).is_file())
    shutil.rmtree(copy, ignore_errors=True)

    print("[5] --changed picks what a change can have left unproved, nothing else")
    rows = [{"id": "a-rule", "file": "stepbuilder/a.py", "old": "x = 1", "new": "x = 2",
             "suites": ["tests/test_a.py"], "why": "a"},
            {"id": "b-rule", "file": "stepbuilder/b.py", "old": "y = 1", "new": "y = 2",
             "suites": ["tests/test_b.py"], "why": "b"},
            {"id": "c-rule", "file": "skill/c.il", "old": "z = 1", "new": "z = 2",
             "suites": ["tools/skill_checks.py"], "why": "c"}]

    def picked(changed, previous):
        return [m["id"] for m in mutate.select_changed(rows, changed, previous)]

    check("nothing changed, nothing selected", picked(set(), rows) == [])
    check("the file a row breaks changed: it runs",
          picked({"stepbuilder/a.py"}, rows) == ["a-rule"])
    check("the suite that must catch it changed: the claim moved, so it runs too",
          picked({"tests/test_b.py"}, rows) == ["b-rule"])
    check("an unrelated file changed: nothing runs",
          picked({"README.md", "stepbuilder/gui.py"}, rows) == [])
    edited = [rows[0], dict(rows[1], new="y = 3")]
    check("a row that is new or edited since the revision runs",
          picked(set(), edited) == ["b-rule", "c-rule"])
    check("with no previous table at all, everything runs",
          len(mutate.select_changed(rows, set(), [])) == 3)
    check("ids select by substring, any piece, and none means all",
          [m["id"] for m in mutate.select(rows, ["b-", "c-"])] == ["b-rule", "c-rule"]
          and len(mutate.select(rows, [])) == 3)
    # A shared file - what every suite runs through, or the harness - can
    # disarm any check: until round 132 an edit of check() selected nothing
    # (review 23.10.2026, R7-14).
    check("a file every suite runs through changed: every row runs",
          picked({"tests/_support.py"}, rows) == ["a-rule", "b-rule", "c-rule"]
          and picked({"tools/mutate.py"}, rows) == ["a-rule", "b-rule", "c-rule"])
    # git must answer for the tree it is asked about: a copy under build/ has
    # no .git, and git answered for the checkout around it (R7-17). The
    # questions go to a repository made here, so that they are asked in a
    # copy of the tree too, where rows are judged: a check that needs this
    # tree's own .git is skipped in every copy and holds no row.
    scratch = ROOT / "build" / "sentinel-git"
    _remove(scratch)
    (scratch / "sub").mkdir(parents=True)
    (scratch / "sub" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (scratch / "table.json").write_text('[{"id": "r"}]\n', encoding="utf-8")
    made = [subprocess.run(["git", "-C", str(scratch), *argv], capture_output=True, text=True)
            for argv in (["init", "-q"], ["add", "-A"],
                         ["-c", "user.name=sentinel", "-c", "user.email=sentinel@example.invalid",
                          "commit", "-q", "-m", "sentinel"])]
    if check("a scratch repository to ask git in", all(m.returncode == 0 for m in made),
             [m.stderr.strip() for m in made if m.returncode]):
        (scratch / "sub" / "a.py").write_text("x = 2\n", encoding="utf-8")
        check("a tree that is a git repository of its own is answered for",
              mutate.own_repository(scratch) == "", mutate.own_repository(scratch))
        changed = mutate.changed_paths(scratch, "HEAD")
        check("git answers with repository paths, forward slashes", changed == {"sub/a.py"},
              sorted(changed))
        check("and the table as committed reads back as a list",
              mutate.spec_at(scratch, scratch / "table.json", "HEAD") == [{"id": "r"}])
        said = mutate.own_repository(scratch / "sub")
        check("a folder inside it with no .git of its own is told so, not answered for",
              "no .git of its own" in said, said)
    _remove(scratch)

    harness_rules()
    return 0 if not fails else 1


def harness_rules() -> None:
    """[6] The harness's own rules, each on a sandbox of its own (round 132,
    review 23.10.2026 R7-10, R7-11, R7-12, R7-13)."""
    import contextlib
    import io
    import time

    print("[6] the harness's own rules")
    here = ROOT / "build" / "sentinel-harness"
    shutil.rmtree(here, ignore_errors=True)
    copy = here / "copy"
    (copy / "tests").mkdir(parents=True)
    victim = here / "work" / "victim.py"            # stands for the working tree
    victim.parent.mkdir(parents=True)
    victim.write_text("x = 1\n", encoding="utf-8")
    seen = here / "seen.txt"
    (copy / "tests" / "reads_victim.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        f"Path({str(seen)!r}).write_text(Path({str(victim)!r}).read_text())\nsys.exit(1)\n",
        encoding="utf-8")

    for rel in (str(victim), "../work/victim.py", "stepbuilder/../../work/victim.py"):
        check(f"a path that leaves the tree is told so: {rel}", mutate.escapes(copy, rel))
    check("and one inside it is not", not mutate.escapes(copy, "tests/reads_victim.py"))
    row = {"id": "leaves", "file": str(victim), "old": "x = 1", "new": "x = 2",
           "suites": ["tests/reads_victim.py"], "why": "R7-10"}
    verdict = mutate.mutate_once(copy, row, {"tests/reads_victim.py": 0}, {})
    check("a row whose file is absolute is refused, and the working tree's file is never written "
          "(until round 132 the suite read 'x = 2' there)",
          verdict[0] == "REFUSED" and victim.read_text(encoding="utf-8") == "x = 1\n"
          and not seen.exists(), (verdict, seen.read_text() if seen.exists() else None))

    (copy / "pkg.py").write_text("FLAG = 1\n", encoding="utf-8")
    (copy / "tests" / "always_red.py").write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
    row = {"id": "no-base", "file": "pkg.py", "old": "FLAG = 1", "new": "FLAG = 2",
           "suites": ["tests/always_red.py"], "why": "R7-11"}
    verdict = mutate.mutate_once(copy, row, {"tests/always_red.py": None}, {})
    check("with no baseline a red suite proves nothing: UNPROVEN, not caught",
          verdict[0] == "UNPROVEN", verdict)
    # What caught a row is the FAIL line that bit, not a passing check whose
    # name holds the word: test_harness's do (round 132).
    (copy / "tests" / "named_fail.py").write_text(
        "import sys\nprint('  PASS  a check whose name says FAIL')\n"
        "print('  FAIL  the check that bit  <- 1')\nsys.exit(1)\n", encoding="utf-8")
    row = {"id": "named", "file": "pkg.py", "old": "FLAG = 1", "new": "FLAG = 3",
           "suites": ["tests/named_fail.py"], "why": "what caught it"}
    verdict = mutate.mutate_once(copy, row, {"tests/named_fail.py": 0}, {})
    check("a catch names the FAIL line that bit, not a PASS line whose name holds the word",
          verdict[0] == "caught" and "the check that bit" in verdict[3], verdict)
    # And the suite is told which row is applied in its copy, so this
    # sentinel can leave that row's file uncounted (trap 15).
    (copy / "tests" / "says_mutating.py").write_text(
        "import os, sys\nprint('  FAIL  applied: ' + os.environ.get('MUTATING', '(nothing)'))\n"
        "sys.exit(1)\n", encoding="utf-8")
    row = {"id": "told", "file": "pkg.py", "old": "FLAG = 1", "new": "FLAG = 4",
           "suites": ["tests/says_mutating.py"], "why": "MUTATING"}
    verdict = mutate.mutate_once(copy, row, {"tests/says_mutating.py": 0}, {})
    check("a suite is told the id of the row applied in its copy (MUTATING)",
          verdict[0] == "caught" and "applied: told" in verdict[3], verdict)

    # A grandchild handed the suite's output, its parent gone at once: the
    # pipe stayed open while it lived and the read after a kill waited for it.
    grandchild = ("import subprocess, sys\nsubprocess.Popen([sys.executable, '-c', "
                  "'import time; time.sleep(15)'], stdout=sys.stdout, stderr=sys.stderr)\n")
    (copy / "tests" / "leaver.py").write_text(grandchild + "print('done', flush=True)\n", encoding="utf-8")
    (copy / "tests" / "mediator.py").write_text(grandchild, encoding="utf-8")
    (copy / "tests" / "hanger.py").write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, 'tests/mediator.py'], stdout=sys.stdout, stderr=sys.stderr)\n"
        "time.sleep(60)\n", encoding="utf-8")
    started = time.monotonic()
    code, _, out = mutate.run_suite(copy, "tests/leaver.py", 60.0)
    check("a suite that ends, leaving a child that holds its output, is read when it ends",
          code == 0 and "done" in out and time.monotonic() - started < 10,
          (code, round(time.monotonic() - started, 1)))
    started = time.monotonic()
    code, _, _ = mutate.run_suite(copy, "tests/hanger.py", 2.0)
    check("and one that hangs is HUNG within its limit, whatever its grandchild holds",
          code is mutate.HUNG and time.monotonic() - started < 12, round(time.monotonic() - started, 1))

    # A suite that reads what it should just have written read the last job's
    # file in a copy that had served one: the mutant survived there and was
    # caught in a fresh copy (R7-12). The whole run, one copy, so the
    # baseline and the mutant share it.
    tree = here / "tree"
    (tree / "tests").mkdir(parents=True)
    (tree / "flag.py").write_text("WRITE = True\n", encoding="utf-8")
    (tree / "tests" / "suite.py").write_text(
        "import sys\nfrom pathlib import Path\nhere = Path(__file__).resolve().parent.parent\n"
        "sys.path.insert(0, str(here))\nimport flag\n"
        "out = here / 'build' / 'test-output' / 'out.txt'\nout.parent.mkdir(parents=True, exist_ok=True)\n"
        "if flag.WRITE:\n    out.write_text('fresh')\n"
        "sys.exit(0 if out.exists() and out.read_text() == 'fresh' else 1)\n", encoding="utf-8")
    spec = here / "spec.json"
    spec.write_text(json.dumps([{"id": "skips-the-write", "file": "flag.py", "old": "WRITE = True",
                                 "new": "WRITE = False", "suites": ["tests/suite.py"], "why": "R7-12"}]),
                    encoding="utf-8")
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = mutate.main(["--root", str(tree), "--spec", str(spec), "--workers", "1"])
    check("a mutant that skips writing its output is caught in a copy the baseline has just used",
          code == 0 and "caught" in said.getvalue(), said.getvalue().strip().splitlines()[-3:])
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = mutate.main(["--root", str(tree), "--spec", str(spec), "--workers", "1", "--no-baseline"])
    check("and with --no-baseline the same red suite is no verdict: the run says UNPROVEN and fails",
          code == 1 and "UNPROVEN" in said.getvalue() and "caught 0 of 1" in said.getvalue(),
          said.getvalue().strip().splitlines()[-3:])
    shutil.rmtree(here, ignore_errors=True)


if __name__ == "__main__":
    code = main()
    print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAIL'}")
    sys.exit(code)
