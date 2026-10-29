"""CF-1: API do livro de caixa e a separação dos dois livros."""

import uuid
from datetime import date, timedelta

import pytest

from app.models.enums import AccountType
from tests.cashflow_helpers import make_typed_account
from tests.test_persistence import make_institution, make_user

TODAY = date.today()
D1 = (TODAY - timedelta(days=3)).isoformat()
D2 = (TODAY - timedelta(days=2)).isoformat()
D3 = (TODAY - timedelta(days=1)).isoformat()


@pytest.fixture()
def ledger(api_client, db_session):
    client, user = api_client
    inst = make_institution(db_session, name=f"Banco API {uuid.uuid4().hex[:6]}")

    def account(name, account_type, currency="BRL"):
        return make_typed_account(db_session, user, inst, name, account_type, currency)

    return {
        "client": client,
        "user": user,
        "inst": inst,
        "account": account,
        "checking": account("Corrente", AccountType.CHECKING),
        "savings": account("Reserva", AccountType.SAVINGS),
        "card": account("Cartão", AccountType.CREDIT_CARD),
        "brokerage": account("Corretora", AccountType.BROKERAGE),
    }


def _post_entry(client, account, amount, when=D1, **extra):
    body = {
        "account_id": str(account.id),
        "entry_date": when,
        "amount": amount,
        "description": "lançamento",
    }
    body.update(extra)
    return client.post("/cashflow/entries", json=body)


def _post_transfer(client, source, target, amount, when=D2):
    return client.post(
        "/cashflow/transfers",
        json={
            "from_account_id": str(source.id),
            "to_account_id": str(target.id),
            "entry_date": when,
            "amount": amount,
            "description": "transferência",
        },
    )


class TestLancamentos:
    def test_cria_e_le_de_volta(self, ledger):
        client = ledger["client"]

        created = _post_entry(client, ledger["checking"], "-45.90", nature="EXPENSE")

        assert created.status_code == 201, created.text
        body = created.json()
        assert body["amount"] == "-45.9000"
        assert body["currency_code"] == "BRL"
        assert body["nature"] == "EXPENSE"
        assert body["source"] == "MANUAL"
        assert body["status"] == "ACTIVE"
        assert body["counterparty_account_id"] is None
        assert client.get(f"/cashflow/entries/{body['id']}").json() == body

    def test_moeda_e_usuario_do_cliente_sao_ignorados(self, ledger, db_session):
        client = ledger["client"]
        stranger = make_user(db_session, email="api-stranger@cf.example.com")

        body = _post_entry(
            client, ledger["checking"], "10", currency_code="USD", user_id=str(stranger.id)
        ).json()

        assert body["currency_code"] == "BRL"
        assert body["account_id"] == str(ledger["checking"].id)

    def test_erros_de_regra_sao_400_e_conta_inexistente_404(self, ledger):
        client = ledger["client"]
        tomorrow = (TODAY + timedelta(days=1)).isoformat()

        assert _post_entry(client, ledger["checking"], "0").status_code == 400
        assert _post_entry(client, ledger["checking"], "-1", when=tomorrow).status_code == 400
        assert _post_entry(client, ledger["brokerage"], "-1").status_code == 400
        assert _post_entry(client, ledger["checking"], "-1", nature="TRANSFER").status_code == 400
        missing = client.post(
            "/cashflow/entries",
            json={
                "account_id": str(uuid.uuid4()),
                "entry_date": D1,
                "amount": "-1",
                "description": "x",
            },
        )
        assert missing.status_code == 404

    def test_corpo_invalido_e_422(self, ledger):
        client = ledger["client"]

        assert _post_entry(client, ledger["checking"], "-1", description="   ").status_code == 422
        assert _post_entry(client, ledger["checking"], "-1.23456").status_code == 422
        assert _post_entry(client, ledger["checking"], "-1", nature="GASTO").status_code == 422

    def test_classificar_e_estornar(self, ledger):
        client = ledger["client"]
        entry = _post_entry(client, ledger["checking"], "250").json()

        classified = client.put(
            f"/cashflow/entries/{entry['id']}/nature", json={"nature": "THIRD_PARTY"}
        )
        reversed_once = client.post(f"/cashflow/entries/{entry['id']}/reverse")
        reversed_twice = client.post(f"/cashflow/entries/{entry['id']}/reverse")

        assert classified.status_code == 200
        assert classified.json()["nature"] == "THIRD_PARTY"
        assert [e["status"] for e in reversed_once.json()] == ["REVERSED"]
        assert reversed_twice.status_code == 409
        assert client.get("/cashflow/entries").json() == []
        assert len(client.get("/cashflow/entries?include_reversed=true").json()) == 1

    def test_lancamento_inexistente_e_404(self, ledger):
        client = ledger["client"]
        ghost = uuid.uuid4()

        assert client.get(f"/cashflow/entries/{ghost}").status_code == 404
        assert client.post(f"/cashflow/entries/{ghost}/reverse").status_code == 404
        assert (
            client.put(f"/cashflow/entries/{ghost}/nature", json={"nature": "INCOME"}).status_code
            == 404
        )


