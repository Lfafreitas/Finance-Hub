"""KPIs-1: indicadores da carteira e desempenho de preço de cada ativo."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domain.analytics.kpis import Bar, Holding, portfolio_kpis, price_stats

D = Decimal
AS_OF = date(2026, 10, 14)


def daily(start: date, closes: list[str]) -> list[Bar]:
    return [Bar(start + timedelta(days=i), D(c)) for i, c in enumerate(closes)]


def straight(start_price: str, end_price: str, days: int = 400, end: date = AS_OF) -> list[Bar]:
    """Reta de preço de `days` dias terminando em `end`."""
    a, b = float(start_price), float(end_price)
    start = end - timedelta(days=days - 1)
    return [
        Bar(start + timedelta(days=i), D(str(round(a + (b - a) * i / (days - 1), 4))))
        for i in range(days)
    ]


def holding(ticker="QQQ", cost="100", value="120", cls="ETF_US", label="ETF (Exterior)", **kw):
    return Holding(
        ticker=ticker,
        name=f"{ticker} fundo",
        asset_class=cls,
        asset_class_label=label,
        currency_code=kw.pop("currency", "USD"),
        quantity=D(kw.pop("quantity", "1")),
        cost=D(cost),
        value=None if value is None else D(value),
        **kw,
    )


class TestPrecos:
    def test_retornos_de_periodo_pelo_fechamento_de_inicio(self):
        bars = (
            daily(date(2025, 12, 31), ["100"])
            + daily(date(2026, 9, 14), ["110"])
            + daily(AS_OF, ["121"])
        )

        stats = price_stats(bars, AS_OF)

        assert stats.last_price == D("121")
        assert stats.return_1m == D("0.1000")  # base: 14/09 (30 dias antes)
        assert stats.return_ytd == D("0.2100")  # base: 31/12 do ano anterior
        assert stats.return_3m == D("0.2100")  # base mais próxima antes de 15/07 é 31/12

    def test_periodo_nao_coberto_fica_vazio_em_vez_de_encurtar(self):
        stats = price_stats(daily(date(2026, 9, 1), ["100"] * 44), AS_OF)

        assert stats.return_1m is not None
        assert stats.return_3m is None
        assert stats.return_ytd is None
        assert stats.return_1y is None
        assert stats.low_52w is None and stats.position_52w is None

    def test_faixa_de_52_semanas_e_distancia_da_maxima(self):
        bars = straight("100", "80", days=200, end=AS_OF - timedelta(days=200)) + straight(
            "80", "90", days=200
        )

        stats = price_stats(bars, AS_OF)

        assert stats.high_52w == D("100.0000") or stats.high_52w <= D("100")
        assert stats.low_52w == D("80.0000") or stats.low_52w >= D("80")
        assert stats.from_high == (D("90") / stats.high_52w - 1).quantize(D("0.0001"))
        assert D(0) < stats.position_52w < D(1)

    def test_ytd_parte_do_ultimo_fechamento_do_ano_anterior(self):
        # Um fechamento em 1º de janeiro (mercado que abre no feriado) não é a base.
        bars = daily(date(2025, 12, 31), ["100", "105"]) + daily(AS_OF, ["110"])

        assert price_stats(bars, AS_OF).return_ytd == D("0.1000")

    def test_posicao_exata_na_faixa_de_52_semanas(self):
        closes = ["100"] * 401
        closes[-100] = "80"  # mínima dentro da janela
        closes[-50] = "120"  # máxima dentro da janela
        closes[-1] = "110"
        stats = price_stats(daily(AS_OF - timedelta(days=400), closes), AS_OF)

        assert (stats.low_52w, stats.high_52w) == (D("80"), D("120"))
        assert stats.position_52w == D("0.7500")  # (110 - 80) / (120 - 80)
        assert stats.from_high == D("-0.0833")

    def test_queda_maxima_e_volatilidade(self):
        closes = ["100", "120", "90", "95", "100"] + ["100"] * 30
        stats = price_stats(daily(AS_OF - timedelta(days=34), closes), AS_OF)

        assert stats.max_drawdown_1y == D("-0.2500")  # 120 -> 90
        assert stats.volatility_1y > D("0.5")

    def test_poucos_dias_nao_tem_risco(self):
        stats = price_stats(daily(AS_OF - timedelta(days=5), ["1", "2", "3", "4", "5", "6"]), AS_OF)

        assert stats.volatility_1y is None and stats.max_drawdown_1y is None

    def test_preco_futuro_nao_entra(self):
        bars = daily(AS_OF - timedelta(days=1), ["100", "200", "999"])

        assert price_stats(bars, AS_OF).last_price == D("200")

    def test_sem_preco(self):
        assert price_stats([], AS_OF).last_price is None


class TestCarteira:
    def test_pesos_resultado_e_contribuicao(self):
        result = portfolio_kpis(
            [
                holding("QQQ", cost="100", value="150"),
                holding("VNQ", cost="100", value="50", cls="REIT", label="REIT"),
            ],
            AS_OF,
        )

        qqq, vnq = result.assets
        assert (result.value, result.cost, result.pnl, result.return_pct) == (
            D(200),
            D(200),
            D(0),
            D("0.0000"),
        )
        assert (qqq.ticker, qqq.weight, qqq.return_pct, qqq.contribution) == (
            "QQQ",
            D("0.7500"),
            D("0.5000"),
            D("0.2500"),
        )
        assert (vnq.weight, vnq.return_pct, vnq.contribution) == (
            D("0.2500"),
            D("-0.5000"),
            D("-0.2500"),
        )
        assert (result.positive, result.negative, result.best, result.worst) == (1, 1, "QQQ", "VNQ")

    def test_concentracao(self):
        result = portfolio_kpis(
            [
                holding("A", value="50"),
                holding("B", value="30"),
                holding("C", value="10"),
                holding("D", value="10"),
            ],
            AS_OF,
        )

        assert (result.top_ticker, result.top_weight, result.top3_weight) == (
            "A",
            D("0.5000"),
            D("0.9000"),
        )
        # 1 / (0,25 + 0,09 + 0,01 + 0,01) = 2,78
        assert result.effective_assets == D("2.7778")

    def test_exposicao_por_classe(self):
        result = portfolio_kpis(
            [
                holding("QQQ", value="60"),
                holding("SPY", value="20"),
                holding("VNQ", value="20", cls="REIT", label="REIT"),
            ],
            AS_OF,
        )

        assert [(g.asset_class, g.label, g.weight) for g in result.groups] == [
            ("ETF_US", "ETF (Exterior)", D("0.8000")),
            ("REIT", "REIT", D("0.2000")),
        ]

    def test_sem_cotacao_entra_pelo_custo_e_o_retorno_total_fica_incompleto(self):
        result = portfolio_kpis(
            [holding("QQQ", value="120"), holding("CD", cost="100", value=None)], AS_OF
        )

        cd = next(a for a in result.assets if a.ticker == "CD")
        assert (cd.weight, cd.pnl, cd.return_pct) == (D("0.4545"), None, None)
        assert result.unpriced == ("CD",)
        assert result.complete is False
        assert result.return_pct is None
        assert result.pnl == D(20)

    def test_proventos_e_rendimento_sobre_custo(self):
        result = portfolio_kpis([holding("VNQ", cost="200", value="190", dividends=D("4"))], AS_OF)

        assert result.assets[0].yield_on_cost == D("0.0200")
        assert (result.dividends, result.yield_on_cost) == (D(4), D("0.0200"))

    def test_um_ativo_so_nao_tem_melhor_e_pior(self):
        result = portfolio_kpis([holding("QQQ")], AS_OF)

        assert result.best is None and result.worst is None

    def test_moedas_nunca_se_somam(self):
        with pytest.raises(ValueError):
            portfolio_kpis([holding("QQQ"), holding("ITSA4", currency="BRL")], AS_OF)

    def test_posicao_zerada_fica_de_fora(self):
        assert portfolio_kpis([holding("QQQ", quantity="0")], AS_OF) is None


class TestCesta:
    def test_composicao_atual_nos_ultimos_12_meses(self):
        up = holding("QQQ", value="50", bars=straight("100", "120"), exchange_traded=True)
        down = holding("VNQ", value="50", bars=straight("100", "90"), exchange_traded=True)
        cd = holding("CD", cost="100", value="100", cls="BOND", label="Renda fixa")

        basket = portfolio_kpis([up, down, cd], AS_OF).basket

        assert basket.tickers == ("QQQ", "VNQ")
        assert basket.share_of_portfolio == D("0.5000")
        # rebalanceada todo dia: perto da média dos dois retornos (~ +5%)
        assert D("0.03") < basket.return_1y < D("0.07")
        assert basket.max_drawdown_1y <= D(0)

    def test_ativo_fora_de_bolsa_fica_fora_mesmo_com_historico(self):
        etf = holding("QQQ", value="50", bars=straight("100", "120"), exchange_traded=True)
        cd = holding("CD", value="50", bars=straight("1", "2"), cls="BOND", label="Renda fixa")

        basket = portfolio_kpis([etf, cd], AS_OF).basket

        assert basket.tickers == ("QQQ",)
        assert basket.share_of_portfolio == D("0.5000")

    def test_ativo_sem_um_ano_de_historico_fica_fora(self):
        young = holding(
            "NEW", value="50", bars=straight("10", "11", days=100), exchange_traded=True
        )

        assert portfolio_kpis([young], AS_OF).basket is None


class TestComProventos:
    def test_resultado_com_proventos_por_ativo_e_da_carteira(self):
        reit = holding("VNQ", cost="100", value="95", dividends=D("8"))
        etf = holding("QQQ", cost="100", value="110")

        result = portfolio_kpis([reit, etf], AS_OF)
        by = {a.ticker: a for a in result.assets}

        assert by["VNQ"].return_pct == D("-0.0500")
        assert by["VNQ"].total_return_pct == D("0.0300")  # -5 + 8 sobre 100
        assert by["QQQ"].total_return_pct == D("0.1000")
        assert result.total_return_pct == D("0.0650")  # (5 + 8) / 200

    def test_sem_cotacao_nao_tem_resultado_com_proventos(self):
        result = portfolio_kpis(
            [holding("VNQ", value=None, dividends=D("3")), holding("QQQ")], AS_OF
        )
        by = {a.ticker: a for a in result.assets}

        assert by["VNQ"].total_return_pct is None
        assert result.total_return_pct is None
