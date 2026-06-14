## Summary

Describe the change and the maintainer or user problem it addresses.

## Changes

- Describe the main changes here.

## Verification

List the commands run and relevant results.

```text
python -m unittest discover -s tests
python -m compileall shipguard scripts tests
```

## Release-risk review

- [ ] No public API, output schema, or CLI behavior changes.
- [ ] No database or state migration is required.
- [ ] No new environment variables, permissions, or secrets are required.
- [ ] No dependency or model-provider behavior changes.
- [ ] Tests cover the changed behavior.
- [ ] Rollback is straightforward or explained below.

Explain any unchecked item:

## Contributor checklist

- [ ] I kept this pull request focused.
- [ ] I added or updated tests where behavior changed.
- [ ] I updated documentation for command, configuration, or output changes.
- [ ] I added a user-visible change to `CHANGELOG.md` when applicable.
- [ ] I removed secrets, private repository data, and sensitive logs.
- [ ] I have read and followed `CONTRIBUTING.md` and the Code of Conduct.
