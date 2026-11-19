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

    def overridden(self, name: HarnessName | None, auth: Auth | None, model: str | None) -> "HarnessChoice":
        """This choice with what the command line names instead. Another harness drops the model of the first one."""
        other_harness = name is not None and name is not self.name
        return HarnessChoice(
            name=name or self.name,
            auth=auth or self.auth,
            model=model or (None if other_harness else self.model),
        )


def harness_for(choice: HarnessChoice, read_also: tuple[Path, ...]) -> Harness:
    implementation = {HarnessName.CLAUDE: ClaudeCode, HarnessName.CODEX: Codex}[choice.name]
    return implementation(choice.auth, choice.model, read_also)
