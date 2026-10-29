"""Cenários de mercado até uma data (Análises-1).

Modelo: cada ativo segue um passeio aleatório com volatilidade anual e
retorno esperado anual; a carteira é aproximada por um único ativo com
a volatilidade que sai da matriz de covariância (pesos pelo valor de
hoje). O retorno no horizonte T segue uma lognormal:

    r(z) = exp((μ − σ²/2)·T + z·σ·√T) − 1

- pessimista: z = −1,2816 (só 10% dos casos terminam abaixo);
- realista: z = 0 (a mediana);
- otimista: z = +1,2816 (só 10% dos casos terminam acima).

É uma régua de incerteza, não uma previsão: o retorno esperado é uma
premissa de longo prazo, declarada na resposta. A volatilidade e a
correlação vêm do histórico real de preços quando há pelo menos
`MIN_RETURNS` retornos diários; senão, de um valor padrão por grupo —
e a resposta diz qual dos dois foi usado.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise

Z_10 = 1.2815515655446004
TRADING_DAYS = 252
MIN_RETURNS = 60

EQUITY = "EQUITY"
REAL_ESTATE = "REAL_ESTATE"
CRYPTO = "CRYPTO"
FUND = "FUND"

_GROUP_OF_CLASS = {
    "STOCK_BR": EQUITY,
    "ETF_BR": EQUITY,
    "BDR": EQUITY,
    "STOCK_US": EQUITY,
    "ETF_US": EQUITY,
    "FII": REAL_ESTATE,
    "REIT": REAL_ESTATE,
    "CRYPTO": CRYPTO,
    "FUND": FUND,
}

# Volatilidade anual usada quando falta histórico.
DEFAULT_VOLATILITY = {EQUITY: 0.20, REAL_ESTATE: 0.20, CRYPTO: 0.60, FUND: 0.10}

# Retorno esperado anual (premissa de longo prazo, nominal, na moeda do
# ativo). Não sai do histórico recente: um ano bom não vira premissa.
EXPECTED_RETURN = {
    "USD": {EQUITY: 0.07, REAL_ESTATE: 0.06, CRYPTO: 0.07, FUND: 0.05},
    "BRL": {EQUITY: 0.10, REAL_ESTATE: 0.09, CRYPTO: 0.07, FUND: 0.09},
}
_FALLBACK_RETURN = {EQUITY: 0.07, REAL_ESTATE: 0.06, CRYPTO: 0.07, FUND: 0.05}

# Correlação usada quando falta histórico comum aos dois ativos.
_SAME_GROUP_CORRELATION = 0.85
_CROSS_GROUP_CORRELATION = {
    frozenset({EQUITY, REAL_ESTATE}): 0.70,
    frozenset({EQUITY, FUND}): 0.60,
    frozenset({REAL_ESTATE, FUND}): 0.50,
}
_DEFAULT_CROSS_CORRELATION = 0.30  # cripto com o resto

_RETURN_PLACES = Decimal("0.0001")
_MONEY_PLACES = Decimal("0.01")


def asset_group(asset_class_code: str) -> str | None:
    """Grupo de risco da classe; None = fora dos cenários (renda fixa)."""
    return _GROUP_OF_CLASS.get(asset_class_code)


@dataclass(frozen=True)
class Holding:
    key: str
    value: Decimal
    group: str
    currency_code: str
    # Fechamentos diários (data, preço), em qualquer ordem.
    history: tuple[tuple[date, Decimal], ...] = ()


@dataclass(frozen=True)
class HoldingAssumption:
    key: str
    weight: Decimal
    volatility: Decimal
    volatility_from_history: bool
    history_returns: int
    expected_return: Decimal


@dataclass(frozen=True)
class ScenarioResult:
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
    assumptions: tuple[HoldingAssumption, ...]


def _log_returns(history: tuple[tuple[date, Decimal], ...]) -> dict[date, float]:
    """Retorno logarítmico de cada data em relação ao fechamento anterior."""
    ordered = sorted((day, float(price)) for day, price in history if price > 0)
    returns: dict[date, float] = {}
    for (_, previous), (day, price) in pairwise(ordered):
        returns[day] = math.log(price / previous)
    return returns


def _stdev(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def historical_volatility(history: tuple[tuple[date, Decimal], ...]) -> tuple[float | None, int]:
    returns = list(_log_returns(history).values())
    if len(returns) < MIN_RETURNS:
        return None, len(returns)
    return _stdev(returns) * math.sqrt(TRADING_DAYS), len(returns)


def historical_correlation(
    a: tuple[tuple[date, Decimal], ...], b: tuple[tuple[date, Decimal], ...]
) -> float | None:
    """Correlação dos retornos diários nas datas comuns aos dois."""
    ra, rb = _log_returns(a), _log_returns(b)
    common = sorted(set(ra) & set(rb))
    if len(common) < MIN_RETURNS:
        return None
    xs, ys = [ra[d] for d in common], [rb[d] for d in common]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return max(-1.0, min(1.0, cov / math.sqrt(vx * vy)))


def default_correlation(group_a: str, group_b: str) -> float:
    if group_a == group_b:
        return _SAME_GROUP_CORRELATION
    return _CROSS_GROUP_CORRELATION.get(frozenset({group_a, group_b}), _DEFAULT_CROSS_CORRELATION)


def _normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _ret(value: float) -> Decimal:
    return Decimal(str(value)).quantize(_RETURN_PLACES, rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_PLACES, rounding=ROUND_HALF_UP)


def portfolio_scenarios(holdings: list[Holding], horizon_days: int) -> ScenarioResult | None:
    """Cenários da carteira em `horizon_days` dias corridos. None se
    não há valor a projetar ou o horizonte não é positivo.
    """
    holdings = [h for h in holdings if h.value > 0]
    total = sum((h.value for h in holdings), start=Decimal(0))
    if horizon_days <= 0 or total <= 0:
        return None

    weights = [float(h.value / total) for h in holdings]
    vols: list[float] = []
    assumptions: list[HoldingAssumption] = []
    mu = 0.0
    for holding, weight in zip(holdings, weights, strict=True):
        vol, count = historical_volatility(holding.history)
        from_history = vol is not None
        if vol is None:
            vol = DEFAULT_VOLATILITY[holding.group]
        expected = EXPECTED_RETURN.get(holding.currency_code, _FALLBACK_RETURN)[holding.group]
        vols.append(vol)
        mu += weight * expected
        assumptions.append(
            HoldingAssumption(
                key=holding.key,
                weight=_ret(weight),
                volatility=_ret(vol),
                volatility_from_history=from_history,
                history_returns=count,
                expected_return=_ret(expected),
            )
        )

    variance = 0.0
    for i, hi in enumerate(holdings):
        for j, hj in enumerate(holdings):
            if i == j:
                corr = 1.0
            else:
                measured = historical_correlation(hi.history, hj.history)
                corr = measured if measured is not None else default_correlation(hi.group, hj.group)
            variance += weights[i] * weights[j] * vols[i] * vols[j] * corr
    sigma = math.sqrt(max(variance, 0.0))

    years = horizon_days / 365
    drift = (mu - sigma**2 / 2) * years
    spread = sigma * math.sqrt(years)

    def scenario(z: float) -> float:
        return math.exp(drift + z * spread) - 1

    pessimistic, realistic, optimistic = scenario(-Z_10), scenario(0.0), scenario(Z_10)
    below = _normal_cdf(-drift / spread) if spread > 0 else (1.0 if drift < 0 else 0.0)
    return ScenarioResult(
        horizon_days=horizon_days,
        value_today=_money(total),
        expected_return=_ret(mu),
        volatility=_ret(sigma),
        pessimistic_return=_ret(pessimistic),
        realistic_return=_ret(realistic),
        optimistic_return=_ret(optimistic),
        pessimistic_value=_money(total * (1 + Decimal(str(pessimistic)))),
        realistic_value=_money(total * (1 + Decimal(str(realistic)))),
        optimistic_value=_money(total * (1 + Decimal(str(optimistic)))),
        probability_below_today=_ret(below),
        assumptions=tuple(assumptions),
    )
