"""Schemas do livro de caixa (CF-1). `user_id` e moeda nunca vêm do
cliente: o usuário é o resolvido pela dependency e a moeda é sempre a
da conta.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import AccountType, CashflowEntryStatus, CashflowNature, TransactionSource

_Amount = Field(max_digits=18, decimal_places=4)


def _clean(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("não pode ser vazio")
    return cleaned


class CashflowEntryCreate(BaseModel):
    """Lançamento manual. `amount` é assinado: positivo entra, negativo
    sai. TRANSFER não é aceito aqui — transferência tem endpoint
    próprio, que grava as duas pernas juntas.
    """

    account_id: UUID
    entry_date: date
    amount: Decimal = _Amount
    description: str = Field(max_length=255)
    nature: CashflowNature = CashflowNature.UNCLASSIFIED
    notes: str | None = None

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        return _clean(value)


class CashflowEntryCorrect(BaseModel):
    """Edição de lançamento manual: os novos valores do fato. A conta e
    a classificação ficam as do original; `notes` nulo mantém as notas.
    """

    entry_date: date
    amount: Decimal = _Amount
    description: str = Field(max_length=255)
    notes: str | None = None

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        return _clean(value)


class CashflowTransferCreate(BaseModel):
    """`amount` é sempre positivo: sai de `from_account_id` e entra em
    `to_account_id`.
    """

    from_account_id: UUID
    to_account_id: UUID
    entry_date: date
    amount: Decimal = _Amount
    description: str = Field(max_length=255)
    notes: str | None = None

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        return _clean(value)


class CashflowNatureUpdate(BaseModel):
    nature: CashflowNature


class CashflowEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    entry_date: date
    amount: Decimal
    currency_code: str
    description: str
    source: TransactionSource
    nature: CashflowNature
    counterparty_account_id: UUID | None
    transfer_group_id: UUID | None
    notes: str | None
    status: CashflowEntryStatus
    # CF-2. `classified_by_rule_id` explica a classificação: preenchido
    # = aquela regra decidiu; nulo = manual (ou ainda não classificado).
    # `match_text` é o texto normalizado que as regras comparam.
    category_id: UUID | None = None
    classified_by_rule_id: UUID | None = None
    tag_ids: list[UUID] = Field(default_factory=list)
    match_text: str = ""
    # Edição-2: o lançamento que este substituiu numa edição.
    corrects_entry_id: UUID | None = None


class CashflowEntryCount(BaseModel):
    total: int


class CashflowTransferRead(BaseModel):
    """`entries` tem duas pernas entre contas de caixa e uma só quando
    a outra ponta é uma conta BROKERAGE.
    """

    transfer_group_id: UUID
    entries: list[CashflowEntryRead]


class CashflowCurrencySummary(BaseModel):
    """Espelho de `PeriodSummary` — ver a identidade documentada lá."""

    currency_code: str
    entry_count: int
    income: Decimal
    third_party_net: Decimal
    adjustments_net: Decimal
    unclassified_net: Decimal
    internal_transfers_net: Decimal
    expenses: Decimal
    net_invested: Decimal
    liquid_variation: Decimal
    reserve_variation: Decimal
    card_balance_variation: Decimal


class CashflowSummary(BaseModel):
    start: date
    end: date
    totals_by_currency: list[CashflowCurrencySummary]


class CashflowAccountBalance(BaseModel):
    account_id: UUID
    account_name: str
    account_type: AccountType
    currency_code: str
    balance: Decimal


class CashflowCurrencyBalance(BaseModel):
    """Totais de UMA moeda por papel da conta. Não existe um "total
    geral": somar caixa, reserva e dívida de cartão é decisão de quem
    lê, e moedas diferentes nunca são somadas.
    """

    currency_code: str
    liquid: Decimal
    reserve: Decimal
    card: Decimal


class CashflowBalances(BaseModel):
    as_of: date
    accounts: list[CashflowAccountBalance]
    totals_by_currency: list[CashflowCurrencyBalance]
