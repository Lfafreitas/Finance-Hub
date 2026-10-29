from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.schemas.insights import (
    AlertIndex,
    ChatContext,
    InsightIndex,
    InsightReportRead,
    LookThroughRead,
    SnapshotResult,
)
from app.services import chat_context_service, insights_service, lookthrough_service

router = APIRouter()


@router.get("/insights", response_model=InsightIndex)
def list_insights(_user: UUID = Depends(get_current_user_id)):
    """Análise mais recente do Claude, histórico e arquivos recusados."""
    return insights_service.list_reports()


# As rotas de alertas vêm ANTES de /insights/{report_date}: "alerts" não
# é data e cairia ali.
@router.get("/insights/alerts", response_model=AlertIndex)
def list_alerts(
    days: int = Query(default=7, ge=1, le=insights_service.ALERT_DAYS_MAX),
    _user: UUID = Depends(get_current_user_id),
):
    """Notícias sérias encontradas pela checagem de hora em hora."""
    return insights_service.list_alerts(days=days)


@router.post("/insights/alerts/{alert_id}/read", response_model=AlertIndex)
def mark_alert_read(alert_id: str, _user: UUID = Depends(get_current_user_id)):
    try:
        return insights_service.mark_alerts_read([alert_id])
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"não foi possível gravar: {exc}") from exc


@router.post("/insights/alerts/read-all", response_model=AlertIndex)
def mark_all_alerts_read(_user: UUID = Depends(get_current_user_id)):
    try:
        return insights_service.mark_all_alerts_read()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"não foi possível gravar: {exc}") from exc


@router.get("/insights/lookthrough", response_model=LookThroughRead)
def get_look_through(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    """Empresas por trás dos ETFs: pesos da carteira × composição publicada
    pela gestora (trazida pela análise diária).
    """
    return lookthrough_service.get_look_through(db, user_id)


@router.get("/insights/chat-context", response_model=ChatContext)
def get_chat_context(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    """Resumo da carteira para conversar com o Claude (o usuário leva o texto;
    o backend não chama nenhuma IA). Sem descrições de extrato.
    """
    return ChatContext(text=chat_context_service.build_chat_context(db, user_id))


@router.get("/insights/{report_date}", response_model=InsightReportRead)
def get_insight(report_date: date, _user: UUID = Depends(get_current_user_id)):
    try:
        return insights_service.get_report(report_date)
    except insights_service.InsightReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/insights/snapshot", response_model=SnapshotResult)
def write_snapshot(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    """Atualiza o retrato da carteira que a análise diária do Claude lê."""
    try:
        return insights_service.write_snapshot(db, user_id)
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"não foi possível gravar o retrato da carteira: {exc}"
        ) from exc
