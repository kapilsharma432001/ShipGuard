import tempfile
import unittest
from pathlib import Path

from shipguard.models import GitHubPRRef, PRChangeSummary, ReleaseRiskReport
from shipguard.pr_commenter import (
    INLINE_MARKER,
    SUMMARY_MARKER,
    DiffLineMapper,
    build_comment_plan,
    build_summary_comment,
    post_summary_comment,
    save_comment_preview,
)
from shipguard.report_generator import ReportArtifacts


class FakeGitHubCommentClient:
    has_token = True

    def __init__(self, existing_comments: list[dict[str, object]] | None = None) -> None:
        self.existing_comments = existing_comments or []
        self.created_issue_comments: list[str] = []
        self.updated_issue_comments: list[tuple[int, str]] = []

    def list_issue_comments(
        self,
        owner: str,
        repo: str,
        issue_number: int,
    ) -> list[dict[str, object]]:
        return self.existing_comments

    def update_issue_comment(
        self,
        owner: str,
        repo: str,
        comment_id: int,
        body: str,
    ) -> dict[str, object]:
        self.updated_issue_comments.append((comment_id, body))
        return {"id": comment_id, "body": body}

    def create_issue_comment(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        body: str,
    ) -> dict[str, object]:
        self.created_issue_comments.append(body)
        return {"id": 99, "body": body}


