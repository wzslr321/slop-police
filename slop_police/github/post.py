import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from slop_police.comments import Comment, comments_from
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
    inline: tuple[Comment, ...]
    # The comments whose line the diff does not show, and those about a whole file or the whole change.
    in_body: tuple[Comment, ...]


def placed(comments: list[Comment], diff: RightSide) -> Placement:
    def inline(comment: Comment) -> bool:
        return comment.path is not None and comment.line is not None and diff.shows(comment.path, comment.line)

    return Placement(
        inline=tuple(comment for comment in comments if inline(comment)),
        in_body=tuple(comment for comment in comments if not inline(comment)),
    )


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
            "comments": [
                {"path": comment.path, "line": comment.line, "side": "RIGHT", "body": comment.body}
                for comment in self.placement.inline
            ],
        }


def _body(placement: Placement) -> str:
    total = len(placement.inline) + len(placement.in_body)
    if not placement.in_body:
        return f"slop-police: {_comments(total)} on the diff."
    summary = f"slop-police: {_comments(total)}, {len(placement.in_body)} of them not on a line of the diff:"
    return "\n\n".join([summary, *map(_section, placement.in_body)])


def _section(comment: Comment) -> str:
    if comment.path is None:
        place = "The whole change"
    elif comment.line is None:
        place = f"`{comment.path}`"
    else:
        place = f"`{comment.path}:{comment.line}`"
    return f"**{place}**\n\n{comment.body}"


def _comments(count: int) -> str:
    return "1 comment" if count == 1 else f"{count} comments"


def _send(request: ReviewRequest) -> None:
    posted = subprocess.run(
        ["gh", "api", "--method", "POST", request.pull_request.reviews_endpoint, "--input", "-"],
        input=json.dumps(request.payload()),
        stdout=subprocess.PIPE,
        text=True,
    )
    if posted.returncode != 0:
        sys.exit(posted.returncode)
    print(f"Posted {json.loads(posted.stdout)['html_url']}")


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
    placement = placed(comments, right_side(arguments.diff.read_text()))
    print(f"On lines of the diff: {len(placement.inline)}. In the review body: {len(placement.in_body)}.")
    request = ReviewRequest(PullRequest(arguments.repository, arguments.pull_request), arguments.commit, placement)
    if arguments.dry_run:
        print(f"POST {request.pull_request.reviews_endpoint}")
        print(json.dumps(request.payload(), indent=2, ensure_ascii=False))
        return
    _send(request)


if __name__ == "__main__":
    main()
