import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

from slop_police.github.diff import RightSide, right_side


@dataclass(frozen=True)
class Change:
    """The commits between `base` and the head commit of `checkout`."""

    checkout: Path
    base: str
    label: str
    title: str
    description: str
    # What the reviewer must know about this checkout, such as a rule file to read elsewhere.
    checkout_note: str = ""
    # Where to read first, from a tool outside the reviewer.
    hints: str = ""


class UncommittedChanges(Exception):
    """Tracked files differ from the head commit, so the code the reviewer reads is not the change under review."""


@dataclass(frozen=True)
class ChangedFile:
    path: str
    added: int
    deleted: int


def changed_files(change: Change, ignore: tuple[str, ...]) -> list[ChangedFile]:
    numstat = _git(change.checkout, "diff", "--numstat", "-z", change.base, "HEAD")
    files = _numstat_files(numstat)
    return [file for file in files if not any(fnmatchcase(file.path, pattern) for pattern in ignore)]


def changed_lines(change: Change) -> RightSide:
    """The lines of the head commit that the change adds or rewrites: the right side of its diff without context."""
    options = ["--unified=0", "--no-color", "--no-ext-diff", "--src-prefix=a/", "--dst-prefix=b/"]
    return right_side(_git(change.checkout, "-c", "core.quotepath=false", "diff", *options, change.base, "HEAD"))


def _numstat_files(numstat: str) -> Iterator[ChangedFile]:
    """Reads `git diff --numstat -z`: every field ends with a NUL, and a rename gives an empty path, then its old and new path."""
    fields = iter(numstat.split("\0")[:-1])
    for counts in fields:
        added, deleted, path = counts.split("\t", 2)
        if not path:
            _old_path, path = next(fields), next(fields)
        yield _changed_file(added, deleted, path)


def _changed_file(added: str, deleted: str, path: str) -> ChangedFile:
    binary = added == "-"
    return ChangedFile(
        path=path,
        added=0 if binary else int(added),
        deleted=0 if binary else int(deleted),
    )


def branch_change(checkout: Path, base_ref: str, title: str | None, description: str | None) -> Change:
    """The current branch of `checkout` against where it left `base_ref`, for a change that has no pull request yet."""
    if _git(checkout, "status", "--porcelain", "--untracked-files=no"):
        raise UncommittedChanges(
            f"Tracked files in {checkout} differ from HEAD. Commit or stash them first: "
            "the reviewer reads the files as they are, and the change it reviews ends at HEAD."
        )
    base = _git(checkout, "merge-base", base_ref, "HEAD").strip()
    branch = _git(checkout, "rev-parse", "--abbrev-ref", "HEAD").strip()
    return Change(
        checkout=checkout,
        base=base,
        label=f"a change on branch `{branch}` (no pull request yet)",
        title=title or branch,
        description=description or _git(checkout, "log", "--reverse", "--format=%s%n%n%b", f"{base}..HEAD").strip(),
    )


def _git(checkout: Path, *arguments: str) -> str:
    """Git prints a file name as its bytes, which need not be UTF-8: such a name reaches the prompts with � in it."""
    return subprocess.run(["git", *arguments], cwd=checkout, check=True, capture_output=True, text=True, errors="replace").stdout
