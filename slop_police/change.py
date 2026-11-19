import subprocess
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path


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
    numstat = _git(change.checkout, "diff", "--numstat", change.base, "HEAD")
    files = [_changed_file(line) for line in numstat.splitlines()]
    return [file for file in files if not any(fnmatchcase(file.path, pattern) for pattern in ignore)]


def _changed_file(numstat_line: str) -> ChangedFile:
    added, deleted, path = numstat_line.split("\t")
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
    return subprocess.run(["git", *arguments], cwd=checkout, check=True, capture_output=True, text=True).stdout
