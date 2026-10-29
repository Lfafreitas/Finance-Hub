"""Fase 11, unidade backend 1: GET /transactions/{id}."""

import uuid
from decimal import Decimal

from app.models.enums import TransactionSource, TransactionStatus, TransactionType
from app.models.transaction import Transaction
from tests.test_persistence import make_account, make_asset, make_institution, make_user


def _setup_account(db_session, user, name="Conta GetById"):
    institution = make_institution(db_session, name=f"Inst {name}")
    return make_account(db_session, user, institution, name=name)


def _tx(db, account, asset, source=TransactionSource.IMPORT_CSV):
    tx = Transaction(
        account_id=account.id,
        asset_id=asset.id,
        transaction_type=TransactionType.BUY,
        quantity=Decimal(10),
        unit_price=Decimal(30),
        fees=Decimal(0),
        gross_amount=Decimal(300),
        currency_code="BRL",
        transaction_date="2026-09-20",
        source=source,
        status=TransactionStatus.ACTIVE,
    )
    db.add(tx)
    db.flush()
    return tx


class TestGetTransactionPorId:
    def test_busca_bem_sucedida_inclui_source(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="GID1")
        tx = _tx(db_session, account, asset, source=TransactionSource.IMPORT_OFX)

        response = client.get(f"/transactions/{tx.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(tx.id)
        assert body["account_id"] == str(account.id)
        assert body["asset_id"] == str(asset.id)
        assert body["source"] == "IMPORT_OFX"
        assert body["status"] == "ACTIVE"

    def test_source_manual_tambem_aparece(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta GetById Manual")
        asset = make_asset(db_session, ticker="GID2")
        tx = _tx(db_session, account, asset, source=TransactionSource.MANUAL)

        response = client.get(f"/transactions/{tx.id}")

        assert response.json()["source"] == "MANUAL"

    def test_transacao_inexistente_e_404(self, api_client):
        client, _user = api_client

        response = client.get(f"/transactions/{uuid.uuid4()}")

        assert response.status_code == 404

    def test_transacao_de_outro_usuario_e_404(self, api_client, db_session):
        client, _user = api_client
        outro_user = make_user(db_session, email="outro-get-transaction@example.com")
        outro_account = _setup_account(db_session, outro_user, name="Conta De Outro")
        outro_asset = make_asset(db_session, ticker="GID3")
        outro_tx = _tx(db_session, outro_account, outro_asset)

        response = client.get(f"/transactions/{outro_tx.id}")

        assert response.status_code == 404

    def test_leitura_nao_altera_a_transaction(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta GetById RO")
        asset = make_asset(db_session, ticker="GID4")
        tx = _tx(db_session, account, asset)
        before = (tx.status, tx.gross_amount, tx.quantity)

        client.get(f"/transactions/{tx.id}")

        db_session.expire_all()
        fresh = db_session.get(Transaction, tx.id)
        assert (fresh.status, fresh.gross_amount, fresh.quantity) == before
