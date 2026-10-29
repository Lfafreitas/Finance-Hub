"""Atualização automática de cotações (Análises-1).

Busca na fonte pública os fechamentos do último ano de cada ativo que
o usuário tem (ou teve) em carteira e grava como cotação de fonte
YAHOO. A cotação digitada à mão nunca é sobrescrita: ela é outra fonte
e, na mesma data, vence a automática (ver `repositories.prices`).

Uma falha em um ativo não impede os outros. Nada é gravado de um ativo
cuja resposta não passou pelas checagens (moeda, preço positivo, data
não futura).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.account import Account
from app.models.asset import Asset
from app.models.asset_price import AssetPrice
from app.models.enums import PriceSource, TransactionStatus
from app.models.transaction import Transaction
from app.services.market_data.yahoo import MarketDataError, QuoteProvider, yahoo_symbol


@dataclass(frozen=True)
class RefreshItem:
    asset_id: UUID
    ticker: str
    status: str  # OK | ERROR | UNSUPPORTED
    message: str | None = None
    price: Decimal | None = None
    price_date: date | None = None
    points: int = 0


def held_assets(db: Session, user_id: UUID) -> list[Asset]:
    """Ativos com alguma transação ativa nas contas do usuário."""
    stmt = (
        select(Asset)
        .join(Transaction, Transaction.asset_id == Asset.id)
        .join(Account, Account.id == Transaction.account_id)
        .where(Account.user_id == user_id, Transaction.status == TransactionStatus.ACTIVE)
        .distinct()
        .order_by(Asset.ticker, Asset.country)
    )
    return list(db.execute(stmt).scalars().all())


def refresh_quotes(
    db: Session, user_id: UUID, provider: QuoteProvider, *, today: date | None = None
) -> list[RefreshItem]:
    today = today or date.today()
    items: list[RefreshItem] = []
    for asset in held_assets(db, user_id):
        symbol = yahoo_symbol(
            asset.ticker, asset.country, asset.asset_class_code, asset.currency_code
        )
        if symbol is None:
            items.append(
                RefreshItem(
                    asset_id=asset.id,
                    ticker=asset.ticker,
                    status="UNSUPPORTED",
                    message="sem fonte automática para esta classe ou país — informe a cotação à mão",
                )
            )
            continue
        try:
            series = provider.fetch(symbol)
        except MarketDataError as exc:
            items.append(RefreshItem(asset.id, asset.ticker, "ERROR", str(exc)))
            continue
        if series.currency != asset.currency_code:
            items.append(
                RefreshItem(
                    asset.id,
                    asset.ticker,
                    "ERROR",
                    f"a fonte cota {symbol} em {series.currency}; o ativo está cadastrado em "
                    f"{asset.currency_code} — nada gravado",
                )
            )
            continue
        bars = [bar for bar in series.bars if bar.day <= today]
        if not bars:
            items.append(RefreshItem(asset.id, asset.ticker, "ERROR", "nenhum preço até hoje"))
            continue
        now = utcnow()
        rows = [
            {
                "asset_id": asset.id,
                "price_date": bar.day,
                "price": bar.close,
                "currency_code": asset.currency_code,
                "source": PriceSource.YAHOO,
                "created_at": now,
                "updated_at": now,
            }
            for bar in bars
        ]
        stmt = insert(AssetPrice).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_asset_prices_asset_date_source",
            set_={"price": stmt.excluded.price, "updated_at": stmt.excluded.updated_at},
        )
        db.execute(stmt)
        last = bars[-1]
        items.append(
            RefreshItem(
                asset_id=asset.id,
                ticker=asset.ticker,
                status="OK",
                price=last.close,
                price_date=last.day,
                points=len(bars),
            )
        )
    db.flush()
    return items


def last_refresh(db: Session, asset_ids: list[UUID]) -> datetime | None:
    """Quando a cotação automática desses ativos foi gravada pela última vez."""
    if not asset_ids:
        return None
    stmt = select(func.max(AssetPrice.updated_at)).where(
        AssetPrice.asset_id.in_(asset_ids), AssetPrice.source == PriceSource.YAHOO
    )
    return db.execute(stmt).scalar_one_or_none()
