import uuid
from decimal import Decimal

from app.models.enums import (
    ReconciliationStatus,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.models.reconciliation_log import ReconciliationLog
from app.models.transaction import Transaction
from tests.test_persistence import make_account, make_asset, make_institution, make_user

D = "2026-08-15"
MANUAL = TransactionSource.MANUAL
CSV = TransactionSource.IMPORT_CSV


def _setup_account(db_session, user, name="Conta Reconciliation"):
    return make_account(
        db_session, user, make_institution(db_session, name=f"Inst {name}"), name=name
    )


def _tx(db, account, asset, source, qty="100", price="30", gross=None):
    quantity, unit_price = Decimal(qty), Decimal(price)
    tx = Transaction(
        account_id=account.id,
        asset_id=asset.id,
        transaction_type=TransactionType.BUY,
        quantity=quantity,
        unit_price=unit_price,
        fees=Decimal(0),
        gross_amount=Decimal(gross) if gross is not None else quantity * unit_price,
        currency_code="BRL",
        transaction_date="2026-08-15",
        source=source,
        status=TransactionStatus.ACTIVE,
    )
    db.add(tx)
    db.flush()
    return tx


def _pending_log(db, user, a, b):
    first, second = sorted([a.id, b.id])
    log = ReconciliationLog(
        user_id=user.id,
        transaction_a_id=first,
        transaction_b_id=second,
        match_reason="EQUIVALENT: todos os campos comparados são iguais",
    )
    db.add(log)
    db.flush()
    return log


class TestListarPendentes:
    def test_lista_pendentes_do_usuario(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="RCA1")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)

        response = client.get("/reconciliation/pending")

        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body] == [str(log.id)]
        assert body[0]["status"] == "PENDING"

    def test_nao_lista_pendencia_de_outro_usuario(self, api_client, db_session):
        client, _user = api_client
        outro_user = make_user(db_session, email="outro-reconc@example.com")
        outro_account = _setup_account(db_session, outro_user, name="Conta De Outro")
        asset = make_asset(db_session, ticker="RCA2")
        a = _tx(db_session, outro_account, asset, MANUAL)
        b = _tx(db_session, outro_account, asset, CSV)
        _pending_log(db_session, outro_user, a, b)

        response = client.get("/reconciliation/pending")

        assert response.status_code == 200
        assert response.json() == []

    def test_lista_vazia_sem_pendencias(self, api_client):
        client, _user = api_client

        response = client.get("/reconciliation/pending")

        assert response.status_code == 200
        assert response.json() == []

    def test_nao_lista_log_ja_resolvido(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="RCA3")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)
        response = client.post(f"/reconciliation/{log.id}/resolve", json={"decision": "IGNORE"})
        assert response.status_code == 200

        response = client.get("/reconciliation/pending")

        assert response.json() == []


class TestResolverIgnoreEKeepBoth:
    def test_ignore(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="RCB1")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)

        response = client.post(f"/reconciliation/{log.id}/resolve", json={"decision": "IGNORE"})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "IGNORED"
        assert body["resolved_at"] is not None
        assert body["surviving_transaction_id"] is None

    def test_keep_both(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="RCB2")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)

        response = client.post(f"/reconciliation/{log.id}/resolve", json={"decision": "KEEP_BOTH"})

        assert response.status_code == 200
        assert response.json()["status"] == "KEPT_BOTH"

    def test_ignore_com_surviving_transaction_id_e_rejeitado_pelo_schema(
        self, api_client, db_session
    ):
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="RCB3")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)

        response = client.post(
            f"/reconciliation/{log.id}/resolve",
            json={"decision": "IGNORE", "surviving_transaction_id": str(a.id)},
        )

        assert response.status_code == 422

    def test_resolver_de_novo_e_rejeitado(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="RCB4")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)
        client.post(f"/reconciliation/{log.id}/resolve", json={"decision": "IGNORE"})

        response = client.post(f"/reconciliation/{log.id}/resolve", json={"decision": "KEEP_BOTH"})

        assert response.status_code == 409


