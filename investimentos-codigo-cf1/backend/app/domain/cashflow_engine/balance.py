from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.domain.cashflow_engine.facts import CashEntryFact
from app.models.enums import AccountType


@dataclass(frozen=True)
class AccountBalance:
    account_id: UUID
    account_type: AccountType
    currency_code: str
    balance: Decimal


class BalanceCalculator:
    """Saldo de uma conta = soma dos lançamentos até a data (inclusive).

    Não existe saldo inicial fora do livro: ele é um lançamento
    ADJUSTMENT como qualquer outro. Cartão de crédito fica negativo
    enquanto houver fatura a pagar.
    """

    @staticmethod
    def calculate(facts: Iterable[CashEntryFact], as_of: date) -> list[AccountBalance]:
        totals: dict[UUID, Decimal] = {}
        meta: dict[UUID, tuple[AccountType, str]] = {}
        for fact in facts:
            known = meta.setdefault(fact.account_id, (fact.account_type, fact.currency_code))
            if known != (fact.account_type, fact.currency_code):
                raise ValueError(f"conta {fact.account_id} aparece com tipo ou moeda diferentes")
            if fact.entry_date <= as_of:
                totals[fact.account_id] = totals.get(fact.account_id, Decimal(0)) + fact.amount
        return [
            AccountBalance(
                account_id=account_id,
                account_type=meta[account_id][0],
                currency_code=meta[account_id][1],
                balance=balance,
            )
            for account_id, balance in totals.items()
        ]
