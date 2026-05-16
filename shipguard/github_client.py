from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from shipguard.env_loader import load_env_file
from shipguard.models import GitHubPRRef, PRChangeSummary


GITHUB_API_URL = "https://api.github.com"
DEFAULT_PR_MAX_DIFF_CHARS = 120_000
DIFF_STRATEGY = (
    "risk-prioritized per-file diff packing: high-risk file diffs first, "
    "then medium-risk file diffs, then low-risk file diffs as budget allows; "
    "oversized file diffs use beginning/end excerpts"
)
PARTIAL_DIFF_MARKER = (
    "\n\n[ShipGuard: middle of this file diff omitted because it exceeded "
    "the remaining PR diff context budget]\n\n"
)


class GitHubClientError(RuntimeError):
    """Raised when ShipGuard cannot fetch GitHub PR data."""


class GitHubClient:
    def __init__(self, token: str | None = None, api_url: str = GITHUB_API_URL) -> None:
        self._token = token.strip() if token else None
        self._api_url = api_url.rstrip("/")

    @classmethod
    def from_env(cls) -> "GitHubClient":
        load_env_file(override=True)
        return cls(token=os.getenv("SHIPGUARD_GITHUB_TOKEN"))

    def fetch_pr_changes(
        self,
        pr: GitHubPRRef,
        max_diff_chars: int = DEFAULT_PR_MAX_DIFF_CHARS,
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

        changed_files = [file["filename"] for file in files if file.get("filename")]
        packed_diff = _pack_pr_diff(
            diff=diff,
            changed_files=changed_files,
            max_chars=max_diff_chars,
        )

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
            included_files=packed_diff["included_files"],
            omitted_files=packed_diff["omitted_files"],
            partially_included_files=packed_diff["partially_included_files"],
            diff_strategy=DIFF_STRATEGY,
            diff=packed_diff["diff"],
            diff_truncated=bool(
                packed_diff["omitted_files"] or packed_diff["partially_included_files"]
            ),
            max_diff_chars=max_diff_chars,
        )

    def fetch_repository_metadata(self, owner: str, repo: str) -> dict[str, Any]:
        metadata = self._get_json(_repository_path(owner, repo))
        if not isinstance(metadata, dict):
            raise GitHubClientError("GitHub returned an unexpected repository response.")
        return metadata

    def fetch_recursive_tree(
        self,
        owner: str,
        repo: str,
        ref: str,
    ) -> list[dict[str, Any]]:
        tree = self._get_tree(owner, repo, ref, recursive=True)
        if tree["truncated"]:
            raise GitHubClientError(
                "GitHub recursive tree response was truncated. Use "
                "fetch_repository_tree to receive truncation metadata and fallback "
                "subtree traversal."
            )

        return tree["tree"]

    def fetch_repository_tree(
        self,
        owner: str,
        repo: str,
        ref: str,
    ) -> tuple[list[dict[str, Any]], bool, str | None]:
        recursive = self._get_tree(owner, repo, ref, recursive=True)
        tree = recursive["tree"]
        if not recursive["truncated"]:
            return tree, False, None

        warning = (
            "GitHub recursive tree response was truncated; ShipGuard fetched "
            "subtrees non-recursively to build a complete inventory."
        )
        complete_tree = self._fetch_tree_subtrees(owner, repo, ref)
        return complete_tree, True, warning

    def fetch_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str,
        max_bytes: int = 200_000,
    ) -> str | None:
        content_path = (
            f"{_repository_path(owner, repo)}/contents/{quote(path, safe='/')}"
            f"?ref={quote(ref, safe='')}"
        )
        payload = self._get_json(content_path)
        if not isinstance(payload, dict):
            return None

        if int(payload.get("size") or 0) > max_bytes:
            return None
        if payload.get("encoding") != "base64" or not isinstance(
            payload.get("content"),
            str,
        ):
            return None

        try:
            raw = base64.b64decode(payload["content"].replace("\n", ""))
        except ValueError:
            return None

        if len(raw) > max_bytes or _looks_binary(raw):
            return None

        return raw.decode("utf-8", errors="replace")

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

    def _get_tree(
        self,
        owner: str,
        repo: str,
        ref: str,
        recursive: bool,
    ) -> dict[str, Any]:
        suffix = "?recursive=1" if recursive else ""
        payload = self._get_json(
            f"{_repository_path(owner, repo)}/git/trees/{quote(ref, safe='')}{suffix}"
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("tree"), list):
            raise GitHubClientError(
                "GitHub returned an unexpected repository tree response."
            )

        return {
            "tree": [item for item in payload["tree"] if isinstance(item, dict)],
            "truncated": bool(payload.get("truncated")),
        }

    def _fetch_tree_subtrees(
        self,
        owner: str,
        repo: str,
        ref: str,
    ) -> list[dict[str, Any]]:
        root = self._get_tree(owner, repo, ref, recursive=False)["tree"]
        complete: list[dict[str, Any]] = []
        stack = list(root)

        while stack:
            item = stack.pop(0)
            complete.append(item)
            if item.get("type") != "tree" or not isinstance(item.get("sha"), str):
                continue

            subtree = self._get_tree(owner, repo, item["sha"], recursive=False)["tree"]
            parent_path = item.get("path")
            if not isinstance(parent_path, str):
                continue
            for child in subtree:
                child_path = child.get("path")
                if isinstance(child_path, str):
                    child = {**child, "path": f"{parent_path}/{child_path}"}
                stack.append(child)

        return complete

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


