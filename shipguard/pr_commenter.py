from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shipguard.context_builder import classify_file
from shipguard.github_client import GitHubClient, GitHubClientError
from shipguard.models import (
    GitHubPRRef,
    PRChangeSummary,
    PRCommentPlan,
    PRCommentResult,
    PRInlineCommentSuggestion,
    ReleaseRiskReport,
)
from shipguard.report_generator import ReportArtifacts, ReportGenerationError


SUMMARY_MARKER = "<!-- shipguard:summary -->"
INLINE_MARKER = "<!-- shipguard:inline -->"
PREVIEW_FILE = "pr_comment_preview.md"


@dataclass(frozen=True)
class DiffLine:
    path: str
    line: int
    side: str
    content: str


class DiffLineMapper:
    def __init__(self, lines: list[DiffLine]) -> None:
        self._lines = lines

    @classmethod
    def from_diff(cls, diff: str) -> "DiffLineMapper":
        lines: list[DiffLine] = []
        path: str | None = None
        old_line = 0
        new_line = 0
        in_hunk = False

        for raw_line in diff.splitlines():
            if raw_line.startswith("diff --git "):
                path = _diff_git_path(raw_line)
                in_hunk = False
                continue
            if raw_line.startswith("+++ "):
                normalized = _normalize_diff_path(raw_line[4:].strip())
                if normalized:
                    path = normalized
                continue
            if raw_line.startswith("@@ "):
                match = re.match(
                    r"@@ -(?P<old>\d+)(?:,\d+)? \+(?P<new>\d+)(?:,\d+)? @@",
                    raw_line,
                )
                if not match:
                    in_hunk = False
                    continue
                old_line = int(match.group("old"))
                new_line = int(match.group("new"))
                in_hunk = True
                continue
            if not in_hunk or path is None:
                continue
            if raw_line.startswith("+") and not raw_line.startswith("+++"):
                lines.append(
                    DiffLine(
                        path=path,
                        line=new_line,
                        side="RIGHT",
                        content=raw_line[1:],
                    )
                )
                new_line += 1
            elif raw_line.startswith("-") and not raw_line.startswith("---"):
                lines.append(
                    DiffLine(
                        path=path,
                        line=old_line,
                        side="LEFT",
                        content=raw_line[1:],
                    )
                )
                old_line += 1
            else:
                old_line += 1
                new_line += 1

        return cls(lines)

    def added_lines(self, path: str) -> list[DiffLine]:
        return [
            line
            for line in self._lines
            if line.path == path and line.side == "RIGHT"
        ]

    def removed_lines(self, path: str) -> list[DiffLine]:
        return [
            line
            for line in self._lines
            if line.path == path and line.side == "LEFT"
        ]

    def first_added_matching(
        self,
        path: str,
        patterns: list[str],
    ) -> DiffLine | None:
        compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
        for line in self.added_lines(path):
            if any(pattern.search(line.content) for pattern in compiled):
                return line
        return None


def build_comment_plan(
    pr_summary: PRChangeSummary,
    report: ReleaseRiskReport,
    artifacts: ReportArtifacts,
    max_inline_comments: int = 5,
) -> PRCommentPlan:
    skipped_notes: list[str] = []
    inline_comments = build_inline_comment_suggestions(
        pr_summary=pr_summary,
        report=report,
        max_inline_comments=max_inline_comments,
        skipped_notes=skipped_notes,
    )
    summary_body = build_summary_comment(
        pr_summary=pr_summary,
        report=report,
        artifacts=artifacts,
        skipped_inline_notes=skipped_notes,
    )
    return PRCommentPlan(
        summary_body=summary_body,
        inline_comments=inline_comments,
        skipped_inline_notes=skipped_notes,
    )


