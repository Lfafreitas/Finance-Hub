"""Empresas por trás dos ETFs: pesos da carteira (KPIs do app) × composição
dos fundos publicada pela gestora (trazida pela análise diária v3).

As composições vêm da análise MAIS RECENTE que tiver alguma; os pesos são
os de hoje. Cada moeda à parte.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.analytics.lookthrough import Composition, Constituent, Holding, look_through
from app.schemas.insights import (
    CompanyExposureRead,
    CurrencyLookThrough,
    FundCoverageRead,
    InsightReport,
    LookThroughRead,
    ViaRead,
)
from app.services import insights_service
from app.services.performance_service import get_kpis


def _compositions(report: InsightReport) -> list[Composition]:
    return [
        Composition(
            fund=c.etf,
            as_of=c.as_of,
            source=c.source,
            constituents=tuple(
                Constituent(name=h.name, ticker=h.ticker, weight=Decimal(str(h.weight)))
                for h in c.top
            ),
        )
        for c in report.etf_holdings
    ]


def _latest_with_compositions() -> tuple[date | None, list[Composition]]:
    index = insights_service.list_reports()
    for item in index.history:  # mais nova primeiro
        if index.latest is not None and item.report_date == index.latest.report_date:
            report = index.latest.report
        else:
            try:
                report = insights_service.get_report(item.report_date).report
            except (
                insights_service.InsightReportNotFoundError,
                OSError,
            ):  # sumiu ou ficou inválido no meio
                continue
        if report.etf_holdings:
            return item.report_date, _compositions(report)
    return None, []


def get_look_through(db: Session, user_id: UUID, *, today: date | None = None) -> LookThroughRead:
    report_date, compositions = _latest_with_compositions()
    kpis = get_kpis(db, user_id, today=today)
    currencies = []
    for block in kpis.totals_by_currency:
        holdings = [
            Holding(ticker=a.ticker, asset_class=a.asset_class, weight=a.weight)
            for a in block.assets
            if a.weight is not None
        ]
        result = look_through(holdings, compositions)
        if not result.companies and not result.missing:
            continue
        currencies.append(
            CurrencyLookThrough(
                currency_code=block.currency_code,
                companies=[
                    CompanyExposureRead(
                        name=c.name,
                        ticker=c.ticker,
                        weight=c.weight,
                        via=[ViaRead(ticker=v.ticker, weight=v.weight) for v in c.via],
                    )
                    for c in result.companies
                ],
                funds=[
                    FundCoverageRead(
                        ticker=f.ticker,
                        weight=f.weight,
                        coverage=f.coverage,
                        as_of=f.as_of,
                        source=f.source,
                    )
                    for f in result.funds
                ],
                missing=result.missing,
                explained=result.explained,
            )
        )
    return LookThroughRead(report_date=report_date, currencies=currencies)
