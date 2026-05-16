# ShipGuard

ShipGuard is an AI Release Risk Reasoner. This repository currently contains the
day-0 Python CLI scaffold with a real OpenAI-compatible LLM integration.

## Setup

Create a virtual environment and install the project:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Configure the LLM through environment variables:

```bash
export SHIPGUARD_LLM_BASE_URL="https://your-openai-compatible-endpoint/v1"
export SHIPGUARD_LLM_API_KEY="your-api-key"
export SHIPGUARD_LLM_MODEL="your-model-name"
```

You can also put these values in a local `.env` file in the directory where you
run ShipGuard:

```bash
SHIPGUARD_LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
SHIPGUARD_LLM_API_KEY=your-api-key
SHIPGUARD_LLM_MODEL=your-model-name
```

For GitHub PR analysis, public repositories work without a GitHub token. For
private repositories or higher rate limits, set:

```bash
export SHIPGUARD_GITHUB_TOKEN="your-github-token"
```

Or add it to `.env`:

```bash
SHIPGUARD_GITHUB_TOKEN=your-github-token
```

When a local `.env` file is present, ShipGuard uses its values for
`SHIPGUARD_*` configuration.

Do not commit secrets. Use `.env.example` as the template for local environment
files.

## Run

Create the synthetic demo repository:

```bash
python scripts/create_demo_repo.py
```

The generated `sample-app/` directory is a nested git repository and is ignored
by the parent ShipGuard repo.

Then analyze it:

```bash
python -m shipguard analyze --repo ./sample-app
```

ShipGuard reads the target repository's current git diff and sends that release
context to the configured LLM. The CLI includes the current branch, latest commit
hash, changed file names, changed file extensions, `git diff --stat`, and the
full git diff.

Large diffs are truncated before being sent to the LLM. The default limit is
30,000 characters:

```bash
python -m shipguard analyze --repo ./sample-app --max-diff-chars 30000
```

Analyze a GitHub pull request:

```bash
python -m shipguard analyze-pr --pr-url https://github.com/OWNER/REPO/pull/NUMBER
```

ShipGuard fetches PR metadata, changed file names, and the PR diff from GitHub.
For PR analysis, ShipGuard always sends full PR metadata and the complete
changed file list. File diffs are packed by release-risk priority so migrations,
API/schema changes, config/deployment changes, auth/security changes, and
dependency files are considered before lower-risk files. The default PR diff
context budget is 120,000 characters:

```bash
python -m shipguard analyze-pr --pr-url https://github.com/OWNER/REPO/pull/NUMBER --max-diff-chars 120000
```

By default, PR analysis also uses project memory. ShipGuard indexes selected
base-branch files from GitHub, extracts deterministic context, optionally asks
the configured LLM for a project summary, and stores memory locally under
`.shipguard/memory/<owner>_<repo>/`.

```bash
python -m shipguard analyze-pr \
  --pr-url https://github.com/OWNER/REPO/pull/NUMBER \
  --use-memory \
  --show-memory-summary
```

Memory files:

- `project_memory.json`
- `files_index.json`
- `release_history.jsonl`

Useful flags:

- `--no-memory` skips project memory.
- `--rebuild-memory` rebuilds memory from the PR base SHA.
- `--memory-dir .shipguard/memory` changes the local memory directory.
- `--show-memory-summary` prints a short memory summary.

The CLI prints:

- Release Readiness Score
- Decision
- Risk Level
- What may break
- What CI may miss
