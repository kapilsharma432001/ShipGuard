# ShipGuard

ShipGuard is an AI Release Risk Reasoner for pull requests and local release
diffs. CI/CD tells you if the pipeline passed. ShipGuard tells you if the
release is safe.

ShipGuard reads real change context, sends it to an OpenAI-compatible LLM, and
returns a structured release risk report with a readiness score, decision, risk
level, likely breakages, and CI blind spots. For GitHub PRs it can also build
repository-level project memory and generate a Release Passport in Markdown,
HTML, and JSON.

## Capabilities

- Local git diff analysis with `python -m shipguard analyze --repo ./sample-app`
- GitHub PR URL analysis with `python -m shipguard analyze-pr --pr-url <PR_URL>`
- OpenAI-compatible LLM integration for Tiger AI Gateway or any compatible
  endpoint
- Smart PR diff packing that prioritizes risky files before lower-risk files
- Generic repository memory built from the PR base SHA
- Deterministic project signal extraction for env vars, API routes, DB tables,
  classes/functions, imports, migration operations, dependencies, security
  signals, and test framework hints
- Release Passport report generation:
  - `release_passport.md`
  - `release_passport.html` when `--html` is passed
  - `analysis.json`

## Requirements

- Python 3.11+
- Git for local repository analysis
- Network access for GitHub PR analysis and LLM calls
- A configured OpenAI-compatible LLM endpoint

Install the project in editable mode:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## Configuration

ShipGuard uses environment variables only. Do not hardcode secrets.

Required for all LLM-backed analysis:

```bash
export SHIPGUARD_LLM_BASE_URL="https://your-openai-compatible-endpoint/v1"
export SHIPGUARD_LLM_API_KEY="your-api-key"
export SHIPGUARD_LLM_MODEL="your-model-name"
```

Optional for GitHub PR analysis:

```bash
export SHIPGUARD_GITHUB_TOKEN="your-github-token"
```

Public repositories can work without `SHIPGUARD_GITHUB_TOKEN`, but private
repositories and higher rate limits require it.

You can also create a local `.env` file in the directory where you run
ShipGuard:

```bash
SHIPGUARD_LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
SHIPGUARD_LLM_API_KEY=your-api-key
SHIPGUARD_LLM_MODEL=your-model-name
SHIPGUARD_GITHUB_TOKEN=your-github-token
```

Use `.env.example` as the template. `.env` and `.env.*` are ignored by git, and
`.env.example` is intentionally allowed.

## CLI Overview

Show available commands:

```bash
python -m shipguard --help
```

Commands:

- `analyze`: analyze a local git repository diff
- `analyze-pr`: analyze a GitHub pull request URL

## Local Git Diff Analysis

Run:

```bash
python -m shipguard analyze --repo ./sample-app
```

ShipGuard validates that the path exists and is a git repository, then reads:

- current branch
- latest commit hash when available
- changed file names
- changed file extensions
- `git diff --stat`
- full git diff up to the configured limit
- whether the repo has uncommitted changes

Default local diff context limit:

```bash
python -m shipguard analyze --repo ./sample-app --max-diff-chars 30000
```

If the repository path does not exist or is not a git repository, ShipGuard
prints a clear error and exits with code `2`.

## Synthetic Demo Repository

Create a small fake Claims API repository with intentional release risks:

```bash
python scripts/create_demo_repo.py
```

This creates `sample-app/` as a nested git repository, commits a safe baseline,
then leaves risky changes uncommitted so ShipGuard can analyze a real diff.

The synthetic demo includes fake FastAPI-style code, fake Alembic-style
migrations, tests, `docker-compose.yml`, and `.env.example`. It intentionally
contains risks such as enum changes, required field changes, unsafe `NOT NULL`
migration behavior, missing env config, missing regression tests, and rollback
migration problems. It does not contain real company or client code.

Analyze it:

```bash
python -m shipguard analyze --repo ./sample-app
```

## GitHub PR Analysis

Run:

```bash
python -m shipguard analyze-pr --pr-url https://github.com/OWNER/REPO/pull/NUMBER
```

