"""Anotações, fontes de leitura e o que delas vai (ou não) para o Claude."""

import json

import pytest

from app.core.config import settings
from tests.api.test_insights_api import _report, _write

NOTE = {
    "title": "Tese do QQQ",
    "body": "Esperar a temporada de balanços antes de aportar mais.",
    "tickers": ["qqq", " spy ", "QQQ"],
}


@pytest.fixture()
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "insights_dir", tmp_path)
    return tmp_path


class TestAnotacoes:
    def test_cria_lista_edita_e_apaga(self, api_client):
        client, _user = api_client
        created = client.post("/notes", json=NOTE)
        assert created.status_code == 201, created.text
        note = created.json()
        assert note["tickers"] == ["QQQ", "SPY"]  # maiúsculas, sem repetir
        assert note["share_with_claude"] is False and note["pinned"] is False

        edited = client.put(
            f"/notes/{note['id']}", json={**NOTE, "pinned": True, "body": "Mudei de ideia."}
        )
        assert edited.json()["body"] == "Mudei de ideia." and edited.json()["pinned"] is True

        assert [n["id"] for n in client.get("/notes").json()] == [note["id"]]
        assert client.delete(f"/notes/{note['id']}").status_code == 204
        assert client.get("/notes").json() == []
        assert client.delete(f"/notes/{note['id']}").status_code == 404

    def test_trecho_destacado_com_a_fonte(self, api_client):
        client, _user = api_client
        body = {
            "quote": "O Fed manteve os juros.",
            "source_title": "Jornal de 27/10/2026",
            "source_url": "https://example.com/x",
        }
        note = client.post("/notes", json=body).json()
        assert (note["quote"], note["body"], note["title"]) == ("O Fed manteve os juros.", "", None)

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"title": "   ", "body": "  "},
            {"body": "x", "source_url": "javascript:alert(1)"},
            {"body": "x", "tickers": ["A" * 21]},
            {"body": "x", "tickers": ["A,B"]},
            {"body": "x", "extra": 1},
        ],
    )
    def test_recusa_o_que_nao_serve(self, api_client, body):
        client, _user = api_client
        assert client.post("/notes", json=body).status_code == 422

    def test_fixadas_primeiro_e_busca(self, api_client):
        client, _user = api_client
        old = client.post("/notes", json={"body": "nota antiga sobre VNQ", "pinned": True}).json()
        new = client.post("/notes", json={"body": "nota nova", "tickers": ["AAXJ"]}).json()
        assert [n["id"] for n in client.get("/notes").json()] == [old["id"], new["id"]]
        assert [n["id"] for n in client.get("/notes", params={"search": "aaxj"}).json()] == [
            new["id"]
        ]
        assert [n["id"] for n in client.get("/notes", params={"search": "vnq"}).json()] == [
            old["id"]
        ]


class TestFontesDeLeitura:
    def test_cadastra_edita_e_remove(self, api_client):
        client, _user = api_client
        src = client.post(
            "/reading-sources",
            json={
                "name": "World Reports",
                "url": "https://worldreports.io/brasil/pt/",
                "focus": "pranchas do Brasil",
            },
        )
        assert src.status_code == 201, src.text
        sid = src.json()["id"]
        off = client.put(
            f"/reading-sources/{sid}",
            json={"name": "WR", "url": "https://worldreports.io", "active": False},
        )
        assert off.json()["active"] is False and off.json()["focus"] is None
        assert client.delete(f"/reading-sources/{sid}").status_code == 204
        assert client.get("/reading-sources").json() == []

    def test_link_precisa_ser_http(self, api_client):
        client, _user = api_client
        assert (
            client.post("/reading-sources", json={"name": "x", "url": "ftp://x"}).status_code == 422
        )
        assert client.post("/reading-sources", json={"name": "x", "url": ""}).status_code == 422


class TestOQueVaiParaOClaude:
    def test_so_notas_marcadas_e_fontes_ativas_vao_no_retrato(self, api_client, folder):
        client, _user = api_client
        client.post("/notes", json={"body": "PRIVADA não sai daqui"})
        client.post(
            "/notes",
            json={
                "title": "Para o Claude",
                "body": "Estou pensando em cripto.",
                "share_with_claude": True,
            },
        )
        client.post("/reading-sources", json={"name": "Ativa", "url": "https://a.example.com"})
        client.post(
            "/reading-sources",
            json={"name": "Pausada", "url": "https://b.example.com", "active": False},
        )

        assert client.post("/insights/snapshot").status_code == 200
        snapshot = json.loads((folder / "carteira.json").read_text(encoding="utf-8"))

        assert [s["name"] for s in snapshot["reading_sources"]] == ["Ativa"]
        assert [n["title"] for n in snapshot["notes_for_claude"]] == ["Para o Claude"]
        assert "PRIVADA" not in json.dumps(snapshot, ensure_ascii=False)

    def test_conversa_leva_so_as_marcadas(self, api_client, folder):
        client, _user = api_client
        client.post("/notes", json={"body": "PRIVADA não sai daqui"})
        client.post(
            "/notes",
            json={
                "quote": "Trecho lido",
                "body": "Minha dúvida.",
                "tickers": ["QQQ"],
                "share_with_claude": True,
            },
        )

        text = client.get("/insights/chat-context").json()["text"]

        assert "## Minhas anotações (marcadas para conversar com o Claude)" in text
        assert "[QQQ]" in text and "“Trecho lido” Minha dúvida." in text
        assert "PRIVADA" not in text

    def test_sem_nota_marcada_nao_ha_secao(self, api_client, folder):
        client, _user = api_client
        client.post("/notes", json={"body": "só minha"})
        assert "Minhas anotações" not in client.get("/insights/chat-context").json()["text"]


class TestOutrasLeituras:
    def test_relatorio_v4_traz_as_leituras(self, api_client, folder):
        client, _user = api_client
        report = _report(schema_version=4)
        report["papers"] = [
            {
                "source": "World Reports",
                "title": "Prancha nova: crédito e endividamento",
                "url": "https://worldreports.io/brasil/pt/",
                "published_at": "2026-10-22",
                "summary": "Resumo.",
                "takeaways": ["Ponto 1", "Ponto 2"],
                "relation": None,
            }
        ]
        _write(folder, "2026-10-28.json", report)
        latest = client.get("/insights").json()["latest"]["report"]
        assert latest["papers"][0]["takeaways"] == ["Ponto 1", "Ponto 2"]

    @pytest.mark.parametrize(
        "paper",
        [
            {"source": "x", "title": "t", "url": "javascript:x", "summary": "s"},
            {
                "source": "x",
                "title": "t",
                "url": "https://x",
                "summary": "s",
                "takeaways": ["a" * 301],
            },
            {
                "source": "x",
                "title": "t",
                "url": "https://x",
                "summary": "s",
                "takeaways": ["a"] * 6,
            },
            {"source": "x", "title": "t", "url": "https://x", "summary": "s", "ordem": "compre"},
        ],
    )
    def test_leitura_fora_do_formato_recusa_o_arquivo(self, api_client, folder, paper):
        client, _user = api_client
        report = _report(schema_version=4)
        report["papers"] = [paper]
        _write(folder, "2026-10-28.json", report)
        assert client.get("/insights").json()["latest"] is None
