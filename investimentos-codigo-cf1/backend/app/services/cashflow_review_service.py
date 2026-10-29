"""Revisão do que falta classificar (Painel-1): grupos com sugestão e
classificação em lote. A regra mora em `cashflow_engine.review`; a
classificação de cada lançamento é a mesma da tela (`classify_entry`).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.cashflow_engine import parse_description
from app.domain.cashflow_engine.review import KnownClassification, PendingEntry, group_pending
from app.models.cashflow_entry import CashflowEntry
from app.models.enums import CashflowEntryStatus, CashflowNature
from app.repositories import cashflow as cashflow_repo
from app.schemas.cashflow_classification import EntryClassificationWrite
from app.schemas.cashflow_review import (
    BatchClassificationResult,
    BatchClassificationWrite,
    PendingEntryRead,
    PendingGroupRead,
    PendingGroups,
    SuggestionRead,
)
from app.services import cashflow_classification_service as classification
from app.services.exceptions import InvalidCashflowClassificationError

PREVIEW = 6


def list_pending_groups(db: Session, user_id: UUID, *, limit: int = 50) -> PendingGroups:
    account_ids = [a.id for a in cashflow_repo.list_cash_accounts(db, user_id)]
    if not account_ids:
        return PendingGroups(pending_entries=0, pending_groups=0, groups=[])
    entries = db.execute(
        select(CashflowEntry).where(
            CashflowEntry.account_id.in_(account_ids),
            CashflowEntry.status == CashflowEntryStatus.ACTIVE,
        )
    ).scalars()
    pending: list[PendingEntry] = []
    known: list[KnownClassification] = []
    for entry in entries:
        text = parse_description(entry.description).match_text
        if entry.nature is CashflowNature.UNCLASSIFIED:
            pending.append(
                PendingEntry(
                    id=entry.id,
                    account_id=entry.account_id,
                    match_text=text,
                    description=entry.description,
                    currency_code=entry.currency_code,
                    amount=entry.amount,
                    entry_date=entry.entry_date,
                )
            )
        else:
            known.append(
                KnownClassification(text, entry.nature, entry.category_id, entry.entry_date)
            )
    groups = group_pending(pending, known)
    return PendingGroups(
        pending_entries=len(pending),
        pending_groups=len(groups),
        groups=[
            PendingGroupRead(
                match_text=g.match_text,
                currency_code=g.currency_code,
                sample_description=g.entries[0].description,
                count=g.count,
                total=g.total,
                inflows=g.inflows,
                outflows=g.outflows,
                first_date=min(e.entry_date for e in g.entries),
                last_date=max(e.entry_date for e in g.entries),
                entry_ids=[e.id for e in g.entries],
                preview=[
                    PendingEntryRead(
                        id=e.id,
                        account_id=e.account_id,
                        entry_date=e.entry_date,
                        amount=e.amount,
                        description=e.description,
                    )
                    for e in g.entries[:PREVIEW]
                ],
                suggestion=(
                    SuggestionRead(
                        nature=g.suggestion.nature,
                        category_id=g.suggestion.category_id,
                        evidence=g.suggestion.evidence,
                        share=g.suggestion.share,
                    )
                    if g.suggestion
                    else None
                ),
            )
            for g in groups[:limit]
        ],
    )


def classify_batch(
    db: Session, user_id: UUID, payload: BatchClassificationWrite
) -> BatchClassificationResult:
    """Tudo ou nada: se um lançamento for recusado (de outro usuário,
    excluído, transferência), nenhum muda.
    """
    if payload.nature is CashflowNature.UNCLASSIFIED:
        raise InvalidCashflowClassificationError("escolha uma natureza para classificar")
    ids = list(dict.fromkeys(payload.entry_ids))
    single = EntryClassificationWrite(
        nature=payload.nature, category_id=payload.category_id, tag_ids=payload.tag_ids
    )
    with db.begin_nested():
        for entry_id in ids:
            classification.classify_entry(db, user_id, entry_id, single)
    return BatchClassificationResult(classified=len(ids))