class TestTransferencias:
    def test_entre_contas_de_caixa_devolve_as_duas_pernas(self, ledger):
        response = _post_transfer(ledger["client"], ledger["checking"], ledger["savings"], "500")

        assert response.status_code == 201, response.text
        body = response.json()
        amounts = sorted(e["amount"] for e in body["entries"])
        assert amounts == ["-500.0000", "500.0000"]
        assert {e["transfer_group_id"] for e in body["entries"]} == {body["transfer_group_id"]}

    def test_aporte_devolve_uma_perna(self, ledger):
        body = _post_transfer(
            ledger["client"], ledger["checking"], ledger["brokerage"], "700"
        ).json()

        assert [(e["account_id"], e["amount"]) for e in body["entries"]] == [
            (str(ledger["checking"].id), "-700.0000")
        ]

    def test_erros_de_transferencia(self, ledger):
        client = ledger["client"]
        usd = ledger["account"]("Conta USD", AccountType.CHECKING, "USD")
        other_brokerage = ledger["account"]("Corretora 2", AccountType.BROKERAGE)

        assert (
            _post_transfer(client, ledger["checking"], ledger["checking"], "1").status_code == 400
        )
        assert _post_transfer(client, ledger["checking"], usd, "1").status_code == 400
        assert _post_transfer(client, ledger["checking"], ledger["savings"], "0").status_code == 400
        assert _post_transfer(client, ledger["brokerage"], other_brokerage, "1").status_code == 400
        assert client.get("/cashflow/entries").json() == []


class TestResumoESaldos:
    def test_resumo_e_saldos_do_periodo(self, ledger):
        client = ledger["client"]
        _post_entry(client, ledger["checking"], "3000", nature="INCOME")
        _post_entry(client, ledger["checking"], "-400", nature="EXPENSE")
        _post_entry(client, ledger["card"], "-600", when=D2, nature="EXPENSE")
        _post_transfer(client, ledger["checking"], ledger["card"], "300", when=D3)
        _post_transfer(client, ledger["checking"], ledger["brokerage"], "700", when=D3)

        summary = client.get(f"/cashflow/summary?start={D1}&end={D3}")
        balances = client.get(f"/cashflow/balances?as_of={D3}")

        assert summary.status_code == 200, summary.text
        assert summary.json() == {
            "start": D1,
            "end": D3,
            "totals_by_currency": [
                {
                    "currency_code": "BRL",
                    "entry_count": 6,
                    "income": "3000.0000",
                    "third_party_net": "0.0000",
                    "adjustments_net": "0.0000",
                    "unclassified_net": "0.0000",
                    "internal_transfers_net": "0.0000",
                    "expenses": "1000.0000",
                    "net_invested": "700.0000",
                    "liquid_variation": "1600.0000",
                    "reserve_variation": "0.0000",
                    "card_balance_variation": "-300.0000",
                }
            ],
        }
        body = balances.json()
        assert {a["account_name"]: a["balance"] for a in body["accounts"]} == {
            "Cartão": "-300.0000",
            "Corrente": "1600.0000",
            "Reserva": "0.0000",
        }
        assert body["totals_by_currency"] == [
            {
                "currency_code": "BRL",
                "liquid": "1600.0000",
                "reserve": "0.0000",
                "card": "-300.0000",
            }
        ]

    def test_resumo_sem_lancamentos_nao_inventa_moeda(self, ledger):
        body = ledger["client"].get(f"/cashflow/summary?start={D1}&end={D3}").json()

        assert body["totals_by_currency"] == []

    def test_periodo_invertido_e_400_e_sem_periodo_e_422(self, ledger):
        client = ledger["client"]

        assert client.get(f"/cashflow/summary?start={D3}&end={D1}").status_code == 400
        assert client.get("/cashflow/summary").status_code == 422


