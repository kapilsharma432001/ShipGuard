# ShipGuard GitHub Action Usage

## Current status

ShipGuard includes an initial, early-stage composite GitHub Action wrapper. It
runs model-backed pull request analysis in advisory mode and can upload the
generated Release Passport files.

The root `action.yml` is available through the repository's `v0` action tag.
The first GitHub/action release is `v0.1.0`.

The wrapper follows the safety model in the
[GitHub Action design](github-action-design.md). It does not prove that a
release is safe and does not replace CI or maintainer review.

## GitHub Action versus PyPI installation

GitHub Action and CLI installation are separate distribution paths:

- GitHub Action workflows use `kapilsharma432001/ShipGuard@v0`.
- CLI users install the `shipguard-ai` PyPI distribution with
  `python -m pip install shipguard-ai`.
- Python code continues to import the `shipguard` package.
- The installed console command remains `shipguard`.

Installing `shipguard-ai` does not install or configure the GitHub Action, and
referencing the GitHub Action does not publish or install a PyPI release.

## Dogfooding in this repository

ShipGuard includes an optional dogfooding workflow at
`.github/workflows/shipguard.yml`. It uses the local root action to review pull
requests and upload advisory Release Passport artifacts.

The workflow runs model-backed analysis only when
`SHIPGUARD_LLM_BASE_URL`, `SHIPGUARD_LLM_API_KEY`, and
`SHIPGUARD_LLM_MODEL` are all configured. When any secret is unavailable, it
skips the action and prints a short explanation without printing secret values.
Fork pull requests normally do not receive repository secrets, so they usually
take this skip path.

For safety, the workflow checks out the pull request base SHA before invoking
`uses: ./`. ShipGuard then fetches the proposed PR changes through the GitHub
API. This avoids executing a contributor-modified local action with model
secrets. The workflow uses read-only repository and pull request permissions,
does not post comments, and does not use `pull_request_target`.

## Verifying the dogfooding workflow

After configuring all three `SHIPGUARD_LLM_*` repository secrets, maintainers
can open a small documentation-only pull request to verify the integration.
Check the workflow run to confirm that:

- the ShipGuard step runs instead of taking the missing-secrets skip path;
- a Release Passport artifact is uploaded;
- no pull request comments are posted; and
- the result remains advisory rather than blocking the pull request.

Record only the observed workflow result. Do not add documentation claiming the
verification passed before the GitHub Actions run completes successfully.

## What works today

The initial wrapper:

- installs ShipGuard from the checked-out action revision;
- runs `python -m shipguard analyze-pr` for a required pull request URL;
- supports project memory, memory rebuilds, diff limits, HTML reports, and
  dry-run comment previews;
- generates Markdown and JSON Release Passport files, with HTML enabled by
  default for the action;
- uploads `.shipguard/reports/**` using `actions/upload-artifact@v4` by default;
- accepts an optional GitHub token for private repositories or higher API rate
  limits; and
- treats findings as advisory while still failing on tool or configuration
  errors.

## Not implemented yet

This first version does not:

- post or update a pull request summary comment;
- post inline review comments;
- submit `REQUEST_CHANGES`;
- block a merge based on risk level or decision;
- implement a `fail_on` risk policy; or
- cache project memory across ephemeral runners.

The inputs `post_comment`, `post_inline_comments`, and `request_changes` are
reserved for future compatibility. The action exits with a clear error if any
of them is set to `"true"`.

## Required secrets

Release-risk analysis currently requires an explicitly configured
OpenAI-compatible model endpoint:

- `SHIPGUARD_LLM_BASE_URL`
- `SHIPGUARD_LLM_API_KEY`
- `SHIPGUARD_LLM_MODEL`

The action does not print these values. Repository maintainers are responsible
for approving the endpoint and reviewing its access, logging, retention,
training, and deletion policies before sending repository context.

`github_token` is optional for public pull request reads. Pass
`${{ github.token }}` for private repositories or higher API rate limits. The
wrapper maps this input to `SHIPGUARD_GITHUB_TOKEN` without printing it.

