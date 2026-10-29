"""GET /performance/benchmarks e o CDI baixado junto com as cotações."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.api.routers.prices import get_quote_provider, get_rate_provider
from app.main import app
from app.models.asset_price import AssetPrice
from app.models.benchmark_rate import BenchmarkRate
from app.models.enums import AccountType, PriceSource
from app.services.market_data.yahoo import MarketDataError
from tests.cashflow_helpers import make_typed_account
from tests.test_persistence import make_asset, make_institution

TODAY = date.today()


def _trade(client, account, body):
    response = client.post("/transactions", json={"account_id": str(account.id), **body})
    assert response.status_code == 201, response.text


def _buy(client, account, asset, qty, price, when, currency):
    gross = str(Decimal(qty) * Decimal(price))
    _trade(
        client,
        account,
        {
            "transaction_type": "DEPOSIT",
            "gross_amount": gross,
            "currency_code": currency,
            "transaction_date": when,
        },
    )
    _trade(
        client,
        account,
        {
            "transaction_type": "BUY",
            "asset_id": str(asset.id),
            "quantity": qty,
            "unit_price": price,
            "gross_amount": gross,
            "currency_code": currency,
            "transaction_date": when,
        },
    )


def _price(db, asset, day, price, currency="USD"):
    db.add(
        AssetPrice(
            asset_id=asset.id,
            price_date=day,
            price=price,
            currency_code=currency,
            source=PriceSource.MANUAL,
        )
    )


def test_dolar_comparado_ao_spy_com_os_mesmos_aportes(api_client, db_session):
    client, user = api_client
    inst = make_institution(db_session, name=f"Corretora B {uuid.uuid4().hex[:6]}")
    account = make_typed_account(db_session, user, inst, "Conta", AccountType.BROKERAGE, "USD")
    from app.models.asset import Asset

    spy = db_session.execute(
        select(Asset).where(Asset.ticker == "SPY", Asset.currency_code == "USD")
    ).scalar_one_or_none()
    if spy is None:
        spy = make_asset(db_session, "SPY", "ETF_US", "US", "USD")
    other = make_asset(db_session, f"Q{uuid.uuid4().hex[:4].upper()}", "ETF_US", "US", "USD")
    d0, d1 = TODAY - timedelta(days=20), TODAY - timedelta(days=10)
    _price(db_session, spy, d0, "100")
    _price(db_session, spy, d1, "110")
    _price(db_session, spy, TODAY, "121")
    _price(db_session, other, d0, "50")
    _price(db_session, other, TODAY, "60")
    db_session.flush()
    _buy(client, account, other, "2", "50", d0.isoformat(), "USD")  # 100 no dia 0

    (usd,) = client.get("/performance/benchmarks").json()["comparisons"]

    assert usd["currency_code"] == "USD" and usd["benchmark"] == "SPY"
    assert usd["available"] is True
    assert float(usd["net_invested"]) == 100
    assert float(usd["portfolio_value"]) == 120  # 2 × 60
    assert float(usd["benchmark_value"]) == 121  # 1 cota do SPY × 121
    assert float(usd["difference"]) == -1
    assert float(usd["portfolio_return"]) == 0.2
    assert float(usd["benchmark_return"]) == 0.21
    assert usd["points"][0]["date"] == d0.isoformat()
    assert usd["points"][-1]["date"] == TODAY.isoformat()


def test_sem_cotacao_da_referencia_explica_o_que_falta(api_client, db_session):
    client, user = api_client
    inst = make_institution(db_session, name=f"Banco R {uuid.uuid4().hex[:6]}")
    account = make_typed_account(db_session, user, inst, "Conta BR", AccountType.BROKERAGE, "BRL")
    asset = make_asset(db_session, f"T{uuid.uuid4().hex[:4].upper()}", "CDB", "BR", "BRL")
    _buy(client, account, asset, "1", "1000", (TODAY - timedelta(days=5)).isoformat(), "BRL")

    (brl,) = client.get("/performance/benchmarks").json()["comparisons"]

    assert brl["benchmark"] == "CDI" and brl["available"] is False
    assert "CDI ainda não baixado" in brl["reason"]


class _FakeRates:
    def __init__(self):
        self.calls = []

    def fetch(self, start, end):
        self.calls.append((start, end))
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        return [(d, Decimal("0.05")) for d in days if d.weekday() < 5]


class _NoQuotes:
    def fetch(self, symbol):
        raise MarketDataError("sem rede no teste")


def test_atualizar_cotacoes_baixa_o_cdi_e_libera_a_comparacao_em_reais(api_client, db_session):
    client, user = api_client
    inst = make_institution(db_session, name=f"Banco C {uuid.uuid4().hex[:6]}")
    account = make_typed_account(db_session, user, inst, "Conta BR", AccountType.BROKERAGE, "BRL")
    asset = make_asset(db_session, f"T{uuid.uuid4().hex[:4].upper()}", "CDB", "BR", "BRL")
    _buy(client, account, asset, "1", "1000", (TODAY - timedelta(days=30)).isoformat(), "BRL")
    rates = _FakeRates()
    app.dependency_overrides[get_rate_provider] = lambda: rates
    app.dependency_overrides[get_quote_provider] = lambda: _NoQuotes()

    body = client.post("/prices/refresh").json()
    assert body["cdi_status"].startswith("OK:")
    assert (
        db_session.execute(select(BenchmarkRate).where(BenchmarkRate.code == "CDI")).first()
        is not None
    )

    (brl,) = client.get("/performance/benchmarks").json()["comparisons"]
    assert brl["available"] is True
    assert float(brl["benchmark_value"]) > 1000  # o CDI rendeu
    assert float(brl["benchmark_return"]) > 0

    # Segunda busca no mesmo dia: nada falta, nada é pedido de novo.
    client.post("/prices/refresh")
    assert len(rates.calls) == 1
    # Um dia sem CDI no fim: só esse período é pedido.
    db_session.execute(
        BenchmarkRate.__table__.delete().where(BenchmarkRate.rate_date >= TODAY - timedelta(days=2))
    )
    client.post("/prices/refresh")
    assert len(rates.calls) == 2
    assert rates.calls[-1][0] >= TODAY - timedelta(days=5)


def test_falha_do_banco_central_nao_derruba_as_cotacoes(api_client, db_session):
    client, user = api_client
    inst = make_institution(db_session, name=f"Banco F {uuid.uuid4().hex[:6]}")
    account = make_typed_account(db_session, user, inst, "Conta BR", AccountType.BROKERAGE, "BRL")
    asset = make_asset(db_session, f"T{uuid.uuid4().hex[:4].upper()}", "CDB", "BR", "BRL")
    _buy(client, account, asset, "1", "1000", (TODAY - timedelta(days=30)).isoformat(), "BRL")

    class _Broken:
        def fetch(self, start, end):
            raise MarketDataError("o Banco Central respondeu 503")

    app.dependency_overrides[get_rate_provider] = lambda: _Broken()
    app.dependency_overrides[get_quote_provider] = lambda: _NoQuotes()

    response = client.post("/prices/refresh")

    assert response.status_code == 200
    assert response.json()["cdi_status"] == "ERRO: o Banco Central respondeu 503"


def test_fim_de_semana_sem_cdi_novo_nao_pede_nada(api_client, db_session):
    """Regressão: num sábado, com o CDI gravado até sexta, a segunda busca
    pedia ao Banco Central um período só de fim de semana."""
    from app.services import benchmark_service

    client, user = api_client
    inst = make_institution(db_session, name=f"Banco S {uuid.uuid4().hex[:6]}")
    account = make_typed_account(db_session, user, inst, "Conta BR", AccountType.BROKERAGE, "BRL")
    asset = make_asset(db_session, f"T{uuid.uuid4().hex[:4].upper()}", "CDB", "BR", "BRL")
    saturday = TODAY - timedelta(days=(TODAY.weekday() - 5) % 7)
    _buy(client, account, asset, "1", "1000", (saturday - timedelta(days=30)).isoformat(), "BRL")
    rates = _FakeRates()

    benchmark_service.refresh_cdi(db_session, user.id, rates, today=saturday)
    assert len(rates.calls) == 1
    benchmark_service.refresh_cdi(db_session, user.id, rates, today=saturday)
    benchmark_service.refresh_cdi(db_session, user.id, rates, today=saturday + timedelta(days=1))

    assert len(rates.calls) == 1
