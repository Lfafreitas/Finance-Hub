from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import Transaction
from app.models.enums import TransactionSource, TransactionType
from tests.test_persistence import make_account, make_institution, make_user


def force_deferred_checks(session):
    """Os triggers de vínculo de transferência (FK + consistência) são
    DEFERRED até o COMMIT — e nossos testes nunca commitam de verdade
    (isolamento via rollback). `SET CONSTRAINTS ALL IMMEDIATE` força a
    checagem agora, dentro da mesma transação, sem precisar commitar.
    """
    session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


def make_transfer(session, account, transaction_type, linked_id=None, amount=Decimal("100.00")):
    txn = Transaction(
        account_id=account.id,
        asset_id=None,
        transaction_type=transaction_type,
        fees=Decimal(0),
        gross_amount=amount,
        currency_code="BRL",
        transaction_date=date(2026, 1, 1),
        source=TransactionSource.MANUAL,
        linked_transaction_id=linked_id,
    )
    session.add(txn)
    session.flush()
    return txn


class TestVinculoDeTransferencia:
    def test_par_valido_out_in_e_aceito(self, db_session):
        user = make_user(db_session, email="par-valido@example.com")
        institution = make_institution(db_session, name="Inst Par Valido")
        acc_a = make_account(db_session, user, institution, name="Conta A Valido")
        acc_b = make_account(db_session, user, institution, name="Conta B Valido")

        out_txn = make_transfer(db_session, acc_a, TransactionType.TRANSFER_OUT)
        in_txn = make_transfer(db_session, acc_b, TransactionType.TRANSFER_IN, linked_id=out_txn.id)
        out_txn.linked_transaction_id = in_txn.id
        db_session.flush()

        force_deferred_checks(db_session)  # não deve levantar

    def test_perna_solitaria_sem_vinculo_e_permitida_temporariamente(self, db_session):
        """'não obrigar a existência da segunda ponta no momento da
        primeira importação' — uma TRANSFER_OUT sem linked_transaction_id
        ainda é válida.
        """
        user = make_user(db_session, email="solitaria@example.com")
        institution = make_institution(db_session, name="Inst Solitaria")
        account = make_account(db_session, user, institution, name="Conta Solitaria")

        make_transfer(db_session, account, TransactionType.TRANSFER_OUT, linked_id=None)
        force_deferred_checks(db_session)  # não deve levantar

    def test_autovinculo_e_rejeitado(self, db_session):
        user = make_user(db_session, email="auto@example.com")
        institution = make_institution(db_session, name="Inst Auto")
        account = make_account(db_session, user, institution, name="Conta Auto")

        txn = make_transfer(db_session, account, TransactionType.TRANSFER_OUT)
        txn.linked_transaction_id = txn.id
        db_session.flush()

        with pytest.raises(IntegrityError):
            force_deferred_checks(db_session)

    def test_out_out_e_rejeitado(self, db_session):
        user = make_user(db_session, email="outout@example.com")
        institution = make_institution(db_session, name="Inst OutOut")
        acc_a = make_account(db_session, user, institution, name="Conta A OutOut")
        acc_b = make_account(db_session, user, institution, name="Conta B OutOut")

        t1 = make_transfer(db_session, acc_a, TransactionType.TRANSFER_OUT)
        t2 = make_transfer(db_session, acc_b, TransactionType.TRANSFER_OUT, linked_id=t1.id)
        t1.linked_transaction_id = t2.id
        db_session.flush()

        with pytest.raises(IntegrityError):
            force_deferred_checks(db_session)

    def test_vinculo_assimetrico_e_rejeitado(self, db_session):
        user = make_user(db_session, email="assimetria@example.com")
        institution = make_institution(db_session, name="Inst Assimetria")
        acc_a = make_account(db_session, user, institution, name="Conta A Assimetria")
        acc_b = make_account(db_session, user, institution, name="Conta B Assimetria")

        in_txn = make_transfer(db_session, acc_b, TransactionType.TRANSFER_IN, linked_id=None)
        make_transfer(db_session, acc_a, TransactionType.TRANSFER_OUT, linked_id=in_txn.id)
        # in_txn nunca aponta de volta

        with pytest.raises(IntegrityError):
            force_deferred_checks(db_session)

    def test_vinculo_ja_estabelecido_e_imutavel(self, db_session):
        user = make_user(db_session, email="imut-link@example.com")
        institution = make_institution(db_session, name="Inst Imut Link")
        acc_a = make_account(db_session, user, institution, name="Conta A Imut")
        acc_b = make_account(db_session, user, institution, name="Conta B Imut")
        acc_c = make_account(db_session, user, institution, name="Conta C Imut")

        out_txn = make_transfer(db_session, acc_a, TransactionType.TRANSFER_OUT)
        in_txn = make_transfer(db_session, acc_b, TransactionType.TRANSFER_IN, linked_id=out_txn.id)
        out_txn.linked_transaction_id = in_txn.id
        db_session.flush()
        force_deferred_checks(db_session)  # par válido, confirmado

        outra_in = make_transfer(db_session, acc_c, TransactionType.TRANSFER_IN)
        out_txn.linked_transaction_id = outra_in.id
        with pytest.raises(IntegrityError):
            db_session.flush()  # bloqueado pelo trigger de imutabilidade (BEFORE UPDATE, imediato)
