"""Valoração a mercado de uma posição — Fase 12 (motor de cotações).

Puro, sem I/O: recebe a posição já calculada pelo `PositionCalculator`
e uma cotação já obtida por quem chama (D3: o Financial Engine não
busca cotação). Não converte moeda — posição e cotação precisam estar
na mesma moeda, e quem garante isso é quem chama.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.financial_engine.types import PositionResult


@dataclass(frozen=True)
class PriceQuote:
    """Preço de UMA unidade do ativo em uma data, na moeda indicada."""

    price: Decimal
    price_date: date
    currency_code: str


@dataclass(frozen=True)
class ValuationResult:
    """`market_value` = quantidade atual × preço. `unrealized_pnl` =
    valor de mercado − custo de aquisição do que ainda está em carteira
    (`PositionResult.total_cost_basis`). `unrealized_return_pct` é o
    P&L não realizado sobre esse mesmo custo, como fração (0.10 = 10%);
    `None` quando o custo é zero (ex.: posição só de bonificação), em
    que o percentual não é definível.
    """

    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_return_pct: Decimal | None


class ValuationCalculator:
    @staticmethod
    def calculate(position: PositionResult, quote: PriceQuote) -> ValuationResult:
        if quote.price <= 0:
            raise ValueError("cotação deve ser maior que zero")
        if position.quantity < 0:
            raise ValueError("posição com quantidade negativa não pode ser valorada")

        market_value = position.quantity * quote.price
        unrealized_pnl = market_value - position.total_cost_basis
        unrealized_return_pct = (
            unrealized_pnl / position.total_cost_basis if position.total_cost_basis > 0 else None
        )
        return ValuationResult(
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
            unrealized_return_pct=unrealized_return_pct,
        )