def build_summary_comment(
    pr_summary: PRChangeSummary,
    report: ReleaseRiskReport,
    artifacts: ReportArtifacts,
    skipped_inline_notes: list[str] | None = None,
) -> str:
    risks = report.what_may_break[:5]
    ci_misses = report.what_ci_may_miss[:5]
    next_steps = _suggested_next_steps(report)
    skipped_inline_notes = skipped_inline_notes or []

    lines = [
        SUMMARY_MARKER,
        "",
        "## ShipGuard Release Review",
        "",
        "I reviewed this PR like a release reviewer, not just a code reviewer.",
        "",
        f"Release readiness: {report.release_readiness_score}/100",
        f"Decision: {report.decision.value}",
        f"Risk level: {report.risk_level.value}",
        "",
        "What worries me:",
        *_numbered(risks),
        "",
        "What CI may miss:",
        *_bullets(ci_misses),
        "",
        "Suggested next steps:",
        *_bullets(next_steps),
    ]

    if skipped_inline_notes:
        lines.extend(
            [
                "",
                "Inline notes I could not place safely:",
                *_bullets(skipped_inline_notes[:5]),
            ]
        )

    lines.extend(
        [
            "",
            "Generated artifacts:",
            f"- Markdown: `{artifacts.markdown_path}`",
            f"- JSON: `{artifacts.analysis_json_path}`",
        ]
    )
    if artifacts.html_path:
        lines.append(f"- HTML: `{artifacts.html_path}`")
        lines.append("")
        lines.append(
            "The full HTML report is generated locally or in the CI artifact path above."
        )
    else:
        lines.append("")
        lines.append("No HTML report was generated in this run. Use `--html` to create one.")

    return "\n".join(lines).strip() + "\n"


def build_inline_comment_suggestions(
    pr_summary: PRChangeSummary,
    report: ReleaseRiskReport | None = None,
    max_inline_comments: int = 5,
    skipped_notes: list[str] | None = None,
) -> list[PRInlineCommentSuggestion]:
    if max_inline_comments <= 0:
        return []

    skipped_notes = skipped_notes if skipped_notes is not None else []
    mapper = DiffLineMapper.from_diff(pr_summary.diff)
    comments: list[PRInlineCommentSuggestion] = []
    commented_paths: set[str] = set()
    tests_changed = any(classify_file(path) == "TEST" for path in pr_summary.changed_files)
    config_changed = any(
        classify_file(path) in {"CONFIG", "DEPLOYMENT", "CI_CD"}
        for path in pr_summary.changed_files
    )

    def add(line: DiffLine | None, body: str, reason: str, path: str) -> None:
        if len(comments) >= max_inline_comments or path in commented_paths:
            return
        if line is None:
            skipped_notes.append(f"{path}: {reason}")
            return
        comments.append(
            PRInlineCommentSuggestion(
                path=line.path,
                line=line.line,
                side=line.side,
                body=f"{body}\n\n{INLINE_MARKER}",
                reason=reason,
            )
        )
        commented_paths.add(path)

    for path in pr_summary.changed_files:
        if len(comments) >= max_inline_comments:
            break
        category = classify_file(path)
        added = mapper.added_lines(path)
        removed = mapper.removed_lines(path)
        if not added:
            continue

        if category == "MIGRATION":
            unsafe_column = _first_added_not_null_without_default(added)
            if unsafe_column:
                add(
                    unsafe_column,
                    (
                        "ShipGuard risk: this appears to add a required column without "
                        "a default or backfill. It may pass on an empty DB but fail on "
                        "production rows. Safer path: add it nullable, backfill, then "
                        "enforce NOT NULL."
                    ),
                    "unsafe required migration column",
                    path,
                )
                continue

            unsafe_rollback = mapper.first_added_matching(
                path,
                [r"\bpass\b", r"NotImplemented", r"drop_table", r"drop_column"],
            )
            if unsafe_rollback:
                add(
                    unsafe_rollback,
                    (
                        "ShipGuard risk: rollback evidence looks missing or destructive. "
                        "Please document a safe rollback or forward-fix path before release."
                    ),
                    "rollback evidence missing or unsafe",
                    path,
                )
                continue

        if category == "API" or _is_api_like_path(path):
            enum_change = _first_added_enum_contract_change(added, removed)
            line = enum_change or mapper.first_added_matching(
                path,
                [r"@\w+\.(get|post|put|delete|patch)\(", r"Field\(\.\.\.", r"response_model"],
            )
            if line:
                add(
                    line,
                    (
                        "ShipGuard risk: this changes a public request/response or route "
                        "contract. Old clients may break. Please add a backward "
                        "compatibility test or version this API."
                    ),
                    "public API contract changed",
                    path,
                )
                continue

        env_line = _first_added_env_var_usage(added)
        if (
            env_line
            and category in {"SOURCE", "API", "SERVICE", "DB_MODEL", "SECURITY"}
            and not config_changed
        ):
            add(
                env_line,
                (
                    "ShipGuard risk: code uses a new environment variable, but this PR "
                    "does not show matching deployment/config evidence. This can fail "
                    "after deployment."
                ),
                "new environment variable without config evidence",
                path,
            )
            continue

    risky_without_tests = [
        path
        for path in pr_summary.changed_files
        if classify_file(path) in {"API", "MIGRATION", "DB_MODEL", "CONFIG", "DEPLOYMENT"}
    ]
    if risky_without_tests and not tests_changed:
        skipped_notes.append(
            "I did not see test files changed for release-sensitive files: "
            + ", ".join(risky_without_tests[:5])
        )

    if report is not None and len(comments) < max_inline_comments:
        _add_report_risk_comments(
            mapper=mapper,
            pr_summary=pr_summary,
            report=report,
            comments=comments,
            commented_paths=commented_paths,
            max_inline_comments=max_inline_comments,
        )

    return comments


