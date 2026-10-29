"""CF-1: o que o BANCO garante no livro de caixa, independente do
service — CHECKs, imutabilidade do fato e separação dos dois livros.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import CashflowEntry, Transaction
from app.models.enums import (
    AccountType,
    CashflowEntryStatus,
    CashflowNature,
    TransactionSource,
    TransactionType,
)
from tests.cashflow_helpers import make_typed_account
from tests.test_persistence import make_account, make_institution, make_user


def _setup(session):
    user = make_user(session, email=f"{uuid.uuid4().hex[:8]}@cf.example.com")
    institution = make_institution(session, name=f"Banco {uuid.uuid4().hex[:8]}")
    checking = make_typed_account(session, user, institution, "Corrente")
    return user, institution, checking


def _entry(account, **overrides) -> CashflowEntry:
    values = {
        "account_id": account.id,
        "entry_date": date(2026, 1, 10),
        "amount": Decimal("-50.00"),
        "currency_code": account.currency_code,
        "description": "Padaria",
        "source": TransactionSource.MANUAL,
        "nature": CashflowNature.EXPENSE,
    }
    values.update(overrides)
    return CashflowEntry(**values)


def _flush_fails(session, obj, match):
    session.add(obj)
    with pytest.raises(IntegrityError, match=match):
        session.flush()


class TestChecks:
    def test_grava_lancamento_valido_como_active(self, db_session):
        _user, _inst, checking = _setup(db_session)
        entry = _entry(checking)
        db_session.add(entry)
        db_session.flush()
        db_session.refresh(entry)

        assert entry.status is CashflowEntryStatus.ACTIVE
        assert entry.amount == Decimal("-50.0000")

    def test_valor_zero_e_rejeitado(self, db_session):
        _user, _inst, checking = _setup(db_session)

        _flush_fails(db_session, _entry(checking, amount=Decimal(0)), "amount_nonzero")

    def test_transfer_sem_contraparte_e_rejeitado(self, db_session):
        _user, _inst, checking = _setup(db_session)
        entry = _entry(checking, nature=CashflowNature.TRANSFER, transfer_group_id=uuid.uuid4())

        _flush_fails(db_session, entry, "transfer_has_counterparty")

    def test_transfer_sem_grupo_e_rejeitado(self, db_session):
        user, inst, checking = _setup(db_session)
        other = make_typed_account(db_session, user, inst, "Reserva", AccountType.SAVINGS)
        entry = _entry(checking, nature=CashflowNature.TRANSFER, counterparty_account_id=other.id)

        _flush_fails(db_session, entry, "transfer_has_group")

    def test_contraparte_em_lancamento_que_nao_e_transfer_e_rejeitado(self, db_session):
        user, inst, checking = _setup(db_session)
        other = make_typed_account(db_session, user, inst, "Reserva", AccountType.SAVINGS)

        _flush_fails(
            db_session, _entry(checking, counterparty_account_id=other.id), "transfer_has_"
        )

    def test_contraparte_igual_a_propria_conta_e_rejeitado(self, db_session):
        _user, _inst, checking = _setup(db_session)
        entry = _entry(
            checking,
            nature=CashflowNature.TRANSFER,
            counterparty_account_id=checking.id,
            transfer_group_id=uuid.uuid4(),
        )

        _flush_fails(db_session, entry, "counterparty_differs")


class TestFatoImutavel:
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("amount", Decimal("-51.00")),
            ("entry_date", date(2026, 1, 11)),
            ("description", "Outra coisa"),
            ("currency_code", "USD"),
            ("source", TransactionSource.IMPORT_CSV),
        ],
    )
    def test_campo_de_fato_nao_muda(self, db_session, field, value):
        _user, _inst, checking = _setup(db_session)
        entry = _entry(checking)
        db_session.add(entry)
        db_session.flush()

        setattr(entry, field, value)

        with pytest.raises(IntegrityError, match="registro histórico protegido"):
            db_session.flush()

    def test_conta_nao_muda(self, db_session):
        user, inst, checking = _setup(db_session)
        other = make_typed_account(db_session, user, inst, "Outra corrente")
        entry = _entry(checking)
        db_session.add(entry)
        db_session.flush()

        entry.account_id = other.id

        with pytest.raises(IntegrityError, match="registro histórico protegido"):
            db_session.flush()

    def test_classificacao_e_notes_mudam_livremente(self, db_session):
        _user, _inst, checking = _setup(db_session)
        entry = _entry(checking, nature=CashflowNature.UNCLASSIFIED)
        db_session.add(entry)
        db_session.flush()

        entry.nature = CashflowNature.EXPENSE
        entry.notes = "almoço"
        db_session.flush()
        db_session.refresh(entry)

        assert entry.nature is CashflowNature.EXPENSE
        assert entry.notes == "almoço"

    def test_status_vai_e_volta_entre_active_e_reversed(self, db_session):
        """Edição-2: excluir (ACTIVE -> REVERSED) e restaurar
        (REVERSED -> ACTIVE) são as duas transições do banco.
        """
        _user, _inst, checking = _setup(db_session)
        entry = _entry(checking)
        db_session.add(entry)
        db_session.flush()

        entry.status = CashflowEntryStatus.REVERSED
        db_session.flush()
        entry.status = CashflowEntryStatus.ACTIVE
        db_session.flush()
        db_session.refresh(entry)

        assert entry.status is CashflowEntryStatus.ACTIVE

    def test_substituido_por_e_fato(self, db_session):
        _user, _inst, checking = _setup(db_session)
        original = _entry(checking)
        db_session.add(original)
        db_session.flush()
        corrected = _entry(checking, corrects_entry_id=original.id)
        db_session.add(corrected)
        db_session.flush()

        corrected.corrects_entry_id = None
        with pytest.raises(IntegrityError, match="o fato não pode ser alterado"):
            db_session.flush()

    def test_um_lancamento_e_substituido_uma_vez_so(self, db_session):
        _user, _inst, checking = _setup(db_session)
        original = _entry(checking)
        db_session.add(original)
        db_session.flush()
        db_session.add(_entry(checking, corrects_entry_id=original.id))
        db_session.flush()
        db_session.add(_entry(checking, corrects_entry_id=original.id))

        with pytest.raises(IntegrityError, match="uq_cashflow_entries_corrects_entry_id"):
            db_session.flush()

    def test_delete_e_rejeitado(self, db_session):
        _user, _inst, checking = _setup(db_session)
        entry = _entry(checking)
        db_session.add(entry)
        db_session.flush()

        with pytest.raises(IntegrityError, match="não pode ser apagado"):
            db_session.execute(
                text("DELETE FROM cashflow_entries WHERE id = :id"), {"id": entry.id}
            )


class TestLivrosSeparados:
    def test_conta_existente_sem_tipo_informado_e_brokerage(self, db_session):
        user = make_user(db_session, email="legacy@cf.example.com")
        account = make_account(db_session, user, make_institution(db_session, name="Corretora L"))
        db_session.refresh(account)

        assert account.account_type is AccountType.BROKERAGE

    def test_conta_brokerage_nao_recebe_cashflow_entry(self, db_session):
        user, inst, _checking = _setup(db_session)
        brokerage = make_typed_account(db_session, user, inst, "Corretora", AccountType.BROKERAGE)

        _flush_fails(db_session, _entry(brokerage), "livro de investimentos")

    @pytest.mark.parametrize(
        "account_type",
        [AccountType.CHECKING, AccountType.SAVINGS, AccountType.CASH, AccountType.CREDIT_CARD],
    )
    def test_conta_de_caixa_nao_recebe_transaction(self, db_session, account_type):
        user, inst, _checking = _setup(db_session)
        account = make_typed_account(db_session, user, inst, "Caixa X", account_type)
        transaction = Transaction(
            account_id=account.id,
            transaction_type=TransactionType.DEPOSIT,
            gross_amount=Decimal(100),
            currency_code="BRL",
            transaction_date=date(2026, 1, 1),
            source=TransactionSource.MANUAL,
        )

        _flush_fails(db_session, transaction, "livro de caixa")

    def test_conta_com_lancamento_de_caixa_nao_vira_brokerage(self, db_session):
        _user, _inst, checking = _setup(db_session)
        db_session.add(_entry(checking))
        db_session.flush()

        checking.account_type = AccountType.BROKERAGE

        with pytest.raises(IntegrityError, match="não pode trocar de livro"):
            db_session.flush()

    def test_conta_com_transaction_nao_vira_conta_de_caixa(self, db_session):
        user, inst, _checking = _setup(db_session)
        brokerage = make_typed_account(db_session, user, inst, "Corretora", AccountType.BROKERAGE)
        db_session.add(
            Transaction(
                account_id=brokerage.id,
                transaction_type=TransactionType.DEPOSIT,
                gross_amount=Decimal(100),
                currency_code="BRL",
                transaction_date=date(2026, 1, 1),
                source=TransactionSource.MANUAL,
            )
        )
        db_session.flush()

        brokerage.account_type = AccountType.CHECKING

        with pytest.raises(IntegrityError, match="não pode trocar de livro"):
            db_session.flush()

    def test_troca_dentro_do_livro_de_caixa_e_permitida(self, db_session):
        _user, _inst, checking = _setup(db_session)
        db_session.add(_entry(checking))
        db_session.flush()

        checking.account_type = AccountType.SAVINGS
        db_session.flush()
        db_session.refresh(checking)

        assert checking.account_type is AccountType.SAVINGS

    def test_conta_vazia_pode_trocar_de_livro(self, db_session):
        _user, _inst, checking = _setup(db_session)

        checking.account_type = AccountType.BROKERAGE
        db_session.flush()
        db_session.refresh(checking)

        assert checking.account_type is AccountType.BROKERAGE

    def test_corretora_contraparte_de_aporte_nao_troca_de_livro(self, db_session):
        user, inst, checking = _setup(db_session)
        brokerage = make_typed_account(db_session, user, inst, "Corretora", AccountType.BROKERAGE)
        db_session.add(
            _entry(
                checking,
                nature=CashflowNature.TRANSFER,
                counterparty_account_id=brokerage.id,
                transfer_group_id=uuid.uuid4(),
            )
        )
        db_session.flush()

        brokerage.account_type = AccountType.CHECKING

        with pytest.raises(IntegrityError, match="não pode trocar de livro"):
            db_session.flush()
