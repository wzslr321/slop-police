import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from slop_police.harness import Answer, Auth, HarnessFailed, Usage, environment_for, run_session

# `codex exec` takes a key it finds over the ChatGPT login.
API_VARIABLES = ("CODEX_API_KEY", "OPENAI_API_KEY")


@dataclass(frozen=True)
class Codex:
    auth: Auth
    model: str | None = None
    # The read-only sandbox can read the whole disk, so this needs no flag.
    read_also: tuple[Path, ...] = ()

    def login_problem(self) -> str | None:
        if self.auth is Auth.API:
            return None if os.environ.get("CODEX_API_KEY") else 'auth = "api" needs CODEX_API_KEY in the environment.'
        status = subprocess.run(
            ["codex", "login", "status"], capture_output=True, text=True, env=environment_for(self.auth, API_VARIABLES)
        )
        signed_in = "ChatGPT" in status.stdout + status.stderr
        return None if signed_in else "Codex is not signed in with ChatGPT: run `codex login`."

    def ask(self, prompt: str, schema: dict, cwd: Path, read_code: bool) -> Answer:
        with TemporaryDirectory() as scratch:
            schema_file = Path(scratch) / "schema.json"
            answer_file = Path(scratch) / "answer.json"
            nothing_to_read = Path(scratch) / "empty"
            schema_file.write_text(json.dumps(_strict(schema)))
            nothing_to_read.mkdir()
            command = self._command(schema_file, answer_file, cwd if read_code else nothing_to_read)
            completed = run_session(command, prompt, None, environment_for(self.auth, API_VARIABLES))
            events = _events(completed.stdout)
            if completed.returncode != 0 or not answer_file.exists():
                raise HarnessFailed(_failure(events) or completed.stderr[-2000:])
            return Answer(output=json.loads(answer_file.read_text()), usage=_usage(events))

    def _command(self, schema_file: Path, answer_file: Path, directory: Path) -> list[str]:
        return [
            "codex",
            "exec",
            *(["--model", self.model] if self.model else []),
            # User configuration is skipped so that no plugin or MCP server of this machine reaches the reviewer.
            "--ignore-user-config",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox", "read-only",
            "--json",
            "--output-schema", str(schema_file),
            "--output-last-message", str(answer_file),
            "--cd", str(directory),
            "-",
        ]


def _strict(schema: object) -> object:
    """The same schema with `additionalProperties: false` on every object, which Codex requires."""
    if isinstance(schema, list):
        return [_strict(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    strict = {key: _strict(value) for key, value in schema.items()}
    return {**strict, "additionalProperties": False} if schema.get("type") == "object" else strict


def _events(jsonl: str) -> list[dict]:
    return [json.loads(line) for line in jsonl.splitlines() if line.startswith("{")]


def _usage(events: list[dict]) -> Usage:
    turns = [event["usage"] for event in events if event.get("type") == "turn.completed"]
    return Usage(
        input_tokens=sum(turn["input_tokens"] for turn in turns),
        output_tokens=sum(turn["output_tokens"] for turn in turns),
        cost_usd=None,
    )


def _failure(events: list[dict]) -> str | None:
    errors = [event.get("message") or json.dumps(event) for event in events if event.get("type") in ("error", "turn.failed")]
    return errors[-1][:2000] if errors else None
