"""Agente-2: relatório v2 (avaliação da carteira e indicadores com
número, data e fonte) e alertas da checagem de hora em hora.
"""

import json
from datetime import date, timedelta

import pytest

from app.core.config import settings
from tests.api.test_insights_api import _report, _write

TODAY = date.today()


@pytest.fixture()
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "insights_dir", tmp_path)
    return tmp_path


def _v2(**overrides):
    report = _report(schema_version=2)
    report["holdings"][0]["key_metrics"] = [
        {"code": "DIVIDEND_YIELD", "value": 0.0385, "as_of": "2026-10-14", "source": "Vanguard"},
        {"code": "P_FFO", "value": 17.2, "as_of": "2026-10-14", "source": "Nareit", "url": None},
    ]
    report["portfolio_review"] = {
        "overall": "Carteira concentrada em tecnologia americana.",
        "good": [
            {"title": "Custos baixos", "detail": "Taxas abaixo de 0,25%.", "tickers": ["SPY"]}
        ],
        "attention": [{"title": "Concentração", "detail": "QQQ é 43%.", "tickers": ["QQQ"]}],
        "risks": [],
        "improve": [{"title": "Pouca renda", "detail": "Rendimento sobre custo de 0,4%."}],
    }
    report.update(overrides)
    return report


def _alerts(*alerts):
    return {"schema_version": 1, "alerts": list(alerts)}


def _alert(alert_id="a1", detected="2026-10-14T10:05:00-03:00", **overrides):
    alert = {
        "id": alert_id,
        "detected_at": detected,
        "severity": "ALTA",
        "tickers": ["AAXJ"],
        "title": "Bolsa da Coreia cai 7%",
        "summary": "Venda forte de fabricantes de chips.",
        "why_it_matters": "AAXJ tem peso alto em Coreia.",
        "sources": [{"title": "AP", "url": "https://apnews.com/x"}],
    }
    alert.update(overrides)
    return alert


def _write_alerts(folder, day, content):
    path = folder / "alertas"
    path.mkdir(exist_ok=True)
    data = content if isinstance(content, str) else json.dumps(content)
    (path / f"{day.isoformat()}.json").write_text(data, encoding="utf-8")


class TestRelatorioV2:
    def test_avaliacao_e_indicadores_chegam_na_tela(self, api_client, folder):
        client, _user = api_client
        _write(folder, "2026-10-14.json", _v2())

        latest = client.get("/insights").json()["latest"]["report"]

        assert latest["schema_version"] == 2
        review = latest["portfolio_review"]
        assert [p["title"] for p in review["attention"]] == ["Concentração"]
        assert review["improve"][0]["tickers"] == []
        metrics = latest["holdings"][0]["key_metrics"]
        assert [(m["code"], m["value"]) for m in metrics] == [
            ("DIVIDEND_YIELD", 0.0385),
            ("P_FFO", 17.2),
        ]

    def test_relatorio_v1_continua_valendo_sem_os_campos_novos(self, api_client, folder):
        client, _user = api_client
        _write(folder, "2026-10-14.json", _report())

        latest = client.get("/insights").json()["latest"]["report"]

        assert latest["portfolio_review"] is None
        assert latest["holdings"][0]["key_metrics"] == []

    @pytest.mark.parametrize(
        ("metric", "error"),
        [
            ({"code": "DIVIDEND_YIELD", "value": 3.85}, None),  # fração ok (até 5)
            ({"code": "DIVIDEND_YIELD", "value": 38.5}, "fração"),
            ({"code": "INVENTADO", "value": 1}, "code"),
            ({"code": "PE_TTM", "value": float("nan")}, None),
        ],
    )
    def test_indicador_fora_do_formato_recusa_o_arquivo(self, api_client, folder, metric, error):
        client, _user = api_client
        report = _v2()
        report["holdings"][0]["key_metrics"] = [{"as_of": "2026-10-14", "source": "x", **metric}]
        text = json.dumps(report).replace("NaN", "NaN")
        _write(folder, "2026-10-14.json", text)

        body = client.get("/insights").json()

        if error is None and metric["value"] == metric["value"]:
            assert body["latest"] is not None
        else:
            assert body["latest"] is None
            assert body["invalid_files"][0]["file_name"] == "2026-10-14.json"
            if error:
                assert error in body["invalid_files"][0]["error"]

    def test_link_estranho_no_indicador_recusa(self, api_client, folder):
        client, _user = api_client
        report = _v2()
        report["holdings"][0]["key_metrics"][0]["url"] = "javascript:alert(1)"
        _write(folder, "2026-10-14.json", report)

        assert client.get("/insights").json()["latest"] is None

    def test_campo_desconhecido_na_avaliacao_recusa(self, api_client, folder):
        client, _user = api_client
        report = _v2()
        report["portfolio_review"]["comprar"] = ["QQQ"]
        _write(folder, "2026-10-14.json", report)

        assert client.get("/insights").json()["latest"] is None


