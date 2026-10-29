"""Fase 11, unidade backend 2: GET /reconciliation/{id}/comparison."""

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
from app.services import reconciliation_service
from tests.test_persistence import make_account, make_asset, make_institution, make_user

MANUAL = TransactionSource.MANUAL
CSV = TransactionSource.IMPORT_CSV

FIELD_ORDER = [
    "transaction_date",
    "quantity",
    "unit_price",
    "gross_amount",
    "fees",
    "currency_code",
    "fx_rate_to_brl",
]


def _setup_account(db_session, user, name="Conta Comparison"):
    return make_account(
        db_session, user, make_institution(db_session, name=f"Inst {name}"), name=name
    )


def _tx(db, account, asset, source, *, qty="100", price="30", gross="3000", fees="0", day="15"):
    tx = Transaction(
        account_id=account.id,
        asset_id=asset.id,
        transaction_type=TransactionType.BUY,
        quantity=Decimal(qty),
        unit_price=Decimal(price),
        fees=Decimal(fees),
        gross_amount=Decimal(gross),
        currency_code="BRL",
        transaction_date=f"2026-08-{day}",
        source=source,
        status=TransactionStatus.ACTIVE,
    )
    db.add(tx)
    db.flush()
    # Recarrega do banco: é assim que a comparação enxerga a Transaction
    # numa request real (date de verdade, NUMERIC já na escala da coluna).
    db.refresh(tx)
    return tx


def _log(db, user, a, b, reason="motivo guardado no log"):
    first, second = sorted([a.id, b.id])
    log = ReconciliationLog(
        user_id=user.id, transaction_a_id=first, transaction_b_id=second, match_reason=reason
    )
    db.add(log)
    db.flush()
    return log


def _by_field(body):
    return {item["field"]: item for item in body["fields"]}


class TestComparacaoEquivalent:
    def test_par_equivalent(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="CMP1")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _log(db_session, user, a, b)

        response = client.get(f"/reconciliation/{log.id}/comparison")

        assert response.status_code == 200
        body = response.json()
        assert body["reconciliation_id"] == str(log.id)
        assert body["classification"] == "EQUIVALENT"
        assert [item["field"] for item in body["fields"]] == FIELD_ORDER
        assert all(item["equal"] for item in body["fields"])

    def test_valores_numericos_nunca_em_notacao_cientifica(self, api_client, db_session):
        """Diferença zero entre dois NUMERIC(20, 8) é `Decimal("0E-8")`:
        precisa sair como "0.00000000", nunca "0E-8".
        """
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="CMP2")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _log(db_session, user, a, b)

        fields = _by_field(client.get(f"/reconciliation/{log.id}/comparison").json())

        assert fields["quantity"]["absolute_difference"] == "0.00000000"
        assert fields["quantity"]["value_a"] == "100.00000000"
        assert fields["unit_price"]["absolute_difference"] == "0.00000000"
        assert fields["gross_amount"]["absolute_difference"] == "0.0000"
        assert fields["transaction_date"]["absolute_difference"] == "0"
        assert fields["transaction_date"]["relative_difference"] is None
        assert fields["currency_code"]["absolute_difference"] is None

    def test_fx_nulo_em_brl_aparece_como_taxa_implicita_1(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="CMP3")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _log(db_session, user, a, b)

        fx = _by_field(client.get(f"/reconciliation/{log.id}/comparison").json())["fx_rate_to_brl"]

        assert fx["equal"] is True
        assert fx["value_a"] == "1"
        assert fx["value_b"] == "1"


