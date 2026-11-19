"""The engine runs its own code, never modules of the checkout it reviews."""

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ENGINE_COMMAND = Path(__file__).resolve().parent.parent / "bin" / "slop-police"
PLANTED = "raise RuntimeError('a module of the checkout ran')\n"


class EngineCodeTest(unittest.TestCase):
    def test_a_checkout_cannot_replace_the_engine_or_the_standard_library(self) -> None:
        with TemporaryDirectory() as folder:
            checkout = Path(folder)
            (checkout / "slop_police").mkdir()
            for module in ("slop_police/__init__.py", "slop_police/__main__.py", "json.py"):
                (checkout / module).write_text(PLANTED)

            started = subprocess.run([ENGINE_COMMAND, "--help"], cwd=checkout, capture_output=True, text=True)

        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertIn("usage: slop-police", started.stdout)


if __name__ == "__main__":
    unittest.main()
