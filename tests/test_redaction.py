import unittest

from slop_police.comments import Comment, Dropped
from slop_police.harness import Usage
from slop_police.process import Review
from slop_police.redaction import Redaction

ENVIRONMENT = {
    "CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat01-plan",
    "ANTHROPIC_API_KEY": "",
    "HOME": "/home/runner",
}


class RedactionTest(unittest.TestCase):
    def test_a_set_credential_leaves_the_review_nowhere(self) -> None:
        leaking = Review(
            comments=[Comment("sk-ant-oat01-plan.py", 3, "The environment holds sk-ant-oat01-plan.")],
            dropped=[Dropped(Comment(None, None, "sk-ant-oat01-plan"), "read from /proc/self/environ: sk-ant-oat01-plan")],
            usage=Usage(),
            seconds=1.0,
        )

        redacted = Redaction.of(ENVIRONMENT).review(leaking)

        self.assertEqual(redacted.comments, [Comment("[redacted].py", 3, "The environment holds [redacted].")])
        self.assertEqual(redacted.dropped, [Dropped(Comment(None, None, "[redacted]"), "read from /proc/self/environ: [redacted]")])

    def test_variables_that_hold_no_credential_are_left_alone(self) -> None:
        self.assertEqual(Redaction.of(ENVIRONMENT).text("HOME is /home/runner"), "HOME is /home/runner")


if __name__ == "__main__":
    unittest.main()
