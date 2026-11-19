import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from slop_police.harness import Answer, Auth, HarnessFailed, PayerVariables, Usage, run_session

PAYERS = PayerVariables(
    plan=("CLAUDE_CODE_OAUTH_TOKEN",),
    api=("ANTHROPIC_API_KEY",),
    # A gateway's token and the switches to another cloud, which Claude Code takes over both of the above.
    elsewhere=("ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"),
)

READ_ONLY_TOOLS = (
    "Read",
    "Grep",
    "Glob",
    "Bash(git diff:*)",
    "Bash(git log:*)",
    "Bash(git show:*)",
)


# No settings file is read, of this machine or of the checkout: one could bring hooks, permission rules,
# `env` or an `apiKeyHelper` into the review.
NO_SETTINGS = ("--setting-sources", "")


@dataclass(frozen=True)
class SignIn:
    """Who Claude Code would bill, as `claude auth status` reports it."""

    method: str
    provider: str
    key_source: str | None = None

    def __str__(self) -> str:
        source = f', apiKeySource "{self.key_source}"' if self.key_source else ""
        return f'authMethod "{self.method}", apiProvider "{self.provider}"{source}'


NOT_SIGNED_IN = "none"

# The sign-ins through which the one who pays is the one each `Auth` names.
PAYING_SIGN_INS = {
    Auth.PLAN: (SignIn("claude.ai", "firstParty"), SignIn("oauth_token", "firstParty")),
    Auth.API: (SignIn("api_key", "firstParty", "ANTHROPIC_API_KEY"),),
}


@dataclass(frozen=True)
class ClaudeCode:
    auth: Auth
    model: str | None = None
    read_also: tuple[Path, ...] = ()

    def login_problem(self) -> str | None:
        if self.auth is Auth.API and not os.environ.get("ANTHROPIC_API_KEY"):
            return 'auth = "api" needs ANTHROPIC_API_KEY in the environment.'
        sign_in = _sign_in(PAYERS.environment(self.auth))
        if sign_in in PAYING_SIGN_INS[self.auth]:
            return None
        if self.auth is Auth.PLAN and sign_in.method == NOT_SIGNED_IN:
            return "Claude Code is not signed in: run `claude auth login`, or set CLAUDE_CODE_OAUTH_TOKEN."
        return f'auth = "{self.auth.value}", but `claude auth status` reports {sign_in}: someone else would pay.'

    def ask(self, prompt: str, schema: dict, cwd: Path, read_code: bool) -> Answer:
        completed = run_session(self._command(schema, read_code), prompt, cwd, PAYERS.environment(self.auth))
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
            *NO_SETTINGS,
            "--strict-mcp-config",
            "--no-session-persistence",
        ]
        if not read_code:
            return [*command, "--tools", ""]
        also = ["--add-dir", *map(str, self.read_also)] if self.read_also else []
        return [*command, *also, "--tools", "Read", "Grep", "Glob", "Bash", "--allowedTools", *READ_ONLY_TOOLS]


def _sign_in(environment: dict[str, str]) -> SignIn:
    """Asked with the sessions' settings, which are none, so that it reports the sign-in they will use."""
    status = subprocess.run(["claude", *NO_SETTINGS, "auth", "status"], capture_output=True, text=True, env=environment)
    try:
        reported = json.loads(status.stdout)
    except json.JSONDecodeError as error:
        raise HarnessFailed(f"`claude auth status` printed no JSON: {status.stderr or status.stdout}") from error
    return SignIn(reported["authMethod"], reported["apiProvider"], reported.get("apiKeySource"))


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
