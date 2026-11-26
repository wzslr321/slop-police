import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from slop_police.comments import Lines

HUNK_HEADER = re.compile(r"@@ -\d+(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@")


@dataclass(frozen=True)
class RightSide:
    """The lines a pull request's diff shows on its right side, hunk by hunk: added and context lines.

    GitHub takes an inline comment only on these lines, and a comment on several lines only inside one hunk.
    """

    hunks: Mapping[str, tuple[Lines, ...]]

    def shown_part(self, path: str, lines: Lines) -> Lines | None:
        """The part of `lines` in the first hunk they reach into, or None when no hunk shows any of them."""
        for hunk in self.hunks.get(path, ()):
            if part := lines.overlap(hunk):
                return part
        return None

    def touches(self, path: str, lines: Lines | None) -> bool:
        """Whether a hunk shows any of `lines`, or any line of the file when there are none."""
        if lines is None:
            return path in self.hunks
        return self.shown_part(path, lines) is not None


def right_side(diff: str) -> RightSide:
    """The right side of a unified diff from `git diff`, with `a/` and `b/` prefixes."""
    hunks: dict[str, list[Lines]] = {}
    path: str | None = None
    # Not `splitlines`, which also splits a line of code at a form feed.
    rows = iter(diff.split("\n"))
    for row in rows:
        if row.startswith("diff --git "):
            path = None
        elif row.startswith("+++ "):
            path = _new_path(row)
        elif header := HUNK_HEADER.match(row):
            shown = _hunk_right_lines(header, rows)
            if path is not None and shown is not None:
                hunks.setdefault(path, []).append(shown)
    return RightSide({path: tuple(shown) for path, shown in hunks.items()})


def _new_path(header: str) -> str | None:
    """None for a deleted file. Git ends a name that has a space with a tab."""
    name = header.removeprefix("+++ ").rstrip("\t")
    return None if name == "/dev/null" else name.removeprefix("b/")


def _hunk_right_lines(header: re.Match[str], rows: Iterator[str]) -> Lines | None:
    """Reads one hunk from `rows`. It counts the lines, because an added line can look like a file header.

    None for a hunk that only deletes.
    """
    old_left = int(header["old_count"] or 1)
    new_left = int(header["new_count"] or 1)
    first = int(header["new_start"])
    next_line = first
    while old_left > 0 or new_left > 0:
        marker = next(rows)[:1]
        if marker == "\\":
            continue
        if marker == "-":
            old_left -= 1
            continue
        next_line += 1
        new_left -= 1
        if marker != "+":
            old_left -= 1
    return Lines(first, next_line - 1) if next_line > first else None
