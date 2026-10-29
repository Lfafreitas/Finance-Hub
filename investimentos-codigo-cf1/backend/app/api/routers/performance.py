from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.schemas.performance import (
    AgendaRead,
    AllocationRead,
    AllocationTargetsWrite,
    BenchmarksRead,
    FinancialHealthIndex,
    PerformanceHistory,
    PortfolioKpisRead,
    WidgetSummary,
)
from app.services import (
    agenda_service,
    allocation_service,
    benchmark_service,
    financial_health_service,
    performance_service,
)
from app.services.exceptions import InvalidAllocationTargetError, InvalidCashflowPeriodError

router = APIRouter(prefix="/performance")


@router.get("/history", response_model=PerformanceHistory)
def get_history(
    days: int | None = Query(default=None, ge=1, le=performance_service.MAX_DAYS),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Patrimônio dia a dia, por moeda: investimentos (valor e custo) e
    caixa. Sem `days`, desde o primeiro movimento.
    """
    try:
        return performance_service.get_history(db, user_id, days=days)
    except InvalidCashflowPeriodError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/widget", response_model=WidgetSummary)
def get_widget(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    """Resumo compacto para o widget da área de trabalho: patrimônio,
    quanto rendeu, variação do último pregão e os últimos 30 dias.
    """
    return performance_service.get_widget(db, user_id)


@router.get("/kpis", response_model=PortfolioKpisRead)
def get_kpis(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    """Indicadores da carteira e de cada ativo, por moeda: pesos,
    concentração, resultado, proventos e desempenho de preço (1 mês, 3
    meses, no ano, 12 meses, volatilidade, queda máxima, faixa de 52
    semanas).
    """
    return performance_service.get_kpis(db, user_id)


@router.get("/agenda", response_model=AgendaRead)
def get_agenda(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    """Vencimentos de renda fixa das posições atuais, em ordem de data, e
    os ativos de renda fixa sem vencimento informado no cadastro.
    """
    return agenda_service.get_agenda(db, user_id)


@router.get("/financial-health", response_model=FinancialHealthIndex)
def get_financial_health(
    db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)
):
    """Quantos meses de gasto a reserva cobre e quanto da renda sobra, com
    os últimos meses fechados do controle financeiro (só totais).
    """
    return financial_health_service.get_financial_health(db, user_id)


@router.get("/benchmarks", response_model=BenchmarksRead)
def get_benchmarks(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    """Os mesmos aportes, nas mesmas datas, aplicados na referência da
    moeda (SPY em dólar, CDI em reais).
    """
    return benchmark_service.get_benchmarks(db, user_id)


@router.get("/allocation", response_model=AllocationRead)
def get_allocation(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    """Peso atual de cada classe de ativo × o alvo definido pelo usuário."""
    return allocation_service.get_allocation(db, user_id)


@router.put("/allocation/{currency_code}", response_model=AllocationRead)
def set_allocation_targets(
    currency_code: str,
    payload: AllocationTargetsWrite,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Troca os alvos de uma moeda (lista vazia apaga). Soma tem de dar 100%."""
    try:
        allocation_service.set_targets(db, user_id, currency_code, payload)
    except InvalidAllocationTargetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return allocation_service.get_allocation(db, user_id)
