from datetime import date
from decimal import Decimal

from app.models.enums import TransactionSource, TransactionStatus, TransactionType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction
from tests.test_persistence import make_account, make_asset, make_institution, make_user


def _setup_account(db_session, user, name="Conta Dashboard API"):
    institution = make_institution(db_session, name=f"Inst {name}")
    return make_account(db_session, user, institution, name=name)


class TestListarContasECarteiras:
    def test_lista_contas_do_usuario_com_nome_da_instituicao(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Lista API")

        response = client.get("/accounts")
        assert response.status_code == 200
        body = response.json()
        assert any(a["id"] == str(account.id) for a in body)
        found = next(a for a in body if a["id"] == str(account.id))
        assert found["institution_name"]

    def test_nao_lista_contas_de_outro_usuario(self, api_client, db_session):
        client, _user = api_client
        outro = make_user(db_session, email="outro-lista@example.com")
        institution = make_institution(db_session, name="Inst Outro Lista")
        conta_de_outro = make_account(db_session, outro, institution, name="Conta De Outro Lista")

        response = client.get("/accounts")
        ids = [a["id"] for a in response.json()]
        assert str(conta_de_outro.id) not in ids

    def test_lista_portfolios_do_usuario(self, api_client, db_session):
        client, user = api_client
        portfolio = Portfolio(user_id=user.id, name="Brasil API")
        db_session.add(portfolio)
        db_session.flush()

        response = client.get("/portfolios")
        assert response.status_code == 200
        names = [p["name"] for p in response.json()]
        assert "Brasil API" in names


class TestDashboardSummaryAPI:
    def test_summary_consolidado_com_dado_de_mercado_null(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Summary API")
        asset = make_asset(db_session, ticker="SUMAPI1")

        client.post(
            "/transactions",
            json={
                "account_id": str(account.id),
                "transaction_type": "DEPOSIT",
                "gross_amount": "1000.00",
                "currency_code": "BRL",
                "transaction_date": "2026-01-01",
            },
        )
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
                "transaction_date": "2026-01-02",
            },
        )

        response = client.get("/dashboard/summary")
        assert response.status_code == 200
        body = response.json()

        assert [block["currency_code"] for block in body["totals_by_currency"]] == ["BRL"]
        brl = body["totals_by_currency"][0]
        assert brl["market_value"] is None
        assert brl["unrealized_pnl"] is None
        assert brl["current_return"] is None
        assert "SUMAPI1" in brl["market_data_unavailable_reason"]
        assert Decimal(brl["total_cost_basis"]) == Decimal("100.0000000000")
        assert len(body["positions"]) == 1
        assert body["positions"][0]["market_value"] is None
        # Fase 8: posição ainda aberta -> xirr/cagr None, mas is_closed presente
        assert body["positions"][0]["is_closed"] is False
        assert body["positions"][0]["xirr"] is None
        assert brl["is_closed"] is False
        assert brl["xirr"] is None

    def test_summary_com_posicao_fechada_traz_xirr(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Summary Fechada API")
        asset = make_asset(db_session, ticker="SUMAPI2")

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
        client.post(
            "/transactions",
            json={
                "account_id": str(account.id),
                "asset_id": str(asset.id),
                "transaction_type": "SELL",
                "quantity": "10",
                "unit_price": "12.00",
                "gross_amount": "120.00",
                "currency_code": "BRL",
                "transaction_date": "2026-06-01",
            },
        )

        response = client.get("/dashboard/summary")
        assert response.status_code == 200
        body = response.json()

        position = body["positions"][0]
        assert position["is_closed"] is True
        assert position["xirr"] is not None
        assert position["realized_cost_basis"] == "100.0000000000000000"
        assert body["totals_by_currency"][0]["is_closed"] is True
        assert body["totals_by_currency"][0]["xirr"] is not None

    def test_summary_filtrado_por_portfolio_inexistente_e_404(self, api_client):
        client, _user = api_client
        import uuid

        response = client.get(f"/dashboard/summary?portfolio_id={uuid.uuid4()}")
        assert response.status_code == 404


class TestDashboardSummaryPorMoedaAPI:
    def _post(self, client, account, asset, kind, currency, qty="10", price="100.00"):
        response = client.post(
            "/transactions",
            json={
                "account_id": str(account.id),
                "asset_id": str(asset.id),
                "transaction_type": kind,
                "quantity": qty,
                "unit_price": price,
                "gross_amount": str(Decimal(qty) * Decimal(price)),
                "currency_code": currency,
                "transaction_date": "2026-01-02",
            },
        )
        assert response.status_code == 201, response.text

    def test_contrato_serializado_separa_brl_e_usd(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Summary Moedas API")
        br = make_asset(db_session, ticker="SUMBR")
        us = make_asset(db_session, ticker="SUMUS", country="US", currency_code="USD")
        self._post(client, account, br, "BUY", "BRL")
        self._post(client, account, us, "BUY", "USD")

        body = client.get("/dashboard/summary").json()

        assert set(body) == {
            "portfolio_id",
            "positions",
            "totals_by_currency",
        }
        assert [b["currency_code"] for b in body["totals_by_currency"]] == ["BRL", "USD"]
        for block in body["totals_by_currency"]:
            assert Decimal(block["total_cost_basis"]) == Decimal(1000)
            assert len(block["allocation"]) == 1
            assert Decimal(block["allocation"][0]["percentage"]) == Decimal(100)
        assert {p["currency_code"] for p in body["positions"]} == {"BRL", "USD"}

    def test_posicao_inconsistente_serializa_nulos_e_motivo(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Summary Mista API")
        asset = make_asset(db_session, ticker="SUMMIX")
        self._post(client, account, asset, "BUY", "BRL")
        # Dado legado: a API não aceita mais moeda diferente da do ativo
        # (Moeda-3), então a segunda Transaction é gravada direto no banco.
        db_session.add(
            Transaction(
                account_id=account.id,
                asset_id=asset.id,
                transaction_type=TransactionType.BUY,
                quantity=Decimal(10),
                unit_price=Decimal(100),
                fees=Decimal(0),
                gross_amount=Decimal(1000),
                currency_code="USD",
                transaction_date=date(2026, 1, 2),
                source=TransactionSource.MANUAL,
                status=TransactionStatus.ACTIVE,
            )
        )
        db_session.flush()

        response = client.get("/dashboard/summary")

        assert response.status_code == 200
        body = response.json()
        assert body["totals_by_currency"] == []
        position = body["positions"][0]
        assert position["currency_code"] is None
        assert "BRL, USD" in position["currency_inconsistency_reason"]
        assert Decimal(position["quantity"]) == Decimal(20)
        assert position["total_cost_basis"] is None
        assert position["average_cost"] is None
        assert position["realized_gain"] is None
        assert position["dividends_received"] is None
        assert position["realized_cost_basis"] is None