def save_comment_preview(plan: PRCommentPlan, report_dir: Path) -> Path:
    preview_path = report_dir / PREVIEW_FILE
    content = _render_preview(plan)
    try:
        report_dir.mkdir(parents=True, exist_ok=True)
        preview_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise ReportGenerationError(f"could not write comment preview: {preview_path}") from exc
    plan.preview_path = str(preview_path)
    return preview_path


def post_summary_comment(
    github_client: GitHubClient,
    pr_ref: GitHubPRRef,
    body: str,
) -> str:
    _require_github_token(github_client)
    comments = github_client.list_issue_comments(pr_ref.owner, pr_ref.repo, pr_ref.number)
    existing = _find_marker_comment(comments, SUMMARY_MARKER)
    if existing is not None:
        comment_id = int(existing["id"])
        github_client.update_issue_comment(pr_ref.owner, pr_ref.repo, comment_id, body)
        return "updated"

    github_client.create_issue_comment(pr_ref.owner, pr_ref.repo, pr_ref.number, body)
    return "created"


def post_inline_review_comments(
    github_client: GitHubClient,
    pr_summary: PRChangeSummary,
    comments: list[PRInlineCommentSuggestion],
    request_changes: bool = False,
) -> int:
    _require_github_token(github_client)
    if not comments:
        return 0
    event = "REQUEST_CHANGES" if request_changes else "COMMENT"
    github_client.create_pull_request_review(
        owner=pr_summary.owner,
        repo=pr_summary.repo,
        pull_number=pr_summary.pr_number,
        commit_id=pr_summary.head_sha,
        body="ShipGuard inline release-risk notes.",
        event=event,
        comments=[comment.model_dump(mode="json") for comment in comments],
    )
    return len(comments)


def clear_shipguard_comments(
    github_client: GitHubClient,
    pr_ref: GitHubPRRef,
) -> PRCommentResult:
    _require_github_token(github_client)
    result = PRCommentResult()

    for comment in github_client.list_issue_comments(pr_ref.owner, pr_ref.repo, pr_ref.number):
        if SUMMARY_MARKER not in str(comment.get("body") or ""):
            continue
        try:
            github_client.delete_issue_comment(
                pr_ref.owner,
                pr_ref.repo,
                int(comment["id"]),
            )
            result.deleted_summary_comments += 1
        except (GitHubClientError, KeyError, TypeError, ValueError) as exc:
            result.warnings.append(f"Could not delete summary comment: {exc}")

    for comment in github_client.list_pull_request_review_comments(
        pr_ref.owner,
        pr_ref.repo,
        pr_ref.number,
    ):
        if INLINE_MARKER not in str(comment.get("body") or ""):
            continue
        try:
            github_client.delete_pull_request_review_comment(
                pr_ref.owner,
                pr_ref.repo,
                int(comment["id"]),
            )
            result.deleted_inline_comments += 1
        except (GitHubClientError, KeyError, TypeError, ValueError) as exc:
            result.warnings.append(f"Could not delete inline comment: {exc}")

    return result


def _render_preview(plan: PRCommentPlan) -> str:
    lines = [
        "# ShipGuard PR Comment Preview",
        "",
        "## Top-level summary comment",
        "",
        plan.summary_body.rstrip(),
        "",
        "## Inline review comments",
        "",
    ]
    if plan.inline_comments:
        for index, comment in enumerate(plan.inline_comments, start=1):
            lines.extend(
                [
                    f"### {index}. `{comment.path}` line {comment.line} ({comment.side})",
                    "",
                    comment.body.rstrip(),
                    "",
                ]
            )
    else:
        lines.append("- No high-confidence inline comments were generated.")
        lines.append("")

    lines.extend(["## Inline notes not placed", ""])
    lines.extend(_bullets(plan.skipped_inline_notes) if plan.skipped_inline_notes else ["- None"])
    lines.append("")
    return "\n".join(lines)


def _find_marker_comment(comments: list[dict[str, Any]], marker: str) -> dict[str, Any] | None:
    for comment in comments:
        if marker in str(comment.get("body") or ""):
            return comment
    return None


