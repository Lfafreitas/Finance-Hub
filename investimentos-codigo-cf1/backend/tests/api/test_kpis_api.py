"""KPIs-1: GET /performance/kpis lê posições e o histórico gravado."""

import json
import uuid
from datetime import date, timedelta

from app.core.config import settings
from app.models.asset_price import AssetPrice
from app.models.enums import AccountType, PriceSource
from tests.cashflow_helpers import make_typed_account
from tests.test_persistence import make_asset, make_institution

TODAY = date.today()


def _trade(client, account, body):
    response = client.post("/transactions", json={"account_id": str(account.id), **body})
    assert response.status_code == 201, response.text


def _buy(client, account, asset, quantity, price, when):
    gross = str(round(float(quantity) * float(price), 2))
    _trade(
        client,
        account,
        {
            "transaction_type": "DEPOSIT",
            "gross_amount": gross,
            "currency_code": "USD",
            "transaction_date": when,
        },
    )
    _trade(
        client,
        account,
        {
            "transaction_type": "BUY",
            "asset_id": str(asset.id),
            "quantity": quantity,
            "unit_price": price,
            "gross_amount": gross,
            "currency_code": "USD",
            "transaction_date": when,
        },
    )


def _series(db, asset, start_price, end_price, days=400):
    for i in range(days):
        day = TODAY - timedelta(days=days - 1 - i)
        price = start_price + (end_price - start_price) * i / (days - 1)
        db.add(
            AssetPrice(
                asset_id=asset.id,
                price_date=day,
                price=round(price, 4),
                currency_code="USD",
                source=PriceSource.YAHOO,
            )
        )
    db.flush()


def test_indicadores_somam_o_ativo_entre_contas_e_medem_o_preco(api_client, db_session):
    client, user = api_client
    inst = make_institution(db_session, name=f"Corretora K {uuid.uuid4().hex[:6]}")
    a = make_typed_account(db_session, user, inst, "Conta A", AccountType.BROKERAGE, "USD")
    b = make_typed_account(db_session, user, inst, "Conta B", AccountType.BROKERAGE, "USD")
    tag = uuid.uuid4().hex[:4].upper()
    qqq = make_asset(db_session, f"Q{tag}", "ETF_US", "US", "USD")
    reit = make_asset(db_session, f"R{tag}", "REIT", "US", "USD")
    when = (TODAY - timedelta(days=30)).isoformat()
    _buy(client, a, qqq, "1", "100", when)
    _buy(client, b, qqq, "1", "100", when)
    _buy(client, a, reit, "2", "50", when)
    _series(db_session, qqq, 80.0, 150.0)
    _series(db_session, reit, 60.0, 45.0)

    body = client.get("/performance/kpis").json()

    (usd,) = body["totals_by_currency"]
    assert usd["currency_code"] == "USD"
    by_ticker = {x["ticker"]: x for x in usd["assets"]}
    q, r = by_ticker[qqq.ticker], by_ticker[reit.ticker]
    assert q["quantity"] == "2.00000000" or float(q["quantity"]) == 2
    assert float(q["cost"]) == 200 and float(q["value"]) == 300
    assert float(r["value"]) == 90
    assert float(q["weight"]) == round(300 / 390, 4)
    assert float(q["return_pct"]) == 0.5
    assert r["asset_class"] == "REIT" and r["asset_class_label"]
    assert float(q["stats"]["return_1y"]) > 0.7  # de ~80 para 150
    assert float(r["stats"]["return_1y"]) < 0
    assert r["stats"]["high_52w"] is not None
    assert usd["top_ticker"] == qqq.ticker
    assert {g["asset_class"] for g in usd["groups"]} == {"ETF_US", "REIT"}
    assert usd["basket"]["tickers"] == sorted([qqq.ticker, reit.ticker])
    assert usd["complete"] is True


def test_carteira_vazia(api_client):
    client, _user = api_client

    body = client.get("/performance/kpis").json()

    assert body["totals_by_currency"] == []


def test_retrato_para_o_claude_leva_os_indicadores(api_client, db_session, tmp_path, monkeypatch):
    client, user = api_client
    monkeypatch.setattr(settings, "insights_dir", tmp_path)
    inst = make_institution(db_session, name=f"Corretora K2 {uuid.uuid4().hex[:6]}")
    account = make_typed_account(db_session, user, inst, "Conta", AccountType.BROKERAGE, "USD")
    asset = make_asset(db_session, f"S{uuid.uuid4().hex[:4].upper()}", "ETF_US", "US", "USD")
    _buy(client, account, asset, "1", "100", (TODAY - timedelta(days=3)).isoformat())
    _series(db_session, asset, 90.0, 110.0)

    assert client.post("/insights/snapshot").status_code == 200

    snapshot = json.loads((tmp_path / "carteira.json").read_text(encoding="utf-8"))
    (usd,) = snapshot["kpis"]["totals_by_currency"]
    assert usd["assets"][0]["ticker"] == asset.ticker
    assert usd["assets"][0]["stats"]["return_1y"] is not None
