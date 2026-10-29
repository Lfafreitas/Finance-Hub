"""Análises-1: atualização automática de cotações e análises da
carteira pela API. A fonte é sempre falsa nos testes.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.api.routers.prices import get_quote_provider
from app.main import app
from app.models.asset_price import AssetPrice
from app.models.enums import AccountType, PriceSource
from app.services.market_data.yahoo import MarketDataError, QuoteBar, QuoteSeries
from tests.cashflow_helpers import make_typed_account
from tests.test_persistence import make_asset, make_institution

TODAY = date.today()


def _days_ago(n):
    return TODAY - timedelta(days=n)


class FakeProvider:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def fetch(self, symbol):
        self.calls.append(symbol)
        response = self.responses.get(symbol)
        if isinstance(response, Exception):
            raise response
        if response is None:
            raise MarketDataError("código não encontrado na fonte")
        return response


def _series(symbol, closes, currency="USD"):
    """`closes`: lista de (dias atrás, preço)."""
    bars = [QuoteBar(day=_days_ago(n), close=Decimal(p)) for n, p in closes]
    return QuoteSeries(symbol=symbol, currency=currency, bars=sorted(bars, key=lambda b: b.day))


@pytest.fixture()
def world(api_client, db_session):
    client, user = api_client
    inst = make_institution(db_session, name=f"Corretora A1 {uuid.uuid4().hex[:6]}")
    usd = make_typed_account(db_session, user, inst, "Inter US", AccountType.BROKERAGE, "USD")
    usd2 = make_typed_account(db_session, user, inst, "XP US", AccountType.BROKERAGE, "USD")
    brl = make_typed_account(db_session, user, inst, "XP BR", AccountType.BROKERAGE, "BRL")
    suffix = uuid.uuid4().hex[:4].upper()
    spy = make_asset(db_session, f"SPY{suffix}", "ETF_US", "US", "USD")
    qqq = make_asset(db_session, f"QQQ{suffix}", "ETF_US", "US", "USD")
    vnq = make_asset(db_session, f"VNQ{suffix}", "REIT", "US", "USD")
    cd = make_asset(db_session, f"CDUS{suffix}", "BOND", "US", "USD")
    petr = make_asset(db_session, f"PETR{suffix}", "STOCK_BR", "BR", "BRL")
    idle = make_asset(db_session, f"IDLE{suffix}", "ETF_US", "US", "USD")

    def tx(account, kind, amount, when, asset=None, qty=None, price=None, currency="USD"):
        body = {
            "account_id": str(account.id),
            "transaction_type": kind,
            "gross_amount": amount,
            "currency_code": currency,
            "transaction_date": when.isoformat(),
        }
        if asset is not None:
            body.update(asset_id=str(asset.id), quantity=qty, unit_price=price)
        response = client.post("/transactions", json=body)
        assert response.status_code == 201, response.text
        return response.json()

    def price(asset, value, when=None, currency="USD"):
        response = client.put(
            f"/assets/{asset.id}/prices",
            json={"price_date": (when or _days_ago(1)).isoformat(), "price": value},
        )
        assert response.status_code == 200, response.text

    return {
        "client": client,
        "db": db_session,
        "usd": usd,
        "usd2": usd2,
        "brl": brl,
        "spy": spy,
        "qqq": qqq,
        "vnq": vnq,
        "cd": cd,
        "petr": petr,
        "idle": idle,
        "tx": tx,
        "price": price,
    }


def _use_provider(provider):
    app.dependency_overrides[get_quote_provider] = lambda: provider


class TestAtualizarCotacoes:
    def _hold(self, w):
        w["tx"](w["usd"], "BUY", "100", _days_ago(30), w["spy"], "0.5", "200")
        w["tx"](w["usd"], "BUY", "50", _days_ago(30), w["cd"], "50", "1")
        w["tx"](w["brl"], "BUY", "300", _days_ago(30), w["petr"], "10", "30", currency="BRL")

    def test_grava_o_historico_como_fonte_automatica_so_dos_ativos_da_carteira(self, world):
        self._hold(world)
        spy, petr = world["spy"], world["petr"]
        provider = FakeProvider(
            {
                spy.ticker: _series(spy.ticker, [(3, "770.10"), (2, "771.00"), (0, "777.14")]),
                f"{petr.ticker}.SA": _series(petr.ticker, [(0, "38.50")], currency="BRL"),
            }
        )
        _use_provider(provider)

        body = world["client"].post("/prices/refresh").json()

        by_ticker = {item["ticker"]: item for item in body["items"]}
        assert by_ticker[spy.ticker]["status"] == "OK"
        assert by_ticker[spy.ticker]["points"] == 3
        assert by_ticker[spy.ticker]["price"] == "777.14"
        assert by_ticker[spy.ticker]["price_date"] == TODAY.isoformat()
        assert by_ticker[petr.ticker]["status"] == "OK"
        assert world["idle"].ticker not in by_ticker
        assert world["idle"].ticker not in provider.calls
        rows = world["db"].query(AssetPrice).filter_by(asset_id=spy.id).all()
        assert {(r.source, r.currency_code) for r in rows} == {(PriceSource.YAHOO, "USD")}
        assert len(rows) == 3

    def test_renda_fixa_nao_e_buscada(self, world):
        self._hold(world)
        provider = FakeProvider({})
        _use_provider(provider)

        body = world["client"].post("/prices/refresh").json()

        item = next(i for i in body["items"] if i["ticker"] == world["cd"].ticker)
        assert item["status"] == "UNSUPPORTED"
        assert "informe a cotação à mão" in item["message"]
        assert world["cd"].ticker not in provider.calls

    def test_moeda_diferente_da_do_ativo_nao_grava_nada(self, world):
        self._hold(world)
        spy = world["spy"]
        _use_provider(
            FakeProvider({spy.ticker: _series(spy.ticker, [(0, "4000")], currency="BRL")})
        )

        body = world["client"].post("/prices/refresh").json()

        item = next(i for i in body["items"] if i["ticker"] == spy.ticker)
        assert item["status"] == "ERROR"
        assert "BRL" in item["message"] and "nada gravado" in item["message"]
        assert world["db"].query(AssetPrice).filter_by(asset_id=spy.id).count() == 0

    def test_falha_de_um_ativo_nao_impede_os_outros(self, world):
        self._hold(world)
        spy, petr = world["spy"], world["petr"]
        _use_provider(
            FakeProvider(
                {
                    spy.ticker: MarketDataError("sem resposta da fonte: ConnectTimeout"),
                    f"{petr.ticker}.SA": _series(petr.ticker, [(0, "38.50")], currency="BRL"),
                }
            )
        )

        body = world["client"].post("/prices/refresh").json()

        by_ticker = {item["ticker"]: item for item in body["items"]}
        assert by_ticker[spy.ticker]["status"] == "ERROR"
        assert "ConnectTimeout" in by_ticker[spy.ticker]["message"]
        assert by_ticker[petr.ticker]["status"] == "OK"

    def test_atualizar_de_novo_substitui_sem_duplicar_e_ignora_data_futura(self, world):
        self._hold(world)
        spy = world["spy"]
        _use_provider(FakeProvider({spy.ticker: _series(spy.ticker, [(1, "770"), (0, "775")])}))
        world["client"].post("/prices/refresh")
        _use_provider(FakeProvider({spy.ticker: _series(spy.ticker, [(0, "777.14"), (-1, "999")])}))

        world["client"].post("/prices/refresh")

        rows = {
            r.price_date: r.price
            for r in world["db"].query(AssetPrice).filter_by(asset_id=spy.id).all()
        }
        assert rows == {_days_ago(1): Decimal("770.00000000"), TODAY: Decimal("777.14000000")}

    def test_cotacao_manual_na_mesma_data_vence_a_automatica(self, world):
        self._hold(world)
        spy = world["spy"]
        world["price"](spy, "760", TODAY)
        _use_provider(FakeProvider({spy.ticker: _series(spy.ticker, [(0, "777.14")])}))

        world["client"].post("/prices/refresh")

        latest = {p["asset_ticker"]: p for p in world["client"].get("/prices/latest").json()}
        assert latest[spy.ticker]["price"] == "760.00000000"
        position = next(
            p
            for p in world["client"].get("/dashboard/summary").json()["positions"]
            if p["asset_ticker"] == spy.ticker
        )
        assert position["market_price"] == "760.00000000"

    def test_automatica_mais_nova_vence_manual_mais_antiga(self, world):
        self._hold(world)
        spy = world["spy"]
        world["price"](spy, "700", _days_ago(5))
        _use_provider(FakeProvider({spy.ticker: _series(spy.ticker, [(0, "777.14")])}))

        world["client"].post("/prices/refresh")

        latest = {p["asset_ticker"]: p for p in world["client"].get("/prices/latest").json()}
        assert latest[spy.ticker]["price"] == "777.14000000"

    def test_ativo_so_com_transacao_estornada_nao_e_buscado(self, world):
        bought = world["tx"](world["usd"], "BUY", "100", _days_ago(30), world["qqq"], "1", "100")
        assert world["client"].post(f"/transactions/{bought['id']}/reverse").status_code == 200
        provider = FakeProvider({})
        _use_provider(provider)

        body = world["client"].post("/prices/refresh").json()

        assert world["qqq"].ticker not in {i["ticker"] for i in body["items"]}


class TestAnalises:
    def _portfolio(self, w):
        tx, usd, usd2 = w["tx"], w["usd"], w["usd2"]
        tx(usd, "DEPOSIT", "100.00", _days_ago(40))
        tx(usd, "DEPOSIT", "200.00", _days_ago(10))
        tx(usd, "BUY", "120", _days_ago(40), w["spy"], "0.2", "600")
        tx(usd, "BUY", "150", _days_ago(10), w["qqq"], "0.25", "600")
        tx(usd2, "BUY", "100", _days_ago(10), w["qqq"], "0.2", "500")
        tx(usd, "BUY", "30", _days_ago(10), w["vnq"], "0.3", "100")
        tx(usd, "BUY", "50", _days_ago(10), w["cd"], "50", "1")
        w["price"](w["spy"], "700")
        w["price"](w["qqq"], "800")
        w["price"](w["vnq"], "100")
        w["price"](w["cd"], "1.01")

    def test_concentracao_pelo_valor_de_mercado_com_o_mesmo_ativo_em_duas_contas(self, world):
        self._portfolio(world)

        body = world["client"].get("/analytics/portfolio").json()

        (usd,) = body["blocks"]
        assert usd["currency_code"] == "USD"
        conc = usd["concentration"]
        assert conc["basis"] == "MARKET"
        # SPY 0,2·700=140; QQQ 0,45·800=360; VNQ 0,3·100=30; CD 50·1,01=50,5
        assert Decimal(conc["total"]) == Decimal("580.5")
        assert [(w["label"], Decimal(w["weight"])) for w in conc["by_asset"]] == [
            (world["qqq"].ticker, Decimal("0.6202")),
            (world["spy"].ticker, Decimal("0.2412")),
            (world["cd"].ticker, Decimal("0.0870")),
            (world["vnq"].ticker, Decimal("0.0517")),
        ]
        assert [w["label"] for w in conc["by_account"]] == ["Inter US", "XP US"]
        assert "ETF (Exterior)" in [w["label"] for w in conc["by_class"]]
        # SPY 140 + QQQ 360 + VNQ 30 = 530 variável; CD 50,50 fixa
        assert [(g["key"], g["label"], Decimal(g["value"])) for g in conc["by_group"]] == [
            ("VARIABLE", "Renda variável", Decimal(530)),
            ("FIXED", "Renda fixa", Decimal("50.5")),
        ]
        assert any("mais de 40%" in f for f in conc["flags"])

    def test_cenarios_so_com_risco_de_mercado_e_renda_fixa_declarada_fora(self, world):
        self._portfolio(world)

        usd = world["client"].get("/analytics/portfolio").json()["blocks"][0]

        scenarios = usd["scenarios"]
        assert Decimal(scenarios["value_today"]) == Decimal("530.00")  # sem os 50,50 do CD
        assert scenarios["until"] == date(TODAY.year, 12, 31).isoformat()
        assert scenarios["horizon_days"] == (date(TODAY.year, 12, 31) - TODAY).days
        assert [e["key"] for e in scenarios["excluded"]] == [world["cd"].ticker]
        assert "renda fixa" in scenarios["excluded"][0]["reason"]
        keys = [a["key"] for a in scenarios["assumptions"]]
        assert sorted(keys) == sorted(
            [world["spy"].ticker, world["qqq"].ticker, world["vnq"].ticker]
        )
        assert all(a["volatility_from_history"] is False for a in scenarios["assumptions"])
        assert (
            Decimal(scenarios["pessimistic_value"])
            < Decimal(scenarios["realistic_value"])
            < Decimal(scenarios["optimistic_value"])
        )

    def test_historico_de_cotacoes_automaticas_alimenta_a_volatilidade(self, world):
        self._portfolio(world)
        spy = world["spy"]
        closes = [
            (n, str(round(600 + (5 if n % 2 else -5) + (90 - n) * 0.5, 2)))
            for n in range(90, 0, -1)
        ]
        _use_provider(FakeProvider({spy.ticker: _series(spy.ticker, closes)}))
        world["client"].post("/prices/refresh")

        usd = world["client"].get("/analytics/portfolio").json()["blocks"][0]

        spy_assumption = next(a for a in usd["scenarios"]["assumptions"] if a["key"] == spy.ticker)
        assert spy_assumption["volatility_from_history"] is True
        assert spy_assumption["history_returns"] >= 60
        assert usd["scenarios"] is not None
        assert world["client"].get("/analytics/portfolio").json()["quotes_refreshed_at"] is not None

    def test_sem_cotacao_concentracao_pelo_custo_e_ativo_fora_dos_cenarios(self, world):
        self._portfolio(world)
        world["tx"](world["usd"], "BUY", "40", _days_ago(5), world["idle"], "1", "40")

        usd = world["client"].get("/analytics/portfolio").json()["blocks"][0]

        assert usd["concentration"]["basis"] == "COST"
        assert usd["market_value"] is None
        excluded = {e["key"]: e["reason"] for e in usd["scenarios"]["excluded"]}
        assert "sem cotação" in excluded[world["idle"].ticker]
        assert any(world["idle"].ticker in alert for alert in usd["alerts"])

    def test_ritmo_de_aporte_vem_dos_depositos(self, world):
        self._portfolio(world)

        contributions = (
            world["client"].get("/analytics/portfolio").json()["blocks"][0]["contributions"]
        )

        in_year = [d for d in (_days_ago(40), _days_ago(10)) if d.year == TODAY.year]
        expected = sum(
            Decimal(v)
            for d, v in zip((_days_ago(40), _days_ago(10)), ("100", "200"), strict=True)
            if d in in_year
        )
        assert Decimal(contributions["total_year"]) == expected
        assert {p["pace"] for p in contributions["projections"]} == {
            "AVERAGE",
            "LAST_3",
            "LAST_MONTH",
        }

    def test_cotacao_antiga_gera_alerta(self, world):
        self._portfolio(world)
        world["price"](world["vnq"], "99", _days_ago(30))
        world["db"].query(AssetPrice).filter(
            AssetPrice.asset_id == world["vnq"].id, AssetPrice.price_date == _days_ago(1)
        ).delete()
        world["db"].flush()

        usd = world["client"].get("/analytics/portfolio").json()["blocks"][0]

        assert (
            f"cotação de {world['vnq'].ticker} é de {_days_ago(30).strftime('%d/%m/%Y')}"
            in usd["alerts"]
        )

    def test_moedas_nunca_se_misturam(self, world):
        self._portfolio(world)
        world["tx"](
            world["brl"], "BUY", "300", _days_ago(5), world["petr"], "10", "30", currency="BRL"
        )
        world["price"](world["petr"], "35")

        blocks = {
            b["currency_code"]: b
            for b in world["client"].get("/analytics/portfolio").json()["blocks"]
        }

        assert set(blocks) == {"BRL", "USD"}
        assert Decimal(blocks["BRL"]["concentration"]["total"]) == Decimal(350)
        assert [w["label"] for w in blocks["BRL"]["concentration"]["by_asset"]] == [
            world["petr"].ticker
        ]
        assert world["petr"].ticker not in [
            w["label"] for w in blocks["USD"]["concentration"]["by_asset"]
        ]
        assert blocks["BRL"]["scenarios"]["expected_return"] == "0.1000"

    def test_data_final_escolhida_e_data_passada(self, world):
        self._portfolio(world)
        client = world["client"]
        until = (TODAY + timedelta(days=30)).isoformat()

        chosen = client.get("/analytics/portfolio", params={"until": until}).json()["blocks"][0]
        past = client.get("/analytics/portfolio", params={"until": TODAY.isoformat()}).json()[
            "blocks"
        ][0]

        assert chosen["scenarios"]["horizon_days"] == 30
        assert past["scenarios"] is None
        assert "depois de hoje" in past["scenarios_unavailable_reason"]

    def test_carteira_vazia_e_carteira_inexistente(self, world):
        client = world["client"]

        assert client.get("/analytics/portfolio").json()["blocks"] == []
        response = client.get("/analytics/portfolio", params={"portfolio_id": str(uuid.uuid4())})
        assert response.status_code == 404


def test_historico_usa_a_cotacao_manual_quando_as_duas_fontes_tem_a_mesma_data(world):
    from app.services.analytics_service import _history

    spy, db = world["spy"], world["db"]
    day = _days_ago(3)
    db.add(
        AssetPrice(
            asset_id=spy.id,
            price_date=day,
            price=Decimal(999),
            currency_code="USD",
            source=PriceSource.YAHOO,
        )
    )
    db.add(
        AssetPrice(
            asset_id=spy.id,
            price_date=day,
            price=Decimal(700),
            currency_code="USD",
            source=PriceSource.MANUAL,
        )
    )
    db.add(
        AssetPrice(
            asset_id=spy.id,
            price_date=_days_ago(2),
            price=Decimal(710),
            currency_code="USD",
            source=PriceSource.YAHOO,
        )
    )
    db.flush()

    history = _history(db, [spy.id], TODAY)

    assert history[spy.id] == (
        (day, Decimal("700.00000000")),
        (_days_ago(2), Decimal("710.00000000")),
    )
