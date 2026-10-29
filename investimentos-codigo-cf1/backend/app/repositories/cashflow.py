from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.cashflow_entry import CashflowEntry
from app.models.enums import AccountType, CashflowEntryStatus, CashflowNature


def list_cash_accounts(session: Session, user_id: UUID) -> list[Account]:
    stmt = (
        select(Account)
        .where(Account.user_id == user_id, Account.account_type != AccountType.BROKERAGE)
        .order_by(Account.name, Account.id)
    )
    return list(session.execute(stmt).scalars().all())


def list_active_entries(
    session: Session, account_ids: list[UUID], *, until: date | None = None
) -> list[CashflowEntry]:
    if not account_ids:
        return []
    stmt = select(CashflowEntry).where(
        CashflowEntry.account_id.in_(account_ids),
        CashflowEntry.status == CashflowEntryStatus.ACTIVE,
    )
    if until is not None:
        stmt = stmt.where(CashflowEntry.entry_date <= until)
    return list(session.execute(stmt).scalars().all())


def _entries_filter(
    account_ids: list[UUID],
    *,
    start: date | None,
    end: date | None,
    include_reversed: bool,
    nature: CashflowNature | None,
    category_ids: list[UUID] | None,
    uncategorized: bool,
    search: str | None,
):
    """Condições comuns à listagem e à contagem: as duas precisam
    responder sobre exatamente o mesmo conjunto.
    """
    conditions = [CashflowEntry.account_id.in_(account_ids)]
    if not include_reversed:
        conditions.append(CashflowEntry.status == CashflowEntryStatus.ACTIVE)
    if start is not None:
        conditions.append(CashflowEntry.entry_date >= start)
    if end is not None:
        conditions.append(CashflowEntry.entry_date <= end)
    if nature is not None:
        conditions.append(CashflowEntry.nature == nature)
    if uncategorized:
        conditions.append(CashflowEntry.category_id.is_(None))
    elif category_ids is not None:
        conditions.append(CashflowEntry.category_id.in_(category_ids))
    if search:
        # O texto do usuário é comparado literalmente: % e _ não são curingas.
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(CashflowEntry.description.ilike(f"%{escaped}%", escape="\\"))
    return conditions


def list_entries(
    session: Session,
    account_ids: list[UUID],
    *,
    start: date | None,
    end: date | None,
    include_reversed: bool,
    limit: int,
    offset: int,
    nature: CashflowNature | None = None,
    category_ids: list[UUID] | None = None,
    uncategorized: bool = False,
    search: str | None = None,
) -> list[CashflowEntry]:
    if not account_ids:
        return []
    stmt = (
        select(CashflowEntry)
        .where(
            *_entries_filter(
                account_ids,
                start=start,
                end=end,
                include_reversed=include_reversed,
                nature=nature,
                category_ids=category_ids,
                uncategorized=uncategorized,
                search=search,
            )
        )
        .order_by(
            CashflowEntry.entry_date.desc(), CashflowEntry.created_at.desc(), CashflowEntry.id
        )
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).scalars().all())


def count_entries(
    session: Session,
    account_ids: list[UUID],
    *,
    start: date | None,
    end: date | None,
    include_reversed: bool,
    nature: CashflowNature | None = None,
    category_ids: list[UUID] | None = None,
    uncategorized: bool = False,
    search: str | None = None,
) -> int:
    if not account_ids:
        return 0
    stmt = (
        select(func.count())
        .select_from(CashflowEntry)
        .where(
            *_entries_filter(
                account_ids,
                start=start,
                end=end,
                include_reversed=include_reversed,
                nature=nature,
                category_ids=category_ids,
                uncategorized=uncategorized,
                search=search,
            )
        )
    )
    return int(session.execute(stmt).scalar_one())


def list_group_entries(session: Session, transfer_group_id: UUID) -> list[CashflowEntry]:
    stmt = (
        select(CashflowEntry)
        .where(CashflowEntry.transfer_group_id == transfer_group_id)
        .order_by(CashflowEntry.amount)
        .with_for_update()
    )
    return list(session.execute(stmt).scalars().all())
