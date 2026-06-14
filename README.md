# ShipGuard

**AI-powered release risk reviewer for pull requests.**

CI tells you whether tests passed. ShipGuard helps identify whether the release
looks risky.

ShipGuard reviews local git diffs and GitHub pull requests for release-sensitive
changes, then produces a structured risk report with likely breakages, CI blind
spots, missing evidence, rollout considerations, and rollback considerations.

ShipGuard is an early-stage open-source project under active development. Its
output is advisory: it does not prove that a release is safe, replace CI,
replace security review, or replace maintainer judgment.

> **Data handling:** ShipGuard sends selected code and diff context to the
> OpenAI-compatible endpoint you configure. Do not use it with confidential
> code unless that endpoint and your token-handling process are approved for
> the data involved.

## What ShipGuard does

ShipGuard can:

- analyze the current diff in a local git repository;
- fetch and analyze a GitHub pull request;
- prioritize release-sensitive files when a PR is too large for one prompt;
- build reusable project context from the PR base commit;
- identify evidence related to API contracts, database migrations,
  configuration, dependencies, security-sensitive code, and tests;
- generate Markdown, JSON, and optional self-contained HTML reports; and
- preview or post a PR summary and conservative inline review comments.

ShipGuard reports risk signals and missing evidence. It does not deploy code,
run migrations, execute a rollback, or guarantee production behavior.

## Why it exists

Production incidents can happen even when CI is green. Tests may pass while a
change still introduces:

- backward-incompatible API or schema behavior;
- a database migration that locks, fails, or cannot be rolled back safely;
- a new environment variable that is missing from deployment configuration;
- a dependency or authentication change with a wider blast radius;
- a rollout that assumes production data looks like test data;
- missing regression, compatibility, migration, or rollback tests; or
- operational risk that is visible in the diff but outside the test suite.

ShipGuard gives maintainers a release-oriented review pass focused on those
questions.

## Key features

- **Local diff review:** Analyze a working tree without opening a PR.
- **GitHub PR review:** Fetch PR metadata and changed-file patches from a PR URL.
- **Risk-aware diff packing:** Prioritize migrations, APIs, config, deployment,
  security, dependency, business logic, and test files.
- **Project memory:** Build repository context from the PR base SHA and store it
  locally for later reviews.
- **Structured findings:** Return a readiness score, decision, risk level,
  likely breakages, and CI blind spots.
- **Release Passport artifacts:** Write Markdown and JSON reports, with optional
  self-contained HTML.
- **Maintainer-friendly comments:** Preview, create, update, and selectively
  clear ShipGuard-generated GitHub comments.
- **OpenAI-compatible endpoint support:** Use a model endpoint selected and
  operated by the user.

## Quick start

### Requirements

- Python 3.11 or newer
- Git for local repository analysis
- Network access for GitHub PR analysis and model calls
- An OpenAI-compatible model endpoint

### Install

```bash
git clone https://github.com/kapilsharma432001/ShipGuard.git
cd ShipGuard
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

On systems where `python` does not point to Python 3, use `python3` for the
virtual-environment creation command.

### Configure

ShipGuard reads configuration from environment variables. Never commit real
credentials.

```bash
export SHIPGUARD_LLM_BASE_URL="https://your-openai-compatible-endpoint/v1"
export SHIPGUARD_LLM_API_KEY="your-api-key"
export SHIPGUARD_LLM_MODEL="your-model-name"
```

GitHub authentication is optional for public PR reads and required for private
repositories, higher API limits, and posting or clearing comments:

```bash
export SHIPGUARD_GITHUB_TOKEN="your-github-token"
```

You can instead copy `.env.example` to a local `.env` file in the directory
where you run ShipGuard. `.env` and `.env.*` are ignored by git, while
`.env.example` remains tracked.

### Run

Show the available commands:

```bash
python -m shipguard --help
```

Analyze a local repository diff:

```bash
python -m shipguard analyze --repo ./sample-app
```

Analyze a GitHub pull request:

```bash
python -m shipguard analyze-pr \
  --pr-url https://github.com/OWNER/REPO/pull/NUMBER
