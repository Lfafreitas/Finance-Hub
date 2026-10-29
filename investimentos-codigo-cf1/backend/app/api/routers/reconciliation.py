from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.schemas.reconciliation import (
    FieldComparisonRead,
    ReconciliationComparisonRead,
    ReconciliationLogRead,
    ReconciliationResolveRequest,
    ReconciliationScanRequest,
    ReconciliationScanResult,
)
from app.services import reconciliation_service
from app.services.exceptions import (
    AccountNotFoundError,
    DomainConflictError,
    InvalidMergeSurvivorError,
    InvalidScanScopeError,
    PortfolioNotFoundError,
    ReconciliationAlreadyResolvedError,
    ReconciliationLogNotFoundError,
    ReversalInvalidatesHistoryError,
    TransactionAlreadyReversedError,
    TransactionNotFoundError,
    UnsupportedReversalError,
)

router = APIRouter(prefix="/reconciliation")

# Mesmo padrão de app/api/routers/transactions.py: mapeamento único
# exceção de domínio -> status HTTP; a regra de negócio mora inteira
# no service.
_ERROR_STATUS = {
    AccountNotFoundError: 404,
    PortfolioNotFoundError: 404,
    ReconciliationLogNotFoundError: 404,
    TransactionNotFoundError: 404,
    InvalidScanScopeError: 400,
    InvalidMergeSurvivorError: 400,
    UnsupportedReversalError: 400,
    ReversalInvalidatesHistoryError: 400,
    ReconciliationAlreadyResolvedError: 409,
    TransactionAlreadyReversedError: 409,
    DomainConflictError: 409,
}

_DOMAIN_ERRORS = tuple(_ERROR_STATUS.keys())


def _raise_as_http(exc: Exception):
    status_code = _ERROR_STATUS.get(type(exc), 400)
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/pending", response_model=list[ReconciliationLogRead])
def list_pending_reconciliations(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    return reconciliation_service.list_pending(db, user_id)


@router.post("/scan", response_model=ReconciliationScanResult)
def scan_reconciliation(
    payload: ReconciliationScanRequest | None = None,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Scan manual (Fase 11, unidade backend 3): casca de API sobre
    `scan_for_reconciliation`. Corpo opcional — sem corpo (ou `{}`)
    escaneia todas as contas do usuário. A regra de escopo (conta OU
    portfolio, nunca os dois) é validada pelo service.
    """
    scope = payload or ReconciliationScanRequest()
    try:
        created = reconciliation_service.scan_for_reconciliation(
            db, user_id, account_id=scope.account_id, portfolio_id=scope.portfolio_id
        )
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return ReconciliationScanResult(created_count=len(created), created=created)


@router.get("/{reconciliation_id}/comparison", response_model=ReconciliationComparisonRead)
def get_reconciliation_comparison(
    reconciliation_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        result = reconciliation_service.get_comparison(db, user_id, reconciliation_id)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return ReconciliationComparisonRead(
        reconciliation_id=reconciliation_id,
        classification=result.classification,
        match_reason=result.match_reason,
        fields=[FieldComparisonRead.from_domain(f) for f in result.comparison.fields],
    )


@router.post("/{reconciliation_id}/resolve", response_model=ReconciliationLogRead)
def resolve_reconciliation(
    reconciliation_id: UUID,
    payload: ReconciliationResolveRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return reconciliation_service.resolve_reconciliation(
            db,
            user_id,
            reconciliation_id,
            payload.decision,
            payload.surviving_transaction_id,
        )
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
