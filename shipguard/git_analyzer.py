from __future__ import annotations

import subprocess
from pathlib import Path

from shipguard.models import GitChangeSummary


class GitAnalyzerError(RuntimeError):
    """Raised when ShipGuard cannot read git metadata from a repo."""


def collect_git_changes(repo: Path, max_diff_chars: int = 30_000) -> GitChangeSummary:
    if max_diff_chars <= 0:
        raise GitAnalyzerError("max diff characters must be greater than zero.")

    repo = repo.resolve()
    _ensure_git_repo(repo)

    status = _run_git(repo, "status", "--porcelain")
    diff = _run_git(repo, "diff", "--no-ext-diff", "HEAD", "--")
    diff_stat = _run_git(repo, "diff", "--stat", "HEAD", "--")
    changed_files = _changed_files(repo)

    truncated_diff, was_truncated = _truncate(diff, max_diff_chars)

    return GitChangeSummary(
        repo_path=str(repo),
        current_branch=_optional_git(repo, "branch", "--show-current"),
        latest_commit_hash=_optional_git(repo, "rev-parse", "--short", "HEAD"),
        has_uncommitted_changes=bool(status.strip()),
        changed_files=changed_files,
        changed_file_extensions=_file_extensions(changed_files),
        diff_stat=diff_stat.strip(),
        diff=truncated_diff,
        diff_truncated=was_truncated,
        max_diff_chars=max_diff_chars,
    )


def format_release_prompt(summary: GitChangeSummary) -> str:
    changed_files = "\n".join(f"- {path}" for path in summary.changed_files) or "- None"
    extensions = ", ".join(summary.changed_file_extensions) or "none"
    truncated_note = (
        f"The full git diff was truncated to {summary.max_diff_chars} characters. "
        "Reason only from the visible diff and call out that additional risk may be hidden."
        if summary.diff_truncated
        else "The full git diff was included."
    )
    diff = summary.diff or "(no git diff output)"
    diff_stat = summary.diff_stat or "(no git diff stat output)"

    return f"""Analyze this release based on the actual git diff below.

Repository: {summary.repo_path}
Current branch: {summary.current_branch or "unknown"}
Latest commit: {summary.latest_commit_hash or "unknown"}
Has uncommitted changes: {summary.has_uncommitted_changes}
Changed file extensions: {extensions}
Diff size limit: {summary.max_diff_chars} characters
Diff truncation: {truncated_note}

Changed files:
{changed_files}

Git diff --stat:
{diff_stat}

Git diff:
```diff
{diff}
```
"""


def _ensure_git_repo(repo: Path) -> None:
    result = _run_git_result(repo, "rev-parse", "--is-inside-work-tree")
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise GitAnalyzerError(f"not a git repository: {repo}")


def _changed_files(repo: Path) -> list[str]:
    diff_files = _run_git(repo, "diff", "--name-only", "HEAD", "--").splitlines()
    untracked_files = _run_git(
        repo,
        "ls-files",
        "--others",
        "--exclude-standard",
    ).splitlines()
    return sorted({path for path in [*diff_files, *untracked_files] if path})


def _file_extensions(paths: list[str]) -> list[str]:
    extensions = {Path(path).suffix.lower() for path in paths if Path(path).suffix}
    return sorted(extensions)


def _truncate(content: str, max_chars: int) -> tuple[str, bool]:
    if len(content) <= max_chars:
        return content, False

    marker = "\n\n[ShipGuard: git diff truncated because it exceeded the size limit]\n"
    if max_chars <= len(marker):
        return marker[:max_chars], True

    keep_chars = max(max_chars - len(marker), 0)
    return content[:keep_chars].rstrip() + marker, True


def _optional_git(repo: Path, *args: str) -> str | None:
    result = _run_git_result(repo, *args)
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _run_git(repo: Path, *args: str) -> str:
    result = _run_git_result(repo, *args)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise GitAnalyzerError(detail)
    return result.stdout


def _run_git_result(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise GitAnalyzerError("git executable was not found on PATH.") from exc