```

## Example use cases

- Review an API change for removed fields, changed enum values, or client
  compatibility risk.
- Review a migration for backfill, locking, production-data, and rollback
  concerns.
- Check whether new environment variables are represented in deployment
  configuration.
- Surface dependency, authentication, or permission changes that deserve
  focused review.
- Identify when a risky implementation change lacks targeted tests or rollout
  evidence.
- Generate a release review artifact for a maintainer to discuss before merge.

## Current status

ShipGuard is an early-stage CLI project and is under active development.

- The package metadata currently identifies version `0.1.0`.
- The CLI supports local diffs and GitHub pull requests.
- Model-backed analysis requires a user-configured OpenAI-compatible endpoint.
- Project memory and generated reports are stored locally under `.shipguard/`.
- Unit tests cover core context, environment loading, report generation, and PR
  commenting behavior.
- There is not yet a stable configuration or output compatibility guarantee.
- Findings have not been validated as a substitute for production release
  controls and should be reviewed by a human.

Issues, design feedback, documentation improvements, tests, and focused fixes
are welcome.

## Roadmap

Near-term work focuses on analysis reliability, maintainer workflows,
integrations, evidence quality, and clearer examples. See [ROADMAP.md](ROADMAP.md)
for the directional roadmap. Roadmap items are not release commitments.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for local setup, development checks,
issue guidance, pull request expectations, and contribution ideas.

By participating, you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Do not put API keys, private repository content, exploit details, or other
sensitive data in a public issue. See [SECURITY.md](SECURITY.md) for reporting
guidance and the current private-reporting limitation.

## CLI reference

ShipGuard exposes three commands:

- `analyze`: analyze a local git repository diff;
- `analyze-pr`: analyze a GitHub pull request URL; and
- `clear-comments`: remove only ShipGuard-generated comments from a PR.

Inspect command-specific options with:

```bash
python -m shipguard analyze --help
python -m shipguard analyze-pr --help
python -m shipguard clear-comments --help
```

### Local git diff analysis

```bash
python -m shipguard analyze --repo ./sample-app
```

ShipGuard validates the path and reads the current branch, latest commit hash
when available, changed file names and extensions, `git diff --stat`, the diff
up to the configured limit, and whether the repository has uncommitted changes.

Set the local diff context limit:

```bash
python -m shipguard analyze \
  --repo ./sample-app \
  --max-diff-chars 30000
```

An invalid or non-git repository path produces an error and exit code `2`.

### GitHub PR analysis

```bash
python -m shipguard analyze-pr \
  --pr-url https://github.com/OWNER/REPO/pull/NUMBER
```

ShipGuard fetches PR metadata and changed files, packs the diff, calls the
configured model, prints a terminal report, and writes Release Passport
artifacts.

Set the PR diff context limit:

```bash
python -m shipguard analyze-pr \
  --pr-url https://github.com/OWNER/REPO/pull/NUMBER \
  --max-diff-chars 120000
```

Fetched PR context includes the title, body, state, branches, base and head
SHAs, change counts, changed file names, and available patches.

## Risk-aware diff packing

ShipGuard splits PR changes into per-file sections instead of taking only the
first characters of a large diff.

Highest-priority categories include:

- migrations and versioned database changes;
- API routes, schemas, serializers, controllers, and models;
- configuration, environment, container, and deployment files;
- authentication, authorization, permission, and token code; and
- dependency manifests and lock files.

Business logic, database models, and tests receive medium priority. Documentation
and formatting-oriented files receive lower priority.

Large file patches may include only their beginning and end. When the context
budget omits files, ShipGuard tells the model that the changed-file list is
complete but the diff evidence is partial.

## Project memory

Project memory is enabled by default for `analyze-pr`.

```bash
python -m shipguard analyze-pr \
  --pr-url https://github.com/OWNER/REPO/pull/NUMBER \
  --use-memory \
  --show-memory-summary
```

Memory is built from the PR base SHA. This keeps existing project context
separate from proposed changes in the PR.

The memory builder:

- inventories files from the base commit;
- classifies files using path, filename, extension, and content signals;
- skips binary, generated, vendor, cache, and oversized files;
- extracts deterministic signals such as API routes, database tables,
  migrations, imports, symbols, environment variables, and test frameworks;
- optionally summarizes compact file context with the configured model; and
- falls back to deterministic context if model summarization fails.

Memory is stored under:

```text
.shipguard/memory/<owner>_<repo>/
  repo_inventory.json
  files_index.json
  project_memory.json
  memory_build_report.json
  release_history.jsonl
```

Relevant options:

- `--use-memory` / `--no-memory`: enable or disable project memory;
- `--rebuild-memory`: rebuild from the PR base SHA;
- `--memory-dir .shipguard/memory`: select a memory directory; and
- `--show-memory-summary`: print build counts, warnings, and the memory path.

If GitHub returns a truncated recursive tree, ShipGuard records the warning and
attempts non-recursive subtree traversal.

## Release Passport reports

Successful PR analysis writes:

```text
.shipguard/reports/<owner>_<repo>_pr_<number>/
  release_passport.md
  analysis.json
```

Generate the optional self-contained HTML report:

```bash
python -m shipguard analyze-pr \
  --pr-url https://github.com/OWNER/REPO/pull/NUMBER \
  --use-memory \
  --show-memory-summary \
  --html
```

This also writes:

```text
.shipguard/reports/<owner>_<repo>_pr_<number>/
  release_passport.html
