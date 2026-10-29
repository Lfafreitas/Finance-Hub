"""Agenda: vencimento e taxa anual de ativos de renda fixa

Duas colunas opcionais em `assets`. Nenhum dado existente é alterado:
ficam vazias até o vencimento ser informado no cadastro.

Revision ID: c7f3a9d2e481
Revises: b4e8f2a6c1d9
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7f3a9d2e481"
down_revision: str | Sequence[str] | None = "b4e8f2a6c1d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("maturity_date", sa.Date(), nullable=True))
    op.add_column("assets", sa.Column("annual_rate", sa.Numeric(9, 6), nullable=True))
    op.create_check_constraint(
        "ck_asset_annual_rate_range",
        "assets",
        "annual_rate IS NULL OR (annual_rate >= 0 AND annual_rate <= 1)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_asset_annual_rate_range", "assets", type_="check")
    op.drop_column("assets", "annual_rate")
    op.drop_column("assets", "maturity_date")
