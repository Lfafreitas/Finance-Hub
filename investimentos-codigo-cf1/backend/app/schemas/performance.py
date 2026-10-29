"""Evolução do patrimônio e resumo do widget (Painel-1). Moedas nunca se
somam: cada bloco é de uma moeda.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class HistoryPointRead(BaseModel):
    """`investments_value`: cotação quando existe, custo quando não
    (tickers em `unpriced`). `cash` = conta + reserva + cartão.
    """

    date: date
    investments_value: Decimal
    investments_cost: Decimal
    cash: Decimal
    total: Decimal
    unpriced: list[str]


class CurrencyHistory(BaseModel):
    currency_code: str
    points: list[HistoryPointRead]


class PerformanceHistory(BaseModel):
    start: date | None
    end: date
    totals_by_currency: list[CurrencyHistory]


class AssetMoveRead(BaseModel):
    ticker: str
    quantity: Decimal
    price: Decimal
    price_date: date
    previous_price: Decimal
    previous_date: date
    change_value: Decimal
    change_pct: Decimal


class SparkPoint(BaseModel):
    date: date
    value: Decimal


class CurrencyWidget(BaseModel):
    """Um bloco por moeda. `day_*` vem só de ativos negociados em bolsa
    com duas cotações; nulo quando não há nenhum.
    """

    currency_code: str
    total: Decimal
    investments_value: Decimal
    investments_cost: Decimal
    investments_basis: str
    unpriced: list[str]
    result: Decimal
    result_pct: Decimal | None
    day_change: Decimal | None
    day_change_pct: Decimal | None
    day_date: date | None
    movers: list[AssetMoveRead]
    spark: list[SparkPoint]


class WidgetSummary(BaseModel):
    as_of: date
    generated_at: datetime
    quotes_refreshed_at: datetime | None
    totals_by_currency: list[CurrencyWidget]


# --- KPIs-1: indicadores da carteira e de cada ativo -----------------------------


class PriceStatsRead(BaseModel):
    """Desempenho de PREÇO (sem proventos), do histórico diário gravado.
    Campo nulo = o histórico não cobre o período.
    """

    last_price: Decimal | None
    last_date: date | None
    return_1m: Decimal | None
    return_3m: Decimal | None
    return_ytd: Decimal | None
    return_1y: Decimal | None
    volatility_1y: Decimal | None
    max_drawdown_1y: Decimal | None
    low_52w: Decimal | None
    high_52w: Decimal | None
    position_52w: Decimal | None
    from_high: Decimal | None


class AssetKpisRead(BaseModel):
    ticker: str
    name: str
    asset_class: str
    asset_class_label: str
    quantity: Decimal
    cost: Decimal
    value: Decimal | None
    weight: Decimal | None
    pnl: Decimal | None
    return_pct: Decimal | None
    contribution: Decimal | None
    dividends: Decimal
    yield_on_cost: Decimal | None
    day_change_pct: Decimal | None
    stats: PriceStatsRead
    total_return_pct: Decimal | None = None


class GroupWeightRead(BaseModel):
    asset_class: str
    label: str
    value: Decimal
    weight: Decimal


class BasketStatsRead(BaseModel):
    tickers: list[str]
    share_of_portfolio: Decimal
    return_1y: Decimal
    volatility_1y: Decimal
    max_drawdown_1y: Decimal


class CurrencyKpis(BaseModel):
    currency_code: str
    value: Decimal
    cost: Decimal
    pnl: Decimal
    return_pct: Decimal | None
    complete: bool
    unpriced: list[str]
    top_ticker: str | None
    top_weight: Decimal | None
    top3_weight: Decimal | None
    effective_assets: Decimal | None
    positive: int
    negative: int
    best: str | None
    worst: str | None
    dividends: Decimal
    yield_on_cost: Decimal | None
    groups: list[GroupWeightRead]
    basket: BasketStatsRead | None
    assets: list[AssetKpisRead]
    total_return_pct: Decimal | None = None


class PortfolioKpisRead(BaseModel):
    as_of: date
    totals_by_currency: list[CurrencyKpis]


class MaturityRead(BaseModel):
    ticker: str
    name: str
    currency_code: str
    maturity_date: date
    days_left: int
    annual_rate: Decimal | None
    cost: Decimal
    value: Decimal | None
    estimated_at_maturity: Decimal | None


class AgendaRead(BaseModel):
    """Vencimentos de renda fixa em ordem de data (cada um na sua moeda)."""

    as_of: date
    maturities: list[MaturityRead]
    missing_maturity: list[str]


class BenchmarkPoint(BaseModel):
    date: date
    portfolio: Decimal
    benchmark: Decimal


class BenchmarkComparison(BaseModel):
    """Os mesmos aportes, nas mesmas datas, aplicados na referência."""

    currency_code: str
    benchmark: str  # "SPY" | "CDI"
    benchmark_label: str
    available: bool
    reason: str | None = None
    net_invested: Decimal | None = None
    portfolio_value: Decimal | None = None
    benchmark_value: Decimal | None = None
    difference: Decimal | None = None
    portfolio_return: Decimal | None = None
    benchmark_return: Decimal | None = None
    unpriced: list[str] = []
    points: list[BenchmarkPoint] = []


class BenchmarksRead(BaseModel):
    as_of: date
    comparisons: list[BenchmarkComparison]


class AllocationRowRead(BaseModel):
    asset_class: str
    label: str
    value: Decimal
    current_weight: Decimal
    target_weight: Decimal | None
    gap: Decimal | None
    value_gap: Decimal | None


class CurrencyAllocation(BaseModel):
    currency_code: str
    total: Decimal
    has_targets: bool
    rows: list[AllocationRowRead]


class AllocationRead(BaseModel):
    currencies: list[CurrencyAllocation]


class AllocationTargetItem(BaseModel):
    asset_class_code: str = Field(max_length=30)
    target_weight: Decimal = Field(ge=0, le=1, max_digits=5, decimal_places=4)


class AllocationTargetsWrite(BaseModel):
    """Lista vazia apaga os alvos da moeda. Senão, a soma tem de dar 100%."""

    targets: list[AllocationTargetItem] = Field(max_length=20)


class FinancialHealthRead(BaseModel):
    """Uma moeda. Médias dos últimos meses fechados com lançamento
    (`months`). `complete` falso: há lançamento sem classificação nesses
    meses (`incomplete_months`), e a cobertura vira um teto.
    """

    currency_code: str
    months: list[str]
    avg_income: Decimal | None
    avg_expenses: Decimal | None
    avg_invested: Decimal | None
    savings_rate: Decimal | None
    reserve: Decimal
    coverage_months: Decimal | None
    complete: bool
    incomplete_months: list[str]


class FinancialHealthIndex(BaseModel):
    as_of: date
    currencies: list[FinancialHealthRead]
