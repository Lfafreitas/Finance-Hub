"""Ligar lançamentos já existentes como transferência (CF-3).

Um arquivo de banco traz cada ponta de uma transferência como uma
linha solta. Ligar as pontas é CLASSIFICAÇÃO: nenhum fato muda — só
`nature`, a contraparte e o grupo.

Três operações:

- ligar dois lançamentos (conta -> cartão, conta -> reserva...);
- marcar um lançamento como aporte/resgate em conta de investimentos
  (uma perna só, porque a outra ponta é do livro de investimentos);
- desfazer a ligação: as pernas voltam a não classificado.

Transferência para uma conta de caixa que não é importada (outro banco
sem extrato) NÃO existe aqui: sem a segunda perna o caixa não fecha.
Esse dinheiro fica como o usuário classificar.
"""

from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from app.domain.cashflow_engine import (
    TransferCandidate,
    find_invoice_payment_pairs,
    parse_description,
)
from app.domain.cashflow_engine.transfers import DEFAULT_MAX_DAYS
from app.models.account import Account
from app.models.cashflow_classification import cashflow_entry_tags
from app.models.cashflow_entry import CashflowEntry
from app.models.enums import AccountType, CashflowEntryStatus, CashflowNature
from app.repositories import cashflow as cashflow_repo
from app.services import cashflow_service
from app.services.exceptions import (
    AccountNotFoundError,
    CashflowEntryAlreadyReversedError,
    InvalidCashflowTransferLinkError,
)

# Ligação manual aceita uma folga maior que o casamento automático:
# TED e boleto podem levar alguns dias entre as duas pontas.
MANUAL_LINK_MAX_DAYS = 10


def _linkable(db: Session, user_id: UUID, entry_id: UUID) -> CashflowEntry:
    entry = cashflow_service._get_owned_entry(db, user_id, entry_id, lock=True)
    if entry.status is CashflowEntryStatus.REVERSED:
        raise CashflowEntryAlreadyReversedError(f"lançamento {entry_id} está estornado")
    if entry.nature is CashflowNature.TRANSFER:
        raise InvalidCashflowTransferLinkError(
            f"lançamento {entry_id} já faz parte de uma transferência"
        )
    return entry


def _set_transfer(db: Session, entry: CashflowEntry, counterparty_id: UUID, group_id: UUID) -> None:
    entry.nature = CashflowNature.TRANSFER
    entry.counterparty_account_id = counterparty_id
    entry.transfer_group_id = group_id
    # Transferência não tem categoria nem regra; as tags saem junto.
    entry.category_id = None
    entry.classified_by_rule_id = None
    db.execute(delete(cashflow_entry_tags).where(cashflow_entry_tags.c.entry_id == entry.id))


def link_entries(
    db: Session,
    user_id: UUID,
    entry_id: UUID,
    counterparty_entry_id: UUID,
    *,
    max_days: int = MANUAL_LINK_MAX_DAYS,
) -> list[CashflowEntry]:
    if entry_id == counterparty_entry_id:
        raise InvalidCashflowTransferLinkError("um lançamento não é transferência para ele mesmo")
    # Ordem fixa de bloqueio: duas ligações cruzadas não se travam.
    first_id, second_id = sorted([entry_id, counterparty_entry_id], key=str)
    by_id = {
        first_id: _linkable(db, user_id, first_id),
        second_id: _linkable(db, user_id, second_id),
    }
    a, b = by_id[entry_id], by_id[counterparty_entry_id]
    if a.account_id == b.account_id:
        raise InvalidCashflowTransferLinkError("os dois lançamentos são da mesma conta")
    if a.currency_code != b.currency_code:
        raise InvalidCashflowTransferLinkError(
            "transferência entre moedas diferentes está fora do escopo desta fase"
        )
    if a.amount != -b.amount:
        raise InvalidCashflowTransferLinkError(
            f"os valores não se anulam ({a.amount} e {b.amount}): não é a mesma transferência"
        )
    if abs((a.entry_date - b.entry_date).days) > max_days:
        raise InvalidCashflowTransferLinkError(
            f"as datas estão a mais de {max_days} dias uma da outra"
        )
    group_id = uuid.uuid4()
    with db.begin_nested():
        _set_transfer(db, a, b.account_id, group_id)
        _set_transfer(db, b, a.account_id, group_id)
        db.flush()
    return [a, b]