ShipGuard parses the PR URL, fetches PR metadata, fetches changed files, packs
the PR diff, calls the configured LLM, prints the terminal report, and writes
Release Passport artifacts.

Fetched PR metadata includes:

- title
- body
- state
- base branch
- head branch
- base SHA
- head SHA
- changed files count
- additions
- deletions
- changed file names
- PR diff

Default PR diff context limit:

```bash
python -m shipguard analyze-pr \
  --pr-url https://github.com/OWNER/REPO/pull/NUMBER \
  --max-diff-chars 120000
```

## Smart PR Diff Packing

PR analysis does not blindly take the first N characters of the diff. ShipGuard
splits the PR diff into per-file sections and prioritizes risky files first.

Highest priority:

- migrations, Alembic, versioned migration files
- API routes, schemas, serializers, controllers, Pydantic models
- config, settings, env, Docker, deployment files
- auth, security, permission, token files
- dependency files such as `pyproject.toml`, `requirements.txt`,
  `package.json`, and lock files

Medium priority:

- service and business logic files
- database model files
- tests

Low priority:

- README, docs, and formatting-oriented files

If a file diff is too large, ShipGuard includes the beginning and end of that
file diff with a truncation marker. If files are omitted because of the context
budget, the prompt tells the LLM that the changed file list is complete and
that omitted risky files should be treated as missing evidence requiring manual
review.

## Project Memory

Project memory is enabled by default for `analyze-pr`.

```bash
python -m shipguard analyze-pr \
  --pr-url https://github.com/OWNER/REPO/pull/NUMBER \
  --use-memory \
  --show-memory-summary
```

Memory is built from the PR base SHA, not the PR head. This is intentional:
project memory represents the existing base-branch project context, while the
PR diff represents proposed changes. Files newly added in the PR appear in the
changed-file list and PR diff, not in base-branch memory until after they are
merged and memory is rebuilt for a later PR.

Memory behavior:

- fetches repository metadata
- fetches the full repository file tree from the PR base SHA
- records an inventory entry for every discovered file
- classifies every file with generic path, filename, extension, and content
  signals
- fetches content only for eligible text, code, and config files
- skips binary, generated, vendor, cache, and oversized files safely
- extracts deterministic project signals
- summarizes compact file contexts with the LLM in batches when available
- falls back to deterministic memory if LLM project summarization fails

Memory storage:

```text
.shipguard/memory/<owner>_<repo>/
  repo_inventory.json
  files_index.json
  project_memory.json
  memory_build_report.json
  release_history.jsonl
```

`repo_inventory.json` includes every discovered file. `files_index.json`
includes only fetched and analyzed text/code/config files. `release_history.jsonl`
is appended after successful PR analysis.

Useful memory flags:

- `--use-memory / --no-memory`: enable or disable project memory
- `--rebuild-memory`: rebuild memory from the PR base SHA
- `--memory-dir .shipguard/memory`: change the local memory directory
- `--show-memory-summary`: print discovered/fetched/skipped counts, tree
  truncation status, summary source, known category counts, and memory path

If GitHub reports a truncated recursive tree response, ShipGuard records the
warning and falls back to non-recursive subtree traversal when possible.

## Release Passport Reports

PR analysis always generates:

```text
.shipguard/reports/<owner>_<repo>_pr_<number>/
  release_passport.md
  analysis.json
```

Generate the self-contained HTML dashboard with `--html`:

```bash
python -m shipguard analyze-pr \
  --pr-url https://github.com/OWNER/REPO/pull/NUMBER \
  --use-memory \
  --show-memory-summary \
  --html
```

This also creates:

```text
.shipguard/reports/<owner>_<repo>_pr_<number>/
  release_passport.html
```

The Markdown report includes:

- ShipGuard Release Passport
- repository and PR details
- generated timestamp
- release readiness score
- decision
- risk level
- executive summary
- project memory summary
- changed files
- what may break
- what CI may miss
- missing evidence
- safer rollout plan
- rollback plan
- score breakdown if available
- appendix with memory and diff context summary

