import json
from dataclasses import asdict

from slop_police.comments import Comment
from slop_police.process import Review


def as_markdown(review: Review) -> str:
    if not review.comments:
        return "No findings."
    return "\n\n".join(_numbered(number, comment) for number, comment in enumerate(review.comments, start=1))


def _numbered(number: int, comment: Comment) -> str:
    return f"{number}. {_place(comment)}\n\n{comment.body}"


def _place(comment: Comment) -> str:
    if comment.path is None:
        return "the description"
    if comment.lines is None:
        return f"`{comment.path}`"
    return f"`{comment.path}:{comment.lines}`"


def as_json(review: Review) -> str:
    return json.dumps(asdict(review), indent=2, ensure_ascii=False) + "\n"
