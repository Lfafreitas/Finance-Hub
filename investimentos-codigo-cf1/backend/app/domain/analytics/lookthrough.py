"""Empresas "por trás" dos ETFs: quanto da carteira de uma moeda está em
cada empresa, somando o que vem pelos fundos (pela composição publicada
pela gestora) e o que é ação comprada direto.

Exposição de uma empresa = Σ (peso do fundo na carteira × peso da empresa
no fundo) + peso da ação direta. Ex.: QQQ é 42% da carteira e NVIDIA é 9%
do QQQ → 3,8% da carteira está em NVIDIA só pelo QQQ.

A composição cobre só as maiores posições de cada fundo (`coverage`), por
isso o resultado é um piso: a exposição real a cada empresa listada é pelo
menos isso. Fundo sem composição fica em `missing`, nunca é estimado.

Puro: recebe pesos e composições, não lê banco nem arquivo.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

FUND_CLASSES = frozenset({"ETF_US", "ETF_BR", "REIT", "FII"})
DIRECT_CLASSES = frozenset({"STOCK_US", "STOCK_BR", "BDR"})
TOP_COMPANIES = 12
_ZERO = Decimal(0)


@dataclass(frozen=True)
class Holding:
    """Uma posição da carteira numa moeda: peso em 0..1."""

    ticker: str
    asset_class: str
    weight: Decimal


@dataclass(frozen=True)
class Constituent:
    name: str
    ticker: str | None
    weight: Decimal  # fração do fundo


@dataclass(frozen=True)
class Composition:
    fund: str
    as_of: date
    source: str
    constituents: tuple[Constituent, ...]


@dataclass(frozen=True)
class Via:
    ticker: str  # o fundo, ou a própria ação quando comprada direto
    weight: Decimal  # fração da carteira que chega à empresa por aqui


@dataclass
class CompanyExposure:
    name: str
    ticker: str | None
    weight: Decimal = _ZERO
    via: list[Via] = field(default_factory=list)


@dataclass(frozen=True)
class FundCoverage:
    ticker: str
    weight: Decimal  # peso do fundo na carteira
    coverage: Decimal  # fração do fundo explicada pelas posições listadas
    as_of: date
    source: str


@dataclass(frozen=True)
class LookThrough:
    companies: list[CompanyExposure]
    funds: list[FundCoverage]
    missing: list[str]
    explained: Decimal  # fração da carteira que as empresas listadas explicam


def _key(ticker: str | None, name: str) -> str:
    return (ticker or name).strip().upper()


def look_through(
    holdings: Iterable[Holding],
    compositions: Iterable[Composition],
    top: int = TOP_COMPANIES,
) -> LookThrough:
    by_fund = {c.fund.strip().upper(): c for c in compositions}
    companies: dict[str, CompanyExposure] = {}
    funds: list[FundCoverage] = []
    missing: list[str] = []

    def add(key: str, name: str, ticker: str | None, via: str, weight: Decimal) -> None:
        item = companies.setdefault(key, CompanyExposure(name=name, ticker=ticker))
        item.weight += weight
        item.via.append(Via(ticker=via, weight=weight))

    for h in holdings:
        if h.weight <= 0:
            continue
        ticker = h.ticker.strip().upper()
        if h.asset_class in DIRECT_CLASSES:
            add(ticker, h.ticker, h.ticker, h.ticker, h.weight)
            continue
        composition = by_fund.get(ticker)
        if composition is None:
            if h.asset_class in FUND_CLASSES:
                missing.append(h.ticker)
            continue
        coverage = sum((c.weight for c in composition.constituents), start=_ZERO)
        funds.append(
            FundCoverage(
                ticker=h.ticker,
                weight=h.weight,
                coverage=coverage,
                as_of=composition.as_of,
                source=composition.source,
            )
        )
        for c in composition.constituents:
            add(_key(c.ticker, c.name), c.name, c.ticker, h.ticker, h.weight * c.weight)

    ranked = sorted(companies.values(), key=lambda c: (-c.weight, c.name))
    for item in ranked:
        item.via.sort(key=lambda v: (-v.weight, v.ticker))
    shown = ranked[:top]
    return LookThrough(
        companies=shown,
        funds=sorted(funds, key=lambda f: (-f.weight, f.ticker)),
        missing=sorted(missing),
        explained=sum((c.weight for c in shown), start=_ZERO),
    )
