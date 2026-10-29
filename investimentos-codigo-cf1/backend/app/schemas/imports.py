from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import TransactionType


class ImportRow(BaseModel):
    """Uma linha normalizada de importação — o conteúdo assinado pelo
    HMAC (preview → commit). Nenhum campo aqui deve ser derivável de
    outra fonte que não o próprio arquivo + o que o servidor já
    calculou na preview (fingerprint, flags de duplicata).
    """

    row_index: int
    transaction_type: TransactionType
    asset_ticker: str | None = None
    asset_id: UUID | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    fees: Decimal = Decimal(0)
    gross_amount: Decimal
    currency_code: str
    transaction_date: date
    external_reference: str
    is_exact_duplicate: bool = False
    possible_duplicate: bool = False
    duplicate_reason: str | None = None
    error: str | None = None  # ex.: ativo não cadastrado — linha não pode ser incluída


class ImportPreviewResponse(BaseModel):
    account_id: UUID
    source_format: str  # "CSV" | "XLSX" | "OFX"
    rows: list[ImportRow]
    signature: str


class ImportCommitRequest(BaseModel):
    account_id: UUID
    source_format: str
    rows: list[ImportRow]
    signature: str
    included_row_indexes: list[int]


class ImportCommitResult(BaseModel):
    imported_count: int
    excluded_count: int
    transaction_ids: list[UUID]
