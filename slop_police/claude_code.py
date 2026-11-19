import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from slop_police.harness import Answer, Auth, HarnessFailed, Usage, environment_for, run_session

# Claude Code takes each of these over a subscription login, in `-p` mode without asking.
API_VARIABLES = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
)

READ_ONLY_TOOLS = (
    "Read",
    "Grep",
    "Glob",
    "Bash(git diff:*)",
    "Bash(git log:*)",
    "Bash(git show:*)",
)


@dataclass(frozen=True)
class ClaudeCode:
    auth: Auth
    model: str | None = None
    read_also: tuple[Path, ...] = ()

    def login_problem(self) -> str | None:
        if self.auth is Auth.API:
            return None if os.environ.get("ANTHROPIC_API_KEY") else 'auth = "api" needs ANTHROPIC_API_KEY in the environment.'
        if _signed_in(environment_for(self.auth, API_VARIABLES)):
            return None
        return "Claude Code is not signed in: run `claude auth login`, or set CLAUDE_CODE_OAUTH_TOKEN."

    def ask(self, prompt: str, schema: dict, cwd: Path, read_code: bool) -> Answer:
        completed = run_session(self._command(schema, read_code), prompt, cwd, environment_for(self.auth, API_VARIABLES))
        if completed.returncode != 0:
            raise HarnessFailed(completed.stderr or completed.stdout)
        return _answer(json.loads(completed.stdout))

    def _command(self, schema: dict, read_code: bool) -> list[str]:
        command = [
            "claude",
            "-p",
            *(["--model", self.model] if self.model else []),
            "--output-format", "json",
            "--json-schema", json.dumps(schema),
            "--permission-mode", "dontAsk",
            # User settings are skipped so that no hook of this machine reaches the reviewer.
            "--setting-sources", "project",
            "--strict-mcp-config",
            "--no-session-persistence",
        ]
        if not read_code:
            return [*command, "--tools", ""]
        also = ["--add-dir", *map(str, self.read_also)] if self.read_also else []
        return [*command, *also, "--tools", "Read", "Grep", "Glob", "Bash", "--allowedTools", *READ_ONLY_TOOLS]


def _signed_in(environment: dict[str, str]) -> bool:
    status = subprocess.run(["claude", "auth", "status"], capture_output=True, text=True, env=environment)
    try:
        return bool(json.loads(status.stdout).get("loggedIn"))
    except json.JSONDecodeError:
        return False


def _answer(result: dict) -> Answer:
    if result.get("is_error") or "structured_output" not in result:
        raise HarnessFailed(json.dumps(result)[:2000])
    used = result["usage"]
    return Answer(
        output=result["structured_output"],
        usage=Usage(
            input_tokens=used["input_tokens"] + used["cache_creation_input_tokens"] + used["cache_read_input_tokens"],
            output_tokens=used["output_tokens"],
            # With a subscription this is what the tokens would cost through the API.
            cost_usd=result["total_cost_usd"],
        ),
    )
