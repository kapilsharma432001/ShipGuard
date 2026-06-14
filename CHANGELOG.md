# Changelog

All notable changes to ShipGuard will be documented in this file.

The project intends to follow [Keep a
Changelog](https://keepachangelog.com/en/1.1.0/) and semantic versioning once a
stable release process is established.

## [Unreleased]

### Added

- Standard open-source governance and contribution documentation.
- GitHub issue and pull request templates.
- A maintainer-oriented roadmap.
- GitHub Actions validation for tests, compilation, and CLI help on supported
  Python versions.
- Maintainer backlog guidance with suggested labels and actionable issue
  drafts.
- A proposed, design-only GitHub Action integration covering safety,
  permissions, artifacts, failures, and privacy.
- An initial advisory composite GitHub Action wrapper that runs PR analysis and
  uploads Release Passport artifacts.
- GitHub Action usage documentation covering secrets, permissions, limitations,
  artifact privacy, and troubleshooting.
- A read-only, secret-gated dogfooding workflow for advisory pull request
  Release Passport artifacts.
- Documentation for verifying the dogfooding workflow with a small pull
  request.
- A PyPI Trusted Publishing workflow that builds, checks, and publishes package
  distributions without an API token.
- PyPI release documentation for local validation and repository setup.

### Changed

- Reframed the README around pull request release-risk review, current
  capabilities, limitations, and supported workflows.
- Changed the intended PyPI distribution name to `shipguard-ai` and bumped the
  package version to `0.1.1`, while preserving the `shipguard` import namespace
  and CLI command.