class TestAlertas:
    def test_sem_pasta_nao_ha_alerta(self, api_client, folder):
        client, _user = api_client

        body = client.get("/insights/alerts").json()

        assert body == {"alerts": [], "unread_count": 0, "invalid_files": []}

    def test_lista_os_dos_ultimos_dias_mais_novo_primeiro(self, api_client, folder):
        client, _user = api_client
        _write_alerts(folder, TODAY, _alerts(_alert("hoje", f"{TODAY.isoformat()}T15:00:00-03:00")))
        _write_alerts(
            folder,
            TODAY - timedelta(days=1),
            _alerts(_alert("ontem", f"{(TODAY - timedelta(days=1)).isoformat()}T09:00:00-03:00")),
        )
        old = TODAY - timedelta(days=10)
        _write_alerts(folder, old, _alerts(_alert("velho", f"{old.isoformat()}T09:00:00-03:00")))

        body = client.get("/insights/alerts").json()

        assert [a["alert"]["id"] for a in body["alerts"]] == ["hoje", "ontem"]
        assert body["unread_count"] == 2
        assert body["alerts"][0]["day"] == TODAY.isoformat()
        assert [
            a["alert"]["id"] for a in client.get("/insights/alerts?days=30").json()["alerts"]
        ] == [
            "hoje",
            "ontem",
            "velho",
        ]

    def test_marcar_como_lido_e_lembrado(self, api_client, folder):
        client, _user = api_client
        _write_alerts(
            folder,
            TODAY,
            _alerts(_alert("a1"), _alert("a2", f"{TODAY.isoformat()}T11:00:00-03:00")),
        )

        after = client.post("/insights/alerts/a1/read").json()

        assert after["unread_count"] == 1
        assert {a["alert"]["id"]: a["read"] for a in after["alerts"]} == {"a1": True, "a2": False}
        assert client.get("/insights/alerts").json()["unread_count"] == 1
        assert json.loads((folder / "alertas" / "lidos.json").read_text())["read"] == ["a1"]

    def test_marcar_um_por_vez_guarda_os_dois(self, api_client, folder):
        client, _user = api_client
        _write_alerts(folder, TODAY, _alerts(_alert("a1"), _alert("a2")))

        client.post("/insights/alerts/a1/read")
        body = client.post("/insights/alerts/a2/read").json()

        assert body["unread_count"] == 0
        assert json.loads((folder / "alertas" / "lidos.json").read_text())["read"] == ["a1", "a2"]

    def test_arquivo_com_data_futura_nao_aparece(self, api_client, folder):
        client, _user = api_client
        _write_alerts(folder, TODAY + timedelta(days=1), _alerts(_alert("amanha")))

        assert client.get("/insights/alerts").json()["alerts"] == []

    def test_janela_tem_teto_de_60_dias(self, folder):
        from app.services import insights_service

        old = TODAY - timedelta(days=100)
        _write_alerts(folder, old, _alerts(_alert("antigo", f"{old.isoformat()}T09:00:00-03:00")))

        assert insights_service.list_alerts(days=1000, today=TODAY).alerts == []

    def test_marcar_todos(self, api_client, folder):
        client, _user = api_client
        _write_alerts(folder, TODAY, _alerts(_alert("a1"), _alert("a2")))

        body = client.post("/insights/alerts/read-all").json()

        assert body["unread_count"] == 0
        assert not (folder / "alertas" / ".lidos.json.tmp").exists()

    def test_arquivo_fora_do_formato_e_listado_e_os_outros_valem(self, api_client, folder):
        client, _user = api_client
        _write_alerts(folder, TODAY, _alerts(_alert("bom")))
        _write_alerts(folder, TODAY - timedelta(days=1), _alerts(_alert("ruim", severity="MEDIA")))

        body = client.get("/insights/alerts").json()

        assert [a["alert"]["id"] for a in body["alerts"]] == ["bom"]
        assert (
            body["invalid_files"][0]["file_name"]
            == f"{(TODAY - timedelta(days=1)).isoformat()}.json"
        )

    @pytest.mark.parametrize(
        "bad",
        [
            {"sources": []},  # alerta sem fonte não vale
            {"sources": [{"title": "x", "url": "ftp://x"}]},
            {"id": "com espaço"},
            {"tickers": ["X" * 21]},
            {"extra": 1},
        ],
    )
    def test_alerta_sem_fonte_ou_fora_do_formato_recusa(self, api_client, folder, bad):
        client, _user = api_client
        _write_alerts(folder, TODAY, _alerts(_alert(**bad)))

        body = client.get("/insights/alerts").json()

        assert body["alerts"] == []
        assert len(body["invalid_files"]) == 1

    def test_mesmo_alerta_em_dois_dias_aparece_uma_vez(self, api_client, folder):
        client, _user = api_client
        _write_alerts(folder, TODAY, _alerts(_alert("x")))
        _write_alerts(folder, TODAY - timedelta(days=1), _alerts(_alert("x")))

        assert len(client.get("/insights/alerts").json()["alerts"]) == 1

    def test_rota_de_alertas_nao_e_confundida_com_data(self, api_client, folder):
        client, _user = api_client

        assert client.get("/insights/alerts").status_code == 200
        assert client.get("/insights/2026-10-14").status_code == 404
