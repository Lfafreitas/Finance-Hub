"""Saúde financeira: cobertura da reserva em meses de gasto e taxa de
poupança, por moeda, com os últimos meses fechados do controle financeiro.
Só totais: nenhuma descrição de lançamento sai daqui.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.analytics.financial_health import WINDOW, financial_health
from app.schemas.performance import FinancialHealthIndex, FinancialHealthRead
from app.services import overview_service
from app.services.cashflow_insights_service import get_monthly_flows


def _previous_month(today: date) -> str:
    year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return f"{year}-{month:02d}"


def get_financial_health(
    db: Session, user_id: UUID, *, today: date | None = None
) -> FinancialHealthIndex:
    today = today or date.today()
    # Uma folga de meses: mês sem lançamento não entra na média.
    flows = get_monthly_flows(db, user_id, end_month=_previous_month(today), months=WINDOW + 3)
    months_by_currency = {c.currency_code: c.months for c in flows.totals_by_currency}
    reserve_by_currency = {
        c.currency_code: c.reserve
        for c in overview_service.get_overview(db, user_id, as_of=today).totals_by_currency
    }
    currencies = []
    for currency in sorted(set(months_by_currency) | set(reserve_by_currency)):
        health = financial_health(
            months_by_currency.get(currency, []), reserve_by_currency.get(currency, Decimal(0))
        )
        if not health.months and health.reserve <= 0:
            continue
        currencies.append(
            FinancialHealthRead(
                currency_code=currency,
                months=health.months,
                avg_income=health.avg_income,
                avg_expenses=health.avg_expenses,
                avg_invested=health.avg_invested,
                savings_rate=health.savings_rate,
                reserve=health.reserve,
                coverage_months=health.coverage_months,
                complete=health.complete,
                incomplete_months=health.incomplete_months,
            )
        )
    return FinancialHealthIndex(as_of=today, currencies=currencies)
