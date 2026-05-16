import tempfile
import unittest
from pathlib import Path

from shipguard.context_builder import (
    classify_file,
    extract_file_context,
    load_or_build_project_context,
    update_memory_after_analysis,
)
from shipguard.models import PRChangeSummary, ReleaseRiskReport
from shipguard.project_memory import ProjectMemoryStore


class FakeGitHubClient:
    def __init__(self) -> None:
        self.tree = [
            {"path": "README.md", "type": "blob", "sha": "readme", "size": 1200},
            {"path": "src/app/routes/claims.py", "type": "blob", "sha": "api", "size": 3000},
            {"path": "src/app/services/claims_service.py", "type": "blob", "sha": "service", "size": 3000},
            {"path": "src/app/models/claim.py", "type": "blob", "sha": "model", "size": 3000},
            {"path": "alembic/versions/001_add_claim.py", "type": "blob", "sha": "migration", "size": 3000},
            {"path": "config/settings.py", "type": "blob", "sha": "settings", "size": 3000},
            {"path": "Dockerfile", "type": "blob", "sha": "docker", "size": 300},
            {"path": ".github/workflows/ci.yml", "type": "blob", "sha": "ci", "size": 300},
            {"path": "tests/test_claims.py", "type": "blob", "sha": "test", "size": 900},
            {"path": "auth/token.py", "type": "blob", "sha": "security", "size": 800},
            {"path": "frontend/components/ClaimCard.tsx", "type": "blob", "sha": "ui", "size": 900},
            {"path": "package.json", "type": "blob", "sha": "package", "size": 600},
            {"path": "src/main.py", "type": "blob", "sha": "source", "size": 600},
            {"path": "assets/logo.png", "type": "blob", "sha": "binary", "size": 400},
            {"path": "node_modules/pkg/index.js", "type": "blob", "sha": "vendor", "size": 400},
            {"path": "src/generated_large.py", "type": "blob", "sha": "large", "size": 250_001},
        ]
        self.content = {
            "README.md": "# Claims API\n",
            "src/app/routes/claims.py": (
                "from fastapi import APIRouter\n"
                "from src.app.services.claims_service import decide_claim\n"
                "router = APIRouter()\n"
                "@router.post('/claims/{claim_id}/decision')\n"
                "def decide(claim_id: str):\n"
                "    return decide_claim(claim_id)\n"
            ),
            "src/app/services/claims_service.py": (
                "import os\n"
                "def decide_claim(claim_id: str):\n"
                "    return os.getenv('CLAIMS_DECISION_MODE')\n"
            ),
            "src/app/models/claim.py": (
                "class Claim(Base):\n"
                "    __tablename__ = 'claims'\n"
            ),
            "alembic/versions/001_add_claim.py": (
                "from alembic import op\n"
                "def upgrade():\n"
                "    op.add_column('claims', sa.Column('reviewer_id', sa.String(), nullable=False))\n"
            ),
            "config/settings.py": "import os\nCLAIMS_TOKEN = os.environ['CLAIMS_TOKEN']\n",
            "Dockerfile": "FROM python:3.12-slim\n",
            ".github/workflows/ci.yml": "name: ci\n",
            "tests/test_claims.py": "import pytest\n\ndef test_claims():\n    assert True\n",
            "auth/token.py": "def verify_jwt(token: str):\n    return token\n",
            "frontend/components/ClaimCard.tsx": "import React from 'react'\nexport function ClaimCard() { return <div /> }\n",
            "package.json": '{"dependencies": {"fastapi": "^1.0.0", "react": "^18.0.0"}}',
            "src/main.py": "def main():\n    pass\n",
        }
        self.fetched_paths: list[str] = []

    def fetch_repository_metadata(self, owner: str, repo: str) -> dict[str, str]:
        return {"default_branch": "main"}

    def fetch_repository_tree(
        self,
        owner: str,
        repo: str,
        ref: str,
    ) -> tuple[list[dict[str, object]], bool, str | None]:
        return self.tree, True, "recursive tree was truncated; fallback traversal used"

    def fetch_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str,
        max_bytes: int = 200_000,
    ) -> str | None:
        self.fetched_paths.append(path)
        return self.content.get(path)


class FakeLLMClient:
    def summarize_project_context(self, project_context: str) -> dict[str, object]:
        return {
            "architecture_summary": "Claims service with API, database, deployment, and tests.",
            "important_components": ["src/app/routes/claims.py", "src/app/models/claim.py"],
            "known_api_surface": ["POST /claims/{claim_id}/decision"],
            "known_data_surface": ["claims"],
            "known_config_surface": ["CLAIMS_DECISION_MODE", "CLAIMS_TOKEN"],
            "known_release_risks": ["Claims enum and database migrations are release-sensitive."],
            "file_summaries": [
                {
                    "path": "src/app/routes/claims.py",
                    "summary": "Claims decision API route.",
                }
            ],
        }


