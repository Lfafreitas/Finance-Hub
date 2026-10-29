"""Fatura-PDF: perfis NUBANK_CARD_OFX e NUBANK_CARD_PDF

Só acrescenta dois valores ao tipo `cashflow_import_profile`. Nenhum
dado existente é alterado.

Revision ID: b4e8f2a6c1d9
Revises: a7d3c9e5f1b2
Create Date: 2026-10-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b4e8f2a6c1d9"
down_revision: str | Sequence[str] | None = "a7d3c9e5f1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = ("NUBANK_ACCOUNT_CSV", "NUBANK_ACCOUNT_OFX", "NUBANK_CARD_CSV")


def upgrade() -> None:
    op.execute("ALTER TYPE cashflow_import_profile ADD VALUE IF NOT EXISTS 'NUBANK_CARD_OFX'")
    op.execute("ALTER TYPE cashflow_import_profile ADD VALUE IF NOT EXISTS 'NUBANK_CARD_PDF'")


def downgrade() -> None:
    # O Postgres não remove valor de enum: o tipo é recriado. Recusa se
    # algum lote já usa um dos perfis novos (apagar o lote apagaria a
    # origem de lançamentos gravados).
    op.execute("""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM cashflow_import_batches
            WHERE profile::text IN ('NUBANK_CARD_OFX', 'NUBANK_CARD_PDF')
          ) THEN
            RAISE EXCEPTION 'há importações de fatura em OFX/PDF: downgrade recusado';
          END IF;
        END $$;
        """)
    values = ", ".join(f"'{v}'" for v in _OLD)
    op.execute("ALTER TYPE cashflow_import_profile RENAME TO cashflow_import_profile_old")
    op.execute(f"CREATE TYPE cashflow_import_profile AS ENUM ({values})")
    op.execute(
        "ALTER TABLE cashflow_import_batches ALTER COLUMN profile TYPE cashflow_import_profile "
        "USING profile::text::cashflow_import_profile"
    )
    op.execute("DROP TYPE cashflow_import_profile_old")
