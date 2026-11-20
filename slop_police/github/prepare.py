"""What the review action reads before it installs a harness: the configuration and the harness that applies.

It prints them as `name=value` lines for `$GITHUB_OUTPUT`.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from slop_police.config import load_config
from slop_police.harness import Auth
from slop_police.harnesses import HarnessChoice, HarnessName

REVIEW_FOLDER = ".review"

CODEX_PLAN = (
    'Codex with auth = "plan" is not supported in GitHub Actions: its ChatGPT login lives in an auth.json '
    "that every job would have to write back to the secret store, and OpenAI advises against it for public "
    'repositories. Use auth = "api" with the codex-api-key input, or the claude harness.'
)


class NotReady(Exception):
    """Why the review cannot start, in words that say what to do."""


def review_folder_on_base(checkout: Path, base: str, into: Path) -> Path:
    """The `.review` folder as the base commit has it, copied to `into`, so that a pull request cannot change its own lenses."""
    if not _has_commit(checkout, base):
        raise NotReady(f"The checkout has no commit {base}. Check it out with `fetch-depth: 0`.")
    listed = _git(checkout, "ls-tree", "-r", "-z", "--name-only", base, "--", REVIEW_FOLDER)
    paths = [Path(path.decode()) for path in listed.split(b"\0") if path]
    if Path(REVIEW_FOLDER, "config.toml") not in paths:
        raise NotReady(
            f"The base commit {base} has no {REVIEW_FOLDER}/config.toml. "
            f"Add a {REVIEW_FOLDER} folder to the base branch, or name another folder with the `config` input."
        )
    for path in paths:
        copy = into / path.relative_to(REVIEW_FOLDER)
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(_git(checkout, "show", f"{base}:{path}"))
    return into


def named_review_folder(folder: Path) -> Path:
    if not (folder / "config.toml").is_file():
        raise NotReady(f"The `config` input names {folder}, which has no config.toml.")
    return folder.resolve()


def harness_in_actions(config_folder: Path, name: HarnessName | None, auth: Auth | None) -> HarnessChoice:
    choice = load_config(config_folder).harness.overridden(name, auth, model=None, effort=None)
    if choice.name is HarnessName.CODEX and choice.auth is Auth.PLAN:
        raise NotReady(CODEX_PLAN)
    return choice


def _has_commit(checkout: Path, base: str) -> bool:
    found = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"], cwd=checkout, capture_output=True)
    return found.returncode == 0


def _git(checkout: Path, *arguments: str) -> bytes:
    return subprocess.run(["git", *arguments], cwd=checkout, check=True, capture_output=True).stdout


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="slop_police.github.prepare")
    parser.add_argument("--repo", type=Path, required=True, help="the checkout to review")
    parser.add_argument("--base", required=True)
    parser.add_argument("--into", type=Path, required=True, help="where to copy the base commit's review folder")
    parser.add_argument("--config", type=Path, help="a review folder to use instead of the base commit's")
    parser.add_argument("--harness", type=HarnessName)
    parser.add_argument("--auth", type=Auth)
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    try:
        if arguments.config:
            folder = named_review_folder(arguments.config)
        else:
            folder = review_folder_on_base(arguments.repo, arguments.base, arguments.into)
        choice = harness_in_actions(folder, arguments.harness, arguments.auth)
    except NotReady as reason:
        sys.exit(f"slop-police: {reason}")
    print(f"config={folder}")
    print(f"harness={choice.name.value}")
    print(f"auth={choice.auth.value}")


if __name__ == "__main__":
    main()
