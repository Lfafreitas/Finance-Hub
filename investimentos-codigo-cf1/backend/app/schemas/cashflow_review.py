"""Revisão do que falta classificar (Painel-1)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import CashflowNature

MAX_BATCH = 500


class PendingEntryRead(BaseModel):
    id: UUID
    account_id: UUID
    entry_date: date
    amount: Decimal
    description: str


class SuggestionRead(BaseModel):
    """O que você já fez com este mesmo texto: a classificação mais
    frequente, quantas vezes (`evidence`) e a fatia do histórico
    (`share`, 0..1).
    """

    nature: CashflowNature
    category_id: UUID | None
    evidence: int
    share: Decimal


class PendingGroupRead(BaseModel):
    match_text: str
    currency_code: str
    sample_description: str
    count: int
    total: Decimal
    inflows: int
    outflows: int
    first_date: date
    last_date: date
    entry_ids: list[UUID]
    # Os mais recentes, para conferir antes de classificar.
    preview: list[PendingEntryRead]
    suggestion: SuggestionRead | None


class PendingGroups(BaseModel):
    pending_entries: int
    pending_groups: int
    groups: list[PendingGroupRead]


class BatchClassificationWrite(BaseModel):
    """Mesma classificação manual para vários lançamentos de uma vez:
    tudo ou nada.
    """

    entry_ids: list[UUID] = Field(min_length=1, max_length=MAX_BATCH)
    nature: CashflowNature
    category_id: UUID | None = None
    tag_ids: list[UUID] = Field(default_factory=list)


class BatchClassificationResult(BaseModel):
    classified: int
