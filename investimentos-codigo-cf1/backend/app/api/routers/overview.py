from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.schemas.overview import Overview
from app.services import overview_service

router = APIRouter()


@router.get("/overview", response_model=Overview)
def get_overview(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    """Patrimônio por moeda: investimentos (renda variável, renda fixa,
    fundos), reserva, disponível e cartão. Moedas nunca se somam.
    """
    return overview_service.get_overview(db, user_id)
