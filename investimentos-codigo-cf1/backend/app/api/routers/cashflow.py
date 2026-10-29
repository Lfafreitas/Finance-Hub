from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.core.config import settings
from app.models.enums import CashflowImportProfile, CashflowNature
from app.schemas.cashflow import (
    CashflowBalances,
    CashflowEntryCorrect,
    CashflowEntryCount,
    CashflowEntryCreate,
    CashflowEntryRead,
    CashflowNatureUpdate,
    CashflowSummary,
    CashflowTransferCreate,
    CashflowTransferRead,
)
from app.schemas.cashflow_classification import (
    CategoryBreakdown,
    CategoryRead,
    CategoryWrite,
    EntryClassificationWrite,
    RuleApplyRequest,
    RuleApplyResult,
    RuleRead,
    RuleWrite,
    TagRead,
    TagWrite,
)
from app.schemas.cashflow_imports import (
    CashflowImportBatchRead,
    CashflowImportCommitRequest,
    CashflowImportCommitResult,
    CashflowImportPreview,
    CashflowTransferLinkRequest,
    CashflowTransferLinkResult,
    CashflowTransferMatchResult,
)
from app.schemas.cashflow_inbox import InboxListing, InboxRunResult
from app.schemas.cashflow_insights import MonthlyFlows, SpendingInsightsRead
from app.schemas.cashflow_review import (
    BatchClassificationResult,
    BatchClassificationWrite,
    PendingGroups,
)
from app.services import cashflow_classification_service as classification
from app.services import (
    cashflow_import_service,
    cashflow_inbox_service,
    cashflow_insights_service,
    cashflow_review_service,
    cashflow_service,
    cashflow_transfer_service,
)
from app.services.exceptions import (
    AccountNotFoundError,
    CashflowCategoryNotFoundError,
    CashflowClassificationInUseError,
    CashflowEntryAlreadyReversedError,
    CashflowEntryNotFoundError,
    CashflowEntryNotRestorableError,
    CashflowRuleNotFoundError,
    CashflowTagNotFoundError,
    CrossCurrencyTransferError,
    DuplicateRegistryEntryError,
    ImportParsingError,
    ImportRowRejectedError,
    InvalidCashflowClassificationError,
    InvalidCashflowEntryError,
    InvalidCashflowPeriodError,
    InvalidCashflowTransferLinkError,
    InvalidImportSignatureError,
    SameAccountTransferError,
)

router = APIRouter(prefix="/cashflow")

_ERROR_STATUS = {
    AccountNotFoundError: 404,
    CashflowEntryNotFoundError: 404,
    CashflowEntryAlreadyReversedError: 409,
    CashflowEntryNotRestorableError: 409,
    InvalidCashflowEntryError: 400,
    InvalidCashflowPeriodError: 400,
    SameAccountTransferError: 400,
    CrossCurrencyTransferError: 400,
    CashflowCategoryNotFoundError: 404,
    CashflowTagNotFoundError: 404,
    CashflowRuleNotFoundError: 404,
    InvalidCashflowClassificationError: 400,
    CashflowClassificationInUseError: 409,
    DuplicateRegistryEntryError: 409,
    ImportParsingError: 400,
    InvalidImportSignatureError: 409,
    ImportRowRejectedError: 422,
    InvalidCashflowTransferLinkError: 400,
}
_DOMAIN_ERRORS = tuple(_ERROR_STATUS.keys())


def _raise_as_http(exc: Exception):
    raise HTTPException(status_code=_ERROR_STATUS.get(type(exc), 400), detail=str(exc)) from exc


