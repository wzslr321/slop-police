from dataclasses import dataclass

COMMENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "comments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": ["string", "null"]},
                    "line": {"type": ["integer", "null"]},
                    "body": {"type": "string"},
                },
                "required": ["path", "line", "body"],
            },
        }
    },
    "required": ["comments"],
}


@dataclass(frozen=True)
class Comment:
    path: str | None
    line: int | None
    body: str


@dataclass(frozen=True)
class Dropped:
    comment: Comment
    reason: str


def comments_from(output: dict) -> list[Comment]:
    return [Comment(item["path"], item["line"], item["body"]) for item in output["comments"]]
