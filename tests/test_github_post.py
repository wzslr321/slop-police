"""Which comments GitHub can take on a line of the diff, and the review that carries them."""

import unittest

from slop_police.comments import Comment
from slop_police.github.diff import right_side
from slop_police.github.post import PullRequest, ReviewRequest, placed

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


class RightSideTest(unittest.TestCase):
    def test_added_and_context_lines_of_every_file_that_stays(self) -> None:
        self.assertEqual(
            right_side(DIFF).lines,
            {"shop.py": frozenset({1, 2, 3, 4, 11, 12, 13}), "new name.py": frozenset({5})},
        )


class ReviewRequestTest(unittest.TestCase):
    def setUp(self) -> None:
        on_added_line = Comment("shop.py", 3, "Name the count.")
        on_context_line = Comment("shop.py", 13, "Say when it is done.")
        outside_the_diff = Comment("shop.py", 30, "This was already wrong.")
        whole_file = Comment("gone.py", None, "Who used this?")
        whole_change = Comment(None, None, "Split the change.")
        comments = [on_added_line, outside_the_diff, on_context_line, whole_file, whole_change]
        self.request = ReviewRequest(PullRequest("owner/shop", 7), "abc123", placed(comments, right_side(DIFF)))

    def test_lines_the_diff_shows_get_inline_comments_and_the_rest_go_into_the_body(self) -> None:
        payload = self.request.payload()

        self.assertEqual(
            payload["comments"],
            [
                {"path": "shop.py", "line": 3, "side": "RIGHT", "body": "Name the count."},
                {"path": "shop.py", "line": 13, "side": "RIGHT", "body": "Say when it is done."},
            ],
        )
        self.assertEqual(
            payload["body"],
            "slop-police: 5 comments, 3 of them not on a line of the diff:\n\n"
            "**`shop.py:30`**\n\nThis was already wrong.\n\n"
            "**`gone.py`**\n\nWho used this?\n\n"
            "**The whole change**\n\nSplit the change.",
        )

    def test_the_review_only_comments_on_the_reviewed_commit(self) -> None:
        payload = self.request.payload()

        self.assertEqual((payload["event"], payload["commit_id"]), ("COMMENT", "abc123"))
        self.assertEqual(self.request.pull_request.reviews_endpoint, "repos/owner/shop/pulls/7/reviews")


if __name__ == "__main__":
    unittest.main()
