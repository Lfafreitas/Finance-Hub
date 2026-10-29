"""Relatório v3 (jornal): números do mercado, oportunidades para estudar e
composição dos ETFs — e a exposição às empresas por trás dos ETFs.
"""

import copy
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.config import settings
from app.models.enums import AccountType
from tests.api.test_insights_api import _report, _write
from tests.api.test_kpis_api import _buy
from tests.cashflow_helpers import make_typed_account
from tests.test_persistence import make_asset, make_institution

TODAY = date.today()


@pytest.fixture()
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "insights_dir", tmp_path)
    return tmp_path


def _v3(qqq="QQQ", **overrides):
    report = _report(schema_version=3)
    report["market"] = [
        {
            "label": "S&P 500",
            "value": "6.712",
            "change": "-0,4% no dia",
            "direction": "DOWN",
            "as_of": "2026-10-24",
            "source": "Yahoo Finance",
        }
    ]
    report["opportunities"] = [
        {
            "title": "Semicondutores depois da correção",
            "thesis": "Lucros do setor seguem crescendo enquanto o preço caiu.",
            "tickers": ["SMH", qqq],
            "relation": "QQQ já tem 25% em chips.",
            "why_now": "Queda de 12% em um mês.",
            "risks": ["Demanda de IA desacelerar", "Restrições de exportação"],
            "how_to_follow": "Resultados da TSMC e da NVIDIA em novembro.",
            "sources": [{"title": "FactSet", "url": "https://insight.factset.com/x"}],
        }
    ]
    report["etf_holdings"] = [
        {
            "etf": qqq,
            "as_of": "2026-10-23",
            "source": "Invesco",
            "url": "https://www.invesco.com/qqq",
            "top": [
                {"name": "NVIDIA", "ticker": "NVDA", "weight": 0.1},
                {"name": "Microsoft", "ticker": "MSFT", "weight": 0.08},
            ],
        }
    ]
    report.update(overrides)
    return report


class TestFormatoV3:
    def test_jornal_chega_inteiro(self, api_client, folder):
        client, _user = api_client
        _write(folder, "2026-10-24.json", _v3())

        latest = client.get("/insights").json()["latest"]["report"]

        assert latest["schema_version"] == 3
        assert latest["market"][0]["direction"] == "DOWN"
        (opp,) = latest["opportunities"]
        assert opp["tickers"] == ["SMH", "QQQ"] and len(opp["risks"]) == 2
        assert latest["etf_holdings"][0]["top"][0]["weight"] == 0.1

    def test_v2_continua_valido_sem_os_campos_novos(self, api_client, folder):
        client, _user = api_client
        _write(folder, "2026-10-24.json", _report(schema_version=2))

        latest = client.get("/insights").json()["latest"]["report"]
        assert (latest["market"], latest["opportunities"], latest["etf_holdings"]) == ([], [], [])

    @pytest.mark.parametrize(
        "breaks",
        [
            lambda r: r["etf_holdings"][0]["top"][0].update(weight=8),  # percentual, não fração
            lambda r: r["etf_holdings"][0]["top"][0].update(weight=0),
            lambda r: r["etf_holdings"][0]["top"].append(
                {"name": "X", "ticker": "X", "weight": 0.9}
            ),
            lambda r: r["etf_holdings"][0]["top"].append(
                {"name": "Nvidia", "ticker": "nvda", "weight": 0.01}
            ),
            lambda r: r["etf_holdings"].append(
                copy.deepcopy(r["etf_holdings"][0]) | {"etf": "qqq"}
            ),
            lambda r: r["etf_holdings"][0].update(url="javascript:alert(1)"),
            lambda r: r["opportunities"][0].update(sources=[]),  # oportunidade sem fonte
            lambda r: r["opportunities"][0].update(risks=[]),  # sem risco
            lambda r: r["opportunities"][0].update(risks=["x" * 301]),
            lambda r: r["opportunities"][0].update(tickers=["X" * 21]),
            lambda r: r["opportunities"][0].update(acao="comprar"),  # campo a mais
            lambda r: r.update(opportunities=r["opportunities"] * 7),
            lambda r: r["market"][0].update(direction="SOBE"),
            lambda r: r.update(schema_version=5),
        ],
    )
    def test_arquivo_fora_do_formato_e_recusado(self, api_client, folder, breaks):
        client, _user = api_client
        report = _v3()
        breaks(report)
        _write(folder, "2026-10-24.json", report)

        body = client.get("/insights").json()
        assert body["latest"] is None
        assert [f["file_name"] for f in body["invalid_files"]] == ["2026-10-24.json"]


def _portfolio(client, db, user):
    inst = make_institution(db, name=f"Corretora LT {uuid.uuid4().hex[:6]}")
    account = make_typed_account(db, user, inst, "Conta", AccountType.BROKERAGE, "USD")
    tag = uuid.uuid4().hex[:4].upper()
    qqq = make_asset(db, f"Q{tag}", "ETF_US", "US", "USD")
    vnq = make_asset(db, f"V{tag}", "REIT", "US", "USD")
    cd = make_asset(db, f"C{tag}", "BOND", "US", "USD")
    when = (TODAY - timedelta(days=3)).isoformat()
    _buy(client, account, qqq, "1", "500", when)
    _buy(client, account, vnq, "1", "100", when)
    _buy(client, account, cd, "4", "100", when)
    return qqq.ticker, vnq.ticker


class TestEmpresasPorTrasDosEtfs:
    def test_pesos_da_carteira_vezes_composicao(self, api_client, db_session, folder):
        client, user = api_client
        qqq, vnq = _portfolio(client, db_session, user)
        _write(folder, "2026-10-24.json", _v3(qqq=qqq))

        body = client.get("/insights/lookthrough").json()

        assert body["report_date"] == "2026-10-24"
        (usd,) = body["currencies"]
        assert usd["currency_code"] == "USD"
        # QQQ é 50% da carteira (sem cotação: pelo custo) → NVIDIA 5%, MSFT 4%.
        assert [(c["ticker"], Decimal(c["weight"])) for c in usd["companies"]] == [
            ("NVDA", Decimal("0.05")),
            ("MSFT", Decimal("0.04")),
        ]
        assert usd["companies"][0]["via"][0]["ticker"] == qqq
        (fund,) = usd["funds"]
        assert (Decimal(fund["coverage"]), fund["source"]) == (Decimal("0.18"), "Invesco")
        assert usd["missing"] == [vnq]
        assert Decimal(usd["explained"]) == Decimal("0.09")

    def test_usa_a_ultima_analise_que_trouxe_composicao(self, api_client, db_session, folder):
        client, user = api_client
        qqq, _vnq = _portfolio(client, db_session, user)
        _write(folder, "2026-10-23.json", _v3(qqq=qqq))
        _write(folder, "2026-10-24.json", _report(schema_version=2))  # mais nova, sem composição

        body = client.get("/insights/lookthrough").json()
        assert body["report_date"] == "2026-10-23"
        assert body["currencies"][0]["companies"]

    def test_sem_analise_v3_lista_os_fundos_sem_composicao(self, api_client, db_session, folder):
        client, user = api_client
        qqq, vnq = _portfolio(client, db_session, user)

        body = client.get("/insights/lookthrough").json()
        assert body["report_date"] is None
        (usd,) = body["currencies"]
        assert usd["companies"] == [] and sorted(usd["missing"]) == sorted([qqq, vnq])
