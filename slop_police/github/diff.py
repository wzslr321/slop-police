import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

HUNK_HEADER = re.compile(r"@@ -\d+(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@")


@dataclass(frozen=True)
class RightSide:
    """The lines a pull request's diff shows on its right side, where GitHub takes an inline comment: added and context lines."""

    lines: Mapping[str, frozenset[int]]

    def shows(self, path: str, line: int) -> bool:
        return line in self.lines.get(path, frozenset())


def right_side(diff: str) -> RightSide:
    """The right side of a unified diff from `git diff`, with `a/` and `b/` prefixes."""
    lines: dict[str, set[int]] = {}
    path: str | None = None
    # Not `splitlines`, which also splits a line of code at a form feed.
    rows = iter(diff.split("\n"))
    for row in rows:
        if row.startswith("diff --git "):
            path = None
        elif row.startswith("+++ "):
            path = _new_path(row)
        elif hunk := HUNK_HEADER.match(row):
            shown = _hunk_right_lines(hunk, rows)
            if path is not None:
                lines.setdefault(path, set()).update(shown)
    return RightSide({path: frozenset(numbers) for path, numbers in lines.items()})


def _new_path(header: str) -> str | None:
    """None for a deleted file. Git ends a name that has a space with a tab."""
    name = header.removeprefix("+++ ").rstrip("\t")
    return None if name == "/dev/null" else name.removeprefix("b/")


def _hunk_right_lines(header: re.Match[str], rows: Iterator[str]) -> set[int]:
    """Reads one hunk from `rows`. It counts the lines, because an added line can look like a file header."""
    old_left = int(header["old_count"] or 1)
    new_left = int(header["new_count"] or 1)
    line = int(header["new_start"])
    shown: set[int] = set()
    while old_left > 0 or new_left > 0:
        marker = next(rows)[:1]
        if marker == "\\":
            continue
        if marker == "-":
            old_left -= 1
            continue
        shown.add(line)
        line += 1
        new_left -= 1
        if marker != "+":
            old_left -= 1
    return shown
