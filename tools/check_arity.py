# Paths are derived from this file's own location, so the suite runs from
# wherever the repository is checked out. Anything a test writes goes to
# build/test-output/, which is gitignored.
import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parent.parent
_OUT = _ROOT / "build" / "test-output"
_OUT.mkdir(parents=True, exist_ok=True)
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

"""Fourth mechanical check on the SKILL sources: call arity.

The class of defect it catches already occurred once in this project
(makeSlot called makeCircle(x y d) when makeCircle takes 2 args). Nothing
else checks it: SKILL resolves calls at run time, so a wrong-arity call
loads fine and fails only when that line executes.

Handles @optional / @key / @rest in the definition; reports a call whose
positional count falls outside [required, maximum].
"""
import re, sys
from pathlib import Path

from skill_lex import clean  # noqa: E402,F401 - the shared lexer (round 80, G2)

FILES = [str(_ROOT / "makeVariant3dIntermediates.il"),
         str(_ROOT / "simple3d.il"),
         # the exporter's nine parts (round 76, D6)
         *sorted(str(q) for q in (_ROOT / "skill").glob("s3d_*.il"))]

# Each probe is loaded on its own in a live Allegro session, so each is checked
# against its own definitions only.
PROBES = sorted(str(p) for p in (_ROOT / "tools" / "probes").glob("*.il"))
# Standalone .il helpers directly under tools/ are loaded by hand in a live
# Allegro session too, so they get the same treatment as the probes.
PROBES += sorted(str(p) for p in (_ROOT / "tools").glob("*.il"))


def split_top_level(s):
    """Split an argument blob on top-level whitespace, respecting nesting."""
    args, depth, cur = [], 0, []
    for ch in s:
        if ch in "([":
            depth += 1; cur.append(ch)
        elif ch in ")]":
            depth -= 1; cur.append(ch)
        elif ch.isspace() and depth == 0:
            if cur: args.append("".join(cur)); cur = []
        else:
            cur.append(ch)
    if cur: args.append("".join(cur))
    return _join_infix(args)


# SKILL uses infix arithmetic inside argument lists: `headList( parts n - 1 )`
# is TWO arguments, not four. A lone operator token binds its neighbours.
_INFIX = {"-", "+", "*", "/", "<", ">", "<=", ">=", "==", "!=", "&&", "||"}


def _join_infix(args):
    out = []
    i = 0
    while i < len(args):
        if args[i] in _INFIX and out and i + 1 < len(args):
            out[-1] = out[-1] + args[i] + args[i + 1]
            i += 2
        else:
            out.append(args[i])
            i += 1
    return out


def body_of(text, open_idx):
    """Text between the paren at open_idx and its match."""
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "(": depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:i], i
    return None, len(text)


def collect_defs(text):
    """name -> (required, maximum or None for unlimited)."""
    defs = {}
    for m in re.finditer(r"procedure\(\s*([A-Za-z_]\w*)\s*\(", text):
        name = m.group(1)
        arg_open = text.index("(", m.end() - 1)
        blob, _ = body_of(text, arg_open)
        if blob is None:
            continue
        toks = split_top_level(blob)
        required, optional, unlimited = 0, 0, False
        mode = "req"
        for t in toks:
            if t.startswith("@"):
                if t.startswith("@rest"): unlimited = True
                mode = "opt"
                continue
            if mode == "req": required += 1
            else: optional += 1
        defs[name] = (required, None if unlimited else required + optional)
    return defs


def collect_calls(text, names):
    """(name, argcount, line) for every call to a known procedure."""
    calls = []
    for m in re.finditer(r"(?<![\w>-])([A-Za-z_]\w*)\s*\(", text):
        name = m.group(1)
        if name not in names:
            continue
        # skip the definition itself
        prefix = text[max(0, m.start() - 12):m.start()]
        if prefix.rstrip().endswith("procedure("):
            continue
        open_idx = m.end() - 1
        blob, _ = body_of(text, open_idx)
        if blob is None:
            continue
        n = len(split_top_level(blob))
        line = text.count("\n", 0, m.start()) + 1
        calls.append((name, n, line))
    return calls


def main():
    texts = {f: clean(f) for f in FILES}
    defs = {}
    for t in texts.values():
        defs.update(collect_defs(t))

    print(f"{len(defs)} procedures defined across both files")
    bad = []
    for f, t in texts.items():
        for name, n, line in collect_calls(t, defs):
            lo, hi = defs[name]
            if n < lo or (hi is not None and n > hi):
                bad.append((Path(f).name, line, name, n, lo, hi))

    for f in PROBES:
        t = clean(f)
        own = collect_defs(t)
        for name, n, line in collect_calls(t, own):
            lo, hi = own[name]
            if n < lo or (hi is not None and n > hi):
                bad.append((Path(f).name, line, name, n, lo, hi))
    print(f"{len(PROBES)} probe(s) checked against their own definitions")

    if bad:
        print("\nARITY MISMATCHES:")
        for fn, line, name, n, lo, hi in bad:
            rng = f"{lo}" if hi == lo else f"{lo}..{hi if hi is not None else 'N'}"
            print(f"  {fn}:{line}  {name}( {n} args ) but defined to take {rng}")
    else:
        print("no arity mismatches")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
