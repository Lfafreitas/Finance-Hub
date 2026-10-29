"""Ritmo de aporte (Análises-1).

Aporte é o mesmo do dashboard: dinheiro que entrou (ou saiu) do escopo
— depósitos, retiradas e transferências com contas de fora. Aqui ele é
agrupado por mês dentro do ano de referência e projetado até dezembro
em três ritmos:

- AVERAGE: média mensal desde o primeiro mês com aporte no ano;
- LAST_3: média dos últimos 3 meses (até o mês de referência);
- LAST_MONTH: o mês de referência.

A projeção soma ao que já entrou no ano o ritmo vezes os meses que
faltam DEPOIS do mês de referência. Nenhum mercado entra aqui.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

_MONEY = Decimal("0.01")


@dataclass(frozen=True)
class MonthAmount:
    month: str  # AAAA-MM
    amount: Decimal


@dataclass(frozen=True)
class PaceProjection:
    pace: str
    monthly: Decimal
    # O que ainda entraria até dezembro nesse ritmo.
    remaining_total: Decimal
    year_end_total: Decimal


@dataclass(frozen=True)
class ContributionPace:
    year: int
    total_year: Decimal
    months: tuple[MonthAmount, ...]
    remaining_months: int
    projections: tuple[PaceProjection, ...]


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def contribution_pace(
    events: list[tuple[date, Decimal]], reference: date
) -> ContributionPace | None:
    """`events`: (data, valor com sinal). None quando não há aporte no
    ano de referência até a data de referência.
    """
    year = reference.year
    by_month: dict[int, Decimal] = {}
    for when, amount in events:
        if when.year == year and when <= reference:
            by_month[when.month] = by_month.get(when.month, Decimal(0)) + amount
    if not by_month:
        return None

    first = min(by_month)
    current = reference.month
    months = tuple(
        MonthAmount(month=f"{year}-{m:02d}", amount=_money(by_month.get(m, Decimal(0))))
        for m in range(first, current + 1)
    )
    total = sum(by_month.values(), start=Decimal(0))
    elapsed = current - first + 1
    last3_months = range(max(first, current - 2), current + 1)
    last3 = sum((by_month.get(m, Decimal(0)) for m in last3_months), start=Decimal(0))
    paces = {
        "AVERAGE": total / elapsed,
        "LAST_3": last3 / len(last3_months),
        "LAST_MONTH": by_month.get(current, Decimal(0)),
    }
    remaining = 12 - current
    projections = tuple(
        PaceProjection(
            pace=name,
            monthly=_money(monthly),
            remaining_total=_money(monthly * remaining),
            year_end_total=_money(total + monthly * remaining),
        )
        for name, monthly in paces.items()
    )
    return ContributionPace(
        year=year,
        total_year=_money(total),
        months=months,
        remaining_months=remaining,
        projections=projections,
    )
