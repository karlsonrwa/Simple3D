"""What the SKILL checkers do to a file before they look at it - once.

`skill_checks.py` (five mechanical checks) and `check_arity.py` (call arity)
each carried a copy of the comment stripper and the string blanker, and the
first had the balanced-group walk as well; a fix to one was a fix to be
copied. Round 80, plan G2: the copy is here, imported by both. Nothing here
knows what a check is - it only makes the text safe to scan.

The rules, which every check leans on:
  - a `;` starts a comment unless it sits inside a string literal;
  - a string literal is blanked to "" so the parens and names inside it do
    not count, keeping the line structure;
  - a group is balanced by counting parens on text that has had both done.
"""

import re
from pathlib import Path


def strip_line_comment(line):
    """Remove a ; comment, respecting string literals on that line."""
    out, in_str, esc = [], False, False
    for ch in line:
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == ";":
                break
            if ch == '"':
                in_str = True
            out.append(ch)
    return "".join(out)


def strip_comments(text):
    """Every line with its ; comment removed."""
    return "\n".join(strip_line_comment(l) for l in text.splitlines())


def strip_strings(code):
    """Replace "..." literals with "", so nothing inside one counts."""
    return re.sub(r'"(\\.|[^"\\])*"', '""', code)


def clean(path):
    """A file as code only: comments off, strings blanked."""
    return strip_strings(strip_comments(Path(path).read_text(encoding="utf-8", errors="replace")))


def balanced_end(src, i):
    """Index just past the group that opens at src[i] == '('."""
    depth = 0
    while i < len(src):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(src)