class TestComparacaoDivergent:
    def test_par_divergent_com_multiplos_campos(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="CMP4")
        a = _tx(db_session, account, asset, MANUAL, qty="100", gross="3000", fees="0", day="15")
        b = _tx(db_session, account, asset, CSV, qty="110", gross="3300", fees="4.5", day="16")
        log = _log(db_session, user, a, b)
        # A/B da resposta seguem a ordem canônica do LOG, não a de criação.
        first, second = (a, b) if log.transaction_a_id == a.id else (b, a)

        response = client.get(f"/reconciliation/{log.id}/comparison")

        assert response.status_code == 200
        body = response.json()
        assert body["classification"] == "DIVERGENT"
        fields = _by_field(body)
        differing = {name for name, item in fields.items() if not item["equal"]}
        assert differing == {"transaction_date", "quantity", "gross_amount", "fees"}

        assert fields["transaction_date"]["value_a"] == str(first.transaction_date)
        assert fields["transaction_date"]["value_b"] == str(second.transaction_date)
        assert fields["transaction_date"]["absolute_difference"] == "1"

        assert Decimal(fields["quantity"]["value_a"]) == first.quantity
        assert Decimal(fields["quantity"]["value_b"]) == second.quantity
        assert Decimal(fields["quantity"]["absolute_difference"]) == Decimal(10)
        # Relativa sempre sobre o MAIOR valor absoluto: 10 / 110.
        assert Decimal(fields["quantity"]["relative_difference"]) == Decimal(10) / Decimal(110)

        assert Decimal(fields["gross_amount"]["absolute_difference"]) == Decimal(300)
        assert Decimal(fields["fees"]["absolute_difference"]) == Decimal("4.5")
        assert Decimal(fields["fees"]["relative_difference"]) == Decimal(1)

        assert fields["unit_price"]["equal"] is True
        assert fields["currency_code"]["equal"] is True

    def test_match_reason_e_o_texto_guardado_no_log(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="CMP5")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV, gross="3100")
        log = _log(db_session, user, a, b, reason="TEXTO HISTÓRICO DO LOG")

        body = client.get(f"/reconciliation/{log.id}/comparison").json()

        assert body["match_reason"] == "TEXTO HISTÓRICO DO LOG"
        assert body["classification"] == "DIVERGENT"

    def test_nao_reavalia_candidatura(self, api_client, db_session, monkeypatch):
        """Um par registrado continua comparável mesmo que NÃO passe
        mais por `is_candidate` (aqui: gross a 50% de distância) — e
        `match()` nunca é chamado.
        """
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="CMP6")
        a = _tx(db_session, account, asset, MANUAL, gross="3000")
        b = _tx(db_session, account, asset, CSV, gross="6000")
        log = _log(db_session, user, a, b)

        def _boom(*_args, **_kwargs):
            raise AssertionError("match() não deve ser chamado pela comparação")

        monkeypatch.setattr(reconciliation_service, "match", _boom)

        response = client.get(f"/reconciliation/{log.id}/comparison")

        assert response.status_code == 200
        assert response.json()["classification"] == "DIVERGENT"


class TestOwnershipEExistencia:
    def test_log_inexistente_e_404(self, api_client):
        client, _user = api_client

        response = client.get(f"/reconciliation/{uuid.uuid4()}/comparison")

        assert response.status_code == 404

    def test_log_de_outro_usuario_e_404(self, api_client, db_session):
        client, _user = api_client
        outro = make_user(db_session, email="outro-comparison@example.com")
        account = _setup_account(db_session, outro, name="Conta De Outro Comparison")
        asset = make_asset(db_session, ticker="CMP7")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _log(db_session, outro, a, b)

        response = client.get(f"/reconciliation/{log.id}/comparison")

        assert response.status_code == 404
        assert str(a.id) not in response.text
        assert str(b.id) not in response.text

    def test_id_malformado_e_422(self, api_client):
        client, _user = api_client

        assert client.get("/reconciliation/nao-e-uuid/comparison").status_code == 422


class TestLeituraPuraEQualquerStatus:
    def test_leitura_nao_altera_log_nem_transactions(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="CMP8")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV, gross="3100")
        log = _log(db_session, user, a, b)
        updated_before = log.updated_at

        client.get(f"/reconciliation/{log.id}/comparison")

        db_session.expire_all()
        assert log.status == ReconciliationStatus.PENDING
        assert log.resolved_at is None
        assert log.updated_at == updated_before
        assert a.status == TransactionStatus.ACTIVE
        assert b.status == TransactionStatus.ACTIVE
        assert db_session.query(ReconciliationLog).count() == 1

    def test_funciona_para_log_ja_resolvido_com_merge(self, api_client, db_session):
        """Depois do MERGE uma das Transactions está REVERSED: a
        comparação continua disponível (histórico inspecionável).
        """
        client, user = api_client
        account = _setup_account(db_session, user)
        asset = make_asset(db_session, ticker="CMP9")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _log(db_session, user, a, b)
        merge = client.post(
            f"/reconciliation/{log.id}/resolve",
            json={"decision": "MERGE", "surviving_transaction_id": str(a.id)},
        )
        assert merge.status_code == 200

        response = client.get(f"/reconciliation/{log.id}/comparison")

        assert response.status_code == 200
        assert response.json()["classification"] == "EQUIVALENT"
