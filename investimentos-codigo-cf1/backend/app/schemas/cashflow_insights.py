"""Visão mês a mês e "onde dá para melhorar" do livro de caixa (Visual-1)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class MonthFlow(BaseModel):
    """Um mês de UMA moeda. `surplus` = renda − gastos (o que sobrou da
    renda depois dos gastos). Não classificado fica à parte: enquanto
    houver, entradas e saídas estão incompletas.
    """

    month: str
    income: Decimal
    expenses: Decimal
    surplus: Decimal
    net_invested: Decimal
    unclassified_net: Decimal
    entry_count: int


class CurrencyMonthlyFlows(BaseModel):
    currency_code: str
    months: list[MonthFlow]


class MonthlyFlows(BaseModel):
    end_month: str
    months: int
    totals_by_currency: list[CurrencyMonthlyFlows]


class CategoryChangeRead(BaseModel):
    key: str
    label: str
    current: Decimal
    average: Decimal
    difference: Decimal


class RecurringItemRead(BaseModel):
    label: str
    monthly_average: Decimal


class CategoryShareRead(BaseModel):
    key: str | None
    label: str | None
    amount: Decimal
    share: Decimal


class CurrencySpendingInsights(BaseModel):
    """`history_months`: quantos dos 3 meses anteriores têm gasto — com
    menos de 2, "acima do normal" não é calculado. Frações em 0..1.
    """

    currency_code: str
    month: str
    expenses: Decimal
    history_months: int
    above_normal: list[CategoryChangeRead]
    recurring: list[RecurringItemRead]
    recurring_total: Decimal
    small_count: int
    small_total: Decimal
    small_limit: Decimal
    top_categories: list[CategoryShareRead]
    top_share: Decimal | None
    unclassified_outflow: Decimal
    unclassified_share: Decimal | None


class SpendingInsightsRead(BaseModel):
    month: str
    totals_by_currency: list[CurrencySpendingInsights]
