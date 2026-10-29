"""Agenda: GET /performance/agenda e vencimento/taxa no cadastro do ativo."""

import uuid
from datetime import date, timedelta

from app.models.enums import AccountType
from tests.api.test_kpis_api import _buy
from tests.cashflow_helpers import make_typed_account
from tests.test_persistence import make_asset, make_institution

TODAY = date.today()


def _asset_body(asset, **extra):
    return {
        "ticker": asset.ticker,
        "name": asset.name,
        "asset_class_code": asset.asset_class_code,
        "country": asset.country,
        "currency_code": asset.currency_code,
        **extra,
    }


def test_cadastro_guarda_vencimento_e_taxa_e_edicao_antiga_nao_apaga(api_client, db_session):
    client, _user = api_client
    tag = uuid.uuid4().hex[:5].upper()
    asset = make_asset(db_session, f"CD{tag}", "BOND", "US", "USD")
    maturity = (TODAY + timedelta(days=40)).isoformat()

    body = client.put(
        f"/assets/{asset.id}", json=_asset_body(asset, maturity_date=maturity, annual_rate="0.0385")
    ).json()
    assert body["maturity_date"] == maturity
    assert float(body["annual_rate"]) == 0.0385

    # Tela que não conhece os campos novos: mantém o que estava.
    body = client.put(f"/assets/{asset.id}", json=_asset_body(asset, name="Outro nome")).json()
    assert body["maturity_date"] == maturity and body["name"] == "Outro nome"

    # null apaga.
    body = client.put(f"/assets/{asset.id}", json=_asset_body(asset, maturity_date=None)).json()
    assert body["maturity_date"] is None
    assert float(body["annual_rate"]) == 0.0385


def test_taxa_fora_da_faixa_recusada(api_client, db_session):
    client, _user = api_client
    asset = make_asset(db_session, f"CD{uuid.uuid4().hex[:5].upper()}", "BOND", "US", "USD")

    for rate in ("3.85", "-0.01"):
        response = client.put(f"/assets/{asset.id}", json=_asset_body(asset, annual_rate=rate))
        assert response.status_code == 422, rate


def test_agenda_lista_os_vencimentos_da_carteira(api_client, db_session):
    client, user = api_client
    inst = make_institution(db_session, name=f"Banco A {uuid.uuid4().hex[:6]}")
    account = make_typed_account(db_session, user, inst, "Conta", AccountType.BROKERAGE, "USD")
    tag = uuid.uuid4().hex[:4].upper()
    near = make_asset(db_session, f"CDN{tag}", "BOND", "US", "USD")
    far = make_asset(db_session, f"CDF{tag}", "BOND", "US", "USD")
    blank = make_asset(db_session, f"CDX{tag}", "BOND", "US", "USD")
    etf = make_asset(db_session, f"E{tag}", "ETF_US", "US", "USD")
    near.maturity_date, near.annual_rate = TODAY + timedelta(days=38), 0.0385
    far.maturity_date = TODAY + timedelta(days=52)
    db_session.flush()
    bought = (TODAY - timedelta(days=327)).isoformat()
    for asset in (near, far, blank, etf):
        _buy(client, account, asset, "100", "1", bought)

    body = client.get("/performance/agenda").json()

    assert [m["ticker"] for m in body["maturities"]] == [near.ticker, far.ticker]
    first = body["maturities"][0]
    assert first["days_left"] == 38 and first["currency_code"] == "USD"
    assert float(first["cost"]) == 100
    # 365 dias a 3,85% sobre 100
    assert float(first["estimated_at_maturity"]) == 103.85
    assert body["maturities"][1]["estimated_at_maturity"] is None
    assert body["missing_maturity"] == [blank.ticker]
