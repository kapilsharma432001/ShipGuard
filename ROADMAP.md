# ShipGuard Roadmap

ShipGuard is an early-stage project. This roadmap is directional and does not
promise release dates or compatibility guarantees. Priorities may change based
on maintainer capacity, contributor interest, and evidence from real workflows.

See [MAINTAINER_BACKLOG.md](MAINTAINER_BACKLOG.md) for label guidance and
concrete issue drafts that maintainers can create as review capacity allows.

## Near term

- Make installation and first-run errors clearer.
- Improve deterministic behavior when model calls fail or return invalid data.
- Add representative tests for large, partial, and malformed diffs.
- Define and document configuration and report schema stability expectations.
- Build a small, reviewable evaluation set from synthetic and public examples.
- Reduce noisy findings and make confidence and evidence more explicit.

## Maintainer workflows

- Maintain the initial
  [composite GitHub Action wrapper](docs/github-action-usage.md) for advisory PR
  analysis and artifact upload.
- Add optional summary comments only after permissions and rerun behavior are
  tested and documented.
- Keep inline comments, `REQUEST_CHANGES`, and risk-based blocking modes as
  future, explicitly enabled work.
- Support repository-level configuration for risk priorities and comment
  behavior.
- Improve repeat-run behavior, finding deduplication, and reviewer feedback.
- Explore baseline or suppression workflows for accepted risks.
- Make review summaries easier to use as non-blocking merge evidence.

## Integrations

- Improve GitHub authentication and permission guidance.
- Explore a GitHub App or similarly scoped installation model.
- Define artifact upload examples for common CI systems.
- Evaluate GitLab and other code-review integrations after the GitHub workflow
  is reliable.
- Keep model-provider integration compatible with user-controlled,
  OpenAI-compatible endpoints.

## Risk detection improvements

- Strengthen API and data-contract compatibility signals.
- Expand migration checks for backfills, locks, reversibility, and rollout
  sequencing.
- Improve configuration and environment-variable change detection.
- Add dependency-change context and supply-chain review signals.
- Connect risky code paths to relevant tests and missing coverage evidence.
- Improve authentication, authorization, and permission-change review.
- Distinguish observed evidence, inference, uncertainty, and missing evidence.

## Documentation and examples

- Add an architecture overview and contributor design notes.
- Document privacy, data flow, retention considerations, and threat boundaries.
- Add synthetic examples for API, migration, configuration, dependency, and
  rollback risks.
- Document expected false positives, false negatives, and review limitations.
- Provide complete examples for local use, PR use, dry-run comments, and CI
  artifacts.
- Add a release process when the project is ready to publish tagged releases.
