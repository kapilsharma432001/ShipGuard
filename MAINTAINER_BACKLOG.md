# ShipGuard Maintainer Backlog

ShipGuard is early-stage and under active development. This document turns the
directional [roadmap](ROADMAP.md) into issue drafts that maintainers can create
manually when there is capacity to review and support the work. It is not a
release commitment and does not imply external adoption.

## Turning roadmap ideas into issues

1. Search open and closed issues before creating a new one.
2. Create one issue per observable outcome. Split broad roadmap themes into
   reviewable changes with explicit acceptance criteria.
3. Use the feature or bug template, then replace generic prompts with concrete,
   sanitized examples.
4. Apply one type label, relevant area labels, and a participation label only
   when the issue is ready for outside contribution.
5. Add `design-needed` when behavior, compatibility, permissions, privacy, or
   output contracts must be agreed before implementation.
6. Link the issue from the relevant roadmap section. Update or remove the draft
   here after the GitHub issue becomes the source of truth.

Do not open every draft at once. Prefer a small set of issues that maintainers
can actively clarify, review, and close.

## Suggested labels

These labels are guidance; maintainers must create and describe them in GitHub
before applying them.

| Label | Use |
| --- | --- |
| `good first issue` | Small, bounded work with clear files and acceptance criteria. |
| `help wanted` | Scoped work where maintainer review capacity is available. |
| `documentation` | User, contributor, architecture, or policy documentation. |
| `enhancement` | New behavior or a meaningful improvement to existing behavior. |
| `testing` | Test coverage, fixtures, or evaluation infrastructure. |
| `github-actions` | GitHub Actions, CI integration, or workflow artifacts. |
| `risk-detection` | Release-risk signals, evidence, scoring inputs, or findings. |
| `security` | Credentials, permissions, unsafe behavior, or security boundaries. |
| `privacy` | Code sharing, model data flow, retention, or sensitive artifacts. |
| `design-needed` | Requires an agreed design before implementation starts. |
| `maintainer-workflow` | Review, triage, release, or repository maintenance workflow. |

Use labels narrowly. For example, a documentation-only privacy issue can use
`documentation` and `privacy` without also using `security` unless it addresses
a security boundary.

## Contribution readiness

Good first issues should be independently testable, avoid credentials and live
API calls, and have a small expected diff. Drafts 4, 10, 12, 13, and 15 are
reasonable first-issue candidates after a maintainer confirms their scope.

Use `help wanted` only after the expected behavior is clear. Drafts 1, 3, 5, 6,
7, 8, 9, and 14 need design discussion before implementation because they can
affect permissions, compatibility, output contracts, or finding quality.

Milestones should contain work that maintainers intend to coordinate, not the
entire idea list. Drafts 1-3 and 5-9 are candidates for future integration or
risk-detection milestones after design approval. Draft 14 is a candidate for an
evaluation milestone. Documentation and isolated test issues can usually remain
unmilestoned unless they block a planned release.

## Issue drafts

### 1. Define an advisory ShipGuard GitHub Action integration

**Suggested labels:** `enhancement`, `github-actions`, `maintainer-workflow`,
`design-needed`

**Design:** See the
[proposed GitHub Action design](docs/github-action-design.md), created for
GitHub issue #14.

**Status:** The design and initial advisory wrapper are implemented. Comment
posting, stricter modes, and broader evaluation remain future work.

**Problem:** Maintainers need an agreed interface for running ShipGuard as an
advisory review step in another repository.

**Expected outcome:** An agreed integration design covering invocation,
permissions, configuration, artifacts, failure behavior, and whether comments
remain opt-in.

**Acceptance criteria:**

- Document the proposed action interface and minimum GitHub permissions.
- Keep analysis advisory by default and require explicit opt-in for comments.
- Define how forks and missing credentials behave without exposing secrets.

**Notes for contributors:** Treat the design and usage documents as the current
interface. Propose later phases separately rather than adding mutation or
blocking behavior to the initial wrapper.

### 2. Document CI artifact upload for Release Passport reports

**Suggested labels:** `documentation`, `github-actions`,
`maintainer-workflow`

