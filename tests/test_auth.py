"""With `plan`, a key in the environment never reaches the CLI. With `api`, a missing key stops the review."""

import unittest
from unittest.mock import patch

from slop_police import claude_code, codex
from slop_police.claude_code import ClaudeCode
from slop_police.codex import Codex
from slop_police.harness import Auth, environment_for

WITH_KEYS = {
    "PATH": "/usr/bin",
    "ANTHROPIC_API_KEY": "a-key",
    "CLAUDE_CODE_OAUTH_TOKEN": "a-plan-token",
    "CODEX_API_KEY": "a-key",
    "OPENAI_API_KEY": "a-key",
}


class PlanTest(unittest.TestCase):
    def test_claude_gets_the_plan_token_and_no_api_key(self) -> None:
        with patch.dict("os.environ", WITH_KEYS, clear=True):
            environment = environment_for(Auth.PLAN, claude_code.API_VARIABLES)

        self.assertEqual(environment, {"PATH": "/usr/bin", "CLAUDE_CODE_OAUTH_TOKEN": "a-plan-token", "CODEX_API_KEY": "a-key", "OPENAI_API_KEY": "a-key"})

    def test_codex_gets_no_api_key(self) -> None:
        with patch.dict("os.environ", WITH_KEYS, clear=True):
            environment = environment_for(Auth.PLAN, codex.API_VARIABLES)

        self.assertNotIn("CODEX_API_KEY", environment)
        self.assertNotIn("OPENAI_API_KEY", environment)


class ApiTest(unittest.TestCase):
    def test_the_key_reaches_the_cli(self) -> None:
        with patch.dict("os.environ", WITH_KEYS, clear=True):
            self.assertEqual(environment_for(Auth.API, codex.API_VARIABLES)["CODEX_API_KEY"], "a-key")
            self.assertIsNone(ClaudeCode(Auth.API).login_problem())
            self.assertIsNone(Codex(Auth.API).login_problem())

    def test_a_missing_key_is_named(self) -> None:
        with patch.dict("os.environ", {"PATH": "/usr/bin"}, clear=True):
            self.assertIn("ANTHROPIC_API_KEY", ClaudeCode(Auth.API).login_problem())
            self.assertIn("CODEX_API_KEY", Codex(Auth.API).login_problem())


if __name__ == "__main__":
    unittest.main()
