"""Leitura de cotações do endpoint público de gráficos do Yahoo Finance.

A fonte não tem contrato nem garantia: a resposta é lida com
desconfiança. Moeda diferente da do ativo, preço não positivo ou corpo
fora do formato esperado viram erro — nunca uma cotação gravada.

Datas: o Yahoo informa instantes em segundos desde a época e o desvio
do fuso da bolsa (`gmtoffset`). A data de cada barra é a data LOCAL da
bolsa, calculada com esse desvio — sem depender da base de fusos do
sistema operacional (que o Windows não traz).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Protocol

import httpx

_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_PRICE_PLACES = Decimal("0.0001")

# Classes com preço de bolsa. Renda fixa e fundos não têm cotação aqui.
EXCHANGE_TRADED_CLASSES = frozenset(
    {"STOCK_BR", "FII", "ETF_BR", "BDR", "STOCK_US", "ETF_US", "REIT", "CRYPTO"}
)


class MarketDataError(Exception):
    """A fonte não respondeu, ou respondeu algo que não é uma cotação."""


@dataclass(frozen=True)
class QuoteBar:
    day: date
    close: Decimal


@dataclass(frozen=True)
class QuoteSeries:
    """Fechamentos diários em ordem de data. A última barra pode ser o
    preço do pregão em andamento (é substituída a cada atualização).
    """

    symbol: str
    currency: str
    bars: list[QuoteBar]


class QuoteProvider(Protocol):
    def fetch(self, symbol: str) -> QuoteSeries: ...


def yahoo_symbol(
    ticker: str, country: str, asset_class_code: str, currency_code: str
) -> str | None:
    """Código do ativo no Yahoo, ou None quando não há fonte automática."""
    if asset_class_code not in EXCHANGE_TRADED_CLASSES:
        return None
    clean = ticker.strip().upper()
    if not clean:
        return None
    if asset_class_code == "CRYPTO":
        return f"{clean}-{currency_code}"
    if country == "BR":
        return f"{clean}.SA"
    if country == "US":
        # BRK.B na bolsa é BRK-B no Yahoo.
        return clean.replace(".", "-")
    return None


def _price(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        price = Decimal(str(value)).quantize(_PRICE_PLACES)
    except (InvalidOperation, ValueError):
        return None
    return price if price > 0 else None


def _local_day(epoch_seconds: object, gmtoffset: int) -> date:
    if not isinstance(epoch_seconds, int | float) or isinstance(epoch_seconds, bool):
        raise MarketDataError("instante inválido na resposta da fonte")
    return (datetime.fromtimestamp(epoch_seconds, UTC) + timedelta(seconds=gmtoffset)).date()


def parse_chart(payload: object) -> QuoteSeries:
    """Converte a resposta do endpoint de gráficos em fechamentos
    diários. Barras sem preço são ignoradas; o preço do pregão em
    andamento (`regularMarketPrice`) substitui a barra do seu dia.
    """
    try:
        chart = payload["chart"]  # type: ignore[index]
        error = chart.get("error")
        if error:
            description = error.get("description") if isinstance(error, dict) else str(error)
            raise MarketDataError(f"a fonte recusou o código: {description}")
        results = chart.get("result") or []
        if not results:
            raise MarketDataError("a fonte não devolveu dados para este código")
        result = results[0]
        meta = result["meta"]
        currency = str(meta.get("currency") or "").upper()
        symbol = str(meta.get("symbol") or "")
        gmtoffset = int(meta.get("gmtoffset") or 0)
        timestamps = result.get("timestamp") or []
        closes = ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    except (KeyError, TypeError, AttributeError, IndexError, ValueError) as exc:
        raise MarketDataError("resposta da fonte fora do formato esperado") from exc
    if len(currency) != 3:
        raise MarketDataError("a fonte não informou a moeda da cotação")

    by_day: dict[date, Decimal] = {}
    for when, close in zip(timestamps, closes, strict=False):
        price = _price(close)
        if price is not None:
            by_day[_local_day(when, gmtoffset)] = price

    live = _price(meta.get("regularMarketPrice"))
    live_time = meta.get("regularMarketTime")
    if live is not None and live_time is not None:
        by_day[_local_day(live_time, gmtoffset)] = live

    if not by_day:
        raise MarketDataError("a fonte não devolveu nenhum preço válido")
    bars = [QuoteBar(day=day, close=by_day[day]) for day in sorted(by_day)]
    return QuoteSeries(symbol=symbol, currency=currency, bars=bars)


class YahooChartProvider:
    """Busca um ano de fechamentos diários de um código."""

    def __init__(self, client: httpx.Client | None = None, timeout: float = 10.0) -> None:
        self._client = client or httpx.Client(
            timeout=timeout, headers={"User-Agent": "Mozilla/5.0 (controle-investimentos)"}
        )

    def fetch(self, symbol: str) -> QuoteSeries:
        try:
            response = self._client.get(
                _URL.format(symbol=symbol), params={"range": "1y", "interval": "1d"}
            )
        except httpx.HTTPError as exc:
            raise MarketDataError(f"sem resposta da fonte: {exc.__class__.__name__}") from exc
        if response.status_code == 404:
            raise MarketDataError("código não encontrado na fonte")
        if response.status_code != 200:
            raise MarketDataError(f"a fonte respondeu {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise MarketDataError("a fonte não devolveu JSON") from exc
        return parse_chart(payload)
