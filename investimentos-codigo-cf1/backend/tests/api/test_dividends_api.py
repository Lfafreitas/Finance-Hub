from datetime import date
from decimal import Decimal

from app.models.enums import TransactionSource, TransactionStatus, TransactionType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction
from tests.test_persistence import make_account, make_asset, make_institution, make_user


def _setup_account(db_session, user, name="Conta Dividends API"):
    institution = make_institution(db_session, name=f"Inst {name}")
    return make_account(db_session, user, institution, name=name)


def _dividend(db, account, asset, amount, day=1, month=1, year=2026, currency="BRL"):
    txn = Transaction(
        account_id=account.id,
        asset_id=asset.id,
        transaction_type=TransactionType.DIVIDEND,
        fees=Decimal(0),
        gross_amount=Decimal(amount),
        currency_code=currency,
        transaction_date=date(year, month, day),
        source=TransactionSource.MANUAL,
    )
    db.add(txn)
    db.flush()
    return txn


class TestDividendsSummaryAPI:
    def test_summary_traz_totais_e_quebra_por_instituicao_real(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Div Inst")
        asset = make_asset(db_session, ticker="DIVAPI1")

        _dividend(db_session, account, asset, "100.00", day=1, month=1)
        _dividend(db_session, account, asset, "50.00", day=1, month=2)

        response = client.get("/dividends/summary")
        assert response.status_code == 200
        body = response.json()

        totals = {t["currency_code"]: t["total_received"] for t in body["totals_by_currency"]}
        assert totals["BRL"] == "150.0000"
        assert body["consolidated_total_received"] == "150.0000"
        assert len(body["by_institution"]) == 1
        assert body["by_institution"][0]["amount"] == "150.0000"
        assert body["predicted"] is None
        assert "calendário de proventos" in body["predicted_unavailable_reason"]

    def test_nao_mistura_proventos_de_outro_usuario(self, api_client, db_session):
        client, _user = api_client
        outro = make_user(db_session, email="outro-dividends@example.com")
        institution = make_institution(db_session, name="Inst Outro Dividends")
        conta_de_outro = make_account(
            db_session, outro, institution, name="Conta De Outro Dividends"
        )
        asset = make_asset(db_session, ticker="DIVAPI2")
        _dividend(db_session, conta_de_outro, asset, "999.00")

        response = client.get("/dividends/summary")
        assert response.status_code == 200
        assert response.json()["totals_by_currency"] == []

    def test_filtro_por_portfolio(self, api_client, db_session):
        client, user = api_client
        portfolio = Portfolio(user_id=user.id, name="Div Portfolio API")
        db_session.add(portfolio)
        db_session.flush()

        conta_dentro = _setup_account(db_session, user, name="Conta Dentro Div Portfolio")
        conta_dentro.portfolio_id = portfolio.id
        conta_fora = _setup_account(db_session, user, name="Conta Fora Div Portfolio")
        db_session.flush()

        asset = make_asset(db_session, ticker="DIVAPI3")
        _dividend(db_session, conta_dentro, asset, "10.00")
        _dividend(db_session, conta_fora, asset, "1000.00")

        response = client.get(f"/dividends/summary?portfolio_id={portfolio.id}")
        assert response.status_code == 200
        body = response.json()
        assert body["totals_by_currency"][0]["total_received"] == "10.0000"

    def test_portfolio_inexistente_e_404(self, api_client):
        client, _user = api_client
        import uuid

        response = client.get(f"/dividends/summary?portfolio_id={uuid.uuid4()}")
        assert response.status_code == 404

    def test_transacao_reversed_nao_entra_no_resumo(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Div Reversed")
        asset = make_asset(db_session, ticker="DIVAPI4")

        _dividend(db_session, account, asset, "100.00", day=1, month=1)
        errado = _dividend(db_session, account, asset, "99999.00", day=2, month=1)
        errado.status = TransactionStatus.REVERSED
        db_session.flush()

        response = client.get("/dividends/summary")
        body = response.json()
        assert body["totals_by_currency"][0]["total_received"] == "100.0000"

    def test_moedas_diferentes_nao_consolida(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Div Moeda Mista")
        asset = make_asset(db_session, ticker="DIVAPI5")

        _dividend(db_session, account, asset, "100.00", currency="BRL")
        _dividend(db_session, account, asset, "50.00", currency="USD")

        response = client.get("/dividends/summary")
        body = response.json()
        assert body["consolidated_total_received"] is None
        assert "BRL" in body["consolidation_unavailable_reason"]
        assert "USD" in body["consolidation_unavailable_reason"]
