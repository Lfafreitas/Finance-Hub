from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import TransactionSource, TransactionStatus, TransactionType

# Tipos aceitos por POST /transactions — TRANSFER_OUT/IN têm fluxo
# próprio (POST /transfers) e nunca devem ser criados por aqui.
_MANUAL_TRANSACTION_TYPES = {
    t
    for t in TransactionType
    if t not in (TransactionType.TRANSFER_OUT, TransactionType.TRANSFER_IN)
}


class TransactionCreate(BaseModel):
    """Corpo de POST /transactions e do valor corrigido de
    POST /transactions/{id}/correct. `source` não é um campo aqui de
    propósito: toda transação criada por este endpoint é MANUAL — o
    cliente não escolhe a fonte, o service que define.
    """

    account_id: UUID
    asset_id: UUID | None = None
    transaction_type: TransactionType
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    fees: Decimal = Decimal(0)
    gross_amount: Decimal
    currency_code: str = Field(min_length=3, max_length=3)
    transaction_date: date
    fx_rate_to_brl: Decimal | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _rejeita_tipos_de_transferencia(self) -> TransactionCreate:
        if self.transaction_type not in _MANUAL_TRANSACTION_TYPES:
            raise ValueError(
                f"{self.transaction_type} não é aceito em /transactions — use /transfers"
            )
        return self


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    asset_id: UUID | None
    transaction_type: TransactionType
    quantity: Decimal | None
    unit_price: Decimal | None
    fees: Decimal
    gross_amount: Decimal
    currency_code: str
    transaction_date: date
    fx_rate_to_brl: Decimal | None
    source: TransactionSource
    status: TransactionStatus
    reverses_transaction_id: UUID | None
    linked_transaction_id: UUID | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class TransferCreate(BaseModel):
    """Corpo de POST /transfers — cria as duas pernas atomicamente."""

    from_account_id: UUID
    to_account_id: UUID
    gross_amount: Decimal
    transaction_date: date
    fees: Decimal = Decimal(0)
    notes: str | None = None


class TransferRead(BaseModel):
    transfer_out: TransactionRead
    transfer_in: TransactionRead


class PositionRead(BaseModel):
    account_id: UUID
    asset_id: UUID
    quantity: Decimal
    average_cost: Decimal
    total_cost_basis: Decimal
    realized_gain: Decimal
    dividends_received: Decimal