def _require_github_token(github_client: GitHubClient) -> None:
    if not github_client.has_token:
        raise GitHubClientError(
            "SHIPGUARD_GITHUB_TOKEN is required to post or clear PR comments."
        )


def _first_added_not_null_without_default(lines: list[DiffLine]) -> DiffLine | None:
    for line in lines:
        content = line.content.lower()
        if ("nullable=false" in content or "not null" in content) and "default" not in content:
            return line
    return None


def _first_added_enum_contract_change(
    added: list[DiffLine],
    removed: list[DiffLine],
) -> DiffLine | None:
    removed_values = _quoted_values(removed)
    if not removed_values:
        return None
    for line in added:
        for value in _quoted_values([line]):
            if value.upper() in {item.upper() for item in removed_values} and value not in removed_values:
                return line
    return None


def _first_added_env_var_usage(lines: list[DiffLine]) -> DiffLine | None:
    for line in lines:
        if re.search(
            r"(os\.environ|os\.getenv|process\.env|environ\.get)\W+['\"]?[A-Z][A-Z0-9_]*",
            line.content,
        ):
            return line
    return None


def _quoted_values(lines: list[DiffLine]) -> list[str]:
    values: list[str] = []
    for line in lines:
        values.extend(re.findall(r"['\"]([A-Za-z][A-Za-z0-9_]*)['\"]", line.content))
    return values


def _add_report_risk_comments(
    mapper: DiffLineMapper,
    pr_summary: PRChangeSummary,
    report: ReleaseRiskReport,
    comments: list[PRInlineCommentSuggestion],
    commented_paths: set[str],
    max_inline_comments: int,
) -> None:
    for risk in report.what_may_break:
        if len(comments) >= max_inline_comments:
            return

        line = _best_changed_line_for_risk(
            mapper=mapper,
            changed_files=pr_summary.changed_files,
            risk=risk,
            commented_paths=commented_paths,
        )
        if line is None:
            continue

        comments.append(
            PRInlineCommentSuggestion(
                path=line.path,
                line=line.line,
                side=line.side,
                body=f"{_report_risk_comment_body(risk)}\n\n{INLINE_MARKER}",
                reason="release risk from analysis",
            )
        )
        commented_paths.add(line.path)


def _best_changed_line_for_risk(
    mapper: DiffLineMapper,
    changed_files: list[str],
    risk: str,
    commented_paths: set[str],
) -> DiffLine | None:
    risk_tokens = _tokens(risk)
    candidates: list[tuple[int, int, DiffLine]] = []

    for path_index, path in enumerate(changed_files):
        if path in commented_paths:
            continue

        category = classify_file(path)
        if not _should_consider_path_for_risk(category, risk_tokens):
            continue

        added_lines = mapper.added_lines(path)
        if not added_lines:
            continue

        path_score = _path_risk_score(path, risk_tokens)
        for line_index, line in enumerate(added_lines):
            score = path_score + _line_risk_score(line.content, risk_tokens)
            if score >= 3:
                candidates.append((score, -(path_index * 1000 + line_index), line))

    if not candidates:
        return None

    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def _path_risk_score(path: str, risk_tokens: set[str]) -> int:
    path_tokens = _tokens(path)
    category = classify_file(path)
    score = 2 * len(risk_tokens & path_tokens)

    if category == "TEST" and risk_tokens & {"ci", "test", "tests", "coverage"}:
        score += 3
    elif category == "TEST":
        score -= 3
    elif category == "DOCS":
        score -= 2

    for category_name, terms in _CATEGORY_RISK_TERMS.items():
        if category == category_name and risk_tokens & terms:
            score += 3

    if risk_tokens & {"comment", "comments", "inline", "review", "marker"}:
        if path_tokens & {"commenter", "comment", "comments", "github", "cli"}:
            score += 4

    return score


def _should_consider_path_for_risk(category: str, risk_tokens: set[str]) -> bool:
    if category == "TEST":
        return bool(risk_tokens & {"ci", "test", "tests", "coverage"})
    if category == "DOCS":
        return bool(risk_tokens & {"doc", "docs", "documentation", "readme"})
    return True


def _line_risk_score(content: str, risk_tokens: set[str]) -> int:
    line_tokens = _tokens(content)
    score = len(risk_tokens & line_tokens)
    lower_content = content.lower()
    for token in risk_tokens:
        if len(token) >= 6 and token in lower_content:
            score += 1
    return score


def _report_risk_comment_body(risk: str) -> str:
    return (
        "ShipGuard risk: "
        f"{_shorten(risk, 260)}\n\n"
        f"Suggested change: {_suggested_change_for_risk(risk)}"
    )


