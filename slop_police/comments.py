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
class Lines:
    """Lines `first` to `last` of a file in the head commit."""

    first: int
    last: int

    def __str__(self) -> str:
        return str(self.first) if self.first == self.last else f"{self.first}-{self.last}"

    def overlap(self, other: "Lines") -> "Lines | None":
        first, last = max(self.first, other.first), min(self.last, other.last)
        return Lines(first, last) if first <= last else None


@dataclass(frozen=True)
class Comment:
    path: str | None
    line: int | None
    body: str
    # The last line of the code the comment is about, the same as `line` for one line. A review file
    # written before ranges has none.
    end_line: int | None = None

    @property
    def lines(self) -> Lines | None:
        """None for a comment about a whole file or the whole change."""
        if self.line is None:
            return None
        return Lines(self.line, max(self.line, self.end_line or self.line))


@dataclass(frozen=True)
class Dropped:
    comment: Comment
    reason: str


def comments_from(output: dict) -> list[Comment]:
    """Reads the editor's answer, which has no `end_line`, and a review file, which may have one."""
    return [Comment(item["path"], item["line"], item["body"], item.get("end_line")) for item in output["comments"]]
