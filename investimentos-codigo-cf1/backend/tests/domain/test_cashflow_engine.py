"""CF-1: motor puro do livro de caixa."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.domain.cashflow_engine import (
    BalanceCalculator,
    CashEntryFact,
    CashflowIdentityError,
    CashflowSummaryCalculator,
)
from app.domain.cashflow_engine.summary import _Accumulator
from app.models.enums import AccountType, CashflowNature

CHECKING = uuid.uuid4()
SAVINGS = uuid.uuid4()
CARD = uuid.uuid4()
WALLET = uuid.uuid4()
USD_ACCOUNT = uuid.uuid4()

_TYPES = {
    CHECKING: AccountType.CHECKING,
    SAVINGS: AccountType.SAVINGS,
    CARD: AccountType.CREDIT_CARD,
    WALLET: AccountType.CASH,
    USD_ACCOUNT: AccountType.CHECKING,
}

JAN = (date(2026, 1, 1), date(2026, 1, 31))


def fact(account, day, amount, nature, counterparty=None, currency="BRL", month=1, year=2026):
    return CashEntryFact(
        account_id=account,
        account_type=_TYPES[account],
        currency_code=currency,
        entry_date=date(year, month, day),
        amount=Decimal(amount),
        nature=nature,
        counterparty_account_type=counterparty,
    )


N = CashflowNature


def _month():
    """Um mês com a mesma estrutura do histórico real: salário, acerto
    com terceiros, gasto no débito, compra e estorno no cartão,
    pagamento de fatura, reserva, aporte e saldo inicial.
    """
    return [
        fact(CHECKING, 1, "287.34", N.ADJUSTMENT),
        fact(CHECKING, 5, "3000.00", N.INCOME),
        fact(CHECKING, 6, "250.00", N.THIRD_PARTY),
        fact(CHECKING, 7, "-80.00", N.THIRD_PARTY),
        fact(CHECKING, 8, "-400.00", N.EXPENSE),
        fact(CARD, 9, "-600.00", N.EXPENSE),
        fact(CARD, 10, "150.00", N.EXPENSE),  # estorno
        fact(CHECKING, 15, "-300.00", N.TRANSFER, AccountType.CREDIT_CARD),
        fact(CARD, 15, "300.00", N.TRANSFER, AccountType.CHECKING),
        fact(CHECKING, 20, "-500.00", N.TRANSFER, AccountType.SAVINGS),
        fact(SAVINGS, 20, "500.00", N.TRANSFER, AccountType.CHECKING),
        fact(CHECKING, 21, "-700.00", N.TRANSFER, AccountType.BROKERAGE),
        fact(CHECKING, 22, "100.00", N.TRANSFER, AccountType.BROKERAGE),  # resgate
        fact(CHECKING, 25, "-12.90", N.UNCLASSIFIED),
    ]


class TestResumoDoPeriodo:
    def test_cada_termo_do_mes(self):
        summary = CashflowSummaryCalculator.calculate(_month(), *JAN)["BRL"]

        assert summary.entry_count == 14
        assert summary.income == Decimal("3000.00")
        assert summary.third_party_net == Decimal("170.00")
        assert summary.adjustments_net == Decimal("287.34")
        assert summary.unclassified_net == Decimal("-12.90")
        assert summary.internal_transfers_net == Decimal("0.00")
        assert summary.expenses == Decimal("850.00")
        assert summary.net_invested == Decimal("600.00")
        assert summary.liquid_variation == Decimal("1644.44")
        assert summary.reserve_variation == Decimal("500.00")
        assert summary.card_balance_variation == Decimal("-150.00")

    def test_identidade_fecha_no_centavo(self):
        summary = CashflowSummaryCalculator.calculate(_month(), *JAN)["BRL"]

        assert summary.sources_total == Decimal("3444.44")
        assert summary.uses_total == Decimal("3444.44")

    def test_estorno_reduz_gasto_e_nunca_vira_renda(self):
        facts = [fact(CARD, 3, "-2999.00", N.EXPENSE), fact(CARD, 9, "2999.00", N.EXPENSE)]

        summary = CashflowSummaryCalculator.calculate(facts, *JAN)["BRL"]

        assert summary.expenses == Decimal("0.00")
        assert summary.income == Decimal(0)

    def test_devolucao_de_renda_reduz_a_renda(self):
        facts = [fact(CHECKING, 3, "2000", N.INCOME), fact(CHECKING, 9, "-721.50", N.INCOME)]

        summary = CashflowSummaryCalculator.calculate(facts, *JAN)["BRL"]

        assert summary.income == Decimal("1278.50")
        assert summary.expenses == Decimal(0)

    def test_terceiros_nao_entra_em_renda_nem_em_gasto(self):
        facts = [fact(CHECKING, 3, "400", N.THIRD_PARTY), fact(CHECKING, 4, "-90", N.THIRD_PARTY)]

        summary = CashflowSummaryCalculator.calculate(facts, *JAN)["BRL"]

        assert (summary.income, summary.expenses) == (Decimal(0), Decimal(0))
        assert summary.third_party_net == Decimal(310)

    def test_pagamento_de_fatura_nao_e_gasto(self):
        facts = [
            fact(CHECKING, 15, "-300", N.TRANSFER, AccountType.CREDIT_CARD),
            fact(CARD, 15, "300", N.TRANSFER, AccountType.CHECKING),
        ]

        summary = CashflowSummaryCalculator.calculate(facts, *JAN)["BRL"]

        assert summary.expenses == Decimal(0)
        assert summary.net_invested == Decimal(0)
        assert summary.liquid_variation == Decimal(-300)
        assert summary.card_balance_variation == Decimal(300)

    def test_reserva_nao_e_aporte_em_corretora(self):
        facts = [
            fact(CHECKING, 20, "-500", N.TRANSFER, AccountType.SAVINGS),
            fact(SAVINGS, 20, "500", N.TRANSFER, AccountType.CHECKING),
        ]

        summary = CashflowSummaryCalculator.calculate(facts, *JAN)["BRL"]

        assert summary.net_invested == Decimal(0)
        assert summary.reserve_variation == Decimal(500)
        assert summary.liquid_variation == Decimal(-500)

    def test_resgate_reduz_o_aporte_liquido(self):
        facts = [
            fact(CHECKING, 21, "-700", N.TRANSFER, AccountType.BROKERAGE),
            fact(CHECKING, 22, "100", N.TRANSFER, AccountType.BROKERAGE),
        ]

        summary = CashflowSummaryCalculator.calculate(facts, *JAN)["BRL"]

        assert summary.net_invested == Decimal(600)
        assert summary.internal_transfers_net == Decimal(0)

    def test_perna_orfa_aparece_em_transferencias_internas(self):
        facts = [fact(CHECKING, 20, "-500", N.TRANSFER, AccountType.SAVINGS)]

        summary = CashflowSummaryCalculator.calculate(facts, *JAN)["BRL"]

        assert summary.internal_transfers_net == Decimal(-500)
        assert summary.sources_total == summary.uses_total

    def test_dinheiro_em_especie_conta_como_caixa_disponivel(self):
        facts = [fact(WALLET, 3, "-35", N.EXPENSE)]

        summary = CashflowSummaryCalculator.calculate(facts, *JAN)["BRL"]

        assert summary.liquid_variation == Decimal(-35)
        assert summary.reserve_variation == Decimal(0)

    def test_datas_do_periodo_sao_inclusivas_e_o_resto_fica_fora(self):
        facts = [
            fact(CHECKING, 31, "-1", N.EXPENSE, month=12, year=2025),
            fact(CHECKING, 1, "-10", N.EXPENSE),
            fact(CHECKING, 31, "-100", N.EXPENSE),
            fact(CHECKING, 1, "-1000", N.EXPENSE, month=2),
        ]

        summary = CashflowSummaryCalculator.calculate(facts, *JAN)["BRL"]

        assert summary.expenses == Decimal(110)
        assert summary.entry_count == 2

    def test_periodo_invertido_e_erro(self):
        with pytest.raises(ValueError, match="início"):
            CashflowSummaryCalculator.calculate([], date(2026, 2, 1), date(2026, 1, 1))

    def test_periodo_sem_lancamento_nao_inventa_moeda(self):
        assert CashflowSummaryCalculator.calculate([], *JAN) == {}


class TestConferenciaDaIdentidade:
    def test_acumulador_corrompido_nao_devolve_numero(self):
        accumulator = _Accumulator()
        accumulator.add(fact(CHECKING, 5, "3000", N.INCOME))
        accumulator.liquid += Decimal("0.01")

        with pytest.raises(CashflowIdentityError, match="BRL"):
            accumulator.build("BRL")


class TestMoedas:
    def test_moedas_nunca_sao_somadas(self):
        facts = [
            fact(CHECKING, 5, "3000", N.INCOME),
            fact(CHECKING, 6, "-400", N.EXPENSE),
            fact(USD_ACCOUNT, 5, "200", N.INCOME, currency="USD"),
            fact(USD_ACCOUNT, 6, "-30", N.EXPENSE, currency="USD"),
        ]

        summaries = CashflowSummaryCalculator.calculate(facts, *JAN)

        assert list(summaries) == ["BRL", "USD"]
        assert (summaries["BRL"].income, summaries["BRL"].expenses) == (
            Decimal(3000),
            Decimal(400),
        )
        assert (summaries["USD"].income, summaries["USD"].expenses) == (
            Decimal(200),
            Decimal(30),
        )
        assert summaries["USD"].liquid_variation == Decimal(170)


class TestSaldos:
    def test_saldo_por_conta_ate_a_data_inclusive(self):
        balances = {
            b.account_id: b for b in BalanceCalculator.calculate(_month(), date(2026, 1, 15))
        }

        assert balances[CHECKING].balance == Decimal("2757.34")
        assert balances[CARD].balance == Decimal("-150.00")
        assert SAVINGS not in balances

    def test_saldo_final_do_mes(self):
        balances = {
            b.account_id: b for b in BalanceCalculator.calculate(_month(), date(2026, 1, 31))
        }

        assert balances[CHECKING].balance == Decimal("1644.44")
        assert balances[SAVINGS].balance == Decimal("500.00")
        assert balances[CARD].account_type is AccountType.CREDIT_CARD
        assert balances[CHECKING].currency_code == "BRL"

    def test_variacao_do_periodo_e_a_diferenca_de_saldos(self):
        extra = [*_month(), fact(CHECKING, 3, "-44.44", N.EXPENSE, month=2)]
        before = {b.account_id: b.balance for b in BalanceCalculator.calculate(extra, JAN[1])}
        after = {
            b.account_id: b.balance for b in BalanceCalculator.calculate(extra, date(2026, 2, 28))
        }

        summary = CashflowSummaryCalculator.calculate(extra, date(2026, 2, 1), date(2026, 2, 28))

        assert summary["BRL"].liquid_variation == after[CHECKING] - before[CHECKING]
        assert after[CHECKING] == Decimal("1600.00")

    def test_conta_com_moeda_inconsistente_e_erro(self):
        facts = [
            fact(CHECKING, 1, "10", N.INCOME),
            fact(CHECKING, 2, "10", N.INCOME, currency="USD"),
        ]

        with pytest.raises(ValueError, match="moeda"):
            BalanceCalculator.calculate(facts, date(2026, 1, 31))


class TestFatoInvalido:
    def test_conta_brokerage_nao_e_do_livro_de_caixa(self):
        with pytest.raises(ValueError, match="BROKERAGE"):
            CashEntryFact(
                account_id=uuid.uuid4(),
                account_type=AccountType.BROKERAGE,
                currency_code="BRL",
                entry_date=date(2026, 1, 1),
                amount=Decimal(1),
                nature=N.INCOME,
            )

    def test_valor_zero(self):
        with pytest.raises(ValueError, match="zero"):
            fact(CHECKING, 1, "0", N.INCOME)

    def test_transfer_sem_contraparte(self):
        with pytest.raises(ValueError, match="contraparte"):
            fact(CHECKING, 1, "-10", N.TRANSFER)

    def test_contraparte_fora_de_transfer(self):
        with pytest.raises(ValueError, match="contraparte"):
            fact(CHECKING, 1, "-10", N.EXPENSE, AccountType.SAVINGS)
