"""CF-1: regras do livro de caixa na camada de serviço."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models import CashflowEntry
from app.models.enums import AccountType, CashflowEntryStatus, CashflowNature, TransactionSource
from app.schemas.cashflow import CashflowEntryCreate, CashflowTransferCreate
from app.services import cashflow_service as service
from app.services.exceptions import (
    AccountNotFoundError,
    CashflowEntryAlreadyReversedError,
    CashflowEntryNotFoundError,
    CrossCurrencyTransferError,
    InvalidCashflowEntryError,
    InvalidCashflowPeriodError,
    SameAccountTransferError,
)
from tests.cashflow_helpers import make_typed_account
from tests.test_persistence import make_institution, make_user

TODAY = date(2026, 3, 31)
D = Decimal


class World:
    def __init__(self, session):
        self.db = session
        self.user = make_user(session, email=f"{uuid.uuid4().hex[:8]}@svc.example.com")
        self.inst = make_institution(session, name=f"Banco {uuid.uuid4().hex[:8]}")
        self.checking = self.account("Corrente", AccountType.CHECKING)
        self.savings = self.account("Reserva", AccountType.SAVINGS)
        self.card = self.account("Cartão", AccountType.CREDIT_CARD)
        self.brokerage = self.account("Corretora", AccountType.BROKERAGE)

    def account(self, name, account_type, currency="BRL"):
        return make_typed_account(self.db, self.user, self.inst, name, account_type, currency)

    def entry(self, account, day, amount, nature=CashflowNature.EXPENSE, month=1, desc="x"):
        payload = CashflowEntryCreate(
            account_id=account.id,
            entry_date=date(2026, month, day),
            amount=D(amount),
            description=desc,
            nature=nature,
        )
        return service.create_entry(self.db, self.user.id, payload, today=TODAY)

    def transfer(self, source, target, day, amount, month=1):
        payload = CashflowTransferCreate(
            from_account_id=source.id,
            to_account_id=target.id,
            entry_date=date(2026, month, day),
            amount=D(amount),
            description="transferência",
        )
        return service.create_transfer(self.db, self.user.id, payload, today=TODAY)


@pytest.fixture()
def world(db_session):
    return World(db_session)


class TestCriarLancamento:
    def test_moeda_vem_da_conta_e_origem_e_manual(self, world):
        usd = world.account("Conta USD", AccountType.CHECKING, "USD")

        entry = world.entry(usd, 5, "-12.34")

        assert entry.currency_code == "USD"
        assert entry.source is TransactionSource.MANUAL
        assert entry.status is CashflowEntryStatus.ACTIVE
        assert entry.nature is CashflowNature.EXPENSE

    def test_natureza_padrao_e_nao_classificado(self, world):
        payload = CashflowEntryCreate(
            account_id=world.checking.id,
            entry_date=date(2026, 1, 5),
            amount=D("-10"),
            description="  Pix enviado  ",
        )

        entry = service.create_entry(world.db, world.user.id, payload, today=TODAY)

        assert entry.nature is CashflowNature.UNCLASSIFIED
        assert entry.description == "Pix enviado"

    def test_conta_de_investimentos_e_rejeitada(self, world):
        with pytest.raises(InvalidCashflowEntryError, match="investimentos"):
            world.entry(world.brokerage, 5, "-10")

    def test_valor_zero_e_rejeitado(self, world):
        with pytest.raises(InvalidCashflowEntryError, match="zero"):
            world.entry(world.checking, 5, "0")

    def test_data_futura_e_rejeitada_e_hoje_e_aceito(self, world):
        with pytest.raises(InvalidCashflowEntryError, match="futuro"):
            world.entry(world.checking, 1, "-10", month=4)

        assert world.entry(world.checking, 31, "-10", month=3).entry_date == TODAY

    def test_transfer_nao_entra_por_lancamento_avulso(self, world):
        with pytest.raises(InvalidCashflowEntryError, match="transfers"):
            world.entry(world.checking, 5, "-10", CashflowNature.TRANSFER)

    def test_conta_de_outro_usuario_e_nao_encontrada(self, world):
        stranger = make_user(world.db, email="stranger@svc.example.com")
        foreign = make_typed_account(world.db, stranger, world.inst, "Alheia")

        with pytest.raises(AccountNotFoundError):
            world.entry(foreign, 5, "-10")


class TestTransferencia:
    def test_entre_contas_de_caixa_grava_duas_pernas_opostas(self, world):
        legs = world.transfer(world.checking, world.savings, 20, "500")

        out, incoming = sorted(legs, key=lambda e: e.amount)
        assert (out.account_id, out.amount) == (world.checking.id, D("-500"))
        assert (incoming.account_id, incoming.amount) == (world.savings.id, D("500"))
        assert out.counterparty_account_id == world.savings.id
        assert incoming.counterparty_account_id == world.checking.id
        assert out.transfer_group_id == incoming.transfer_group_id is not None
        assert {leg.nature for leg in legs} == {CashflowNature.TRANSFER}

    def test_aporte_grava_uma_perna_so_no_caixa(self, world):
        legs = world.transfer(world.checking, world.brokerage, 21, "700")

        assert len(legs) == 1
        assert (legs[0].account_id, legs[0].amount) == (world.checking.id, D("-700"))
        assert legs[0].counterparty_account_id == world.brokerage.id
        assert world.db.query(CashflowEntry).filter_by(account_id=world.brokerage.id).count() == 0

    def test_resgate_grava_a_entrada_no_caixa(self, world):
        legs = world.transfer(world.brokerage, world.checking, 22, "100")

        assert [(leg.account_id, leg.amount) for leg in legs] == [(world.checking.id, D("100"))]

    def test_entre_duas_contas_de_investimentos_e_rejeitada(self, world):
        other = world.account("Outra corretora", AccountType.BROKERAGE)

        with pytest.raises(InvalidCashflowEntryError, match="investimentos"):
            world.transfer(world.brokerage, other, 5, "10")

    def test_mesma_conta_e_rejeitada(self, world):
        with pytest.raises(SameAccountTransferError):
            world.transfer(world.checking, world.checking, 5, "10")

    @pytest.mark.parametrize("amount", ["0", "-10"])
    def test_valor_nao_positivo_e_rejeitado(self, world, amount):
        with pytest.raises(InvalidCashflowEntryError, match="maior que zero"):
            world.transfer(world.checking, world.savings, 5, amount)

    def test_moedas_diferentes_e_rejeitada_sem_gravar_nada(self, world):
        usd = world.account("Conta USD", AccountType.CHECKING, "USD")

        with pytest.raises(CrossCurrencyTransferError):
            world.transfer(world.checking, usd, 5, "10")

        assert world.db.query(CashflowEntry).count() == 0

    def test_data_futura_e_rejeitada(self, world):
        with pytest.raises(InvalidCashflowEntryError, match="futuro"):
            world.transfer(world.checking, world.savings, 1, "10", month=4)

    def test_conta_alheia_em_qualquer_ponta_e_nao_encontrada(self, world):
        stranger = make_user(world.db, email="stranger2@svc.example.com")
        foreign = make_typed_account(world.db, stranger, world.inst, "Alheia 2")

        with pytest.raises(AccountNotFoundError):
            world.transfer(world.checking, foreign, 5, "10")
        with pytest.raises(AccountNotFoundError):
            world.transfer(foreign, world.checking, 5, "10")


class TestClassificar:
    def test_muda_so_a_natureza(self, world):
        entry = world.entry(world.checking, 5, "250", CashflowNature.UNCLASSIFIED)

        updated = service.classify_entry(
            world.db, world.user.id, entry.id, CashflowNature.THIRD_PARTY
        )

        assert updated.nature is CashflowNature.THIRD_PARTY
        assert (updated.amount, updated.entry_date) == (D("250"), date(2026, 1, 5))

    def test_nao_transforma_em_transfer(self, world):
        entry = world.entry(world.checking, 5, "-250", CashflowNature.UNCLASSIFIED)

        with pytest.raises(InvalidCashflowEntryError, match="reclassificada"):
            service.classify_entry(world.db, world.user.id, entry.id, CashflowNature.TRANSFER)

    def test_nao_reclassifica_perna_de_transfer(self, world):
        leg = world.transfer(world.checking, world.savings, 5, "10")[0]

        with pytest.raises(InvalidCashflowEntryError, match="reclassificada"):
            service.classify_entry(world.db, world.user.id, leg.id, CashflowNature.EXPENSE)

    def test_lancamento_estornado_nao_e_reclassificado(self, world):
        entry = world.entry(world.checking, 5, "-10")
        service.reverse_entry(world.db, world.user.id, entry.id)

        with pytest.raises(CashflowEntryAlreadyReversedError):
            service.classify_entry(world.db, world.user.id, entry.id, CashflowNature.INCOME)

    def test_lancamento_de_outro_usuario_e_nao_encontrado(self, world):
        entry = world.entry(world.checking, 5, "-10")
        stranger = make_user(world.db, email="stranger3@svc.example.com")

        with pytest.raises(CashflowEntryNotFoundError):
            service.classify_entry(world.db, stranger.id, entry.id, CashflowNature.INCOME)
        with pytest.raises(CashflowEntryNotFoundError):
            service.get_entry(world.db, stranger.id, entry.id)
        with pytest.raises(CashflowEntryNotFoundError):
            service.reverse_entry(world.db, stranger.id, entry.id)


class TestEstornar:
    def test_estorno_tira_o_lancamento_do_saldo_e_do_resumo(self, world):
        world.entry(world.checking, 5, "1000", CashflowNature.INCOME)
        wrong = world.entry(world.checking, 6, "-400")

        reversed_entries = service.reverse_entry(world.db, world.user.id, wrong.id)

        assert [e.status for e in reversed_entries] == [CashflowEntryStatus.REVERSED]
        summary = service.get_summary(world.db, world.user.id, date(2026, 1, 1), date(2026, 1, 31))
        assert summary.totals_by_currency[0].expenses == D(0)
        balances = service.get_balances(world.db, world.user.id, date(2026, 1, 31))
        assert balances.accounts[1].balance == D("1000")

    def test_estornar_uma_perna_estorna_a_transferencia_inteira(self, world):
        legs = world.transfer(world.checking, world.savings, 20, "500")

        reversed_entries = service.reverse_entry(world.db, world.user.id, legs[1].id)

        assert {e.id for e in reversed_entries} == {leg.id for leg in legs}
        assert {e.status for e in reversed_entries} == {CashflowEntryStatus.REVERSED}

    def test_estornar_duas_vezes_e_rejeitado(self, world):
        entry = world.entry(world.checking, 5, "-10")
        service.reverse_entry(world.db, world.user.id, entry.id)

        with pytest.raises(CashflowEntryAlreadyReversedError):
            service.reverse_entry(world.db, world.user.id, entry.id)


def _real_month(world):
    """Mesma estrutura do histórico real e do teste do motor."""
    n = CashflowNature
    world.entry(world.checking, 1, "287.34", n.ADJUSTMENT)
    world.entry(world.checking, 5, "3000.00", n.INCOME)
    world.entry(world.checking, 6, "250.00", n.THIRD_PARTY)
    world.entry(world.checking, 7, "-80.00", n.THIRD_PARTY)
    world.entry(world.checking, 8, "-400.00", n.EXPENSE)
    world.entry(world.card, 9, "-600.00", n.EXPENSE)
    world.entry(world.card, 10, "150.00", n.EXPENSE)
    world.transfer(world.checking, world.card, 15, "300")
    world.transfer(world.checking, world.savings, 20, "500")
    world.transfer(world.checking, world.brokerage, 21, "700")
    world.transfer(world.brokerage, world.checking, 22, "100")
    world.entry(world.checking, 25, "-12.90", n.UNCLASSIFIED)


class TestResumoESaldos:
    def test_resumo_do_mes_vindo_do_banco(self, world):
        _real_month(world)

        summary = service.get_summary(world.db, world.user.id, date(2026, 1, 1), date(2026, 1, 31))

        (brl,) = summary.totals_by_currency
        assert brl.currency_code == "BRL"
        assert brl.entry_count == 14
        assert brl.income == D("3000")
        assert brl.third_party_net == D("170")
        assert brl.adjustments_net == D("287.34")
        assert brl.unclassified_net == D("-12.90")
        assert brl.internal_transfers_net == D(0)
        assert brl.expenses == D("850")
        assert brl.net_invested == D("600")
        assert brl.liquid_variation == D("1644.44")
        assert brl.reserve_variation == D("500")
        assert brl.card_balance_variation == D("-150")

    def test_saldos_por_conta_e_totais_por_papel(self, world):
        _real_month(world)

        balances = service.get_balances(world.db, world.user.id, date(2026, 1, 31))

        by_name = {a.account_name: a for a in balances.accounts}
        assert set(by_name) == {"Corrente", "Reserva", "Cartão"}
        assert by_name["Corrente"].balance == D("1644.44")
        assert by_name["Reserva"].balance == D("500")
        assert by_name["Cartão"].balance == D("-150")
        (brl,) = balances.totals_by_currency
        assert (brl.liquid, brl.reserve, brl.card) == (D("1644.44"), D("500"), D("-150"))

    def test_saldo_em_data_anterior_ignora_o_que_veio_depois(self, world):
        _real_month(world)

        balances = service.get_balances(world.db, world.user.id, date(2026, 1, 9))

        by_name = {a.account_name: a.balance for a in balances.accounts}
        assert by_name == {"Corrente": D("3057.34"), "Reserva": D(0), "Cartão": D("-600")}

    def test_conta_sem_lancamento_aparece_com_saldo_zero(self, world):
        balances = service.get_balances(world.db, world.user.id, date(2026, 1, 31))

        assert [a.balance for a in balances.accounts] == [D(0), D(0), D(0)]
        assert balances.totals_by_currency[0].liquid == D(0)

    def test_moedas_ficam_em_blocos_separados(self, world):
        usd = world.account("Conta USD", AccountType.CHECKING, "USD")
        world.entry(world.checking, 5, "3000", CashflowNature.INCOME)
        world.entry(usd, 5, "200", CashflowNature.INCOME)
        world.entry(usd, 6, "-30", CashflowNature.EXPENSE)

        summary = service.get_summary(world.db, world.user.id, date(2026, 1, 1), date(2026, 1, 31))
        balances = service.get_balances(world.db, world.user.id, date(2026, 1, 31))

        assert [(t.currency_code, t.income, t.expenses) for t in summary.totals_by_currency] == [
            ("BRL", D("3000"), D(0)),
            ("USD", D("200"), D("30")),
        ]
        assert [(t.currency_code, t.liquid) for t in balances.totals_by_currency] == [
            ("BRL", D("3000")),
            ("USD", D("170")),
        ]

    def test_dados_de_outro_usuario_nao_entram(self, world, db_session):
        other = World(db_session)
        other.entry(other.checking, 5, "9999", CashflowNature.INCOME)
        world.entry(world.checking, 5, "100", CashflowNature.INCOME)

        summary = service.get_summary(world.db, world.user.id, date(2026, 1, 1), date(2026, 1, 31))

        assert summary.totals_by_currency[0].income == D("100")

    def test_periodo_invertido_e_rejeitado(self, world):
        with pytest.raises(InvalidCashflowPeriodError):
            service.get_summary(world.db, world.user.id, date(2026, 2, 1), date(2026, 1, 1))


class TestListar:
    def test_mais_recente_primeiro_sem_estornados_por_padrao(self, world):
        old = world.entry(world.checking, 5, "-1", desc="antigo")
        new = world.entry(world.card, 20, "-2", desc="novo")
        gone = world.entry(world.checking, 10, "-3", desc="estornado")
        service.reverse_entry(world.db, world.user.id, gone.id)

        default = service.list_entries(world.db, world.user.id)
        everything = service.list_entries(world.db, world.user.id, include_reversed=True)

        assert [e.id for e in default] == [new.id, old.id]
        assert [e.id for e in everything] == [new.id, gone.id, old.id]

    def test_filtra_por_conta_e_periodo(self, world):
        world.entry(world.checking, 5, "-1")
        target = world.entry(world.card, 20, "-2")
        world.entry(world.card, 5, "-3", month=2)

        found = service.list_entries(
            world.db,
            world.user.id,
            account_id=world.card.id,
            start=date(2026, 1, 1),
            end=date(2026, 1, 31),
        )

        assert [e.id for e in found] == [target.id]

    def test_conta_alheia_e_nao_encontrada(self, world):
        stranger = make_user(world.db, email="stranger4@svc.example.com")
        foreign = make_typed_account(world.db, stranger, world.inst, "Alheia 4")

        with pytest.raises(AccountNotFoundError):
            service.list_entries(world.db, world.user.id, account_id=foreign.id)
