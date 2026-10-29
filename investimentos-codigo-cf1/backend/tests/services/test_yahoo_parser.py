"""Análises-1: leitura da resposta da fonte de cotações."""

from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.services.market_data.yahoo import (
    MarketDataError,
    YahooChartProvider,
    parse_chart,
    yahoo_symbol,
)

# 2026-10-05 13:30 UTC, 2026-10-06 13:30 UTC, 2026-10-07 13:30 UTC
T1, T2, T3 = 1791207000, 1791293400, 1791379800
NY_OFFSET = -14400


def _payload(
    closes=(770.1, None, 777.14), currency="USD", live=None, live_time=None, gmtoffset=NY_OFFSET
):
    meta = {"currency": currency, "symbol": "SPY", "gmtoffset": gmtoffset}
    if live is not None:
        meta["regularMarketPrice"] = live
        meta["regularMarketTime"] = live_time
    return {
        "chart": {
            "result": [
                {
                    "meta": meta,
                    "timestamp": [T1, T2, T3],
                    "indicators": {"quote": [{"close": list(closes)}]},
                }
            ],
            "error": None,
        }
    }


class TestParse:
    def test_le_fechamentos_na_data_local_da_bolsa_e_ignora_barra_sem_preco(self):
        series = parse_chart(_payload())

        assert series.currency == "USD"
        assert [(b.day, b.close) for b in series.bars] == [
            (date(2026, 10, 5), Decimal("770.1000")),
            (date(2026, 10, 7), Decimal("777.1400")),
        ]

    def test_data_usa_o_fuso_da_bolsa_e_nao_o_utc(self):
        # 03:00 UTC de 08/10 ainda é 07/10 em Nova York (−4h).
        payload = _payload(closes=(1.0,), gmtoffset=NY_OFFSET)
        payload["chart"]["result"][0]["timestamp"] = [1791428400]

        assert parse_chart(payload).bars[0].day == date(2026, 10, 7)

    def test_preco_do_pregao_em_andamento_substitui_a_barra_do_dia(self):
        series = parse_chart(_payload(live=779.5, live_time=T3 + 3600))

        assert series.bars[-1] == series.bars[-1].__class__(date(2026, 10, 7), Decimal("779.5000"))
        assert len(series.bars) == 2

    def test_preco_do_pregao_de_um_dia_novo_vira_uma_barra_nova(self):
        series = parse_chart(_payload(live=780.0, live_time=T3 + 86400))

        assert series.bars[-1].day == date(2026, 10, 8)
        assert len(series.bars) == 3

    def test_preco_nao_positivo_ou_invalido_e_ignorado(self):
        payload = _payload(closes=(0, "abc", 10.0))
        payload["chart"]["result"][0]["indicators"]["quote"][0]["close"] = [-5, True, 10.0]

        assert [b.close for b in parse_chart(payload).bars] == [Decimal("10.0000")]
        assert [b.close for b in parse_chart(_payload(closes=(0, "abc", 10.0))).bars] == [
            Decimal("10.0000")
        ]

    def test_erro_da_fonte_vira_erro(self):
        payload = {
            "chart": {
                "result": None,
                "error": {"code": "Not Found", "description": "No data found"},
            }
        }

        with pytest.raises(MarketDataError, match="No data found"):
            parse_chart(payload)

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"chart": {"result": [], "error": None}},
            {"chart": {"result": [{"timestamp": []}], "error": None}},
            "texto",
        ],
    )
    def test_formato_inesperado_vira_erro(self, payload):
        with pytest.raises(MarketDataError):
            parse_chart(payload)

    def test_sem_moeda_vira_erro(self):
        with pytest.raises(MarketDataError, match="moeda"):
            parse_chart(_payload(currency=""))

    def test_nenhum_preco_valido_vira_erro(self):
        with pytest.raises(MarketDataError, match="nenhum preço"):
            parse_chart(_payload(closes=(None, None, None)))


class TestSimbolo:
    @pytest.mark.parametrize(
        ("ticker", "country", "cls", "currency", "expected"),
        [
            ("SPY", "US", "ETF_US", "USD", "SPY"),
            (" brk.b ", "US", "STOCK_US", "USD", "BRK-B"),
            ("PETR4", "BR", "STOCK_BR", "BRL", "PETR4.SA"),
            ("HGLG11", "BR", "FII", "BRL", "HGLG11.SA"),
            ("BTC", "US", "CRYPTO", "USD", "BTC-USD"),
            ("VNQ", "US", "REIT", "USD", "VNQ"),
        ],
    )
    def test_codigo_na_fonte(self, ticker, country, cls, currency, expected):
        assert yahoo_symbol(ticker, country, cls, currency) == expected

    @pytest.mark.parametrize(
        ("ticker", "country", "cls"),
        [
            ("CDB-X", "BR", "CDB"),
            ("TESOURO", "BR", "TESOURO_DIRETO"),
            ("FUNDO", "BR", "FUND"),
            ("SAP", "DE", "STOCK_US"),
            ("  ", "US", "ETF_US"),
        ],
    )
    def test_sem_fonte_automatica(self, ticker, country, cls):
        assert yahoo_symbol(ticker, country, cls, "USD") is None


class TestProvedor:
    def _provider(self, handler):
        return YahooChartProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))

    def test_pede_um_ano_diario_do_codigo(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            return httpx.Response(200, json=_payload())

        series = self._provider(handler).fetch("SPY")

        assert "/v8/finance/chart/SPY" in seen["url"]
        assert "range=1y" in seen["url"] and "interval=1d" in seen["url"]
        assert len(series.bars) == 2

    @pytest.mark.parametrize(
        ("status", "message"),
        [(404, "não encontrado"), (500, "respondeu 500"), (429, "respondeu 429")],
    )
    def test_status_de_erro_vira_erro(self, status, message):
        provider = self._provider(lambda request: httpx.Response(status, text="x"))

        with pytest.raises(MarketDataError, match=message):
            provider.fetch("SPY")

    def test_corpo_que_nao_e_json_vira_erro(self):
        provider = self._provider(lambda request: httpx.Response(200, text="<html>"))

        with pytest.raises(MarketDataError, match="JSON"):
            provider.fetch("SPY")

    def test_falha_de_rede_vira_erro(self):
        def handler(request):
            raise httpx.ConnectError("sem rede")

        with pytest.raises(MarketDataError, match="sem resposta"):
            self._provider(handler).fetch("SPY")
