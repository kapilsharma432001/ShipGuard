# ShipGuard Proof and Examples

## Current status

ShipGuard is an early-stage open-source release-risk reviewer under active
development. It is available as a Python package and a GitHub Action, and this
repository runs the action against its own pull requests.

These are distribution and integration milestones. ShipGuard remains advisory:
its findings require maintainer review and do not establish that a release is
safe.

## PyPI package

The [`shipguard-ai` distribution is published on
PyPI](https://pypi.org/project/shipguard-ai/). Install it with:

```bash
python -m pip install shipguard-ai
```

The project uses different names for distribution, import, and command-line
use:

| Purpose | Name |
| --- | --- |
| PyPI distribution | `shipguard-ai` |
| Python import package | `shipguard` |
| CLI command | `shipguard` |

Publishing a package proves that the release artifacts can be installed through
PyPI. It does not demonstrate usage, reliability, or production maturity.

## GitHub Action

The repository contains a root composite action for advisory pull request
analysis. Workflows reference the released action line with:

```yaml
uses: kapilsharma432001/ShipGuard@v0
```

The action runs ShipGuard, generates Release Passport reports, and can upload
them as workflow artifacts. Model-backed analysis requires an explicitly
configured OpenAI-compatible endpoint and model credentials.

See the [GitHub Action usage guide](github-action-usage.md) for inputs,
permissions, limitations, and privacy guidance.

## Dogfooding workflow

ShipGuard's [dogfooding
workflow](https://github.com/kapilsharma432001/ShipGuard/blob/main/.github/workflows/shipguard.yml)
runs ShipGuard on pull requests in this repository when all required
`SHIPGUARD_LLM_*` secrets are available. It uses read-only repository and pull
request permissions and explicitly disables summary comments, inline comments,
and request-changes behavior.

A [successful public workflow
run](https://github.com/kapilsharma432001/ShipGuard/actions/runs/27500976995)
on June 14, 2026, recorded a successful `Run ShipGuard` step, skipped the
missing-secrets fallback, and uploaded a `shipguard-release-passport` artifact.
Because the workflow only invokes ShipGuard when all three model settings are
available, this is evidence that the configured dogfooding path generated
Release Passport artifacts.

This document does not reproduce artifact contents. Reports may contain code
snippets, file names, configuration details, or inferred risks and should only
be shared after sanitization.

## Example workflows

This minimal example runs the released action in advisory mode:

```yaml
name: ShipGuard Release Risk Review

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: read

jobs:
  shipguard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run ShipGuard
        uses: kapilsharma432001/ShipGuard@v0
        with:
          pr_url: ${{ github.event.pull_request.html_url }}
          github_token: ${{ github.token }}
          post_comment: "false"
          post_inline_comments: "false"
          request_changes: "false"
        env:
          SHIPGUARD_LLM_BASE_URL: ${{ secrets.SHIPGUARD_LLM_BASE_URL }}
          SHIPGUARD_LLM_API_KEY: ${{ secrets.SHIPGUARD_LLM_API_KEY }}
          SHIPGUARD_LLM_MODEL: ${{ secrets.SHIPGUARD_LLM_MODEL }}
```

A successful run can generate these report files:

```text
release_passport.md
release_passport.html
analysis.json
```

## Safety model

- Findings are advisory and do not block merges by default.
- Comment posting and request-changes behavior are disabled in the current
  action.
- Model-backed review requires explicit endpoint, key, and model configuration.
- Secrets must not be printed, committed, or copied into reports or issues.
- Selected diff and repository context may be sent to the configured model
  endpoint.
- Uploaded artifacts may contain repository context and must follow the
  repository's access and retention policy.
- Fork pull requests normally do not receive repository secrets and may skip
  model-backed analysis.

## What this proves

- `shipguard-ai` has a publicly installable PyPI release.
- The `shipguard` import package and CLI remain available through that
  distribution.
- A released GitHub Action reference is documented for pull request workflows.
- ShipGuard's own pull request workflow has completed model-backed analysis and
  uploaded a Release Passport artifact.
- The current dogfooding configuration is read-only and advisory.

## What this does not prove yet

- External adoption, users, download volume, or production deployment.
- Accuracy across languages, frameworks, repository sizes, or risk categories.
- A measured reduction in incidents or review time.
- Security-scanner coverage or a guarantee that a release is safe.
- Suitability for confidential code without an approved model endpoint and
  data-retention policy.
- Stable inputs, outputs, or compatibility guarantees for future versions.
