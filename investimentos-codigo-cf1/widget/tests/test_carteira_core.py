"""Widget: formatação, sparkline, estado e configuração (sem interface)."""

import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import carteira_core as core

NOW = datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)


class TestFormatacao:
    def test_dinheiro_no_padrao_brasileiro_na_moeda_do_bloco(self):
        assert core.money("13275.6", "BRL") == "R$ 13.275,60"
        assert core.money("506.86", "USD") == "US$ 506,86"
        assert core.money("-13.6", "BRL") == "-R$ 13,60"
        assert core.money("1234567.891", "BRL") == "R$ 1.234.567,89"
        assert core.money(None, "BRL") == "—"
        assert core.money("abc", "BRL") == "—"
        assert core.money("10", "JPY") == "JPY 10,00"

    def test_sinal_explicito_em_ganho_e_perda(self):
        assert core.signed_money("5.62", "USD") == "+US$ 5,62"
        assert core.signed_money("-12.3", "USD") == "-US$ 12,30"
        assert core.signed_money("0", "USD") == "US$ 0,00"
        assert core.signed_percent("0.0112") == "+1,12%"
        assert core.signed_percent("-0.0245") == "-2,45%"
        assert core.signed_percent("0") == "0,00%"
        assert core.signed_percent(None) == "—"

    def test_tom_e_data_curta(self):
        assert core.tone("1") == "up"
        assert core.tone("-0.01") == "down"
        assert core.tone("0") == "flat"
        assert core.tone(None) == "flat"
        assert core.short_date("2026-10-09") == "09/10"
        assert core.short_date(None) == ""


class TestSparkline:
    def test_maior_valor_no_topo_e_menor_embaixo(self):
        points = core.spark_points(["100", "150", "50"], 106, 46, pad=3)

        assert points == [(3.0, 23.0), (53.0, 3.0), (103.0, 43.0)]

    def test_serie_constante_fica_no_meio(self):
        assert [y for _, y in core.spark_points(["7", "7", "7"], 100, 40)] == [20, 20, 20]

    def test_menos_de_dois_pontos_nao_desenha(self):
        assert core.spark_points(["7"], 100, 40) == []
        assert core.spark_points([], 100, 40) == []


class TestEstado:
    def test_cotacao_velha_pede_busca(self):
        fresh = (NOW - timedelta(minutes=5)).isoformat()
        old = (NOW - timedelta(minutes=16)).isoformat()

        assert core.quotes_need_refresh(fresh, NOW) is False
        assert core.quotes_need_refresh(old, NOW) is True
        assert core.quotes_need_refresh(None, NOW) is True
        assert core.quotes_need_refresh("lixo", NOW) is True
        assert core.quotes_need_refresh("2026-10-09T17:50:00Z", NOW) is False

    def test_estado_da_bolinha(self):
        assert core.freshness(None, offline=True).level == "offline"
        assert core.freshness({"quotes_refreshed_at": None}, False, NOW).level == "stale"
        fresh = {"quotes_refreshed_at": (NOW - timedelta(minutes=1)).isoformat()}
        assert core.freshness(fresh, False, NOW).level == "ok"
        old = {"quotes_refreshed_at": (NOW - timedelta(hours=2)).isoformat()}
        state = core.freshness(old, False, NOW)
        assert state.level == "stale" and "buscando" in state.label

    def test_real_primeiro_dolar_depois(self):
        summary = {
            "totals_by_currency": [
                {"currency_code": "USD"},
                {"currency_code": "EUR"},
                {"currency_code": "BRL"},
            ]
        }

        assert [b["currency_code"] for b in core.blocks(summary)] == ["BRL", "USD", "EUR"]
        assert core.blocks(None) == []


class TestConfiguracao:
    def test_salva_e_le_so_as_chaves_conhecidas(self, tmp_path):
        path = tmp_path / "x" / "config.json"
        core.save_config({**core.DEFAULTS, "x": 10, "y": 20, "compact": True}, path)
        path.write_text(json.dumps({**json.loads(path.read_text()), "intruso": 1}))

        config = core.load_config(path)

        assert config["x"] == 10 and config["compact"] is True
        assert "intruso" not in config

    def test_arquivo_ausente_ou_quebrado_usa_o_padrao(self, tmp_path):
        broken = tmp_path / "config.json"
        broken.write_text("{nao é json")

        assert core.load_config(tmp_path / "nada.json") == core.DEFAULTS
        assert core.load_config(broken) == core.DEFAULTS

    def test_comando_do_backend_usa_o_venv_do_projeto(self, tmp_path):
        widget = tmp_path / "widget"
        widget.mkdir()
        assert core.backend_command(widget) is None

        python = tmp_path / "backend" / ".venv" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.write_text("")
        command, cwd = core.backend_command(widget)

        assert command[:3] == [str(python), "-m", "uvicorn"]
        assert command[-4:] == ["--host", "127.0.0.1", "--port", "8000"]
        assert cwd == tmp_path / "backend"


