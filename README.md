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

For GitHub PR analysis, public repositories work without a GitHub token. For
private repositories or higher rate limits, set:

```bash
export SHIPGUARD_GITHUB_TOKEN="your-github-token"
```

Do not commit secrets. Use `.env.example` as the template if you manage local
environment files yourself.

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
The same diff size limit is available:

```bash
python -m shipguard analyze-pr --pr-url https://github.com/OWNER/REPO/pull/NUMBER --max-diff-chars 30000
```

The CLI prints:

- Release Readiness Score
- Decision
- Risk Level
- What may break
- What CI may miss
