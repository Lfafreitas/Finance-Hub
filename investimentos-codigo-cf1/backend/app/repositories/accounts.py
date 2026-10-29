from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.institution import Institution
from app.models.portfolio import Portfolio


def list_accounts(session: Session, user_id: UUID) -> list[Account]:
    stmt = select(Account).where(Account.user_id == user_id).order_by(Account.name)
    return list(session.execute(stmt).scalars().all())


def list_portfolios(session: Session, user_id: UUID) -> list[Portfolio]:
    stmt = select(Portfolio).where(Portfolio.user_id == user_id).order_by(Portfolio.name)
    return list(session.execute(stmt).scalars().all())


def get_institutions_by_id(session: Session, institution_ids: set[UUID]) -> dict[UUID, Institution]:
    if not institution_ids:
        return {}
    stmt = select(Institution).where(Institution.id.in_(institution_ids))
    return {i.id: i for i in session.execute(stmt).scalars().all()}
