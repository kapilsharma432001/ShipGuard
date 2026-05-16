from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from shipguard.models import GitHubPRRef, PRChangeSummary


GITHUB_API_URL = "https://api.github.com"


class GitHubClientError(RuntimeError):
    """Raised when ShipGuard cannot fetch GitHub PR data."""


class GitHubClient:
    def __init__(self, token: str | None = None, api_url: str = GITHUB_API_URL) -> None:
        self._token = token.strip() if token else None
        self._api_url = api_url.rstrip("/")

    @classmethod
    def from_env(cls) -> "GitHubClient":
        return cls(token=os.getenv("SHIPGUARD_GITHUB_TOKEN"))

    def fetch_pr_changes(
        self,
        pr: GitHubPRRef,
        max_diff_chars: int = 30_000,
    ) -> PRChangeSummary:
        if max_diff_chars <= 0:
            raise GitHubClientError("max diff characters must be greater than zero.")

        path = _pull_request_path(pr)
        metadata = self._get_json(path)
        if not isinstance(metadata, dict):
            raise GitHubClientError("GitHub returned an unexpected PR metadata response.")

        files = self._get_changed_files(pr)
        diff = self._get_text(path, accept="application/vnd.github.diff")

        if not diff.strip():
            raise GitHubClientError(
                "GitHub returned an empty PR diff. The PR may have no file changes "
                "or the diff may be unavailable."
            )

        truncated_diff, was_truncated = _truncate(diff, max_diff_chars)
        changed_files = [file["filename"] for file in files if file.get("filename")]

        return PRChangeSummary(
            pr_url=pr.url,
            owner=pr.owner,
            repo=pr.repo,
            pr_number=pr.number,
            title=str(metadata.get("title") or ""),
            body=_optional_str(metadata.get("body")),
            state=str(metadata.get("state") or "unknown"),
            base_branch=_nested_str(metadata, "base", "ref"),
            head_branch=_nested_str(metadata, "head", "ref"),
            base_sha=_nested_str(metadata, "base", "sha"),
            head_sha=_nested_str(metadata, "head", "sha"),
            changed_files_count=int(metadata.get("changed_files") or len(changed_files)),
            additions=int(metadata.get("additions") or 0),
            deletions=int(metadata.get("deletions") or 0),
            changed_files=changed_files,
            changed_file_extensions=_file_extensions(changed_files),
            diff=truncated_diff,
            diff_truncated=was_truncated,
            max_diff_chars=max_diff_chars,
        )

    def _get_changed_files(self, pr: GitHubPRRef) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        page = 1
        while True:
            page_files = self._get_json(
                f"{_pull_request_path(pr)}/files?per_page=100&page={page}"
            )
            if not isinstance(page_files, list):
                raise GitHubClientError("GitHub returned an unexpected PR files response.")

            files.extend(item for item in page_files if isinstance(item, dict))
            if len(page_files) < 100:
                return files
            page += 1

    def _get_json(self, path: str) -> Any:
        body = self._request(path, accept="application/vnd.github+json")
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise GitHubClientError("GitHub returned invalid JSON.") from exc

    def _get_text(self, path: str, accept: str) -> str:
        return self._request(path, accept=accept)

    def _request(self, path: str, accept: str) -> str:
        url = f"{self._api_url}{path}"
        headers = {
            "Accept": accept,
            "User-Agent": "ShipGuard",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            raise GitHubClientError(_github_error_message(exc, self._token)) from exc
        except URLError as exc:
            raise GitHubClientError(f"GitHub request failed: {exc.reason}") from exc


def format_pr_prompt(summary: PRChangeSummary) -> str:
    changed_files = "\n".join(f"- {path}" for path in summary.changed_files) or "- None"
    extensions = ", ".join(summary.changed_file_extensions) or "none"
    body = summary.body or "(no PR description)"
    truncated_note = (
        f"The PR diff was truncated to {summary.max_diff_chars} characters. "
        "Reason only from the visible diff and call out that additional risk may be hidden."
        if summary.diff_truncated
        else "The full PR diff was included."
    )

    return f"""Analyze this GitHub pull request release risk based on the metadata and diff below.

PR URL: {summary.pr_url}
Repository: {summary.owner}/{summary.repo}
PR number: {summary.pr_number}
Title: {summary.title}
Body:
{body}

State: {summary.state}
Base branch: {summary.base_branch}
Head branch: {summary.head_branch}
Base SHA: {summary.base_sha}
Head SHA: {summary.head_sha}
Changed files count: {summary.changed_files_count}
Additions: {summary.additions}
Deletions: {summary.deletions}
Changed file extensions: {extensions}
Diff size limit: {summary.max_diff_chars} characters
Diff truncation: {truncated_note}

Changed files:
{changed_files}

PR diff:
```diff
{summary.diff}
```
"""


def _pull_request_path(pr: GitHubPRRef) -> str:
    owner = quote(pr.owner, safe="")
    repo = quote(pr.repo, safe="")
    return f"/repos/{owner}/{repo}/pulls/{pr.number}"


def _nested_str(data: dict[str, Any], section: str, key: str) -> str:
    value = data.get(section)
    if not isinstance(value, dict):
        return "unknown"
    return str(value.get(key) or "unknown")


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _file_extensions(paths: list[str]) -> list[str]:
    extensions = {Path(path).suffix.lower() for path in paths if Path(path).suffix}
    return sorted(extensions)


def _truncate(content: str, max_chars: int) -> tuple[str, bool]:
    if len(content) <= max_chars:
        return content, False

    marker = "\n\n[ShipGuard: PR diff truncated because it exceeded the size limit]\n"
    if max_chars <= len(marker):
        return marker[:max_chars], True

    keep_chars = max(max_chars - len(marker), 0)
    return content[:keep_chars].rstrip() + marker, True


def _github_error_message(exc: HTTPError, token: str | None) -> str:
    base = f"GitHub API request failed with HTTP {exc.code}."
    if exc.code in {401, 403, 404} and not token:
        return (
            f"{base} If this is a private repository or you are rate limited, "
            "set SHIPGUARD_GITHUB_TOKEN and try again."
        )
    if exc.code == 403:
        return f"{base} Check repository access or GitHub rate limits."
    if exc.code == 404:
        return f"{base} Check that the PR URL exists and the token has access."
    return base
