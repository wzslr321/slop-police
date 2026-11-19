"""Only the variables of the chosen `auth` reach the CLI, and a sign-in through which someone else pays stops the review."""

import unittest
from unittest.mock import patch

from slop_police import claude_code, codex
from slop_police.claude_code import ClaudeCode, SignIn
from slop_police.codex import Codex
from slop_police.harness import Auth
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


class SignInTest(unittest.TestCase):
    def login_problem(self, auth: Auth, sign_in: SignIn) -> str | None:
        with patch.dict("os.environ", WITH_KEYS, clear=True), patch.object(claude_code, "_sign_in", return_value=sign_in):
            return ClaudeCode(auth).login_problem()

    def test_the_sign_in_that_auth_names_starts_the_review(self) -> None:
        self.assertIsNone(self.login_problem(Auth.PLAN, SignIn("claude.ai", "firstParty")))
        self.assertIsNone(self.login_problem(Auth.API, SignIn("api_key", "firstParty", "ANTHROPIC_API_KEY")))

    def test_a_sign_in_through_which_someone_else_pays_is_named(self) -> None:
        self.assertEqual(
            self.login_problem(Auth.PLAN, SignIn("api_key", "firstParty", "/login managed key")),
            'auth = "plan", but `claude auth status` reports authMethod "api_key", apiProvider "firstParty", '
            'apiKeySource "/login managed key": someone else would pay.',
        )

    def test_a_missing_key_is_named(self) -> None:
        with patch.dict("os.environ", {"PATH": "/usr/bin"}, clear=True):
            self.assertIn("ANTHROPIC_API_KEY", ClaudeCode(Auth.API).login_problem())
            self.assertIn("CODEX_API_KEY", Codex(Auth.API).login_problem())


class CommandLineChoiceTest(unittest.TestCase):
    configured = HarnessChoice(HarnessName.CLAUDE, Auth.PLAN, "claude-sonnet-5-5")

    def test_another_harness_drops_the_configured_model(self) -> None:
        self.assertEqual(
            self.configured.overridden(HarnessName.CODEX, None, None),
            HarnessChoice(HarnessName.CODEX, Auth.PLAN, None),
        )

    def test_the_same_harness_keeps_what_was_not_named(self) -> None:
        self.assertEqual(
            self.configured.overridden(None, Auth.API, None),
            HarnessChoice(HarnessName.CLAUDE, Auth.API, "claude-sonnet-5-5"),
        )


if __name__ == "__main__":
    unittest.main()
