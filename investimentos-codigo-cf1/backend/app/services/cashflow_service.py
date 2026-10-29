"""Livro de caixa (CF-1): lançamentos, transferências, classificação,
estorno, saldos e resumo do período.

A regra de cálculo mora só em `app.domain.cashflow_engine`; este
service valida, grava e traduz registros em fatos para o motor.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.domain.cashflow_engine import (
    BalanceCalculator,
    CashEntryFact,
    CashflowSummaryCalculator,
)
from app.models.account import Account
from app.models.cashflow_classification import CashflowCategory, cashflow_entry_tags
from app.models.cashflow_entry import CashflowEntry
from app.models.enums import (
    AccountType,
    CashflowEntryStatus,
    CashflowNature,
    TransactionSource,
)
from app.repositories import cashflow as cashflow_repo
from app.schemas.cashflow import (
    CashflowAccountBalance,
    CashflowBalances,
    CashflowCurrencyBalance,
    CashflowCurrencySummary,
    CashflowEntryCorrect,
    CashflowEntryCreate,
    CashflowSummary,
    CashflowTransferCreate,
)
from app.services.exceptions import (
    AccountNotFoundError,
    CashflowCategoryNotFoundError,
    CashflowEntryAlreadyReversedError,
    CashflowEntryNotFoundError,
    CashflowEntryNotRestorableError,
    CrossCurrencyTransferError,
    InvalidCashflowEntryError,
    InvalidCashflowPeriodError,
    SameAccountTransferError,
)

MAX_PAGE_SIZE = 500
_ZERO = Decimal("0.0000")
_LIQUID_TYPES = {AccountType.CHECKING, AccountType.CASH}


def _get_owned_account(db: Session, account_id: UUID, user_id: UUID) -> Account:
    account = db.get(Account, account_id)
    if account is None or account.user_id != user_id:
        raise AccountNotFoundError(f"conta {account_id} não encontrada")
    return account


def _get_cash_account(db: Session, account_id: UUID, user_id: UUID) -> Account:
    account = _get_owned_account(db, account_id, user_id)
    if account.account_type is AccountType.BROKERAGE:
        raise InvalidCashflowEntryError(
            f"conta {account.name} é de investimentos: não recebe lançamento de caixa"
        )
    return account


def _check_date(entry_date: date, today: date | None) -> None:
    if entry_date > (today or date.today()):
        raise InvalidCashflowEntryError("a data do lançamento não pode estar no futuro")


def create_entry(
    db: Session, user_id: UUID, payload: CashflowEntryCreate, *, today: date | None = None
) -> CashflowEntry:
    account = _get_cash_account(db, payload.account_id, user_id)
    if payload.amount == 0:
        raise InvalidCashflowEntryError("o valor do lançamento não pode ser zero")
    if payload.nature is CashflowNature.TRANSFER:
        raise InvalidCashflowEntryError(
            "transferência entre contas é registrada em /cashflow/transfers"
        )
    _check_date(payload.entry_date, today)

    entry = CashflowEntry(
        account_id=account.id,
        entry_date=payload.entry_date,
        amount=payload.amount,
        currency_code=account.currency_code,
        description=payload.description,
        source=TransactionSource.MANUAL,
        nature=payload.nature,
        notes=payload.notes,
    )
    db.add(entry)
    db.flush()
    # Devolve o valor como o banco guardou (escala 4), não como chegou.
    db.refresh(entry)
    return entry


def create_transfer(
    db: Session, user_id: UUID, payload: CashflowTransferCreate, *, today: date | None = None
) -> list[CashflowEntry]:
    """Grava a transferência inteira ou nada.

    - caixa -> caixa: duas pernas, mesmo grupo, valores opostos;
    - caixa -> BROKERAGE (aporte) ou BROKERAGE -> caixa (resgate): uma
      perna só, no lado do caixa;
    - BROKERAGE -> BROKERAGE não é do livro de caixa.
    """
    if payload.from_account_id == payload.to_account_id:
        raise SameAccountTransferError("conta de origem e destino não podem ser a mesma")
    if payload.amount <= 0:
        raise InvalidCashflowEntryError("o valor da transferência deve ser maior que zero")
    _check_date(payload.entry_date, today)

    from_account = _get_owned_account(db, payload.from_account_id, user_id)
    to_account = _get_owned_account(db, payload.to_account_id, user_id)
    if from_account.currency_code != to_account.currency_code:
        raise CrossCurrencyTransferError(
            "transferência entre contas de moedas diferentes está fora do escopo desta fase"
        )
    from_is_cash = from_account.account_type is not AccountType.BROKERAGE
    to_is_cash = to_account.account_type is not AccountType.BROKERAGE
    if not from_is_cash and not to_is_cash:
        raise InvalidCashflowEntryError(
            "transferência entre duas contas de investimentos não é do livro de caixa"
        )

    group_id = uuid.uuid4()
    legs: list[CashflowEntry] = []

    def _leg(account: Account, counterparty: Account, amount: Decimal) -> None:
        legs.append(
            CashflowEntry(
                account_id=account.id,
                entry_date=payload.entry_date,
                amount=amount,
                currency_code=account.currency_code,
                description=payload.description,
                source=TransactionSource.MANUAL,
                nature=CashflowNature.TRANSFER,
                counterparty_account_id=counterparty.id,
                transfer_group_id=group_id,
                notes=payload.notes,
            )
        )

    if from_is_cash:
        _leg(from_account, to_account, -payload.amount)
    if to_is_cash:
        _leg(to_account, from_account, payload.amount)

    with db.begin_nested():
        db.add_all(legs)
        db.flush()
    for leg in legs:
        db.refresh(leg)
    return legs


def _get_owned_entry(
    db: Session, user_id: UUID, entry_id: UUID, *, lock: bool = False
) -> CashflowEntry:
    entry = db.get(CashflowEntry, entry_id, with_for_update=lock)
    if entry is None:
        raise CashflowEntryNotFoundError(f"lançamento {entry_id} não encontrado")
    account = db.get(Account, entry.account_id)
    if account is None or account.user_id != user_id:
        raise CashflowEntryNotFoundError(f"lançamento {entry_id} não encontrado")
    return entry


def get_entry(db: Session, user_id: UUID, entry_id: UUID) -> CashflowEntry:
    return _get_owned_entry(db, user_id, entry_id)


def classify_entry(
    db: Session, user_id: UUID, entry_id: UUID, nature: CashflowNature
) -> CashflowEntry:
    """Muda só a classificação; o fato não é tocado. Transferência não
    entra nem sai por aqui: ela tem contraparte e, entre contas de
    caixa, uma segunda perna que precisa mudar junto.
    """
    entry = _get_owned_entry(db, user_id, entry_id, lock=True)
    if entry.status is CashflowEntryStatus.REVERSED:
        raise CashflowEntryAlreadyReversedError(f"lançamento {entry_id} está estornado")
    if entry.nature is CashflowNature.TRANSFER or nature is CashflowNature.TRANSFER:
        raise InvalidCashflowEntryError(
            "transferência não é reclassificada: estorne e registre de novo"
        )
    entry.nature = nature
    # Decisão manual: nenhuma regra volta a mexer neste lançamento.
    entry.classified_by_rule_id = None
    db.flush()
    return entry


def reverse_entry(db: Session, user_id: UUID, entry_id: UUID) -> list[CashflowEntry]:
    """Estorna o lançamento. Em transferência, todas as pernas do grupo
    são estornadas juntas — nunca sobra perna órfã.
    """
    entry = _get_owned_entry(db, user_id, entry_id, lock=True)
    if entry.status is CashflowEntryStatus.REVERSED:
        raise CashflowEntryAlreadyReversedError(f"lançamento {entry_id} já está estornado")
    targets = (
        cashflow_repo.list_group_entries(db, entry.transfer_group_id)
        if entry.transfer_group_id is not None
        else [entry]
    )
    with db.begin_nested():
        for target in targets:
            target.status = CashflowEntryStatus.REVERSED
        db.flush()
    return targets


def restore_entry(db: Session, user_id: UUID, entry_id: UUID) -> list[CashflowEntry]:
    """Desfaz a exclusão (Edição-2): REVERSED -> ACTIVE. Em
    transferência, todas as pernas do grupo voltam juntas.

    Recusa o lançamento que foi substituído por uma edição: a versão
    nova é a que vale, e restaurar a antiga contaria o mesmo fato duas
    vezes.
    """
    entry = _get_owned_entry(db, user_id, entry_id, lock=True)
    if entry.status is CashflowEntryStatus.ACTIVE:
        raise CashflowEntryNotRestorableError(f"lançamento {entry_id} não está excluído")
    targets = (
        cashflow_repo.list_group_entries(db, entry.transfer_group_id)
        if entry.transfer_group_id is not None
        else [entry]
    )
    target_ids = [target.id for target in targets]
    replaced = db.execute(
        select(CashflowEntry.id).where(CashflowEntry.corrects_entry_id.in_(target_ids))
    ).first()
    if replaced is not None:
        raise CashflowEntryNotRestorableError(
            "este lançamento foi editado: a versão nova é a que vale. "
            "Para voltar aos valores antigos, edite a versão nova"
        )
    with db.begin_nested():
        for target in targets:
            target.status = CashflowEntryStatus.ACTIVE
        db.flush()
    return targets


def correct_entry(
    db: Session,
    user_id: UUID,
    entry_id: UUID,
    payload: CashflowEntryCorrect,
    *,
    today: date | None = None,
) -> CashflowEntry:
    """Edita um lançamento manual (Edição-2): exclui o original e grava
    um novo com os valores corrigidos, ligado por `corrects_entry_id`.
    O fato antigo nunca é sobrescrito.

    A classificação (natureza, categoria, tags, notas) é copiada; as
    notas podem ser trocadas no mesmo pedido.

    Só vale para lançamento manual e que não seja transferência:
    - importado: data e valor vêm do banco; reimportar o extrato não
      recriaria a linha, e o saldo deixaria de bater com o banco;
    - transferência: tem duas pontas; exclua e registre de novo.
    """
    original = _get_owned_entry(db, user_id, entry_id, lock=True)
    if original.status is CashflowEntryStatus.REVERSED:
        raise CashflowEntryAlreadyReversedError(f"lançamento {entry_id} está excluído")
    if original.source is not TransactionSource.MANUAL:
        raise InvalidCashflowEntryError(
            "lançamento importado do banco não é editado: data e valor vêm do extrato. "
            "Mude a classificação ou exclua"
        )
    if original.nature is CashflowNature.TRANSFER:
        raise InvalidCashflowEntryError("transferência não é editada: exclua e registre de novo")
    if payload.amount == 0:
        raise InvalidCashflowEntryError("o valor do lançamento não pode ser zero")
    _check_date(payload.entry_date, today)

    tag_ids = list(
        db.execute(
            select(cashflow_entry_tags.c.tag_id).where(
                cashflow_entry_tags.c.entry_id == original.id
            )
        ).scalars()
    )
    with db.begin_nested():
        original.status = CashflowEntryStatus.REVERSED
        corrected = CashflowEntry(
            account_id=original.account_id,
            entry_date=payload.entry_date,
            amount=payload.amount,
            currency_code=original.currency_code,
            description=payload.description,
            source=TransactionSource.MANUAL,
            nature=original.nature,
            category_id=original.category_id,
            classified_by_rule_id=original.classified_by_rule_id,
            notes=payload.notes if payload.notes is not None else original.notes,
            corrects_entry_id=original.id,
        )
        db.add(corrected)
        db.flush()
        if tag_ids:
            db.execute(
                insert(cashflow_entry_tags),
                [{"entry_id": corrected.id, "tag_id": tag_id} for tag_id in tag_ids],
            )
    db.refresh(corrected)
    return corrected


def _entry_filters(
    db: Session,
    user_id: UUID,
    *,
    account_id: UUID | None,
    start: date | None,
    end: date | None,
    include_reversed: bool,
    nature: CashflowNature | None,
    category_id: UUID | None,
    uncategorized: bool,
    search: str | None,
) -> tuple[list[UUID], dict]:
    """Valida os filtros e devolve (contas, filtros do repositório).
    Filtrar por uma categoria-mãe inclui as filhas — o mesmo critério
    do total por categoria.
    """
    if start is not None and end is not None and start > end:
        raise InvalidCashflowPeriodError("início do período depois do fim")
    if uncategorized and category_id is not None:
        raise InvalidCashflowEntryError(
            "escolha uma categoria OU os lançamentos sem categoria, não os dois"
        )
    if account_id is not None:
        account_ids = [_get_owned_account(db, account_id, user_id).id]
    else:
        account_ids = [a.id for a in cashflow_repo.list_cash_accounts(db, user_id)]
    category_ids: list[UUID] | None = None
    if category_id is not None:
        category = db.get(CashflowCategory, category_id)
        if category is None or category.user_id != user_id:
            raise CashflowCategoryNotFoundError(f"categoria {category_id} não encontrada")
        children = db.execute(
            select(CashflowCategory.id).where(CashflowCategory.parent_id == category.id)
        ).scalars()
        category_ids = [category.id, *children]
    text = " ".join((search or "").split())
    return account_ids, {
        "start": start,
        "end": end,
        "include_reversed": include_reversed,
        "nature": nature,
        "category_ids": category_ids,
        "uncategorized": uncategorized,
        "search": text or None,
    }


def list_entries(
    db: Session,
    user_id: UUID,
    *,
    account_id: UUID | None = None,
    start: date | None = None,
    end: date | None = None,
    include_reversed: bool = False,
    nature: CashflowNature | None = None,
    category_id: UUID | None = None,
    uncategorized: bool = False,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[CashflowEntry]:
    account_ids, filters = _entry_filters(
        db,
        user_id,
        account_id=account_id,
        start=start,
        end=end,
        include_reversed=include_reversed,
        nature=nature,
        category_id=category_id,
        uncategorized=uncategorized,
        search=search,
    )
    return cashflow_repo.list_entries(
        db,
        account_ids,
        limit=max(1, min(limit, MAX_PAGE_SIZE)),
        offset=max(0, offset),
        **filters,
    )


def count_entries(
    db: Session,
    user_id: UUID,
    *,
    account_id: UUID | None = None,
    start: date | None = None,
    end: date | None = None,
    include_reversed: bool = False,
    nature: CashflowNature | None = None,
    category_id: UUID | None = None,
    uncategorized: bool = False,
    search: str | None = None,
) -> int:
    """Quantos lançamentos a listagem devolveria com os mesmos filtros,
    sem paginação.
    """
    account_ids, filters = _entry_filters(
        db,
        user_id,
        account_id=account_id,
        start=start,
        end=end,
        include_reversed=include_reversed,
        nature=nature,
        category_id=category_id,
        uncategorized=uncategorized,
        search=search,
    )
    return cashflow_repo.count_entries(db, account_ids, **filters)


def _load_facts(
    db: Session, user_id: UUID, *, until: date
) -> tuple[list[Account], list[CashEntryFact]]:
    accounts = cashflow_repo.list_cash_accounts(db, user_id)
    by_id = {a.id: a for a in accounts}
    entries = cashflow_repo.list_active_entries(db, list(by_id), until=until)
    counterparty_ids = {
        e.counterparty_account_id for e in entries if e.counterparty_account_id is not None
    }
    counterparty_types = dict(by_id.items())
    for missing in counterparty_ids - set(by_id):
        counterparty_types[missing] = db.get(Account, missing)
    facts = [
        CashEntryFact(
            account_id=entry.account_id,
            account_type=by_id[entry.account_id].account_type,
            currency_code=entry.currency_code,
            entry_date=entry.entry_date,
            amount=entry.amount,
            nature=entry.nature,
            counterparty_account_type=(
                counterparty_types[entry.counterparty_account_id].account_type
                if entry.counterparty_account_id is not None
                else None
            ),
            category_id=entry.category_id,
        )
        for entry in entries
    ]
    return accounts, facts


def get_summary(db: Session, user_id: UUID, start: date, end: date) -> CashflowSummary:
    if start > end:
        raise InvalidCashflowPeriodError("início do período depois do fim")
    _accounts, facts = _load_facts(db, user_id, until=end)
    summaries = CashflowSummaryCalculator.calculate(facts, start, end)
    return CashflowSummary(
        start=start,
        end=end,
        totals_by_currency=[
            CashflowCurrencySummary(
                currency_code=s.currency_code,
                entry_count=s.entry_count,
                income=s.income,
                third_party_net=s.third_party_net,
                adjustments_net=s.adjustments_net,
                unclassified_net=s.unclassified_net,
                internal_transfers_net=s.internal_transfers_net,
                expenses=s.expenses,
                net_invested=s.net_invested,
                liquid_variation=s.liquid_variation,
                reserve_variation=s.reserve_variation,
                card_balance_variation=s.card_balance_variation,
            )
            for s in summaries.values()
        ],
    )


def get_balances(db: Session, user_id: UUID, as_of: date | None = None) -> CashflowBalances:
    """Toda conta de caixa aparece, mesmo sem lançamento (saldo zero)."""
    as_of = as_of or date.today()
    accounts, facts = _load_facts(db, user_id, until=as_of)
    computed = {b.account_id: b.balance for b in BalanceCalculator.calculate(facts, as_of)}

    rows: list[CashflowAccountBalance] = []
    totals: dict[str, dict[str, Decimal]] = {}
    for account in accounts:
        balance = computed.get(account.id, _ZERO)
        rows.append(
            CashflowAccountBalance(
                account_id=account.id,
                account_name=account.name,
                account_type=account.account_type,
                currency_code=account.currency_code,
                balance=balance,
            )
        )
        bucket = totals.setdefault(
            account.currency_code, {"liquid": _ZERO, "reserve": _ZERO, "card": _ZERO}
        )
        if account.account_type in _LIQUID_TYPES:
            bucket["liquid"] += balance
        elif account.account_type is AccountType.SAVINGS:
            bucket["reserve"] += balance
        else:
            bucket["card"] += balance
    return CashflowBalances(
        as_of=as_of,
        accounts=rows,
        totals_by_currency=[
            CashflowCurrencyBalance(currency_code=code, **totals[code]) for code in sorted(totals)
        ],
    )
