"""Fase 10b, unidade 7: POST /transactions e POST /transactions/{id}/correct
disparando a checagem síncrona pós-criação (D-H1). Roda tudo na mesma
sessão do request (api_client), sem precisar de commit real nem de
BackgroundTask -- isso é exclusivo do fluxo de importação, coberto em
tests/api/test_import_reconciliation_integration.py.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import or_

from app.models.enums import ReconciliationStatus, TransactionSource, TransactionStatus
from app.models.reconciliation_log import ReconciliationLog
from app.models.transaction import Transaction
from tests.test_persistence import make_account, make_asset, make_institution

D = "2026-09-10"
D_DATE = date(2026, 9, 10)


def _setup_account(db_session, user, name="Conta Check"):
    return make_account(
        db_session, user, make_institution(db_session, name=f"Inst {name}"), name=name
    )


def _tx(db, account, asset, source, qty="100", price="30", gross=None):
    quantity, unit_price = Decimal(qty), Decimal(price)
    tx = Transaction(
        account_id=account.id,
        asset_id=asset.id,
        transaction_type="BUY",
        quantity=quantity,
        unit_price=unit_price,
        fees=Decimal(0),
        gross_amount=Decimal(gross) if gross is not None else quantity * unit_price,
        currency_code="BRL",
        transaction_date=D_DATE,
        source=source,
        status=TransactionStatus.ACTIVE,
    )
    db.add(tx)
    db.flush()
    return tx


class TestCriacaoDisparaReconciliacao:
    def test_post_transactions_cria_normalmente(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, "N1")
        asset = make_asset(db_session, ticker="CHA1")

        response = client.post(
            "/transactions",
            json={
                "account_id": str(account.id),
                "asset_id": str(asset.id),
                "transaction_type": "BUY",
                "quantity": "100",
                "unit_price": "30",
                "gross_amount": "3000",
                "currency_code": "BRL",
                "transaction_date": D,
            },
        )

        assert response.status_code == 201
        assert response.json()["gross_amount"] in ("3000", "3000.00", 3000)

    def test_reconciliacao_encontra_candidato_e_cria_pending(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, "N2")
        asset = make_asset(db_session, ticker="CHA2")
        existing = _tx(db_session, account, asset, TransactionSource.IMPORT_CSV)

        response = client.post(
            "/transactions",
            json={
                "account_id": str(account.id),
                "asset_id": str(asset.id),
                "transaction_type": "BUY",
                "quantity": "100",
                "unit_price": "30",
                "gross_amount": "3000",
                "currency_code": "BRL",
                "transaction_date": D,
            },
        )
        new_id = response.json()["id"]

        logs = (
            db_session.query(ReconciliationLog)
            .filter(
                ReconciliationLog.transaction_a_id.in_([existing.id, new_id]),
                ReconciliationLog.transaction_b_id.in_([existing.id, new_id]),
            )
            .all()
        )
        assert len(logs) == 1
        assert logs[0].status == ReconciliationStatus.PENDING

    def test_sem_candidato_nao_cria_log(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, "N3")
        asset = make_asset(db_session, ticker="CHA3")

        client.post(
            "/transactions",
            json={
                "account_id": str(account.id),
                "asset_id": str(asset.id),
                "transaction_type": "BUY",
                "quantity": "100",
                "unit_price": "30",
                "gross_amount": "3000",
                "currency_code": "BRL",
                "transaction_date": D,
            },
        )

        assert db_session.query(ReconciliationLog).count() == 0

    def test_falha_interna_do_matcher_nao_impede_criacao(self, api_client, db_session, monkeypatch):
        from app.services import reconciliation_service

        client, user = api_client
        account = _setup_account(db_session, user, "N4")
        asset = make_asset(db_session, ticker="CHA4")
        _tx(db_session, account, asset, TransactionSource.IMPORT_CSV)
        monkeypatch.setattr(
            reconciliation_service,
            "match",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        response = client.post(
            "/transactions",
            json={
                "account_id": str(account.id),
                "asset_id": str(asset.id),
                "transaction_type": "BUY",
                "quantity": "100",
                "unit_price": "30",
                "gross_amount": "3000",
                "currency_code": "BRL",
                "transaction_date": D,
            },
        )

        assert response.status_code == 201  # a falha da reconciliação não vira erro HTTP
        db_session.expire_all()
        created = db_session.get(Transaction, response.json()["id"])
        assert created is not None
        assert created.status == TransactionStatus.ACTIVE
        assert db_session.query(ReconciliationLog).count() == 0


class TestCorrecaoDisparaReconciliacao:
    def test_correct_cria_nova_transaction(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, "C1")
        asset = make_asset(db_session, ticker="CHC1")
        original = _tx(db_session, account, asset, TransactionSource.MANUAL, qty="10", gross="100")

        response = client.post(
            f"/transactions/{original.id}/correct",
            json={
                "account_id": str(account.id),
                "asset_id": str(asset.id),
                "transaction_type": "BUY",
                "quantity": "12",
                "unit_price": "10",
                "gross_amount": "120",
                "currency_code": "BRL",
                "transaction_date": D,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] != str(original.id)
        db_session.expire_all()
        assert db_session.get(Transaction, original.id).status == TransactionStatus.REVERSED

    def test_nova_transaction_da_correcao_pode_gerar_log(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, "C2")
        asset = make_asset(db_session, ticker="CHC2")
        original = _tx(
            db_session, account, asset, TransactionSource.MANUAL, qty="100", gross="3000"
        )
        candidate = _tx(
            db_session, account, asset, TransactionSource.IMPORT_CSV, qty="100", gross="3000"
        )

        response = client.post(
            f"/transactions/{original.id}/correct",
            json={
                "account_id": str(account.id),
                "asset_id": str(asset.id),
                "transaction_type": "BUY",
                "quantity": "100",
                "unit_price": "30",
                "gross_amount": "3000",
                "currency_code": "BRL",
                "transaction_date": D,
            },
        )
        corrected_id = response.json()["id"]

        logs = (
            db_session.query(ReconciliationLog)
            .filter(
                ReconciliationLog.transaction_a_id.in_([candidate.id, corrected_id]),
                ReconciliationLog.transaction_b_id.in_([candidate.id, corrected_id]),
            )
            .all()
        )
        assert len(logs) == 1

    def test_original_revertida_nao_dispara_checagem_como_se_fosse_nova(
        self, api_client, db_session
    ):
        # A original vira REVERSED e some do escopo do matcher (só olha
        # ACTIVE) -- então ela nunca pode aparecer como um lado de um
        # ReconciliationLog criado por esta correção.
        client, user = api_client
        account = _setup_account(db_session, user, "C3")
        asset = make_asset(db_session, ticker="CHC3")
        original = _tx(
            db_session, account, asset, TransactionSource.MANUAL, qty="100", gross="3000"
        )
        _tx(db_session, account, asset, TransactionSource.IMPORT_CSV, qty="100", gross="3000")

        client.post(
            f"/transactions/{original.id}/correct",
            json={
                "account_id": str(account.id),
                "asset_id": str(asset.id),
                "transaction_type": "BUY",
                "quantity": "100",
                "unit_price": "30",
                "gross_amount": "3000",
                "currency_code": "BRL",
                "transaction_date": D,
            },
        )

        logs_with_original = (
            db_session.query(ReconciliationLog)
            .filter(
                or_(
                    ReconciliationLog.transaction_a_id == original.id,
                    ReconciliationLog.transaction_b_id == original.id,
                )
            )
            .all()
        )
        assert logs_with_original == []
