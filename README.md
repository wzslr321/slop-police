# slop-police

Reviews a branch before its pull request and returns comments a maintainer would write, in the order to fix them.

It knows nothing about what good code is. That comes from the repository under review: its rule files and its lenses.

## How a review runs

1. Each lens looks for one kind of problem in the change and lists candidates.
2. A second session per lens opens the code and tries to prove each candidate wrong.
3. An editor merges what the lenses found twice and orders the comments by what to fix first.

Every step is its own session of a coding harness with read-only tools, so the lenses do not influence each other. Five lenses make eleven sessions.

## Run it

```sh
uv tool install git+https://github.com/wzslr321/slop-police
slop-police --base origin/main
```

Run it in the checkout to review, on a committed branch. It prints the comments and, with `--json <file>`, also saves the candidates it dropped and why. From a clone, `bin/slop-police` does the same without installing.

## Harness and who pays

The sessions run in Claude Code or in Codex. `auth` says who pays, and slop-police holds the CLI to it:

| `name` | `auth = "plan"` | `auth = "api"` |
|---|---|---|
| `claude` | The subscription `claude` is signed in to, or `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`. | `ANTHROPIC_API_KEY` |
| `codex` | The ChatGPT login of `codex`. | `CODEX_API_KEY` |

Both CLIs take an API key they find in the environment over the subscription, without asking. So with `plan` slop-police starts them without the key variables, and with `api` it refuses to start when the key is missing.

`--harness`, `--auth` and `--model` on the command line replace what the configuration names, for one run.

Claude Code reports what the tokens would cost through the API, also on a subscription. Codex reports tokens only.

## What a repository provides

A `.review` folder (or another one, with `--config`):

```
.review/
  config.toml
  lenses/
    <lens>.md
```

`config.toml`:

| Key | Meaning |
|---|---|
| `name`, `about` | How the prompts name the repository. |
| `rules` | Files the reviewer reads before it judges. |
| `lenses` | The lenses to run, by file name. |
| `priority` | The order in which the editor puts the comments, in words. |
| `ignore` | Patterns of changed files the reviewer does not list, such as generated code. |
| `read_also` | Folders outside the checkout the reviewer may read. |
| `max_comments` | Keep only the first comments after the editor. Without it, all. |
| `[harness]` `name`, `auth`, `model` | Which harness runs the sessions, who pays, and the model. Without them: `claude`, `plan`, the CLI's own model. |

A lens is a prompt for one kind of problem: the rule it rests on, what to look for, and the exceptions.
