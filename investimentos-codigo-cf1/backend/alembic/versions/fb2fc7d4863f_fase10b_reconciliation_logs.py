"""fase10b: reconciliation_logs

Revision ID: fb2fc7d4863f
Revises: acfec251182b
Create Date: 2026-09-24

Cria apenas `reconciliation_logs` e o enum nativo
`reconciliation_status`. Nenhuma tabela existente é alterada.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fb2fc7d4863f"
down_revision: str | Sequence[str] | None = "acfec251182b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    reconciliation_status = postgresql.ENUM(
        "PENDING",
        "IGNORED",
        "KEPT_BOTH",
        "MERGED",
        "STALE",
        name="reconciliation_status",
        create_type=False,
    )
    reconciliation_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "reconciliation_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("transaction_a_id", sa.UUID(), nullable=False),
        sa.Column("transaction_b_id", sa.UUID(), nullable=False),
        sa.Column("match_reason", sa.Text(), nullable=False),
        sa.Column("status", reconciliation_status, nullable=False),
        sa.Column("surviving_transaction_id", sa.UUID(), nullable=True),
        sa.Column("reversed_transaction_id", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "transaction_a_id < transaction_b_id", name="ck_reconciliation_logs_canonical_pair"
        ),
        sa.CheckConstraint(
            "(status = 'MERGED' "
            " AND surviving_transaction_id IS NOT NULL "
            " AND reversed_transaction_id IS NOT NULL "
            " AND surviving_transaction_id <> reversed_transaction_id "
            " AND surviving_transaction_id IN (transaction_a_id, transaction_b_id) "
            " AND reversed_transaction_id IN (transaction_a_id, transaction_b_id)) "
            "OR (status <> 'MERGED' "
            " AND surviving_transaction_id IS NULL "
            " AND reversed_transaction_id IS NULL)",
            name="ck_reconciliation_logs_merge_consistency",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND resolved_at IS NULL) "
            "OR (status IN ('IGNORED', 'KEPT_BOTH', 'MERGED') AND resolved_at IS NOT NULL) "
            "OR status = 'STALE'",
            name="ck_reconciliation_logs_resolved_at",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["transaction_a_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["transaction_b_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["surviving_transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["reversed_transaction_id"], ["transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "transaction_a_id", "transaction_b_id", name="uq_reconciliation_logs_pair"
        ),
    )
    op.create_index(
        "ix_reconciliation_logs_user_status", "reconciliation_logs", ["user_id", "status"]
    )
    op.create_index(
        "ix_reconciliation_logs_transaction_a_id", "reconciliation_logs", ["transaction_a_id"]
    )
    op.create_index(
        "ix_reconciliation_logs_transaction_b_id", "reconciliation_logs", ["transaction_b_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_reconciliation_logs_transaction_b_id", table_name="reconciliation_logs")
    op.drop_index("ix_reconciliation_logs_transaction_a_id", table_name="reconciliation_logs")
    op.drop_index("ix_reconciliation_logs_user_status", table_name="reconciliation_logs")
    op.drop_table("reconciliation_logs")
    postgresql.ENUM(name="reconciliation_status").drop(op.get_bind(), checkfirst=True)