class TestLivrosSeparadosNaApi:
    def test_conta_e_criada_com_tipo_e_lista_devolve_o_tipo(self, ledger):
        client = ledger["client"]

        created = client.post(
            "/accounts",
            json={
                "name": "Carteira física",
                "institution_id": str(ledger["inst"].id),
                "currency_code": "BRL",
                "account_type": "CASH",
            },
        )
        default = client.post(
            "/accounts",
            json={
                "name": "Sem tipo",
                "institution_id": str(ledger["inst"].id),
                "currency_code": "BRL",
            },
        )

        assert created.status_code == 201, created.text
        assert created.json()["account_type"] == "CASH"
        assert default.json()["account_type"] == "BROKERAGE"
        listed = {a["name"]: a["account_type"] for a in client.get("/accounts").json()}
        assert listed["Carteira física"] == "CASH"
        assert listed["Cartão"] == "CREDIT_CARD"

    def test_tipo_invalido_e_422(self, ledger):
        response = ledger["client"].post(
            "/accounts",
            json={
                "name": "Tipo errado",
                "institution_id": str(ledger["inst"].id),
                "currency_code": "BRL",
                "account_type": "POUPANCA",
            },
        )

        assert response.status_code == 422

    def test_carteira_de_investimentos_nao_vincula_conta_de_caixa(self, ledger):
        client = ledger["client"]
        portfolio = client.post("/portfolios", json={"name": "Carteira CF"}).json()

        response = client.post(
            "/accounts",
            json={
                "name": "Corrente com carteira",
                "institution_id": str(ledger["inst"].id),
                "currency_code": "BRL",
                "account_type": "CHECKING",
                "portfolio_id": portfolio["id"],
            },
        )

        assert response.status_code == 400
        assert "investimentos" in response.json()["detail"]

    def test_transaction_em_conta_de_caixa_e_400(self, ledger):
        response = ledger["client"].post(
            "/transactions",
            json={
                "account_id": str(ledger["checking"].id),
                "transaction_type": "DEPOSIT",
                "gross_amount": "100",
                "currency_code": "BRL",
                "transaction_date": D1,
            },
        )

        assert response.status_code == 400
        assert "controle financeiro" in response.json()["detail"]

    def test_transferencia_de_investimento_com_conta_de_caixa_e_400(self, ledger):
        response = ledger["client"].post(
            "/transfers",
            json={
                "from_account_id": str(ledger["brokerage"].id),
                "to_account_id": str(ledger["checking"].id),
                "gross_amount": "100",
                "transaction_date": D1,
            },
        )

        assert response.status_code == 400

    def test_importacao_de_investimentos_em_conta_de_caixa_e_400(self, ledger):
        csv = b"data,tipo,ticker,quantidade,preco,valor\n2026-01-05,DEPOSITO,,,,100\n"

        response = ledger["client"].post(
            "/imports/preview",
            data={"account_id": str(ledger["checking"].id), "source_format": "csv"},
            files={"file": ("x.csv", csv, "text/csv")},
        )

        assert response.status_code == 400
        assert "controle financeiro" in response.json()["detail"]

    def test_dashboard_de_investimentos_ignora_o_livro_de_caixa(self, ledger):
        client = ledger["client"]
        _post_entry(client, ledger["checking"], "3000", nature="INCOME")

        body = client.get("/dashboard/summary").json()

        assert body["positions"] == []
        assert body["totals_by_currency"] == []
