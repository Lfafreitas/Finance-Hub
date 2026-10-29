"""Fase 12: cotações manuais."""

import uuid
from datetime import date, timedelta

from app.models.asset_price import AssetPrice
from tests.test_persistence import make_asset

TODAY = date.today()
YESTERDAY = (TODAY - timedelta(days=1)).isoformat()


def _put(client, asset, price, price_date=YESTERDAY):
    return client.put(f"/assets/{asset.id}/prices", json={"price_date": price_date, "price": price})


class TestInformarCotacao:
    def test_grava_na_moeda_do_ativo_com_fonte_manual(self, api_client, db_session):
        client, _user = api_client
        asset = make_asset(db_session, ticker="PRCUS", country="US", currency_code="USD")

        response = _put(client, asset, "187.4567")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["currency_code"] == "USD"
        assert body["source"] == "MANUAL"
        assert body["price"] == "187.4567"
        assert body["price_date"] == YESTERDAY

    def test_mesma_data_substitui_em_vez_de_duplicar(self, api_client, db_session):
        client, _user = api_client
        asset = make_asset(db_session, ticker="PRCUP")
        first = _put(client, asset, "30").json()

        second = _put(client, asset, "31.5").json()

        assert second["id"] == first["id"]
        assert second["price"] == "31.5"
        assert db_session.query(AssetPrice).filter_by(asset_id=asset.id).count() == 1

    def test_datas_diferentes_formam_historico_mais_recente_primeiro(self, api_client, db_session):
        client, _user = api_client
        asset = make_asset(db_session, ticker="PRCHIST")
        older = (TODAY - timedelta(days=10)).isoformat()
        _put(client, asset, "28", older)
        _put(client, asset, "30", YESTERDAY)

        history = client.get(f"/assets/{asset.id}/prices").json()

        assert [(h["price_date"], h["price"]) for h in history] == [
            (YESTERDAY, "30.00000000"),
            (older, "28.00000000"),
        ]

    def test_preco_nao_positivo_e_400(self, api_client, db_session):
        client, _user = api_client
        asset = make_asset(db_session, ticker="PRCNEG")

        assert _put(client, asset, "0").status_code == 400
        assert _put(client, asset, "-5").status_code == 400
        assert db_session.query(AssetPrice).filter_by(asset_id=asset.id).count() == 0

    def test_data_futura_e_400(self, api_client, db_session):
        client, _user = api_client
        asset = make_asset(db_session, ticker="PRCFUT")

        response = _put(client, asset, "10", (TODAY + timedelta(days=1)).isoformat())

        assert response.status_code == 400
        assert "futuro" in response.json()["detail"]

    def test_hoje_e_aceito(self, api_client, db_session):
        client, _user = api_client
        asset = make_asset(db_session, ticker="PRCHOJE")

        assert _put(client, asset, "10", TODAY.isoformat()).status_code == 200

    def test_ativo_inexistente_e_404(self, api_client):
        client, _user = api_client

        put = client.put(
            f"/assets/{uuid.uuid4()}/prices", json={"price_date": YESTERDAY, "price": "1"}
        )
        get = client.get(f"/assets/{uuid.uuid4()}/prices")

        assert put.status_code == 404
        assert get.status_code == 404


class TestUltimasCotacoes:
    def test_lista_todo_ativo_com_a_cotacao_mais_recente_ou_nulo(self, api_client, db_session):
        client, _user = api_client
        com = make_asset(db_session, ticker="PRCLATA")
        sem = make_asset(db_session, ticker="PRCLATB")
        _put(client, com, "28", (TODAY - timedelta(days=10)).isoformat())
        _put(client, com, "30", YESTERDAY)

        latest = {item["asset_ticker"]: item for item in client.get("/prices/latest").json()}

        assert latest["PRCLATA"]["price"] == "30.00000000"
        assert latest["PRCLATA"]["price_date"] == YESTERDAY
        assert latest["PRCLATA"]["currency_code"] == "BRL"
        assert latest["PRCLATA"]["asset_id"] == str(com.id)
        assert latest["PRCLATB"]["price"] is None
        assert latest["PRCLATB"]["price_date"] is None
        assert latest["PRCLATB"]["asset_id"] == str(sem.id)
