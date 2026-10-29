"""Saúde financeira de uma moeda: quantos meses de gastos a reserva cobre
e quanto da renda sobra (taxa de poupança).

Base: os últimos meses FECHADOS do controle financeiro (o mês corrente
ainda está pela metade). Mês sem renda, sem gasto e sem lançamento por
classificar não entra na média (ex.: só o rendimento da reserva).

- `coverage_months` = reserva / gasto médio por mês;
- `savings_rate` = (renda − gastos) / renda, somando os meses;
- `complete` = nenhum mês considerado tem lançamento sem classificação.
  Enquanto houver, gastos e renda estão incompletos: a cobertura é um
  TETO (o gasto real é maior ou igual) e a taxa de poupança, uma leitura
  provisória. A tela diz isso junto do número.

Puro: recebe os meses já calculados pelo controle financeiro.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

_ZERO = Decimal(0)
WINDOW = 3


class MonthLike(Protocol):
    month: str
    income: Decimal
    expenses: Decimal
    net_invested: Decimal
    unclassified_net: Decimal
    entry_count: int


@dataclass(frozen=True)
class FinancialHealth:
    months: list[str]
    avg_income: Decimal | None
    avg_expenses: Decimal | None
    avg_invested: Decimal | None
    savings_rate: Decimal | None
    reserve: Decimal
    coverage_months: Decimal | None
    complete: bool
    incomplete_months: list[str]


def financial_health(months: Sequence[MonthLike], reserve: Decimal) -> FinancialHealth:
    used = [m for m in months if m.income > 0 or m.expenses > 0 or m.unclassified_net != 0][
        -WINDOW:
    ]
    if not used:
        return FinancialHealth([], None, None, None, None, reserve, None, True, [])
    n = Decimal(len(used))
    income = sum((m.income for m in used), start=_ZERO)
    expenses = sum((m.expenses for m in used), start=_ZERO)
    invested = sum((m.net_invested for m in used), start=_ZERO)
    avg_expenses = expenses / n
    incomplete = [m.month for m in used if m.unclassified_net != 0]
    return FinancialHealth(
        months=[m.month for m in used],
        avg_income=income / n,
        avg_expenses=avg_expenses,
        avg_invested=invested / n,
        savings_rate=(income - expenses) / income if income > 0 else None,
        reserve=reserve,
        coverage_months=reserve / avg_expenses if avg_expenses > 0 and reserve > 0 else None,
        complete=not incomplete,
        incomplete_months=incomplete,
    )
