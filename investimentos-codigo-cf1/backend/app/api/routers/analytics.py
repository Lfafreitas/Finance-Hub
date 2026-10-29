from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.schemas.analytics import PortfolioAnalytics
from app.services import analytics_service
from app.services.exceptions import PortfolioNotFoundError

router = APIRouter()


@router.get("/analytics/portfolio", response_model=PortfolioAnalytics)
def get_portfolio_analytics(
    portfolio_id: UUID | None = None,
    until: date | None = None,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Cenários, concentração, ritmo de aporte e alertas, por moeda.
    `until`: data final dos cenários (padrão: 31/12 do ano corrente).
    """
    try:
        return analytics_service.get_portfolio_analytics(db, user_id, portfolio_id, until=until)
    except PortfolioNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
