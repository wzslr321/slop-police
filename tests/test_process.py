"""The process end to end, with scripted answers in place of a model."""

import subprocess
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

from slop_police import process
from slop_police.change import Change
from slop_police.codex import _strict
from slop_police.comments import COMMENTS_SCHEMA, Comment
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
    """Answers each lens with one candidate to keep and one to drop, and the editor with one comment moved a line down."""

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
        merged = [{"path": "shop.py", "line": 1, "body": "naming: fix it"}, {"path": "shop.py", "line": 2, "body": "tests: fix it"}]
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


@dataclass
class DescribingHarness(ScriptedHarness):
    """The lens `tests` keeps a candidate about the description, and the editor rewrites every body it is given."""

    def ask(self, prompt: str, schema: dict, cwd: Path, read_code: bool) -> Answer:
        if schema is CANDIDATES_SCHEMA and "Lens: tests" in prompt:
            no_place = {"path": None, "line": None, "end_line": None, "symbol": None}
            about_the_description = {**no_place, "problem": "p", "evidence": "Sums the cart.", "fix": "f"}
            return Answer({"candidates": [about_the_description, _candidate("tests wrong")]}, Usage())
        if schema is COMMENTS_SCHEMA:
            rewritten = [{"path": "shop.py", "line": 1, "body": "naming: rewritten"}]
            if "Sums the cart." in prompt:
                rewritten.append({"path": None, "line": None, "body": "tests: rewritten"})
            return Answer({"comments": rewritten}, Usage())
        return super().ask(prompt, schema, cwd, read_code)


@dataclass
class WholeFileHarness(ScriptedHarness):
    """The lens `tests` keeps a candidate that names a file and no lines."""

    def ask(self, prompt: str, schema: dict, cwd: Path, read_code: bool) -> Answer:
        if schema is CANDIDATES_SCHEMA and "Lens: tests" in prompt:
            whole_file = {**_candidate("tests kept"), "line": None, "end_line": None, "symbol": None}
            return Answer({"candidates": [whole_file, _candidate("tests wrong")]}, Usage())
        return super().ask(prompt, schema, cwd, read_code)


@dataclass
class ElsewhereHarness(ScriptedHarness):
    """The lens `tests` keeps a candidate on a file the change leaves as it is, and the editor keeps both comments."""

    def ask(self, prompt: str, schema: dict, cwd: Path, read_code: bool) -> Answer:
        if schema is CANDIDATES_SCHEMA and "Lens: tests" in prompt:
            on_the_rules = {**_candidate("tests kept"), "path": "RULES.md", "end_line": 1}
            return Answer({"candidates": [on_the_rules, _candidate("tests wrong")]}, Usage())
        if schema is COMMENTS_SCHEMA:
            rewritten = [{"path": "shop.py", "line": 1, "body": "naming: rewritten"}]
            if "RULES.md" in prompt:
                rewritten.append({"path": "RULES.md", "line": 1, "body": "tests: rewritten"})
            return Answer({"comments": rewritten}, Usage())
        return super().ask(prompt, schema, cwd, read_code)


def _candidate(problem: str) -> dict:
    return {"path": "shop.py", "line": 1, "end_line": 3, "symbol": "total", "problem": problem, "evidence": "x", "fix": "y"}


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
            [Comment("shop.py", 1, "naming: fix it", end_line=3), Comment("shop.py", 2, "tests: fix it", end_line=2)],
            "the editor's comment at the lens's line takes its range, the moved one keeps one line, max_comments cuts the third",
        )
        self.assertEqual([dropped.reason for dropped in review.dropped], ["the code does not show it"] * 2)

    def test_each_lens_gets_the_change_and_the_repository_rules(self) -> None:
        self.review()

        finding = [prompt for prompt in self.harness.prompts if "Lens: naming" in prompt][0]
        self.assertIn("pull request #7 of example/shop, a small web shop", finding)
        self.assertIn("- shop.py (+2 -0)", finding)
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

    def test_a_candidate_without_a_path_is_checked_against_the_description(self) -> None:
        self.harness = DescribingHarness()

        self.review()

        check = [prompt for prompt in self.harness.prompts if "Candidates, numbered" in prompt][-1]
        self.assertIn("Description:\n\nSums the cart.", check)

    def test_a_comment_on_the_description_passes_the_editor_by_with_its_quote(self) -> None:
        self.harness = DescribingHarness()

        review = self.review()

        on_the_description = Comment(None, None, "> Sums the cart.\n\ntests: fix it")
        self.assertEqual(review.comments, [Comment("shop.py", 1, "naming: rewritten", end_line=3), on_the_description])

    def test_a_candidate_with_a_path_and_no_lines_does_not_stop_the_run(self) -> None:
        self.harness = WholeFileHarness()

        review = self.review()

        self.assertEqual(review.comments[0], Comment("shop.py", 1, "naming: fix it", end_line=3))

    def test_the_check_knows_which_candidates_are_off_the_changed_lines(self) -> None:
        self.harness = ElsewhereHarness()

        self.review()

        check = [prompt for prompt in self.harness.prompts if "Candidates, numbered" in prompt][-1]
        self.assertIn('#0 {"path": "RULES.md", "line": 1, "end_line": 1,', check)
        self.assertIn('"problem": "tests kept", "evidence": "x", "fix": "y", "on_changed_lines": false}', check)
        self.assertIn('"problem": "tests wrong", "evidence": "x", "fix": "y", "on_changed_lines": true}', check)

    def test_a_comment_the_editor_puts_off_the_changed_lines_is_marked_as_left_behind(self) -> None:
        self.harness = ElsewhereHarness()

        review = self.review()

        left_behind = Comment("RULES.md", 1, "tests: rewritten", end_line=1, elsewhere=True)
        self.assertEqual(review.comments, [Comment("shop.py", 1, "naming: rewritten", end_line=3), left_behind])


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
    (checkout / "shop.py").write_text("total = 0\ncount = 0\n")
    (checkout / "pubspec.lock").write_text("locked\n")
    git("add", ".")
    git("commit", "-q", "-m", "add totals")
    return base


if __name__ == "__main__":
    unittest.main()