class ContextBuilderTests(unittest.TestCase):
    def test_classifies_generic_repository_files(self) -> None:
        cases = {
            "app/routes/claims.py": "API",
            "src/services/claims.py": "SERVICE",
            "src/models/claim.py": "DB_MODEL",
            "alembic/versions/001_claims.py": "MIGRATION",
            "config/settings.py": "CONFIG",
            "docker-compose.yml": "DEPLOYMENT",
            ".github/workflows/ci.yml": "CI_CD",
            "tests/test_claims.py": "TEST",
            "auth/token.py": "SECURITY",
            "frontend/components/ClaimCard.tsx": "FRONTEND",
            "package.json": "DEPENDENCY",
            "docs/release.md": "DOCS",
            "src/main.py": "SOURCE",
        }

        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(classify_file(path), expected)

    def test_extracts_deterministic_file_signals(self) -> None:
        context = extract_file_context(
            "app/routes/claims.py",
            "\n".join(
                [
                    "import os",
                    "from alembic import op",
                    "from fastapi import APIRouter",
                    "router = APIRouter()",
                    "@router.post('/claims/{claim_id}/decision')",
                    "def decide_claim(claim_id: str):",
                    "    os.getenv('CLAIMS_DECISION_MODE')",
                    "class Claim(Base):",
                    "    __tablename__ = 'claims'",
                    "op.add_column('claims', sa.Column('reviewer_id', sa.String()))",
                ]
            ),
        )

        self.assertIn("CLAIMS_DECISION_MODE", context.env_vars)
        self.assertIn("POST /claims/{claim_id}/decision", context.api_routes)
        self.assertIn("claims", context.db_tables)
        self.assertIn("decide_claim", context.important_symbols)
        self.assertIn("add_column", context.migration_operations)
        self.assertIn("os", context.imports)

    def test_builds_repo_wide_memory_and_persists_transparent_files(self) -> None:
        fake_github = FakeGitHubClient()
        pr_summary = _pr_summary()

        with tempfile.TemporaryDirectory() as tmp_dir:
            store = ProjectMemoryStore(
                memory_dir=Path(tmp_dir),
                owner=pr_summary.owner,
                repo=pr_summary.repo,
            )
            package = load_or_build_project_context(
                github_client=fake_github,
                pr_summary=pr_summary,
                store=store,
                llm_client=FakeLLMClient(),
                rebuild=True,
            )

            inventory_paths = {item.path for item in package.inventory}
            self.assertEqual(inventory_paths, {item["path"] for item in fake_github.tree})
            self.assertTrue(store.repo_inventory_path.is_file())
            self.assertTrue(store.files_index_path.is_file())
            self.assertTrue(store.project_memory_path.is_file())
            self.assertTrue(store.memory_build_report_path.is_file())

            report = package.build_report
            self.assertEqual(report.total_files_discovered, len(fake_github.tree))
            self.assertTrue(report.tree_truncated)
            self.assertEqual(report.llm_summary_used, True)
            self.assertEqual(package.memory.summary_source, "LLM")
            self.assertIn("Claims service", package.memory.architecture_summary or "")

            skipped_by_path = {
                item.path: item.skipped_reason
                for item in package.inventory
                if item.skipped_reason
            }
            self.assertIn("binary candidate", skipped_by_path["assets/logo.png"])
            self.assertIn("generated", skipped_by_path["node_modules/pkg/index.js"])
            self.assertIn("larger than", skipped_by_path["src/generated_large.py"])
            self.assertNotIn("assets/logo.png", fake_github.fetched_paths)
            self.assertNotIn("node_modules/pkg/index.js", fake_github.fetched_paths)
            self.assertNotIn("src/generated_large.py", fake_github.fetched_paths)

            report_model = ReleaseRiskReport(
                release_readiness_score=55,
                decision="REVIEW_REQUIRED",
                risk_level="HIGH",
                what_may_break=["Claims API clients may break."],
                what_ci_may_miss=["Rollback behavior may be untested."],
            )
            updated_memory = update_memory_after_analysis(
                store=store,
                memory=package.memory,
                pr_summary=pr_summary,
                report=report_model,
            )
            self.assertIn("CLAIMS_FLAG", updated_memory.known_config_surface)
            self.assertIn("claims_archive", updated_memory.known_data_surface)
            self.assertTrue(store.release_history_path.is_file())
            self.assertEqual(len(store.load_release_history()), 1)

    def test_saves_deterministic_memory_without_llm(self) -> None:
        pr_summary = _pr_summary()

        with tempfile.TemporaryDirectory() as tmp_dir:
            store = ProjectMemoryStore(
                memory_dir=Path(tmp_dir),
                owner=pr_summary.owner,
                repo=pr_summary.repo,
            )
            package = load_or_build_project_context(
                github_client=FakeGitHubClient(),
                pr_summary=pr_summary,
                store=store,
                llm_client=None,
                rebuild=True,
            )

            self.assertEqual(package.memory.summary_source, "DETERMINISTIC")
            self.assertFalse(package.build_report.llm_summary_used)
            self.assertIsNone(package.build_report.llm_summary_error)
            self.assertTrue(store.project_memory_path.is_file())
            self.assertTrue(store.memory_build_report_path.is_file())


def _pr_summary() -> PRChangeSummary:
    return PRChangeSummary(
        pr_url="https://github.com/example/claims-api/pull/7",
        owner="example",
        repo="claims-api",
        pr_number=7,
        title="Risky claims release",
        body="Changes claims behavior.",
        state="open",
        base_branch="main",
        head_branch="feature/risky-claims",
        base_sha="base-sha",
        head_sha="head-sha",
        changed_files_count=2,
        additions=10,
        deletions=2,
        changed_files=[
            "src/app/routes/claims.py",
            "alembic/versions/001_add_claim.py",
        ],
        changed_file_extensions=[".py"],
        included_files=[
            "src/app/routes/claims.py",
            "alembic/versions/001_add_claim.py",
        ],
        omitted_files=[],
        partially_included_files=[],
        diff_strategy="test",
        diff=(
            "diff --git a/src/app/routes/claims.py b/src/app/routes/claims.py\n"
            "+@router.post('/claims/{claim_id}/decision')\n"
            "+os.getenv('CLAIMS_FLAG')\n"
            "+__tablename__ = 'claims_archive'\n"
        ),
        diff_truncated=False,
        max_diff_chars=120_000,
    )


if __name__ == "__main__":
    unittest.main()
