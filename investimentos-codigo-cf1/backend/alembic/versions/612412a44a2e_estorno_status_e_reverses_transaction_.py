"""estorno: status e reverses_transaction_id em Transaction

Revision ID: 612412a44a2e
Revises: c4d73ae6e83b
Create Date: 2026-09-10 20:35:21.624358

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "612412a44a2e"
down_revision: str | Sequence[str] | None = "c4d73ae6e83b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    transaction_status = sa.Enum("ACTIVE", "REVERSED", name="transaction_status")
    transaction_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "transactions",
        sa.Column(
            "status",
            transaction_status,
            nullable=False,
            server_default="ACTIVE",
        ),
    )
    op.add_column("transactions", sa.Column("reverses_transaction_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_transactions_reverses_transaction_id"),
        "transactions",
        ["reverses_transaction_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_transactions_reverses_transaction_id",
        "transactions",
        "transactions",
        ["reverses_transaction_id"],
        ["id"],
    )

    # --- Trigger de imutabilidade financeira -----------------------------
    # Regra de negócio (aprovada): uma Transaction já persistida é um
    # registro histórico protegido. Campos financeiros nunca mudam depois
    # do INSERT. A única mudança de estado permitida é status
    # ACTIVE -> REVERSED (estorno). `notes`/`updated_at` continuam livres
    # por serem metadado administrativo, não fato financeiro.
    op.execute("""
        CREATE OR REPLACE FUNCTION enforce_transaction_immutability()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.account_id IS DISTINCT FROM OLD.account_id
                OR NEW.asset_id IS DISTINCT FROM OLD.asset_id
                OR NEW.transaction_type IS DISTINCT FROM OLD.transaction_type
                OR NEW.quantity IS DISTINCT FROM OLD.quantity
                OR NEW.unit_price IS DISTINCT FROM OLD.unit_price
                OR NEW.fees IS DISTINCT FROM OLD.fees
                OR NEW.gross_amount IS DISTINCT FROM OLD.gross_amount
                OR NEW.currency_code IS DISTINCT FROM OLD.currency_code
                OR NEW.transaction_date IS DISTINCT FROM OLD.transaction_date
                OR NEW.source IS DISTINCT FROM OLD.source
                OR NEW.external_reference IS DISTINCT FROM OLD.external_reference
                OR NEW.reverses_transaction_id IS DISTINCT FROM OLD.reverses_transaction_id
                OR NEW.created_at IS DISTINCT FROM OLD.created_at
            THEN
                RAISE EXCEPTION
                    'transaction % é um registro histórico protegido: campos financeiros não podem ser alterados. Use status=REVERSED + uma nova Transaction para corrigir.',
                    OLD.id
                    USING ERRCODE = '23000';
            END IF;

            IF NEW.status IS DISTINCT FROM OLD.status THEN
                IF NOT (OLD.status = 'ACTIVE' AND NEW.status = 'REVERSED') THEN
                    RAISE EXCEPTION
                        'transição de status inválida em transaction % (% -> %): só ACTIVE -> REVERSED é permitido',
                        OLD.id, OLD.status, NEW.status
                        USING ERRCODE = '23000';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """)
    op.execute("""
        CREATE TRIGGER trg_transactions_immutability
        BEFORE UPDATE ON transactions
        FOR EACH ROW
        EXECUTE FUNCTION enforce_transaction_immutability();
        """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_transactions_immutability ON transactions;")
    op.execute("DROP FUNCTION IF EXISTS enforce_transaction_immutability();")
    op.drop_constraint(
        "fk_transactions_reverses_transaction_id", "transactions", type_="foreignkey"
    )
    op.drop_index(op.f("ix_transactions_reverses_transaction_id"), table_name="transactions")
    op.drop_column("transactions", "reverses_transaction_id")
    op.drop_column("transactions", "status")
    sa.Enum(name="transaction_status").drop(op.get_bind(), checkfirst=True)
