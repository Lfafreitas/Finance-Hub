"""Estorno de lançamento de investimento pela API (usado pela tela)."""

import uuid
from datetime import date, timedelta

from app.models.enums import AccountType
from tests.cashflow_helpers import make_typed_account
from tests.test_persistence import make_asset, make_institution, make_user

D1 = (date.today() - timedelta(days=5)).isoformat()
D2 = (date.today() - timedelta(days=4)).isoformat()


def _setup(db, user, name="Conta Estorno"):
    inst = make_institution(db, name=f"Inst Estorno {uuid.uuid4().hex[:6]}")
    return make_typed_account(db, user, inst, name, AccountType.BROKERAGE)


def _trade(client, account, asset, kind, quantity, when=D1):
    response = client.post(
        "/transactions",
        json={
            "account_id": str(account.id),
            "asset_id": str(asset.id),
            "transaction_type": kind,
            "quantity": quantity,
            "unit_price": "10",
            "gross_amount": str(int(quantity) * 10),
            "currency_code": "BRL",
            "transaction_date": when,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestEstornoPelaApi:
    def test_estorna_e_o_lancamento_sai_da_posicao(self, api_client, db_session):
        client, user = api_client
        account = _setup(db_session, user)
        asset = make_asset(db_session, ticker="EST3")
        kept = _trade(client, account, asset, "BUY", "100")
        wrong = _trade(client, account, asset, "BUY", "40", when=D2)

        response = client.post(f"/transactions/{wrong['id']}/reverse")

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "REVERSED"
        assert response.json()["id"] == wrong["id"]
        position = client.get(f"/accounts/{account.id}/positions/{asset.id}").json()
        assert position["quantity"] == "100.00000000"
        history = client.get(f"/accounts/{account.id}/transactions").json()
        assert {t["id"]: t["status"] for t in history} == {
            kept["id"]: "ACTIVE",
            wrong["id"]: "REVERSED",
        }

    def test_estornar_duas_vezes_e_409(self, api_client, db_session):
        client, user = api_client
        account = _setup(db_session, user)
        asset = make_asset(db_session, ticker="EST4")
        buy = _trade(client, account, asset, "BUY", "10")
        client.post(f"/transactions/{buy['id']}/reverse")

        assert client.post(f"/transactions/{buy['id']}/reverse").status_code == 409

    def test_estorno_que_deixaria_venda_sem_posicao_e_400_e_nada_muda(self, api_client, db_session):
        client, user = api_client
        account = _setup(db_session, user)
        asset = make_asset(db_session, ticker="EST5")
        buy = _trade(client, account, asset, "BUY", "100")
        _trade(client, account, asset, "SELL", "80", when=D2)

        response = client.post(f"/transactions/{buy['id']}/reverse")

        assert response.status_code == 400
        assert client.get(f"/transactions/{buy['id']}").json()["status"] == "ACTIVE"

    def test_perna_de_transferencia_nao_e_estornada_sozinha(self, api_client, db_session):
        client, user = api_client
        source = _setup(db_session, user, "Origem Estorno")
        target = _setup(db_session, user, "Destino Estorno")
        transfer = client.post(
            "/transfers",
            json={
                "from_account_id": str(source.id),
                "to_account_id": str(target.id),
                "gross_amount": "100",
                "transaction_date": D1,
            },
        ).json()
        leg_id = transfer["transfer_out"]["id"]

        response = client.post(f"/transactions/{leg_id}/reverse")

        assert response.status_code == 400
        assert "transferência" in response.json()["detail"]

    def test_inexistente_ou_de_outro_usuario_e_404(self, api_client, db_session):
        client, _user = api_client
        stranger = make_user(db_session, email="estorno-stranger@example.com")
        foreign_account = _setup(db_session, stranger, "Alheia Estorno")
        from decimal import Decimal

        from app.models import Transaction
        from app.models.enums import TransactionSource, TransactionType

        foreign = Transaction(
            account_id=foreign_account.id,
            transaction_type=TransactionType.DEPOSIT,
            gross_amount=Decimal(100),
            currency_code="BRL",
            transaction_date=date(2026, 1, 1),
            source=TransactionSource.MANUAL,
        )
        db_session.add(foreign)
        db_session.flush()

        assert client.post(f"/transactions/{uuid.uuid4()}/reverse").status_code == 404
        assert client.post(f"/transactions/{foreign.id}/reverse").status_code == 404
        db_session.refresh(foreign)
        assert foreign.status.value == "ACTIVE"
