"""edicao: troca de livro da conta considera contraparte de transferência

Revision ID: f1d8b3a6c2e9
Revises: e5c1a9f07b42
Create Date: 2026-10-06

Só substitui a função do trigger `trg_accounts_type_stability`. Uma
conta BROKERAGE sem lançamento próprio pode ser a contraparte de um
aporte (perna única no livro de caixa); se ela virasse conta de caixa,
esse aporte passaria a ser lido como transferência interna com perna
órfã. Nenhuma tabela ou dado é alterado.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1d8b3a6c2e9"
down_revision: str | Sequence[str] | None = "e5c1a9f07b42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION = """
    CREATE OR REPLACE FUNCTION enforce_account_type_stability()
    RETURNS TRIGGER AS $$
    BEGIN
        IF NEW.account_type IS DISTINCT FROM OLD.account_type
            AND (NEW.account_type = 'BROKERAGE') <> (OLD.account_type = 'BROKERAGE')
            AND (
                EXISTS (SELECT 1 FROM transactions WHERE account_id = OLD.id)
                OR EXISTS (SELECT 1 FROM cashflow_entries WHERE account_id = OLD.id)
                {counterparty}
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
    """


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        _FUNCTION.format(
            counterparty=(
                "OR EXISTS (SELECT 1 FROM cashflow_entries "
                "WHERE counterparty_account_id = OLD.id)"
            )
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(_FUNCTION.format(counterparty=""))
