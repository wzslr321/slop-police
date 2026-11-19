"""The process end to end, with scripted answers in place of a model."""

import subprocess
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

from slop_police import process
from slop_police.change import Change
from slop_police.codex import _strict
from slop_police.comments import Comment
from slop_police.config import load_config
from slop_police.harness import Answer, HarnessFailed, Usage
from slop_police.process import CANDIDATES_SCHEMA, VERDICTS_SCHEMA

CONFIG = """
name = "example/shop"
about = "a small web shop"
rules = ["RULES.md"]
lenses = ["naming", "tests"]
priority = "Naming first."
ignore = ["*.lock"]
max_comments = 2
"""


@dataclass
class ScriptedHarness:
    """Answers each lens with one candidate to keep and one to drop, and the editor with what it was given."""

    prompts: list[str] = field(default_factory=list)

    def login_problem(self) -> str | None:
        return None

    def ask(self, prompt: str, schema: dict, cwd: Path, read_code: bool) -> Answer:
        self.prompts.append(prompt)
        if schema is CANDIDATES_SCHEMA:
            lens = "naming" if "Lens: naming" in prompt else "tests"
            return Answer({"candidates": [_candidate(f"{lens} kept"), _candidate(f"{lens} wrong")]}, Usage(10, 1, 0.5))
        if schema is VERDICTS_SCHEMA:
            lens = "naming" if "Lens: naming" in prompt else "tests"
            return Answer(
                {
                    "verdicts": [
                        {"candidate": 0, "keep": True, "reason": "", "comment": f"{lens}: fix it"},
                        {"candidate": 1, "keep": False, "reason": "the code does not show it", "comment": ""},
                    ]
                },
                Usage(10, 1, 0.5),
            )
        merged = [{"path": "shop.py", "line": 1, "body": "naming: fix it"}, {"path": "shop.py", "line": 1, "body": "tests: fix it"}]
        return Answer({"comments": [*merged, {"path": None, "line": None, "body": "a third one"}]}, Usage(5, 1, None))


@dataclass
class MiscountingHarness(ScriptedHarness):
    """Checks the two candidates of each lens with one verdict per index in `judged`."""

    judged: tuple[int, ...] = ()

    def ask(self, prompt: str, schema: dict, cwd: Path, read_code: bool) -> Answer:
        if schema is VERDICTS_SCHEMA:
            verdicts = [{"candidate": index, "keep": True, "reason": "", "comment": "fix it"} for index in self.judged]
            return Answer({"verdicts": verdicts}, Usage())
        return super().ask(prompt, schema, cwd, read_code)


def _candidate(problem: str) -> dict:
    return {"path": "shop.py", "line": 1, "symbol": "total", "problem": problem, "evidence": "x", "fix": "y"}


class ProcessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.checkout = Path(self.folder.name)
        self.base = _repository_with_one_change(self.checkout)
        self.harness = ScriptedHarness()

    def review(self) -> process.Review:
        change = Change(self.checkout, self.base, "pull request #7", "Add totals", "Sums the cart.")
        return process.review(change, load_config(self.checkout / ".review"), harness=self.harness)

    def test_kept_candidates_become_comments_and_dropped_ones_keep_their_reason(self) -> None:
        review = self.review()

        self.assertEqual(
            review.comments,
            [Comment("shop.py", 1, "naming: fix it"), Comment("shop.py", 1, "tests: fix it")],
            "the editor's third comment is cut by max_comments",
        )
        self.assertEqual([dropped.reason for dropped in review.dropped], ["the code does not show it"] * 2)

    def test_each_lens_gets_the_change_and_the_repository_rules(self) -> None:
        self.review()

        finding = [prompt for prompt in self.harness.prompts if "Lens: naming" in prompt][0]
        self.assertIn("pull request #7 of example/shop, a small web shop", finding)
        self.assertIn("- shop.py (+1 -0)", finding)
        self.assertNotIn("pubspec.lock", finding, "ignored files are not listed")
        self.assertIn("rules are in `RULES.md`", finding)

    def test_a_harness_without_prices_leaves_the_cost_unknown(self) -> None:
        usage = self.review().usage

        self.assertEqual((usage.input_tokens, usage.output_tokens), (45, 5))
        self.assertIsNone(usage.cost_usd)

    def test_a_candidate_without_exactly_one_verdict_stops_the_run(self) -> None:
        problems = {
            "no verdict for #0, #1": (),
            "more than one verdict for #0": (0, 1, 0),
            "verdicts for candidates that do not exist: #2": (0, 1, 2),
        }
        for problem, judged in problems.items():
            with self.subTest(problem):
                self.harness = MiscountingHarness(judged=judged)

                with self.assertRaises(HarnessFailed) as stopped:
                    self.review()

                self.assertEqual(str(stopped.exception), f"The check of lens `naming` gave {problem}.")


class CodexSchemaTest(unittest.TestCase):
    def test_every_object_refuses_other_properties(self) -> None:
        strict = _strict(CANDIDATES_SCHEMA)

        self.assertIs(strict["additionalProperties"], False)
        self.assertIs(strict["properties"]["candidates"]["items"]["additionalProperties"], False)
        self.assertNotIn("additionalProperties", CANDIDATES_SCHEMA, "the engine's own schema stays as it was")


def _repository_with_one_change(checkout: Path) -> str:
    def git(*arguments: str) -> str:
        identity = ["-c", "user.name=test", "-c", "user.email=test@example.com"]
        return subprocess.run(["git", *identity, *arguments], cwd=checkout, check=True, capture_output=True, text=True).stdout

    review_folder = checkout / ".review"
    (review_folder / "lenses").mkdir(parents=True)
    (review_folder / "config.toml").write_text(CONFIG)
    (review_folder / "lenses" / "naming.md").write_text("## Lens: naming\n")
    (review_folder / "lenses" / "tests.md").write_text("## Lens: tests\n")
    (checkout / "RULES.md").write_text("Name things.\n")
    git("init", "-q", "-b", "main")
    git("add", ".")
    git("commit", "-q", "-m", "start")
    base = git("rev-parse", "HEAD").strip()
    (checkout / "shop.py").write_text("total = 0\n")
    (checkout / "pubspec.lock").write_text("locked\n")
    git("add", ".")
    git("commit", "-q", "-m", "add totals")
    return base


if __name__ == "__main__":
    unittest.main()
