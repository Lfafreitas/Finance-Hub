from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.domain.cashflow_engine.facts import CashEntryFact
from app.models.enums import CashflowNature

_ZERO = Decimal("0.0000")


@dataclass(frozen=True)
class CategoryTotals:
    """Totais de UMA categoria em UMA moeda. `own_*` são os lançamentos
    classificados diretamente nela; `total_*` somam as subcategorias.
    `category_id` nulo é a linha "sem categoria".
    """

    category_id: UUID | None
    own_expenses: Decimal
    own_income: Decimal
    total_expenses: Decimal
    total_income: Decimal


class CategoryBreakdownCalculator:
    """Gasto e renda por categoria. Só EXPENSE e INCOME entram: terceiros,
    ajustes, transferências e não classificados não são gasto nem renda.

    A soma dos `own_expenses` de todas as linhas (com a "sem categoria")
    é, por construção, o `expenses` do resumo do mesmo período — o
    service confere isso antes de responder.
    """

    @staticmethod
    def calculate(
        facts: Iterable[CashEntryFact],
        start: date,
        end: date,
        parent_of: Mapping[UUID, UUID | None],
    ) -> dict[str, list[CategoryTotals]]:
        if start > end:
            raise ValueError("início do período depois do fim")
        own: dict[str, dict[UUID | None, list[Decimal]]] = {}
        for fact in facts:
            if not start <= fact.entry_date <= end:
                continue
            if fact.nature not in (CashflowNature.EXPENSE, CashflowNature.INCOME):
                continue
            if fact.category_id is not None and fact.category_id not in parent_of:
                raise ValueError(f"categoria desconhecida: {fact.category_id}")
            bucket = own.setdefault(fact.currency_code, {}).setdefault(
                fact.category_id, [_ZERO, _ZERO]
            )
            if fact.nature is CashflowNature.EXPENSE:
                bucket[0] -= fact.amount
            else:
                bucket[1] += fact.amount

        result: dict[str, list[CategoryTotals]] = {}
        for currency in sorted(own):
            totals = {category: list(values) for category, values in own[currency].items()}
            for category, values in own[currency].items():
                parent = parent_of.get(category) if category is not None else None
                if parent is not None:
                    rolled = totals.setdefault(parent, [_ZERO, _ZERO])
                    rolled[0] += values[0]
                    rolled[1] += values[1]
            result[currency] = [
                CategoryTotals(
                    category_id=category,
                    own_expenses=own[currency].get(category, [_ZERO, _ZERO])[0],
                    own_income=own[currency].get(category, [_ZERO, _ZERO])[1],
                    total_expenses=values[0],
                    total_income=values[1],
                )
                for category, values in totals.items()
            ]
        return result
