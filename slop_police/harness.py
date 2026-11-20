import os
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol


class Auth(Enum):
    """Who pays for a session: the subscription the CLI is signed in to, or an API key from the environment."""

    PLAN = "plan"
    API = "api"


class Effort(Enum):
    """How hard the model reasons, in the levels that both Claude Code and Codex take."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    # None when the harness reports tokens only.
    cost_usd: float | None = 0.0

    def __add__(self, other: "Usage") -> "Usage":
        priced = self.cost_usd is not None and other.cost_usd is not None
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cost_usd=self.cost_usd + other.cost_usd if priced else None,
        )


@dataclass(frozen=True)
class Answer:
    output: dict
    usage: Usage


SESSION_TIMEOUT_SECONDS = 20 * 60


class HarnessFailed(Exception):
    pass


class Harness(Protocol):
    def login_problem(self) -> str | None:
        """Why no session can start with the chosen `Auth`, or None when one can."""

    def ask(self, prompt: str, schema: dict, cwd: Path, read_code: bool) -> Answer:
        """One session that answers in `schema`. With `read_code` it may read `cwd`, and nothing may write."""


def run_session(command: list[str], prompt: str, cwd: Path | None, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            input=prompt,
            cwd=cwd,
            capture_output=True,
            text=True,
            env=environment,
            timeout=SESSION_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as timeout:
        raise HarnessFailed(f"`{command[0]}` gave no answer in {SESSION_TIMEOUT_SECONDS // 60} minutes.") from timeout


@dataclass(frozen=True)
class PayerVariables:
    """The environment variables through which a CLI picks who pays: those of each `Auth`, and those of anyone else."""

    plan: tuple[str, ...]
    api: tuple[str, ...]
    elsewhere: tuple[str, ...]

    def environment(self, auth: Auth) -> dict[str, str]:
        """This process's environment without the variables through which someone other than `auth` would pay."""
        kept = self.plan if auth is Auth.PLAN else self.api
        dropped = {*self.plan, *self.api, *self.elsewhere} - {*kept}
        return {name: value for name, value in os.environ.items() if name not in dropped}