class PRCommenterTests(unittest.TestCase):
    def test_summary_comment_uses_easy_language_and_marker(self) -> None:
        body = build_summary_comment(
            pr_summary=_pr_summary(),
            report=_risk_report(),
            artifacts=_artifacts(),
            skipped_inline_notes=["app/routes/claims.py: public API contract changed"],
        )

        self.assertIn(SUMMARY_MARKER, body)
        self.assertIn("## ShipGuard Release Review", body)
        self.assertIn("Release readiness: 46/100", body)
        self.assertIn("Decision: BLOCK_RELEASE", body)
        self.assertIn("What worries me:", body)
        self.assertIn("Suggested next steps:", body)
        self.assertIn("release_passport.html", body)

    def test_diff_line_mapper_maps_added_lines_to_right_side(self) -> None:
        mapper = DiffLineMapper.from_diff(_diff())
        line = mapper.first_added_matching(
            "alembic/versions/002_claim_status.py",
            [r"nullable=False"],
        )

        self.assertIsNotNone(line)
        self.assertEqual(line.path, "alembic/versions/002_claim_status.py")
        self.assertEqual(line.line, 11)
        self.assertEqual(line.side, "RIGHT")

    def test_existing_summary_comment_is_updated_not_duplicated(self) -> None:
        client = FakeGitHubCommentClient(
            existing_comments=[
                {"id": 12, "body": f"{SUMMARY_MARKER}\nold summary"},
            ]
        )

        action = post_summary_comment(
            github_client=client,
            pr_ref=GitHubPRRef(
                owner="example",
                repo="claims-api",
                number=42,
                url="https://github.com/example/claims-api/pull/42",
            ),
            body=f"{SUMMARY_MARKER}\nnew summary",
        )

        self.assertEqual(action, "updated")
        self.assertEqual(len(client.updated_issue_comments), 1)
        self.assertEqual(len(client.created_issue_comments), 0)

    def test_dry_run_preview_file_is_written(self) -> None:
        plan = build_comment_plan(
            pr_summary=_pr_summary(),
            report=_risk_report(),
            artifacts=_artifacts(),
            max_inline_comments=5,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            preview_path = save_comment_preview(plan, Path(tmp_dir))

            self.assertTrue(preview_path.is_file())
            preview = preview_path.read_text(encoding="utf-8")
            self.assertIn("# ShipGuard PR Comment Preview", preview)
            self.assertIn(SUMMARY_MARKER, preview)
            self.assertIn(INLINE_MARKER, preview)
            self.assertEqual(plan.preview_path, str(preview_path))

    def test_report_risks_are_anchored_to_changed_lines(self) -> None:
        plan = build_comment_plan(
            pr_summary=_comment_feature_pr_summary(),
            report=_comment_feature_risk_report(),
            artifacts=_artifacts(),
            max_inline_comments=5,
        )

        self.assertGreaterEqual(len(plan.inline_comments), 2)
        bodies = "\n".join(comment.body for comment in plan.inline_comments)
        paths = {comment.path for comment in plan.inline_comments}

        self.assertIn("Suggested change:", bodies)
        self.assertIn(INLINE_MARKER, bodies)
        self.assertTrue(
            {"shipguard/cli.py", "shipguard/pr_commenter.py"} & paths
        )


def _pr_summary() -> PRChangeSummary:
    return PRChangeSummary(
        pr_url="https://github.com/example/claims-api/pull/42",
        owner="example",
        repo="claims-api",
        pr_number=42,
        title="Risky claims release",
        body="Changes claims API behavior.",
        state="open",
        base_branch="main",
        head_branch="feature/claims-release",
        base_sha="base-sha",
        head_sha="head-sha",
        changed_files_count=3,
        additions=20,
        deletions=5,
        changed_files=[
            "alembic/versions/002_claim_status.py",
            "app/routes/claims.py",
            "app/settings.py",
        ],
        changed_file_extensions=[".py"],
        included_files=[
            "alembic/versions/002_claim_status.py",
            "app/routes/claims.py",
            "app/settings.py",
        ],
        omitted_files=[],
        partially_included_files=[],
        diff_strategy="test",
        diff=_diff(),
        diff_truncated=False,
        max_diff_chars=120_000,
    )


def _risk_report() -> ReleaseRiskReport:
    return ReleaseRiskReport(
        release_readiness_score=46,
        decision="BLOCK_RELEASE",
        risk_level="HIGH",
        what_may_break=[
            "Old API consumers may break because enum values changed.",
            "Migration may fail on existing production data.",
            "Rollback is not safe.",
            "Config/env evidence is missing.",
        ],
        what_ci_may_miss=[
            "CI may pass on an empty database.",
            "CI may not test old clients.",
            "CI may not verify rollback.",
        ],
    )


def _comment_feature_pr_summary() -> PRChangeSummary:
    return PRChangeSummary(
        pr_url="https://github.com/example/shipguard/pull/8",
        owner="example",
        repo="shipguard",
        pr_number=8,
        title="Add PR comments",
        body="Adds GitHub PR summary and inline comments.",
        state="open",
        base_branch="main",
        head_branch="feature/pr-comments",
        base_sha="base-sha",
        head_sha="head-sha",
        changed_files_count=3,
        additions=80,
        deletions=2,
        changed_files=[
            "shipguard/cli.py",
            "shipguard/pr_commenter.py",
            "shipguard/github_client.py",
        ],
        changed_file_extensions=[".py"],
        included_files=[
            "shipguard/cli.py",
            "shipguard/pr_commenter.py",
            "shipguard/github_client.py",
        ],
        omitted_files=[],
        partially_included_files=[],
        diff_strategy="test",
        diff=_comment_feature_diff(),
        diff_truncated=False,
        max_diff_chars=120_000,
    )


def _comment_feature_risk_report() -> ReleaseRiskReport:
    return ReleaseRiskReport(
        release_readiness_score=63,
        decision="REVIEW_REQUIRED",
        risk_level="MEDIUM",
        what_may_break=[
            "`analyze-pr` now has new side effects when comment flags are used: it writes `pr_comment_preview.md`, which can fail in read-only workspaces.",
            "Posting or clearing comments now requires `SHIPGUARD_GITHUB_TOKEN` with comment/review write permissions; read-only tokens can fail with 401/403.",
            "Inline review posting is coupled to `pr_summary.head_sha`; force-pushed PRs can make GitHub reject the review.",
        ],
        what_ci_may_miss=[
            "CI may not exercise real GitHub write calls.",
        ],
    )


def _artifacts() -> ReportArtifacts:
    return ReportArtifacts(
        markdown_path=".shipguard/reports/example_claims-api_pr_42/release_passport.md",
        html_path=".shipguard/reports/example_claims-api_pr_42/release_passport.html",
        analysis_json_path=".shipguard/reports/example_claims-api_pr_42/analysis.json",
    )


def _diff() -> str:
    return """diff --git a/alembic/versions/002_claim_status.py b/alembic/versions/002_claim_status.py
--- a/alembic/versions/002_claim_status.py
+++ b/alembic/versions/002_claim_status.py
@@ -9,4 +9,5 @@ def upgrade():
     op.add_column("claims", sa.Column("status", sa.String()))
     op.execute("UPDATE claims SET status = 'PENDING'")
+    op.add_column("claims", sa.Column("reviewer_id", sa.String(), nullable=False))
 
 def downgrade():
+    pass
diff --git a/app/routes/claims.py b/app/routes/claims.py
--- a/app/routes/claims.py
+++ b/app/routes/claims.py
@@ -20,4 +20,4 @@ def map_status(status):
-    return "Denied"
+    return "DENIED"
diff --git a/app/settings.py b/app/settings.py
--- a/app/settings.py
+++ b/app/settings.py
@@ -1,2 +1,3 @@
 import os
+CLAIMS_GATEWAY_URL = os.getenv("CLAIMS_GATEWAY_URL")
"""


def _comment_feature_diff() -> str:
    return """diff --git a/shipguard/cli.py b/shipguard/cli.py
--- a/shipguard/cli.py
+++ b/shipguard/cli.py
@@ -170,3 +170,8 @@ def analyze_pr():
+    post_comment: bool = typer.Option(False, "--post-comment")
+    post_inline_comments: bool = typer.Option(False, "--post-inline-comments")
+    if post_comment or post_inline_comments:
+        save_comment_preview(comment_plan, report_dir=Path(artifacts.markdown_path).parent)
+        post_summary_comment(github_client=github_client, pr_ref=pr_ref, body=body)
diff --git a/shipguard/pr_commenter.py b/shipguard/pr_commenter.py
--- a/shipguard/pr_commenter.py
+++ b/shipguard/pr_commenter.py
@@ -1,3 +1,10 @@
+PREVIEW_FILE = "pr_comment_preview.md"
+def post_inline_review_comments(github_client, pr_summary, comments):
+    _require_github_token(github_client)
+    github_client.create_pull_request_review(
+        commit_id=pr_summary.head_sha,
+        comments=comments,
+    )
diff --git a/shipguard/github_client.py b/shipguard/github_client.py
--- a/shipguard/github_client.py
+++ b/shipguard/github_client.py
@@ -10,3 +10,8 @@ class GitHubClient:
+    def create_issue_comment(self, owner, repo, issue_number, body):
+        return self._send_json(path, method="POST", payload={"body": body})
+    def update_issue_comment(self, owner, repo, comment_id, body):
+        return self._send_json(path, method="PATCH", payload={"body": body})
+    def delete_issue_comment(self, owner, repo, comment_id):
+        return self._request(path, method="DELETE")
"""


if __name__ == "__main__":
    unittest.main()
