"""Análises-2: troca de arquivos com o Claude — retrato da carteira e
relatórios diários.
"""

import json
import uuid
from datetime import date, timedelta

import pytest

from app.core.config import settings
from app.models.enums import AccountType
from tests.cashflow_helpers import make_typed_account
from tests.test_persistence import make_asset, make_institution

TODAY = date.today()


def _report(**overrides):
    report = {
        "schema_version": 1,
        "generated_at": "2026-10-09T08:00:00-03:00",
        "headline": "Juros americanos seguem pressionando tecnologia",
        "summary": [
            "O Fed sinalizou mais uma alta.",
            "O S&P 500 está perto da média histórica de P/L.",
        ],
        "holdings": [
            {
                "ticker": "QQQ",
                "signal": "ATENCAO",
                "reading": "P/L acima da mediana histórica.",
                "metrics": [{"label": "P/L", "value": "29,4", "context": "mediana 23,2"}],
                "sources": [{"title": "GuruFocus", "url": "https://www.gurufocus.com/x"}],
            }
        ],
        "news": [
            {
                "ticker": "SPY",
                "topic": "Mercado americano",
                "title": "Índices recuam de recordes",
                "source": "Yahoo Finance",
                "url": "https://finance.yahoo.com/x",
                "published_at": "2026-10-07",
                "summary": "Juros longos subiram.",
            }
        ],
        "research": [
            {
                "house": "FactSet",
                "title": "Earnings Insight",
                "url": "https://www.factset.com/earningsinsight",
                "published_at": "2026-10-02",
                "summary": "P/L projetado 19,0.",
                "relevance": "SPY",
            }
        ],
        "watch": [
            {"topic": "Reunião do Fed", "why": "Juros mexem em crescimento.", "date": "2026-10-28"}
        ],
        "disclaimer": "Leitura de dados públicos, não recomendação.",
    }
    report.update(overrides)
    return report


@pytest.fixture()
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "insights_dir", tmp_path)
    return tmp_path


def _write(folder, name, content):
    reports = folder / "relatorios"
    reports.mkdir(exist_ok=True)
    data = content if isinstance(content, str) else json.dumps(content)
    (reports / name).write_text(data, encoding="utf-8")


class TestRelatorios:
    def test_sem_pasta_nao_ha_relatorio(self, api_client, folder):
        client, _ = api_client

        body = client.get("/insights").json()

        assert body == {
            "latest": None,
            "history": [],
            "invalid_files": [],
            "snapshot_written_at": None,
        }

    def test_mais_recente_e_historico_em_ordem(self, api_client, folder):
        client, _ = api_client
        _write(folder, "2026-10-08.json", _report(headline="Ontem"))
        _write(folder, "2026-10-09.json", _report(headline="Hoje"))

        body = client.get("/insights").json()

        assert body["latest"]["report_date"] == "2026-10-09"
        assert body["latest"]["report"]["headline"] == "Hoje"
        assert [(h["report_date"], h["headline"]) for h in body["history"]] == [
            ("2026-10-09", "Hoje"),
            ("2026-10-08", "Ontem"),
        ]
        assert body["latest"]["report"]["holdings"][0]["metrics"][0]["value"] == "29,4"

    def test_le_um_dia_especifico_e_dia_sem_relatorio_e_404(self, api_client, folder):
        client, _ = api_client
        _write(folder, "2026-10-08.json", _report(headline="Ontem"))

        assert client.get("/insights/2026-10-08").json()["report"]["headline"] == "Ontem"
        response = client.get("/insights/2026-10-01")
        assert response.status_code == 404
        assert "01/10/2026" in response.json()["detail"]

    @pytest.mark.parametrize(
        ("overrides", "expected"),
        [
            ({"news": [_report()["news"][0] | {"url": "javascript:alert(1)"}]}, "http"),
            ({"research": [_report()["research"][0] | {"url": "ftp://x"}]}, "http"),
            ({"holdings": [_report()["holdings"][0] | {"signal": "COMPRAR"}]}, "signal"),
            ({"campo_estranho": 1}, "campo_estranho"),
            ({"schema_version": 5}, "schema_version"),
            ({"summary": []}, "summary"),
            ({"headline": ""}, "headline"),
            ({"summary": ["x" * 2001]}, "summary"),
        ],
    )
    def test_arquivo_fora_do_formato_e_recusado_e_listado(
        self, api_client, folder, overrides, expected
    ):
        client, _ = api_client
        _write(folder, "2026-10-08.json", _report(headline="Válido"))
        _write(folder, "2026-10-09.json", _report(**overrides))

        body = client.get("/insights").json()

        assert body["latest"]["report_date"] == "2026-10-08"
        assert [f["file_name"] for f in body["invalid_files"]] == ["2026-10-09.json"]
        assert expected in body["invalid_files"][0]["error"]
        response = client.get("/insights/2026-10-09")
        assert response.status_code == 404
        assert "formato inválido" in response.json()["detail"]

    def test_json_quebrado_e_arquivo_grande_demais_sao_recusados(self, api_client, folder):
        client, _ = api_client
        _write(folder, "2026-10-08.json", "{ quebrado")
        _write(folder, "2026-10-09.json", _report(headline="Válido"))
        _write(folder, "2026-10-10.json", json.dumps(_report()) + " " * (512 * 1024))

        body = client.get("/insights").json()

        invalid = {f["file_name"]: f["error"] for f in body["invalid_files"]}
        assert set(invalid) == {"2026-10-08.json", "2026-10-10.json"}
        assert "KB" in invalid["2026-10-10.json"]
        assert body["latest"]["report_date"] == "2026-10-09"

    def test_arquivos_com_outro_nome_sao_ignorados(self, api_client, folder):
        client, _ = api_client
        _write(folder, "rascunho.json", _report())
        _write(folder, "2026-10-08.txt", _report())
        _write(folder, "../fora.json", _report())

        body = client.get("/insights").json()

        assert body["latest"] is None
        assert body["invalid_files"] == []

    def test_data_impossivel_no_nome_e_recusada(self, api_client, folder):
        client, _ = api_client
        _write(folder, "2026-02-30.json", _report())

        body = client.get("/insights").json()

        assert body["latest"] is None
        assert body["invalid_files"][0]["file_name"] == "2026-02-30.json"


