"""Fase 11, unidade backend 3: POST /reconciliation/scan."""

import uuid
from datetime import date
from decimal import Decimal

from app.models.enums import (
    ReconciliationStatus,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.models.portfolio import Portfolio
from app.models.reconciliation_log import ReconciliationLog
from app.models.transaction import Transaction
from app.services import reconciliation_service
from tests.test_persistence import make_account, make_asset, make_institution, make_user

MANUAL = TransactionSource.MANUAL
CSV = TransactionSource.IMPORT_CSV


def _account(db, user, name, portfolio=None):
    account = make_account(db, user, make_institution(db, name=f"Inst {name}"), name=name)
    if portfolio is not None:
        account.portfolio_id = portfolio.id
        db.flush()
    return account


def _portfolio(db, user, name="Carteira Scan"):
    portfolio = Portfolio(user_id=user.id, name=name)
    db.add(portfolio)
    db.flush()
    return portfolio


def _tx(db, account, asset, source, gross="3000"):
    tx = Transaction(
        account_id=account.id,
        asset_id=asset.id,
        transaction_type=TransactionType.BUY,
        quantity=Decimal(100),
        unit_price=Decimal(30),
        fees=Decimal(0),
        gross_amount=Decimal(gross),
        currency_code="BRL",
        transaction_date=date(2026, 8, 15),
        source=source,
        status=TransactionStatus.ACTIVE,
    )
    db.add(tx)
    db.flush()
    return tx


def _pair(db, account, ticker):
    asset = make_asset(db, ticker=ticker)
    return _tx(db, account, asset, MANUAL), _tx(db, account, asset, CSV)


class TestEscopos:
    def test_scan_global_sem_corpo(self, api_client, db_session):
        client, user = api_client
        a, b = _pair(db_session, _account(db_session, user, "Scan API 1"), "SA1")
        _pair(db_session, _account(db_session, user, "Scan API 1b"), "SA1B")

        response = client.post("/reconciliation/scan")

        assert response.status_code == 200
        body = response.json()
        assert body["created_count"] == 2
        assert len(body["created"]) == 2
        assert {item["status"] for item in body["created"]} == {"PENDING"}
        pares = {(item["transaction_a_id"], item["transaction_b_id"]) for item in body["created"]}
        assert tuple(sorted([str(a.id), str(b.id)])) in pares

    def test_scan_global_com_corpo_vazio(self, api_client, db_session):
        client, user = api_client
        _pair(db_session, _account(db_session, user, "Scan API 2"), "SA2")

        response = client.post("/reconciliation/scan", json={})

        assert response.status_code == 200
        assert response.json()["created_count"] == 1

    def test_scan_por_conta_ignora_as_demais(self, api_client, db_session):
        client, user = api_client
        alvo = _account(db_session, user, "Scan API 3 alvo")
        _pair(db_session, alvo, "SA3")
        _pair(db_session, _account(db_session, user, "Scan API 3 outra"), "SA3B")

        response = client.post("/reconciliation/scan", json={"account_id": str(alvo.id)})

        assert response.status_code == 200
        assert response.json()["created_count"] == 1
        assert db_session.query(ReconciliationLog).count() == 1

    def test_scan_por_portfolio_ignora_contas_de_fora(self, api_client, db_session):
        client, user = api_client
        portfolio = _portfolio(db_session, user)
        _pair(db_session, _account(db_session, user, "Scan API 4 dentro", portfolio), "SA4")
        _pair(db_session, _account(db_session, user, "Scan API 4 fora"), "SA4B")

        response = client.post("/reconciliation/scan", json={"portfolio_id": str(portfolio.id)})

        assert response.status_code == 200
        assert response.json()["created_count"] == 1

    def test_conta_e_portfolio_juntos_e_400(self, api_client, db_session):
        client, user = api_client
        portfolio = _portfolio(db_session, user)
        account = _account(db_session, user, "Scan API 5", portfolio)
        _pair(db_session, account, "SA5")

        response = client.post(
            "/reconciliation/scan",
            json={"account_id": str(account.id), "portfolio_id": str(portfolio.id)},
        )

        assert response.status_code == 400
        assert db_session.query(ReconciliationLog).count() == 0


class TestOwnership:
    def test_conta_inexistente_e_404(self, api_client):
        client, _user = api_client

        response = client.post("/reconciliation/scan", json={"account_id": str(uuid.uuid4())})

        assert response.status_code == 404

    def test_conta_de_outro_usuario_e_404_e_nada_e_criado(self, api_client, db_session):
        client, _user = api_client
        outro = make_user(db_session, email="outro-scan-api@example.com")
        conta = _account(db_session, outro, "Scan API De Outro")
        _pair(db_session, conta, "SA6")

        response = client.post("/reconciliation/scan", json={"account_id": str(conta.id)})

        assert response.status_code == 404
        assert db_session.query(ReconciliationLog).count() == 0

    def test_portfolio_de_outro_usuario_e_404(self, api_client, db_session):
        client, _user = api_client
        outro = make_user(db_session, email="outro-scan-api-2@example.com")
        portfolio = _portfolio(db_session, outro, name="Carteira De Outro")

        response = client.post("/reconciliation/scan", json={"portfolio_id": str(portfolio.id)})

        assert response.status_code == 404

    def test_scan_global_nunca_atravessa_usuarios(self, api_client, db_session):
        client, _user = api_client
        outro = make_user(db_session, email="outro-scan-api-3@example.com")
        _pair(db_session, _account(db_session, outro, "Scan API De Outro 3"), "SA7")

        response = client.post("/reconciliation/scan")

        assert response.status_code == 200
        assert response.json() == {"created_count": 0, "created": []}
        assert db_session.query(ReconciliationLog).count() == 0


class TestComportamento:
    def test_segundo_scan_nao_recria_pares(self, api_client, db_session):
        client, user = api_client
        _pair(db_session, _account(db_session, user, "Scan API 8"), "SA8")

        first = client.post("/reconciliation/scan")
        second = client.post("/reconciliation/scan")

        assert first.json()["created_count"] == 1
        assert second.json() == {"created_count": 0, "created": []}
        assert db_session.query(ReconciliationLog).count() == 1

    def test_par_resolvido_nao_e_reapresentado(self, api_client, db_session):
        client, user = api_client
        _pair(db_session, _account(db_session, user, "Scan API 9"), "SA9")
        log_id = client.post("/reconciliation/scan").json()["created"][0]["id"]
        client.post(f"/reconciliation/{log_id}/resolve", json={"decision": "IGNORE"})

        response = client.post("/reconciliation/scan")

        assert response.json()["created_count"] == 0
        assert client.get("/reconciliation/pending").json() == []

    def test_scan_nao_altera_transactions_nem_resolve_nada(self, api_client, db_session):
        client, user = api_client
        a, b = _pair(db_session, _account(db_session, user, "Scan API 10"), "SA10")

        client.post("/reconciliation/scan")

        db_session.expire_all()
        assert a.status == TransactionStatus.ACTIVE
        assert b.status == TransactionStatus.ACTIVE
        log = db_session.query(ReconciliationLog).one()
        assert log.status == ReconciliationStatus.PENDING
        assert log.resolved_at is None

    def test_pendencia_criada_pelo_scan_aparece_em_pending(self, api_client, db_session):
        client, user = api_client
        _pair(db_session, _account(db_session, user, "Scan API 11"), "SA11")

        created = client.post("/reconciliation/scan").json()["created"]
        pending = client.get("/reconciliation/pending").json()

        assert [item["id"] for item in pending] == [created[0]["id"]]

    def test_corpo_com_uuid_invalido_e_422(self, api_client):
        client, _user = api_client

        response = client.post("/reconciliation/scan", json={"account_id": "x"})

        assert response.status_code == 422


class TestCorridaComOutroProcesso:
    def test_par_criado_por_outro_processo_durante_o_scan_nao_derruba_o_scan(
        self, api_client, db_session, monkeypatch
    ):
        """Dívida 3 (scan sem SAVEPOINT): outro processo registra o par
        DEPOIS de o scan ler os pares existentes. O UNIQUE rejeita o
        insert; o scan trata como benigno, segue com os demais pares e
        não duplica nada.
        """
        client, user = api_client
        account = _account(db_session, user, "Scan API 12")
        a, b = _pair(db_session, account, "SA12")
        _pair(db_session, account, "SA12B")
        first, second = sorted([a.id, b.id])
        db_session.add(
            ReconciliationLog(
                user_id=user.id,
                transaction_a_id=first,
                transaction_b_id=second,
                match_reason="criado por outro processo",
            )
        )
        db_session.flush()
        # O scan "não viu" o log acima na sua leitura inicial.
        monkeypatch.setattr(reconciliation_service, "_existing_pairs", lambda *_a, **_k: set())

        response = client.post("/reconciliation/scan")

        assert response.status_code == 200
        assert response.json()["created_count"] == 1  # só o par SA12B
        assert db_session.query(ReconciliationLog).count() == 2
        original = (
            db_session.query(ReconciliationLog)
            .filter(ReconciliationLog.transaction_a_id == first)
            .one()
        )
        assert original.match_reason == "criado por outro processo"
