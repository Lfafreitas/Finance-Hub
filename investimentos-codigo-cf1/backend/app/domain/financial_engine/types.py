"""Tipos de dado do Financial Engine.

Decisão de design importante: `TransactionFact` NÃO tem campo `status`.
A exclusão de transações `REVERSED` é responsabilidade exclusiva da
camada de acesso a dado (`app/repositories/transactions.py`), que só
converte para `TransactionFact` as transações `ACTIVE`. Isso torna
estruturalmente impossível uma `REVERSED` "vazar" para dentro do
Financial Engine — não é uma convenção a lembrar, é a própria forma do
dado que impede.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.models.enums import TransactionType


@dataclass(frozen=True)
class TransactionFact:
    """Espelho puro (sem ORM) de uma Transaction já confirmada como
    ACTIVE. Pré-condição de quem constrói uma lista de facts: já vêm
    ordenadas cronologicamente por `transaction_date`, com desempate técnico
    por `created_at` (ver `TRANSACTION_ORDER` em
    `app/repositories/transactions.py`) — `created_at` é a ordem de
    gravação do registro, NÃO a ordem econômica real. O Financial
    Engine NÃO reordena, para não embutir uma regra de desempate
    econômica (ex.: "no mesmo dia, compra antes de venda").
    """

    id: UUID
    account_id: UUID
    asset_id: UUID | None
    transaction_type: TransactionType
    quantity: Decimal | None
    unit_price: Decimal | None
    fees: Decimal
    gross_amount: Decimal
    currency_code: str
    transaction_date: date
    linked_transaction_id: UUID | None = None


@dataclass(frozen=True)
class PositionResult:
    """Resultado calculado — nunca persistido nesta fase (decisão D1).
    Tudo aqui é 100% recomputável a partir de uma lista de
    `TransactionFact` do mesmo par (account_id, asset_id).

    `total_cost_basis` = custo de aquisição do que ainda está em
    carteira (remanescente) — nome mantido por compatibilidade com
    quem já consome este campo (Fases 6/7), mesmo que
    "remaining_cost_basis" descrevesse melhor a semântica.

    `realized_cost_basis` (Fase 8, D-E1) = custo de aquisição das
    unidades que já foram VENDIDAS — soma do `cost_removed` que o
    `PositionCalculator` calcula a cada `SELL` usando a mesma regra de
    custo médio ponderado, e que antes era descartado após o uso.
    `realized_cost_basis + total_cost_basis` ficam desacoplados de
    propósito: usar o remanescente como base de um retorno realizado
    estaria errado (não é o custo do que foi vendido).
    """

    account_id: UUID
    asset_id: UUID
    quantity: Decimal
    average_cost: Decimal
    total_cost_basis: Decimal
    realized_gain: Decimal
    dividends_received: Decimal
    realized_cost_basis: Decimal = Decimal(0)
