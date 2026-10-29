"""Painel-1: série de cotações para a evolução do patrimônio."""

import uuid
from datetime import date
from decimal import Decimal

from app.models import AssetPrice
from app.models.enums import PriceSource
from app.repositories.prices import list_price_series
from tests.test_persistence import make_asset


def _price(session, asset, day, value, source):
    session.add(
        AssetPrice(
            asset_id=asset.id,
            price_date=day,
            price=Decimal(value),
            currency_code="USD",
            source=source,
        )
    )
    session.flush()


def test_uma_por_dia_em_ordem_crescente_com_a_manual_vencendo(db_session):
    asset = make_asset(db_session, f"S{uuid.uuid4().hex[:5].upper()}", "ETF_US", "US", "USD")
    _price(db_session, asset, date(2026, 9, 2), "102", PriceSource.YAHOO)
    _price(db_session, asset, date(2026, 9, 1), "100", PriceSource.YAHOO)
    _price(db_session, asset, date(2026, 9, 2), "101.5", PriceSource.MANUAL)
    _price(db_session, asset, date(2026, 9, 9), "999", PriceSource.YAHOO)

    series = list_price_series(db_session, [asset.id], date(2026, 9, 5))[asset.id]

    assert [(p.price_date, p.price, p.source) for p in series] == [
        (date(2026, 9, 1), Decimal("100.00000000"), PriceSource.YAHOO),
        (date(2026, 9, 2), Decimal("101.50000000"), PriceSource.MANUAL),
    ]


def test_sem_ativos_nada_e_lido(db_session):
    assert list_price_series(db_session, [], date(2026, 9, 5)) == {}
