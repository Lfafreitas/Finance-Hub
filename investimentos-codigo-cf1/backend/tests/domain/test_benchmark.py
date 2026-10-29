"""Comparação com referência: os mesmos aportes, nas mesmas datas."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domain.analytics.benchmark import (
    Flow,
    Level,
    MissingLevel,
    cdi_levels,
    flows_from_facts,
    simulate,
)
from app.domain.financial_engine import TransactionFact
from app.models.enums import TransactionType

D = Decimal
D0 = date(2026, 1, 5)


def fact(kind, qty, price, fees="0", day=D0):
    return TransactionFact(
        id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        asset_id=uuid.uuid4(),
        transaction_type=kind,
        quantity=D(qty),
        unit_price=D(price),
        fees=D(fees),
        gross_amount=D(qty) * D(price),
        currency_code="USD",
        transaction_date=day,
    )


def test_aporte_e_compra_com_taxa_e_venda_liquida_dividendo_fica_fora():
    flows = flows_from_facts(
        [
            fact(TransactionType.SELL, "1", "120", "1", D0 + timedelta(days=10)),
            fact(TransactionType.BUY, "2", "100", "1"),
            fact(TransactionType.DIVIDEND, "0", "0"),
        ]
    )

    assert flows == [Flow(D0, D("201")), Flow(D0 + timedelta(days=10), D("-119"))]


def test_mesmos_aportes_na_referencia():
    levels = [Level(D0, D("100")), Level(D0 + timedelta(days=30), D("110"))]
    flows = [Flow(D0, D("100")), Flow(D0 + timedelta(days=30), D("110"))]
    days = [D0, D0 + timedelta(days=15), D0 + timedelta(days=30)]

    sim = simulate(flows, levels, days)

    # 1 cota no dia 0; mais 1 cota no dia 30; nível 110 → 220
    assert sim.values == [(days[0], D("100")), (days[1], D("100")), (days[2], D("220"))]
    assert sim.net_invested == D("210")


def test_aporte_em_dia_sem_pregao_usa_o_ultimo_nivel_anterior():
    levels = [Level(D0, D("50"))]
    sim = simulate([Flow(D0 + timedelta(days=2), D("100"))], levels, [D0 + timedelta(days=2)])

    assert sim.values[-1][1] == D("100")


def test_aporte_antes_da_primeira_cotacao_nao_inventa():
    with pytest.raises(MissingLevel):
        simulate([Flow(D0, D("100"))], [Level(D0 + timedelta(days=1), D("10"))], [D0])


def test_venda_resgata_cotas_da_referencia():
    levels = [Level(D0, D("10")), Level(D0 + timedelta(days=1), D("20"))]
    flows = [Flow(D0, D("100")), Flow(D0 + timedelta(days=1), D("-100"))]

    sim = simulate(flows, levels, [D0 + timedelta(days=1)])

    # 10 cotas; vende 5 (100/20); sobram 5 × 20 = 100
    assert sim.values[-1][1] == D("100")
    assert sim.net_invested == D("0")


def test_cdi_acumula_a_taxa_de_antes_do_dia():
    levels = cdi_levels([(D0 + timedelta(days=1), D("0.1")), (D0, D("0.1"))])

    assert levels[0] == Level(D0, D("1"))
    assert levels[1] == Level(D0 + timedelta(days=1), D("1.001"))
    sim = simulate(
        [Flow(D0, D("1000"))],
        [*levels, Level(D0 + timedelta(days=2), D("1.001") * D("1.001"))],
        [D0 + timedelta(days=2)],
    )
    assert sim.values[-1][1] == D("1002.0010")
