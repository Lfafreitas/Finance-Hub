"""Mês a mês e "onde dá para melhorar" (Visual-1). Os números saem do
mesmo motor do resumo; as regras de melhoria, de
`cashflow_engine.insights`.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.cashflow_engine import CashflowSummaryCalculator, parse_description
from app.domain.cashflow_engine.insights import SMALL_LIMIT, SpendFact, spending_insights
from app.models.enums import CashflowNature
from app.repositories import cashflow as cashflow_repo
from app.schemas.cashflow_insights import (
    CategoryChangeRead,
    CategoryShareRead,
    CurrencyMonthlyFlows,
    CurrencySpendingInsights,
    MonthFlow,
    MonthlyFlows,
    RecurringItemRead,
    SpendingInsightsRead,
)
from app.services import cashflow_classification_service as classification
from app.services import cashflow_service
from app.services.exceptions import InvalidCashflowPeriodError

MAX_MONTHS = 24
_ZERO = Decimal("0.0000")


def parse_month(value: str | None, today: date | None = None) -> tuple[int, int]:
    if value is None:
        today = today or date.today()
        return today.year, today.month
    try:
        year_text, month_text = value.split("-")
        year, month = int(year_text), int(month_text)
    except ValueError as exc:
        raise InvalidCashflowPeriodError("mês no formato AAAA-MM") from exc
    if not (1 <= month <= 12) or year < 1900:
        raise InvalidCashflowPeriodError("mês no formato AAAA-MM")
    return year, month


def _shift(year: int, month: int, back: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) - back
    return index // 12, index % 12 + 1


def _bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def get_monthly_flows(
    db: Session, user_id: UUID, end_month: str | None = None, months: int = 6
) -> MonthlyFlows:
    if not 1 <= months <= MAX_MONTHS:
        raise InvalidCashflowPeriodError(f"de 1 a {MAX_MONTHS} meses")
    year, month = parse_month(end_month)
    periods = [_shift(year, month, back) for back in range(months - 1, -1, -1)]
    _, last_day = _bounds(year, month)
    _accounts, facts = cashflow_service._load_facts(db, user_id, until=last_day)

    by_currency: dict[str, dict[str, MonthFlow]] = {}
    for y, m in periods:
        start, end = _bounds(y, m)
        for currency, summary in CashflowSummaryCalculator.calculate(facts, start, end).items():
            by_currency.setdefault(currency, {})[f"{y}-{m:02d}"] = MonthFlow(
                month=f"{y}-{m:02d}",
                income=summary.income,
                expenses=summary.expenses,
                surplus=summary.income - summary.expenses,
                net_invested=summary.net_invested,
                unclassified_net=summary.unclassified_net,
                entry_count=summary.entry_count,
            )
    empty = {
        "income": _ZERO,
        "expenses": _ZERO,
        "surplus": _ZERO,
        "net_invested": _ZERO,
        "unclassified_net": _ZERO,
        "entry_count": 0,
    }
    return MonthlyFlows(
        end_month=f"{year}-{month:02d}",
        months=months,
        totals_by_currency=[
            CurrencyMonthlyFlows(
                currency_code=currency,
                months=[
                    by_currency[currency].get(f"{y}-{m:02d}")
                    or MonthFlow(month=f"{y}-{m:02d}", **empty)
                    for y, m in periods
                ],
            )
            for currency in sorted(by_currency)
        ],
    )


def get_spending_insights(
    db: Session, user_id: UUID, month: str | None = None
) -> SpendingInsightsRead:
    year, month_number = parse_month(month)
    first_year, first_month = _shift(year, month_number, 3)
    start, _ = _bounds(first_year, first_month)
    _, end = _bounds(year, month_number)

    accounts = cashflow_repo.list_cash_accounts(db, user_id)
    categories = {c.id: c for c in classification.list_categories(db, user_id)}

    def root(category_id):
        category = categories.get(category_id)
        while category is not None and category.parent_id is not None:
            category = categories.get(category.parent_id)
        return category

    facts: dict[str, list[SpendFact]] = {}
    for entry in cashflow_repo.list_active_entries(db, [a.id for a in accounts], until=end):
        if entry.entry_date < start:
            continue
        if entry.nature not in (CashflowNature.EXPENSE, CashflowNature.UNCLASSIFIED):
            continue
        top = root(entry.category_id) if entry.category_id else None
        facts.setdefault(entry.currency_code, []).append(
            SpendFact(
                entry_date=entry.entry_date,
                amount=entry.amount,
                expense=entry.nature is CashflowNature.EXPENSE,
                category_key=str(top.id) if top else None,
                category_label=top.name if top else None,
                match_text=parse_description(entry.description).match_text,
            )
        )

    blocks: list[CurrencySpendingInsights] = []
    for currency in sorted(facts):
        result = spending_insights(facts[currency], year, month_number)
        blocks.append(
            CurrencySpendingInsights(
                currency_code=currency,
                month=result.month,
                expenses=result.expenses,
                history_months=result.history_months,
                above_normal=[CategoryChangeRead(**c.__dict__) for c in result.above_normal],
                recurring=[RecurringItemRead(**r.__dict__) for r in result.recurring],
                recurring_total=result.recurring_total,
                small_count=result.small_count,
                small_total=result.small_total,
                small_limit=SMALL_LIMIT,
                top_categories=[CategoryShareRead(**c.__dict__) for c in result.top_categories],
                top_share=result.top_share,
                unclassified_outflow=result.unclassified_outflow,
                unclassified_share=result.unclassified_share,
            )
        )
    return SpendingInsightsRead(month=f"{year}-{month_number:02d}", totals_by_currency=blocks)
