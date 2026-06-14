# PyPI Release Guide

## Package identity

The PyPI distribution name for this project is `shipguard-ai`.

```bash
python -m pip install shipguard-ai
```

The distribution name is separate from the installed Python package and CLI:

- Distribution: `shipguard-ai`
- Import package: `shipguard`
- CLI command: `shipguard`

This project should not be published under the existing or unavailable
`shipguard` PyPI distribution name.

## Versioning

- `v0.1.0` was the first GitHub release and GitHub Action release.
- `v0.1.1` is the first package release published to PyPI as `shipguard-ai`.

## Verify the published package

Install and verify the published distribution in a clean environment:

```bash
python -m pip install shipguard-ai
shipguard --help
python -c "import shipguard; print('shipguard import works')"
```

These commands confirm the distinction between the `shipguard-ai` distribution,
the `shipguard` import package, and the `shipguard` CLI command.

## Local build checks

Use Python 3.11 or newer from a clean virtual environment:

```bash
python -m pip install build twine
rm -rf dist build *.egg-info
python -m build
python -m twine check dist/*
```

The build should create both:

```text
dist/shipguard_ai-0.1.1-py3-none-any.whl
dist/shipguard_ai-0.1.1.tar.gz
```

Before publishing, inspect the archives and verify:

- the wheel contains the `shipguard` import package;
- the console entry point remains `shipguard`;
- package metadata names the distribution `shipguard-ai`;
- the README is present as the package description and the license file is
  included; and
- no credentials, `.env` files, generated reports, or private repository data
  are present.

## Recommended publishing method

Use PyPI Trusted Publishing through
`.github/workflows/publish-pypi.yml`. Trusted Publishing uses GitHub's OIDC
identity and does not require a stored PyPI password or API token.

Before the workflow can publish, configure a PyPI Trusted Publisher for the
existing project, or a pending Trusted Publisher when creating the project for
the first time, with:

- PyPI project: `shipguard-ai`
- GitHub owner: `kapilsharma432001`
- GitHub repository: `ShipGuard`
- Workflow: `publish-pypi.yml`
- GitHub environment: `pypi`

Also create the `pypi` environment in GitHub. Maintainers may add required
reviewers and deployment-branch restrictions there.

The workflow separates building from publishing. Only the publish job receives
`id-token: write`; the build job remains read-only. The checked distributions
are transferred between jobs as a workflow artifact.

## Publishing

The workflow runs when a GitHub release is published and can also be started
manually with `workflow_dispatch`.

For a release:

1. Run the local build checks.
2. Confirm `pyproject.toml` contains the intended, unused version.
3. Merge the release preparation.
4. Create and publish the matching GitHub release from the intended commit.
5. Approve the protected `pypi` environment deployment if configured.
6. Confirm the workflow and PyPI project page before announcing availability.

For manual dispatch, select the exact reviewed release commit or tag. PyPI
rejects re-uploading files for a version that already exists.

## Credential safety

Do not commit PyPI API tokens, passwords, `.pypirc` files, or generated
credentials. Do not add a PyPI token to this workflow.

If Trusted Publishing is not configured correctly, fix the PyPI publisher or
GitHub environment settings instead of adding a long-lived token.
