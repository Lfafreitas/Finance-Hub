"""fase12: asset_prices

Revision ID: d2a6c1e85f34
Revises: fb2fc7d4863f
Create Date: 2026-10-03

Cria apenas `asset_prices` e o enum nativo `price_source`. Nenhuma
tabela existente é alterada.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2a6c1e85f34"
down_revision: str | Sequence[str] | None = "fb2fc7d4863f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    price_source = postgresql.ENUM("MANUAL", name="price_source", create_type=False)
    price_source.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "asset_prices",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("price_date", sa.Date(), nullable=False),
        sa.Column("price", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("source", price_source, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("price > 0", name="ck_asset_prices_price_positive"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["currency_code"], ["currencies.code"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asset_id", "price_date", "source", name="uq_asset_prices_asset_date_source"
        ),
    )
    op.create_index(op.f("ix_asset_prices_asset_id"), "asset_prices", ["asset_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_asset_prices_asset_id"), table_name="asset_prices")
    op.drop_table("asset_prices")
    postgresql.ENUM(name="price_source").drop(op.get_bind(), checkfirst=True)