class TestHttp:
    def test_backend_desligado_vira_erro_proprio(self, monkeypatch):
        monkeypatch.setattr(core, "API", "http://127.0.0.1:9")

        try:
            core.fetch_summary(timeout=1)
        except core.BackendOffline:
            pass
        else:
            raise AssertionError("deveria acusar backend desligado")


def test_decimal_tolerante():
    assert core._decimal("1.5") == Decimal("1.5")
    assert core._decimal(None) is None


def _index(news, report_date="2026-10-13"):
    return {
        "latest": {
            "report_date": report_date,
            "report": {"headline": "Manchete do dia", "news": news},
        },
        "history": [],
        "invalid_files": [],
        "snapshot_written_at": None,
    }


def _news(n, **extra):
    return {
        "ticker": "QQQ",
        "topic": "Tema",
        "title": f"Notícia {n}",
        "source": "Fonte",
        "url": f"https://exemplo.com/{n}",
        "published_at": "2026-10-12",
        "summary": "resumo",
        **extra,
    }


class TestNoticias:
    def test_primeiras_noticias_na_ordem_do_relatorio(self):
        items = core.news_items(_index([_news(i) for i in range(6)]))

        assert [i["title"] for i in items] == ["Notícia 0", "Notícia 1", "Notícia 2", "Notícia 3"]
        assert items[0] == {
            "ticker": "QQQ",
            "title": "Notícia 0",
            "source": "Fonte",
            "date": "12/10",
            "url": "https://exemplo.com/0",
        }

    def test_sem_ticker_usa_o_tema_e_link_estranho_nao_vira_clique(self):
        (item,) = core.news_items(_index([_news(1, ticker=None, url="javascript:alert(1)")]))

        assert item["ticker"] == "Tema"
        assert item["url"] is None

    def test_sem_analise_nada_e_mostrado(self):
        assert core.news_items(None) == []
        assert core.news_items({"latest": None}) == []
        assert core.headline(None) is None
        assert core.report_label(None) == ("sem análise ainda", True)

    def test_rotulo_marca_analise_velha(self):
        from datetime import date

        today = date(2026, 10, 13)
        assert core.report_label(_index([]), today) == ("análise de 13/10", False)
        assert core.report_label(_index([], "2026-10-12"), today) == ("análise de 12/10", False)
        assert core.report_label(_index([], "2026-10-11"), today) == ("análise de 11/10", True)
        assert core.headline(_index([])) == "Manchete do dia"

    def test_noticias_ligadas_por_padrao(self, tmp_path):
        assert core.load_config(tmp_path / "nao-existe.json")["news"] is True


# --- Esconder valores e alertas -------------------------------------------------


def test_valor_escondido_nao_mostra_numero_nem_sinal():
    assert core.money("1234.56", "BRL", hidden=True) == "R$ •••••"
    assert core.money("-13.60", "USD", hidden=True) == "US$ •••••"
    assert core.signed_money("10.70", "USD", hidden=True) == "US$ •••••"
    assert core.signed_money("-5", "BRL", hidden=True) == "R$ •••••"
    # Sem valor continua "—"; sem esconder, igual a antes.
    assert core.money(None, "BRL", hidden=True) == "—"
    assert core.signed_money("10.70", "USD") == "+US$ 10,70"


def _alerts(*items):
    return {
        "alerts": [
            {"day": "2026-10-15", "read": read, "alert": {"id": i, "severity": sev, "title": f"T{i}"}}
            for i, sev, read in items
        ],
        "unread_count": sum(1 for *_, read in items if not read),
        "invalid_files": [],
    }


def test_linha_de_alerta():
    assert core.alert_line(None) is None
    assert core.alert_line(_alerts(("a", "ALTA", True))) is None
    assert core.alert_line(_alerts(("a", "ALTA", False))) == ("⚠ Ta", "stale")
    # O mais novo vem primeiro; lidos não contam; um CRÍTICO deixa vermelho.
    line = core.alert_line(_alerts(("a", "ALTA", False), ("b", "ALTA", True), ("c", "CRITICA", False)))
    assert line == ("⚠ Ta (+1)", "offline")


def test_configuracao_padrao_nao_esconde(tmp_path):
    assert core.load_config(tmp_path / "nada.json")["hidden"] is False
