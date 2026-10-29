"""Acesso a `AssetPrice` (Fase 12)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.models.asset_price import AssetPrice
from app.models.enums import PriceSource

# Mais recente primeiro. Na MESMA data, a cotação digitada pelo usuário
# vence a automática: corrigir à mão um preço errado da fonte tem de
# valer. `updated_at` só desempata o que sobrar.
_NEWEST_FIRST = (
    AssetPrice.price_date.desc(),
    case((AssetPrice.source == PriceSource.MANUAL, 0), else_=1),
    AssetPrice.updated_at.desc(),
)


def list_prices(session: Session, asset_id: UUID) -> list[AssetPrice]:
    stmt = select(AssetPrice).where(AssetPrice.asset_id == asset_id).order_by(*_NEWEST_FIRST)
    return list(session.execute(stmt).scalars().all())


def get_latest_prices(
    session: Session, asset_ids: Iterable[UUID], on_or_before: date
) -> dict[UUID, AssetPrice]:
    """A cotação mais recente de cada ativo com `price_date <=
    on_or_before`. Cotação com data FUTURA em relação à referência
    nunca é usada. Ativo sem cotação simplesmente não aparece.
    """
    ids = list(asset_ids)
    if not ids:
        return {}
    stmt = (
        select(AssetPrice)
        .where(AssetPrice.asset_id.in_(ids), AssetPrice.price_date <= on_or_before)
        .order_by(AssetPrice.asset_id, *_NEWEST_FIRST)
    )
    latest: dict[UUID, AssetPrice] = {}
    for price in session.execute(stmt).scalars():
        latest.setdefault(price.asset_id, price)
    return latest


def list_price_series(
    session: Session, asset_ids: Iterable[UUID], on_or_before: date
) -> dict[UUID, list[AssetPrice]]:
    """Série de cotações de cada ativo, em ordem CRESCENTE de data, uma
    por data. Na mesma data vale a mesma precedência de
    `get_latest_prices` (a digitada à mão vence a automática).
    """
    ids = list(asset_ids)
    if not ids:
        return {}
    stmt = (
        select(AssetPrice)
        .where(AssetPrice.asset_id.in_(ids), AssetPrice.price_date <= on_or_before)
        .order_by(AssetPrice.asset_id, *_NEWEST_FIRST)
    )
    series: dict[UUID, list[AssetPrice]] = {}
    for price in session.execute(stmt).scalars():
        items = series.setdefault(price.asset_id, [])
        if items and items[-1].price_date == price.price_date:
            continue
        items.append(price)
    return {asset_id: items[::-1] for asset_id, items in series.items()}
