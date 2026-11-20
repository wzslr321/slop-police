"""Only the variables of the chosen `auth` reach the CLI, and a sign-in through which someone else pays stops the review."""

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from slop_police import claude_code, codex
from slop_police.claude_code import ClaudeCode
from slop_police.codex import Codex
from slop_police.harness import Auth, Effort
from slop_police.harnesses import HarnessChoice, HarnessName

WITH_KEYS = {
    "PATH": "/usr/bin",
    "ANTHROPIC_API_KEY": "a-key",
    "ANTHROPIC_AUTH_TOKEN": "a-gateway-token",
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "CLAUDE_CODE_OAUTH_TOKEN": "a-plan-token",
    "CODEX_API_KEY": "a-key",
    "OPENAI_API_KEY": "a-key",
}
NOT_CLAUDE = {"PATH": "/usr/bin", "CODEX_API_KEY": "a-key", "OPENAI_API_KEY": "a-key"}


class EnvironmentTest(unittest.TestCase):
    def test_claude_gets_the_plan_token_or_the_api_key_and_nothing_else_that_pays(self) -> None:
        with patch.dict("os.environ", WITH_KEYS, clear=True):
            on_plan = claude_code.PAYERS.environment(Auth.PLAN)
            on_api = claude_code.PAYERS.environment(Auth.API)

        self.assertEqual(on_plan, {**NOT_CLAUDE, "CLAUDE_CODE_OAUTH_TOKEN": "a-plan-token"})
        self.assertEqual(on_api, {**NOT_CLAUDE, "ANTHROPIC_API_KEY": "a-key"})

    def test_codex_gets_codex_api_key_with_api_and_no_other_key(self) -> None:
        with patch.dict("os.environ", WITH_KEYS, clear=True):
            on_plan = codex.PAYERS.environment(Auth.PLAN)
            on_api = codex.PAYERS.environment(Auth.API)

        self.assertFalse({"CODEX_API_KEY", "OPENAI_API_KEY"} & on_plan.keys())
        self.assertEqual(on_api["CODEX_API_KEY"], "a-key")
        self.assertNotIn("OPENAI_API_KEY", on_api)


# `claude --setting-sources "" auth status` of Claude Code 2.1.319, without the fields the check does not read.
TOKEN_STATUS = '{"loggedIn": true, "authMethod": "oauth_token", "apiProvider": "firstParty"}'
API_KEY_STATUS = '{"loggedIn": true, "authMethod": "api_key", "apiProvider": "firstParty", "apiKeySource": "ANTHROPIC_API_KEY"}'


class SignInTest(unittest.TestCase):
    def login_problem(self, auth: Auth, environment: dict[str, str], status: str) -> str | None:
        reported = subprocess.CompletedProcess(["claude"], 0, stdout=status, stderr="")
        with patch.dict("os.environ", environment, clear=True), patch.object(claude_code.subprocess, "run", return_value=reported):
            return ClaudeCode(auth).login_problem()

    def test_the_sign_in_that_auth_names_starts_the_review(self) -> None:
        self.assertIsNone(self.login_problem(Auth.PLAN, {"CLAUDE_CODE_OAUTH_TOKEN": "a-plan-token"}, TOKEN_STATUS))
        self.assertIsNone(self.login_problem(Auth.API, {"ANTHROPIC_API_KEY": "a-key"}, API_KEY_STATUS))

    def test_a_token_that_is_not_the_plan_token_is_named(self) -> None:
        self.assertEqual(
            self.login_problem(Auth.PLAN, {}, TOKEN_STATUS),
            'auth = "plan", but `claude auth status` reports authMethod "oauth_token", apiProvider "firstParty": '
            "someone else would pay.",
        )

    def test_a_missing_key_is_named(self) -> None:
        with patch.dict("os.environ", {"PATH": "/usr/bin"}, clear=True):
            self.assertIn("ANTHROPIC_API_KEY", ClaudeCode(Auth.API).login_problem())
            self.assertIn("CODEX_API_KEY", Codex(Auth.API).login_problem())


class CommandLineChoiceTest(unittest.TestCase):
    configured = HarnessChoice(HarnessName.CLAUDE, Auth.PLAN, "claude-sonnet-5-5", Effort.HIGH)

    def test_another_harness_drops_the_configured_model_and_keeps_the_effort(self) -> None:
        self.assertEqual(
            self.configured.overridden(HarnessName.CODEX, None, None, None),
            HarnessChoice(HarnessName.CODEX, Auth.PLAN, None, Effort.HIGH),
        )

    def test_the_same_harness_keeps_what_was_not_named(self) -> None:
        self.assertEqual(
            self.configured.overridden(None, Auth.API, None, Effort.XHIGH),
            HarnessChoice(HarnessName.CLAUDE, Auth.API, "claude-sonnet-5-5", Effort.XHIGH),
        )


class EffortTest(unittest.TestCase):
    def test_each_cli_gets_the_effort_in_its_own_option(self) -> None:
        claude_command = ClaudeCode(Auth.PLAN, effort=Effort.XHIGH)._command({}, read_code=False)
        codex_command = Codex(Auth.API, effort=Effort.XHIGH)._command(Path("schema"), Path("answer"), Path("."))

        self.assertIn(["--effort", "xhigh"], _pairs(claude_command))
        self.assertIn(["--config", 'model_reasoning_effort="xhigh"'], _pairs(codex_command))


def _pairs(command: list[str]) -> list[list[str]]:
    return [command[index : index + 2] for index in range(len(command) - 1)]


if __name__ == "__main__":
    unittest.main()
