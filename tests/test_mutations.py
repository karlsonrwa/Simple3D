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

So this suite applies nothing and runs no mutant. Per row it checks what the
harness would check before applying it - the file exists, `old` occurs
exactly once, `new` differs and does not contain `old` (an early `return`
shadowing the line leaves the original in place), the suites it names exist,
the id is unique - and then two things about the harness itself: that a copy
made the way a worker makes one carries every file a row names, byte for
byte, and no bytecode, and none of what must stay out; and that `--changed`
picks rows by the file, the suite and the row, nothing else. It fails in the
same round as the refactor that broke the pattern.

Rounds 88 and 89 (2026-09-15 and -17) for the table, round 90 (2026-09-21)
for the copies; the reasoning is in docs/test-audit.md.
"""
from __future__ import annotations

import json
import shutil
import sys

from _support import ROOT, check, fails

sys.path.insert(0, str(ROOT / "tools"))
import mutate                                          # noqa: E402

TABLE = ROOT / "tests" / "mutations.json"
# Just under the table's size when this was last raised: half the rows could
# not vanish and still pass. The number only ever grows.
MIN_ENTRIES = 200
FIELDS = ("id", "file", "old", "new", "suites", "why")


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
    sources: dict = {}
    for m in table:
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
          not mutate.left_behind(ROOT, table))

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
    changed = mutate.changed_paths(ROOT, "HEAD")
    check("git answers with repository paths, forward slashes",
          all("\\" not in p for p in changed), ", ".join(sorted(changed)[:3]))
    check("and the table as committed reads back as a list",
          isinstance(mutate.spec_at(ROOT, TABLE, "HEAD"), list))

    return 0 if not fails else 1


if __name__ == "__main__":
    code = main()
    print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAIL'}")
    sys.exit(code)
