"""Empresas por trás dos ETFs: soma pelos fundos e pela ação direta."""

from datetime import date
from decimal import Decimal as D

from app.domain.analytics.lookthrough import Composition, Constituent, Holding, look_through

DAY = date(2026, 10, 24)


def comp(fund, *items):
    return Composition(
        fund=fund,
        as_of=DAY,
        source="gestora",
        constituents=tuple(Constituent(name, ticker, D(w)) for name, ticker, w in items),
    )


QQQ = comp(
    "QQQ", ("NVIDIA", "NVDA", "0.10"), ("Microsoft", "MSFT", "0.08"), ("Apple", "AAPL", "0.07")
)
SPY = comp(
    "SPY", ("NVIDIA", "NVDA", "0.07"), ("Apple", "AAPL", "0.06"), ("Microsoft", "MSFT", "0.06")
)


def test_mesma_empresa_por_dois_fundos_soma():
    result = look_through(
        [Holding("QQQ", "ETF_US", D("0.5")), Holding("SPY", "ETF_US", D("0.3"))], [QQQ, SPY]
    )

    nvda = result.companies[0]
    assert (nvda.name, nvda.ticker) == ("NVIDIA", "NVDA")
    assert nvda.weight == D("0.071")  # 0,5×10% + 0,3×7%
    assert [(v.ticker, v.weight) for v in nvda.via] == [("QQQ", D("0.050")), ("SPY", D("0.021"))]
    assert [c.ticker for c in result.companies] == ["NVDA", "MSFT", "AAPL"]
    assert result.explained == D("0.071") + D("0.058") + D("0.053")


def test_cobertura_de_cada_fundo_e_fundo_sem_composicao():
    result = look_through(
        [
            Holding("QQQ", "ETF_US", D("0.5")),
            Holding("VNQ", "REIT", D("0.1")),
            Holding("CD1", "BOND", D("0.2")),  # renda fixa não é "fundo sem composição"
        ],
        [QQQ],
    )

    (fund,) = result.funds
    assert (fund.ticker, fund.weight, fund.coverage) == ("QQQ", D("0.5"), D("0.25"))
    assert result.missing == ["VNQ"]


def test_acao_direta_conta_como_a_propria_empresa_e_soma_com_o_fundo():
    result = look_through(
        [Holding("QQQ", "ETF_US", D("0.5")), Holding("nvda", "STOCK_US", D("0.02"))], [QQQ]
    )

    nvda = result.companies[0]
    assert nvda.weight == D("0.07")
    assert [v.ticker for v in nvda.via] == ["QQQ", "nvda"]


def test_empresa_sem_ticker_agrupa_pelo_nome_sem_diferenciar_maiusculas():
    a = comp("AAA", ("Taiwan Semiconductor", None, "0.1"))
    b = comp("BBB", ("TAIWAN SEMICONDUCTOR", None, "0.2"))
    result = look_through(
        [Holding("AAA", "ETF_US", D("0.5")), Holding("bbb", "ETF_US", D("0.5"))], [a, b]
    )

    (tsmc,) = result.companies
    assert tsmc.weight == D("0.15") and tsmc.name == "Taiwan Semiconductor"


def test_limite_de_empresas_e_peso_zero_ignorado():
    many = comp("BIG", *[(f"E{i:02d}", f"E{i:02d}", "0.01") for i in range(20)])
    result = look_through(
        [Holding("BIG", "ETF_US", D(1)), Holding("QQQ", "ETF_US", D(0))], [many, QQQ], top=5
    )

    assert len(result.companies) == 5
    assert [f.ticker for f in result.funds] == ["BIG"]
    assert result.explained == D("0.05")


def test_sem_nada():
    result = look_through([], [])
    assert (result.companies, result.funds, result.missing, result.explained) == ([], [], [], 0)
