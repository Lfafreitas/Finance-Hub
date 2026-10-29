"""Fase 12: valoração a mercado de uma posição (puro, sem banco)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.domain.financial_engine.types import PositionResult
from app.domain.financial_engine.valuation import PriceQuote, ValuationCalculator


def _position(quantity, cost):
    return PositionResult(
        account_id=uuid.uuid4(),
        asset_id=uuid.uuid4(),
        quantity=Decimal(quantity),
        average_cost=Decimal(0),
        total_cost_basis=Decimal(cost),
        realized_gain=Decimal(0),
        dividends_received=Decimal(0),
    )


def _quote(price):
    return PriceQuote(price=Decimal(price), price_date=date(2026, 6, 30), currency_code="BRL")


class TestValoracao:
    def test_valor_de_mercado_e_quantidade_vezes_preco(self):
        result = ValuationCalculator.calculate(_position("100", "3000"), _quote("33.50"))

        assert result.market_value == Decimal("3350.00")
        assert result.unrealized_pnl == Decimal("350.00")
        assert result.unrealized_return_pct == Decimal("350.00") / Decimal(3000)

    def test_prejuizo_nao_realizado_e_negativo(self):
        result = ValuationCalculator.calculate(_position("100", "3000"), _quote("27"))

        assert result.market_value == Decimal(2700)
        assert result.unrealized_pnl == Decimal(-300)
        assert result.unrealized_return_pct == Decimal("-0.1")

    def test_quantidade_fracionaria_preserva_precisao(self):
        result = ValuationCalculator.calculate(
            _position("0.12345678", "10"), _quote("100.00000001")
        )

        assert result.market_value == Decimal("0.12345678") * Decimal("100.00000001")

    def test_custo_zero_nao_tem_percentual(self):
        """Posição só de bonificação: há valor e ganho, mas dividir por
        custo zero não define um percentual.
        """
        result = ValuationCalculator.calculate(_position("10", "0"), _quote("5"))

        assert result.market_value == Decimal(50)
        assert result.unrealized_pnl == Decimal(50)
        assert result.unrealized_return_pct is None

    def test_o_custo_usado_e_o_remanescente_nao_o_historico(self):
        """Depois de vender metade, `total_cost_basis` é só o custo do
        que ficou — é contra ele que o P&L não realizado é medido.
        """
        result = ValuationCalculator.calculate(_position("50", "1500"), _quote("40"))

        assert result.unrealized_pnl == Decimal(500)

    @pytest.mark.parametrize("price", ["0", "-1"])
    def test_cotacao_nao_positiva_e_rejeitada(self, price):
        with pytest.raises(ValueError, match="maior que zero"):
            ValuationCalculator.calculate(_position("10", "100"), _quote(price))

    def test_quantidade_negativa_e_rejeitada(self):
        with pytest.raises(ValueError, match="negativa"):
            ValuationCalculator.calculate(_position("-1", "100"), _quote("10"))
