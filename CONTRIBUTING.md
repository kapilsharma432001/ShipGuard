# Contributing to ShipGuard

ShipGuard is an early-stage open-source project. Focused bug fixes, tests,
documentation improvements, risk-detection ideas, and maintainer workflow
improvements are welcome.

Please follow the [Code of Conduct](CODE_OF_CONDUCT.md) in all project spaces.
Report security concerns using [SECURITY.md](SECURITY.md), not a public issue.

## Local setup

ShipGuard requires Python 3.11 or newer and Git.

```bash
git clone https://github.com/kapilsharma432001/ShipGuard.git
cd ShipGuard
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

If `python` does not point to Python 3 on your system, use `python3` to create
the virtual environment.

To run model-backed analysis, create local environment variables or copy
`.env.example` to `.env` and add credentials for an OpenAI-compatible endpoint.
Never commit real API keys, tokens, private repository data, or generated
reports containing sensitive code.

## Development checks

Run the unit tests:

```bash
python -m unittest discover -s tests
```

Run a compile check:

```bash
python -m compileall shipguard scripts tests
```

Check the CLI:

```bash
python -m shipguard --help
python -m shipguard analyze --help
python -m shipguard analyze-pr --help
python -m shipguard clear-comments --help
```

The repository does not currently configure a project-wide linter or formatter.
Do not introduce broad formatting-only changes. A proposal to add a tool should
explain the command, configuration, and expected contributor workflow.

## Opening an issue

Before opening an issue:

1. Search existing issues for the same problem or proposal.
2. Use the relevant issue template.
3. Include the Python version, operating system, command, expected behavior,
   actual behavior, and a minimal reproduction when applicable.
4. Remove credentials, private repository content, and other sensitive data
   from logs and examples.

For feature requests, describe the maintainer problem first. A focused use case
is more useful than a broad request for "more AI" or a complete redesign.

Maintainers and contributors can use
[MAINTAINER_BACKLOG.md](MAINTAINER_BACKLOG.md) for label guidance and scoped
issue drafts. The GitHub issue should become the source of truth once created.

## Opening a pull request

1. Keep the change focused on one problem.
2. Add or update tests when behavior changes.
3. Update documentation when commands, configuration, or output changes.
4. Add a concise entry under `Unreleased` in `CHANGELOG.md` for user-visible
   changes.
5. Run the discoverable development checks above.
6. Complete the pull request template, including risk and verification notes.

Avoid unrelated refactors in the same pull request. Changes to prompts, risk
scoring, GitHub comment behavior, or report schemas should explain the expected
behavioral impact and include representative tests where practical.

## Welcome contributions

- Bug fixes with a clear reproduction.
- Unit and integration tests.
- Documentation and setup improvements.
- Better error messages and failure handling.
- Risk-detection rules with concrete evidence and low-noise behavior.
- Privacy, security, and data-handling improvements.
- GitHub maintainer workflow improvements.
- Synthetic examples that do not contain private or proprietary code.

## Good first contribution ideas

- Improve a troubleshooting entry based on a reproducible failure.
- Add tests for malformed GitHub PR URLs or unusual diff shapes.
- Add tests for report rendering edge cases.
- Improve CLI help text without changing command behavior.
- Add a small synthetic risk example to the demo repository generator.
- Clarify platform-specific setup steps.
- Document a false positive or missed risk using sanitized, synthetic input.

For a larger change, open an issue first so maintainers and contributors can
agree on scope before significant implementation work.
