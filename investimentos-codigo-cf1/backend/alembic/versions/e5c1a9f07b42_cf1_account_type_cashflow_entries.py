"""cf1: accounts.account_type e cashflow_entries

Revision ID: e5c1a9f07b42
Revises: d2a6c1e85f34
Create Date: 2026-10-05

- `accounts.account_type`: toda conta existente vira BROKERAGE (até
  aqui o sistema só tinha o livro de investimentos).
- `cashflow_entries`: livro de caixa. Nenhuma outra tabela é alterada
  e nenhum dado existente é migrado.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5c1a9f07b42"
down_revision: str | Sequence[str] | None = "d2a6c1e85f34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    account_type = postgresql.ENUM(
        "CHECKING",
        "SAVINGS",
        "CASH",
        "CREDIT_CARD",
        "BROKERAGE",
        name="account_type",
        create_type=False,
    )
    account_type.create(bind, checkfirst=True)
    op.add_column(
        "accounts",
        sa.Column("account_type", account_type, nullable=False, server_default="BROKERAGE"),
    )

    cashflow_nature = postgresql.ENUM(
        "INCOME",
        "EXPENSE",
        "THIRD_PARTY",
        "TRANSFER",
        "ADJUSTMENT",
        "UNCLASSIFIED",
        name="cashflow_nature",
        create_type=False,
    )
    cashflow_nature.create(bind, checkfirst=True)
    cashflow_entry_status = postgresql.ENUM(
        "ACTIVE", "REVERSED", name="cashflow_entry_status", create_type=False
    )
    cashflow_entry_status.create(bind, checkfirst=True)
    transaction_source = postgresql.ENUM(name="transaction_source", create_type=False)

    op.create_table(
        "cashflow_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("source", transaction_source, nullable=False),
        sa.Column("nature", cashflow_nature, nullable=False),
        sa.Column("counterparty_account_id", sa.UUID(), nullable=True),
        sa.Column("transfer_group_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", cashflow_entry_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount <> 0", name="ck_cashflow_entries_amount_nonzero"),
        sa.CheckConstraint(
            "(nature = 'TRANSFER') = (counterparty_account_id IS NOT NULL)",
            name="ck_cashflow_entries_transfer_has_counterparty",
        ),
        sa.CheckConstraint(
            "(nature = 'TRANSFER') = (transfer_group_id IS NOT NULL)",
            name="ck_cashflow_entries_transfer_has_group",
        ),
        sa.CheckConstraint(
            "counterparty_account_id IS NULL OR counterparty_account_id <> account_id",
            name="ck_cashflow_entries_counterparty_differs",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["counterparty_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["currency_code"], ["currencies.code"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_cashflow_entries_account_id"), "cashflow_entries", ["account_id"], unique=False
    )
    op.create_index(
        op.f("ix_cashflow_entries_counterparty_account_id"),
        "cashflow_entries",
        ["counterparty_account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cashflow_entries_transfer_group_id"),
        "cashflow_entries",
        ["transfer_group_id"],
        unique=False,
    )
    op.create_index(
        "ix_cashflow_entries_account_date",
        "cashflow_entries",
        ["account_id", "entry_date"],
        unique=False,
    )

    # --- Fato imutável, classificação mutável ----------------------------
    # Protegidos: conta, data, valor, moeda, descrição, origem. Livres:
    # nature, counterparty_account_id, transfer_group_id, notes (a
    # coerência entre eles é garantida pelas CHECKs acima). `status` só
    # ACTIVE -> REVERSED. DELETE nunca.
    op.execute("""
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
        """)
    op.execute("""
        CREATE TRIGGER trg_cashflow_entries_immutability
        BEFORE UPDATE OR DELETE ON cashflow_entries
        FOR EACH ROW
        EXECUTE FUNCTION enforce_cashflow_entry_immutability();
        """)

    # --- Os dois livros não se misturam ----------------------------------
    # Conta BROKERAGE não recebe CashflowEntry; conta de caixa não
    # recebe Transaction. Reforçado no banco, não só no service.
    op.execute("""
        CREATE OR REPLACE FUNCTION enforce_ledger_separation()
        RETURNS TRIGGER AS $$
        DECLARE
            acct_type account_type;
        BEGIN
            SELECT account_type INTO acct_type FROM accounts WHERE id = NEW.account_id;
            IF TG_TABLE_NAME = 'cashflow_entries' AND acct_type = 'BROKERAGE' THEN
                RAISE EXCEPTION
                    'conta % é BROKERAGE: pertence ao livro de investimentos e não recebe cashflow_entries',
                    NEW.account_id
                    USING ERRCODE = '23000';
            END IF;
            IF TG_TABLE_NAME = 'transactions' AND acct_type <> 'BROKERAGE' THEN
                RAISE EXCEPTION
                    'conta % é do livro de caixa (%): não recebe transactions de investimento',
                    NEW.account_id, acct_type
                    USING ERRCODE = '23000';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """)
    op.execute("""
        CREATE TRIGGER trg_cashflow_entries_ledger_separation
        BEFORE INSERT ON cashflow_entries
        FOR EACH ROW
        EXECUTE FUNCTION enforce_ledger_separation();
        """)
    op.execute("""
        CREATE TRIGGER trg_transactions_ledger_separation
        BEFORE INSERT ON transactions
        FOR EACH ROW
        EXECUTE FUNCTION enforce_ledger_separation();
        """)
    # Uma conta que já tem lançamentos não pode trocar de livro.
    op.execute("""
        CREATE OR REPLACE FUNCTION enforce_account_type_stability()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.account_type IS DISTINCT FROM OLD.account_type
                AND (NEW.account_type = 'BROKERAGE') <> (OLD.account_type = 'BROKERAGE')
                AND (
                    EXISTS (SELECT 1 FROM transactions WHERE account_id = OLD.id)
                    OR EXISTS (SELECT 1 FROM cashflow_entries WHERE account_id = OLD.id)
                )
            THEN
                RAISE EXCEPTION
                    'conta % já tem lançamentos: não pode trocar de livro (% -> %)',
                    OLD.id, OLD.account_type, NEW.account_type
                    USING ERRCODE = '23000';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """)
    op.execute("""
        CREATE TRIGGER trg_accounts_type_stability
        BEFORE UPDATE ON accounts
        FOR EACH ROW
        EXECUTE FUNCTION enforce_account_type_stability();
        """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_accounts_type_stability ON accounts;")
    op.execute("DROP FUNCTION IF EXISTS enforce_account_type_stability();")
    op.execute("DROP TRIGGER IF EXISTS trg_transactions_ledger_separation ON transactions;")
    op.execute("DROP TRIGGER IF EXISTS trg_cashflow_entries_ledger_separation ON cashflow_entries;")
    op.execute("DROP FUNCTION IF EXISTS enforce_ledger_separation();")
    op.execute("DROP TRIGGER IF EXISTS trg_cashflow_entries_immutability ON cashflow_entries;")
    op.execute("DROP FUNCTION IF EXISTS enforce_cashflow_entry_immutability();")
    op.drop_index("ix_cashflow_entries_account_date", table_name="cashflow_entries")
    op.drop_index(op.f("ix_cashflow_entries_transfer_group_id"), table_name="cashflow_entries")
    op.drop_index(
        op.f("ix_cashflow_entries_counterparty_account_id"), table_name="cashflow_entries"
    )
    op.drop_index(op.f("ix_cashflow_entries_account_id"), table_name="cashflow_entries")
    op.drop_table("cashflow_entries")
    sa.Enum(name="cashflow_entry_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="cashflow_nature").drop(op.get_bind(), checkfirst=True)
    op.drop_column("accounts", "account_type")
    sa.Enum(name="account_type").drop(op.get_bind(), checkfirst=True)
