"""Schemas das análises da carteira (Análises-1). Tudo por moeda:
moedas nunca são somadas nem convertidas.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class WeightRead(BaseModel):
    key: str
    label: str
    value: Decimal
    weight: Decimal


class ConcentrationRead(BaseModel):
    """`basis`: MARKET (valor de mercado) quando toda posição aberta da
    moeda tem cotação; COST (custo) quando alguma não tem.
    """

    basis: str
    total: Decimal
    by_asset: list[WeightRead]
    by_class: list[WeightRead]
    by_account: list[WeightRead]
    # Renda variável, renda fixa, fundos — mesmas chaves de /overview.
    by_group: list[WeightRead]
    top3_weight: Decimal
    flags: list[str]


class HoldingAssumptionRead(BaseModel):
    key: str
    weight: Decimal
    volatility: Decimal
    volatility_from_history: bool
    history_returns: int
    expected_return: Decimal


class ExcludedHoldingRead(BaseModel):
    key: str
    reason: str


class ScenariosRead(BaseModel):
    """Retornos como fração (0.0123 = 1,23%). `probability_below_today`
    é a chance, no modelo, de terminar o período abaixo do valor de hoje.
    """

    until: date
    horizon_days: int
    value_today: Decimal
    expected_return: Decimal
    volatility: Decimal
    pessimistic_return: Decimal
    realistic_return: Decimal
    optimistic_return: Decimal
    pessimistic_value: Decimal
    realistic_value: Decimal
    optimistic_value: Decimal
    probability_below_today: Decimal
    assumptions: list[HoldingAssumptionRead]
    excluded: list[ExcludedHoldingRead]


class MonthAmountRead(BaseModel):
    month: str
    amount: Decimal


class PaceProjectionRead(BaseModel):
    pace: str
    monthly: Decimal
    remaining_total: Decimal
    year_end_total: Decimal


class ContributionPaceRead(BaseModel):
    year: int
    total_year: Decimal
    months: list[MonthAmountRead]
    remaining_months: int
    projections: list[PaceProjectionRead]


class CurrencyAnalytics(BaseModel):
    currency_code: str
    market_value: Decimal | None
    market_data_as_of: date | None
    concentration: ConcentrationRead | None
    scenarios: ScenariosRead | None
    scenarios_unavailable_reason: str | None
    contributions: ContributionPaceRead | None
    alerts: list[str]


class PortfolioAnalytics(BaseModel):
    reference_date: date
    quotes_refreshed_at: datetime | None
    blocks: list[CurrencyAnalytics]
