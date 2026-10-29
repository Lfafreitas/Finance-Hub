"""Análises-1: cenários de mercado. Os números esperados são calculados
à mão a partir da fórmula documentada no módulo.
"""

import math
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domain.analytics.scenarios import (
    MIN_RETURNS,
    Holding,
    default_correlation,
    historical_correlation,
    historical_volatility,
    portfolio_scenarios,
)

D0 = date(2025, 1, 1)


def _series(daily_log_returns, start=Decimal(100)):
    """Preços diários a partir de retornos logarítmicos dados."""
    prices = [(D0, start)]
    price = float(start)
    for i, r in enumerate(daily_log_returns, start=1):
        price *= math.exp(r)
        prices.append((D0 + timedelta(days=i), Decimal(str(round(price, 8)))))
    return tuple(prices)


def _alternating(n, size=0.01):
    return [size if i % 2 == 0 else -size for i in range(n)]


def _holding(key="SPY", value="1000", group="EQUITY", currency="USD", history=()):
    return Holding(
        key=key, value=Decimal(value), group=group, currency_code=currency, history=history
    )


class TestUmAtivoSemHistorico:
    def test_formula_lognormal_com_premissas_padrao(self):
        result = portfolio_scenarios([_holding()], 365)

        # σ = 0,20 (padrão de ações), μ = 0,07 (USD), T = 1
        drift, spread = 0.07 - 0.02, 0.20
        assert result.realistic_return == Decimal(str(round(math.exp(drift) - 1, 4)))
        assert result.pessimistic_return == Decimal(
            str(round(math.exp(drift - 1.2815515655446004 * spread) - 1, 4))
        )
        assert result.optimistic_return == Decimal(
            str(round(math.exp(drift + 1.2815515655446004 * spread) - 1, 4))
        )
        assert result.probability_below_today == Decimal("0.4013")  # Φ(−0,25)
        assert result.volatility == Decimal("0.2000")
        assert result.expected_return == Decimal("0.0700")

    def test_valores_sao_o_valor_de_hoje_vezes_o_retorno(self):
        result = portfolio_scenarios([_holding(value="356.01")], 84)

        assert result.value_today == Decimal("356.01")
        for ret, value in [
            (result.pessimistic_return, result.pessimistic_value),
            (result.realistic_return, result.realistic_value),
            (result.optimistic_return, result.optimistic_value),
        ]:
            assert abs(value - Decimal("356.01") * (1 + ret)) <= Decimal("0.02")
        assert result.pessimistic_value < result.realistic_value < result.optimistic_value

    def test_leque_cresce_com_a_raiz_do_tempo(self):
        quarter = portfolio_scenarios([_holding()], 365 // 4 + 1)

        years = (365 // 4 + 1) / 365
        drift = (0.07 - 0.02) * years
        expected = math.exp(drift - 1.2815515655446004 * 0.20 * math.sqrt(years)) - 1
        assert quarter.pessimistic_return == Decimal(str(round(expected, 4)))

    def test_horizonte_mais_curto_abre_menos_o_leque(self):
        short = portfolio_scenarios([_holding()], 30)
        long = portfolio_scenarios([_holding()], 365)

        assert long.pessimistic_return < short.pessimistic_return < 0
        assert long.optimistic_return > short.optimistic_return > 0

    def test_premissa_de_retorno_depende_da_moeda(self):
        brl = portfolio_scenarios([_holding(currency="BRL")], 365)
        usd = portfolio_scenarios([_holding(currency="USD")], 365)

        assert brl.expected_return == Decimal("0.1000")
        assert usd.expected_return == Decimal("0.0700")

    def test_premissas_por_grupo(self):
        crypto = portfolio_scenarios([_holding(group="CRYPTO")], 365)
        reit = portfolio_scenarios([_holding(group="REAL_ESTATE")], 365)

        assert crypto.volatility == Decimal("0.6000")
        assert reit.expected_return == Decimal("0.0600")

    @pytest.mark.parametrize("days", [0, -5])
    def test_horizonte_nao_positivo_nao_tem_cenario(self, days):
        assert portfolio_scenarios([_holding()], days) is None

    def test_sem_valor_nao_tem_cenario(self):
        assert portfolio_scenarios([], 30) is None
        assert portfolio_scenarios([_holding(value="0")], 30) is None


class TestHistorico:
    def test_volatilidade_vem_do_historico_quando_ha_retornos_suficientes(self):
        history = _series(_alternating(100))

        vol, count = historical_volatility(history)

        assert count == 100
        expected = 0.01 * math.sqrt(100 / 99) * math.sqrt(252)
        assert vol == pytest.approx(expected, rel=1e-6)

    def test_pouco_historico_usa_o_padrao_e_diz_isso(self):
        history = _series(_alternating(MIN_RETURNS - 1, 0.03))

        result = portfolio_scenarios([_holding(history=history)], 365)

        (assumption,) = result.assumptions
        assert assumption.volatility_from_history is False
        assert assumption.history_returns == MIN_RETURNS - 1
        assert assumption.volatility == Decimal("0.2000")

    def test_historico_suficiente_e_usado_e_declarado(self):
        history = _series(_alternating(MIN_RETURNS, 0.03))

        result = portfolio_scenarios([_holding(history=history)], 365)

        (assumption,) = result.assumptions
        assert assumption.volatility_from_history is True
        assert assumption.history_returns == MIN_RETURNS
        assert assumption.volatility > Decimal("0.40")
        assert result.volatility == assumption.volatility

    def test_ordem_das_datas_nao_importa(self):
        history = _series([0.01 * math.sin(i) + 0.002 for i in range(80)])
        shuffled = history[40:] + history[:40]

        assert historical_volatility(tuple(reversed(history))) == historical_volatility(history)
        assert historical_volatility(shuffled) == historical_volatility(history)

    def test_correlacao_medida_nas_datas_comuns(self):
        returns = [0.01 * math.sin(i) for i in range(90)]
        a = _series(returns)
        same = _series(returns, start=Decimal(50))
        opposite = _series([-r for r in returns])

        assert historical_correlation(a, same) == pytest.approx(1.0)
        assert historical_correlation(a, opposite) == pytest.approx(-1.0)
        assert historical_correlation(a, a[:MIN_RETURNS]) is None


class TestCarteira:
    def test_dois_ativos_do_mesmo_grupo_sem_historico_usam_correlacao_padrao(self):
        result = portfolio_scenarios([_holding("A"), _holding("B")], 365)

        expected = 0.20 * math.sqrt(0.25 + 0.25 + 2 * 0.25 * 0.85)
        assert result.volatility == Decimal(str(round(expected, 4)))
        assert [a.weight for a in result.assumptions] == [Decimal("0.5000"), Decimal("0.5000")]

    def test_correlacao_padrao_entre_grupos(self):
        assert default_correlation("EQUITY", "EQUITY") == 0.85
        assert default_correlation("EQUITY", "REAL_ESTATE") == 0.70
        assert default_correlation("REAL_ESTATE", "EQUITY") == 0.70
        assert default_correlation("EQUITY", "CRYPTO") == 0.30

    def test_ativos_que_se_anulam_quase_nao_oscilam(self):
        returns = [0.01 * math.sin(i) for i in range(90)]
        a = _holding("A", history=_series(returns))
        b = _holding("B", history=_series([-r for r in returns]))

        result = portfolio_scenarios([a, b], 365)

        assert result.volatility < Decimal("0.0010")
        assert result.probability_below_today == Decimal("0.0000")

    def test_pesos_pelo_valor_e_retorno_esperado_ponderado(self):
        result = portfolio_scenarios(
            [
                _holding("A", "750", currency="BRL"),
                _holding("B", "250", group="REAL_ESTATE", currency="BRL"),
            ],
            365,
        )

        assert [a.weight for a in result.assumptions] == [Decimal("0.7500"), Decimal("0.2500")]
        assert result.expected_return == Decimal("0.0975")  # 0,75·0,10 + 0,25·0,09
        assert result.value_today == Decimal("1000.00")

    def test_posicao_sem_valor_e_ignorada(self):
        with_zero = portfolio_scenarios([_holding("A"), _holding("B", "0")], 365)
        alone = portfolio_scenarios([_holding("A")], 365)

        assert with_zero.volatility == alone.volatility
        assert [a.key for a in with_zero.assumptions] == ["A"]
