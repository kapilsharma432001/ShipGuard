#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_APP = ROOT / "sample-app"
MARKER = SAMPLE_APP / ".shipguard-demo"


BASELINE_FILES = {
    "README.md": """
        # Sample Claims API

        Synthetic FastAPI-style demo app for ShipGuard. This repository contains
        fake Claims API examples only.
        """,
    ".gitignore": """
        __pycache__/
        *.py[cod]
        .pytest_cache/
        .env
        .env.*
        !.env.example
        """,
    ".env.example": """
        DATABASE_URL=postgresql://claims:claims@localhost:5432/claims
        CLAIMS_API_TOKEN=dev-token
        """,
    "docker-compose.yml": """
        services:
          api:
            image: python:3.12-slim
            working_dir: /app
            command: uvicorn app.main:app --host 0.0.0.0 --port 8000
            volumes:
              - .:/app
            environment:
              DATABASE_URL: postgresql://claims:claims@db:5432/claims
              CLAIMS_API_TOKEN: dev-token
            ports:
              - "8000:8000"
            depends_on:
              - db

          db:
            image: postgres:16
            environment:
              POSTGRES_USER: claims
              POSTGRES_PASSWORD: claims
              POSTGRES_DB: claims
            ports:
              - "5432:5432"
        """,
    "pyproject.toml": """
        [project]
        name = "sample-claims-api"
        version = "0.1.0"
        requires-python = ">=3.11"
        dependencies = [
            "fastapi",
            "pydantic",
            "sqlalchemy",
            "alembic",
        ]

        [tool.pytest.ini_options]
        testpaths = ["tests"]
        """,
    "app/__init__.py": "",
    "app/main.py": """
        from fastapi import FastAPI

        from app.api.routes.claims import router as claims_router

        app = FastAPI(title="Sample Claims API")
        app.include_router(claims_router)
        """,
    "app/api/__init__.py": "",
    "app/api/routes/__init__.py": "",
    "app/api/routes/claims.py": """
        from enum import Enum

        from fastapi import APIRouter, HTTPException
        from pydantic import BaseModel, Field

        from app.services.claims import decide_claim, submit_claim

        router = APIRouter(prefix="/claims", tags=["claims"])


        class ClaimDecision(str, Enum):
            approved = "Approved"
            denied = "Denied"


        class ClaimSubmission(BaseModel):
            claim_id: str = Field(min_length=1)
            claimant_id: str = Field(min_length=1)
            amount_cents: int = Field(gt=0)
            reason: str = Field(min_length=1)


        class ClaimSubmissionResponse(BaseModel):
            claim_id: str
            status: str
            assigned_queue: str


        class ClaimDecisionRequest(BaseModel):
            decision: ClaimDecision
            reviewer_id: str = Field(min_length=1)
            notes: str | None = None


        class ClaimDecisionResponse(BaseModel):
            claim_id: str
            status: ClaimDecision
            reviewer_id: str


        @router.post("", response_model=ClaimSubmissionResponse)
        def create_claim(payload: ClaimSubmission) -> dict[str, object]:
            return submit_claim(payload.model_dump())


        @router.post("/{claim_id}/decision", response_model=ClaimDecisionResponse)
        def update_claim_decision(
            claim_id: str,
            payload: ClaimDecisionRequest,
        ) -> dict[str, object]:
            result = decide_claim(
                claim_id=claim_id,
                decision=payload.decision.value,
                reviewer_id=payload.reviewer_id,
            )
            if result is None:
                raise HTTPException(status_code=404, detail="claim not found")
            return result
        """,
    "app/core/__init__.py": "",
    "app/core/config.py": """
        import os


        DATABASE_URL = os.environ["DATABASE_URL"]
        CLAIMS_API_TOKEN = os.environ["CLAIMS_API_TOKEN"]
        """,
    "app/db/__init__.py": "",
    "app/db/models.py": """
        from sqlalchemy import Column, Integer, String
        from sqlalchemy.orm import declarative_base

        Base = declarative_base()


        class Claim(Base):
            __tablename__ = "claims"

            id = Column(Integer, primary_key=True)
            claim_id = Column(String(64), unique=True, nullable=False)
            claimant_id = Column(String(64), nullable=False)
            amount_cents = Column(Integer, nullable=False)
            status = Column(String(20), nullable=False)
        """,
    "app/services/__init__.py": "",
    "app/services/claims.py": """
        OPEN_CLAIMS = {
            "CLAIM-100": {
                "claim_id": "CLAIM-100",
                "claimant_id": "MEMBER-1",
                "amount_cents": 42000,
                "status": "Pending",
            }
        }


        def submit_claim(payload: dict[str, object]) -> dict[str, object]:
            OPEN_CLAIMS[payload["claim_id"]] = {
                **payload,
                "status": "Pending",
            }
            return {
                "claim_id": payload["claim_id"],
                "status": "Pending",
                "assigned_queue": "standard-review",
            }


        def decide_claim(
            claim_id: str,
            decision: str,
            reviewer_id: str,
        ) -> dict[str, object] | None:
            claim = OPEN_CLAIMS.get(claim_id)
            if claim is None:
                return None

            claim["status"] = decision
            claim["reviewer_id"] = reviewer_id
            return {
                "claim_id": claim_id,
                "status": decision,
                "reviewer_id": reviewer_id,
            }
        """,
    "alembic/versions/202605150900_create_claims_table.py": """
        from alembic import op
        import sqlalchemy as sa


        revision = "202605150900"
        down_revision = None
        branch_labels = None
        depends_on = None


        def upgrade() -> None:
            op.create_table(
                "claims",
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("claim_id", sa.String(length=64), nullable=False),
                sa.Column("claimant_id", sa.String(length=64), nullable=False),
                sa.Column("amount_cents", sa.Integer(), nullable=False),
                sa.Column("status", sa.String(length=20), nullable=False),
                sa.UniqueConstraint("claim_id"),
            )


        def downgrade() -> None:
            op.drop_table("claims")
        """,
    "tests/test_claims_api.py": """
        from app.api.routes.claims import ClaimDecision
        from app.services.claims import decide_claim, submit_claim


        def test_submit_claim_assigns_standard_queue() -> None:
            result = submit_claim(
                {
                    "claim_id": "CLAIM-200",
                    "claimant_id": "MEMBER-2",
                    "amount_cents": 12500,
                    "reason": "broken windshield",
                }
            )

            assert result == {
                "claim_id": "CLAIM-200",
                "status": "Pending",
                "assigned_queue": "standard-review",
            }


        def test_denied_claim_uses_public_api_enum_value() -> None:
            result = decide_claim(
                claim_id="CLAIM-100",
                decision=ClaimDecision.denied.value,
                reviewer_id="REVIEWER-9",
            )

            assert result == {
                "claim_id": "CLAIM-100",
                "status": "Denied",
                "reviewer_id": "REVIEWER-9",
            }
        """,
}


