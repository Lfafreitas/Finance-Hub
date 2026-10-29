"""Dívida técnica 1: `correct_transaction` valida o histórico
resultante com o `PositionCalculator`, como `reverse_transaction` já
fazia. Uma correção que deixaria o histórico inválido é rejeitada e
não deixa NENHUM efeito (original continua ACTIVE, corrigida não existe).
"""

from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import TransactionSource, TransactionStatus, TransactionType
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate
from app.services import transaction_service
from app.services.exceptions import CorrectionInvalidatesHistoryError
from tests.test_persistence import make_account, make_asset, make_institution, make_user


def _setup(db, tag):
    user = make_user(db, email=f"corr-hist-{tag}@example.com")
    account = make_account(db, user, make_institution(db, name=f"Inst CorrHist {tag}"))
    asset = make_asset(db, ticker=f"CH{tag}")
    return user, account, asset


def _payload(account, asset, kind, qty, price="10", day=1):
    quantity, unit_price = Decimal(qty), Decimal(price)
    return TransactionCreate(
        account_id=account.id,
        asset_id=asset.id,
        transaction_type=kind,
        quantity=quantity,
        unit_price=unit_price,
        gross_amount=quantity * unit_price,
        currency_code="BRL",
        transaction_date=date(2026, 3, day),
    )


def _create(db, user, account, asset, kind, qty, day):
    return transaction_service.create_transaction(
        db, user.id, _payload(account, asset, kind, qty, day=day)
    )


def _snapshot(db, account):
    rows = db.query(Transaction).filter(Transaction.account_id == account.id).all()
    return sorted((str(r.id), r.status, r.quantity) for r in rows)


class TestCorrecaoQueInvalidaHistoricoERejeitada:
    def test_reduzir_buy_do_qual_um_sell_depende(self, db_session):
        user, account, asset = _setup(db_session, "1")
        buy = _create(db_session, user, account, asset, "BUY", "100", day=1)
        _create(db_session, user, account, asset, "SELL", "80", day=5)
        before = _snapshot(db_session, account)

        with pytest.raises(CorrectionInvalidatesHistoryError):
            transaction_service.correct_transaction(
                db_session, user.id, buy.id, _payload(account, asset, "BUY", "50", day=1)
            )

        db_session.expire_all()
        assert _snapshot(db_session, account) == before  # nada mudou
        assert buy.status == TransactionStatus.ACTIVE
        position = transaction_service.get_position(db_session, user.id, account.id, asset.id)
        assert position.quantity == Decimal(20)

    def test_aumentar_sell_alem_da_posicao(self, db_session):
        user, account, asset = _setup(db_session, "2")
        _create(db_session, user, account, asset, "BUY", "100", day=1)
        sell = _create(db_session, user, account, asset, "SELL", "80", day=5)
        before = _snapshot(db_session, account)

        with pytest.raises(CorrectionInvalidatesHistoryError):
            transaction_service.correct_transaction(
                db_session, user.id, sell.id, _payload(account, asset, "SELL", "120", day=5)
            )

        db_session.expire_all()
        assert _snapshot(db_session, account) == before
        assert sell.status == TransactionStatus.ACTIVE

    def test_mover_buy_para_depois_do_sell(self, db_session):
        user, account, asset = _setup(db_session, "3")
        buy = _create(db_session, user, account, asset, "BUY", "100", day=1)
        _create(db_session, user, account, asset, "SELL", "80", day=5)

        with pytest.raises(CorrectionInvalidatesHistoryError):
            transaction_service.correct_transaction(
                db_session, user.id, buy.id, _payload(account, asset, "BUY", "100", day=9)
            )

        db_session.expire_all()
        assert buy.status == TransactionStatus.ACTIVE

    def test_trocar_buy_por_sell_sem_posicao(self, db_session):
        user, account, asset = _setup(db_session, "4")
        buy = _create(db_session, user, account, asset, "BUY", "100", day=1)

        with pytest.raises(CorrectionInvalidatesHistoryError):
            transaction_service.correct_transaction(
                db_session, user.id, buy.id, _payload(account, asset, "SELL", "10", day=1)
            )

        db_session.expire_all()
        assert buy.status == TransactionStatus.ACTIVE

    def test_sessao_continua_utilizavel_apos_rejeicao(self, db_session):
        user, account, asset = _setup(db_session, "5")
        buy = _create(db_session, user, account, asset, "BUY", "100", day=1)
        _create(db_session, user, account, asset, "SELL", "80", day=5)
        with pytest.raises(CorrectionInvalidatesHistoryError):
            transaction_service.correct_transaction(
                db_session, user.id, buy.id, _payload(account, asset, "BUY", "50", day=1)
            )

        # Uma correção VÁLIDA logo em seguida funciona na mesma sessão.
        corrected = transaction_service.correct_transaction(
            db_session, user.id, buy.id, _payload(account, asset, "BUY", "90", day=1)
        )

        assert corrected.status == TransactionStatus.ACTIVE
        position = transaction_service.get_position(db_session, user.id, account.id, asset.id)
        assert position.quantity == Decimal(10)


class TestCorrecaoValidaContinuaFuncionando:
    def test_reduzir_buy_dentro_do_que_o_sell_permite(self, db_session):
        user, account, asset = _setup(db_session, "6")
        buy = _create(db_session, user, account, asset, "BUY", "100", day=1)
        _create(db_session, user, account, asset, "SELL", "80", day=5)

        corrected = transaction_service.correct_transaction(
            db_session, user.id, buy.id, _payload(account, asset, "BUY", "80", day=1)
        )

        db_session.expire_all()
        assert buy.status == TransactionStatus.REVERSED
        assert corrected.reverses_transaction_id == buy.id
        assert corrected.source == TransactionSource.MANUAL
        position = transaction_service.get_position(db_session, user.id, account.id, asset.id)
        assert position.quantity == Decimal(0)

    def test_sell_corrigido_ate_o_limite_exato_da_posicao(self, db_session):
        user, account, asset = _setup(db_session, "7")
        _create(db_session, user, account, asset, "BUY", "100", day=1)
        sell = _create(db_session, user, account, asset, "SELL", "80", day=5)

        corrected = transaction_service.correct_transaction(
            db_session, user.id, sell.id, _payload(account, asset, "SELL", "100", day=5)
        )

        assert corrected.quantity == Decimal(100)

    def test_correcao_sem_ativo_nao_passa_pelo_engine(self, db_session):
        user, account, _asset = _setup(db_session, "8")
        deposit_payload = TransactionCreate(
            account_id=account.id,
            transaction_type=TransactionType.DEPOSIT,
            gross_amount=Decimal(100),
            currency_code="BRL",
            transaction_date=date(2026, 3, 1),
        )
        deposit = transaction_service.create_transaction(db_session, user.id, deposit_payload)

        corrected = transaction_service.correct_transaction(
            db_session,
            user.id,
            deposit.id,
            deposit_payload.model_copy(update={"gross_amount": Decimal(150)}),
        )

        assert corrected.gross_amount == Decimal(150)
