# ShipGuard GitHub Action Design

## Status

**Partially implemented.** The initial composite wrapper and artifact upload
support now exist at the repository root. Comment posting, inline comments,
blocking behavior, and risk-based failure policy remain design-only.

Related GitHub issue: [#14](https://github.com/kapilsharma432001/ShipGuard/issues/14)

See [GitHub Action usage](github-action-usage.md) for the implemented input
surface and current release status. This document continues to record the
broader safety model and future interface; names and behavior may still change.

## Goals

A future ShipGuard GitHub Action should:

- run ShipGuard for pull request events;
- generate release-risk reports before merge;
- upload Release Passport artifacts for maintainer review;
- optionally post or update an advisory pull request summary comment;
- leave room for conservative, explicitly enabled inline comments later; and
- help maintainers discuss release risk alongside existing CI results.

The integration should be predictable in forks and private repositories, make
external data transmission visible, and use the minimum GitHub permissions
needed for each enabled feature.

## Non-goals

The proposed action is:

- not a replacement for CI, tests, code review, or release engineering;
- not a security scanner;
- not a deployment gate by default;
- not a guarantee that a release is safe;
- not expected to post comments by default;
- not expected to request changes or block a merge by default; and
- not allowed to send private code to a model endpoint unless a repository
  maintainer explicitly configures and approves that endpoint.

Publishing and maintaining a `v0` tag or release remains a separate maintainer
step.

## Proposed user experience

The following workflow matches the initial wrapper, but the
`kapilsharma432001/ShipGuard@v0` reference is unavailable until a corresponding
Git tag or release exists.

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

      # Available only after a v0 tag or release is published.
      - name: Run ShipGuard
        uses: kapilsharma432001/ShipGuard@v0
        with:
          pr_url: ${{ github.event.pull_request.html_url }}
          post_comment: "false"
          upload_artifacts: "true"
        env:
          SHIPGUARD_LLM_BASE_URL: ${{ secrets.SHIPGUARD_LLM_BASE_URL }}
          SHIPGUARD_LLM_API_KEY: ${{ secrets.SHIPGUARD_LLM_API_KEY }}
          SHIPGUARD_LLM_MODEL: ${{ secrets.SHIPGUARD_LLM_MODEL }}
          GITHUB_TOKEN: ${{ github.token }}
```

Model secrets would be required for the model-backed review shown above.
Installing the wrapper, checking its inputs, showing CLI help, or running a
future preflight/local-validation mode should not require model secrets.
ShipGuard's current PR analysis cannot generate a release-risk report without
a configured model endpoint.

To post a summary comment, a maintainer would need to change
`pull-requests: read` to `pull-requests: write` and explicitly set
`post_comment: "true"`. Enabling a mutation should never happen implicitly
because a token happens to be available.

## Inputs

The implemented inputs are documented in
[GitHub Action usage](github-action-usage.md). The broader table below retains
future design ideas; inputs absent from the usage guide are not implemented.

| Input | Purpose | Proposed default | Safety notes |
| --- | --- | --- | --- |
| `pr_url` | Pull request URL to analyze. | Required. | Validate the host and path before making requests. Do not accept arbitrary API hosts implicitly. |
| `repo` | Checked-out repository path for local validation or future local-diff mode. | `"."` | Resolve within `GITHUB_WORKSPACE` by default and reject surprising paths. |
| `use_memory` | Build and include project memory from the PR base SHA. | `"true"` | Memory may contain repository structure and extracted code context. |
| `rebuild_memory` | Ignore cached memory and rebuild it for the current base SHA. | `"false"` | Rebuilds may increase API and model usage. |
| `max_diff_chars` | Maximum PR diff characters supplied to analysis. | `"120000"` | Truncation must be visible in reports; omitted evidence must not be treated as safe. |
| `html` | Generate `release_passport.html`. | `"true"` in the initial action. | HTML may contain repository and risk context and should be handled as sensitive. |
| `upload_artifacts` | Upload generated reports as workflow artifacts. | `"true"` | Artifact names, contents, and retention must follow repository policy. |
| `post_comment` | Create or update an advisory PR summary comment. | `"false"` | Accepted for compatibility but `"true"` fails until posting is implemented. |
| `post_inline_comments` | Post conservative comments on supported changed lines. | `"false"` | Accepted for compatibility but `"true"` fails until posting is implemented. |
| `request_changes` | Use a blocking `REQUEST_CHANGES` review for inline comments. | `"false"` | Accepted for compatibility but `"true"` fails until blocking behavior is implemented. |
| `max_inline_comments` | Limit inline comments per run. | `"5"` | Enforce a small upper bound to avoid review noise. |
| `fail_on` | Control whether tool errors or risk findings fail the action. | `"tool_error"` | Risk findings remain advisory by default. Proposed values need design approval. |
| `dry_run_comments` | Generate `pr_comment_preview.md` without posting. | `"false"` | Preview generation must not require write permission. |

Invalid combinations should fail before analysis. Examples include
`request_changes: "true"` without inline comments or any comment-posting input
without sufficient permissions.

## Environment variables and secrets

### Model configuration

Model-backed analysis requires explicit configuration:

- `SHIPGUARD_LLM_BASE_URL`
- `SHIPGUARD_LLM_API_KEY`
- `SHIPGUARD_LLM_MODEL`

The wrapper must not print secret values, include them in reports, or pass them
through action outputs. Error messages should name missing variables without
showing their contents.

Private repository maintainers must review the model endpoint's access control,
logging, retention, training, and deletion policies before enabling analysis.
Configuring a secret is an explicit decision to allow selected diff and
repository context to be transmitted to that endpoint.

### GitHub authentication

The action should accept the workflow-provided `GITHUB_TOKEN` by default and
map it internally to the authentication expected by ShipGuard. An explicitly
provided `SHIPGUARD_GITHUB_TOKEN` may be supported for unusual installations,
but it should not be required for normal GitHub Actions use.

Tokens must use least-privilege permissions:

- read access for fetching private PR and repository context;
- write access only when comments are explicitly enabled; and
- no administration, deployment, package, or unrelated repository permission.

Fork pull requests do not receive repository secrets by default. The action
must fail clearly or run an explicitly designed secret-free preflight; it must
not weaken GitHub's fork protections or use `pull_request_target` with
untrusted checkout code as a shortcut.

## Permissions model

Recommended permissions should depend on enabled behavior:

| Capability | Suggested permission |
| --- | --- |
| Checkout and repository context | `contents: read` |
| Analysis-only PR metadata and diff access | `pull-requests: read` |
| Summary or inline comments | `pull-requests: write` |
| Release report artifact upload | Use the official artifact mechanism without granting unrelated write permissions. |

The implementation should document the smallest complete workflow for each
mode. In normal GitHub Actions workflows, `actions/upload-artifact` uses the
job's artifact runtime and does not justify granting broad `actions: write`.
If implementation testing identifies an additional permission, it should be
scoped to the artifact-producing job and documented with a reason.

The action should inspect requested features, but it cannot reliably prove the
effective token permissions in advance. Permission failures must therefore be
clear and must never trigger a retry with broader credentials.

## Default safety behavior

The proposed defaults are:

- advisory mode;
- no summary comment posting;
- no inline comment posting;
- no `REQUEST_CHANGES` review;
- Release Passport generation and artifact upload enabled when analysis
  succeeds;
- `fail_on: "tool_error"`, so operational failures fail but risk findings do
  not; and
- explicit opt-in for every behavior that mutates a pull request or blocks a
  merge.

`fail_on: "never"` may be useful for exploratory adoption, but it should still
surface tool failures in logs and outputs. Stricter values such as `"high"`,
`"critical"`, or `"block_release"` should not be implemented until decision
semantics and compatibility guarantees are documented.

The presence of `GITHUB_TOKEN` or model secrets must not enable comments,
blocking behavior, or additional data collection by itself.

## Outputs and artifacts

Successful model-backed PR analysis currently produces:

- `release_passport.md`
- `analysis.json`
- `release_passport.html` when HTML output is enabled
- `pr_comment_preview.md` when comment preview or posting behavior is enabled

The future action should upload only files that were generated and should
report their local paths as action outputs. Proposed metadata outputs include
the report directory, risk level, decision, readiness score, and whether the
diff was truncated. Output names and stability require design review.

Artifact names should include the repository and PR number without exposing
branch names or user-controlled text unnecessarily. Retention should be
configurable through the workflow or follow the repository's default policy.

## Failure modes

Under the proposed default `fail_on: "tool_error"`, operational failures fail
the action while risk findings remain successful, advisory results.

| Failure | Default treatment | Reason |
| --- | --- | --- |
| Missing model configuration | Fail when model-backed review was requested; warn or succeed only in an explicit preflight mode. | A report cannot be generated without the required endpoint configuration. |
| Invalid PR URL | Fail before network access. | The requested analysis target is invalid. |
| GitHub rate limit or inaccessible PR | Fail if required context cannot be fetched. | Continuing would produce an incomplete or misleading review. |
| Model endpoint timeout | Fail after a small, documented retry policy. | No valid risk result exists. |
| Invalid or empty model response | Fail and do not publish comments. | Malformed findings must not be presented as a review. |
| Oversized or partially available diff | Warn, mark truncation in the report, and continue when useful evidence remains. | Partial evidence is expected for large PRs but must be visible. |
| Artifact upload failure | Fail when `upload_artifacts` is enabled. | The explicitly requested deliverable was not retained. |
| Permission failure while posting comments | Fail the requested posting step without retrying with broader permissions. | The repository explicitly requested a mutation that did not complete. |

The implementation should generate reports before attempting optional comments
so a posting failure does not destroy already-produced local evidence. It
should not post partial or malformed analysis.

## Privacy and data handling

ShipGuard may send selected pull request diffs and repository context to the
configured model endpoint. Repository maintainers are responsible for
approving that endpoint and understanding its logging, retention, training,
access, and deletion policies.

Generated artifacts may contain file names, code snippets, route names,
database details, configuration names, and inferred release risks. They should
be treated according to the repository's data-classification and artifact
retention policies. Public repositories should still avoid exposing secrets
that were accidentally committed or included in a diff.

Do not enable model-backed analysis for confidential code without an approved
endpoint and retention policy. Do not print secrets, upload local `.env` files,
or persist credentials in project memory, reports, caches, comments, or action
outputs.

## Implementation plan

### Phase 1: Documentation and design - completed

- Review this interface, threat boundaries, permission model, and open
  questions.
- Decide packaging, versioning, ownership, and compatibility expectations.

### Phase 2: Composite action wrapper around the existing CLI - implemented

- Install a pinned or checked-out ShipGuard version.
- Validate inputs and map them to existing CLI flags.
- Support analysis-only behavior before any GitHub mutation.
- Continue improving wrapper checks without model or GitHub network calls.

### Phase 3: Artifact upload support - initial support implemented

- Collect only generated Release Passport files.
- Use `actions/upload-artifact@v4` for the current report path.
- Continue documenting artifact names, missing-file behavior, and retention.

### Phase 4: Optional summary comment support

- Require `post_comment: "true"` and `pull-requests: write`.
- Preserve ShipGuard's marker-based update behavior to avoid duplicate summary
  comments.
- Keep dry-run preview available with read-only permissions.

### Phase 5: Inline comments and stricter modes

- Keep inline comments bounded and evidence-based.
- Require separate opt-in for inline comments and `REQUEST_CHANGES`.
- Define `fail_on` semantics and compatibility before offering blocking modes.

### Phase 6: Examples and evaluation

- Add public and synthetic workflow examples.
- Exercise fork, private repository, permission, truncation, and rerun cases.
- Evaluate noise and failure behavior without making unsupported accuracy
  claims.

Each phase should be independently reviewable. Later phases should not be
bundled into the initial wrapper implementation.

## Open questions

- The initial action lives at the root of this repository. Should it remain
  here as the interface grows, or move to a separate `shipguard-action`
  repository later?
- The initial action runs model-backed analysis. Should a separate,
  secret-free preflight mode be added?
- Which values should `fail_on` support, and how should they map to ShipGuard
  decisions and risk levels?
- How should project memory behave on ephemeral runners: rebuild every run,
  use GitHub cache, download a prior artifact, or remain disabled initially?
- How should summary and inline comments be deduplicated across reruns, force
  pushes, and changed PR head SHAs?
- The initial action uploads reports by default. Should that default change
  after practical workflow feedback?
- Should artifact upload failure fail the job when `fail_on: "never"`?
- How should the action behave for fork pull requests where model secrets are
  intentionally unavailable?
- The initial action accepts `github_token` and maps it to
  `SHIPGUARD_GITHUB_TOKEN`. Should the underlying CLI eventually recognize
  `GITHUB_TOKEN` directly?
- What action outputs can be considered stable enough for downstream workflow
  conditions?
