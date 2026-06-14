import json
import tempfile
import unittest
from pathlib import Path

from shipguard.models import PRChangeSummary, ReleaseRiskReport
from shipguard.report_generator import generate_release_passport


class ReportGeneratorTests(unittest.TestCase):
    def test_generates_markdown_json_and_optional_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifacts = generate_release_passport(
                pr_summary=_pr_summary(),
                report=_risk_report(),
                include_html=True,
                output_root=Path(tmp_dir),
            )

            markdown_path = Path(artifacts.markdown_path)
            html_path = Path(artifacts.html_path or "")
            json_path = Path(artifacts.analysis_json_path)
            self.assertTrue(markdown_path.is_file())
            self.assertTrue(html_path.is_file())
            self.assertTrue(json_path.is_file())

            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertIn("# ShipGuard Release Passport", markdown)
            self.assertIn("## Safer rollout plan", markdown)
            self.assertIn("## Rollback plan", markdown)

            html = html_path.read_text(encoding="utf-8")
            self.assertIn("ShipGuard Release Passport", html)
            self.assertIn(
                "CI tells you whether tests passed. ShipGuard helps identify "
                "whether the release looks risky.",
                html,
            )
            self.assertIn("<style>", html)
            self.assertNotIn("https://cdn", html.lower())
            self.assertNotIn("react", html.lower())

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["pr"]["pr_number"], 42)
            self.assertEqual(
                payload["release_risk_report"]["decision"],
                "REVIEW_REQUIRED",
            )
            self.assertEqual(
                payload["generated_artifact_paths"]["html_path"],
                artifacts.html_path,
            )

    def test_html_is_not_generated_without_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifacts = generate_release_passport(
                pr_summary=_pr_summary(),
                report=_risk_report(),
                include_html=False,
                output_root=Path(tmp_dir),
            )

            self.assertTrue(Path(artifacts.markdown_path).is_file())
            self.assertTrue(Path(artifacts.analysis_json_path).is_file())
            self.assertIsNone(artifacts.html_path)
            report_dir = Path(artifacts.markdown_path).parent
            self.assertFalse((report_dir / "release_passport.html").exists())


def _pr_summary() -> PRChangeSummary:
    return PRChangeSummary(
        pr_url="https://github.com/example/claims-api/pull/42",
        owner="example",
        repo="claims-api",
        pr_number=42,
        title="Change claims decision contract",
        body="Adds a new claims decision response.",
        state="open",
        base_branch="main",
        head_branch="feature/claims-contract",
        base_sha="base-sha",
        head_sha="head-sha",
        changed_files_count=3,
        additions=24,
        deletions=6,
        changed_files=[
            "app/routes/claims.py",
            "alembic/versions/002_claim_status.py",
            "docker-compose.yml",
        ],
        changed_file_extensions=[".py", ".yml"],
        included_files=["app/routes/claims.py"],
        omitted_files=["docker-compose.yml"],
        partially_included_files=["alembic/versions/002_claim_status.py"],
        diff_strategy="risk-prioritized test packing",
        diff="diff --git a/app/routes/claims.py b/app/routes/claims.py\n+changed",
        diff_truncated=True,
        max_diff_chars=120_000,
    )


def _risk_report() -> ReleaseRiskReport:
    return ReleaseRiskReport(
        release_readiness_score=58,
        decision="REVIEW_REQUIRED",
        risk_level="HIGH",
        what_may_break=[
            "Claims API consumers may break when enum values or response fields change.",
            "Database migration may lock writes if applied without a backfill.",
        ],
        what_ci_may_miss=[
            "CI may not exercise old API clients.",
            "CI may not validate production-sized migration behavior.",
        ],
    )


if __name__ == "__main__":
    unittest.main()
