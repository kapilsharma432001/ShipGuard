from alembic import op
import sqlalchemy as sa


revision = "002_add_claim_source"
down_revision = "001_create_claims_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "claims",
        sa.Column("claim_source", sa.String(length=32), nullable=False),
    )


def downgrade() -> None:
    pass
