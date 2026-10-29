"""PUT/GET /performance/allocation: alvos do usuário e o peso atual."""

import uuid
from datetime import date, timedelta

from app.models.enums import AccountType
from tests.api.test_kpis_api import _buy
from tests.cashflow_helpers import make_typed_account
from tests.test_persistence import make_asset, make_institution

TODAY = date.today()


def _setup(client, db, user):
    inst = make_institution(db, name=f"Corretora L {uuid.uuid4().hex[:6]}")
    account = make_typed_account(db, user, inst, "Conta", AccountType.BROKERAGE, "USD")
    tag = uuid.uuid4().hex[:4].upper()
    etf = make_asset(db, f"E{tag}", "ETF_US", "US", "USD")
    bond = make_asset(db, f"B{tag}", "BOND", "US", "USD")
    when = (TODAY - timedelta(days=3)).isoformat()
    _buy(client, account, etf, "3", "100", when)
    _buy(client, account, bond, "1", "100", when)


def test_sem_alvo_mostra_peso_atual(api_client, db_session):
    client, user = api_client
    _setup(client, db_session, user)

    (usd,) = client.get("/performance/allocation").json()["currencies"]

    assert usd["has_targets"] is False
    rows = {r["asset_class"]: r for r in usd["rows"]}
    assert float(rows["ETF_US"]["current_weight"]) == 0.75
    assert rows["ETF_US"]["target_weight"] is None


def test_grava_alvos_e_mostra_o_desvio(api_client, db_session):
    client, user = api_client
    _setup(client, db_session, user)

    body = client.put(
        "/performance/allocation/usd",
        json={
            "targets": [
                {"asset_class_code": "etf_us", "target_weight": "0.6"},
                {"asset_class_code": "BOND", "target_weight": "0.3"},
                {"asset_class_code": "REIT", "target_weight": "0.1"},
            ]
        },
    ).json()

    (usd,) = body["currencies"]
    assert usd["has_targets"] is True
    rows = {r["asset_class"]: r for r in usd["rows"]}
    assert float(rows["ETF_US"]["gap"]) == 0.15
    assert float(rows["ETF_US"]["value_gap"]) == -60
    assert float(rows["REIT"]["value_gap"]) == 40
    assert float(rows["REIT"]["current_weight"]) == 0

    # Trocar substitui tudo; lista vazia apaga.
    client.put(
        "/performance/allocation/USD",
        json={"targets": [{"asset_class_code": "ETF_US", "target_weight": "1"}]},
    )
    rows = {
        r["asset_class"]: r
        for r in client.get("/performance/allocation").json()["currencies"][0]["rows"]
    }
    assert "REIT" not in rows and float(rows["BOND"]["target_weight"]) == 0
    body = client.put("/performance/allocation/USD", json={"targets": []}).json()
    assert body["currencies"][0]["has_targets"] is False


def test_alvos_invalidos_recusados(api_client, db_session):
    client, user = api_client
    _setup(client, db_session, user)
    bad = [
        [{"asset_class_code": "ETF_US", "target_weight": "0.5"}],  # soma 50%
        [
            {"asset_class_code": "ETF_US", "target_weight": "0.5"},
            {"asset_class_code": "ETF_US", "target_weight": "0.5"},
        ],
        # Repetida: a última "valeria" e a soma daria 100% — mesmo assim recusa.
        [
            {"asset_class_code": "ETF_US", "target_weight": "0"},
            {"asset_class_code": "BOND", "target_weight": "0.5"},
            {"asset_class_code": "ETF_US", "target_weight": "0.5"},
        ],
        [{"asset_class_code": "NADA", "target_weight": "1"}],
        [{"asset_class_code": "ETF_US", "target_weight": "1.5"}],
    ]
    for targets in bad:
        response = client.put("/performance/allocation/USD", json={"targets": targets})
        assert response.status_code == 422, targets
    response = client.put(
        "/performance/allocation/XYZ",
        json={"targets": [{"asset_class_code": "ETF_US", "target_weight": "1"}]},
    )
    assert response.status_code == 422
    assert client.get("/performance/allocation").json()["currencies"][0]["has_targets"] is False
