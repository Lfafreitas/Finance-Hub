"""Painel-1: revisão do que falta classificar — pela API."""

import uuid
from datetime import date, timedelta

import pytest

from app.models.enums import AccountType
from tests.cashflow_helpers import make_typed_account
from tests.test_persistence import make_institution, make_user

TODAY = date.today()


@pytest.fixture()
def r(api_client, db_session):
    client, user = api_client
    inst = make_institution(db_session, name=f"Banco Rev {uuid.uuid4().hex[:6]}")
    checking = make_typed_account(db_session, user, inst, "Conta", AccountType.CHECKING)
    savings = make_typed_account(db_session, user, inst, "Reserva", AccountType.SAVINGS)

    def entry(description, amount, days_ago=1, nature="UNCLASSIFIED"):
        response = client.post(
            "/cashflow/entries",
            json={
                "account_id": str(checking.id),
                "entry_date": (TODAY - timedelta(days=days_ago)).isoformat(),
                "amount": amount,
                "description": description,
                "nature": nature,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    return {
        "client": client,
        "entry": entry,
        "checking": checking,
        "savings": savings,
        "inst": inst,
    }


class TestGrupos:
    def test_pendentes_juntos_pelo_texto_com_sugestao_do_historico(self, r):
        client = r["client"]
        transport = client.post("/cashflow/categories", json={"name": "Transporte"}).json()
        old = r["entry"]("Transferência enviada pelo Pix - Uber - 17.895.646/0001-87", "-20", 40)
        client.put(
            f"/cashflow/entries/{old['id']}/classification",
            json={"nature": "EXPENSE", "category_id": transport["id"]},
        )
        a = r["entry"]("Transferência enviada pelo Pix - Uber - 17.895.646/0001-87", "-12.45", 2)
        b = r["entry"]("Transferência enviada pelo Pix - Uber - 17.895.646/0001-87", "-16.89", 1)
        r["entry"]("Compra no débito - Padaria", "-9.00", 3)

        body = client.get("/cashflow/pending/groups").json()

        assert body["pending_entries"] == 3
        assert body["pending_groups"] == 2
        uber = body["groups"][0]
        assert uber["match_text"] == "transferencia enviada pelo pix uber"
        assert uber["count"] == 2
        assert uber["total"] == "-29.3400"
        assert uber["entry_ids"] == [b["id"], a["id"]]
        assert [p["id"] for p in uber["preview"]] == [b["id"], a["id"]]
        assert uber["suggestion"] == {
            "nature": "EXPENSE",
            "category_id": transport["id"],
            "evidence": 1,
            "share": "1.0000",
        }
        assert body["groups"][1]["suggestion"] is None

    def test_limite_corta_a_lista_mas_nao_a_contagem(self, r):
        for name in ("A", "B", "C"):
            r["entry"](f"Compra no débito - Loja {name}", "-1")

        body = r["client"].get("/cashflow/pending/groups?limit=2").json()

        assert body["pending_groups"] == 3
        assert len(body["groups"]) == 2

    def test_sem_conta_de_caixa_lista_vazia(self, api_client):
        client, _user = api_client

        assert client.get("/cashflow/pending/groups").json() == {
            "pending_entries": 0,
            "pending_groups": 0,
            "groups": [],
        }


class TestLote:
    def test_classifica_todos_de_uma_vez(self, r):
        client = r["client"]
        food = client.post("/cashflow/categories", json={"name": "Alimentação"}).json()
        ids = [r["entry"](f"Padaria {i}", "-5")["id"] for i in range(3)]

        response = client.post(
            "/cashflow/entries/classify-batch",
            json={"entry_ids": ids, "nature": "EXPENSE", "category_id": food["id"]},
        )

        assert response.status_code == 200, response.text
        assert response.json() == {"classified": 3}
        for entry_id in ids:
            body = client.get(f"/cashflow/entries/{entry_id}").json()
            assert (body["nature"], body["category_id"]) == ("EXPENSE", food["id"])
            assert body["classified_by_rule_id"] is None
        assert client.get("/cashflow/pending/groups").json()["pending_entries"] == 0

    def test_tudo_ou_nada(self, r, db_session):
        client = r["client"]
        good = r["entry"]("Padaria", "-5")["id"]
        stranger = make_user(db_session, email=f"rev-{uuid.uuid4().hex[:6]}@cf.example.com")
        other = make_typed_account(db_session, stranger, r["inst"], "Dele", AccountType.CHECKING)
        from tests.api.test_cashflow_edit_api import _imported

        foreign = _imported(db_session, other)

        response = client.post(
            "/cashflow/entries/classify-batch",
            json={"entry_ids": [good, str(foreign.id)], "nature": "EXPENSE"},
        )

        assert response.status_code == 404
        assert client.get(f"/cashflow/entries/{good}").json()["nature"] == "UNCLASSIFIED"

    def test_transferencia_e_nao_classificado_sao_recusados(self, r):
        client = r["client"]
        entry = r["entry"]("Padaria", "-5")["id"]

        for nature in ("TRANSFER", "UNCLASSIFIED"):
            response = client.post(
                "/cashflow/entries/classify-batch",
                json={"entry_ids": [entry], "nature": nature},
            )
            assert response.status_code == 400

    def test_lista_vazia_e_recusada(self, r):
        response = r["client"].post(
            "/cashflow/entries/classify-batch", json={"entry_ids": [], "nature": "EXPENSE"}
        )

        assert response.status_code == 422