def format_pr_prompt(summary: PRChangeSummary, memory_context: str | None = None) -> str:
    changed_files = "\n".join(f"- {path}" for path in summary.changed_files) or "- None"
    extensions = ", ".join(summary.changed_file_extensions) or "none"
    body = summary.body or "(no PR description)"
    included_files = _format_file_list(summary.included_files)
    partial_files = _format_file_list(summary.partially_included_files)
    omitted_files = _format_file_list(summary.omitted_files)
    diff_note = (
        "Some file diffs were omitted or partially included. Treat omitted risky files "
        "as missing evidence and mention that manual review is needed."
        if summary.diff_truncated
        else "Every changed file diff was included in full."
    )

    if memory_context:
        memory_instruction = (
            "Do not review this PR in isolation. Use project memory to identify "
            "compatibility, migration, config, rollback, and testing risks."
        )
        memory_section = memory_context
    else:
        memory_instruction = "Project memory was disabled for this analysis."
        memory_section = "Project memory: not used for this analysis."

    return f"""Analyze this GitHub pull request release risk based on the metadata and diff below.
{memory_instruction}

{memory_section}

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
PR diff context budget: {summary.max_diff_chars} characters
PR diff packing strategy: {summary.diff_strategy}
PR diff completeness: {diff_note}

Changed files (complete list):
{changed_files}

Included full file diffs:
{included_files}

Partially included file diffs:
{partial_files}

Omitted files due to context budget:
{omitted_files}

Important: the changed file list is complete even when the diff content below is partial.
If omitted or partially included files look release-risk sensitive, call that out as
missing evidence requiring manual review.

PR diff context:
```diff
{summary.diff}
```
"""


def _pull_request_path(pr: GitHubPRRef) -> str:
    return f"{_repository_path(pr.owner, pr.repo)}/pulls/{pr.number}"


def _repository_path(owner: str, repo: str) -> str:
    return f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"


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


def _looks_binary(content: bytes) -> bool:
    return b"\x00" in content[:1024]


def _pack_pr_diff(
    diff: str,
    changed_files: list[str],
    max_chars: int,
) -> dict[str, Any]:
    sections = _split_diff_by_file(diff)
    ordered_files = sorted(
        changed_files,
        key=lambda path: (_risk_priority(path), changed_files.index(path)),
    )
    included_files: list[str] = []
    omitted_files: list[str] = []
    partially_included_files: list[str] = []
    packed_sections: list[str] = []
    used_chars = 0

    for path in ordered_files:
        section = sections.get(path) or _missing_file_diff_section(path)
        prefix = "" if not packed_sections else "\n"
        full_section = f"{prefix}{section.rstrip()}\n"
        remaining = max_chars - used_chars

        if remaining <= 0:
            omitted_files.append(path)
            continue

        if len(full_section) <= remaining:
            packed_sections.append(full_section)
            included_files.append(path)
            used_chars += len(full_section)
            continue

        partial_section = _partial_file_diff(full_section, remaining)
        if partial_section:
            packed_sections.append(partial_section)
            partially_included_files.append(path)
            used_chars += len(partial_section)
        else:
            omitted_files.append(path)

    return {
        "diff": "".join(packed_sections).rstrip(),
        "included_files": included_files,
        "omitted_files": omitted_files,
        "partially_included_files": partially_included_files,
    }


