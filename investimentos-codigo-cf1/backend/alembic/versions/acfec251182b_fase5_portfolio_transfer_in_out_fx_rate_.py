"""fase5: portfolio, transfer in/out, fx_rate_to_brl, linked_transaction_id

Revision ID: acfec251182b
Revises: 612412a44a2e
Create Date: 2026-09-11 03:54:06.573541

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "acfec251182b"
down_revision: str | Sequence[str] | None = "612412a44a2e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_TRANSACTION_TYPES = (
    "BUY",
    "SELL",
    "DEPOSIT",
    "WITHDRAWAL",
    "DIVIDEND",
    "JCP",
    "INCOME",
    "FEE",
    "TRANSFER",
    "FX_CONVERSION",
    "BONUS_SHARES",
    "STOCK_SPLIT",
    "REVERSE_SPLIT",
)
NEW_TRANSACTION_TYPES = (
    "BUY",
    "SELL",
    "DEPOSIT",
    "WITHDRAWAL",
    "DIVIDEND",
    "JCP",
    "INCOME",
    "FEE",
    "TRANSFER_OUT",
    "TRANSFER_IN",
    "FX_CONVERSION",
    "BONUS_SHARES",
    "STOCK_SPLIT",
    "REVERSE_SPLIT",
)


def upgrade() -> None:
    """Upgrade schema."""
    # --- 1) portfolios + accounts.portfolio_id (estrutural) --------------
    op.create_table(
        "portfolios",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name"),
    )
    op.create_index(op.f("ix_portfolios_user_id"), "portfolios", ["user_id"], unique=False)

    op.add_column("accounts", sa.Column("portfolio_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_accounts_portfolio_id"), "accounts", ["portfolio_id"], unique=False)
    op.create_foreign_key(
        "fk_accounts_portfolio_id", "accounts", "portfolios", ["portfolio_id"], ["id"]
    )

    # --- 2) TRANSFER -> TRANSFER_OUT / TRANSFER_IN ------------------------
    # Tabela `transactions` está vazia em produção real (nenhuma API de
    # escrita existe ainda) — recriação do tipo é segura. Se já houvesse
    # dado com valor 'TRANSFER', o cast abaixo falharia (proposital: não
    # inventamos uma regra de para qual lado migrar dado existente).
    op.execute("ALTER TYPE transaction_type RENAME TO transaction_type_old")
    new_enum = sa.Enum(*NEW_TRANSACTION_TYPES, name="transaction_type")
    new_enum.create(op.get_bind())
    op.execute(
        "ALTER TABLE transactions "
        "ALTER COLUMN transaction_type TYPE transaction_type "
        "USING transaction_type::text::transaction_type"
    )
    op.execute("DROP TYPE transaction_type_old")

    # --- 3) novas colunas em transactions ---------------------------------
    op.add_column("transactions", sa.Column("linked_transaction_id", sa.UUID(), nullable=True))
    op.add_column(
        "transactions",
        sa.Column("fx_rate_to_brl", sa.Numeric(precision=18, scale=8), nullable=True),
    )
    op.create_index(
        op.f("ix_transactions_linked_transaction_id"),
        "transactions",
        ["linked_transaction_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_transactions_linked_transaction_id",
        "transactions",
        "transactions",
        ["linked_transaction_id"],
        ["id"],
        deferrable=True,
        initially="DEFERRED",
    )

    # --- 4) trigger de imutabilidade: atualizado para fx_rate_to_brl -----
    # (imutável como qualquer campo financeiro) e linked_transaction_id
    # (mutável só de NULL -> um valor; uma vez setado, congelado).
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
                OR NEW.fx_rate_to_brl IS DISTINCT FROM OLD.fx_rate_to_brl
                OR NEW.created_at IS DISTINCT FROM OLD.created_at
            THEN
                RAISE EXCEPTION
                    'transaction % é um registro histórico protegido: campos financeiros não podem ser alterados. Use status=REVERSED + uma nova Transaction para corrigir.',
                    OLD.id
                    USING ERRCODE = '23000';
            END IF;

            -- linked_transaction_id: mutável só de NULL -> valor (uma vez).
            -- Depois de setado, vira imutável como os demais campos.
            IF OLD.linked_transaction_id IS NOT NULL
                AND NEW.linked_transaction_id IS DISTINCT FROM OLD.linked_transaction_id
            THEN
                RAISE EXCEPTION
                    'transaction %: linked_transaction_id já está definido e é imutável após estabelecido',
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

    # --- 5) trigger de consistência do par TRANSFER_OUT <-> TRANSFER_IN --
    # CONSTRAINT TRIGGER deferido para o COMMIT: as duas pernas costumam
    # ser gravadas em statements/momentos distintos (a segunda perna pode
    # nem existir ainda quando a primeira é criada), então a validação de
    # "aponta de volta simetricamente" só pode ser feita quando as duas
    # já estão gravadas na mesma transação de banco.
    op.execute("""
        CREATE OR REPLACE FUNCTION enforce_transfer_link_consistency()
        RETURNS TRIGGER AS $$
        DECLARE
            target RECORD;
        BEGIN
            IF NEW.linked_transaction_id IS NULL THEN
                RETURN NEW;
            END IF;

            IF NEW.linked_transaction_id = NEW.id THEN
                RAISE EXCEPTION
                    'transaction %: linked_transaction_id não pode apontar para si mesma',
                    NEW.id
                    USING ERRCODE = '23000';
            END IF;

            IF NEW.transaction_type NOT IN ('TRANSFER_OUT', 'TRANSFER_IN') THEN
                RAISE EXCEPTION
                    'transaction %: linked_transaction_id só é válido para TRANSFER_OUT/TRANSFER_IN (tipo atual: %)',
                    NEW.id, NEW.transaction_type
                    USING ERRCODE = '23000';
            END IF;

            SELECT id, transaction_type, linked_transaction_id
                INTO target
                FROM transactions
                WHERE id = NEW.linked_transaction_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION
                    'transaction %: linked_transaction_id % não existe',
                    NEW.id, NEW.linked_transaction_id
                    USING ERRCODE = '23000';
            END IF;

            IF target.transaction_type = NEW.transaction_type THEN
                RAISE EXCEPTION
                    'transaction %: par de transferência inválido — % não pode ligar com outra %',
                    NEW.id, NEW.transaction_type, NEW.transaction_type
                    USING ERRCODE = '23000';
            END IF;

            IF target.linked_transaction_id IS DISTINCT FROM NEW.id THEN
                RAISE EXCEPTION
                    'transaction %: a outra perna (%) não aponta de volta para esta transação',
                    NEW.id, target.id
                    USING ERRCODE = '23000';
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """)
    op.execute("""
        CREATE CONSTRAINT TRIGGER trg_transactions_transfer_link_consistency
        AFTER INSERT OR UPDATE ON transactions
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION enforce_transfer_link_consistency();
        """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_transactions_transfer_link_consistency ON transactions;")
    op.execute("DROP FUNCTION IF EXISTS enforce_transfer_link_consistency();")

    # Reverte enforce_transaction_immutability para a versão da Fase 4
    # (sem fx_rate_to_brl / linked_transaction_id).
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

    op.drop_constraint("fk_transactions_linked_transaction_id", "transactions", type_="foreignkey")
    op.drop_index(op.f("ix_transactions_linked_transaction_id"), table_name="transactions")
    op.drop_column("transactions", "fx_rate_to_brl")
    op.drop_column("transactions", "linked_transaction_id")

    op.execute("ALTER TYPE transaction_type RENAME TO transaction_type_new")
    old_enum = sa.Enum(*OLD_TRANSACTION_TYPES, name="transaction_type")
    old_enum.create(op.get_bind())
    op.execute(
        "ALTER TABLE transactions "
        "ALTER COLUMN transaction_type TYPE transaction_type "
        "USING transaction_type::text::transaction_type"
    )
    op.execute("DROP TYPE transaction_type_new")

    op.drop_constraint("fk_accounts_portfolio_id", "accounts", type_="foreignkey")
    op.drop_index(op.f("ix_accounts_portfolio_id"), table_name="accounts")
    op.drop_column("accounts", "portfolio_id")
    op.drop_index(op.f("ix_portfolios_user_id"), table_name="portfolios")
    op.drop_table("portfolios")