```

Reports can include:

- repository and PR metadata;
- readiness score, decision, and risk level;
- an executive summary;
- project memory and changed-file context;
- likely breakages and CI blind spots;
- missing evidence;
- safer rollout and rollback considerations; and
- an optional score breakdown.

The HTML report is self-contained with inline CSS and no external CDN or
JavaScript dependency. `analysis.json` contains the structured report and
artifact paths. Generated report directories are ignored by git.

## GitHub PR comments

Posting and clearing comments requires `SHIPGUARD_GITHUB_TOKEN`. ShipGuard does
not print the token.

Preview comments without posting:

```bash
python -m shipguard analyze-pr \
  --pr-url https://github.com/OWNER/REPO/pull/NUMBER \
  --use-memory \
  --html \
  --dry-run-comments
```

The preview is written to:

```text
.shipguard/reports/<owner>_<repo>_pr_<number>/pr_comment_preview.md
```

Post or update a top-level summary:

```bash
python -m shipguard analyze-pr \
  --pr-url https://github.com/OWNER/REPO/pull/NUMBER \
  --use-memory \
  --html \
  --post-comment
```

ShipGuard marks its summary with `<!-- shipguard:summary -->`. If a marked
summary already exists, ShipGuard updates it instead of creating another one.

Post conservative inline comments:

```bash
python -m shipguard analyze-pr \
  --pr-url https://github.com/OWNER/REPO/pull/NUMBER \
  --use-memory \
  --html \
  --post-comment \
  --post-inline-comments \
  --max-inline-comments 5
```

Inline comments use `<!-- shipguard:inline -->` and are limited to changed lines
where ShipGuard can map a finding to diff evidence. Examples include a required
column without backfill evidence, a risky rollback, an API contract change, or
a new environment variable without configuration evidence.

The default GitHub review event is non-blocking `COMMENT`. To request changes:

```bash
python -m shipguard analyze-pr \
  --pr-url https://github.com/OWNER/REPO/pull/NUMBER \
  --post-inline-comments \
  --request-changes
```

Clear marked ShipGuard comments:

```bash
python -m shipguard clear-comments \
  --pr-url https://github.com/OWNER/REPO/pull/NUMBER
```

The clear command deletes only comments containing ShipGuard's summary or
inline markers. It does not delete unmarked comments.

## Synthetic demo

Create a small synthetic Claims API repository with intentional release risks:

```bash
python scripts/create_demo_repo.py
```

The script creates `sample-app/` as a nested git repository, commits a baseline,
and leaves risky changes uncommitted. The demo contains synthetic API,
migration, test, container, and environment configuration examples. It does not
contain real company or client code.

Analyze it with:

```bash
python -m shipguard analyze --repo ./sample-app
```

## Repository structure

```text
shipguard/
  __main__.py          # python -m shipguard entrypoint
  cli.py               # Typer commands
  env_loader.py        # local .env loading
  git_analyzer.py      # local git diff collection
  github_client.py     # GitHub PR and repository API client
  pr_url_parser.py     # GitHub PR URL parser
  llm_client.py        # OpenAI-compatible model client
  models.py            # Pydantic models and enums
  context_builder.py   # project memory and context engine
  project_memory.py    # local JSON memory storage
  report_generator.py  # Release Passport artifacts
  pr_commenter.py      # PR summary and inline comment handling
scripts/
  create_demo_repo.py  # synthetic sample-app generator
tests/
  test_env_loader.py
  test_context_builder.py
  test_report_generator.py
  test_pr_commenter.py
```

## Development checks

Run the unit tests:

```bash
python -m unittest discover -s tests
```

Run a compile check:

```bash
python -m compileall shipguard scripts tests
```

Check the CLI entry points:

```bash
python -m shipguard --help
python -m shipguard analyze --help
python -m shipguard analyze-pr --help
python -m shipguard clear-comments --help
```

GitHub Actions runs these checks on pull requests and pushes to `main` using
Python 3.11 and 3.12.

No project-wide linting or formatting command is currently configured.

## Troubleshooting

**Missing model configuration**

Set `SHIPGUARD_LLM_BASE_URL`, `SHIPGUARD_LLM_API_KEY`, and
`SHIPGUARD_LLM_MODEL`.

**Private repository or GitHub API rate limit**

Set `SHIPGUARD_GITHUB_TOKEN` with access to the repository. Posting and clearing
comments also requires a token with the relevant repository permissions.

**Invalid PR URL**

Use the standard form:

```text
https://github.com/OWNER/REPO/pull/NUMBER
```

**Project memory does not include a newly added file**

Memory represents the PR base SHA. New files remain visible in the PR changed
file list and diff, but they do not enter base-branch memory until a later
review after merge and rebuild.

**Expected report files are missing**

`release_passport.md` and `analysis.json` are written after successful
model-backed PR analysis. `release_passport.html` is written only with
`--html`.

## License

ShipGuard is available under the [MIT License](LICENSE).
