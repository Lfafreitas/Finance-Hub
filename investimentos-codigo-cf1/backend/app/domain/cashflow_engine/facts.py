from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.models.enums import AccountType, CashflowNature


@dataclass(frozen=True)
class CashEntryFact:
    """Um `CashflowEntry` ACTIVE, reduzido ao que o motor precisa.

    `counterparty_account_type` só existe em TRANSFER: é ele que
    distingue aporte/resgate (contraparte BROKERAGE) de movimento
    interno do caixa.
    """

    account_id: UUID
    account_type: AccountType
    currency_code: str
    entry_date: date
    amount: Decimal
    nature: CashflowNature
    counterparty_account_type: AccountType | None = None
    category_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.account_type is AccountType.BROKERAGE:
            raise ValueError("conta BROKERAGE não pertence ao livro de caixa")
        if self.amount == 0:
            raise ValueError("lançamento de caixa com valor zero")
        is_transfer = self.nature is CashflowNature.TRANSFER
        if is_transfer != (self.counterparty_account_type is not None):
            raise ValueError("TRANSFER exige contraparte; as demais naturezas não têm contraparte")
        if is_transfer and self.category_id is not None:
            raise ValueError("transferência não tem categoria")
