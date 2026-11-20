"""Which comments GitHub can take on a line of the diff, and the review that carries them."""

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from slop_police.comments import Comment, Lines
from slop_police.github.diff import right_side
from slop_police.github.post import PullRequest, ReviewRequest, _send, placed, right_side_of

DIFF = """\
diff --git a/shop.py b/shop.py
index 1111111..2222222 100644
--- a/shop.py
+++ b/shop.py
@@ -1,3 +1,4 @@
 import json
-total = 0
+total = 1
+count = 0
 print(total)
@@ -10,2 +11,3 @@ def pay():
     pass
+++ b/not_a_file.py
     done
diff --git a/old name.py b/new name.py
similarity index 80%
rename from old name.py
rename to new name.py
--- a/old name.py\t
+++ b/new name.py\t
@@ -5 +5 @@
-a = 1
+a = 2
\\ No newline at end of file
diff --git a/gone.py b/gone.py
deleted file mode 100644
index 3333333..0000000
--- a/gone.py
+++ /dev/null
@@ -1,2 +0,0 @@
-x = 1
-y = 2
"""

LATIN_1_DIFF = """\
diff --git a/menu.txt b/menu.txt
index 1111111..2222222 100644
--- a/menu.txt
+++ b/menu.txt
@@ -1 +1,3 @@
 soup
+crème brûlée
+tea
"""


class RightSideTest(unittest.TestCase):
    def test_added_and_context_lines_of_every_file_that_stays_by_hunk(self) -> None:
        self.assertEqual(
            right_side(DIFF).hunks,
            {"shop.py": (Lines(1, 4), Lines(11, 13)), "new name.py": (Lines(5, 5),)},
        )

    def test_a_file_in_latin_1_does_not_stop_the_posting(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        diff_file = Path(folder.name, "change.diff")
        diff_file.write_bytes(LATIN_1_DIFF.encode("latin-1"))

        self.assertEqual(right_side_of(diff_file).hunks, {"menu.txt": (Lines(1, 3),)})


class ReviewRequestTest(unittest.TestCase):
    def setUp(self) -> None:
        one_line = Comment("shop.py", 3, "Name the count.")
        in_a_hunk = Comment("shop.py", 2, "Keep the totals together.", end_line=4)
        past_a_hunk = Comment("shop.py", 12, "Say when it is done.", end_line=20)
        outside_the_diff = Comment("shop.py", 30, "This was already wrong.", end_line=32)
        whole_file = Comment("gone.py", None, "Who used this?")
        description = Comment(None, None, "Say what the change does.")
        more_description = Comment(None, None, "Say how it was checked.")
        comments = [one_line, description, outside_the_diff, in_a_hunk, past_a_hunk, whole_file, more_description]
        self.request = ReviewRequest(PullRequest("owner/shop", 7), "abc123", placed(comments, right_side(DIFF)))

    def test_lines_the_diff_shows_get_inline_comments_and_the_rest_go_into_the_body(self) -> None:
        payload = self.request.payload()

        self.assertEqual(
            payload["comments"],
            [
                {"path": "shop.py", "line": 3, "side": "RIGHT", "body": "Name the count."},
                {"path": "shop.py", "line": 4, "side": "RIGHT", "start_line": 2, "start_side": "RIGHT", "body": "Keep the totals together."},
                {"path": "shop.py", "line": 13, "side": "RIGHT", "start_line": 12, "start_side": "RIGHT", "body": "Say when it is done."},
            ],
            "a range past the end of its hunk is cut to the hunk",
        )
        self.assertEqual(
            payload["body"],
            "slop-police: 7 comments, 4 of them not on a line of the diff:\n\n"
            "**`shop.py:30-32`**\n\nThis was already wrong.\n\n"
            "**`gone.py`**\n\nWho used this?\n\n"
            "**The description**\n\nSay what the change does.\n\nSay how it was checked.",
        )

    def test_the_review_only_comments_on_the_reviewed_commit(self) -> None:
        payload = self.request.payload()

        self.assertEqual((payload["event"], payload["commit_id"]), ("COMMENT", "abc123"))
        self.assertEqual(self.request.pull_request.reviews_endpoint, "repos/owner/shop/pulls/7/reviews")

    def test_a_review_github_created_before_a_server_error_counts_as_posted(self) -> None:
        body = self.request.payload()["body"]
        now = datetime.now(timezone.utc).isoformat()
        earlier = {"commit_id": "abc123", "body": body, "submitted_at": "2026-01-01T10:00:00Z", "html_url": "earlier"}
        created = {"commit_id": "abc123", "body": body, "submitted_at": now, "html_url": "created"}
        output = io.StringIO()

        with TemporaryDirectory() as folder, redirect_stdout(output), redirect_stderr(io.StringIO()):
            _script_gh(Path(folder), reviews=[[earlier, created]])
            with patch.dict(os.environ, {"PATH": f"{folder}{os.pathsep}{os.environ['PATH']}"}):
                _send(self.request)

        self.assertIn("the review is on the pull request: created", output.getvalue())


def _script_gh(folder: Path, reviews: list[list[dict]]) -> None:
    """A `gh` that answers the review with HTTP 502 and lists `reviews` as pages."""
    (folder / "reviews.json").write_text(json.dumps(reviews))
    gh = folder / "gh"
    gh.write_text(
        f"#!{sys.executable}\n"
        "import pathlib, sys\n"
        "if '--method' in sys.argv:\n"
        "    sys.stdin.read()\n"
        "    sys.exit('gh: Server Error (HTTP 502)')\n"
        "print((pathlib.Path(sys.argv[0]).parent / 'reviews.json').read_text())\n"
    )
    gh.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
