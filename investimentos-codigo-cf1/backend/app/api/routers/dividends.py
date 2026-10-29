from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.schemas.dividends import DividendsSummary
from app.services import dividends_service
from app.services.exceptions import PortfolioNotFoundError

router = APIRouter()


@router.get("/dividends/summary", response_model=DividendsSummary)
def get_dividends_summary(
    portfolio_id: UUID | None = None,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return dividends_service.get_dividends_summary(db, user_id, portfolio_id)
    except PortfolioNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