RISKY_FILES = {
    "app/api/routes/claims.py": """
        from enum import Enum

        from fastapi import APIRouter, HTTPException
        from pydantic import BaseModel, Field

        from app.services.claims import decide_claim, submit_claim

        router = APIRouter(prefix="/claims", tags=["claims"])


        class ClaimDecision(str, Enum):
            approved = "Approved"
            denied = "DENIED"


        class ClaimSubmission(BaseModel):
            claim_id: str = Field(min_length=1)
            member_id: str = Field(min_length=1)
            amount_cents: int = Field(gt=0)
            reason: str = Field(min_length=1)
            submission_channel: str = Field(min_length=1)


        class ClaimSubmissionResponse(BaseModel):
            claim_id: str
            status: str
            review_queue: str


        class ClaimDecisionRequest(BaseModel):
            decision: ClaimDecision
            reviewer_id: str = Field(min_length=1)
            notes: str | None = None


        class ClaimDecisionResponse(BaseModel):
            claim_id: str
            status: ClaimDecision
            reviewer_id: str


        @router.post("", response_model=ClaimSubmissionResponse)
        def create_claim(payload: ClaimSubmission) -> dict[str, object]:
            return submit_claim(payload.model_dump())


        @router.post("/{claim_id}/decision", response_model=ClaimDecisionResponse)
        def update_claim_decision(
            claim_id: str,
            payload: ClaimDecisionRequest,
        ) -> dict[str, object]:
            result = decide_claim(
                claim_id=claim_id,
                decision=payload.decision.value,
                reviewer_id=payload.reviewer_id,
            )
            if result is None:
                raise HTTPException(status_code=404, detail="claim not found")
            return result
        """,
    "app/core/config.py": """
        import os


        DATABASE_URL = os.environ["DATABASE_URL"]
        CLAIMS_API_TOKEN = os.environ["CLAIMS_API_TOKEN"]
        FRAUD_MODEL_ENDPOINT = os.environ["FRAUD_MODEL_ENDPOINT"]
        """,
    "app/db/models.py": """
        from sqlalchemy import Column, Integer, String
        from sqlalchemy.orm import declarative_base

        Base = declarative_base()


        class Claim(Base):
            __tablename__ = "claims"

            id = Column(Integer, primary_key=True)
            claim_id = Column(String(64), unique=True, nullable=False)
            member_id = Column(String(64), nullable=False)
            amount_cents = Column(Integer, nullable=False)
            status = Column(String(20), nullable=False)
            claim_source = Column(String(30), nullable=False)
        """,
    "app/services/claims.py": """
        from app.core.config import FRAUD_MODEL_ENDPOINT


        OPEN_CLAIMS = {
            "CLAIM-100": {
                "claim_id": "CLAIM-100",
                "member_id": "MEMBER-1",
                "amount_cents": 42000,
                "status": "Pending",
            }
        }


        def submit_claim(payload: dict[str, object]) -> dict[str, object]:
            review_queue = "standard-review"
            if int(payload["amount_cents"]) >= 500000:
                review_queue = "fraud-review"

            OPEN_CLAIMS[payload["claim_id"]] = {
                **payload,
                "status": "Pending",
                "fraud_model_endpoint": FRAUD_MODEL_ENDPOINT,
            }
            return {
                "claim_id": payload["claim_id"],
                "status": "Pending",
                "review_queue": review_queue,
            }


        def decide_claim(
            claim_id: str,
            decision: str,
            reviewer_id: str,
        ) -> dict[str, object] | None:
            claim = OPEN_CLAIMS.get(claim_id)
            if claim is None:
                return None

            claim["status"] = decision
            claim["reviewer_id"] = reviewer_id
            return {
                "claim_id": claim_id,
                "status": decision,
                "reviewer_id": reviewer_id,
            }
        """,
    "alembic/versions/202605151030_add_claim_source.py": """
        from alembic import op
        import sqlalchemy as sa


        revision = "202605151030"
        down_revision = "202605150900"
        branch_labels = None
        depends_on = None


        def upgrade() -> None:
            op.add_column(
                "claims",
                sa.Column("claim_source", sa.String(length=30), nullable=False),
            )


        def downgrade() -> None:
            pass
        """,
}


