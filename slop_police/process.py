import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from slop_police.change import Change, changed_files, changed_lines
from slop_police.comments import COMMENTS_SCHEMA, Comment, Dropped, Lines, comments_from
from slop_police.config import Config
from slop_police.github.diff import RightSide
from slop_police.harness import Harness, HarnessFailed, Usage
from slop_police.harnesses import harness_for

PROMPTS = Path(__file__).resolve().parent / "prompts"

CANDIDATES_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": ["string", "null"]},
                    "line": {"type": ["integer", "null"]},
                    "end_line": {"type": ["integer", "null"]},
                    "symbol": {"type": ["string", "null"]},
                    "problem": {"type": "string"},
                    "evidence": {"type": "string"},
                    "fix": {"type": "string"},
                },
                "required": ["path", "line", "end_line", "symbol", "problem", "evidence", "fix"],
            },
        }
    },
    "required": ["candidates"],
}

VERDICTS_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate": {"type": "integer"},
                    "keep": {"type": "boolean"},
                    "reason": {"type": "string"},
                    "comment": {"type": "string"},
                },
                "required": ["candidate", "keep", "reason", "comment"],
            },
        }
    },
    "required": ["verdicts"],
}


class VerdictsDoNotMatch(HarnessFailed):
    """The check of a lens did not give each of its candidates exactly one verdict."""


@dataclass(frozen=True)
class CodeCandidate:
    path: str
    line: int
    end_line: int
    symbol: str
    problem: str
    evidence: str
    fix: str
    # Off the lines the change adds or rewrites, only a change that leaves this code wrong makes it a finding.
    on_changed_lines: bool

    def comment(self, body: str) -> Comment:
        return Comment(self.path, self.line, body, self.end_line)


@dataclass(frozen=True)
class DescriptionCandidate:
    """About the sentence of the pull request's description that `evidence` quotes."""

    problem: str
    evidence: str
    fix: str

    def comment(self, body: str) -> Comment:
        """The sentence stands in for a place in the code."""
        return Comment(None, None, f"> {self.evidence}\n\n{body}")


Candidate = CodeCandidate | DescriptionCandidate


@dataclass(frozen=True)
class Checked:
    comments: list[Comment]
    dropped: list[Dropped]
    usage: Usage


@dataclass(frozen=True)
class Review:
    comments: list[Comment]
    dropped: list[Dropped]
    usage: Usage
    seconds: float


def review(change: Change, config: Config, parallel: int = 1, harness: Harness | None = None) -> Review:
    """Each lens finds candidates, a second session per lens checks them against the code, an editor merges and orders."""
    started = time.monotonic()
    harness = harness or _ready_harness(config)
    context = _context(change, config)
    changed = changed_lines(change)
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        per_lens = list(pool.map(lambda lens: _through_lens(harness, change, config, context, changed, lens), config.lenses))
    checked = _combined(per_lens)
    edited = _edited(harness, change, config, checked, changed)
    return Review(
        comments=edited.comments[: config.max_comments],
        dropped=edited.dropped,
        usage=edited.usage,
        seconds=time.monotonic() - started,
    )


def _ready_harness(config: Config) -> Harness:
    harness = harness_for(config.harness, config.read_also)
    problem = harness.login_problem()
    if problem:
        raise HarnessFailed(problem)
    return harness


def _through_lens(harness: Harness, change: Change, config: Config, context: str, changed: RightSide, lens: str) -> Checked:
    lens_text = config.lens(lens)
    found = harness.ask(f"{context}\n{lens_text}", CANDIDATES_SCHEMA, change.checkout, read_code=True)
    candidates = [_candidate(item, changed) for item in found.output["candidates"]]
    if not candidates:
        return Checked([], [], found.usage)
    verify_prompt = _verify_prompt(change, config, lens_text, candidates)
    verified = harness.ask(verify_prompt, VERDICTS_SCHEMA, change.checkout, read_code=True)
    verdicts = verified.output["verdicts"]
    _check_one_verdict_each(lens, candidates, verdicts)
    comments, dropped = _sort_verdicts(candidates, verdicts)
    return Checked(comments, dropped, found.usage + verified.usage)


def _candidate(item: dict, changed: RightSide) -> Candidate:
    if item["path"] is None:
        return DescriptionCandidate(item["problem"], item["evidence"], item["fix"])
    line = item["line"]
    lines = None if line is None else Lines(line, max(line, item["end_line"] or line))
    return CodeCandidate(**item, on_changed_lines=changed.touches(item["path"], lines))


