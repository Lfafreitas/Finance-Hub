"""análises-1: fonte automática de cotação

Revision ID: d2e7a1b9c4f3
Revises: c8a1f4e29d05
Create Date: 2026-10-08

`price_source` ganha o valor YAHOO. Nenhum dado é migrado.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d2e7a1b9c4f3"
down_revision: str | Sequence[str] | None = "c8a1f4e29d05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE price_source ADD VALUE IF NOT EXISTS 'YAHOO'")


def downgrade() -> None:
    # O PostgreSQL não remove valor de enum. Apagar as cotações
    # automáticas e recriar o tipo só com MANUAL.
    op.execute("DELETE FROM asset_prices WHERE source = 'YAHOO'")
    op.execute("ALTER TYPE price_source RENAME TO price_source_old")
    op.execute("CREATE TYPE price_source AS ENUM ('MANUAL')")
    op.execute(
        "ALTER TABLE asset_prices ALTER COLUMN source TYPE price_source "
        "USING source::text::price_source"
    )
    op.execute("DROP TYPE price_source_old")
