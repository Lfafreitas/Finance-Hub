"""CDI diário do Banco Central (SGS, série 12) — dado público.

Nada da carteira sai do computador: o pedido leva só o período.
A série vem em % ao dia, uma linha por dia útil:
[{"data": "01/10/2026", "valor": "0.055131"}, ...]
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Protocol

import httpx

from app.services.market_data.yahoo import MarketDataError

_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados"
MAX_DAILY_RATE = Decimal(1)  # 1% ao dia seria absurdo; acima disso, recusa


class RateProvider(Protocol):
    def fetch(self, start: date, end: date) -> list[tuple[date, Decimal]]: ...


def parse_sgs(payload: object) -> list[tuple[date, Decimal]]:
    if not isinstance(payload, list):
        raise MarketDataError("resposta do Banco Central fora do formato")
    out: dict[date, Decimal] = {}
    for row in payload:
        if not isinstance(row, dict):
            raise MarketDataError("linha do Banco Central fora do formato")
        try:
            dd, mm, yyyy = str(row["data"]).split("/")
            if len(yyyy) != 4:
                raise ValueError("ano")
            day = date(int(yyyy), int(mm), int(dd))
            rate = Decimal(str(row["valor"]).replace(",", "."))
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise MarketDataError("linha do Banco Central fora do formato") from exc
        if not rate.is_finite() or rate < 0 or rate > MAX_DAILY_RATE:
            raise MarketDataError(f"taxa do CDI fora do esperado em {day.isoformat()}")
        out[day] = rate
    return sorted(out.items())


class BcbCdiProvider:
    def __init__(self, client: httpx.Client | None = None, timeout: float = 15.0) -> None:
        self._client = client or httpx.Client(timeout=timeout)

    def fetch(self, start: date, end: date) -> list[tuple[date, Decimal]]:
        try:
            response = self._client.get(
                _URL,
                params={
                    "formato": "json",
                    "dataInicial": start.strftime("%d/%m/%Y"),
                    "dataFinal": end.strftime("%d/%m/%Y"),
                },
            )
        except httpx.HTTPError as exc:
            raise MarketDataError(
                f"sem resposta do Banco Central: {exc.__class__.__name__}"
            ) from exc
        if response.status_code == 404:
            return []  # período sem dado (ex.: só fim de semana)
        if response.status_code != 200:
            raise MarketDataError(f"o Banco Central respondeu {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise MarketDataError("o Banco Central não devolveu JSON") from exc
        return parse_sgs(payload)
