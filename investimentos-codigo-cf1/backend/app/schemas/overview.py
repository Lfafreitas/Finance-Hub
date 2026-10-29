"""Patrimônio por moeda (Visual-1): investimentos + caixa, sem somar
moedas nem converter câmbio.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class OverviewPart(BaseModel):
    """Uma fatia do patrimônio. `weight` em 0..1 sobre a soma das
    fatias positivas (a fatura do cartão é dívida e fica à parte).
    """

    key: str
    label: str
    value: Decimal
    weight: Decimal


class CurrencyOverview(BaseModel):
    """`investments_basis`: MARKET (toda posição com cotação), MIXED
    (parte pelo custo, listada em `unpriced`) ou COST (nenhuma cotação).
    `result` = não realizado (só do que tem cotação) + realizado +
    proventos; `result_pct` = `result` / custo das posições abertas.
    """

    currency_code: str
    total: Decimal
    investments_value: Decimal
    investments_cost: Decimal
    investments_basis: str
    unpriced: list[str]
    result: Decimal
    result_pct: Decimal | None
    result_complete: bool
    net_contributions: Decimal
    liquid: Decimal
    reserve: Decimal
    card: Decimal
    parts: list[OverviewPart]
    investment_groups: list[OverviewPart]


class Overview(BaseModel):
    as_of: date
    totals_by_currency: list[CurrencyOverview]
