"""Moeda-3 pela API: criação manual, correção e o caso do CSV sem a
coluna `moeda` (assume BRL) para um ativo cadastrado em USD.
"""

from tests.test_persistence import make_account, make_asset, make_institution


def _setup_account(db_session, user, name):
    return make_account(db_session, user, make_institution(db_session, name=f"Inst {name}"), name)


def _body(account, asset, currency):
    return {
        "account_id": str(account.id),
        "asset_id": str(asset.id),
        "transaction_type": "BUY",
        "quantity": "10",
        "unit_price": "100",
        "gross_amount": "1000",
        "currency_code": currency,
        "transaction_date": "2026-01-05",
    }


def _preview(client, account, csv_content):
    return client.post(
        "/imports/preview",
        data={"account_id": str(account.id), "source_format": "CSV"},
        files={"file": ("extrato.csv", csv_content, "text/csv")},
    ).json()


def _commit(client, preview):
    return client.post(
        "/imports/commit",
        json={
            "account_id": preview["account_id"],
            "source_format": preview["source_format"],
            "rows": preview["rows"],
            "signature": preview["signature"],
            "included_row_indexes": [row["row_index"] for row in preview["rows"]],
        },
    )


class TestApiManual:
    def test_criacao_com_moeda_diferente_do_ativo_e_400_com_mensagem_clara(
        self, api_client, db_session
    ):
        client, user = api_client
        account = _setup_account(db_session, user, "Conta M3 API")
        usd = make_asset(db_session, ticker="M3APIUS", country="US", currency_code="USD")

        response = client.post("/transactions", json=_body(account, usd, "BRL"))

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "BRL" in detail and "USD" in detail and "M3APIUS" in detail
        assert client.get(f"/accounts/{account.id}/transactions").json() == []

    def test_correcao_com_moeda_diferente_do_ativo_e_400(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, "Conta M3 API Correcao")
        usd = make_asset(db_session, ticker="M3APIUS2", country="US", currency_code="USD")
        original = client.post("/transactions", json=_body(account, usd, "USD")).json()

        response = client.post(
            f"/transactions/{original['id']}/correct", json=_body(account, usd, "BRL")
        )

        assert response.status_code == 400
        history = client.get(f"/accounts/{account.id}/transactions").json()
        assert [t["status"] for t in history] == ["ACTIVE"]


class TestCsvSemColunaMoeda:
    CSV_SEM_MOEDA = (
        b"data,tipo,ativo,quantidade,preco_unitario,taxas,valor\n"
        b"2026-01-05,COMPRA,M3CSVUS,10,100,0,1000\n"
    )

    def test_csv_sem_moeda_continua_assumindo_brl(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, "Conta M3 CSV Padrao")
        make_asset(db_session, ticker="M3CSVUS", country="US", currency_code="USD")

        preview = _preview(client, account, self.CSV_SEM_MOEDA)

        assert preview["rows"][0]["currency_code"] == "BRL"

    def test_csv_sem_moeda_para_ativo_usd_e_rejeitado_no_commit_e_nada_e_gravado(
        self, api_client, db_session
    ):
        """Antes da Moeda-3 isto gravava US$ 1.000 como R$ 1.000."""
        client, user = api_client
        account = _setup_account(db_session, user, "Conta M3 CSV")
        make_asset(db_session, ticker="M3CSVUS", country="US", currency_code="USD")
        preview = _preview(client, account, self.CSV_SEM_MOEDA)

        commit = _commit(client, preview)

        assert commit.status_code == 422
        assert "BRL" in commit.json()["detail"] and "USD" in commit.json()["detail"]
        assert client.get(f"/accounts/{account.id}/transactions").json() == []

    def test_lote_inteiro_e_rejeitado_se_uma_linha_tem_moeda_errada(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, "Conta M3 CSV Lote")
        make_asset(db_session, ticker="M3CSVBR")
        make_asset(db_session, ticker="M3CSVUS", country="US", currency_code="USD")
        csv_content = (
            b"data,tipo,ativo,quantidade,preco_unitario,taxas,valor\n"
            b"2026-01-05,COMPRA,M3CSVBR,10,10,0,100\n"
            b"2026-01-06,COMPRA,M3CSVUS,10,100,0,1000\n"
        )

        commit = _commit(client, _preview(client, account, csv_content))

        assert commit.status_code == 422
        assert client.get(f"/accounts/{account.id}/transactions").json() == []

    def test_csv_com_moeda_usd_para_ativo_usd_e_aceito(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, "Conta M3 CSV USD")
        make_asset(db_session, ticker="M3CSVUS", country="US", currency_code="USD")
        csv_content = (
            b"data,tipo,ativo,quantidade,preco_unitario,taxas,valor,moeda\n"
            b"2026-01-05,COMPRA,M3CSVUS,10,100,0,1000,USD\n"
        )

        commit = _commit(client, _preview(client, account, csv_content))

        assert commit.status_code == 200, commit.text
        history = client.get(f"/accounts/{account.id}/transactions").json()
        assert [(t["transaction_type"], t["currency_code"]) for t in history] == [("BUY", "USD")]


class TestAvisoJaNaPreview:
    def test_preview_marca_a_linha_com_moeda_diferente_do_ativo(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, "Conta M3 Preview")
        make_asset(db_session, ticker="M3CSVUS", country="US", currency_code="USD")

        row = _preview(client, account, TestCsvSemColunaMoeda.CSV_SEM_MOEDA)["rows"][0]

        assert row["currency_code"] == "BRL"  # a regra de assumir BRL não mudou
        assert "BRL" in row["error"] and "USD" in row["error"] and "M3CSVUS" in row["error"]

    def test_linha_na_moeda_certa_nao_tem_erro(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, "Conta M3 Preview OK")
        make_asset(db_session, ticker="M3CSVBR")
        csv_content = (
            b"data,tipo,ativo,quantidade,preco_unitario,taxas,valor\n"
            b"2026-01-05,COMPRA,M3CSVBR,10,10,0,100\n"
        )

        row = _preview(client, account, csv_content)["rows"][0]

        assert row["error"] is None
        assert row["asset_id"] is not None

    def test_ticker_que_existe_em_dois_paises_nao_e_resolvido_em_silencio(
        self, api_client, db_session
    ):
        client, user = api_client
        account = _setup_account(db_session, user, "Conta M3 Ambiguo")
        make_asset(db_session, ticker="M3DUAL")
        make_asset(db_session, ticker="M3DUAL", country="US", currency_code="USD")
        csv_content = (
            b"data,tipo,ativo,quantidade,preco_unitario,taxas,valor\n"
            b"2026-01-05,COMPRA,M3DUAL,10,10,0,100\n"
        )

        preview = _preview(client, account, csv_content)
        row = preview["rows"][0]

        assert row["asset_id"] is None
        assert "mais de um país" in row["error"]
        assert _commit(client, preview).status_code == 422
        assert client.get(f"/accounts/{account.id}/transactions").json() == []
