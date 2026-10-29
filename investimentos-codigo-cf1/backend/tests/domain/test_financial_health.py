"""Cobertura da reserva e taxa de poupança com os meses fechados."""

from dataclasses import dataclass
from decimal import Decimal as D

from app.domain.analytics.financial_health import financial_health


@dataclass
class M:
    month: str
    income: D = D(0)
    expenses: D = D(0)
    net_invested: D = D(0)
    unclassified_net: D = D(0)
    entry_count: int = 1


def test_media_dos_ultimos_tres_meses_com_movimento():
    months = [
        M("2026-04", D(9999), D(9999)),  # fica de fora: só os 3 últimos com movimento
        M("2026-05", D(5000), D(3000), D(500)),
        M("2026-06", entry_count=0),  # sem lançamento: não puxa a média para baixo
        M("2026-06b", net_invested=D(100), entry_count=3),  # só ajuste/aplicação: também não
        M("2026-07", D(5000), D(4000), D(300)),
        M("2026-08", D(6000), D(2000), D(700)),
    ]

    h = financial_health(months, D(18000))

    assert h.months == ["2026-05", "2026-07", "2026-08"]
    assert h.avg_expenses == D(3000)
    assert h.avg_income == D(16000) / 3
    assert h.avg_invested == D(500)
    assert h.coverage_months == D(6)
    assert h.savings_rate == D(7000) / D(16000)
    assert h.complete is True and h.incomplete_months == []


def test_sem_classificacao_marca_incompleto():
    h = financial_health([M("2026-08", D(5000), D(1000), unclassified_net=D(-300))], D(3000))
    assert h.complete is False and h.incomplete_months == ["2026-08"]
    assert h.coverage_months == D(3)  # teto: o gasto real é maior


def test_sem_renda_ou_sem_gasto_nao_inventa_numero():
    h = financial_health([M("2026-08", D(0), D(0))], D(1000))
    assert h.savings_rate is None and h.coverage_months is None


def test_gasto_maior_que_a_renda_da_taxa_negativa():
    h = financial_health([M("2026-08", D(1000), D(1500))], D(0))
    assert h.savings_rate == D("-0.5")
    assert h.coverage_months is None  # sem reserva, não há cobertura


def test_sem_meses():
    h = financial_health([M("2026-08", entry_count=0)], D(500))
    assert h.months == [] and h.avg_expenses is None and h.reserve == D(500) and h.complete
