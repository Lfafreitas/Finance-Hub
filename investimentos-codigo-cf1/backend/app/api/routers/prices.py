from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.db.base import utcnow
from app.schemas.prices import (
    AssetLatestPrice,
    AssetPriceRead,
    AssetPriceWrite,
    QuoteRefreshItem,
    QuoteRefreshResult,
)
from app.services import benchmark_service, market_data_service, price_service
from app.services.exceptions import AssetNotFoundError, InvalidPriceError
from app.services.market_data.bcb import BcbCdiProvider, RateProvider
from app.services.market_data.yahoo import MarketDataError, QuoteProvider, YahooChartProvider

router = APIRouter()

_ERROR_STATUS = {AssetNotFoundError: 404, InvalidPriceError: 400}
_DOMAIN_ERRORS = tuple(_ERROR_STATUS.keys())


def _raise_as_http(exc: Exception):
    raise HTTPException(status_code=_ERROR_STATUS.get(type(exc), 400), detail=str(exc)) from exc


@router.get("/prices/latest", response_model=list[AssetLatestPrice])
def list_latest_prices(db: Session = Depends(get_db), _user: UUID = Depends(get_current_user_id)):
    return price_service.list_latest_prices(db)


@router.get("/assets/{asset_id}/prices", response_model=list[AssetPriceRead])
def get_price_history(
    asset_id: UUID,
    db: Session = Depends(get_db),
    _user: UUID = Depends(get_current_user_id),
):
    try:
        return price_service.get_price_history(db, asset_id)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.put("/assets/{asset_id}/prices", response_model=AssetPriceRead)
def set_manual_price(
    asset_id: UUID,
    payload: AssetPriceWrite,
    db: Session = Depends(get_db),
    _user: UUID = Depends(get_current_user_id),
):
    """PUT: informar de novo a cotação de uma data substitui a anterior."""
    try:
        return price_service.set_manual_price(db, asset_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


def get_quote_provider() -> QuoteProvider:
    """Fonte automática de cotações. Os testes trocam por uma falsa."""
    return YahooChartProvider()


def get_rate_provider() -> RateProvider:
    """CDI do Banco Central. Os testes trocam por uma falsa."""
    return BcbCdiProvider()


@router.post("/prices/refresh", response_model=QuoteRefreshResult)
def refresh_quotes(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    provider: QuoteProvider = Depends(get_quote_provider),
    rates: RateProvider = Depends(get_rate_provider),
):
    """Busca as cotações dos ativos da carteira na fonte automática.
    Só os códigos dos ativos saem do computador. Falha em um ativo não
    impede os outros; o resultado diz o que aconteceu com cada um.
    """
    items = market_data_service.refresh_quotes(db, user_id, provider)
    # CDI (referência dos investimentos em reais): só o período sai do
    # computador. Falha aqui não desfaz as cotações.
    try:
        saved = benchmark_service.refresh_cdi(db, user_id, rates)
        cdi_status = f"OK: {saved} dia(s) de CDI gravado(s)" if saved else None
    except MarketDataError as exc:
        cdi_status = f"ERRO: {exc}"
    return QuoteRefreshResult(
        refreshed_at=utcnow(),
        items=[QuoteRefreshItem(**item.__dict__) for item in items],
        cdi_status=cdi_status,
    )
