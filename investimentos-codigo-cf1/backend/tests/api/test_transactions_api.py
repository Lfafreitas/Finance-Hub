import uuid

from tests.test_persistence import make_account, make_asset, make_institution, make_user


def _setup_account(db_session, user, name="Conta API"):
    institution = make_institution(db_session, name=f"Inst {name}")
    return make_account(db_session, user, institution, name=name)


class TestCriarTransacao:
    def test_deposito_simples(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Deposito")

        response = client.post(
            "/transactions",
            json={
                "account_id": str(account.id),
                "transaction_type": "DEPOSIT",
                "gross_amount": "1000.00",
                "currency_code": "BRL",
                "transaction_date": "2026-01-01",
            },
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["transaction_type"] == "DEPOSIT"
        assert body["status"] == "ACTIVE"
        assert body["gross_amount"] == "1000.00"

    def test_transfer_types_sao_rejeitados_neste_endpoint(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Transfer Rejeitada")

        response = client.post(
            "/transactions",
            json={
                "account_id": str(account.id),
                "transaction_type": "TRANSFER_OUT",
                "gross_amount": "100.00",
                "currency_code": "BRL",
                "transaction_date": "2026-01-01",
            },
        )
        assert response.status_code == 422  # rejeitado pela validação do schema

    def test_conta_de_outro_usuario_e_rejeitada(self, api_client, db_session):
        client, _user = api_client
        outro_user = make_user(db_session, email="outro-dono@example.com")
        institution = make_institution(db_session, name="Inst De Outro")
        conta_de_outro = make_account(db_session, outro_user, institution, name="Conta De Outro")

        response = client.post(
            "/transactions",
            json={
                "account_id": str(conta_de_outro.id),
                "transaction_type": "DEPOSIT",
                "gross_amount": "50.00",
                "currency_code": "BRL",
                "transaction_date": "2026-01-01",
            },
        )
        assert response.status_code == 404

    def test_conta_inexistente_e_rejeitada(self, api_client):
        client, _user = api_client
        response = client.post(
            "/transactions",
            json={
                "account_id": str(uuid.uuid4()),
                "transaction_type": "DEPOSIT",
                "gross_amount": "50.00",
                "currency_code": "BRL",
                "transaction_date": "2026-01-01",
            },
        )
        assert response.status_code == 404


class TestVendaSuperiorAPosicao:
    def test_sell_maior_que_posicao_e_rejeitado(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Sell Rejeitado")
        asset = make_asset(db_session, ticker="APIT3")

        buy = client.post(
            "/transactions",
            json={
                "account_id": str(account.id),
                "asset_id": str(asset.id),
                "transaction_type": "BUY",
                "quantity": "10",
                "unit_price": "10.00",
                "gross_amount": "100.00",
                "currency_code": "BRL",
                "transaction_date": "2026-01-01",
            },
        )
        assert buy.status_code == 201

        sell = client.post(
            "/transactions",
            json={
                "account_id": str(account.id),
                "asset_id": str(asset.id),
                "transaction_type": "SELL",
                "quantity": "11",
                "unit_price": "12.00",
                "gross_amount": "132.00",
                "currency_code": "BRL",
                "transaction_date": "2026-01-02",
            },
        )
        assert sell.status_code == 400
        assert "excede a posição" in sell.json()["detail"]

    def test_sell_dentro_da_posicao_e_aceito(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Sell Aceito")
        asset = make_asset(db_session, ticker="APIT4")

        client.post(
            "/transactions",
            json={
                "account_id": str(account.id),
                "asset_id": str(asset.id),
                "transaction_type": "BUY",
                "quantity": "10",
                "unit_price": "10.00",
                "gross_amount": "100.00",
                "currency_code": "BRL",
                "transaction_date": "2026-01-01",
            },
        )
        sell = client.post(
            "/transactions",
            json={
                "account_id": str(account.id),
                "asset_id": str(asset.id),
                "transaction_type": "SELL",
                "quantity": "5",
                "unit_price": "12.00",
                "gross_amount": "60.00",
                "currency_code": "BRL",
                "transaction_date": "2026-01-02",
            },
        )
        assert sell.status_code == 201


class TestTransferencia:
    def test_transferencia_atomica_cria_as_duas_pernas_vinculadas(self, api_client, db_session):
        client, user = api_client
        origem = _setup_account(db_session, user, name="Origem Transfer API")
        destino = _setup_account(db_session, user, name="Destino Transfer API")

        response = client.post(
            "/transfers",
            json={
                "from_account_id": str(origem.id),
                "to_account_id": str(destino.id),
                "gross_amount": "500.00",
                "transaction_date": "2026-01-01",
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["transfer_out"]["transaction_type"] == "TRANSFER_OUT"
        assert body["transfer_in"]["transaction_type"] == "TRANSFER_IN"
        assert body["transfer_out"]["linked_transaction_id"] == body["transfer_in"]["id"]
        assert body["transfer_in"]["linked_transaction_id"] == body["transfer_out"]["id"]

    def test_transferencia_mesma_conta_e_rejeitada(self, api_client, db_session):
        client, user = api_client
        conta = _setup_account(db_session, user, name="Conta Unica Transfer")

        response = client.post(
            "/transfers",
            json={
                "from_account_id": str(conta.id),
                "to_account_id": str(conta.id),
                "gross_amount": "100.00",
                "transaction_date": "2026-01-01",
            },
        )
        assert response.status_code == 400
        assert "mesma" in response.json()["detail"]

    def test_transferencia_entre_contas_de_outro_usuario_e_rejeitada(self, api_client, db_session):
        client, user = api_client
        minha_conta = _setup_account(db_session, user, name="Minha Conta Transfer")

        outro_user = make_user(db_session, email="outro-transfer@example.com")
        institution = make_institution(db_session, name="Inst Outro Transfer")
        conta_de_outro = make_account(
            db_session, outro_user, institution, name="Conta De Outro Transfer"
        )

        response = client.post(
            "/transfers",
            json={
                "from_account_id": str(minha_conta.id),
                "to_account_id": str(conta_de_outro.id),
                "gross_amount": "100.00",
                "transaction_date": "2026-01-01",
            },
        )
        assert response.status_code == 404


class TestCorrecao:
    def test_corrige_transacao_estorna_original_e_cria_ajuste(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Correcao API")

        original = client.post(
            "/transactions",
            json={
                "account_id": str(account.id),
                "transaction_type": "DEPOSIT",
                "gross_amount": "100.00",
                "currency_code": "BRL",
                "transaction_date": "2026-01-01",
            },
        ).json()

        correction = client.post(
            f"/transactions/{original['id']}/correct",
            json={
                "account_id": str(account.id),
                "transaction_type": "DEPOSIT",
                "gross_amount": "150.00",
                "currency_code": "BRL",
                "transaction_date": "2026-01-01",
            },
        )
        assert correction.status_code == 200, correction.text
        body = correction.json()
        assert body["gross_amount"] == "150.00"
        assert body["reverses_transaction_id"] == original["id"]

        history = client.get(f"/accounts/{account.id}/transactions").json()
        original_no_historico = next(t for t in history if t["id"] == original["id"])
        assert original_no_historico["status"] == "REVERSED"
        assert original_no_historico["gross_amount"] == "100.0000"  # original intacta

    def test_corrigir_ja_revertida_e_rejeitado(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Dupla Correcao")

        original = client.post(
            "/transactions",
            json={
                "account_id": str(account.id),
                "transaction_type": "DEPOSIT",
                "gross_amount": "100.00",
                "currency_code": "BRL",
                "transaction_date": "2026-01-01",
            },
        ).json()
        client.post(
            f"/transactions/{original['id']}/correct",
            json={
                "account_id": str(account.id),
                "transaction_type": "DEPOSIT",
                "gross_amount": "150.00",
                "currency_code": "BRL",
                "transaction_date": "2026-01-01",
            },
        )

        segunda_tentativa = client.post(
            f"/transactions/{original['id']}/correct",
            json={
                "account_id": str(account.id),
                "transaction_type": "DEPOSIT",
                "gross_amount": "200.00",
                "currency_code": "BRL",
                "transaction_date": "2026-01-01",
            },
        )
        assert segunda_tentativa.status_code == 409


class TestPosicao:
    def test_consulta_posicao_calculada(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Posicao API")
        asset = make_asset(db_session, ticker="APIT5")

        client.post(
            "/transactions",
            json={
                "account_id": str(account.id),
                "asset_id": str(asset.id),
                "transaction_type": "BUY",
                "quantity": "100",
                "unit_price": "10.00",
                "gross_amount": "1000.00",
                "currency_code": "BRL",
                "transaction_date": "2026-01-01",
            },
        )

        response = client.get(f"/accounts/{account.id}/positions/{asset.id}")
        assert response.status_code == 200
        body = response.json()
        assert body["quantity"] == "100.00000000"
        assert body["average_cost"] == "10.00000000"

    def test_posicao_inexistente_devolve_null(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Posicao Vazia")
        asset = make_asset(db_session, ticker="APIT6")

        response = client.get(f"/accounts/{account.id}/positions/{asset.id}")
        assert response.status_code == 200
        assert response.json() is None


class TestCorrecaoQueInvalidaHistorico:
    def test_api_devolve_400_e_nao_altera_nada(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Correcao Historico API")
        asset = make_asset(db_session, ticker="CHAPI")

        def _body(kind, qty, day):
            return {
                "account_id": str(account.id),
                "asset_id": str(asset.id),
                "transaction_type": kind,
                "quantity": qty,
                "unit_price": "10",
                "gross_amount": str(int(qty) * 10),
                "currency_code": "BRL",
                "transaction_date": f"2026-03-0{day}",
            }

        buy = client.post("/transactions", json=_body("BUY", "100", 1)).json()
        assert client.post("/transactions", json=_body("SELL", "80", 5)).status_code == 201

        response = client.post(f"/transactions/{buy['id']}/correct", json=_body("BUY", "50", 1))

        assert response.status_code == 400
        assert "histórico inválido" in response.json()["detail"]
        history = client.get(f"/accounts/{account.id}/transactions").json()
        assert len(history) == 2
        assert {t["status"] for t in history} == {"ACTIVE"}


class TestDadoIncoerenteNaApi:
    def test_buy_com_quantidade_negativa_e_400(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Dado Incoerente API")
        asset = make_asset(db_session, ticker="DIAPI")

        response = client.post(
            "/transactions",
            json={
                "account_id": str(account.id),
                "asset_id": str(asset.id),
                "transaction_type": "BUY",
                "quantity": "-10",
                "unit_price": "5",
                "gross_amount": "50",
                "currency_code": "BRL",
                "transaction_date": "2026-04-01",
            },
        )

        assert response.status_code == 400
        assert "quantity" in response.json()["detail"]
        assert client.get(f"/accounts/{account.id}/transactions").json() == []
