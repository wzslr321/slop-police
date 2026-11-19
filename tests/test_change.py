import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from slop_police.change import UncommittedChanges, branch_change


class ChangeTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.checkout = Path(folder.name)
        self.git("init", "-q", "-b", "main")
        self.commit({"cart/shop.py": "total = 0\n"})

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

    def test_a_tracked_file_that_differs_from_head_stops_the_review(self) -> None:
        (self.checkout / "cart" / "shop.py").write_text("total = 1\n")

        with self.assertRaisesRegex(UncommittedChanges, "Commit or stash them first"):
            branch_change(self.checkout, "main", None, None)

        self.git("add", ".")
        with self.assertRaisesRegex(UncommittedChanges, "Commit or stash them first", msg="staged"):
            branch_change(self.checkout, "main", None, None)

    def test_an_untracked_file_does_not_stop_it(self) -> None:
        (self.checkout / "notes.txt").write_text("not part of the change\n")

        self.assertEqual(branch_change(self.checkout, "main", None, None).title, "main")


if __name__ == "__main__":
    unittest.main()
