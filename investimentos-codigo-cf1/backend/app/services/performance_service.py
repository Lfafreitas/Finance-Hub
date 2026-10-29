"""Evolução do patrimônio e resumo do widget (Painel-1).

Lê transações, cotações e lançamentos de caixa e entrega para as funções
puras de `app.domain.analytics.history`. Nenhuma regra de cálculo mora
aqui.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.analytics import kpis as kpi_domain
from app.domain.analytics.history import (
    CashMove,
    Holding,
    PricePoint,
    last_session_moves,
    portfolio_history,
)
from app.models.asset import Asset
from app.models.asset_class import AssetClass
from app.models.enums import AccountType
from app.repositories import cashflow as cashflow_repo
from app.repositories.accounts import list_accounts
from app.repositories.prices import list_price_series
from app.repositories.transactions import get_active_transactions
from app.schemas.performance import (
    AssetKpisRead,
    AssetMoveRead,
    BasketStatsRead,
    CurrencyHistory,
    CurrencyKpis,
    CurrencyWidget,
    GroupWeightRead,
    HistoryPointRead,
    PerformanceHistory,
    PortfolioKpisRead,
    PriceStatsRead,
    SparkPoint,
    WidgetSummary,
)
from app.services import market_data_service, overview_service
from app.services.dashboard_service import get_dashboard_summary
from app.services.exceptions import InvalidCashflowPeriodError
from app.services.market_data.yahoo import EXCHANGE_TRADED_CLASSES

MAX_DAYS = 1100
SPARK_DAYS = 30
MOVERS = 5


def _holdings(db: Session, user_id: UUID, until: date) -> list[Holding]:
    accounts = [a for a in list_accounts(db, user_id) if a.account_type is AccountType.BROKERAGE]
    by_pair = []
    for account in accounts:
        facts = get_active_transactions(db, account.id)
        for asset_id in {f.asset_id for f in facts if f.asset_id is not None}:
            pair = [f for f in facts if f.asset_id == asset_id]
            currencies = {f.currency_code for f in pair}
            # Posição em mais de uma moeda é inconsistente (dashboard):
            # fica fora de qualquer total.
            if len(currencies) == 1:
                by_pair.append((asset_id, currencies.pop(), pair))
    assets = {
        a.id: a
        for a in db.execute(select(Asset).where(Asset.id.in_({p[0] for p in by_pair}))).scalars()
    }
    prices = list_price_series(db, assets.keys(), until)
    return [
        Holding(
            ticker=assets[asset_id].ticker,
            currency_code=currency,
            facts=pair,
            prices=[
                PricePoint(p.price_date, p.price, p.currency_code) for p in prices.get(asset_id, [])
            ],
            exchange_traded=assets[asset_id].asset_class_code in EXCHANGE_TRADED_CLASSES,
        )
        for asset_id, currency, pair in by_pair
    ]


def _cash_moves(db: Session, user_id: UUID, until: date) -> list[CashMove]:
    accounts = cashflow_repo.list_cash_accounts(db, user_id)
    entries = cashflow_repo.list_active_entries(db, [a.id for a in accounts], until=until)
    return [CashMove(e.currency_code, e.entry_date, e.amount) for e in entries]


def get_history(
    db: Session, user_id: UUID, *, days: int | None = None, end: date | None = None
) -> PerformanceHistory:
    """Um ponto por dia, do primeiro movimento (ou dos últimos `days`
    dias) até `end`.
    """
    end = end or date.today()
    if days is not None and not 1 <= days <= MAX_DAYS:
        raise InvalidCashflowPeriodError(f"período deve ter de 1 a {MAX_DAYS} dias")
    holdings = _holdings(db, user_id, end)
    cash = _cash_moves(db, user_id, end)
    firsts = [h.facts[0].transaction_date for h in holdings] + [m.entry_date for m in cash]
    if not firsts:
        return PerformanceHistory(start=None, end=end, totals_by_currency=[])
    start = min(firsts)
    start = max(start, end - timedelta(days=(days or MAX_DAYS) - 1))
    span = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    series = portfolio_history(holdings, cash, span)
    return PerformanceHistory(
        start=start,
        end=end,
        totals_by_currency=[
            CurrencyHistory(
                currency_code=currency,
                points=[
                    HistoryPointRead(
                        date=p.day,
                        investments_value=p.investments_value,
                        investments_cost=p.investments_cost,
                        cash=p.cash,
                        total=p.total,
                        unpriced=list(p.unpriced),
                    )
                    for p in points
                ],
            )
            for currency, points in series.items()
        ],
    )


def get_widget(db: Session, user_id: UUID, *, today: date | None = None) -> WidgetSummary:
    today = today or date.today()
    overview = overview_service.get_overview(db, user_id, as_of=today)
    holdings = _holdings(db, user_id, today)
    moves = last_session_moves(holdings, today)
    spark_days = [today - timedelta(days=i) for i in range(SPARK_DAYS - 1, -1, -1)]
    spark = portfolio_history(holdings, [], spark_days)
    asset_ids = [a.id for a in market_data_service.held_assets(db, user_id)]
    blocks = []
    for item in overview.totals_by_currency:
        move = moves.get(item.currency_code)
        points = spark.get(item.currency_code, [])
        blocks.append(
            CurrencyWidget(
                currency_code=item.currency_code,
                total=item.total,
                investments_value=item.investments_value,
                investments_cost=item.investments_cost,
                investments_basis=item.investments_basis,
                unpriced=item.unpriced,
                result=item.result,
                result_pct=item.result_pct,
                day_change=move.change_value if move else None,
                day_change_pct=move.change_pct if move else None,
                day_date=move.last_date if move else None,
                movers=[
                    AssetMoveRead(
                        ticker=m.ticker,
                        quantity=m.quantity,
                        price=m.price,
                        price_date=m.price_date,
                        previous_price=m.previous_price,
                        previous_date=m.previous_date,
                        change_value=m.change_value,
                        change_pct=m.change_pct,
                    )
                    for m in (move.assets[:MOVERS] if move else [])
                ],
                spark=[
                    SparkPoint(date=p.day, value=p.investments_value)
                    for p in points
                    if p.investments_value != 0 or p.investments_cost != 0
                ],
            )
        )
    return WidgetSummary(
        as_of=today,
        generated_at=datetime.now(UTC),
        quotes_refreshed_at=market_data_service.last_refresh(db, asset_ids),
        totals_by_currency=blocks,
    )


def get_kpis(db: Session, user_id: UUID, *, today: date | None = None) -> PortfolioKpisRead:
    """Indicadores por moeda. As posições (custo, valor, proventos) vêm
    do dashboard; o desempenho de preço, do histórico diário gravado.
    """
    today = today or date.today()
    summary = get_dashboard_summary(db, user_id, None, today)
    moves = last_session_moves(_holdings(db, user_id, today), today)
    day_change = {
        (currency, move.ticker): move.change_pct
        for currency, block in moves.items()
        for move in block.assets
    }

    merged: dict[tuple[str, UUID], dict] = {}
    for p in summary.positions:
        if p.currency_code is None or p.quantity <= 0:
            continue
        item = merged.setdefault(
            (p.currency_code, p.asset_id),
            {"positions": [], "ticker": p.asset_ticker, "name": p.asset_name},
        )
        item["positions"].append(p)

    asset_ids = {asset_id for _currency, asset_id in merged}
    assets = {a.id: a for a in db.execute(select(Asset).where(Asset.id.in_(asset_ids))).scalars()}
    labels = dict(db.execute(select(AssetClass.code, AssetClass.label)).all())
    series = list_price_series(db, asset_ids, today)

    by_currency: dict[str, list[kpi_domain.Holding]] = {}
    for (currency, asset_id), item in merged.items():
        positions = item["positions"]
        asset = assets[asset_id]
        # Valor só quando TODAS as contas do ativo têm cotação.
        values = [p.market_value for p in positions]
        by_currency.setdefault(currency, []).append(
            kpi_domain.Holding(
                ticker=item["ticker"],
                name=item["name"],
                asset_class=asset.asset_class_code,
                asset_class_label=labels.get(asset.asset_class_code, asset.asset_class_code),
                currency_code=currency,
                quantity=sum((p.quantity for p in positions), start=kpi_domain._ZERO),
                cost=sum((p.total_cost_basis or 0 for p in positions), start=kpi_domain._ZERO),
                value=(
                    sum(values, start=kpi_domain._ZERO)
                    if all(v is not None for v in values)
                    else None
                ),
                dividends=sum(
                    (p.dividends_received or 0 for p in positions), start=kpi_domain._ZERO
                ),
                day_change_pct=day_change.get((currency, item["ticker"])),
                bars=[
                    kpi_domain.Bar(price.price_date, price.price)
                    for price in series.get(asset_id, [])
                    if price.currency_code == currency
                ],
                exchange_traded=asset.asset_class_code in EXCHANGE_TRADED_CLASSES,
            )
        )

    blocks = []
    for currency in sorted(by_currency, key=lambda c: ({"BRL": 0, "USD": 1}.get(c, 2), c)):
        result = kpi_domain.portfolio_kpis(by_currency[currency], today)
        if result is None:
            continue
        blocks.append(
            CurrencyKpis(
                currency_code=result.currency_code,
                value=result.value,
                cost=result.cost,
                pnl=result.pnl,
                return_pct=result.return_pct,
                complete=result.complete,
                unpriced=list(result.unpriced),
                top_ticker=result.top_ticker,
                top_weight=result.top_weight,
                top3_weight=result.top3_weight,
                effective_assets=result.effective_assets,
                positive=result.positive,
                negative=result.negative,
                best=result.best,
                worst=result.worst,
                dividends=result.dividends,
                yield_on_cost=result.yield_on_cost,
                total_return_pct=result.total_return_pct,
                groups=[GroupWeightRead(**g.__dict__) for g in result.groups],
                basket=(
                    BasketStatsRead(
                        tickers=list(result.basket.tickers),
                        share_of_portfolio=result.basket.share_of_portfolio,
                        return_1y=result.basket.return_1y,
                        volatility_1y=result.basket.volatility_1y,
                        max_drawdown_1y=result.basket.max_drawdown_1y,
                    )
                    if result.basket
                    else None
                ),
                assets=[
                    AssetKpisRead(
                        **{k: v for k, v in a.__dict__.items() if k != "stats"},
                        stats=PriceStatsRead(**a.stats.__dict__),
                    )
                    for a in result.assets
                ],
            )
        )
    return PortfolioKpisRead(as_of=today, totals_by_currency=blocks)
