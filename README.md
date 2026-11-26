# slop-police

Reviews a branch before its pull request and returns comments a maintainer would write, in the order to fix them.

It knows nothing about what good code is. That comes from the repository under review: its rule files and its lenses.

## How a review runs

1. Each lens looks for one kind of problem in the change and lists candidates.
2. A second session per lens opens the code and tries to prove each candidate wrong.
3. An editor merges what the lenses found twice and orders the comments by what to fix first.

Every step is its own session of a coding harness with read-only tools, so the lenses do not influence each other. Five lenses make eleven sessions.

A review is about what the pull request brings in. On the lines it adds or rewrites, the check drops a problem the base commit already has there. In code it leaves as it is, a problem stays only when a change of the pull request leaves that code wrong, such as a doc that still names a removed function.

## Run it

```sh
uv tool install git+https://github.com/wzslr321/slop-police
slop-police --base origin/main
```

Run it in the checkout to review, on a committed branch: the reviewer reads the files as they are, and the change ends at the head commit, so tracked files that differ from it stop the review. It prints the comments and, with `--json <file>`, also saves the candidates it dropped and why. From a clone, `bin/slop-police` does the same without installing.

## Harness and who pays

The sessions run in Claude Code or in Codex. `auth` says who pays, and slop-police holds the CLI to it:

| `name` | `auth = "plan"` | `auth = "api"` |
|---|---|---|
| `claude` | The subscription `claude` is signed in to, or `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`. | `ANTHROPIC_API_KEY` |
| `codex` | The ChatGPT login of `codex`. | `CODEX_API_KEY` |

Both CLIs take an API key they find in the environment over the subscription, without asking, and Claude Code takes more variables over both, such as `ANTHROPIC_AUTH_TOKEN` or `CLAUDE_CODE_USE_BEDROCK`. So slop-police passes the CLI only the variable of the chosen `auth` and refuses to start when an `api` key is missing. Before the first session it asks `claude auth status` how Claude Code would sign in, and stops when someone else would pay.

`--harness`, `--auth`, `--model` and `--effort` on the command line replace what the configuration names, for one run.

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
| `read_also` | Folders outside the checkout the reviewer may read. One that does not exist gets a warning. |
| `max_comments` | Keep only the first comments after the editor. Without it, all. |
| `[harness]` `name`, `auth`, `model`, `effort` | Which harness runs the sessions, who pays, the model, and how hard it reasons: `low`, `medium`, `high` or `xhigh`, the levels both CLIs take. Without them: `claude`, `plan`, the CLI's own model and effort. |

A lens is a prompt for one kind of problem: the rule it rests on, what to look for, and the exceptions. A lens may also be about the pull request's description: its comments quote a sentence of the description instead of naming a place in the code, and on GitHub they go into the review body.

## In GitHub Actions

Two composite actions run in two jobs. The root action reviews the pull request and uploads the comments as an artifact. `post` puts them on the pull request as one review that only comments. The job that holds the model's credential cannot write to the pull request, and the job that writes holds no credential.

The review reads `.review` as the base commit has it, so a pull request cannot change the lenses that review it. The harness, who pays, the model and the effort come from `[harness]` there, so each repository chooses its own. While the base has no `.review`, the `config` input names another folder.

A comment marks the lines of code it is about. On lines the diff shows it becomes an inline comment; GitHub takes a range only inside one hunk, so a range that runs past its hunk is cut to it. Any other comment goes into the review body under its path and lines, and one on code the change leaves wrong under "Left behind by this change", also when the diff shows its lines.

A maintainer starts a review with the label `slop-police`:

```yaml
name: slop-police

on:
  pull_request:
    types: [labeled, unlabeled]

jobs:
  review:
    if: github.event.action == 'labeled' && github.event.label.name == 'slop-police'
    concurrency:
      group: slop-police-${{ github.event.pull_request.number }}
      cancel-in-progress: true
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Check out the pull request
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          fetch-depth: 0
          persist-credentials: false

      - name: Review
        uses: wzslr321/slop-police@v1
        with:
          base: ${{ github.event.pull_request.base.sha }}
          codex-api-key: ${{ secrets.CODEX_API_KEY }}

  stop:
    if: github.event.action == 'unlabeled' && github.event.label.name == 'slop-police'
    concurrency:
      group: slop-police-${{ github.event.pull_request.number }}
      cancel-in-progress: true
    runs-on: ubuntu-latest
    permissions: {}
    steps:
      - name: Stop the review
        run: echo "The label slop-police was removed."

  post:
    needs: review
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    steps:
      - name: Post
        uses: wzslr321/slop-police/post@v1
```

Adding the label again cancels the review that runs, and removing the label stops it: `review` and `stop` share one concurrency group per pull request, and a job that joins it cancels the one that runs. A cancelled review posts nothing. The group is on the jobs and not on the workflow, which starts on every label: a group on the workflow would cancel a review when someone adds another label.

The example passes `codex-api-key` because the `[harness]` it expects in `.review/config.toml` names `codex` with `auth = "api"`. Pass the input that matches yours.

The review action also takes `harness`, `auth`, `model`, `effort` and `parallel` in place of the configuration, `claude-code-oauth-token`, `anthropic-api-key` and `codex-api-key` for the credential the configuration needs, and `claude-code-version` and `codex-version`. It installs only the CLI that will run. Codex on a ChatGPT plan is not supported in Actions: its login would have to be written back to the secret store after every job. `post` takes `dry-run: true` to print the request instead of sending it.

### What to trust

- The reviewer reads the pull request's code and never builds it. Codex runs its commands in its read-only sandbox, which on `ubuntu-latest` can read the whole disk but cannot write or reach the network. Claude Code has no sandbox: it gets `Read`, `Grep`, `Glob` and Bash for `git diff`, `git log` and `git show`. Those Bash rules match the start of a command, so `git log --output=.git/config` can rewrite the checkout's git configuration, and a `git diff` after it runs any command that configuration names. A pull request that talks Claude Code into those two commands runs code in the job that holds the key. Codex refuses the write.
- The engine itself runs no code from the checkout. It starts with `python3 -P`, so a `slop_police` package or a `json.py` in the checkout is only a file to read. Claude Code reads no settings file, neither the branch's nor the runner's, so their hooks, permission rules, `env` and `apiKeyHelper` do not apply, and it does not load the checkout's `CLAUDE.md` either. Codex ignores the `.codex` config, hooks and rules of a project it does not trust, and a fresh runner trusts none.
- On `pull_request` the workflow file comes from the pull request's branch. Whoever can push a branch to the repository can change what runs with the secrets, so the points above guard against the code under review, not against that person.
- Pull requests from forks get no secrets on `pull_request`, so their review stops at the missing key. That is by design.
- The label is the gate: nothing runs and nothing is spent until a maintainer adds it. Removing it cancels a review that runs, and what the model has read until then is paid.
- Before a review leaves the engine, the value of every credential variable that is set (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`, `CODEX_API_KEY`, `OPENAI_API_KEY`) becomes `[redacted]` in the comments and the dropped reasons. The reviewer can read files, on Linux also `/proc/self/environ`. A secret it encodes, splits or rewrites passes the redaction.

## License

MIT
