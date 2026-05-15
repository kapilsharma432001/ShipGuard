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

Do not commit secrets. Use `.env.example` as the template if you manage local
environment files yourself.

## Run

Create the synthetic demo repository:

```bash
python scripts/create_demo_repo.py
```

Then analyze it:

```bash
python -m shipguard analyze --repo ./sample-app
```

The first implementation sends a fixed release-risk prompt to the configured
LLM and prints:

- Release Readiness Score
- Decision
- Risk Level
- What may break
- What CI may miss
