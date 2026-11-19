from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from slop_police.claude_code import ClaudeCode
from slop_police.codex import Codex
from slop_police.harness import Auth, Harness


class HarnessName(Enum):
    CLAUDE = "claude"
    CODEX = "codex"


@dataclass(frozen=True)
class HarnessChoice:
    """The `[harness]` table of a repository's `config.toml`."""

    name: HarnessName = HarnessName.CLAUDE
    auth: Auth = Auth.PLAN
    # None leaves the model to the CLI's own default.
    model: str | None = None


def harness_for(choice: HarnessChoice, read_also: tuple[Path, ...]) -> Harness:
    implementation = {HarnessName.CLAUDE: ClaudeCode, HarnessName.CODEX: Codex}[choice.name]
    return implementation(choice.auth, choice.model, read_also)
