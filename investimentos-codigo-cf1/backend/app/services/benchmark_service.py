"""Comparação da carteira com uma referência na mesma moeda.

Dólar → SPY (fechamentos já gravados pela busca de cotações).
Reais → CDI (taxa diária do Banco Central, gravada em `benchmark_rates`).
Outras moedas não têm referência.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domain.analytics.benchmark import (
    Flow,
    Level,
    MissingLevel,
    cdi_levels,
    flows_from_facts,
    simulate,
)
from app.domain.analytics.history import portfolio_history
from app.models.asset import Asset
from app.models.benchmark_rate import BenchmarkRate
from app.repositories.prices import list_price_series
from app.schemas.performance import BenchmarkComparison, BenchmarkPoint, BenchmarksRead
from app.services.market_data.bcb import RateProvider
from app.services.market_data.yahoo import MarketDataError
from app.services.performance_service import _holdings

CDI = "CDI"
_REFERENCES = {"USD": ("SPY", "SPY (S&P 500)"), "BRL": (CDI, "CDI")}
MAX_POINTS = 180
_Q4 = Decimal("0.0001")


def _spy_levels(db: Session, today: date) -> list[Level]:
    spy = db.execute(
        select(Asset).where(Asset.ticker == "SPY", Asset.currency_code == "USD")
    ).scalar_one_or_none()
    if spy is None:
        return []
    series = list_price_series(db, [spy.id], today).get(spy.id, [])
    return [Level(p.price_date, p.price) for p in series if p.currency_code == "USD"]


def _cdi_levels(db: Session) -> list[Level]:
    rows = db.execute(
        select(BenchmarkRate.rate_date, BenchmarkRate.daily_rate)
        .where(BenchmarkRate.code == CDI)
        .order_by(BenchmarkRate.rate_date)
    ).all()
    return cdi_levels([(r[0], r[1]) for r in rows])


def _thin(points: list[BenchmarkPoint]) -> list[BenchmarkPoint]:
    """No máximo MAX_POINTS pontos, sempre com o primeiro e o último."""
    if len(points) <= MAX_POINTS:
        return points
    step = len(points) / (MAX_POINTS - 1)
    picked = [points[round(i * step)] for i in range(MAX_POINTS - 1)]
    return [*picked, points[-1]]


def _ratio(value: Decimal, base: Decimal) -> Decimal | None:
    if base <= 0:
        return None
    return (value / base - 1).quantize(_Q4, rounding=ROUND_HALF_UP)


def get_benchmarks(db: Session, user_id: UUID, *, today: date | None = None) -> BenchmarksRead:
    today = today or date.today()
    holdings = _holdings(db, user_id, today)
    by_currency: dict[str, list] = {}
    for h in holdings:
        by_currency.setdefault(h.currency_code, []).append(h)

    comparisons = []
    for currency in sorted(by_currency, key=lambda c: (c != "BRL", c != "USD", c)):
        if currency not in _REFERENCES:
            continue
        code, label = _REFERENCES[currency]
        group = by_currency[currency]
        flows: list[Flow] = flows_from_facts([f for h in group for f in h.facts])
        if not flows:
            continue
        base = BenchmarkComparison(
            currency_code=currency, benchmark=code, benchmark_label=label, available=False
        )
        levels = _spy_levels(db, today) if code == "SPY" else _cdi_levels(db)
        start = flows[0].day
        days = [start + timedelta(days=i) for i in range((today - start).days + 1)]
        try:
            sim = simulate(flows, levels, days)
        except MissingLevel:
            reason = (
                "Sem cotações do SPY desde o primeiro aporte — use “Atualizar agora” nas cotações."
                if code == "SPY"
                else "CDI ainda não baixado desde o primeiro aporte — use “Atualizar agora” nas cotações."
            )
            comparisons.append(base.model_copy(update={"reason": reason}))
            continue

        history = portfolio_history(group, [], days)[currency]
        points = [
            BenchmarkPoint(date=p.day, portfolio=p.investments_value, benchmark=value)
            for p, (_day, value) in zip(history, sim.values, strict=True)
        ]
        last = points[-1]
        comparisons.append(
            base.model_copy(
                update={
                    "available": True,
                    "net_invested": sim.net_invested,
                    "portfolio_value": last.portfolio,
                    "benchmark_value": last.benchmark,
                    "difference": last.portfolio - last.benchmark,
                    "portfolio_return": _ratio(last.portfolio, sim.net_invested),
                    "benchmark_return": _ratio(last.benchmark, sim.net_invested),
                    "unpriced": list(history[-1].unpriced),
                    "points": _thin(points),
                }
            )
        )
    return BenchmarksRead(as_of=today, comparisons=comparisons)


def refresh_cdi(
    db: Session, user_id: UUID, provider: RateProvider, *, today: date | None = None
) -> int:
    """Baixa o CDI que falta desde o primeiro aporte em reais (ou dos
    últimos 400 dias). Sem investimento em reais, não pede nada.
    Devolve quantos dias foram gravados.
    """
    today = today or date.today()
    brl = [h for h in _holdings(db, user_id, today) if h.currency_code == "BRL"]
    flows = flows_from_facts([f for h in brl for f in h.facts])
    if not flows:
        return 0
    start = min(flows[0].day, today - timedelta(days=400)) - timedelta(days=7)
    last = db.execute(
        select(func.max(BenchmarkRate.rate_date)).where(BenchmarkRate.code == CDI)
    ).scalar_one()
    first = db.execute(
        select(func.min(BenchmarkRate.rate_date)).where(BenchmarkRate.code == CDI)
    ).scalar_one()
    # Já tem desde o início (com folga de fim de semana/feriado): só o que falta.
    if last is not None and first is not None and first <= start + timedelta(days=7):
        start = last + timedelta(days=1)
    if start > today:
        return 0
    # Só fim de semana faltando: o CDI não é publicado em sábado/domingo.
    if all((start + timedelta(days=i)).weekday() >= 5 for i in range((today - start).days + 1)):
        return 0
    rates = [r for r in provider.fetch(start, today) if r[0] <= today]
    if not rates:
        return 0
    stmt = insert(BenchmarkRate).values(
        [{"code": CDI, "rate_date": d, "daily_rate": r} for d, r in rates]
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["code", "rate_date"], set_={"daily_rate": stmt.excluded.daily_rate}
    )
    db.execute(stmt)
    db.flush()
    return len(rates)


__all__ = ["MarketDataError", "get_benchmarks", "refresh_cdi"]
