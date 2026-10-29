"""Cadastros: ativos, instituições, contas e carteiras."""

import uuid

from app.models.account import Account
from app.models.asset import Asset
from app.models.portfolio import Portfolio
from tests.test_persistence import make_asset, make_institution, make_user


def _asset_body(**overrides):
    body = {
        "ticker": "regt1",
        "name": "  Ativo de Teste  ",
        "asset_class_code": "stock_us",
        "country": "us",
        "currency_code": "usd",
    }
    body.update(overrides)
    return body


class TestReferencias:
    def test_lista_moedas_e_classes_de_ativo(self, api_client):
        client, _user = api_client

        currencies = client.get("/currencies").json()
        classes = client.get("/asset-classes").json()

        assert {"code": "BRL", "name": "Real brasileiro"} in currencies
        assert "USD" in {c["code"] for c in currencies}
        assert "STOCK_BR" in {c["code"] for c in classes}


class TestAtivos:
    def test_cria_ativo_normalizando_ticker_pais_e_moeda(self, api_client, db_session):
        client, _user = api_client

        response = client.post("/assets", json=_asset_body())

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["ticker"] == "REGT1"
        assert body["name"] == "Ativo de Teste"
        assert body["country"] == "US"
        assert body["currency_code"] == "USD"
        assert body["asset_class_code"] == "STOCK_US"
        assert db_session.get(Asset, uuid.UUID(body["id"])).currency_code == "USD"

    def test_lista_ativos_em_ordem_de_ticker(self, api_client, db_session):
        client, _user = api_client
        make_asset(db_session, ticker="REGZZ")
        make_asset(db_session, ticker="REGAA")

        tickers = [
            a["ticker"] for a in client.get("/assets").json() if a["ticker"].startswith("REG")
        ]

        assert tickers == ["REGAA", "REGZZ"]

    def test_ticker_duplicado_no_mesmo_pais_e_409_e_sessao_segue_utilizavel(self, api_client):
        client, _user = api_client
        assert client.post("/assets", json=_asset_body()).status_code == 201

        response = client.post("/assets", json=_asset_body(name="Outro"))

        assert response.status_code == 409
        assert "REGT1" in response.json()["detail"]
        assert client.post("/assets", json=_asset_body(ticker="REGT2")).status_code == 201

    def test_mesmo_ticker_em_outro_pais_e_aceito(self, api_client):
        client, _user = api_client
        client.post("/assets", json=_asset_body())

        response = client.post(
            "/assets",
            json=_asset_body(country="BR", currency_code="BRL", asset_class_code="BDR"),
        )

        assert response.status_code == 201

    def test_moeda_ou_classe_inexistente_e_400(self, api_client):
        client, _user = api_client

        assert client.post("/assets", json=_asset_body(currency_code="XYZ")).status_code == 400
        assert client.post("/assets", json=_asset_body(asset_class_code="NADA")).status_code == 400

    def test_campos_vazios_sao_422(self, api_client):
        client, _user = api_client

        assert client.post("/assets", json=_asset_body(ticker="   ")).status_code == 422
        assert client.post("/assets", json=_asset_body(country="BRA")).status_code == 422


class TestInstituicoes:
    def test_cria_e_lista(self, api_client):
        client, _user = api_client

        created = client.post(
            "/institutions",
            json={"name": " Corretora Registro ", "institution_type": "BROKER", "country": "br"},
        )

        assert created.status_code == 201
        assert created.json()["name"] == "Corretora Registro"
        assert created.json()["country"] == "BR"
        assert created.json()["id"] in {i["id"] for i in client.get("/institutions").json()}

    def test_tipo_invalido_e_422(self, api_client):
        client, _user = api_client

        response = client.post(
            "/institutions", json={"name": "X", "institution_type": "NADA", "country": "BR"}
        )

        assert response.status_code == 422


class TestCarteirasEContas:
    def test_cria_carteira_e_conta_do_usuario_autenticado(self, api_client, db_session):
        client, user = api_client
        institution = make_institution(db_session, name="Inst Registro Conta")
        portfolio = client.post("/portfolios", json={"name": "Longo Prazo Reg"}).json()

        response = client.post(
            "/accounts",
            json={
                "name": "Conta Registro",
                "institution_id": str(institution.id),
                "currency_code": "usd",
                "portfolio_id": portfolio["id"],
            },
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["institution_name"] == "Inst Registro Conta"
        assert body["currency_code"] == "USD"
        assert body["portfolio_id"] == portfolio["id"]
        account = db_session.get(Account, uuid.UUID(body["id"]))
        assert account.user_id == user.id
        assert db_session.get(Portfolio, uuid.UUID(portfolio["id"])).user_id == user.id
        assert body["id"] in {a["id"] for a in client.get("/accounts").json()}

    def test_user_id_do_cliente_e_ignorado(self, api_client, db_session):
        client, user = api_client
        outro = make_user(db_session, email="outro-registro@example.com")
        institution = make_institution(db_session, name="Inst Registro Dono")

        body = client.post(
            "/accounts",
            json={
                "name": "Conta Dono",
                "institution_id": str(institution.id),
                "currency_code": "BRL",
                "user_id": str(outro.id),
            },
        ).json()

        assert db_session.get(Account, uuid.UUID(body["id"])).user_id == user.id

    def test_conta_em_carteira_de_outro_usuario_e_404(self, api_client, db_session):
        client, _user = api_client
        outro = make_user(db_session, email="outro-registro-2@example.com")
        alheia = Portfolio(user_id=outro.id, name="Carteira Alheia Reg")
        db_session.add(alheia)
        db_session.flush()
        institution = make_institution(db_session, name="Inst Registro Alheia")

        response = client.post(
            "/accounts",
            json={
                "name": "Conta Invasora",
                "institution_id": str(institution.id),
                "currency_code": "BRL",
                "portfolio_id": str(alheia.id),
            },
        )

        assert response.status_code == 404
        assert db_session.query(Account).filter_by(name="Conta Invasora").count() == 0

    def test_instituicao_ou_moeda_inexistente_e_400(self, api_client, db_session):
        client, _user = api_client
        institution = make_institution(db_session, name="Inst Registro Ref")
        base = {"name": "Conta Ref", "institution_id": str(institution.id), "currency_code": "BRL"}

        sem_inst = client.post("/accounts", json={**base, "institution_id": str(uuid.uuid4())})
        sem_moeda = client.post("/accounts", json={**base, "currency_code": "XYZ"})

        assert sem_inst.status_code == 400
        assert sem_moeda.status_code == 400

    def test_conta_e_carteira_duplicadas_sao_409(self, api_client, db_session):
        client, _user = api_client
        institution = make_institution(db_session, name="Inst Registro Dup")
        body = {"name": "Conta Dup", "institution_id": str(institution.id), "currency_code": "BRL"}
        assert client.post("/accounts", json=body).status_code == 201
        assert client.post("/portfolios", json={"name": "Carteira Dup"}).status_code == 201

        assert client.post("/accounts", json=body).status_code == 409
        assert client.post("/portfolios", json={"name": "Carteira Dup"}).status_code == 409
        # A sessão continua utilizável depois do conflito.
        assert client.post("/accounts", json={**body, "name": "Conta Dup 2"}).status_code == 201
