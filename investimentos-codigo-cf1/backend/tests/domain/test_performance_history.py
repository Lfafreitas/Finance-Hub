"""Painel-1: evolução do patrimônio e variação do último pregão."""

import uuid
from datetime import date
from decimal import Decimal

from app.domain.analytics.history import (
    CashMove,
    Holding,
    PricePoint,
    last_session_moves,
    portfolio_history,
)
from app.domain.financial_engine.types import TransactionFact
from app.models.enums import TransactionType

ACCOUNT = uuid.uuid4()


def d(day: int, month: int = 9) -> date:
    return date(2026, month, day)


def trade(kind, quantity, price, day, asset, currency="USD", month=9):
    return TransactionFact(
        id=uuid.uuid4(),
        account_id=ACCOUNT,
        asset_id=asset,
        transaction_type=kind,
        quantity=Decimal(quantity),
        unit_price=Decimal(price),
        fees=Decimal(0),
        gross_amount=Decimal(quantity) * Decimal(price),
        currency_code=currency,
        transaction_date=d(day, month),
    )


def holding(ticker, facts, prices, currency="USD", traded=True):
    return Holding(
        ticker=ticker,
        currency_code=currency,
        facts=facts,
        prices=[PricePoint(day, Decimal(p), cur) for day, p, cur in prices],
        exchange_traded=traded,
    )


SPY = uuid.uuid4()
CD = uuid.uuid4()


class TestEvolucao:
    def test_valor_usa_o_ultimo_preco_conhecido_e_a_quantidade_daquele_dia(self):
        spy = holding(
            "SPY",
            [
                trade(TransactionType.BUY, 2, 100, 2, SPY),
                trade(TransactionType.BUY, 1, 110, 4, SPY),
            ],
            [(d(2), "100", "USD"), (d(3), "105", "USD"), (d(5), "120", "USD")],
        )

        series = portfolio_history([spy], [], [d(1), d(2), d(3), d(4), d(5)])["USD"]

        assert [p.investments_value for p in series] == [
            Decimal(0),
            Decimal("200.0000"),
            Decimal("210.0000"),
            Decimal("315.0000"),  # 3 cotas × 105 (sem cotação nova no dia 4)
            Decimal("360.0000"),
        ]
        assert [p.investments_cost for p in series] == [
            Decimal(0),
            Decimal("200.0000"),
            Decimal("200.0000"),
            Decimal("310.0000"),
            Decimal("310.0000"),
        ]

    def test_sem_cotacao_entra_pelo_custo_e_e_nomeado(self):
        cd = holding(
            "CD-X",
            [trade(TransactionType.BUY, 100, 1, 2, CD)],
            [(d(4), "1.01", "USD")],
            traded=False,
        )

        series = portfolio_history([cd], [], [d(3), d(4)])["USD"]

        assert series[0].investments_value == Decimal("100.0000")
        assert series[0].unpriced == ("CD-X",)
        assert series[1].investments_value == Decimal("101.0000")
        assert series[1].unpriced == ()

    def test_cotacao_em_outra_moeda_nao_vale(self):
        spy = holding("SPY", [trade(TransactionType.BUY, 1, 100, 2, SPY)], [(d(2), "500", "BRL")])

        point = portfolio_history([spy], [], [d(3)])["USD"][0]

        assert point.investments_value == Decimal("100.0000")
        assert point.unpriced == ("SPY",)

    def test_venda_tira_a_posicao(self):
        spy = holding(
            "SPY",
            [
                trade(TransactionType.BUY, 2, 100, 2, SPY),
                trade(TransactionType.SELL, 2, 120, 3, SPY),
            ],
            [(d(2), "100", "USD"), (d(3), "120", "USD")],
        )

        series = portfolio_history([spy], [], [d(2), d(3)])["USD"]

        assert series[1].investments_value == Decimal(0)
        assert series[1].investments_cost == Decimal(0)

    def test_posicao_vendida_sem_cotacao_nao_aparece_como_sem_cotacao(self):
        spy = holding(
            "SPY",
            [
                trade(TransactionType.BUY, 2, 100, 2, SPY),
                trade(TransactionType.SELL, 2, 100, 3, SPY),
            ],
            [],
        )

        point = portfolio_history([spy], [], [d(4)])["USD"][0]

        assert point.unpriced == ()
        assert point.investments_value == Decimal(0)

    def test_caixa_acumula_por_moeda_e_entra_no_total(self):
        spy = holding("SPY", [trade(TransactionType.BUY, 1, 100, 2, SPY)], [(d(2), "100", "USD")])
        moves = [
            CashMove("BRL", d(1), Decimal(500)),
            CashMove("BRL", d(3), Decimal("-120.50")),
            CashMove("USD", d(2), Decimal(10)),
        ]

        series = portfolio_history([spy], moves, [d(1), d(2), d(3)])

        assert [p.cash for p in series["BRL"]] == [
            Decimal("500.0000"),
            Decimal("500.0000"),
            Decimal("379.5000"),
        ]
        assert [p.total for p in series["BRL"]] == [p.cash for p in series["BRL"]]
        assert series["USD"][1].total == Decimal("110.0000")
        assert series["USD"][0].total == Decimal(0)

    def test_moedas_nunca_se_somam(self):
        brl = uuid.uuid4()
        a = holding("SPY", [trade(TransactionType.BUY, 1, 100, 2, SPY)], [(d(2), "100", "USD")])
        b = holding(
            "ITSA4",
            [trade(TransactionType.BUY, 10, 10, 2, brl, currency="BRL")],
            [(d(2), "10", "BRL")],
            currency="BRL",
        )

        series = portfolio_history([a, b], [], [d(2)])

        assert series["USD"][0].investments_value == Decimal("100.0000")
        assert series["BRL"][0].investments_value == Decimal("100.0000")


