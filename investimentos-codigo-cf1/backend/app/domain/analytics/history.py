"""Evolução do patrimônio e variação do último pregão (Painel-1).

Funções puras: recebem fatos e cotações já lidos e devolvem números.
Nenhuma regra de posição é reescrita aqui — quantidade e custo de cada
dia saem do `PositionCalculator`, aplicado às transações até aquele dia.

Moedas nunca se somam: cada série é de uma moeda.

Valor de um dia:
- posição com cotação (na moeda da posição) até aquele dia: quantidade ×
  último preço conhecido;
- posição sem cotação até aquele dia: entra pelo custo e o ticker vai em
  `unpriced` — a mesma estimativa declarada do patrimônio (Visual-1).
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.financial_engine import PositionCalculator, PositionResult, TransactionFact

_ZERO = Decimal(0)
_CENT4 = Decimal("0.0001")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_CENT4, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PricePoint:
    price_date: date
    price: Decimal
    currency_code: str


@dataclass(frozen=True)
class Holding:
    """Um par (conta, ativo). `facts` em ordem cronológica; `prices` em
    ordem crescente de data, uma por data (a precedência MANUAL > fonte
    automática já resolvida por quem leu).
    """

    ticker: str
    currency_code: str
    facts: list[TransactionFact]
    prices: list[PricePoint]
    exchange_traded: bool = False


@dataclass(frozen=True)
class CashMove:
    currency_code: str
    entry_date: date
    amount: Decimal


@dataclass(frozen=True)
class HistoryPoint:
    day: date
    investments_value: Decimal
    investments_cost: Decimal
    cash: Decimal
    total: Decimal
    unpriced: tuple[str, ...] = ()


@dataclass
class _HoldingCursor:
    holding: Holding
    fact_dates: list[date] = field(default_factory=list)
    price_dates: list[date] = field(default_factory=list)
    cache: dict[int, PositionResult] = field(default_factory=dict)

    def position(self, day: date) -> PositionResult | None:
        count = bisect_right(self.fact_dates, day)
        if count == 0:
            return None
        if count not in self.cache:
            self.cache[count] = PositionCalculator.calculate(self.holding.facts[:count])
        return self.cache[count]

    def price(self, day: date) -> Decimal | None:
        index = bisect_right(self.price_dates, day)
        if index == 0:
            return None
        point = self.holding.prices[index - 1]
        if point.currency_code != self.holding.currency_code:
            return None
        return point.price


def portfolio_history(
    holdings: list[Holding], cash_moves: list[CashMove], days: list[date]
) -> dict[str, list[HistoryPoint]]:
    """Uma série por moeda, um ponto por dia pedido."""
    cursors = [
        _HoldingCursor(
            holding=h,
            fact_dates=[f.transaction_date for f in h.facts],
            price_dates=[p.price_date for p in h.prices],
        )
        for h in holdings
    ]
    cash_by_currency: dict[str, list[CashMove]] = {}
    for move in sorted(cash_moves, key=lambda m: m.entry_date):
        cash_by_currency.setdefault(move.currency_code, []).append(move)
    currencies = sorted({h.currency_code for h in holdings} | set(cash_by_currency))

    series: dict[str, list[HistoryPoint]] = {c: [] for c in currencies}
    cash_index = {c: 0 for c in cash_by_currency}
    cash_total = {c: _ZERO for c in currencies}
    for day in sorted(days):
        for currency, moves in cash_by_currency.items():
            i = cash_index[currency]
            while i < len(moves) and moves[i].entry_date <= day:
                cash_total[currency] += moves[i].amount
                i += 1
            cash_index[currency] = i

        value = {c: _ZERO for c in currencies}
        cost = {c: _ZERO for c in currencies}
        unpriced: dict[str, list[str]] = {c: [] for c in currencies}
        for cursor in cursors:
            position = cursor.position(day)
            if position is None or position.quantity <= 0:
                continue
            currency = cursor.holding.currency_code
            position_cost = position.total_cost_basis
            cost[currency] += position_cost
            price = cursor.price(day)
            if price is None:
                value[currency] += position_cost
                unpriced[currency].append(cursor.holding.ticker)
            else:
                value[currency] += position.quantity * price

        for currency in currencies:
            invested = _q(value[currency])
            series[currency].append(
                HistoryPoint(
                    day=day,
                    investments_value=invested,
                    investments_cost=_q(cost[currency]),
                    cash=_q(cash_total[currency]),
                    total=_q(invested + cash_total[currency]),
                    unpriced=tuple(sorted(set(unpriced[currency]))),
                )
            )
    return series


@dataclass(frozen=True)
class AssetMove:
    ticker: str
    currency_code: str
    quantity: Decimal
    price: Decimal
    price_date: date
    previous_price: Decimal
    previous_date: date
    change_value: Decimal
    change_pct: Decimal


@dataclass(frozen=True)
class CurrencyMove:
    currency_code: str
    change_value: Decimal
    change_pct: Decimal | None
    last_date: date | None
    assets: list[AssetMove]


def last_session_moves(holdings: list[Holding], as_of: date) -> dict[str, CurrencyMove]:
    """Variação do último pregão de cada ativo negociado em bolsa: o
    último preço até `as_of` contra o preço da data anterior a ele.

    Renda fixa e ativos sem cotação diária ficam de fora — a "variação
    do dia" deles seria a distância entre duas cotações digitadas à mão,
    que pode ser de semanas.
    """
    # O mesmo ativo em duas contas vira uma linha só.
    merged: dict[tuple[str, str], AssetMove] = {}
    base: dict[str, Decimal] = {}
    for holding in holdings:
        if not holding.exchange_traded:
            continue
        cursor = _HoldingCursor(
            holding=holding,
            fact_dates=[f.transaction_date for f in holding.facts],
            price_dates=[p.price_date for p in holding.prices],
        )
        position = cursor.position(as_of)
        if position is None or position.quantity <= 0:
            continue
        usable = [
            p
            for p in holding.prices
            if p.price_date <= as_of and p.currency_code == holding.currency_code
        ]
        if len(usable) < 2:
            continue
        last, previous = usable[-1], usable[-2]
        key = (holding.currency_code, holding.ticker)
        quantity = position.quantity + (merged[key].quantity if key in merged else _ZERO)
        merged[key] = AssetMove(
            ticker=holding.ticker,
            currency_code=holding.currency_code,
            quantity=quantity,
            price=last.price,
            price_date=last.price_date,
            previous_price=previous.price,
            previous_date=previous.price_date,
            change_value=_q(quantity * (last.price - previous.price)),
            change_pct=_q(last.price / previous.price - 1),
        )
        base[holding.currency_code] = (
            base.get(holding.currency_code, _ZERO) + position.quantity * previous.price
        )

    by_currency: dict[str, list[AssetMove]] = {}
    for (currency, _ticker), move in merged.items():
        by_currency.setdefault(currency, []).append(move)

    result: dict[str, CurrencyMove] = {}
    for currency, moves in by_currency.items():
        total = sum((m.change_value for m in moves), start=_ZERO)
        reference = base[currency]
        result[currency] = CurrencyMove(
            currency_code=currency,
            change_value=_q(total),
            change_pct=_q(total / reference) if reference > 0 else None,
            last_date=max(m.price_date for m in moves),
            assets=sorted(moves, key=lambda m: abs(m.change_value), reverse=True),
        )
    return result
