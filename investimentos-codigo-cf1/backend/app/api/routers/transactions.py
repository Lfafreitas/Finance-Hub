from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.schemas.transaction import (
    PositionRead,
    TransactionCreate,
    TransactionRead,
    TransferCreate,
    TransferRead,
)
from app.services import reconciliation_service, transaction_service
from app.services.exceptions import (
    AccountNotFoundError,
    CorrectionInvalidatesHistoryError,
    CrossCurrencyTransferError,
    CurrencyMismatchError,
    DomainConflictError,
    InsufficientPositionError,
    InvalidTransactionDataError,
    NotAnInvestmentAccountError,
    ReversalInvalidatesHistoryError,
    SameAccountTransferError,
    TransactionAlreadyReversedError,
    TransactionNotFoundError,
    UnsupportedCorrectionError,
    UnsupportedReversalError,
)

router = APIRouter()

# Mapeamento único exceção de domínio -> status HTTP. Os handlers dos
# endpoints só chamam o service e traduzem via este dicionário — a
# regra de negócio em si vive inteiramente em `transaction_service`.
_ERROR_STATUS = {
    AccountNotFoundError: 404,
    TransactionNotFoundError: 404,
    SameAccountTransferError: 400,
    CrossCurrencyTransferError: 400,
    CurrencyMismatchError: 400,
    InsufficientPositionError: 400,
    InvalidTransactionDataError: 400,
    NotAnInvestmentAccountError: 400,
    TransactionAlreadyReversedError: 409,
    UnsupportedCorrectionError: 400,
    CorrectionInvalidatesHistoryError: 400,
    UnsupportedReversalError: 400,
    ReversalInvalidatesHistoryError: 400,
    DomainConflictError: 409,
}


_DOMAIN_ERRORS = tuple(_ERROR_STATUS.keys())


def _raise_as_http(exc: Exception):
    status_code = _ERROR_STATUS.get(type(exc), 400)
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/transactions", response_model=TransactionRead, status_code=201)
def create_transaction(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        transaction = transaction_service.create_transaction(db, user_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    # D-H1 (Fase 10b, unidade 7): checagem síncrona pós-criação. Nunca
    # levanta — uma falha aqui não pode impedir nem desfazer a criação
    # acima, que já aconteceu.
    reconciliation_service.check_after_creation(db, user_id, transaction)
    return transaction


@router.post("/transfers", response_model=TransferRead, status_code=201)
def create_transfer(
    payload: TransferCreate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        transfer_out, transfer_in = transaction_service.create_transfer(db, user_id, payload)
        return TransferRead(transfer_out=transfer_out, transfer_in=transfer_in)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.post("/transactions/{transaction_id}/correct", response_model=TransactionRead)
def correct_transaction(
    transaction_id: UUID,
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        corrected = transaction_service.correct_transaction(db, user_id, transaction_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    # D-H1: dispara só para a Transaction NOVA — a original, marcada
    # REVERSED pela própria correção, nunca entra aqui.
    reconciliation_service.check_after_creation(db, user_id, corrected)
    return corrected


@router.post("/transactions/{transaction_id}/reverse", response_model=TransactionRead)
def reverse_transaction(
    transaction_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Estorno pela tela de lançamentos: marca como REVERSED, sem criar
    nada. Mesma função que o MERGE da reconciliação usa — recusa perna
    de transferência e estorno que deixaria o histórico inválido.
    """
    try:
        return transaction_service.reverse_transaction(db, user_id, transaction_id)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.get("/transactions/{transaction_id}", response_model=TransactionRead)
def get_transaction(
    transaction_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return transaction_service.get_transaction(db, user_id, transaction_id)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.get("/accounts/{account_id}/transactions", response_model=list[TransactionRead])
def list_transactions(
    account_id: UUID,
    asset_id: UUID | None = None,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return transaction_service.get_transaction_history(db, user_id, account_id, asset_id)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.get("/accounts/{account_id}/positions/{asset_id}", response_model=PositionRead | None)
def get_position(
    account_id: UUID,
    asset_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return transaction_service.get_position(db, user_id, account_id, asset_id)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
