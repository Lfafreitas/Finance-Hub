"""Painel-1: evolução do patrimônio e resumo do widget — pela API."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.enums import AccountType
from tests.cashflow_helpers import make_typed_account
from tests.test_persistence import make_asset, make_institution

TODAY = date.today()


def ago(days: int) -> date:
    return TODAY - timedelta(days=days)


@pytest.fixture()
def p(api_client, db_session):
    client, user = api_client
    inst = make_institution(db_session, name=f"Inst P1 {uuid.uuid4().hex[:6]}")
    acc = {
        "usd": make_typed_account(db_session, user, inst, "Inter US", AccountType.BROKERAGE, "USD"),
        "checking": make_typed_account(
            db_session, user, inst, "Conta", AccountType.CHECKING, "BRL"
        ),
    }
    suffix = uuid.uuid4().hex[:4].upper()
    assets = {
        "spy": make_asset(db_session, f"SPY{suffix}", "ETF_US", "US", "USD"),
        "cd": make_asset(db_session, f"CD{suffix}", "BOND", "US", "USD"),
    }

    def buy(asset, qty, price, when):
        r = client.post(
            "/transactions",
            json={
                "account_id": str(acc["usd"].id),
                "transaction_type": "BUY",
                "gross_amount": str(Decimal(qty) * Decimal(price)),
                "currency_code": "USD",
                "transaction_date": when.isoformat(),
                "asset_id": str(assets[asset].id),
                "quantity": qty,
                "unit_price": price,
            },
        )
        assert r.status_code == 201, r.text

    def price(asset, value, when):
        r = client.put(
            f"/assets/{assets[asset].id}/prices",
            json={"price_date": when.isoformat(), "price": value},
        )
        assert r.status_code == 200, r.text

    def cash(amount, when):
        r = client.post(
            "/cashflow/entries",
            json={
                "account_id": str(acc["checking"].id),
                "entry_date": when.isoformat(),
                "amount": amount,
                "description": "lançamento",
                "nature": "INCOME",
            },
        )
        assert r.status_code == 201, r.text

    return {"client": client, "buy": buy, "price": price, "cash": cash, "assets": assets}


def _series(body, currency):
    block = next(b for b in body["totals_by_currency"] if b["currency_code"] == currency)
    return {point["date"]: point for point in block["points"]}


class TestEvolucao:
    def test_um_ponto_por_dia_com_valor_custo_e_caixa_por_moeda(self, p):
        p["buy"]("spy", "2", "100", ago(20))
        p["price"]("spy", "110", ago(10))
        p["price"]("spy", "120", ago(1))
        p["cash"]("500", ago(15))

        body = p["client"].get("/performance/history?days=30").json()

        assert body["start"] == ago(20).isoformat()  # primeiro movimento
        assert body["end"] == TODAY.isoformat()
        usd = _series(body, "USD")
        assert len(usd) == 21
        assert Decimal(usd[ago(15).isoformat()]["investments_value"]) == Decimal(200)
        assert usd[ago(15).isoformat()]["unpriced"] == [p["assets"]["spy"].ticker]
        assert Decimal(usd[ago(10).isoformat()]["investments_value"]) == Decimal(220)
        assert usd[ago(10).isoformat()]["unpriced"] == []
        last = usd[TODAY.isoformat()]
        assert Decimal(last["investments_value"]) == Decimal(240)
        assert Decimal(last["investments_cost"]) == Decimal(200)
        assert Decimal(last["total"]) == Decimal(240)
        brl = _series(body, "BRL")
        assert Decimal(brl[ago(16).isoformat()]["cash"]) == Decimal(0)
        assert Decimal(brl[ago(15).isoformat()]["cash"]) == Decimal(500)
        assert Decimal(brl[TODAY.isoformat()]["total"]) == Decimal(500)

    def test_periodo_curto_corta_o_inicio(self, p):
        p["buy"]("spy", "1", "100", ago(40))

        body = p["client"].get("/performance/history?days=7").json()

        assert body["start"] == ago(6).isoformat()
        assert len(_series(body, "USD")) == 7

    def test_sem_movimento_nao_ha_serie(self, p):
        body = p["client"].get("/performance/history").json()

        assert body == {"start": None, "end": TODAY.isoformat(), "totals_by_currency": []}

    @pytest.mark.parametrize("days", ["0", "1101", "abc"])
    def test_periodo_invalido_e_recusado(self, p, days):
        assert p["client"].get(f"/performance/history?days={days}").status_code == 422


class TestWidget:
    def test_patrimonio_variacao_do_pregao_e_ultimos_30_dias(self, p):
        p["buy"]("spy", "2", "100", ago(20))
        p["buy"]("cd", "100", "1", ago(20))
        p["price"]("spy", "110", ago(3))
        p["price"]("spy", "120", ago(1))
        p["price"]("cd", "1.01", ago(3))
        p["price"]("cd", "1.02", ago(1))
        p["cash"]("500", ago(15))

        body = p["client"].get("/performance/widget").json()

        assert body["as_of"] == TODAY.isoformat()
        blocks = {b["currency_code"]: b for b in body["totals_by_currency"]}
        usd = blocks["USD"]
        assert Decimal(usd["total"]) == Decimal(342)  # 2×120 + 100×1,02
        assert Decimal(usd["result"]) == Decimal(42)
        assert Decimal(usd["result_pct"]) == Decimal("0.1400")
        # Só o ETF entra na variação do pregão; o CD não.
        assert Decimal(usd["day_change"]) == Decimal(20)
        assert Decimal(usd["day_change_pct"]) == Decimal("0.0909")
        assert usd["day_date"] == ago(1).isoformat()
        assert [m["ticker"] for m in usd["movers"]] == [p["assets"]["spy"].ticker]
        assert usd["movers"][0]["previous_date"] == ago(3).isoformat()
        assert len(usd["spark"]) == 21
        assert Decimal(usd["spark"][-1]["value"]) == Decimal(342)
        brl = blocks["BRL"]
        assert Decimal(brl["total"]) == Decimal(500)
        assert brl["day_change"] is None and brl["movers"] == [] and brl["spark"] == []

    def test_sem_nada_devolve_lista_vazia(self, p):
        body = p["client"].get("/performance/widget").json()

        assert body["totals_by_currency"] == []
        assert body["quotes_refreshed_at"] is None
