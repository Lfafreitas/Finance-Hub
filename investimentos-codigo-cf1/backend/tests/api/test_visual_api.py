"""Visual-1: patrimônio por moeda, mês a mês e onde melhorar — pela API."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.enums import AccountType
from tests.cashflow_helpers import make_typed_account
from tests.test_persistence import make_asset, make_institution

TODAY = date.today()


def _month(back):
    index = TODAY.year * 12 + TODAY.month - 1 - back
    return index // 12, index % 12 + 1


def _day_in(back, day=10):
    y, m = _month(back)
    return min(date(y, m, day), TODAY) if back == 0 else date(y, m, day)


@pytest.fixture()
def w(api_client, db_session):
    client, user = api_client
    inst = make_institution(db_session, name=f"Inst V1 {uuid.uuid4().hex[:6]}")
    acc = {
        "usd": make_typed_account(db_session, user, inst, "Inter US", AccountType.BROKERAGE, "USD"),
        "brl": make_typed_account(db_session, user, inst, "XP BR", AccountType.BROKERAGE, "BRL"),
        "checking": make_typed_account(
            db_session, user, inst, "Conta", AccountType.CHECKING, "BRL"
        ),
        "savings": make_typed_account(
            db_session, user, inst, "Caixinha", AccountType.SAVINGS, "BRL"
        ),
        "card": make_typed_account(
            db_session, user, inst, "Cartão", AccountType.CREDIT_CARD, "BRL"
        ),
    }
    suffix = uuid.uuid4().hex[:4].upper()
    assets = {
        "spy": make_asset(db_session, f"SPY{suffix}", "ETF_US", "US", "USD"),
        "cd": make_asset(db_session, f"CD{suffix}", "BOND", "US", "USD"),
        "aaxj": make_asset(db_session, f"AAXJ{suffix}", "ETF_US", "US", "USD"),
        "tesouro": make_asset(db_session, f"TD{suffix}", "TESOURO_DIRETO", "BR", "BRL"),
    }

    def tx(account, kind, amount, asset=None, qty=None, price=None, currency="USD", when=None):
        body = {
            "account_id": str(acc[account].id),
            "transaction_type": kind,
            "gross_amount": amount,
            "currency_code": currency,
            "transaction_date": (when or TODAY - timedelta(days=20)).isoformat(),
        }
        if asset:
            body.update(asset_id=str(assets[asset].id), quantity=qty, unit_price=price)
        r = client.post("/transactions", json=body)
        assert r.status_code == 201, r.text

    def price(asset, value):
        r = client.put(
            f"/assets/{assets[asset].id}/prices",
            json={"price_date": (TODAY - timedelta(days=1)).isoformat(), "price": value},
        )
        assert r.status_code == 200, r.text

    def entry(
        account, amount, when, description="lançamento", nature="UNCLASSIFIED", category=None
    ):
        r = client.post(
            "/cashflow/entries",
            json={
                "account_id": str(acc[account].id),
                "entry_date": when.isoformat(),
                "amount": amount,
                "description": description,
                "nature": nature,
            },
        )
        assert r.status_code == 201, r.text
        if category:
            client.put(
                f"/cashflow/entries/{r.json()['id']}/classification",
                json={"nature": nature, "category_id": category},
            )
        return r.json()

    return {
        "client": client,
        "acc": acc,
        "assets": assets,
        "tx": tx,
        "price": price,
        "entry": entry,
    }


class TestPatrimonio:
    def test_por_moeda_com_renda_fixa_reserva_e_quanto_rendeu(self, w):
        w["tx"]("usd", "DEPOSIT", "300")
        w["tx"]("usd", "BUY", "200", "spy", "0.25", "800")
        w["tx"]("usd", "BUY", "100", "cd", "100", "1")
        w["price"]("spy", "840")  # 210 → +10
        w["price"]("cd", "1.007")  # 100,70 → +0,70
        w["entry"]("savings", "13200", TODAY, "Saldo inicial", "ADJUSTMENT")
        w["entry"]("checking", "500", TODAY, "Salário", "INCOME")
        w["entry"]("card", "-120", TODAY, "Compra", "EXPENSE")

        body = w["client"].get("/overview").json()

        blocks = {b["currency_code"]: b for b in body["totals_by_currency"]}
        assert set(blocks) == {"BRL", "USD"}
        usd = blocks["USD"]
        assert Decimal(usd["investments_value"]) == Decimal("310.70")
        assert Decimal(usd["investments_cost"]) == Decimal(300)
        assert Decimal(usd["result"]) == Decimal("10.70")
        assert Decimal(usd["result_pct"]) == Decimal("0.0357")
        assert usd["investments_basis"] == "MARKET" and usd["result_complete"] is True
        assert Decimal(usd["net_contributions"]) == Decimal(300)
        assert [(g["key"], g["label"], Decimal(g["value"])) for g in usd["investment_groups"]] == [
            ("VARIABLE", "Renda variável", Decimal(210)),
            ("FIXED", "Renda fixa", Decimal("100.70")),
        ]
        brl = blocks["BRL"]
        assert Decimal(brl["reserve"]) == Decimal(13200)
        assert Decimal(brl["liquid"]) == Decimal(500)
        assert Decimal(brl["card"]) == Decimal(-120)
        assert Decimal(brl["total"]) == Decimal(13580)  # 13.200 + 500 − 120
        assert [(p["key"], Decimal(p["weight"])) for p in brl["parts"]] == [
            ("RESERVE", Decimal("0.9635")),
            ("LIQUID", Decimal("0.0365")),
        ]
        assert Decimal(usd["total"]) == Decimal("310.70")

    def test_sem_cotacao_entra_pelo_custo_e_diz_quais(self, w):
        w["tx"]("usd", "BUY", "200", "spy", "0.25", "800")
        w["tx"]("usd", "BUY", "50", "aaxj", "0.5", "100")
        w["price"]("spy", "840")

        usd = w["client"].get("/overview").json()["totals_by_currency"][0]

        assert usd["investments_basis"] == "MIXED"
        assert usd["unpriced"] == [w["assets"]["aaxj"].ticker]
        assert Decimal(usd["investments_value"]) == Decimal(260)
        assert Decimal(usd["result"]) == Decimal(10)
        assert usd["result_complete"] is False

    def test_nenhuma_cotacao_e_base_de_custo(self, w):
        w["tx"]("brl", "BUY", "1000", "tesouro", "1", "1000", currency="BRL")

        brl = w["client"].get("/overview").json()["totals_by_currency"][0]

        assert brl["investments_basis"] == "COST"
        assert brl["result_pct"] == "0.0000"
        assert [g["key"] for g in brl["investment_groups"]] == ["FIXED"]

    def test_conta_no_vermelho_nao_vira_fatia_mas_desconta_do_total(self, w):
        w["entry"]("savings", "1000", TODAY, "Saldo", "ADJUSTMENT")
        w["entry"]("checking", "-300", TODAY, "Cheque especial", "EXPENSE")

        (brl,) = w["client"].get("/overview").json()["totals_by_currency"]

        assert Decimal(brl["total"]) == Decimal(700)
        assert [(p["key"], Decimal(p["weight"])) for p in brl["parts"]] == [("RESERVE", Decimal(1))]

    def test_vazio(self, w):
        assert w["client"].get("/overview").json()["totals_by_currency"] == []


class TestMesAMes:
    def test_renda_gastos_sobra_e_meses_sem_movimento(self, w):
        w["entry"]("checking", "3000", _day_in(2), "Salário", "INCOME")
        w["entry"]("card", "-1200", _day_in(2, 12), "Compra", "EXPENSE")
        w["entry"]("checking", "3100", _day_in(0, 1), "Salário", "INCOME")
        w["entry"]("card", "-200", _day_in(0, 1), "Algo", "UNCLASSIFIED")

        body = w["client"].get("/cashflow/summary/monthly", params={"months": 3}).json()

        (brl,) = body["totals_by_currency"]
        y, m = _month(0)
        assert body["end_month"] == f"{y}-{m:02d}"
        months = brl["months"]
        assert [x["month"] for x in months] == [
            f"{a}-{b:02d}" for a, b in (_month(2), _month(1), _month(0))
        ]
        assert (
            Decimal(months[0]["income"]),
            Decimal(months[0]["expenses"]),
            Decimal(months[0]["surplus"]),
        ) == (
            Decimal(3000),
            Decimal(1200),
            Decimal(1800),
        )
        assert months[1]["entry_count"] == 0 and Decimal(months[1]["surplus"]) == 0
        assert Decimal(months[2]["unclassified_net"]) == Decimal(-200)
        assert Decimal(months[2]["surplus"]) == Decimal(3100)

    def test_parametros_invalidos(self, w):
        client = w["client"]

        assert client.get("/cashflow/summary/monthly", params={"months": 0}).status_code == 422
        assert client.get("/cashflow/summary/monthly", params={"months": 25}).status_code == 422
        response = client.get("/cashflow/summary/monthly", params={"end": "2026-13"})
        assert response.status_code == 400
        assert "AAAA-MM" in response.json()["detail"]

    def test_mes_final_escolhido(self, w):
        body = (
            w["client"]
            .get("/cashflow/summary/monthly", params={"end": "2026-02", "months": 2})
            .json()
        )

        assert body["end_month"] == "2026-02"
        assert body["totals_by_currency"] == []


class TestOndeMelhorar:
    def test_regras_aplicadas_aos_lancamentos_com_categoria_mae(self, w):
        client = w["client"]
        food = client.post("/cashflow/categories", json={"name": "Alimentação"}).json()
        market = client.post(
            "/cashflow/categories", json={"name": "Mercado", "parent_id": food["id"]}
        ).json()
        for back in (3, 2, 1):
            w["entry"]("card", "-300", _day_in(back), "Mercado Exemplo", "EXPENSE", market["id"])
            w["entry"]("card", "-12.90", _day_in(back, 13), "Dm*Spotify P46c9", "EXPENSE")
        w["entry"]("card", "-450", _day_in(0, 1), "Mercado Exemplo", "EXPENSE", market["id"])
        w["entry"]("card", "-12.90", _day_in(0, 1), "Spotify", "EXPENSE")

        body = client.get("/cashflow/insights").json()

        (brl,) = body["totals_by_currency"]
        (change,) = brl["above_normal"]
        assert change["label"] == "Alimentação"  # subcategoria sobe para a mãe
        assert Decimal(change["difference"]) == Decimal("150.00")
        assert [(r["label"], Decimal(r["monthly_average"])) for r in brl["recurring"]] == [
            ("mercado exemplo", Decimal("350.00")),
            ("spotify", Decimal("12.90")),
        ]
        assert brl["small_limit"] == "30"
        assert brl["history_months"] == 3

    def test_mes_invalido(self, w):
        assert (
            w["client"].get("/cashflow/insights", params={"month": "out/2026"}).status_code == 400
        )
