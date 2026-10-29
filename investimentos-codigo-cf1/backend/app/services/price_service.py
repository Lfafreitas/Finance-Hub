"""Cotações (Fase 12). Só entrada manual nesta fase: o usuário informa
o preço de um ativo em uma data. Um provedor externo futuro entra como
outra fonte (`PriceSource`), gravando pelo mesmo caminho.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_price import AssetPrice
from app.models.enums import PriceSource
from app.repositories.prices import get_latest_prices, list_prices
from app.schemas.prices import AssetLatestPrice, AssetPriceWrite
from app.services.exceptions import AssetNotFoundError, InvalidPriceError


def _get_asset(db: Session, asset_id: UUID) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise AssetNotFoundError(f"ativo {asset_id} não encontrado")
    return asset


def set_manual_price(
    db: Session, asset_id: UUID, payload: AssetPriceWrite, *, today: date | None = None
) -> AssetPrice:
    """Grava a cotação MANUAL de `asset_id` em `price_date`. Se já
    existe uma para a mesma data, ela é SUBSTITUÍDA (uma cotação é uma
    observação corrigível, não um fato do usuário). A moeda é sempre a
    do ativo.

    Data futura é recusada: uma cotação "de amanhã" não é uma
    observação, e ficaria invisível para a valoração até a data chegar.
    """
    asset = _get_asset(db, asset_id)
    if payload.price <= 0:
        raise InvalidPriceError("a cotação deve ser maior que zero")
    if payload.price_date > (today or date.today()):
        raise InvalidPriceError("a data da cotação não pode estar no futuro")

    stmt = (
        select(AssetPrice)
        .where(
            AssetPrice.asset_id == asset.id,
            AssetPrice.price_date == payload.price_date,
            AssetPrice.source == PriceSource.MANUAL,
        )
        .with_for_update()
    )
    existing = db.execute(stmt).scalar_one_or_none()
    if existing is not None:
        existing.price = payload.price
        existing.currency_code = asset.currency_code
        db.flush()
        return existing

    price = AssetPrice(
        asset_id=asset.id,
        price_date=payload.price_date,
        price=payload.price,
        currency_code=asset.currency_code,
        source=PriceSource.MANUAL,
    )
    db.add(price)
    db.flush()
    return price


def get_price_history(db: Session, asset_id: UUID) -> list[AssetPrice]:
    _get_asset(db, asset_id)
    return list_prices(db, asset_id)


def list_latest_prices(db: Session, *, today: date | None = None) -> list[AssetLatestPrice]:
    assets = list(db.execute(select(Asset).order_by(Asset.ticker, Asset.country)).scalars().all())
    latest = get_latest_prices(db, [a.id for a in assets], today or date.today())
    result: list[AssetLatestPrice] = []
    for asset in assets:
        price = latest.get(asset.id)
        result.append(
            AssetLatestPrice(
                asset_id=asset.id,
                asset_ticker=asset.ticker,
                asset_name=asset.name,
                currency_code=asset.currency_code,
                price=price.price if price else None,
                price_date=price.price_date if price else None,
            )
        )
    return result