def mark_investment_transfer(
    db: Session, user_id: UUID, entry_id: UUID, account_id: UUID
) -> list[CashflowEntry]:
    """Saída vira aporte, entrada vira resgate — o sinal do lançamento
    já diz qual dos dois.
    """
    entry = _linkable(db, user_id, entry_id)
    account = db.get(Account, account_id)
    if account is None or account.user_id != user_id:
        raise AccountNotFoundError(f"conta {account_id} não encontrada")
    if account.account_type is not AccountType.BROKERAGE:
        raise InvalidCashflowTransferLinkError(
            f"{account.name} é uma conta de caixa: ligue este lançamento ao lançamento "
            "correspondente dela"
        )
    if account.currency_code != entry.currency_code:
        raise InvalidCashflowTransferLinkError(
            "transferência entre moedas diferentes está fora do escopo desta fase"
        )
    with db.begin_nested():
        _set_transfer(db, entry, account.id, uuid.uuid4())
        db.flush()
    return [entry]


def unlink_transfer(db: Session, user_id: UUID, entry_id: UUID) -> list[CashflowEntry]:
    """Desfaz a transferência inteira: toda perna do grupo volta a não
    classificado (e a ser elegível para as regras). Nenhum fato muda.
    """
    entry = cashflow_service._get_owned_entry(db, user_id, entry_id, lock=True)
    if entry.status is CashflowEntryStatus.REVERSED:
        raise CashflowEntryAlreadyReversedError(f"lançamento {entry_id} está estornado")
    if entry.nature is not CashflowNature.TRANSFER or entry.transfer_group_id is None:
        raise InvalidCashflowTransferLinkError(f"lançamento {entry_id} não é uma transferência")
    legs = cashflow_repo.list_group_entries(db, entry.transfer_group_id)
    with db.begin_nested():
        for leg in legs:
            leg.nature = CashflowNature.UNCLASSIFIED
            leg.counterparty_account_id = None
            leg.transfer_group_id = None
        db.flush()
    return legs


def match_invoice_payments(
    db: Session, user_id: UUID, *, dry_run: bool, max_days: int = DEFAULT_MAX_DAYS
) -> list[tuple[CashflowEntry, CashflowEntry]]:
    """Casa "Pagamento de fatura" (conta) com "Pagamento recebido"
    (cartão). Nunca toca em lançamento classificado à mão, e só casa
    sem ambiguidade.
    """
    accounts = {a.id: a for a in cashflow_repo.list_cash_accounts(db, user_id)}
    if not accounts:
        return []
    stmt = (
        select(CashflowEntry)
        .where(
            CashflowEntry.account_id.in_(list(accounts)),
            CashflowEntry.status == CashflowEntryStatus.ACTIVE,
            CashflowEntry.nature != CashflowNature.TRANSFER,
            # Elegível = ninguém decidiu à mão: ainda não classificado,
            # ou classificado por regra. Uma regra de texto pode ter
            # pego "Pagamento recebido" antes de a outra ponta chegar;
            # o casamento exato (valor, dia, banco) vale mais que ela.
            or_(
                CashflowEntry.classified_by_rule_id.is_not(None),
                and_(
                    CashflowEntry.nature == CashflowNature.UNCLASSIFIED,
                    CashflowEntry.category_id.is_(None),
                ),
            ),
        )
        .order_by(CashflowEntry.entry_date, CashflowEntry.created_at, CashflowEntry.id)
    )
    if not dry_run:
        stmt = stmt.with_for_update()
    entries = {e.id: e for e in db.execute(stmt).scalars().all()}
    candidates = [
        TransferCandidate(
            entry_id=e.id,
            account_id=e.account_id,
            account_type=accounts[e.account_id].account_type,
            institution_id=accounts[e.account_id].institution_id,
            currency_code=e.currency_code,
            entry_date=e.entry_date,
            amount=e.amount,
            match_text=parse_description(e.description).match_text,
        )
        for e in entries.values()
    ]
    pairs = [
        (entries[sent.entry_id], entries[received.entry_id])
        for sent, received in find_invoice_payment_pairs(candidates, max_days)
    ]
    if not dry_run:
        with db.begin_nested():
            for sent, received in pairs:
                group_id = uuid.uuid4()
                _set_transfer(db, sent, received.account_id, group_id)
                _set_transfer(db, received, sent.account_id, group_id)
            db.flush()
    return pairs
