"""Edição-2: lançamento de caixa pode ser restaurado e editado

- `status` passa a aceitar REVERSED -> ACTIVE (restaurar um lançamento
  excluído). As outras transições continuam recusadas.
- `corrects_entry_id`: o lançamento novo criado por uma edição aponta
  para o que ele substituiu. É fato (imutável, como o resto) e único:
  um lançamento é substituído no máximo uma vez.

Nenhum dado existente é alterado.

Revision ID: a7d3c9e5f1b2
Revises: d2e7a1b9c4f3
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a7d3c9e5f1b2"
down_revision: str | Sequence[str] | None = "d2e7a1b9c4f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION = """
    CREATE OR REPLACE FUNCTION enforce_cashflow_entry_immutability()
    RETURNS TRIGGER AS $$
    BEGIN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION
                'cashflow_entry % é um registro histórico protegido: não pode ser apagado. Use status=REVERSED.',
                OLD.id
                USING ERRCODE = '23000';
        END IF;

        IF NEW.account_id IS DISTINCT FROM OLD.account_id
            OR NEW.entry_date IS DISTINCT FROM OLD.entry_date
            OR NEW.amount IS DISTINCT FROM OLD.amount
            OR NEW.currency_code IS DISTINCT FROM OLD.currency_code
            OR NEW.description IS DISTINCT FROM OLD.description
            OR NEW.source IS DISTINCT FROM OLD.source
            OR NEW.created_at IS DISTINCT FROM OLD.created_at
            OR NEW.external_id IS DISTINCT FROM OLD.external_id
            OR NEW.import_fingerprint IS DISTINCT FROM OLD.import_fingerprint
            OR NEW.import_batch_id IS DISTINCT FROM OLD.import_batch_id
            {extra}
        THEN
            RAISE EXCEPTION
                'cashflow_entry % é um registro histórico protegido: o fato não pode ser alterado. Use status=REVERSED + um novo lançamento para corrigir.',
                OLD.id
                USING ERRCODE = '23000';
        END IF;

        IF NEW.status IS DISTINCT FROM OLD.status THEN
            IF NOT ({transitions}) THEN
                RAISE EXCEPTION
                    'transição de status inválida em cashflow_entry % (% -> %)',
                    OLD.id, OLD.status, NEW.status
                    USING ERRCODE = '23000';
            END IF;
        END IF;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """
_NEW_EXTRA = "OR NEW.corrects_entry_id IS DISTINCT FROM OLD.corrects_entry_id"
_BOTH_WAYS = (
    "(OLD.status = 'ACTIVE' AND NEW.status = 'REVERSED')"
    " OR (OLD.status = 'REVERSED' AND NEW.status = 'ACTIVE')"
)
_ONE_WAY = "OLD.status = 'ACTIVE' AND NEW.status = 'REVERSED'"


def upgrade() -> None:
    op.add_column(
        "cashflow_entries",
        sa.Column("corrects_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_cashflow_entries_corrects_entry_id",
        "cashflow_entries",
        "cashflow_entries",
        ["corrects_entry_id"],
        ["id"],
    )
    op.create_index(
        "uq_cashflow_entries_corrects_entry_id",
        "cashflow_entries",
        ["corrects_entry_id"],
        unique=True,
        postgresql_where=sa.text("corrects_entry_id IS NOT NULL"),
    )
    op.execute(_FUNCTION.format(extra=_NEW_EXTRA, transitions=_BOTH_WAYS))


def downgrade() -> None:
    op.execute(_FUNCTION.format(extra="", transitions=_ONE_WAY))
    op.drop_index("uq_cashflow_entries_corrects_entry_id", table_name="cashflow_entries")
    op.drop_constraint(
        "fk_cashflow_entries_corrects_entry_id", "cashflow_entries", type_="foreignkey"
    )
    op.drop_column("cashflow_entries", "corrects_entry_id")
