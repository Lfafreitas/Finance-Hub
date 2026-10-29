"""Único ponto de acesso a `Transaction` para fins de cálculo
financeiro. Regra 2 da Fase 5: "manter filtragem centralizada no
acesso aos dados; não duplicar essa regra desnecessariamente em vários
pontos" — este módulo é esse ponto único. Nada além daqui deveria
montar uma query em `Transaction` para alimentar o Financial Engine.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.financial_engine.types import TransactionFact
from app.models.enums import TransactionStatus
from app.models.transaction import Transaction

# Ordenação canônica das Transactions (Fase 10b, same-day ordering).
#
# ATENÇÃO — `created_at` é APENAS um desempate técnico e determinístico:
# é o momento em que o REGISTRO foi criado no nosso sistema, não a hora
# econômica em que a operação aconteceu. Duas operações com a mesma
# `transaction_date` são ordenadas pela ordem em que foram gravadas, o
# que NÃO significa que essa tenha sido a ordem real de execução (ex.:
# uma venda às 09:00 importada depois de uma compra das 15:00 do mesmo
# dia). O sistema não possui timestamp econômico; se for necessário no
# futuro, deve ser proposto e aprovado como mudança de modelo/migration.
TRANSACTION_ORDER = (Transaction.transaction_date, Transaction.created_at)


def list_transactions(
    session: Session, account_id: UUID, asset_id: UUID | None = None
) -> list[Transaction]:
    """Histórico completo (ACTIVE e REVERSED) para exibição/auditoria —
    propósito diferente de `get_active_transactions`: aqui devolvemos
    os objetos ORM (não `TransactionFact`) porque isso alimenta uma
    tela de histórico, não o Financial Engine. Uma REVERSED continua
    visível aqui de propósito (rastreabilidade) — só não entra em
    cálculo.
    """
    stmt = (
        select(Transaction).where(Transaction.account_id == account_id).order_by(*TRANSACTION_ORDER)
    )
    if asset_id is not None:
        stmt = stmt.where(Transaction.asset_id == asset_id)

    return list(session.execute(stmt).scalars().all())


def get_active_transactions_for_accounts(
    session: Session, account_ids: Sequence[UUID]
) -> list[Transaction]:
    """Transactions ACTIVE de um CONJUNTO de contas, como objetos ORM
    (com `id`, `source`, `fx_rate_to_brl`, etc.) — usada pelo scan de
    reconciliação (Fase 10b), que precisa de campos que
    `TransactionFact` não carrega. Uma lista vazia de `account_ids`
    devolve `[]` sem consultar o banco.

    Não filtra por usuário: quem chama já deve ter resolvido
    `account_ids` a partir de contas cuja posse foi validada.
    """
    if not account_ids:
        return []
    stmt = (
        select(Transaction)
        .where(
            Transaction.account_id.in_(account_ids),
            Transaction.status == TransactionStatus.ACTIVE,
        )
        .order_by(*TRANSACTION_ORDER)
    )
    return list(session.execute(stmt).scalars().all())


def get_active_transactions(
    session: Session, account_id: UUID, asset_id: UUID | None = None
) -> list[TransactionFact]:
    """Devolve as transações ACTIVE de uma conta (opcionalmente
    filtradas por ativo), já ordenadas por `transaction_date`, já
    convertidas para `TransactionFact` — que não tem campo `status`,
    então uma REVERSED não tem como chegar ao Financial Engine por
    este caminho.
    """
    stmt = (
        select(Transaction)
        .where(Transaction.account_id == account_id)
        .where(Transaction.status == TransactionStatus.ACTIVE)
        .order_by(*TRANSACTION_ORDER)
    )
    if asset_id is not None:
        stmt = stmt.where(Transaction.asset_id == asset_id)

    rows = session.execute(stmt).scalars().all()
    return [_to_fact(row) for row in rows]


def _to_fact(row: Transaction) -> TransactionFact:
    return TransactionFact(
        id=row.id,
        account_id=row.account_id,
        asset_id=row.asset_id,
        transaction_type=row.transaction_type,
        quantity=row.quantity,
        unit_price=row.unit_price,
        fees=row.fees,
        gross_amount=row.gross_amount,
        currency_code=row.currency_code,
        transaction_date=row.transaction_date,
        linked_transaction_id=row.linked_transaction_id,
    )