**Problem:** Release Passport files are generated locally, but maintainers do
not have a documented pattern for retaining them as CI artifacts.

**Expected outcome:** A minimal example showing how a downstream workflow can
upload Markdown, JSON, and optional HTML reports after successful generation.

**Acceptance criteria:**

- Use supported GitHub artifact actions and least-privilege permissions.
- Explain artifact paths, retention considerations, and behavior when analysis
  does not produce a report.
- Use placeholders for credentials and avoid any live model call in repository
  CI.

### 3. Evaluate SARIF and stable machine-readable findings

**Suggested labels:** `enhancement`, `risk-detection`, `design-needed`

**Problem:** `analysis.json` is machine-readable, but its findings are not
defined as a stable interchange format and cannot be consumed directly by
SARIF-compatible tools.

**Expected outcome:** A design decision for SARIF, a versioned ShipGuard finding
format, or both, with a mapping from current report fields.

**Acceptance criteria:**

- Identify required fields such as rule ID, severity, confidence, evidence, and
  file or line location.
- Document which current findings cannot be represented reliably.
- Define compatibility and schema-versioning expectations before coding.

### 4. Document the `analysis.json` schema

**Suggested labels:** `documentation`, `good first issue`

**Problem:** Report generation writes structured JSON, but contributors must
read implementation code and tests to understand its fields.

**Expected outcome:** Concise documentation of the current top-level objects,
required fields, optional values, and compatibility status.

**Acceptance criteria:**

- Base the documentation on `shipguard/models.py` and
  `shipguard/report_generator.py`.
- Include one sanitized, minimal example without private repository data.
- State that the schema is early-stage unless a formal stability policy exists.

### 5. Design repository configuration file support

**Suggested labels:** `enhancement`, `maintainer-workflow`, `design-needed`

**Problem:** Behavior is controlled through environment variables and CLI
options, making repeatable repository-specific risk priorities difficult.

**Expected outcome:** An approved proposal for a versioned configuration file,
including discovery, validation, precedence, and safe defaults.

**Acceptance criteria:**

- Propose a filename and document CLI, environment, and file precedence.
- Define validation and unknown-key behavior with actionable errors.
- Exclude secrets from the configuration format and document that boundary.

### 6. Make comment-posting defaults harder to misuse

**Suggested labels:** `enhancement`, `security`, `maintainer-workflow`,
`design-needed`

**Problem:** Comment posting is opt-in today, but the relationships among
preview, summary comments, inline comments, and `REQUEST_CHANGES` need a clear
safety policy before automation expands.

**Expected outcome:** Explicit invariants and tests that keep network mutations
intentional and make dry-run behavior unambiguous.

**Acceptance criteria:**

- Confirm that analysis alone never posts or deletes comments.
- Require explicit flags for summary, inline, and blocking review behavior.
- Cover conflicting flags and missing-token behavior with tests and clear
  errors.

### 7. Improve rollback-risk detection with evidence

**Suggested labels:** `enhancement`, `risk-detection`, `design-needed`

**Problem:** Rollback risk is part of model guidance and reports, but
deterministic evidence for irreversible or incomplete rollback paths is limited.

**Expected outcome:** Focused rollback signals that cite changed files or lines
and distinguish evidence from inference.

**Acceptance criteria:**

- Define a small initial set of high-confidence rollback patterns.
- Add synthetic positive and negative fixtures with deterministic tests.
- Avoid claiming a rollback is safe when evidence is absent.

### 8. Expand database migration-risk detection

**Suggested labels:** `enhancement`, `risk-detection`, `testing`,
`design-needed`

**Problem:** Migration files and operations are identified, but checks for
backfills, locking, sequencing, and production-data behavior remain limited.

**Expected outcome:** Better detection for a bounded set of high-risk migration
patterns without creating broad noisy warnings.

**Acceptance criteria:**

- Cover required columns, destructive operations, missing backfills, and
  rollback asymmetry with synthetic examples.
- Include framework-neutral behavior plus clearly identified framework-specific
  rules.
- Test both detected risks and safe counterexamples.

### 9. Improve API compatibility detection

