"""Indicadores da carteira e de cada ativo (KPIs-1).

Funções puras: recebem posições, cotações e proventos já lidos e
devolvem números. Nenhuma regra de posição é reescrita aqui — custo,
valor e resultado de cada ativo chegam prontos do dashboard.

Moedas nunca se somam: cada bloco é de uma moeda.

Desempenho de PREÇO (sem proventos): o histórico gravado é o fechamento
diário da fonte pública, não ajustado por dividendos. Por isso retorno
de período, volatilidade e queda máxima medem só o preço — e a tela diz
isso.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

_ZERO = Decimal(0)
_Q4 = Decimal("0.0001")
TRADING_DAYS = 252
MIN_RETURNS_FOR_RISK = 20  # menos que isto, volatilidade e queda não dizem nada


def _q(value: Decimal) -> Decimal:
    return value.quantize(_Q4, rounding=ROUND_HALF_UP)


def _qf(value: float) -> Decimal:
    return _q(Decimal(str(value)))


@dataclass(frozen=True)
class Bar:
    day: date
    close: Decimal


@dataclass(frozen=True)
class PriceStats:
    """Desempenho de preço até `as_of`. Cada campo é None quando o
    histórico não cobre o período (nunca um número de período menor).
    """

    last_price: Decimal | None = None
    last_date: date | None = None
    return_1m: Decimal | None = None
    return_3m: Decimal | None = None
    return_ytd: Decimal | None = None
    return_1y: Decimal | None = None
    volatility_1y: Decimal | None = None
    max_drawdown_1y: Decimal | None = None
    low_52w: Decimal | None = None
    high_52w: Decimal | None = None
    position_52w: Decimal | None = None
    from_high: Decimal | None = None


def _close_on_or_before(bars: list[Bar], day: date) -> Bar | None:
    found = None
    for bar in bars:
        if bar.day > day:
            break
        found = bar
    return found


def _period_return(bars: list[Bar], last: Bar, start: date) -> Decimal | None:
    """Retorno de `start` até o último preço. Exige um fechamento em
    `start` ou antes dele — sem isso, o período não está coberto.
    """
    base = _close_on_or_before(bars, start)
    if base is None or base.close <= 0:
        return None
    return _q(last.close / base.close - 1)


def price_stats(bars: list[Bar], as_of: date) -> PriceStats:
    """`bars` em ordem crescente, um fechamento por dia."""
    usable = [b for b in bars if b.day <= as_of and b.close > 0]
    if not usable:
        return PriceStats()
    last = usable[-1]
    year_ago = last.day - timedelta(days=365)
    window = [b for b in usable if b.day > year_ago]
    covers_year = usable[0].day <= year_ago

    volatility = drawdown = None
    returns = [math.log(float(b.close) / float(a.close)) for a, b in itertools.pairwise(window)]
    if len(returns) >= MIN_RETURNS_FOR_RISK:
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        volatility = _qf(math.sqrt(variance) * math.sqrt(TRADING_DAYS))
        peak = window[0].close
        worst = _ZERO
        for bar in window:
            peak = max(peak, bar.close)
            worst = min(worst, bar.close / peak - 1)
        drawdown = _q(worst)

    low = high = position = from_high = None
    if covers_year:
        low = min(b.close for b in window)
        high = max(b.close for b in window)
        if high > low:
            position = _q((last.close - low) / (high - low))
        from_high = _q(last.close / high - 1)

    return PriceStats(
        last_price=last.close,
        last_date=last.day,
        return_1m=_period_return(usable, last, last.day - timedelta(days=30)),
        return_3m=_period_return(usable, last, last.day - timedelta(days=91)),
        return_ytd=_period_return(usable, last, date(last.day.year - 1, 12, 31)),
        return_1y=_period_return(usable, last, year_ago),
        volatility_1y=volatility,
        max_drawdown_1y=drawdown,
        low_52w=low,
        high_52w=high,
        position_52w=position,
        from_high=from_high,
    )


@dataclass(frozen=True)
class Holding:
    """Um ativo numa moeda, já somado entre contas."""

    ticker: str
    name: str
    asset_class: str
    asset_class_label: str
    currency_code: str
    quantity: Decimal
    cost: Decimal
    value: Decimal | None  # None = sem cotação
    dividends: Decimal = _ZERO
    day_change_pct: Decimal | None = None
    bars: list[Bar] = field(default_factory=list)
    exchange_traded: bool = False


@dataclass(frozen=True)
class AssetKpis:
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
    stats: PriceStats
    # Resultado com proventos: (resultado + proventos recebidos) / custo.
    total_return_pct: Decimal | None = None


@dataclass(frozen=True)
class GroupWeight:
    asset_class: str
    label: str
    value: Decimal
    weight: Decimal


@dataclass(frozen=True)
class BasketStats:
    """A carteira de HOJE (pesos atuais) nos últimos 12 meses, só com os
    ativos de bolsa que têm o ano inteiro de histórico.
    """

    tickers: tuple[str, ...]
    share_of_portfolio: Decimal
    return_1y: Decimal
    volatility_1y: Decimal
    max_drawdown_1y: Decimal


@dataclass(frozen=True)
class PortfolioKpis:
    currency_code: str
    value: Decimal
    cost: Decimal
    pnl: Decimal
    return_pct: Decimal | None
    complete: bool
    unpriced: tuple[str, ...]
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
    groups: list[GroupWeight]
    basket: BasketStats | None
    assets: list[AssetKpis]
    # Resultado com proventos da carteira (só com todas as cotações).
    total_return_pct: Decimal | None = None


def _basket(
    assets: list[tuple[Holding, Decimal]], total: Decimal, as_of: date
) -> BasketStats | None:
    """Série diária da cesta com os pesos de hoje (rebalanceada todo
    dia — é uma simulação da composição atual, não o que aconteceu).
    """
    candidates = []
    for holding, value in assets:
        if not holding.exchange_traded or value <= 0:
            continue
        bars = [b for b in holding.bars if b.day <= as_of and b.close > 0]
        if not bars or bars[0].day > as_of - timedelta(days=365):
            continue
        candidates.append((holding, value, {b.day: b.close for b in bars}))
    if not candidates or total <= 0:
        return None
    covered = sum((v for _h, v, _p in candidates), start=_ZERO)
    start = as_of - timedelta(days=365)
    days = sorted(
        set.intersection(*({d for d in prices if d >= start} for _h, _v, prices in candidates))
    )
    if len(days) < MIN_RETURNS_FOR_RISK + 1:
        return None
    weights = [float(v / covered) for _h, v, _p in candidates]
    daily = []
    for a, b in itertools.pairwise(days):
        daily.append(
            sum(
                w * (float(prices[b]) / float(prices[a]) - 1)
                for w, (_h, _v, prices) in zip(weights, candidates, strict=True)
            )
        )
    level, peak, worst = 1.0, 1.0, 0.0
    for r in daily:
        level *= 1 + r
        peak = max(peak, level)
        worst = min(worst, level / peak - 1)
    mean = sum(daily) / len(daily)
    variance = sum((r - mean) ** 2 for r in daily) / (len(daily) - 1)
    return BasketStats(
        tickers=tuple(sorted(h.ticker for h, _v, _p in candidates)),
        share_of_portfolio=_q(covered / total),
        return_1y=_qf(level - 1),
        volatility_1y=_qf(math.sqrt(variance) * math.sqrt(TRADING_DAYS)),
        max_drawdown_1y=_qf(worst),
    )


def portfolio_kpis(holdings: list[Holding], as_of: date) -> PortfolioKpis | None:
    """Indicadores de UMA moeda. Peso pelo valor de mercado; ativo sem
    cotação entra pelo custo e é nomeado em `unpriced` (mesma estimativa
    declarada do patrimônio).
    """
    holdings = [h for h in holdings if h.quantity > 0]
    if not holdings:
        return None
    currency = holdings[0].currency_code
    if any(h.currency_code != currency for h in holdings):
        raise ValueError("moedas diferentes não se somam")

    valued = [(h, h.value if h.value is not None else h.cost) for h in holdings]
    total = sum((v for _h, v in valued), start=_ZERO)
    cost = sum((h.cost for h in holdings), start=_ZERO)
    priced = [h for h in holdings if h.value is not None]
    pnl = sum((h.value - h.cost for h in priced), start=_ZERO)
    unpriced = tuple(sorted(h.ticker for h in holdings if h.value is None))

    assets: list[AssetKpis] = []
    for holding, value in valued:
        own_pnl = holding.value - holding.cost if holding.value is not None else None
        assets.append(
            AssetKpis(
                ticker=holding.ticker,
                name=holding.name,
                asset_class=holding.asset_class,
                asset_class_label=holding.asset_class_label,
                quantity=holding.quantity,
                cost=holding.cost,
                value=holding.value,
                weight=_q(value / total) if total > 0 else None,
                pnl=own_pnl,
                return_pct=(
                    _q(own_pnl / holding.cost) if own_pnl is not None and holding.cost > 0 else None
                ),
                # Pontos percentuais do resultado da carteira que vieram deste ativo.
                contribution=_q(own_pnl / cost) if own_pnl is not None and cost > 0 else None,
                dividends=holding.dividends,
                yield_on_cost=_q(holding.dividends / holding.cost) if holding.cost > 0 else None,
                day_change_pct=holding.day_change_pct,
                stats=price_stats(holding.bars, as_of),
                total_return_pct=(
                    _q((own_pnl + holding.dividends) / holding.cost)
                    if own_pnl is not None and holding.cost > 0
                    else None
                ),
            )
        )
    assets.sort(key=lambda a: (-(a.weight or _ZERO), a.ticker))

    weights = [a.weight for a in assets if a.weight is not None]
    hhi = sum((w * w for w in weights), start=_ZERO)
    with_return = [a for a in assets if a.return_pct is not None]
    best = max(with_return, key=lambda a: a.return_pct, default=None)
    worst = min(with_return, key=lambda a: a.return_pct, default=None)

    groups: dict[str, tuple[str, Decimal]] = {}
    for holding, value in valued:
        label, acc = groups.get(holding.asset_class, (holding.asset_class_label, _ZERO))
        groups[holding.asset_class] = (label, acc + value)
    dividends = sum((h.dividends for h in holdings), start=_ZERO)

    return PortfolioKpis(
        currency_code=currency,
        value=total,
        cost=cost,
        pnl=pnl,
        return_pct=_q(pnl / cost) if cost > 0 and not unpriced else None,
        complete=not unpriced,
        unpriced=unpriced,
        top_ticker=assets[0].ticker if assets else None,
        top_weight=assets[0].weight if assets else None,
        top3_weight=_q(sum(weights[:3], start=_ZERO)) if weights else None,
        # "Número efetivo de ativos" (1/HHI): quantos ativos de peso igual
        # dariam a mesma concentração.
        effective_assets=_q(1 / hhi) if hhi > 0 else None,
        positive=sum(1 for a in assets if a.pnl is not None and a.pnl > 0),
        negative=sum(1 for a in assets if a.pnl is not None and a.pnl < 0),
        best=best.ticker if best and len(with_return) > 1 else None,
        worst=worst.ticker if worst and len(with_return) > 1 else None,
        dividends=dividends,
        yield_on_cost=_q(dividends / cost) if cost > 0 else None,
        groups=sorted(
            (
                GroupWeight(code, label, value, _q(value / total) if total > 0 else _ZERO)
                for code, (label, value) in groups.items()
            ),
            key=lambda g: (-g.value, g.asset_class),
        ),
        basket=_basket(valued, total, as_of),
        assets=assets,
        total_return_pct=(_q((pnl + dividends) / cost) if cost > 0 and not unpriced else None),
    )
