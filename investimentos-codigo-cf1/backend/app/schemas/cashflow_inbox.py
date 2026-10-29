"""Schemas da pasta Entrada (carga de extratos e faturas soltos na pasta)."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import CashflowImportProfile

InboxStatus = Literal["IMPORTED", "NOTHING_NEW", "REFUSED", "NO_ACCOUNT"]


class InboxFileResult(BaseModel):
    """O que aconteceu com um arquivo. IMPORTED e NOTHING_NEW saem da
    pasta (`moved_to`); REFUSED e NO_ACCOUNT ficam, com o motivo.
    """

    file_name: str
    status: InboxStatus
    profile: CashflowImportProfile | None = None
    account_id: UUID | None = None
    account_name: str | None = None
    imported_count: int = 0
    duplicate_count: int = 0
    error_rows: int = 0
    matched_transfers: int = 0
    balance_difference: Decimal | None = None
    message: str | None = None
    moved_to: str | None = None


class InboxListing(BaseModel):
    inbox_dir: str
    exists: bool
    files: list[str]


class InboxRunResult(BaseModel):
    inbox_dir: str
    files: list[InboxFileResult]
