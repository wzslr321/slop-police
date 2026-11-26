import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from slop_police.change import Change, ChangedFile, UncommittedChanges, branch_change, changed_files, changed_lines
from slop_police.comments import Lines


class ChangeTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.checkout = Path(folder.name)
        self.git("init", "-q", "-b", "main")
        self.base = self.commit({"cart/shop.py": "total = 0\n"})

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

    def test_changed_files_have_the_paths_of_the_head_commit(self) -> None:
        self.git("mv", "cart/shop.py", "cart/store.py")
        (self.checkout / "logo.png").write_bytes(b"\x89PNG\0")
        self.commit({"café.py": "menu = []\n"})

        files = changed_files(Change(self.checkout, self.base, "a change", "Rename", ""), ignore=())

        self.assertEqual(
            files,
            [ChangedFile("café.py", 1, 0), ChangedFile("cart/store.py", 0, 0), ChangedFile("logo.png", 0, 0)],
        )

    def test_changed_lines_are_the_ones_the_head_commit_adds_or_rewrites(self) -> None:
        base = self.commit({"cart/shop.py": "total = 0\ncount = 0\nprint(total)\nprint(count)\n"})
        self.commit({"cart/shop.py": "total = 0\ncount = 1\nprint(total)\n", "café.py": "menu = []\n"})

        changed = changed_lines(Change(self.checkout, base, "a change", "Count", ""))

        self.assertEqual(changed.hunks, {"café.py": (Lines(1, 1),), "cart/shop.py": (Lines(2, 2),)}, "a deleted line has none")


if __name__ == "__main__":
    unittest.main()