The HTML report is self-contained: no external CDN, no React, no JavaScript, and
inline CSS only. It opens directly in a browser and includes a modern dashboard
layout with:

- large hero section
- tagline
- score card
- decision badge
- risk badge
- summary metrics
- risk cards
- CI blind spot checklist
- project memory card
- changed files table
- safer rollout plan
- rollback plan
- generated timestamp footer

`analysis.json` stores the structured report object, including:

- PR metadata
- `ReleaseRiskReport`
- project memory summary if available
- changed files with categories and diff evidence
- missing evidence
- safer rollout plan
- rollback plan
- generated artifact paths

`.shipguard/reports/` is ignored by git.

## Terminal Output

The CLI still prints the text report:

- Release Readiness Score
- Decision
- Risk Level
- What may break
- What CI may miss

For PR analysis it also prints generated artifact paths:

```text
Generated artifacts:
- .shipguard/reports/OWNER_REPO_pr_NUMBER/release_passport.md
- .shipguard/reports/OWNER_REPO_pr_NUMBER/release_passport.html
- .shipguard/reports/OWNER_REPO_pr_NUMBER/analysis.json
```

The HTML path is printed only when `--html` is used.

## Example Acceptance Command

```bash
python -m shipguard analyze-pr \
  --pr-url https://github.com/kapilsharma432001/ShipGuard/pull/6 \
  --use-memory \
  --show-memory-summary \
  --html
```

Expected result:

- terminal release risk summary is printed
- memory summary is printed
- Markdown report is created
- HTML report is created
- JSON analysis artifact is created

## Repository Structure

```text
shipguard/
  __main__.py          # python -m shipguard entrypoint
  cli.py               # Typer commands
  env_loader.py        # local .env loading
  git_analyzer.py      # local git diff collection
  github_client.py     # GitHub PR and repository API client
  pr_url_parser.py     # GitHub PR URL parser
  llm_client.py        # OpenAI-compatible LLM client
  models.py            # Pydantic models and enums
  context_builder.py   # project memory/context engine
  project_memory.py    # local JSON memory storage
  report_generator.py  # Release Passport artifacts
scripts/
  create_demo_repo.py  # synthetic sample-app generator
tests/
  test_env_loader.py
  test_context_builder.py
  test_report_generator.py
```

## Development Checks

Run compile checks:

```bash
python -m compileall shipguard scripts tests
```

Run tests:

```bash
python -m unittest discover -s tests
```

Check command help:

```bash
python -m shipguard --help
python -m shipguard analyze --help
python -m shipguard analyze-pr --help
```

## Troubleshooting

Missing LLM configuration:

```text
Configuration error: missing required environment variable(s)...
```

Set:

- `SHIPGUARD_LLM_BASE_URL`
- `SHIPGUARD_LLM_API_KEY`
- `SHIPGUARD_LLM_MODEL`

Private repository or GitHub rate limit:

```text
GitHub API request failed with HTTP 401/403/404...
```

Set `SHIPGUARD_GITHUB_TOKEN` with access to the repository.

Invalid PR URL:

```text
Invalid PR URL: ...
```

Use a standard GitHub PR URL:

```text
https://github.com/OWNER/REPO/pull/NUMBER
```

Missing local repo path:

```text
Repository path does not exist: ...
```

The `analyze` command exits with code `2` for invalid local repo input.

Unexpected missing files in memory:

Project memory is built from the PR base SHA. Files added by the PR will be in
the PR changed-file list and diff, but not in `files_index.json` until they
exist on the base branch and memory is rebuilt.

Report files not appearing:

- `release_passport.md` and `analysis.json` are generated for PR analysis after
  a successful LLM analysis.
- `release_passport.html` is generated only when `--html` is passed.
- Report files are written under `.shipguard/reports/`.

## Security Notes

- Do not commit `.env` or API keys.
- ShipGuard does not print GitHub or LLM tokens.
- Local memory stores project metadata, extracted env var names, route names,
  table names, release risks, and release history. Store `.shipguard/memory/`
  and `.shipguard/reports/` according to your internal data handling policy.
