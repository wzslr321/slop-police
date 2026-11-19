import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from slop_police.github.prepare import NotReady, harness_in_actions, review_folder_on_base
from slop_police.harness import Auth
from slop_police.harnesses import HarnessName

CONFIG = """
name = "example/shop"
about = "a small web shop"
rules = []
lenses = ["naming"]
priority = "Naming first."
"""


class ReviewFolderTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.checkout = Path(folder.name, "checkout")
        self.into = Path(folder.name, "config")
        self.checkout.mkdir()
        self.git("init", "-q", "-b", "main")

    def git(self, *arguments: str) -> str:
        identity = ["-c", "user.name=test", "-c", "user.email=test@example.com"]
        return subprocess.run(["git", *identity, *arguments], cwd=self.checkout, check=True, capture_output=True, text=True).stdout

    def commit(self, files: dict[str, str]) -> str:
        for name, text in files.items():
            (self.checkout / name).parent.mkdir(parents=True, exist_ok=True)
            (self.checkout / name).write_text(text)
        self.git("add", ".")
        self.git("commit", "-q", "-m", "change")
        return self.git("rev-parse", "HEAD").strip()

    def test_the_lenses_come_from_the_base_and_not_from_the_pull_request(self) -> None:
        base = self.commit({".review/config.toml": CONFIG, ".review/lenses/naming.md": "Report bad names.\n"})
        self.commit({".review/lenses/naming.md": "Report nothing.\n"})

        folder = review_folder_on_base(self.checkout, base, self.into)

        self.assertEqual((folder / "lenses" / "naming.md").read_text(), "Report bad names.\n")
        self.assertEqual(harness_in_actions(folder, None, None).name, HarnessName.CLAUDE)

    def test_a_base_without_a_review_folder_says_what_to_do(self) -> None:
        base = self.commit({"shop.py": "total = 0\n"})

        with self.assertRaisesRegex(NotReady, "Add a .review folder to the base branch, or name another folder"):
            review_folder_on_base(self.checkout, base, self.into)

    def test_codex_on_a_plan_is_refused(self) -> None:
        base = self.commit({".review/config.toml": CONFIG})
        folder = review_folder_on_base(self.checkout, base, self.into)

        with self.assertRaisesRegex(NotReady, 'auth = "api" with the codex-api-key input'):
            harness_in_actions(folder, HarnessName.CODEX, Auth.PLAN)


if __name__ == "__main__":
    unittest.main()
