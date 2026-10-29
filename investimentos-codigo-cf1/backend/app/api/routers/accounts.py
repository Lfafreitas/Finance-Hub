from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.schemas.account import AccountRead, PortfolioRead
from app.services import account_service

router = APIRouter()


@router.get("/accounts", response_model=list[AccountRead])
def list_accounts(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    return account_service.get_accounts(db, user_id)


@router.get("/portfolios", response_model=list[PortfolioRead])
def list_portfolios(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    return account_service.get_portfolios(db, user_id)
