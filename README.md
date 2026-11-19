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

## In GitHub Actions

Two composite actions run in two jobs. The root action reviews the pull request and uploads the comments as an artifact. `post` puts them on the pull request as one review that only comments. The job that holds the model's credential cannot write to the pull request, and the job that writes holds no credential.

The review reads `.review` as the base commit has it, so a pull request cannot change the lenses that review it. While the base has no `.review`, the `config` input names another folder.

A comment on a line the diff shows becomes an inline comment. Any other goes into the review body under its path and line.

slop-police is a private repository, so a consumer checks it out with a deploy key. Add the public key as a read-only deploy key of `wzslr321/slop-police`, and the private key as the secret `SLOP_POLICE_DEPLOY_KEY` of the consumer. A maintainer starts a review with the label `slop-police`:

```yaml
name: slop-police

on:
  pull_request:
    types: [labeled]

jobs:
  review:
    if: github.event.label.name == 'slop-police'
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Check out the pull request
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          fetch-depth: 0
          path: code
          persist-credentials: false

      - name: Check out slop-police
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          repository: wzslr321/slop-police
          ref: <a commit of slop-police>
          ssh-key: ${{ secrets.SLOP_POLICE_DEPLOY_KEY }}
          path: slop-police
          persist-credentials: false

      - name: Review
        uses: ./slop-police
        with:
          repo: code
          base: ${{ github.event.pull_request.base.sha }}
          claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}

  post:
    needs: review
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    steps:
      - name: Check out slop-police
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          repository: wzslr321/slop-police
          ref: <a commit of slop-police>
          ssh-key: ${{ secrets.SLOP_POLICE_DEPLOY_KEY }}
          path: slop-police
          persist-credentials: false

      - name: Post
        uses: ./slop-police/post
```

The review action also takes `harness`, `auth`, `model` and `parallel` in place of the configuration, `anthropic-api-key` and `codex-api-key` for `auth = "api"`, and `claude-code-version` and `codex-version`. It installs only the CLI that will run. Codex on a ChatGPT plan is not supported in Actions: its login would have to be written back to the secret store after every job. `post` takes `dry-run: true` to print the request instead of sending it.

### What to trust

- The reviewer reads the pull request's code with read-only tools and never builds or runs it.
- Claude Code loads `.claude/settings.json` from the checkout, so hooks and permission rules there apply in the review job. Whoever can push a branch can also change the workflow, which runs with the secrets on `pull_request`, so this gives a branch nothing it did not have.
- Pull requests from forks get no secrets on `pull_request`, so their review stops at the missing sign-in. That is by design.
- The label is the gate: nothing runs and nothing is spent until a maintainer adds it.
- Before a review leaves the engine, the value of every credential variable that is set (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`, `CODEX_API_KEY`, `OPENAI_API_KEY`) becomes `[redacted]` in the comments and the dropped reasons. The reviewer can read files, on Linux also `/proc/self/environ`. A secret it encodes, splits or rewrites passes the redaction.