def _split_diff_by_file(diff: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current: list[str] = []

    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            _store_diff_section(sections, current)
            current = [line]
        elif current:
            current.append(line)

    _store_diff_section(sections, current)
    return sections


def _store_diff_section(sections: dict[str, str], lines: list[str]) -> None:
    if not lines:
        return

    path = _diff_section_path(lines)
    if path:
        sections[path] = "".join(lines)


def _diff_section_path(lines: list[str]) -> str | None:
    old_path: str | None = None

    for line in lines:
        if line.startswith("+++ "):
            path = _normalize_diff_path(line[4:].strip())
            if path:
                return path
        if line.startswith("--- "):
            old_path = _normalize_diff_path(line[4:].strip())

    return old_path or _diff_git_path(lines[0])


def _diff_git_path(line: str) -> str | None:
    parts = line.strip().split()
    if len(parts) < 4 or parts[0:2] != ["diff", "--git"]:
        return None

    return _normalize_diff_path(parts[3]) or _normalize_diff_path(parts[2])


def _normalize_diff_path(path: str) -> str | None:
    path = path.strip('"')
    if path == "/dev/null":
        return None
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def _missing_file_diff_section(path: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        "[ShipGuard: GitHub changed-files API listed this file, but the PR "
        "diff did not include a text diff section for it]\n"
    )


def _partial_file_diff(section: str, max_chars: int) -> str:
    if max_chars <= len(PARTIAL_DIFF_MARKER) + 80:
        return ""

    available = max_chars - len(PARTIAL_DIFF_MARKER)
    head_chars = max(available // 2, 0)
    tail_chars = max(available - head_chars, 0)
    return (
        section[:head_chars].rstrip()
        + PARTIAL_DIFF_MARKER
        + section[-tail_chars:].lstrip()
    )


def _risk_priority(path: str) -> int:
    lower_path = path.lower()
    name = Path(lower_path).name
    parts = set(Path(lower_path).parts)

    if (
        {"migrations", "alembic", "versions"} & parts
        or "migration" in lower_path
        or name in _DEPENDENCY_FILES
        or name.endswith(".lock")
        or lower_path.startswith("api/")
        or "/api/" in lower_path
        or {"routes", "schemas", "pydantic"} & parts
        or "schema" in name
        or "pydantic" in lower_path
        or {"config", "settings", "env", "docker", "deployment"} & parts
        or any(term in name for term in ("config", "settings", "env"))
        or name.startswith(".env")
        or name in {"dockerfile", "docker-compose.yml", "docker-compose.yaml"}
        or "deploy" in lower_path
        or {"auth", "security", "permission", "permissions", "token"} & parts
        or any(term in lower_path for term in ("auth", "security", "permission", "token"))
    ):
        return 0

    if (
        {"service", "services", "business", "domain", "db", "database", "models"} & parts
        or "service" in lower_path
        or "business" in lower_path
        or "model" in name
        or name.startswith("test_")
        or name.endswith("_test.py")
        or {"test", "tests"} & parts
    ):
        return 1

    if (
        name.startswith("readme")
        or {"doc", "docs", "documentation"} & parts
        or lower_path.endswith((".md", ".rst", ".txt"))
        or name in {".editorconfig", ".prettierrc", ".prettierignore"}
    ):
        return 2

    return 1


def _format_file_list(paths: list[str]) -> str:
    return "\n".join(f"- {path}" for path in paths) if paths else "- None"


_DEPENDENCY_FILES = {
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "poetry.lock",
    "pdm.lock",
    "pipfile",
    "pipfile.lock",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "uv.lock",
    "go.mod",
    "go.sum",
    "cargo.toml",
    "cargo.lock",
}


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
