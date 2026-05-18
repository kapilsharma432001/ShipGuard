from alembic import op
import sqlalchemy as sa


revision = "001_create_claims_table"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("claimant_id", sa.String(length=64), nullable=False),
        sa.Column("claim_amount", sa.Float(), nullable=False),
        sa.Column("diagnosis_code", sa.String(length=32), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("assigned_queue", sa.String(length=64), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("claims")
