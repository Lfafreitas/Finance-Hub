"""Edição-2: excluir com histórico, restaurar e editar lançamentos de caixa."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import CashflowEntry
from app.models.enums import AccountType, CashflowNature, TransactionSource
from tests.cashflow_helpers import make_typed_account
from tests.test_persistence import make_institution, make_user

TODAY = date.today()
D1 = (TODAY - timedelta(days=5)).isoformat()
D2 = (TODAY - timedelta(days=2)).isoformat()
TOMORROW = (TODAY + timedelta(days=1)).isoformat()


@pytest.fixture()
def ledger(api_client, db_session):
    client, user = api_client
    inst = make_institution(db_session, name=f"Banco Edição {uuid.uuid4().hex[:6]}")
    return {
        "client": client,
        "user": user,
        "inst": inst,
        "checking": make_typed_account(db_session, user, inst, "Corrente", AccountType.CHECKING),
        "savings": make_typed_account(db_session, user, inst, "Reserva", AccountType.SAVINGS),
    }


def _entry(client, account, amount="-80.00", when=D1, **extra):
    body = {
        "account_id": str(account.id),
        "entry_date": when,
        "amount": amount,
        "description": "Mercado",
        "nature": "EXPENSE",
    }
    body.update(extra)
    response = client.post("/cashflow/entries", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _balance(client, account) -> Decimal:
    body = client.get("/cashflow/balances").json()
    return next(
        Decimal(a["balance"]) for a in body["accounts"] if a["account_id"] == str(account.id)
    )


def _correct(client, entry_id, **values):
    body = {"entry_date": D2, "amount": "-95.50", "description": "Mercado do mês"}
    body.update(values)
    return client.post(f"/cashflow/entries/{entry_id}/correct", json=body)


def _imported(db_session, account) -> CashflowEntry:
    entry = CashflowEntry(
        account_id=account.id,
        entry_date=date.fromisoformat(D1),
        amount=Decimal("-30.00"),
        currency_code="BRL",
        description="Compra no débito - Padaria",
        source=TransactionSource.IMPORT_OFX,
        external_id=f"fitid-{uuid.uuid4().hex}",
        nature=CashflowNature.UNCLASSIFIED,
    )
    db_session.add(entry)
    db_session.flush()
    return entry


class TestRestaurar:
    def test_excluir_e_restaurar_volta_o_saldo(self, ledger):
        client, checking = ledger["client"], ledger["checking"]
        entry = _entry(client, checking)

        client.post(f"/cashflow/entries/{entry['id']}/reverse")
        assert _balance(client, checking) == Decimal(0)
        restored = client.post(f"/cashflow/entries/{entry['id']}/restore")

        assert restored.status_code == 200, restored.text
        assert [e["status"] for e in restored.json()] == ["ACTIVE"]
        assert _balance(client, checking) == Decimal(-80)

    def test_transferencia_volta_com_as_duas_pontas(self, ledger):
        client = ledger["client"]
        legs = client.post(
            "/cashflow/transfers",
            json={
                "from_account_id": str(ledger["checking"].id),
                "to_account_id": str(ledger["savings"].id),
                "entry_date": D1,
                "amount": "300.00",
                "description": "Guardar",
            },
        ).json()["entries"]
        client.post(f"/cashflow/entries/{legs[0]['id']}/reverse")

        restored = client.post(f"/cashflow/entries/{legs[1]['id']}/restore")

        assert restored.status_code == 200, restored.text
        assert sorted(e["id"] for e in restored.json()) == sorted(leg["id"] for leg in legs)
        assert {e["status"] for e in restored.json()} == {"ACTIVE"}
        assert _balance(client, ledger["savings"]) == Decimal(300)

    def test_lancamento_ativo_nao_e_restaurado(self, ledger):
        client = ledger["client"]
        entry = _entry(client, ledger["checking"])

        response = client.post(f"/cashflow/entries/{entry['id']}/restore")

        assert response.status_code == 409
        assert "não está excluído" in response.json()["detail"]

    def test_versao_antiga_de_uma_edicao_nao_volta(self, ledger):
        client, checking = ledger["client"], ledger["checking"]
        entry = _entry(client, checking)
        _correct(client, entry["id"])

        response = client.post(f"/cashflow/entries/{entry['id']}/restore")

        assert response.status_code == 409
        assert "foi editado" in response.json()["detail"]
        assert _balance(client, checking) == Decimal("-95.5")

    def test_versao_nova_excluida_pode_voltar(self, ledger):
        client, checking = ledger["client"], ledger["checking"]
        entry = _entry(client, checking)
        new = _correct(client, entry["id"]).json()
        client.post(f"/cashflow/entries/{new['id']}/reverse")

        response = client.post(f"/cashflow/entries/{new['id']}/restore")

        assert response.status_code == 200, response.text
        assert _balance(client, checking) == Decimal("-95.5")

    def test_lancamento_de_outro_usuario_nao_existe(self, ledger, db_session):
        stranger = make_user(db_session, email=f"edit-{uuid.uuid4().hex[:6]}@cf.example.com")
        other = make_typed_account(
            db_session, stranger, ledger["inst"], "Dele", AccountType.CHECKING
        )
        foreign = _imported(db_session, other)

        response = ledger["client"].post(f"/cashflow/entries/{foreign.id}/restore")

        assert response.status_code == 404


class TestEditar:
    def test_edicao_exclui_o_original_e_grava_o_novo_ligado_a_ele(self, ledger):
        client, checking = ledger["client"], ledger["checking"]
        entry = _entry(client, checking, notes="feira")

        response = _correct(client, entry["id"])

        assert response.status_code == 200, response.text
        new = response.json()
        assert new["id"] != entry["id"]
        assert new["entry_date"] == D2
        assert new["amount"] == "-95.5000"
        assert new["description"] == "Mercado do mês"
        assert new["corrects_entry_id"] == entry["id"]
        assert new["status"] == "ACTIVE"
        assert new["source"] == "MANUAL"
        assert new["notes"] == "feira"
        old = client.get(f"/cashflow/entries/{entry['id']}").json()
        assert old["status"] == "REVERSED"
        assert old["amount"] == "-80.0000"
        assert _balance(client, checking) == Decimal("-95.5")

    def test_classificacao_vai_junto_e_notas_podem_mudar(self, ledger):
        client = ledger["client"]
        category = client.post("/cashflow/categories", json={"name": "Mercado"}).json()
        tag = client.post("/cashflow/tags", json={"name": "casa"}).json()
        entry = _entry(client, ledger["checking"])
        client.put(
            f"/cashflow/entries/{entry['id']}/classification",
            json={"nature": "EXPENSE", "category_id": category["id"], "tag_ids": [tag["id"]]},
        )

        new = _correct(client, entry["id"], notes="nota nova").json()

        assert new["nature"] == "EXPENSE"
        assert new["category_id"] == category["id"]
        assert new["tag_ids"] == [tag["id"]]
        assert new["notes"] == "nota nova"
        assert new["classified_by_rule_id"] is None

    def test_importado_do_banco_nao_e_editado(self, ledger, db_session):
        imported = _imported(db_session, ledger["checking"])

        response = _correct(ledger["client"], imported.id)

        assert response.status_code == 400
        assert "importado do banco" in response.json()["detail"]

    def test_transferencia_nao_e_editada(self, ledger):
        client = ledger["client"]
        legs = client.post(
            "/cashflow/transfers",
            json={
                "from_account_id": str(ledger["checking"].id),
                "to_account_id": str(ledger["savings"].id),
                "entry_date": D1,
                "amount": "50.00",
                "description": "Guardar",
            },
        ).json()["entries"]

        response = _correct(client, legs[0]["id"], amount="-60.00")

        assert response.status_code == 400
        assert "transferência não é editada" in response.json()["detail"]

    def test_excluido_nao_e_editado(self, ledger):
        client = ledger["client"]
        entry = _entry(client, ledger["checking"])
        client.post(f"/cashflow/entries/{entry['id']}/reverse")

        response = _correct(client, entry["id"])

        assert response.status_code == 409

    @pytest.mark.parametrize(
        ("values", "message"),
        [
            ({"amount": "0"}, "não pode ser zero"),
            ({"entry_date": TOMORROW}, "futuro"),
        ],
    )
    def test_valores_invalidos_nao_mexem_em_nada(self, ledger, values, message):
        client, checking = ledger["client"], ledger["checking"]
        entry = _entry(client, checking)

        response = _correct(client, entry["id"], **values)

        assert response.status_code == 400
        assert message in response.json()["detail"]
        assert client.get(f"/cashflow/entries/{entry['id']}").json()["status"] == "ACTIVE"
        assert _balance(client, checking) == Decimal(-80)

    def test_editado_uma_vez_so(self, ledger):
        client = ledger["client"]
        entry = _entry(client, ledger["checking"])
        _correct(client, entry["id"])

        response = _correct(client, entry["id"])

        assert response.status_code == 409