Fork pull requests generally do not receive repository secrets. This initial
wrapper therefore cannot perform model-backed review for an untrusted fork
when the model secrets are unavailable. Do not switch to
`pull_request_target` with an untrusted checkout to bypass this protection.

## Recommended permissions

The initial action does not post comments, so read-only permissions are
recommended:

```yaml
permissions:
  contents: read
  pull-requests: read
```

Do not grant `pull-requests: write` for this version. Artifact upload uses the
workflow artifact service and does not require broad repository write access.

## Example workflow

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
        env:
          SHIPGUARD_LLM_BASE_URL: ${{ secrets.SHIPGUARD_LLM_BASE_URL }}
          SHIPGUARD_LLM_API_KEY: ${{ secrets.SHIPGUARD_LLM_API_KEY }}
          SHIPGUARD_LLM_MODEL: ${{ secrets.SHIPGUARD_LLM_MODEL }}
```

For testing before a release, maintainers can reference a reviewed commit SHA
instead of `v0`. Pinning a commit is safer than referencing a moving branch.

## Inputs

| Input | Default | Description |
| --- | --- | --- |
| `pr_url` | Required | GitHub pull request URL to analyze. |
| `python_version` | `"3.11"` | Python version passed to `actions/setup-python@v5`. |
| `use_memory` | `"true"` | Include project memory from the PR base SHA. |
| `rebuild_memory` | `"false"` | Rebuild memory during this run. |
| `max_diff_chars` | `"120000"` | Maximum PR diff characters supplied to ShipGuard. |
| `html` | `"true"` | Generate `release_passport.html`. |
| `upload_artifacts` | `"true"` | Upload generated reports. |
| `artifact_name` | `"shipguard-release-passport"` | Uploaded artifact name. |
| `dry_run_comments` | `"false"` | Generate `pr_comment_preview.md` without posting. |
| `post_comment` | `"false"` | Reserved; `"true"` fails in this version. |
| `post_inline_comments` | `"false"` | Reserved; `"true"` fails in this version. |
| `request_changes` | `"false"` | Reserved; `"true"` fails in this version. |
| `github_token` | `""` | Optional token for GitHub API reads. |

Boolean inputs must be the lowercase strings `"true"` or `"false"`.

## Generated artifacts

Successful analysis writes files below:

```text
.shipguard/reports/<owner>_<repo>_pr_<number>/
  release_passport.md
  release_passport.html
  analysis.json
```

`release_passport.html` is omitted when `html` is `"false"`.
`pr_comment_preview.md` is added when `dry_run_comments` is `"true"`.

Set `upload_artifacts: "false"` to keep the files only in the runner workspace.
If artifact upload is enabled but no files are found, the upload step warns
without failing only because the path is empty.

## Artifact privacy warning

Release Passport artifacts may contain file names, code or diff excerpts,
route and database details, configuration names, and inferred risks. Anyone
who can access the workflow artifacts may be able to read that context.

Choose repository visibility, Actions access, and artifact retention settings
accordingly. Do not run model-backed analysis on confidential code without an
approved model endpoint and retention policy.

## Troubleshooting

### Missing model configuration

Set all three `SHIPGUARD_LLM_*` secrets in the workflow environment. The action
cannot produce a release-risk report without them.

### Invalid pull request URL

Use a standard GitHub URL:

```text
https://github.com/OWNER/REPO/pull/NUMBER
```

### Private repository or rate-limit error

Pass `github_token: ${{ github.token }}` and keep `contents: read` and
`pull-requests: read`.

### Unsupported input error

Keep `post_comment`, `post_inline_comments`, and `request_changes` set to
`"false"`. Mutating and blocking review behavior is intentionally unavailable.

### No uploaded files

Check the ShipGuard analysis step first. Reports are generated only after a
successful model response. The artifact step also requires
`upload_artifacts: "true"`.

### Large or partial pull request diff

Increase `max_diff_chars` carefully. ShipGuard records omitted or partially
included files so maintainers can treat missing context as missing evidence,
not as proof of safety.
