from collections.abc import Mapping
from dataclasses import dataclass, replace

from slop_police.comments import Comment, Dropped
from slop_police.process import Review

# The reviewer can read files, on Linux also `/proc/self/environ`, and its words may be posted on a pull request.
CREDENTIAL_VARIABLES = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CODEX_API_KEY",
    "OPENAI_API_KEY",
)

REDACTED = "[redacted]"


@dataclass(frozen=True)
class Redaction:
    secrets: tuple[str, ...]

    @classmethod
    def of(cls, environment: Mapping[str, str]) -> "Redaction":
        """The values of the credential variables that are set, the longest first so that none hides part of another."""
        values = {environment[name] for name in CREDENTIAL_VARIABLES if environment.get(name)}
        return cls(tuple(sorted(values, key=len, reverse=True)))

    def text(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, REDACTED)
        return text

    def review(self, review: Review) -> Review:
        return replace(
            review,
            comments=[self._comment(comment) for comment in review.comments],
            dropped=[Dropped(self._comment(dropped.comment), self.text(dropped.reason)) for dropped in review.dropped],
        )

    def _comment(self, comment: Comment) -> Comment:
        path = None if comment.path is None else self.text(comment.path)
        return replace(comment, path=path, body=self.text(comment.body))