def main() -> None:
    reset_sample_app()
    write_files(BASELINE_FILES)
    run(["git", "init", "-b", "main"], cwd=SAMPLE_APP)
    run(["git", "config", "user.name", "ShipGuard Demo"], cwd=SAMPLE_APP)
    run(["git", "config", "user.email", "shipguard-demo@example.invalid"], cwd=SAMPLE_APP)
    run(["git", "add", "."], cwd=SAMPLE_APP)
    run(["git", "commit", "-m", "Create safe baseline Claims API"], cwd=SAMPLE_APP)

    write_files(RISKY_FILES)
    run(
        [
            "git",
            "add",
            "--intent-to-add",
            "alembic/versions/202605151030_add_claim_source.py",
        ],
        cwd=SAMPLE_APP,
    )

    print(f"Created demo repo at {SAMPLE_APP.relative_to(ROOT)}")
    print("Baseline committed; risky release changes are intentionally uncommitted.")
    print(flush=True)
    run(["git", "status", "--short"], cwd=SAMPLE_APP)


def reset_sample_app() -> None:
    if SAMPLE_APP.exists():
        if not MARKER.exists():
            raise SystemExit(
                f"Refusing to overwrite existing non-demo directory: {SAMPLE_APP}"
            )
        shutil.rmtree(SAMPLE_APP)

    SAMPLE_APP.mkdir(parents=True)
    MARKER.write_text(
        "Generated by scripts/create_demo_repo.py. Safe to recreate.\n",
        encoding="utf-8",
    )


def write_files(files: dict[str, str]) -> None:
    for relative_path, content in files.items():
        path = SAMPLE_APP / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(normalize(content), encoding="utf-8")


def normalize(content: str) -> str:
    if not content:
        return ""
    return textwrap.dedent(content).strip() + "\n"


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


if __name__ == "__main__":
    main()