class TestUltimoPregao:
    def test_variacao_e_preco_atual_contra_o_anterior(self):
        spy = holding(
            "SPY",
            [trade(TransactionType.BUY, 2, 100, 1, SPY)],
            [(d(1), "100", "USD"), (d(4), "98", "USD"), (d(5), "99", "USD")],
        )

        moves = last_session_moves([spy], d(7))["USD"]

        assert moves.change_value == Decimal("2.0000")
        assert moves.change_pct == Decimal("0.0102")
        assert moves.last_date == d(5)
        assert moves.assets[0].previous_date == d(4)

    def test_cotacao_futura_nao_entra(self):
        spy = holding(
            "SPY",
            [trade(TransactionType.BUY, 1, 100, 1, SPY)],
            [(d(1), "100", "USD"), (d(2), "110", "USD"), (d(9), "500", "USD")],
        )

        moves = last_session_moves([spy], d(5))["USD"]

        assert moves.change_value == Decimal("10.0000")

    def test_renda_fixa_e_ativo_com_uma_cotacao_ficam_de_fora(self):
        cd = holding(
            "CD-X",
            [trade(TransactionType.BUY, 100, 1, 1, CD)],
            [(d(1), "1", "USD"), (d(2), "1.01", "USD")],
            traded=False,
        )
        once = holding(
            "QQQ", [trade(TransactionType.BUY, 1, 100, 1, uuid.uuid4())], [(d(1), "100", "USD")]
        )

        assert last_session_moves([cd, once], d(5)) == {}

    def test_percentual_da_moeda_e_sobre_o_valor_anterior_de_todos(self):
        qqq = uuid.uuid4()
        spy = holding(
            "SPY",
            [trade(TransactionType.BUY, 1, 100, 1, SPY)],
            [(d(1), "100", "USD"), (d(2), "110", "USD")],
        )
        nasdaq = holding(
            "QQQ",
            [trade(TransactionType.BUY, 1, 300, 1, qqq)],
            [(d(1), "300", "USD"), (d(2), "270", "USD")],
        )

        moves = last_session_moves([spy, nasdaq], d(3))["USD"]

        assert moves.change_value == Decimal("-20.0000")
        assert moves.change_pct == Decimal("-0.0500")  # -20 / 400
        assert [a.ticker for a in moves.assets] == ["QQQ", "SPY"]  # maior movimento primeiro

    def test_mesmo_ativo_em_duas_contas_vira_uma_linha(self):
        other = uuid.uuid4()
        prices = [(d(1), "100", "USD"), (d(2), "101", "USD")]
        first = holding("SPY", [trade(TransactionType.BUY, 1, 100, 1, SPY)], prices)
        second_fact = TransactionFact(
            id=uuid.uuid4(),
            account_id=other,
            asset_id=SPY,
            transaction_type=TransactionType.BUY,
            quantity=Decimal(2),
            unit_price=Decimal(100),
            fees=Decimal(0),
            gross_amount=Decimal(200),
            currency_code="USD",
            transaction_date=d(1),
        )
        second = holding("SPY", [second_fact], prices)

        moves = last_session_moves([first, second], d(3))["USD"]

        assert len(moves.assets) == 1
        assert moves.assets[0].quantity == Decimal(3)
        assert moves.change_value == Decimal("3.0000")

    def test_posicao_zerada_nao_entra(self):
        spy = holding(
            "SPY",
            [
                trade(TransactionType.BUY, 1, 100, 1, SPY),
                trade(TransactionType.SELL, 1, 100, 2, SPY),
            ],
            [(d(1), "100", "USD"), (d(3), "101", "USD")],
        )

        assert last_session_moves([spy], d(4)) == {}