**Suggested labels:** `enhancement`, `risk-detection`, `testing`,
`design-needed`

**Problem:** ShipGuard extracts route signals, but it has limited deterministic
comparison of removed routes, changed methods, required fields, and response
contracts.

**Expected outcome:** A scoped compatibility comparison that produces
evidence-backed findings for supported patterns.

**Acceptance criteria:**

- Define supported API patterns before implementation.
- Add synthetic breaking and non-breaking examples.
- Report unsupported or ambiguous changes as missing evidence rather than
  confirmed breakage.

### 10. Add tests for malformed GitHub pull request URLs

**Suggested labels:** `testing`, `good first issue`

**Problem:** `parse_github_pr_url` validates scheme, host, path, and PR number,
but there is no dedicated parser test module.

**Expected outcome:** Table-driven unit tests for valid and invalid URL forms
without network calls.

**Acceptance criteria:**

- Cover wrong schemes and hosts, missing path segments, non-integer numbers,
  zero or negative numbers, extra segments, and surrounding whitespace.
- Assert useful `InvalidPRURLError` messages.
- Preserve valid `https://github.com/OWNER/REPO/pull/NUMBER` behavior.

### 11. Add tests for large and partially packed PR diffs

**Suggested labels:** `testing`, `risk-detection`, `help wanted`

**Problem:** Risk-prioritized diff packing handles partial and omitted files,
but edge-case coverage for tight budgets and large files is limited.

**Expected outcome:** Deterministic tests for ordering, truncation markers,
included files, partial files, omitted files, and budget limits.

**Acceptance criteria:**

- Use synthetic patches and no GitHub or model network calls.
- Verify high-risk files are prioritized over documentation-only files.
- Cover budgets too small for a full section and large single-file diffs.

### 12. Add FastAPI and Django release-risk examples

**Suggested labels:** `documentation`, `good first issue`

**Problem:** The current synthetic demo is useful but does not show maintainers
how ShipGuard concepts map to common FastAPI and Django project structures.

**Expected outcome:** Small, sanitized documentation examples for API, schema,
settings, and migration changes in both frameworks.

**Acceptance criteria:**

- Use synthetic code and clearly label expected risks and limitations.
- Include commands that already exist in the CLI.
- Do not imply framework-wide compatibility or production validation.

### 13. Document privacy and model data flow

**Suggested labels:** `documentation`, `privacy`, `security`,
`good first issue`

**Problem:** Security guidance warns that code is sent to a configured endpoint,
but the exact inputs, local outputs, and user-controlled boundaries are spread
across several documents.

**Expected outcome:** One concise data-flow document covering collection,
transmission, local storage, credentials, and deletion responsibilities.

**Acceptance criteria:**

- Describe local diff, PR, project memory, report, and comment-preview data.
- Separate ShipGuard behavior from endpoint-specific retention or training
  policies.
- Include practical guidance for private repositories and generated artifacts.

### 14. Build a synthetic release-risk evaluation set

**Suggested labels:** `testing`, `risk-detection`, `maintainer-workflow`,
`design-needed`

**Problem:** Changes to prompts and deterministic detection lack a small shared
set of expected examples for comparing regressions and false positives.

**Expected outcome:** A reviewable, synthetic dataset with expected risk
categories and evidence, without presenting it as a benchmark of production
quality.

**Acceptance criteria:**

- Define a simple versioned fixture format and contribution rules.
- Include API, migration, configuration, dependency, rollback, and safe-change
  cases.
- Document how maintainers review disagreements and avoid unsupported accuracy
  claims.

### 15. Add a contributor architecture overview

**Suggested labels:** `documentation`, `good first issue`,
`maintainer-workflow`

**Problem:** The README lists modules, but contributors lack a concise guide to
the data flow and ownership boundaries among CLI, GitHub access, context,
models, model calls, reports, and comments.

**Expected outcome:** A short architecture document that helps contributors
locate changes and tests before editing code.

**Acceptance criteria:**

- Trace local analysis and PR analysis from CLI input to output artifacts.
- Identify modules responsible for external I/O and local persistence.
- Link relevant test files and call out early-stage compatibility boundaries.
