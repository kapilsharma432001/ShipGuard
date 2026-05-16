from __future__ import annotations

from urllib.parse import urlparse

from pydantic import ValidationError

from shipguard.models import GitHubPRRef


class InvalidPRURLError(ValueError):
    """Raised when a URL is not a supported GitHub pull request URL."""


def parse_github_pr_url(pr_url: str) -> GitHubPRRef:
    parsed = urlparse(pr_url.strip())
    parts = [part for part in parsed.path.split("/") if part]

    if parsed.scheme != "https":
        raise InvalidPRURLError("PR URL must start with https://github.com/.")
    if parsed.netloc.lower() != "github.com":
        raise InvalidPRURLError("PR URL must use github.com.")
    if len(parts) != 4 or parts[2] != "pull":
        raise InvalidPRURLError(
            "PR URL must look like https://github.com/OWNER/REPO/pull/NUMBER."
        )

    owner, repo, _, number_text = parts
    try:
        number = int(number_text)
    except ValueError as exc:
        raise InvalidPRURLError("PR number must be an integer.") from exc

    if number <= 0:
        raise InvalidPRURLError("PR number must be greater than zero.")

    try:
        return GitHubPRRef(owner=owner, repo=repo, number=number, url=pr_url.strip())
    except ValidationError as exc:
        raise InvalidPRURLError("PR URL contains invalid owner, repo, or PR data.") from exc