@router.post("/entries", response_model=CashflowEntryRead, status_code=201)
def create_entry(
    payload: CashflowEntryCreate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        entry = cashflow_service.create_entry(db, user_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return classification.to_read(db, [entry])[0]


@router.get("/entries", response_model=list[CashflowEntryRead])
def list_entries(
    account_id: UUID | None = None,
    start: date | None = None,
    end: date | None = None,
    include_reversed: bool = False,
    nature: CashflowNature | None = None,
    category_id: UUID | None = None,
    uncategorized: bool = False,
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=cashflow_service.MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        entries = cashflow_service.list_entries(
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
            limit=limit,
            offset=offset,
        )
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return classification.to_read(db, entries)


@router.get("/entries/count", response_model=CashflowEntryCount)
def count_entries(
    account_id: UUID | None = None,
    start: date | None = None,
    end: date | None = None,
    include_reversed: bool = False,
    nature: CashflowNature | None = None,
    category_id: UUID | None = None,
    uncategorized: bool = False,
    search: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Total da listagem com os mesmos filtros, sem paginação."""
    try:
        total = cashflow_service.count_entries(
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
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return CashflowEntryCount(total=total)


@router.get("/pending/groups", response_model=PendingGroups)
def list_pending_groups(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """O que falta classificar, junto pelo mesmo texto, maiores primeiro,
    com a sugestão tirada do que você já classificou.
    """
    return cashflow_review_service.list_pending_groups(db, user_id, limit=limit)


@router.post("/entries/classify-batch", response_model=BatchClassificationResult)
def classify_batch(
    payload: BatchClassificationWrite,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Mesma classificação manual para vários lançamentos. Tudo ou nada."""
    try:
        return cashflow_review_service.classify_batch(db, user_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.get("/entries/{entry_id}", response_model=CashflowEntryRead)
def get_entry(
    entry_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        entry = cashflow_service.get_entry(db, user_id, entry_id)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return classification.to_read(db, [entry])[0]


@router.put("/entries/{entry_id}/nature", response_model=CashflowEntryRead)
def classify_entry(
    entry_id: UUID,
    payload: CashflowNatureUpdate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        entry = cashflow_service.classify_entry(db, user_id, entry_id, payload.nature)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return classification.to_read(db, [entry])[0]


@router.post("/entries/{entry_id}/reverse", response_model=list[CashflowEntryRead])
def reverse_entry(
    entry_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Devolve todos os lançamentos estornados: um, ou as pernas da
    transferência.
    """
    try:
        entries = cashflow_service.reverse_entry(db, user_id, entry_id)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return classification.to_read(db, entries)


@router.post("/entries/{entry_id}/restore", response_model=list[CashflowEntryRead])
def restore_entry(
    entry_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Desfaz a exclusão. Devolve todos os lançamentos restaurados: um,
    ou as pernas da transferência.
    """
    try:
        entries = cashflow_service.restore_entry(db, user_id, entry_id)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return classification.to_read(db, entries)


@router.post("/entries/{entry_id}/correct", response_model=CashflowEntryRead)
def correct_entry(
    entry_id: UUID,
    payload: CashflowEntryCorrect,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Edita um lançamento manual: o original fica excluído e o novo,
    com os valores corrigidos, é devolvido.
    """
    try:
        entry = cashflow_service.correct_entry(db, user_id, entry_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return classification.to_read(db, [entry])[0]


@router.post("/transfers", response_model=CashflowTransferRead, status_code=201)
def create_transfer(
    payload: CashflowTransferCreate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        legs = cashflow_service.create_transfer(db, user_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return CashflowTransferRead(
        transfer_group_id=legs[0].transfer_group_id, entries=classification.to_read(db, legs)
    )


@router.get("/summary", response_model=CashflowSummary)
def get_summary(
    start: date,
    end: date,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return cashflow_service.get_summary(db, user_id, start, end)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.get("/summary/monthly", response_model=MonthlyFlows)
def get_monthly_flows(
    end: str | None = Query(default=None, description="último mês, AAAA-MM (padrão: o atual)"),
    months: int = Query(default=6, ge=1, le=24),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Renda, gastos, sobra e investido mês a mês, por moeda."""
    try:
        return cashflow_insights_service.get_monthly_flows(db, user_id, end, months)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.get("/insights", response_model=SpendingInsightsRead)
def get_spending_insights(
    month: str | None = Query(default=None, description="AAAA-MM (padrão: o atual)"),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Onde dá para melhorar: o que subiu em relação ao seu histórico,
    o que se repete todo mês, gastos pequenos e onde está o gasto.
    """
    try:
        return cashflow_insights_service.get_spending_insights(db, user_id, month)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.get("/balances", response_model=CashflowBalances)
def get_balances(
    as_of: date | None = None,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    return cashflow_service.get_balances(db, user_id, as_of)


# --- CF-2: classificação ----------------------------------------------------


@router.put("/entries/{entry_id}/classification", response_model=CashflowEntryRead)
def classify_entry_fully(
    entry_id: UUID,
    payload: EntryClassificationWrite,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Classificação manual completa: natureza, categoria e tags."""
    try:
        entry = classification.classify_entry(db, user_id, entry_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return classification.to_read(db, [entry])[0]


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    return classification.list_categories(db, user_id)


@router.post("/categories", response_model=CategoryRead, status_code=201)
def create_category(
    payload: CategoryWrite,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return classification.create_category(db, user_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.post("/categories/defaults", response_model=list[CategoryRead])
def create_default_categories(
    db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)
):
    """Cria o que faltar da árvore inicial e devolve todas as categorias."""
    return classification.create_default_categories(db, user_id)


@router.put("/categories/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: UUID,
    payload: CategoryWrite,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return classification.update_category(db, user_id, category_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(
    category_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        classification.delete_category(db, user_id, category_id)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return Response(status_code=204)


@router.get("/tags", response_model=list[TagRead])
def list_tags(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    return classification.list_tags(db, user_id)


@router.post("/tags", response_model=TagRead, status_code=201)
def create_tag(
    payload: TagWrite,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return classification.create_tag(db, user_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.put("/tags/{tag_id}", response_model=TagRead)
def update_tag(
    tag_id: UUID,
    payload: TagWrite,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return classification.update_tag(db, user_id, tag_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.delete("/tags/{tag_id}", status_code=204)
def delete_tag(
    tag_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        classification.delete_tag(db, user_id, tag_id)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return Response(status_code=204)


@router.get("/rules", response_model=list[RuleRead])
def list_rules(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    return classification.list_rules(db, user_id)


@router.post("/rules", response_model=RuleRead, status_code=201)
def create_rule(
    payload: RuleWrite,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return classification.create_rule(db, user_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.post("/rules/preview", response_model=RuleApplyResult)
def preview_rules(
    payload: RuleApplyRequest | None = None,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Mostra o que a aplicação das regras mudaria. Não grava nada."""
    try:
        return classification.apply_rules(db, user_id, payload or RuleApplyRequest(), dry_run=True)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.post("/rules/apply", response_model=RuleApplyResult)
def apply_rules(
    payload: RuleApplyRequest | None = None,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return classification.apply_rules(db, user_id, payload or RuleApplyRequest(), dry_run=False)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.put("/rules/{rule_id}", response_model=RuleRead)
def update_rule(
    rule_id: UUID,
    payload: RuleWrite,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return classification.update_rule(db, user_id, rule_id, payload)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        classification.delete_rule(db, user_id, rule_id)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return Response(status_code=204)


@router.get("/summary/categories", response_model=CategoryBreakdown)
def get_category_breakdown(
    start: date,
    end: date,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return classification.get_category_breakdown(db, user_id, start, end)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


# --- CF-3: importação e ligação de transferências -----------------------------


@router.post("/imports/preview", response_model=CashflowImportPreview)
async def preview_cashflow_import(
    account_id: UUID = Form(...),
    file: UploadFile = File(...),
    profile: CashflowImportProfile | None = Form(default=None),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Lê o arquivo e mostra o que entraria. Não grava nada. Sem
    `profile`, o formato é detectado pelo conteúdo.
    """
    content = await file.read(settings.import_max_upload_bytes + 1)
    if len(content) > settings.import_max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                "arquivo de importação maior que o limite de "
                f"{settings.import_max_upload_bytes} bytes"
            ),
        )
    try:
        return cashflow_import_service.generate_preview(
            db, user_id, account_id, file.filename or "arquivo", content, profile
        )
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.post("/imports/commit", response_model=CashflowImportCommitResult)
def commit_cashflow_import(
    request: CashflowImportCommitRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        return cashflow_import_service.commit_import(db, user_id, request)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.get("/inbox", response_model=InboxListing)
def list_cashflow_inbox(_user: UUID = Depends(get_current_user_id)):
    """Arquivos esperando na pasta Entrada."""
    return cashflow_inbox_service.list_inbox()


@router.post("/inbox/process", response_model=InboxRunResult)
def process_cashflow_inbox(
    db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)
):
    """Importa os arquivos da pasta Entrada (mesmo caminho da tela, com
    as mesmas conferências) e só DEPOIS do commit move os aceitos para
    `importados/`.
    """
    result, pending = cashflow_inbox_service.process_inbox(db, user_id)
    db.commit()
    cashflow_inbox_service.move_processed(pending)
    return result


@router.get("/imports", response_model=list[CashflowImportBatchRead])
def list_cashflow_imports(
    db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)
):
    return cashflow_import_service.list_batches(db, user_id)


@router.post("/entries/{entry_id}/transfer", response_model=CashflowTransferLinkResult)
def link_transfer(
    entry_id: UUID,
    payload: CashflowTransferLinkRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Transforma lançamentos já existentes em transferência: com o
    lançamento da outra ponta, ou com a conta de investimentos.
    """
    if (payload.counterparty_entry_id is None) == (payload.investment_account_id is None):
        raise HTTPException(
            status_code=400,
            detail="informe o lançamento da outra ponta OU a conta de investimentos",
        )
    try:
        if payload.counterparty_entry_id is not None:
            entries = cashflow_transfer_service.link_entries(
                db, user_id, entry_id, payload.counterparty_entry_id
            )
        else:
            entries = cashflow_transfer_service.mark_investment_transfer(
                db, user_id, entry_id, payload.investment_account_id
            )
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return CashflowTransferLinkResult(entries=classification.to_read(db, entries))


@router.delete("/entries/{entry_id}/transfer", response_model=CashflowTransferLinkResult)
def unlink_transfer(
    entry_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Desfaz a transferência: as pernas voltam a não classificado."""
    try:
        entries = cashflow_transfer_service.unlink_transfer(db, user_id, entry_id)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)
    return CashflowTransferLinkResult(entries=classification.to_read(db, entries))


@router.post("/transfers/match", response_model=CashflowTransferMatchResult)
def match_transfers(
    dry_run: bool = True,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Casa pagamentos de fatura com as faturas. Por padrão só mostra
    (`dry_run=true`); com `dry_run=false`, grava.
    """
    pairs = cashflow_transfer_service.match_invoice_payments(db, user_id, dry_run=dry_run)
    return CashflowTransferMatchResult(
        applied=not dry_run, matches=[cashflow_import_service.to_match(s, r) for s, r in pairs]
    )
