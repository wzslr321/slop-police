import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from slop_police.comments import Comment, Lines, comments_from
from slop_police.github.diff import RightSide, right_side


@dataclass(frozen=True)
class PullRequest:
    repository: str
    number: int

    @property
    def reviews_endpoint(self) -> str:
        return f"repos/{self.repository}/pulls/{self.number}/reviews"


@dataclass(frozen=True)
class Placement:
    # Cut to the lines the diff shows in one hunk.
    inline: tuple[Comment, ...]
    # The comments whose lines the diff does not show, and those about a whole file or the description.
    in_body: tuple[Comment, ...]


def right_side_of(diff_file: Path) -> RightSide:
    """A changed file in another encoding, such as Latin-1, must not stop the posting, which reads only paths and line markers."""
    return right_side(diff_file.read_text(encoding="utf-8", errors="replace"))


def placed(comments: list[Comment], diff: RightSide) -> Placement:
    inline: list[Comment] = []
    in_body: list[Comment] = []
    for comment in comments:
        lines = _shown_lines(comment, diff)
        if lines is None:
            in_body.append(comment)
        else:
            inline.append(replace(comment, line=lines.first, end_line=lines.last))
    return Placement(tuple(inline), tuple(in_body))


def _shown_lines(comment: Comment, diff: RightSide) -> Lines | None:
    if comment.path is None or comment.lines is None:
        return None
    return diff.shown_part(comment.path, comment.lines)


@dataclass(frozen=True)
class ReviewRequest:
    """One review that only comments, on the head commit that was reviewed."""

    pull_request: PullRequest
    commit: str
    placement: Placement

    def payload(self) -> dict:
        return {
            "commit_id": self.commit,
            "event": "COMMENT",
            "body": _body(self.placement),
            "comments": [_inline(comment) for comment in self.placement.inline],
        }


def _inline(comment: Comment) -> dict:
    """GitHub takes a range as its last `line` and its `start_line`, both on the right side, the head commit."""
    lines = comment.lines
    inline = {"path": comment.path, "line": lines.last, "side": "RIGHT", "body": comment.body}
    if lines.first == lines.last:
        return inline
    return {**inline, "start_line": lines.first, "start_side": "RIGHT"}


def _body(placement: Placement) -> str:
    total = len(placement.inline) + len(placement.in_body)
    if not placement.in_body:
        return f"slop-police: {_comments(total)} on the diff."
    summary = f"slop-police: {_comments(total)}, {len(placement.in_body)} of them not on a line of the diff:"
    sections = [_section(comment) for comment in placement.in_body if comment.path is not None]
    on_description = [comment.body for comment in placement.in_body if comment.path is None]
    if on_description:
        sections.append("\n\n".join(["**The description**", *on_description]))
    return "\n\n".join([summary, *sections])


def _section(comment: Comment) -> str:
    if comment.lines is None:
        place = f"`{comment.path}`"
    else:
        place = f"`{comment.path}:{comment.lines}`"
    return f"**{place}**\n\n{comment.body}"


def _comments(count: int) -> str:
    return "1 comment" if count == 1 else f"{count} comments"


# How `gh api` names an answer of 5xx on its error output, such as "gh: Server Error (HTTP 502)".
SERVER_ERROR = re.compile(r"\(HTTP 5\d\d\)")
LOOKS_FOR_THE_REVIEW = 3
SECONDS_BETWEEN_LOOKS = 10
# GitHub stamps the review with its own clock, the runner sent the request by its own.
CLOCK_SKEW = timedelta(minutes=1)


def _send(request: ReviewRequest) -> None:
    sent_at = datetime.now(timezone.utc)
    posted = subprocess.run(
        ["gh", "api", "--method", "POST", request.pull_request.reviews_endpoint, "--input", "-"],
        input=json.dumps(request.payload()),
        capture_output=True,
        text=True,
    )
    sys.stderr.write(posted.stderr)
    if posted.returncode == 0:
        print(f"Posted {json.loads(posted.stdout)['html_url']}")
        return
    if SERVER_ERROR.search(posted.stderr) and (url := _posted_anyway(request, sent_at)):
        print(f"GitHub answered with a server error, but the review is on the pull request: {url}")
        return
    sys.exit(posted.returncode)


def _posted_anyway(request: ReviewRequest, sent_at: datetime) -> str | None:
    """The address of the review GitHub created before it answered with a server error.

    A red job next to it invites a re-run, which posts it twice or pays for another review.
    """
    for look in range(LOOKS_FOR_THE_REVIEW):
        if look:
            time.sleep(SECONDS_BETWEEN_LOOKS)
        for review in _reviews(request.pull_request):
            if _is_from(review, request, sent_at):
                return review["html_url"]
    return None


def _reviews(pull_request: PullRequest) -> list[dict]:
    listed = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", f"{pull_request.reviews_endpoint}?per_page=100"],
        capture_output=True,
        text=True,
    )
    if listed.returncode != 0:
        return []
    return [review for page in json.loads(listed.stdout) for review in page]


def _is_from(review: dict, request: ReviewRequest, sent_at: datetime) -> bool:
    """Whether `request` created `review`, and not an earlier review with the same body on the same commit."""
    return (
        review["commit_id"] == request.commit
        and review["body"] == request.payload()["body"]
        and datetime.fromisoformat(review["submitted_at"]) >= sent_at - CLOCK_SKEW
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="slop_police.github.post", description="Post a review file on a pull request.")
    parser.add_argument("review", type=Path, help="the file slop-police --json wrote")
    parser.add_argument("--diff", type=Path, required=True, help="the reviewed change, from `git diff base...head`")
    parser.add_argument("--commit", required=True, help="the head commit that was reviewed")
    parser.add_argument("--repository", required=True, help="owner/name")
    parser.add_argument("--pull-request", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true", help="print the request instead of sending it")
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    comments = comments_from(json.loads(arguments.review.read_text()))
    if not comments:
        print("The review has no comments, so nothing is posted.")
        return
    placement = placed(comments, right_side_of(arguments.diff))
    print(f"On lines of the diff: {len(placement.inline)}. In the review body: {len(placement.in_body)}.")
    request = ReviewRequest(PullRequest(arguments.repository, arguments.pull_request), arguments.commit, placement)
    if arguments.dry_run:
        print(f"POST {request.pull_request.reviews_endpoint}")
        print(json.dumps(request.payload(), indent=2, ensure_ascii=False))
        return
    _send(request)


if __name__ == "__main__":
    main()
