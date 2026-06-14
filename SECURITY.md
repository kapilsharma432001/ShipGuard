# Security Policy

ShipGuard processes source-code context, pull request data, and credentials for
user-configured services. Treat its configuration and generated artifacts as
sensitive.

## Supported versions

ShipGuard is early-stage and does not yet have a formal supported release line.
Security fixes are handled on a best-effort basis against the default branch.

## Reporting a vulnerability

Do not publish vulnerability details, proof-of-concept exploits, API keys,
access tokens, private repository data, or generated reports containing
sensitive code in a public GitHub issue.

To report a vulnerability:

1. Check the repository's **Security** tab for GitHub private vulnerability
   reporting.
2. If private reporting is enabled, use it and include the affected component,
   impact, reproduction steps, and suggested mitigation when known.
3. If no private channel is available, open a public issue containing only a
   request for private contact. Do not include sensitive details.

There is currently no private security contact documented in this repository.

> **Maintainer action required:** Enable GitHub private vulnerability reporting
> or publish a monitored security contact before recommending ShipGuard for
> wider adoption.

Because this is a volunteer, early-stage project, no response or remediation
service-level agreement is currently offered.

## Protecting secrets and repository data

- Never commit `.env` files, API keys, GitHub tokens, or model credentials.
- Do not paste secrets into issues, pull requests, screenshots, test fixtures,
  or example commands.
- Do not share private repository content in a public report.
- Use an approved model endpoint and data-retention policy for confidential
  code.
- Rotate a credential immediately if it may have been exposed.

ShipGuard sends selected diff and repository context to the configured
OpenAI-compatible endpoint. Users are responsible for confirming that the
endpoint's access controls, logging, retention, and training policies are
appropriate for their code.