class TestRetrato:
    def test_grava_o_retrato_com_posicoes_e_analises_sem_dados_pessoais(
        self, api_client, db_session, folder
    ):
        client, user = api_client
        inst = make_institution(db_session, name=f"Corretora A2 {uuid.uuid4().hex[:6]}")
        account = make_typed_account(
            db_session, user, inst, "Inter US", AccountType.BROKERAGE, "USD"
        )
        spy = make_asset(db_session, f"SPY{uuid.uuid4().hex[:4].upper()}", "ETF_US", "US", "USD")
        when = (TODAY - timedelta(days=5)).isoformat()
        for body in (
            {
                "transaction_type": "DEPOSIT",
                "gross_amount": "100",
                "currency_code": "USD",
                "transaction_date": when,
            },
            {
                "transaction_type": "BUY",
                "asset_id": str(spy.id),
                "quantity": "0.1",
                "unit_price": "700",
                "gross_amount": "70",
                "currency_code": "USD",
                "transaction_date": when,
            },
        ):
            assert (
                client.post(
                    "/transactions", json={"account_id": str(account.id), **body}
                ).status_code
                == 201
            )
        client.put(
            f"/assets/{spy.id}/prices",
            json={"price_date": (TODAY - timedelta(days=1)).isoformat(), "price": "777.14"},
        )

        response = client.post("/insights/snapshot")

        assert response.status_code == 200, response.text
        assert response.json()["positions"] == 1
        snapshot = json.loads((folder / "carteira.json").read_text(encoding="utf-8"))
        (position,) = snapshot["positions"]
        assert position["ticker"] == spy.ticker
        assert position["asset_class"] == "ETF_US"
        assert position["market_value"] == "77.714000000"[
            : len(position["market_value"])
        ] or position["market_value"].startswith("77.714")
        (usd,) = snapshot["currencies"]
        assert usd["currency"] == "USD"
        assert usd["scenarios"]["until"] == date(TODAY.year, 12, 31).isoformat()
        assert usd["concentration"]["by_asset"][0]["weight"] == "1.0000"
        raw = (folder / "carteira.json").read_text(encoding="utf-8")
        assert user.email not in raw
        assert user.full_name not in raw
        assert str(account.id) not in raw
        assert not (folder / ".carteira.json.tmp").exists()
        assert client.get("/insights").json()["snapshot_written_at"] is not None

    def test_retrato_de_carteira_vazia(self, api_client, folder):
        client, _ = api_client

        assert client.post("/insights/snapshot").json()["positions"] == 0
        snapshot = json.loads((folder / "carteira.json").read_text(encoding="utf-8"))
        assert snapshot["positions"] == [] and snapshot["currencies"] == []

    def test_pasta_inacessivel_vira_erro_claro(self, api_client, folder, monkeypatch):
        client, _ = api_client
        blocker = folder / "arquivo"
        blocker.write_text("x")
        monkeypatch.setattr(settings, "insights_dir", blocker / "sub")

        response = client.post("/insights/snapshot")

        assert response.status_code == 500
        assert "retrato da carteira" in response.json()["detail"]
