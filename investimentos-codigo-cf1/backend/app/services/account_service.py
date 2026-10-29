from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.accounts import get_institutions_by_id, list_accounts, list_portfolios
from app.schemas.account import AccountRead, PortfolioRead


def get_accounts(db: Session, user_id: UUID) -> list[AccountRead]:
    accounts = list_accounts(db, user_id)
    institutions = get_institutions_by_id(db, {a.institution_id for a in accounts})
    return [
        AccountRead(
            id=account.id,
            name=account.name,
            institution_id=account.institution_id,
            institution_name=institutions[account.institution_id].name,
            currency_code=account.currency_code,
            portfolio_id=account.portfolio_id,
            account_type=account.account_type,
        )
        for account in accounts
    ]


def get_portfolios(db: Session, user_id: UUID) -> list[PortfolioRead]:
    portfolios = list_portfolios(db, user_id)
    return [PortfolioRead(id=p.id, name=p.name) for p in portfolios]
