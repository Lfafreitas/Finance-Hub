"""Alocação-alvo: peso-alvo por classe de ativo e moeda

Tabela nova `allocation_targets`. Nenhum dado existente é alterado.

Revision ID: e2c8a5b7d914
Revises: d9b4e6f1a273
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e2c8a5b7d914"
down_revision: str | Sequence[str] | None = "d9b4e6f1a273"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "allocation_targets",
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True
        ),
        sa.Column(
            "currency_code", sa.String(3), sa.ForeignKey("currencies.code"), primary_key=True
        ),
        sa.Column(
            "asset_class_code",
            sa.String(30),
            sa.ForeignKey("asset_classes.code"),
            primary_key=True,
        ),
        sa.Column("target_weight", sa.Numeric(5, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "target_weight >= 0 AND target_weight <= 1", name="ck_allocation_target_range"
        ),
    )


def downgrade() -> None:
    op.drop_table("allocation_targets")
