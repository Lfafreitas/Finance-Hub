from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.models.enums import AccountType


class AccountRead(BaseModel):
    id: UUID
    name: str
    institution_id: UUID
    institution_name: str
    currency_code: str
    portfolio_id: UUID | None
    account_type: AccountType


class PortfolioRead(BaseModel):
    id: UUID
    name: str
