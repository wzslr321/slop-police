import tomllib
from dataclasses import dataclass
from pathlib import Path

from slop_police.harness import Auth
from slop_police.harnesses import HarnessChoice, HarnessName


@dataclass(frozen=True)
class Config:
    """How one repository wants to be reviewed: its `.review` folder."""

    directory: Path
    name: str
    about: str
    rules: tuple[str, ...]
    lenses: tuple[str, ...]
    priority: str
    ignore: tuple[str, ...] = ()
    read_also: tuple[Path, ...] = ()
    harness: HarnessChoice = HarnessChoice()
    max_comments: int | None = None

    def lens(self, name: str) -> str:
        return (self.directory / "lenses" / f"{name}.md").read_text()


def load_config(directory: Path) -> Config:
    written = tomllib.loads((directory / "config.toml").read_text())
    return Config(
        directory=directory,
        name=written["name"],
        about=written["about"],
        rules=tuple(written["rules"]),
        lenses=tuple(written["lenses"]),
        priority=written["priority"].strip(),
        ignore=tuple(written.get("ignore", ())),
        read_also=tuple(Path(path).expanduser() for path in written.get("read_also", ())),
        harness=_harness_choice(written.get("harness", {})),
        max_comments=written.get("max_comments"),
    )


def _harness_choice(table: dict) -> HarnessChoice:
    return HarnessChoice(
        name=HarnessName(table.get("name", HarnessName.CLAUDE.value)),
        auth=Auth(table.get("auth", Auth.PLAN.value)),
        model=table.get("model"),
    )