class TestResolverMerge:
    def test_merge_com_survivor_a(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="RCM1")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)

        response = client.post(
            f"/reconciliation/{log.id}/resolve",
            json={"decision": "MERGE", "surviving_transaction_id": str(a.id)},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "MERGED"
        assert body["surviving_transaction_id"] == str(a.id)
        assert body["reversed_transaction_id"] == str(b.id)

    def test_merge_sem_surviving_transaction_id_e_rejeitado_pelo_schema(
        self, api_client, db_session
    ):
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="RCM2")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)

        response = client.post(f"/reconciliation/{log.id}/resolve", json={"decision": "MERGE"})

        assert response.status_code == 422

    def test_merge_com_survivor_fora_do_par_e_rejeitado(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="RCM3")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        outsider = _tx(db_session, account, asset, MANUAL, gross="99999")
        log = _pending_log(db_session, user, a, b)

        response = client.post(
            f"/reconciliation/{log.id}/resolve",
            json={"decision": "MERGE", "surviving_transaction_id": str(outsider.id)},
        )

        assert response.status_code == 400

    def test_merge_com_transaction_de_outro_usuario_como_survivor_e_rejeitado(
        self, api_client, db_session
    ):
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="RCM4")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)
        outro_user = make_user(db_session, email="outro-merge@example.com")
        outro_account = _setup_account(db_session, outro_user, name="Conta De Outro Merge")
        outro_asset = make_asset(db_session, ticker="RCM4B")
        transacao_alheia = _tx(db_session, outro_account, outro_asset, MANUAL)

        response = client.post(
            f"/reconciliation/{log.id}/resolve",
            json={"decision": "MERGE", "surviving_transaction_id": str(transacao_alheia.id)},
        )

        assert response.status_code == 400

    def test_merge_com_historico_invalido_falha_e_nada_muda(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="RCM5")
        buy_small = _tx(db_session, account, asset, MANUAL, qty="40", gross="400")
        buy_big = _tx(db_session, account, asset, CSV, qty="200", gross="2000")
        sell = Transaction(
            account_id=account.id,
            asset_id=asset.id,
            transaction_type=TransactionType.SELL,
            quantity=Decimal(100),
            unit_price=Decimal(12),
            fees=Decimal(0),
            gross_amount=Decimal(1200),
            currency_code="BRL",
            transaction_date="2026-08-15",
            source=MANUAL,
            status=TransactionStatus.ACTIVE,
        )
        db_session.add(sell)
        db_session.flush()
        log = _pending_log(db_session, user, buy_small, buy_big)

        response = client.post(
            f"/reconciliation/{log.id}/resolve",
            json={"decision": "MERGE", "surviving_transaction_id": str(buy_small.id)},
        )

        assert response.status_code == 400
        db_session.expire_all()
        assert db_session.get(Transaction, buy_big.id).status == TransactionStatus.ACTIVE
        assert db_session.get(Transaction, buy_small.id).status == TransactionStatus.ACTIVE
        assert db_session.get(ReconciliationLog, log.id).status == ReconciliationStatus.PENDING


class TestOwnershipELogInexistente:
    def test_resolver_log_de_outro_usuario_e_404(self, api_client, db_session):
        client, _user = api_client
        outro_user = make_user(db_session, email="outro-resolve@example.com")
        outro_account = _setup_account(db_session, outro_user, name="Conta De Outro Resolve")
        asset = make_asset(db_session, ticker="RCO1")
        a = _tx(db_session, outro_account, asset, MANUAL)
        b = _tx(db_session, outro_account, asset, CSV)
        log = _pending_log(db_session, outro_user, a, b)

        response = client.post(f"/reconciliation/{log.id}/resolve", json={"decision": "IGNORE"})

        assert response.status_code == 404
        db_session.expire_all()
        assert db_session.get(ReconciliationLog, log.id).status == ReconciliationStatus.PENDING

    def test_log_inexistente_e_404(self, api_client):
        client, _user = api_client

        response = client.post(
            f"/reconciliation/{uuid.uuid4()}/resolve", json={"decision": "IGNORE"}
        )

        assert response.status_code == 404
