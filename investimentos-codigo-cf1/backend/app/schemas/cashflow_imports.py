"""Schemas da importação do livro de caixa (CF-3)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import CashflowImportProfile, CashflowNature
from app.schemas.cashflow import CashflowEntryRead


class CashflowImportRow(BaseModel):
    """Uma linha lida do arquivo. Os campos de fato (`entry_date`,
    `amount`, `description`, `external_id`, `import_fingerprint`,
    `is_duplicate`, `error`) fazem parte do conteúdo assinado. Os de
    sugestão (`match_text`, `suggested_*`) são só informativos: a
    classificação é recalculada na hora de gravar.
    """

    row_index: int
    entry_date: date | None
    amount: Decimal | None
    description: str
    external_id: str | None = None
    import_fingerprint: str | None = None
    is_duplicate: bool = False
    error: str | None = None
    match_text: str = ""
    suggested_rule_id: UUID | None = None
    suggested_rule_name: str | None = None
    suggested_nature: CashflowNature | None = None
    suggested_category_id: UUID | None = None


class CashflowImportCheck(BaseModel):
    """Conferência do arquivo contra o total que ele mesmo declara
    (fatura em PDF). Só aparece na prévia quando passou: se falha, o
    arquivo é recusado antes.
    """

    label: str
    expected: Decimal
    found: Decimal
    ok: bool


class CashflowImportPreview(BaseModel):
    account_id: UUID
    profile: CashflowImportProfile
    file_name: str
    file_sha256: str
    period_start: date | None
    period_end: date | None
    statement_balance: Decimal | None
    statement_balance_date: date | None
    # Informativo: este mesmo arquivo já foi confirmado nesta conta.
    file_already_imported: bool = False
    rows: list[CashflowImportRow]
    signature: str
    # Informativos (fatura em PDF): fora da assinatura, não vão ao commit.
    checks: list[CashflowImportCheck] = []
    statement_due_date: date | None = None
    statement_previous: Decimal | None = None
    statement_total: Decimal | None = None


class CashflowImportCommitRequest(BaseModel):
    """A prévia devolvida intacta + as linhas escolhidas.

    `create_opening_adjustment`: na PRIMEIRA importação de uma conta, a
    partir de um arquivo que informa o saldo final, cria o lançamento de
    saldo inicial que faz o saldo do sistema bater com o do banco.
    """

    account_id: UUID
    profile: CashflowImportProfile
    file_name: str
    file_sha256: str
    period_start: date | None
    period_end: date | None
    statement_balance: Decimal | None
    statement_balance_date: date | None
    rows: list[CashflowImportRow]
    signature: str
    included_row_indexes: list[int]
    create_opening_adjustment: bool = False


class CashflowTransferMatch(BaseModel):
    """Um pagamento de fatura casado: saída na conta, entrada no cartão.
    `transfer_group_id` é nulo na prévia (o grupo só existe ao gravar).
    """

    transfer_group_id: UUID | None
    sent_entry_id: UUID
    received_entry_id: UUID
    amount: Decimal
    sent_date: date
    received_date: date


class CashflowImportCommitResult(BaseModel):
    """`balance_difference` = saldo do sistema − saldo do arquivo, na
    data do saldo do arquivo. Zero quer dizer que a conta bate com o
    banco. Nulo quando o arquivo não informa saldo.
    """

    batch_id: UUID
    imported_count: int
    not_included_count: int
    opening_adjustment: Decimal | None
    matched_transfers: list[CashflowTransferMatch]
    rules_applied_count: int
    statement_balance: Decimal | None
    statement_balance_date: date | None
    system_balance: Decimal | None
    balance_difference: Decimal | None


class CashflowImportBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    profile: CashflowImportProfile
    file_name: str
    file_sha256: str
    period_start: date | None
    period_end: date | None
    rows_total: int
    rows_imported: int
    statement_balance: Decimal | None
    statement_balance_date: date | None
    created_at: datetime


class CashflowTransferLinkRequest(BaseModel):
    """Informe UM dos dois: o lançamento da outra ponta (entre contas de
    caixa) ou a conta de investimentos (aporte/resgate).
    """

    counterparty_entry_id: UUID | None = None
    investment_account_id: UUID | None = None


class CashflowTransferLinkResult(BaseModel):
    entries: list[CashflowEntryRead]


class CashflowTransferMatchResult(BaseModel):
    applied: bool
    matches: list[CashflowTransferMatch]
