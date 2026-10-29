"""Análises da carteira (Análises-1).

Parte do mesmo resumo do dashboard (posições, valoração, aportes) — não
existe uma segunda conta de posição. Este service só junta o que o
domínio `analytics` precisa: valores por ativo, classe e conta,
histórico de preços e os aportes.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.analytics import (
    Holding,
    Slice,
    asset_group,
    concentration,
    contribution_pace,
    portfolio_scenarios,
)
from app.models.account import Account
from app.models.asset import Asset
from app.models.asset_class import AssetClass
from app.models.asset_price import AssetPrice
from app.models.enums import PriceSource
from app.schemas.analytics import (
    ConcentrationRead,
    ContributionPaceRead,
    CurrencyAnalytics,
    ExcludedHoldingRead,
    HoldingAssumptionRead,
    MonthAmountRead,
    PaceProjectionRead,
    PortfolioAnalytics,
    ScenariosRead,
    WeightRead,
)
from app.schemas.dashboard import DashboardCurrencyTotals, PositionSummary
from app.services import market_data_service
from app.services.dashboard_service import get_dashboard_summary
from app.services.overview_service import GROUP_LABELS, investment_group

HISTORY_DAYS = 400
STALE_QUOTE_DAYS = 7


def _history(
    db: Session, asset_ids: list[UUID], reference: date
) -> dict[UUID, tuple[tuple[date, Decimal], ...]]:
    """Fechamentos por ativo, um por data; na mesma data, o manual vale."""
    if not asset_ids:
        return {}
    stmt = select(AssetPrice).where(
        AssetPrice.asset_id.in_(asset_ids),
        AssetPrice.price_date <= reference,
        AssetPrice.price_date >= reference - timedelta(days=HISTORY_DAYS),
    )
    chosen: dict[tuple[UUID, date], AssetPrice] = {}
    for price in db.execute(stmt).scalars():
        key = (price.asset_id, price.price_date)
        current = chosen.get(key)
        if current is None or (
            price.source is PriceSource.MANUAL and current.source is not PriceSource.MANUAL
        ):
            chosen[key] = price
    result: dict[UUID, list[tuple[date, Decimal]]] = {}
    for (asset_id, day), price in chosen.items():
        result.setdefault(asset_id, []).append((day, price.price))
    return {asset_id: tuple(sorted(rows)) for asset_id, rows in result.items()}


def _contribution_events(block: DashboardCurrencyTotals) -> list[tuple[date, Decimal]]:
    """A evolução do dashboard é acumulada; aqui volta a ser evento a evento."""
    events: list[tuple[date, Decimal]] = []
    previous = Decimal(0)
    for point in block.contribution_evolution:
        events.append((point.date, point.cumulative_net_contribution - previous))
        previous = point.cumulative_net_contribution
    return events


def _block_analytics(
    db: Session,
    block: DashboardCurrencyTotals,
    positions: list[PositionSummary],
    assets: dict[UUID, Asset],
    class_labels: dict[str, str],
    account_names: dict[UUID, str],
    history: dict[UUID, tuple[tuple[date, Decimal], ...]],
    reference: date,
    until: date,
) -> CurrencyAnalytics:
    currency = block.currency_code
    open_positions = [p for p in positions if p.currency_code == currency and p.quantity > 0]
    fully_priced = block.market_value is not None
    basis = "MARKET" if fully_priced else "COST"

    slices: list[Slice] = []
    for position in open_positions:
        asset = assets[position.asset_id]
        value = position.market_value if fully_priced else position.total_cost_basis
        slices.append(
            Slice(
                asset_key=str(asset.id),
                asset_label=asset.ticker,
                class_key=asset.asset_class_code,
                class_label=class_labels.get(asset.asset_class_code, asset.asset_class_code),
                account_key=str(position.account_id),
                account_label=account_names.get(position.account_id, "conta"),
                value=value or Decimal(0),
                group_key=investment_group(asset.asset_class_code),
                group_label=GROUP_LABELS[investment_group(asset.asset_class_code)],
            )
        )
    conc = concentration(slices)
    concentration_read = (
        ConcentrationRead(
            basis=basis,
            total=conc.total,
            by_asset=[WeightRead(**w.__dict__) for w in conc.by_asset],
            by_class=[WeightRead(**w.__dict__) for w in conc.by_class],
            by_account=[WeightRead(**w.__dict__) for w in conc.by_account],
            by_group=[WeightRead(**w.__dict__) for w in conc.by_group],
            top3_weight=conc.top3_weight,
            flags=list(conc.flags),
        )
        if conc
        else None
    )

    # Cenários: só o que tem risco de mercado E cotação. Mesmo ativo em
    # duas contas é um ativo só.
    values: dict[UUID, Decimal] = {}
    excluded: dict[str, str] = {}
    for position in open_positions:
        asset = assets[position.asset_id]
        group = asset_group(asset.asset_class_code)
        if group is None:
            excluded[asset.ticker] = (
                "renda fixa ou classe sem risco de mercado modelado: fica fora dos cenários"
            )
        elif position.market_value is None:
            excluded[asset.ticker] = "sem cotação: fica fora dos cenários até ter preço"
        else:
            values[asset.id] = values.get(asset.id, Decimal(0)) + position.market_value
    holdings = [
        Holding(
            key=assets[asset_id].ticker,
            value=value,
            group=asset_group(assets[asset_id].asset_class_code) or "",
            currency_code=currency,
            history=history.get(asset_id, ()),
        )
        for asset_id, value in sorted(values.items(), key=lambda item: assets[item[0]].ticker)
    ]
    horizon = (until - reference).days
    result = portfolio_scenarios(holdings, horizon)
    scenarios = None
    reason = None
    if horizon <= 0:
        reason = "a data final dos cenários precisa ser depois de hoje"
    elif result is None:
        reason = "nenhuma posição com risco de mercado e cotação nesta moeda"
    else:
        scenarios = ScenariosRead(
            until=until,
            horizon_days=result.horizon_days,
            value_today=result.value_today,
            expected_return=result.expected_return,
            volatility=result.volatility,
            pessimistic_return=result.pessimistic_return,
            realistic_return=result.realistic_return,
            optimistic_return=result.optimistic_return,
            pessimistic_value=result.pessimistic_value,
            realistic_value=result.realistic_value,
            optimistic_value=result.optimistic_value,
            probability_below_today=result.probability_below_today,
            assumptions=[HoldingAssumptionRead(**a.__dict__) for a in result.assumptions],
            excluded=[
                ExcludedHoldingRead(key=key, reason=text) for key, text in sorted(excluded.items())
            ],
        )

    pace = contribution_pace(_contribution_events(block), reference)
    contributions = (
        ContributionPaceRead(
            year=pace.year,
            total_year=pace.total_year,
            months=[MonthAmountRead(**m.__dict__) for m in pace.months],
            remaining_months=pace.remaining_months,
            projections=[PaceProjectionRead(**p.__dict__) for p in pace.projections],
        )
        if pace
        else None
    )

    alerts: list[str] = []
    if block.market_data_unavailable_reason:
        alerts.append(block.market_data_unavailable_reason)
    stale_limit = reference - timedelta(days=STALE_QUOTE_DAYS)
    for position in open_positions:
        if position.market_price_date is not None and position.market_price_date < stale_limit:
            alerts.append(
                f"cotação de {position.asset_ticker} é de "
                f"{position.market_price_date.strftime('%d/%m/%Y')}"
            )

    return CurrencyAnalytics(
        currency_code=currency,
        market_value=block.market_value,
        market_data_as_of=block.market_data_as_of,
        concentration=concentration_read,
        scenarios=scenarios,
        scenarios_unavailable_reason=reason,
        contributions=contributions,
        alerts=sorted(set(alerts)),
    )


def get_portfolio_analytics(
    db: Session,
    user_id: UUID,
    portfolio_id: UUID | None = None,
    *,
    reference_date: date | None = None,
    until: date | None = None,
) -> PortfolioAnalytics:
    reference = reference_date or date.today()
    until = until or date(reference.year, 12, 31)
    summary = get_dashboard_summary(db, user_id, portfolio_id, reference)

    asset_ids = sorted({p.asset_id for p in summary.positions}, key=str)
    assets = {asset_id: db.get(Asset, asset_id) for asset_id in asset_ids}
    class_labels = {c.code: c.label for c in db.execute(select(AssetClass)).scalars()}
    account_names = {
        a.id: a.name
        for a in db.execute(select(Account).where(Account.user_id == user_id)).scalars()
    }
    history = _history(db, asset_ids, reference)

    blocks = [
        _block_analytics(
            db,
            block,
            summary.positions,
            assets,
            class_labels,
            account_names,
            history,
            reference,
            until,
        )
        for block in summary.totals_by_currency
    ]
    return PortfolioAnalytics(
        reference_date=reference,
        quotes_refreshed_at=market_data_service.last_refresh(db, asset_ids),
        blocks=blocks,
    )
