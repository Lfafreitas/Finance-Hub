"""Agenda: vencimentos de renda fixa e estimativa no vencimento."""

from datetime import date
from decimal import Decimal

from app.domain.analytics.agenda import FixedIncomeHolding, build_agenda, estimate_at_maturity

D = Decimal
TODAY = date(2026, 10, 16)


def cd(ticker="CD-A", maturity=date(2026, 11, 23), rate="0.0385", **kw):
    base = {
        "ticker": ticker,
        "name": f"{ticker} nome",
        "asset_class": "BOND",
        "currency_code": "USD",
        "quantity": D("100"),
        "cost": D("100"),
        "value": D("100.73"),
        "maturity_date": maturity,
        "annual_rate": None if rate is None else D(rate),
        "first_purchase": date(2025, 11, 23),
    }
    base.update(kw)
    return FixedIncomeHolding(**base)


def test_vencimentos_em_ordem_de_data_com_dias_que_faltam():
    agenda = build_agenda([cd("CD-B", date(2026, 12, 7)), cd("CD-A", date(2026, 11, 23))], TODAY)

    assert [m.ticker for m in agenda.maturities] == ["CD-A", "CD-B"]
    assert agenda.maturities[0].days_left == 38
    assert agenda.maturities[1].days_left == 52


def test_estimativa_por_juros_compostos_desde_a_compra():
    # 1 ano exato (365 dias) a 3,85% a.a. sobre 100
    assert estimate_at_maturity(D("100"), D("0.0385"), date(2025, 11, 23), date(2026, 11, 23)) == D(
        "103.85"
    )
    # meio ano: (1,0385)^(0,5) ≈ 1,01907
    assert estimate_at_maturity(D("50"), D("0.0385"), date(2026, 6, 9), date(2026, 12, 8)) == D(
        "50.95"
    )


def test_sem_taxa_ou_sem_compra_nao_estima():
    assert estimate_at_maturity(D("100"), None, date(2025, 1, 1), date(2026, 1, 1)) is None
    assert estimate_at_maturity(D("100"), D("0.04"), None, date(2026, 1, 1)) is None
    assert estimate_at_maturity(D("100"), D("0.04"), date(2027, 1, 1), date(2026, 1, 1)) is None
    (item,) = build_agenda([cd(rate=None)], TODAY).maturities
    assert item.estimated_at_maturity is None


def test_renda_fixa_sem_vencimento_e_nomeada_e_outras_classes_nao():
    etf = cd("QQQ", maturity=None, asset_class="ETF_US")
    bond = cd("TBILL", maturity=None)

    agenda = build_agenda([etf, bond], TODAY)

    assert agenda.maturities == []
    assert agenda.missing_maturity == ["TBILL"]


def test_vencido_ainda_na_carteira_aparece_com_dias_negativos_e_zerado_some():
    agenda = build_agenda([cd("VELHO", date(2026, 10, 1)), cd("ZERADO", quantity=D("0"))], TODAY)

    assert [(m.ticker, m.days_left) for m in agenda.maturities] == [("VELHO", -15)]
