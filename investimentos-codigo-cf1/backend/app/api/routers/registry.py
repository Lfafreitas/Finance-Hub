from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.schemas.account import AccountRead, PortfolioRead
from app.schemas.registry import (
    AccountCreate,
    AssetClassRead,
    AssetCreate,
    AssetRead,
    CurrencyRead,
    InstitutionCreate,
    InstitutionRead,
    PortfolioCreate,
)
from app.services import registry_service
from app.services.exceptions import (
    AccountNotFoundError,
    DuplicateRegistryEntryError,
    InvalidRegistryReferenceError,
    PortfolioNotFoundError,
    RegistryEntryNotFoundError,
    RegistryInUseError,
)

router = APIRouter()

_ERROR_STATUS = {
    DuplicateRegistryEntryError: 409,
    InvalidRegistryReferenceError: 400,
    PortfolioNotFoundError: 404,
    AccountNotFoundError: 404,
    RegistryEntryNotFoundError: 404,
    RegistryInUseError: 409,
}
_DOMAIN_ERRORS = tuple(_ERROR_STATUS.keys())


def _raise_as_http(exc: Exception):
    raise HTTPException(status_code=_ERROR_STATUS.get(type(exc), 400), detail=str(exc)) from exc


# Todas as rotas exigem o usuário resolvido, mesmo as de cadastro
# global: sem usuário configurado a API inteira responde do mesmo jeito.


@router.get("/currencies", response_model=list[CurrencyRead])
def list_currencies(db: Session = Depends(get_db), _user: UUID = Depends(get_current_user_id)):
    return registry_service.list_currencies(db)


@router.get("/asset-classes", response_model=list[AssetClassRead])
def list_asset_classes(db: Session = Depends(get_db), _user: UUID = Depends(get_current_user_id)):
    return registry_service.list_asset_classes(db)


@router.get("/assets", response_model=list[AssetRead])
def list_assets(db: Session = Depends(get_db), _user: UUID = Depends(get_current_user_id)):
    return registry_service.list_assets(db)


@router.post("/assets", response_model=AssetRead, status_code=201)
def create_asset(
    payload: AssetCreate,
    db: Session = Depends(get_db),
    _user: UUID = Depends(get_current_user_id),
):
    try:
        return registry_service.create_asset(db, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.get("/institutions", response_model=list[InstitutionRead])
def list_institutions(db: Session = Depends(get_db), _user: UUID = Depends(get_current_user_id)):
    return registry_service.list_institutions(db)


@router.post("/institutions", response_model=InstitutionRead, status_code=201)
def create_institution(
    payload: InstitutionCreate,
    db: Session = Depends(get_db),
    _user: UUID = Depends(get_current_user_id),
):
    return registry_service.create_institution(db, payload)


@router.post("/portfolios", response_model=PortfolioRead, status_code=201)
def create_portfolio(
    payload: PortfolioCreate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        portfolio = registry_service.create_portfolio(db, user_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return PortfolioRead(id=portfolio.id, name=portfolio.name)


@router.post("/accounts", response_model=AccountRead, status_code=201)
def create_account(
    payload: AccountCreate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        account = registry_service.create_account(db, user_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    institution = registry_service.get_institution(db, account.institution_id)
    return AccountRead(
        id=account.id,
        name=account.name,
        institution_id=account.institution_id,
        institution_name=institution.name,
        currency_code=account.currency_code,
        portfolio_id=account.portfolio_id,
        account_type=account.account_type,
    )


# --- Edição e exclusão -----------------------------------------------------
# PUT recebe o cadastro inteiro (mesmo corpo da criação). DELETE só
# remove o que nunca foi usado; caso contrário responde 409 com o motivo.


def _account_read(db: Session, account) -> AccountRead:
    institution = registry_service.get_institution(db, account.institution_id)
    return AccountRead(
        id=account.id,
        name=account.name,
        institution_id=account.institution_id,
        institution_name=institution.name,
        currency_code=account.currency_code,
        portfolio_id=account.portfolio_id,
        account_type=account.account_type,
    )


@router.put("/institutions/{institution_id}", response_model=InstitutionRead)
def update_institution(
    institution_id: UUID,
    payload: InstitutionCreate,
    db: Session = Depends(get_db),
    _user: UUID = Depends(get_current_user_id),
):
    try:
        return registry_service.update_institution(db, institution_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.delete("/institutions/{institution_id}", status_code=204)
def delete_institution(
    institution_id: UUID,
    db: Session = Depends(get_db),
    _user: UUID = Depends(get_current_user_id),
):
    try:
        registry_service.delete_institution(db, institution_id)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return Response(status_code=204)


@router.put("/portfolios/{portfolio_id}", response_model=PortfolioRead)
def update_portfolio(
    portfolio_id: UUID,
    payload: PortfolioCreate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        portfolio = registry_service.update_portfolio(db, user_id, portfolio_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return PortfolioRead(id=portfolio.id, name=portfolio.name)


@router.delete("/portfolios/{portfolio_id}", status_code=204)
def delete_portfolio(
    portfolio_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        registry_service.delete_portfolio(db, user_id, portfolio_id)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return Response(status_code=204)


@router.put("/accounts/{account_id}", response_model=AccountRead)
def update_account(
    account_id: UUID,
    payload: AccountCreate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        account = registry_service.update_account(db, user_id, account_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return _account_read(db, account)


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(
    account_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        registry_service.delete_account(db, user_id, account_id)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return Response(status_code=204)


@router.put("/assets/{asset_id}", response_model=AssetRead)
def update_asset(
    asset_id: UUID,
    payload: AssetCreate,
    db: Session = Depends(get_db),
    _user: UUID = Depends(get_current_user_id),
):
    try:
        return registry_service.update_asset(db, asset_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset(
    asset_id: UUID,
    db: Session = Depends(get_db),
    _user: UUID = Depends(get_current_user_id),
):
    try:
        registry_service.delete_asset(db, asset_id)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return Response(status_code=204)