def _check_one_verdict_each(lens: str, candidates: list[Candidate], verdicts: list[dict]) -> None:
    """Without this, a skipped candidate would pass as no finding, and a repeated one would become two comments."""
    counted = Counter(verdict["candidate"] for verdict in verdicts)
    numbers = range(len(candidates))
    problems = []
    if missing := [number for number in numbers if counted[number] == 0]:
        problems.append(f"no verdict for {_listed(missing)}")
    if repeated := [number for number in numbers if counted[number] > 1]:
        problems.append(f"more than one verdict for {_listed(repeated)}")
    if unknown := sorted(number for number in counted if number not in numbers):
        problems.append(f"verdicts for candidates that do not exist: {_listed(unknown)}")
    if problems:
        raise VerdictsDoNotMatch(f"The check of lens `{lens}` gave {'; '.join(problems)}.")


def _listed(numbers: list[int]) -> str:
    return ", ".join(f"#{number}" for number in numbers)


def _sort_verdicts(candidates: list[Candidate], verdicts: list[dict]) -> tuple[list[Comment], list[Dropped]]:
    comments: list[Comment] = []
    dropped: list[Dropped] = []
    for verdict in verdicts:
        candidate = candidates[verdict["candidate"]]
        if verdict["keep"]:
            comments.append(candidate.comment(verdict["comment"]))
        else:
            dropped.append(Dropped(candidate.comment(candidate.problem), verdict["reason"]))
    return comments, dropped


def _combined(per_lens: list[Checked]) -> Checked:
    return Checked(
        comments=[comment for checked in per_lens for comment in checked.comments],
        dropped=[dropped for checked in per_lens for dropped in checked.dropped],
        usage=sum((checked.usage for checked in per_lens), Usage()),
    )


def _edited(harness: Harness, change: Change, config: Config, checked: Checked, changed: RightSide) -> Checked:
    """The editor rewrites what it gets, so the comments on the description pass it by with their quote as it is.

    A merged comment is about code outside the change when the place the editor gives it is.
    """
    on_code = [comment for comment in checked.comments if comment.path is not None]
    if not on_code:
        return checked
    on_description = [comment for comment in checked.comments if comment.path is None]
    answer = harness.ask(_editor_prompt(change, config, on_code), COMMENTS_SCHEMA, change.checkout, read_code=False)
    edited = _with_ranges(comments_from(answer.output), on_code)
    marked = [replace(comment, elsewhere=not changed.touches(comment.path, comment.lines)) for comment in edited]
    return Checked([*marked, *on_description], checked.dropped, checked.usage + answer.usage)


def _with_ranges(edited: list[Comment], before: list[Comment]) -> list[Comment]:
    """The editor sees no code, so it gives one line, and the range comes from the comment it was given at that line.

    When two lenses found the same line, the merged comment gets the wider range. With no match it keeps one line.
    A comment about a whole file has no range to give.
    """
    last_lines: dict[tuple[str | None, int | None], int] = {}
    for comment in before:
        lines = comment.lines
        if lines is None:
            continue
        place = (comment.path, comment.line)
        last_lines[place] = max(lines.last, last_lines.get(place, lines.last))
    return [replace(comment, end_line=last_lines.get((comment.path, comment.line), comment.line)) for comment in edited]


def _context(change: Change, config: Config) -> str:
    files = changed_files(change, config.ignore)
    context = (PROMPTS / "context.md").read_text().format(
        label=change.label,
        name=config.name,
        about=config.about,
        base=change.base,
        title=change.title,
        description=change.description,
        files="\n".join(f"- {file.path} (+{file.added} -{file.deleted})" for file in files),
        rules=_named(config.rules),
        checkout_note=change.checkout_note,
    )
    return f"{context}\n{change.hints}" if change.hints else context


def _verify_prompt(change: Change, config: Config, lens_text: str, candidates: list[Candidate]) -> str:
    numbered = "\n\n".join(f"#{index} {json.dumps(asdict(candidate))}" for index, candidate in enumerate(candidates))
    return (PROMPTS / "verify.md").read_text().format(
        label=change.label,
        name=config.name,
        base=change.base,
        rules=_named(config.rules),
        checkout_note=change.checkout_note,
        title=change.title,
        description=change.description,
        lens=lens_text,
        candidates=numbered,
    )


def _editor_prompt(change: Change, config: Config, comments: list[Comment]) -> str:
    numbered = "\n\n".join(
        f"#{index} {comment.path}:{comment.line}\n{comment.body}" for index, comment in enumerate(comments)
    )
    return (PROMPTS / "editor.md").read_text().format(
        label=change.label,
        name=config.name,
        priority=config.priority,
        comments=numbered,
    )


def _named(files: tuple[str, ...]) -> str:
    quoted = [f"`{file}`" for file in files]
    if len(quoted) < 2:
        return "".join(quoted)
    return f"{', '.join(quoted[:-1])} and {quoted[-1]}"
