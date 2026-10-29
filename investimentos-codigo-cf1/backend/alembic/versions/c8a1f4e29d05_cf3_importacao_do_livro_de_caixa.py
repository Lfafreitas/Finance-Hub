"""cf3: importação do livro de caixa

Revision ID: c8a1f4e29d05
Revises: b4c9e7d1a3f6
Create Date: 2026-10-06

- `cashflow_import_batches`: um registro por importação confirmada
  (hash e nome do arquivo, nunca o arquivo).
- `cashflow_entries` ganha `external_id`, `import_fingerprint` e
  `import_batch_id`, nulos em todo lançamento existente, com índices
  únicos parciais para a deduplicação.
- O trigger de imutabilidade passa a proteger também esses três campos.

Nenhum dado é migrado.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8a1f4e29d05"
down_revision: str | Sequence[str] | None = "b4c9e7d1a3f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IMMUTABILITY = """
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
            {extra}
        THEN
            RAISE EXCEPTION
                'cashflow_entry % é um registro histórico protegido: o fato não pode ser alterado. Use status=REVERSED + um novo lançamento para corrigir.',
                OLD.id
                USING ERRCODE = '23000';
        END IF;

        IF NEW.status IS DISTINCT FROM OLD.status THEN
            IF NOT (OLD.status = 'ACTIVE' AND NEW.status = 'REVERSED') THEN
                RAISE EXCEPTION
                    'transição de status inválida em cashflow_entry % (% -> %): só ACTIVE -> REVERSED é permitido',
                    OLD.id, OLD.status, NEW.status
                    USING ERRCODE = '23000';
            END IF;
        END IF;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """
_EXTRA = """OR NEW.external_id IS DISTINCT FROM OLD.external_id
            OR NEW.import_fingerprint IS DISTINCT FROM OLD.import_fingerprint
            OR NEW.import_batch_id IS DISTINCT FROM OLD.import_batch_id"""


def upgrade() -> None:
    """Upgrade schema."""
    profile = postgresql.ENUM(
        "NUBANK_ACCOUNT_CSV",
        "NUBANK_ACCOUNT_OFX",
        "NUBANK_CARD_CSV",
        name="cashflow_import_profile",
        create_type=False,
    )
    profile.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "cashflow_import_batches",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("profile", profile, nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("rows_total", sa.Integer(), nullable=False),
        sa.Column("rows_imported", sa.Integer(), nullable=False),
        sa.Column("statement_balance", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("statement_balance_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_cashflow_import_batches_account_id"),
        "cashflow_import_batches",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cashflow_import_batches_file_sha256"),
        "cashflow_import_batches",
        ["file_sha256"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cashflow_import_batches_user_id"),
        "cashflow_import_batches",
        ["user_id"],
        unique=False,
    )

    op.add_column(
        "cashflow_entries", sa.Column("external_id", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "cashflow_entries", sa.Column("import_fingerprint", sa.String(length=80), nullable=True)
    )
    op.add_column("cashflow_entries", sa.Column("import_batch_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_cashflow_entries_import_batch_id"),
        "cashflow_entries",
        ["import_batch_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_cashflow_entries_import_batch_id",
        "cashflow_entries",
        "cashflow_import_batches",
        ["import_batch_id"],
        ["id"],
    )
    op.create_index(
        "uq_cashflow_entries_account_external_id",
        "cashflow_entries",
        ["account_id", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )
    op.create_index(
        "uq_cashflow_entries_account_fingerprint",
        "cashflow_entries",
        ["account_id", "import_fingerprint"],
        unique=True,
        postgresql_where=sa.text("import_fingerprint IS NOT NULL"),
    )
    op.execute(_IMMUTABILITY.format(extra=_EXTRA))


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(_IMMUTABILITY.format(extra=""))
    op.drop_index("uq_cashflow_entries_account_fingerprint", table_name="cashflow_entries")
    op.drop_index("uq_cashflow_entries_account_external_id", table_name="cashflow_entries")
    op.drop_constraint(
        "fk_cashflow_entries_import_batch_id", "cashflow_entries", type_="foreignkey"
    )
    op.drop_index(op.f("ix_cashflow_entries_import_batch_id"), table_name="cashflow_entries")
    op.drop_column("cashflow_entries", "import_batch_id")
    op.drop_column("cashflow_entries", "import_fingerprint")
    op.drop_column("cashflow_entries", "external_id")
    op.drop_table("cashflow_import_batches")
    sa.Enum(name="cashflow_import_profile").drop(op.get_bind(), checkfirst=True)
