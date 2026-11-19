import argparse
from pathlib import Path

from slop_police.change import branch_change
from slop_police.config import load_config
from slop_police.process import review
from slop_police.report import as_json, as_markdown


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="slop-police", description="Review the current branch before its pull request.")
    parser.add_argument("--base", default="origin/main", help="the branch this one will merge into")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="the checkout to review")
    parser.add_argument("--config", type=Path, help="the review folder, by default .review in the checkout")
    parser.add_argument("--title", help="by default the branch name")
    parser.add_argument("--description-file", type=Path, help="by default the commit messages")
    parser.add_argument("--json", type=Path, help="also write comments, dropped candidates and cost to this file")
    parser.add_argument("--parallel", type=int, default=3, help="lenses that run at the same time")
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    checkout = arguments.repo.resolve()
    config = load_config((arguments.config or checkout / ".review").resolve())
    description = arguments.description_file.read_text() if arguments.description_file else None
    change = branch_change(checkout, arguments.base, arguments.title, description)
    result = review(change, config, arguments.parallel)
    if arguments.json:
        arguments.json.write_text(as_json(result))
    print(as_markdown(result))


if __name__ == "__main__":
    main()
