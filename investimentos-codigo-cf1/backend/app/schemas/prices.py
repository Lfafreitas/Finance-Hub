from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import PriceSource


class AssetPriceWrite(BaseModel):
    """Corpo de PUT /assets/{id}/prices. A moeda não é informada: é
    sempre a do ativo. A fonte é sempre MANUAL por este endpoint.
    """

    price_date: date
    price: Decimal


class AssetPriceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_id: UUID
    price_date: date
    price: Decimal
    currency_code: str
    source: PriceSource


class AssetLatestPrice(BaseModel):
    """Um ativo e a sua cotação mais recente (até hoje), para a tela
    de cotações. `price`/`price_date` nulos = ativo sem cotação.
    """

    asset_id: UUID
    asset_ticker: str
    asset_name: str
    currency_code: str
    price: Decimal | None
    price_date: date | None


class QuoteRefreshItem(BaseModel):
    """Resultado da atualização de UM ativo. `status`: OK, ERROR (a
    fonte falhou ou respondeu algo inválido — nada gravado) ou
    UNSUPPORTED (classe ou país sem fonte automática).
    """

    asset_id: UUID
    ticker: str
    status: str
    message: str | None
    price: Decimal | None
    price_date: date | None
    points: int


class QuoteRefreshResult(BaseModel):
    refreshed_at: datetime
    items: list[QuoteRefreshItem]
    cdi_status: str | None = None