def _suggested_change_for_risk(risk: str) -> str:
    text = risk.lower()
    if any(term in text for term in ("preview", "filesystem", "read-only", "disk")):
        return (
            "Make this side effect explicit or non-fatal, and add a test for write "
            "failure so analysis does not fail unexpectedly."
        )
    if any(term in text for term in ("token", "permission", "401", "403", "scope")):
        return (
            "Validate required GitHub token permissions before posting and surface a "
            "specific remediation message when scopes are missing."
        )
    if any(term in text for term in ("clear-comments", "delete", "deletion", "marker")):
        return (
            "Tighten cleanup matching, such as checking both the marker and author, "
            "before deleting existing comments."
        )
    if any(term in text for term in ("head_sha", "force-push", "stale", "line mapping")):
        return (
            "Re-fetch the latest PR head before posting review comments and fall back "
            "to the summary comment if GitHub rejects a line."
        )
    if any(term in text for term in ("post", "patch", "delete", "rate limit", "network")):
        return (
            "Add targeted handling and tests for GitHub write failures so users know "
            "which API operation failed."
        )
    if any(term in text for term in ("heuristic", "regex", "classify_file", "pattern")):
        return (
            "Add representative fixtures for this file type and keep low-confidence "
            "findings in the summary instead of posting misleading inline comments."
        )
    if any(term in text for term in ("test", "ci", "coverage")):
        return "Add an end-to-end test that exercises this changed release path."
    if any(term in text for term in ("api", "client", "request", "response", "contract")):
        return "Add backward compatibility coverage or version the changed API contract."
    if any(term in text for term in ("migration", "database", "db", "rollback")):
        return "Document and test the production migration and rollback path."
    return "Add a guard or focused test around this changed behavior before merging."


def _shorten(value: str, max_chars: int) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip(" ,.;:") + "..."


def _tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for raw in re.findall(r"[A-Za-z0-9_./-]{2,}", value.lower()):
        normalized = raw.strip("`'\".,:;()[]{}")
        if not normalized:
            continue
        for token in [normalized, *re.split(r"[/_.-]+", normalized)]:
            if len(token) >= 2 and token not in _TOKEN_STOPWORDS:
                tokens.add(token)
    return tokens


def _suggested_next_steps(report: ReleaseRiskReport) -> list[str]:
    text = "\n".join([*report.what_may_break, *report.what_ci_may_miss]).lower()
    steps = ["Review the generated Release Passport before merging."]
    if any(term in text for term in ("api", "client", "enum", "request", "response")):
        steps.append("Add backward compatibility tests for old API clients.")
    if any(term in text for term in ("migration", "database", "db", "not null", "backfill")):
        steps.append("Make the migration safe using a nullable column, backfill, then NOT NULL later.")
    if any(term in text for term in ("rollback", "roll back")):
        steps.append("Add rollback evidence or a clear forward-fix plan.")
    if any(term in text for term in ("env", "config", "deployment", "secret")):
        steps.append("Confirm required env vars and deployment config are present.")
    if len(steps) == 1:
        steps.append("Ask a reviewer to validate the highest-risk release behavior manually.")
    return steps[:5]


def _is_api_like_path(path: str) -> bool:
    lower = path.lower()
    return any(
        term in lower
        for term in ("api", "route", "schema", "serializer", "controller", "endpoint")
    )


def _numbered(items: list[str]) -> list[str]:
    return [f"{index}. {item}" for index, item in enumerate(items, start=1)] or ["1. None"]


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] or ["- None"]


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


_CATEGORY_RISK_TERMS = {
    "API": {"api", "client", "contract", "request", "response", "route", "schema"},
    "CI_CD": {"ci", "workflow", "pipeline", "deploy", "deployment"},
    "CONFIG": {"config", "env", "environment", "secret", "token"},
    "DB_MODEL": {"database", "db", "model", "schema", "table"},
    "DEPLOYMENT": {"deploy", "deployment", "env", "config", "secret"},
    "MIGRATION": {"migration", "database", "db", "rollback", "backfill"},
    "SECURITY": {"auth", "permission", "security", "token", "scope"},
    "SERVICE": {"service", "business", "workflow", "operation"},
    "SOURCE": {"function", "class", "logic", "runtime", "side", "effect"},
}

_TOKEN_STOPWORDS = {
    "a",
    "an",
    "and",
    "any",
    "are",
    "as",
    "be",
    "but",
    "by",
    "can",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "may",
    "new",
    "no",
    "not",
    "now",
    "of",
    "old",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "when",
    "with",
    "without",
}
