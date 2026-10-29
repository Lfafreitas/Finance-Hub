import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.schemas.transaction import TransactionCreate, TransferCreate
from app.services import transaction_service
from app.services.exceptions import (
    AccountNotFoundError,
    CrossCurrencyTransferError,
    SameAccountTransferError,
    UnsupportedCorrectionError,
)
from tests.test_persistence import make_account, make_institution, make_user


class TestPropriedadeDeConta:
    def test_criar_transacao_em_conta_inexistente_levanta_erro_de_dominio(self, db_session):
        user = make_user(db_session, email="service-owner@example.com")
        payload = TransactionCreate(
            account_id=uuid.uuid4(),
            transaction_type="DEPOSIT",
            gross_amount=Decimal(100),
            currency_code="BRL",
            transaction_date=date(2026, 1, 1),
        )
        with pytest.raises(AccountNotFoundError):
            transaction_service.create_transaction(db_session, user.id, payload)


class TestTransferenciaEntreMoedasDiferentes:
    def test_moedas_diferentes_e_rejeitado(self, db_session):
        user = make_user(db_session, email="fx-transfer@example.com")
        institution = make_institution(db_session, name="Inst FX Transfer")
        conta_brl = make_account(
            db_session,
            user,
            institution,
            name="Conta BRL",
        )
        conta_usd = make_account(db_session, user, institution, name="Conta USD")
        conta_usd.currency_code = "USD"
        db_session.flush()

        payload = TransferCreate(
            from_account_id=conta_brl.id,
            to_account_id=conta_usd.id,
            gross_amount=Decimal(100),
            transaction_date=date(2026, 1, 1),
        )
        with pytest.raises(CrossCurrencyTransferError):
            transaction_service.create_transfer(db_session, user.id, payload)


class TestSameAccountService:
    def test_mesma_conta_e_rejeitado_no_service(self, db_session):
        user = make_user(db_session, email="same-account@example.com")
        institution = make_institution(db_session, name="Inst Same Account")
        conta = make_account(db_session, user, institution, name="Conta Same Account")

        payload = TransferCreate(
            from_account_id=conta.id,
            to_account_id=conta.id,
            gross_amount=Decimal(100),
            transaction_date=date(2026, 1, 1),
        )
        with pytest.raises(SameAccountTransferError):
            transaction_service.create_transfer(db_session, user.id, payload)


class TestCorrecaoMudaContaOuAtivo:
    def test_correcao_para_outra_conta_e_rejeitada(self, db_session):
        user = make_user(db_session, email="correcao-conta@example.com")
        institution = make_institution(db_session, name="Inst Correcao Conta")
        conta_a = make_account(db_session, user, institution, name="Conta A Correcao")
        conta_b = make_account(db_session, user, institution, name="Conta B Correcao")

        original = transaction_service.create_transaction(
            db_session,
            user.id,
            TransactionCreate(
                account_id=conta_a.id,
                transaction_type="DEPOSIT",
                gross_amount=Decimal(100),
                currency_code="BRL",
                transaction_date=date(2026, 1, 1),
            ),
        )

        payload_outra_conta = TransactionCreate(
            account_id=conta_b.id,
            transaction_type="DEPOSIT",
            gross_amount=Decimal(100),
            currency_code="BRL",
            transaction_date=date(2026, 1, 1),
        )
        with pytest.raises(UnsupportedCorrectionError):
            transaction_service.correct_transaction(
                db_session, user.id, original.id, payload_outra_conta
            )

    def test_correcao_de_perna_de_transferencia_e_rejeitada(self, db_session):
        user = make_user(db_session, email="correcao-transfer@example.com")
        institution = make_institution(db_session, name="Inst Correcao Transfer")
        origem = make_account(db_session, user, institution, name="Origem Correcao Transfer")
        destino = make_account(db_session, user, institution, name="Destino Correcao Transfer")

        transfer_out, _transfer_in = transaction_service.create_transfer(
            db_session,
            user.id,
            TransferCreate(
                from_account_id=origem.id,
                to_account_id=destino.id,
                gross_amount=Decimal(500),
                transaction_date=date(2026, 1, 1),
            ),
        )

        payload = TransactionCreate(
            account_id=origem.id,
            transaction_type="DEPOSIT",
            gross_amount=Decimal(500),
            currency_code="BRL",
            transaction_date=date(2026, 1, 1),
        )
        with pytest.raises(UnsupportedCorrectionError):
            transaction_service.correct_transaction(db_session, user.id, transfer_out.id, payload)
