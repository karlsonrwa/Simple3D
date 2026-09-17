"""The mutation table is still aimed at the code: every pattern in
tests/mutations.json matches its file exactly once, at HEAD, today.

`tools/mutate.py tests/mutations.json` is the expensive job: it breaks the
code the way each entry says, runs the suites the entry names, and reports
which mutations were caught. It is not in run_all (it takes the better part
of an hour). What IS cheap is asking whether that job is still asking its
questions at all - and it stops asking one the moment the file it targets is
refactored and the `old` text is gone. The harness then prints REFUSED and
moves on, and the rule that mutation stood for has had no evidence since
the refactor. A refusal is not a pass.

So this suite applies nothing and runs no mutant. Per entry it checks what
the harness would check before applying it: the file exists, `old` occurs
exactly once, `new` differs and does not contain `old` (an early `return`
shadowing the line leaves the original in place - a killed run then leaves
a mutation nothing can see), the suites it names exist, and the id is
unique. It fails in the same round as the refactor that broke the pattern.

Rounds 88 and 89 (2026-09-15 and -17); the reasoning is in
docs/test-audit.md.
"""
from __future__ import annotations

import json
import sys

from _support import ROOT, check, fails

TABLE = ROOT / "tests" / "mutations.json"
MIN_ENTRIES = 20        # the table was 29 + 15 when written; an emptied file is not "all matched"


def read_source(path) -> str:
    """Bytes, decoded - the harness reads bytes too, so CRLF is seen the same
    way here (and translated in the pattern the same way)."""
    return path.read_bytes().decode("utf-8")


def for_file(pattern: str, text: str) -> str:
    return pattern.replace("\n", "\r\n") if "\r\n" in text else pattern


def suite_path(name: str):
    for folder in ("tests", "tools"):
        p = ROOT / folder / name
        if p.exists():
            return p
    p = ROOT / name
    return p if p.exists() else None


def main() -> int:
    print("[1] the table itself")
    check("tests/mutations.json exists", TABLE.exists())
    if not TABLE.exists():
        return 1
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    check("it is a list", isinstance(table, list))
    check(f"it holds at least {MIN_ENTRIES} entries (has {len(table)})", len(table) >= MIN_ENTRIES)
    ids = [m.get("id") for m in table]
    check("every id is unique", len(ids) == len(set(ids)),
          sorted({i for i in ids if ids.count(i) > 1}))
    for m in table:
        missing = [k for k in ("id", "file", "old", "new", "suites", "why") if k not in m]
        check(f"{m.get('id', '?')}: has every field", not missing, missing)

    print("[2] every pattern still matches exactly once, and would apply")
    sources: dict = {}
    for m in table:
        mid = m.get("id", "?")
        path = ROOT / m.get("file", "")
        if not check(f"{mid}: {m.get('file')} exists", path.is_file()):
            continue
        if path not in sources:
            sources[path] = read_source(path)
        text = sources[path]
        old = for_file(m["old"], text)
        new = for_file(m["new"], text)
        n = text.count(old)
        check(f"{mid}: old occurs exactly once in {m['file']}", n == 1, f"{n} times")
        check(f"{mid}: new differs from old", new != old)
        check(f"{mid}: new does not contain old (the original is removed)", old not in new)
        check(f"{mid}: new is not already in the file (a leftover from a killed run)",
              not (new in text and old not in text))

    print("[3] every suite an entry names exists")
    named = sorted({s for m in table for s in m.get("suites", [])})
    check("at least one suite is named", bool(named))
    for s in named:
        check(f"suite {s} exists under tests/ or tools/", suite_path(s) is not None)

    print("[4] the harness the table is written for is in the tree")
    check("tools/mutate.py exists", (ROOT / "tools" / "mutate.py").is_file())

    return 0 if not fails else 1


if __name__ == "__main__":
    code = main()
    print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAIL'}")
    sys.exit(code)
