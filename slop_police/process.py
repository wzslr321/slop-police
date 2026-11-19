import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from slop_police.change import Change, changed_files
from slop_police.comments import COMMENTS_SCHEMA, Comment, Dropped, comments_from
from slop_police.config import Config
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
                    "path": {"type": "string"},
                    "line": {"type": "integer"},
                    "symbol": {"type": "string"},
                    "problem": {"type": "string"},
                    "evidence": {"type": "string"},
                    "fix": {"type": "string"},
                },
                "required": ["path", "line", "symbol", "problem", "evidence", "fix"],
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


@dataclass(frozen=True)
class Candidate:
    path: str
    line: int
    symbol: str
    problem: str
    evidence: str
    fix: str


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
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        per_lens = list(pool.map(lambda lens: _through_lens(harness, change, config, context, lens), config.lenses))
    checked = _combined(per_lens)
    edited = _edited(harness, change, config, checked) if checked.comments else checked
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


def _through_lens(harness: Harness, change: Change, config: Config, context: str, lens: str) -> Checked:
    lens_text = config.lens(lens)
    found = harness.ask(f"{context}\n{lens_text}", CANDIDATES_SCHEMA, change.checkout, read_code=True)
    candidates = [Candidate(**item) for item in found.output["candidates"]]
    if not candidates:
        return Checked([], [], found.usage)
    verify_prompt = _verify_prompt(change, config, lens_text, candidates)
    verified = harness.ask(verify_prompt, VERDICTS_SCHEMA, change.checkout, read_code=True)
    comments, dropped = _sort_verdicts(candidates, verified.output["verdicts"])
    return Checked(comments, dropped, found.usage + verified.usage)


def _sort_verdicts(candidates: list[Candidate], verdicts: list[dict]) -> tuple[list[Comment], list[Dropped]]:
    comments: list[Comment] = []
    dropped: list[Dropped] = []
    for verdict in verdicts:
        candidate = candidates[verdict["candidate"]]
        if verdict["keep"]:
            comments.append(Comment(candidate.path, candidate.line, verdict["comment"]))
        else:
            dropped.append(Dropped(Comment(candidate.path, candidate.line, candidate.problem), verdict["reason"]))
    return comments, dropped


def _combined(per_lens: list[Checked]) -> Checked:
    return Checked(
        comments=[comment for checked in per_lens for comment in checked.comments],
        dropped=[dropped for checked in per_lens for dropped in checked.dropped],
        usage=sum((checked.usage for checked in per_lens), Usage()),
    )


def _edited(harness: Harness, change: Change, config: Config, checked: Checked) -> Checked:
    answer = harness.ask(_editor_prompt(change, config, checked.comments), COMMENTS_SCHEMA, change.checkout, read_code=False)
    return Checked(comments_from(answer.output), checked.dropped, checked.usage + answer.usage)


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
