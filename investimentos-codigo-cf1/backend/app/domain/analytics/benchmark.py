"""Comparação com uma referência (SPY em dólar, CDI em reais).

Pergunta respondida: "se cada aporte tivesse ido para a referência, no
mesmo dia e no mesmo valor, quanto eu teria hoje?". É a comparação
justa para quem aporta aos poucos — o mesmo dinheiro, nas mesmas datas.

Funções puras. Moedas nunca se somam: cada comparação é de uma moeda e
usa uma referência na mesma moeda.

- Aporte: compra (quantidade × preço + taxas) entra; venda (quantidade ×
  preço − taxas) sai. Proventos não entram — a referência de preço (SPY)
  também é sem dividendos, e a tela diz isso.
- Referência como "nível": o preço do SPY, ou o CDI acumulado (produto
  de 1 + taxa do dia).
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.financial_engine import TransactionFact
from app.models.enums import TransactionType

_ZERO = Decimal(0)
_ONE = Decimal(1)
_HUNDRED = Decimal(100)
_CENT4 = Decimal("0.0001")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_CENT4, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Flow:
    day: date
    amount: Decimal  # positivo = dinheiro entrou nos investimentos


@dataclass(frozen=True)
class Level:
    day: date
    level: Decimal


def flows_from_facts(facts: list[TransactionFact]) -> list[Flow]:
    flows = []
    for f in facts:
        if f.quantity is None or f.unit_price is None:
            continue
        if f.transaction_type == TransactionType.BUY:
            flows.append(Flow(f.transaction_date, f.quantity * f.unit_price + f.fees))
        elif f.transaction_type == TransactionType.SELL:
            flows.append(Flow(f.transaction_date, -(f.quantity * f.unit_price - f.fees)))
    return sorted(flows, key=lambda x: x.day)


def cdi_levels(daily_rates: list[tuple[date, Decimal]]) -> list[Level]:
    """CDI acumulado. A taxa do dia D (em % ao dia, como o Banco Central
    publica) rende de D para o dia útil seguinte: o nível em D inclui só
    as taxas de antes de D.
    """
    levels = []
    level = _ONE
    for day, rate in sorted(daily_rates):
        levels.append(Level(day, level))
        level = level * (_ONE + rate / _HUNDRED)
    return levels


@dataclass(frozen=True)
class Simulation:
    values: list[tuple[date, Decimal]]  # valor da referência em cada dia pedido
    net_invested: Decimal


class MissingLevel(ValueError):
    """A referência não tem cotação na data (ou antes) de um aporte."""


def simulate(flows: list[Flow], levels: list[Level], days: list[date]) -> Simulation:
    """Cada aporte compra "cotas" da referência no nível do dia (ou do
    último dia antes, se não houve pregão); a venda resgata pelo mesmo
    critério. O valor de um dia é cotas × nível daquele dia.
    """
    levels = sorted(levels, key=lambda x: x.day)
    level_days = [x.day for x in levels]

    def level_on(day: date) -> Decimal | None:
        i = bisect_right(level_days, day)
        return levels[i - 1].level if i else None

    units = _ZERO
    invested = _ZERO
    out: list[tuple[date, Decimal]] = []
    pending = sorted(flows, key=lambda x: x.day)
    i = 0
    for day in sorted(days):
        while i < len(pending) and pending[i].day <= day:
            flow = pending[i]
            level = level_on(flow.day)
            if level is None or level <= 0:
                raise MissingLevel(f"sem referência em {flow.day.isoformat()}")
            units += flow.amount / level
            invested += flow.amount
            i += 1
        level = level_on(day)
        out.append((day, _q(units * level) if level is not None else _ZERO))
    return Simulation(values=out, net_invested=_q(invested))
