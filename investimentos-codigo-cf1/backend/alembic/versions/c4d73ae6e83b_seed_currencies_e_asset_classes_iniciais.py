"""seed: currencies e asset_classes iniciais

Revision ID: c4d73ae6e83b
Revises: a4a19c4b23b7
Create Date: 2026-09-10 20:28:43.103653

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d73ae6e83b"
down_revision: str | Sequence[str] | None = "a4a19c4b23b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


currencies_table = sa.table(
    "currencies", sa.column("code", sa.String), sa.column("name", sa.String)
)
asset_classes_table = sa.table(
    "asset_classes", sa.column("code", sa.String), sa.column("label", sa.String)
)

CURRENCIES = [
    {"code": "BRL", "name": "Real brasileiro"},
    {"code": "USD", "name": "Dólar americano"},
]

# Lista inicial cobrindo o escopo declarado (seção 4 do requisito
# original): ativos BR e internacionais. Extensível sem migration de
# schema — só um INSERT futuro.
ASSET_CLASSES = [
    {"code": "STOCK_BR", "label": "Ação (Brasil)"},
    {"code": "FII", "label": "Fundo Imobiliário"},
    {"code": "ETF_BR", "label": "ETF (Brasil)"},
    {"code": "BDR", "label": "BDR"},
    {"code": "TESOURO_DIRETO", "label": "Tesouro Direto"},
    {"code": "CDB", "label": "CDB"},
    {"code": "LCI", "label": "LCI"},
    {"code": "LCA", "label": "LCA"},
    {"code": "DEBENTURE", "label": "Debênture"},
    {"code": "FUND", "label": "Fundo de investimento"},
    {"code": "SAVINGS", "label": "Poupança"},
    {"code": "STOCK_US", "label": "Ação (Exterior)"},
    {"code": "ETF_US", "label": "ETF (Exterior)"},
    {"code": "REIT", "label": "REIT"},
    {"code": "BOND", "label": "Bond / Treasury"},
    {"code": "CRYPTO", "label": "Criptomoeda"},
]


def upgrade() -> None:
    """Upgrade schema."""
    op.bulk_insert(currencies_table, CURRENCIES)
    op.bulk_insert(asset_classes_table, ASSET_CLASSES)


def downgrade() -> None:
    """Downgrade schema."""
    codes = tuple(c["code"] for c in ASSET_CLASSES)
    op.execute(asset_classes_table.delete().where(asset_classes_table.c.code.in_(codes)))
    codes = tuple(c["code"] for c in CURRENCIES)
    op.execute(currencies_table.delete().where(currencies_table.c.code.in_(codes)))
