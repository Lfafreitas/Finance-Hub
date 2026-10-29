"""Referências: taxa diária do CDI

Tabela nova `benchmark_rates` (dado público de mercado). Nenhum dado
existente é alterado.

Revision ID: d9b4e6f1a273
Revises: c7f3a9d2e481
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d9b4e6f1a273"
down_revision: str | Sequence[str] | None = "c7f3a9d2e481"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "benchmark_rates",
        sa.Column("code", sa.String(10), primary_key=True),
        sa.Column("rate_date", sa.Date(), primary_key=True),
        sa.Column("daily_rate", sa.Numeric(14, 10), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("benchmark_rates")
