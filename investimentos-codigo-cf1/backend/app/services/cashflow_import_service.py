"""Importação do livro de caixa (CF-3): prévia assinada + commit
tudo-ou-nada, no mesmo desenho da importação de investimentos — mas
sem tocar nela (decisão 9: `ofx_parser` e o fluxo de investimentos
ficam como estão).

Deduplicação:

- extrato da conta: pelo identificador que o banco dá a cada linha
  (igual no CSV e no OFX, então importar um e depois o outro não
  duplica);
- fatura do cartão (CSV, OFX ou PDF): por conteúdo — hash de (conta,
  data, título normalizado, valor) + a ordem de ocorrência dentro do
  arquivo, para que duas compras idênticas no mesmo dia sejam duas
  linhas. O PDF escreve alguns títulos de outro jeito ("Estorno de X");
  o parser informa o texto equivalente do CSV para a chave.

Nada do arquivo é guardado além do hash e dos dados normalizados
(decisão 14).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.cashflow_engine import (
    RuleSpec,
    RuleTarget,
    first_matching_rule,
    normalize_text,
    parse_description,
)
from app.models.account import Account
from app.models.cashflow_entry import CashflowEntry
from app.models.cashflow_import_batch import CashflowImportBatch
from app.models.enums import (
    AccountType,
    CashflowEntryStatus,
    CashflowImportProfile,
    CashflowNature,
    TransactionSource,
)
from app.schemas.cashflow_classification import RuleApplyRequest
from app.schemas.cashflow_imports import (
    CashflowImportCheck,
    CashflowImportCommitRequest,
    CashflowImportCommitResult,
    CashflowImportPreview,
    CashflowImportRow,
    CashflowTransferMatch,
)
from app.services import (
    cashflow_classification_service as classification,
)
from app.services import cashflow_service, cashflow_transfer_service
from app.services.cashflow_imports.parsers import ParsedStatement, parse_statement
from app.services.exceptions import (
    ImportParsingError,
    ImportRowRejectedError,
    InvalidCashflowEntryError,
    InvalidImportSignatureError,
)

_CARD_PROFILES = {
    CashflowImportProfile.NUBANK_CARD_CSV,
    CashflowImportProfile.NUBANK_CARD_OFX,
    CashflowImportProfile.NUBANK_CARD_PDF,
}
_SOURCE = {
    CashflowImportProfile.NUBANK_ACCOUNT_CSV: TransactionSource.IMPORT_CSV,
    CashflowImportProfile.NUBANK_ACCOUNT_OFX: TransactionSource.IMPORT_OFX,
    CashflowImportProfile.NUBANK_CARD_CSV: TransactionSource.IMPORT_CSV,
    CashflowImportProfile.NUBANK_CARD_OFX: TransactionSource.IMPORT_OFX,
    CashflowImportProfile.NUBANK_CARD_PDF: TransactionSource.IMPORT_PDF,
}
OPENING_BALANCE_DESCRIPTION = "Saldo inicial (conferido com o extrato)"


def _check_account_matches_profile(account: Account, profile: CashflowImportProfile) -> None:
    is_card_account = account.account_type is AccountType.CREDIT_CARD
    if (profile in _CARD_PROFILES) != is_card_account:
        expected = "cartão de crédito" if profile in _CARD_PROFILES else "conta (não cartão)"
        raise ImportParsingError(
            f"este arquivo é de {expected}, mas {account.name} não é desse tipo"
        )


def _fingerprint(account_id: UUID, entry_date: date, description: str, amount: Decimal) -> str:
    canonical = "|".join(
        [
            str(account_id),
            entry_date.isoformat(),
            normalize_text(description),
            str(amount.normalize()),
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_payload(
    *,
    account_id: UUID,
    profile: CashflowImportProfile,
    file_name: str,
    file_sha256: str,
    period_start: date | None,
    period_end: date | None,
    statement_balance: Decimal | None,
    statement_balance_date: date | None,
    rows: list[CashflowImportRow],
) -> bytes:
    def iso(value: date | None) -> str | None:
        return value.isoformat() if value else None

    payload = {
        "kind": "cashflow-import",
        "account_id": str(account_id),
        "profile": profile.value,
        "file_name": file_name,
        "file_sha256": file_sha256,
        "period_start": iso(period_start),
        "period_end": iso(period_end),
        # `normalize()`: 89.20 e 89.2 são o mesmo saldo depois da ida
        # e volta pelo JSON.
        "statement_balance": (
            str(statement_balance.normalize()) if statement_balance is not None else None
        ),
        "statement_balance_date": iso(statement_balance_date),
        "rows": [
            {
                "row_index": r.row_index,
                "entry_date": iso(r.entry_date),
                "amount": str(r.amount.normalize()) if r.amount is not None else None,
                "description": r.description,
                "external_id": r.external_id,
                "import_fingerprint": r.import_fingerprint,
                # Assinados: o cliente não pode apagar o erro nem a
                # marca de duplicata de uma linha e reenviar.
                "is_duplicate": r.is_duplicate,
                "error": r.error,
            }
            for r in rows
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(payload: bytes) -> str:
    return hmac.new(
        settings.import_hmac_secret.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()


def _existing_keys(db: Session, account_id: UUID) -> tuple[set[str], set[str]]:
    rows = db.execute(
        select(CashflowEntry.external_id, CashflowEntry.import_fingerprint).where(
            CashflowEntry.account_id == account_id,
            (CashflowEntry.external_id.is_not(None))
            | (CashflowEntry.import_fingerprint.is_not(None)),
        )
    ).all()
    return ({r[0] for r in rows if r[0]}, {r[1] for r in rows if r[1]})


def _rule_specs(db: Session, user_id: UUID) -> tuple[list[RuleSpec], dict[UUID, str]]:
    rules = [r for r in classification._load_rules(db, user_id) if r.is_active]
    tags = classification._rule_tag_ids(db, [r.id for r in rules])
    specs = [
        RuleSpec(
            rule_id=r.id,
            priority=r.priority,
            order=index,
            match_type=r.match_type,
            pattern=r.pattern,
            direction=r.direction,
            account_id=r.account_id,
            set_nature=r.set_nature,
            set_category_id=r.set_category_id,
            tag_ids=frozenset(tags.get(r.id, [])),
        )
        for index, r in enumerate(rules)
    ]
    return specs, {r.id: r.name for r in rules}


def generate_preview(
    db: Session,
    user_id: UUID,
    account_id: UUID,
    file_name: str,
    content: bytes,
    profile: CashflowImportProfile | None = None,
    *,
    today: date | None = None,
) -> CashflowImportPreview:
    account = cashflow_service._get_cash_account(db, account_id, user_id)
    parsed: ParsedStatement = parse_statement(content, profile)
    _check_account_matches_profile(account, parsed.profile)
    if parsed.currency_code and parsed.currency_code != account.currency_code:
        raise ImportParsingError(
            f"o arquivo está em {parsed.currency_code} e a conta {account.name} "
            f"em {account.currency_code}"
        )

    file_sha256 = hashlib.sha256(content).hexdigest()
    known_ids, known_fingerprints = _existing_keys(db, account.id)
    specs, rule_names = _rule_specs(db, user_id)
    limit = today or date.today()
    seen_ids: set[str] = set()
    occurrences: dict[str, int] = {}

    rows: list[CashflowImportRow] = []
    for raw in parsed.rows:
        error = raw.error
        fingerprint: str | None = None
        is_duplicate = False
        if error is None and raw.entry_date > limit:
            error = "data no futuro"
        if error is None and raw.external_id is not None:
            if raw.external_id in seen_ids:
                error = "identificador repetido dentro do arquivo"
            seen_ids.add(raw.external_id)
            is_duplicate = raw.external_id in known_ids
        elif error is None:
            base = _fingerprint(
                account.id, raw.entry_date, raw.dedupe_text or raw.description, raw.amount
            )
            occurrence = occurrences.get(base, 0)
            occurrences[base] = occurrence + 1
            fingerprint = f"{base}:{occurrence}"
            is_duplicate = fingerprint in known_fingerprints

        row = CashflowImportRow(
            row_index=raw.row_index,
            entry_date=raw.entry_date,
            amount=raw.amount,
            description=raw.description,
            external_id=raw.external_id,
            import_fingerprint=fingerprint,
            is_duplicate=is_duplicate,
            error=error,
            match_text=parse_description(raw.description).match_text if raw.description else "",
        )
        if error is None and not is_duplicate:
            chosen = first_matching_rule(
                specs,
                RuleTarget(match_text=row.match_text, amount=raw.amount, account_id=account.id),
            )
            if chosen is not None:
                row.suggested_rule_id = chosen.rule_id
                row.suggested_rule_name = rule_names[chosen.rule_id]
                row.suggested_nature = chosen.set_nature
                row.suggested_category_id = chosen.set_category_id
        rows.append(row)

    already = db.execute(
        select(CashflowImportBatch.id)
        .where(
            CashflowImportBatch.account_id == account.id,
            CashflowImportBatch.file_sha256 == file_sha256,
        )
        .limit(1)
    ).first()
    fields = {
        "account_id": account.id,
        "profile": parsed.profile,
        "file_name": (file_name or "arquivo")[:255],
        "file_sha256": file_sha256,
        "period_start": parsed.period_start,
        "period_end": parsed.period_end,
        "statement_balance": parsed.statement_balance,
        "statement_balance_date": parsed.statement_balance_date,
    }
    return CashflowImportPreview(
        **fields,
        file_already_imported=already is not None,
        checks=[
            CashflowImportCheck(label=c.label, expected=c.expected, found=c.found, ok=c.ok)
            for c in parsed.checks
        ],
        statement_due_date=parsed.statement_due_date,
        statement_previous=parsed.statement_previous,
        statement_total=parsed.statement_total,
        rows=rows,
        signature=_sign(_canonical_payload(**fields, rows=rows)),
    )


def _account_balance(db: Session, account_id: UUID, as_of: date) -> Decimal:
    total = db.execute(
        select(func.coalesce(func.sum(CashflowEntry.amount), 0)).where(
            CashflowEntry.account_id == account_id,
            CashflowEntry.status == CashflowEntryStatus.ACTIVE,
            CashflowEntry.entry_date <= as_of,
        )
    ).scalar_one()
    return Decimal(total)


def commit_import(
    db: Session, user_id: UUID, request: CashflowImportCommitRequest
) -> CashflowImportCommitResult:
    account = cashflow_service._get_cash_account(db, request.account_id, user_id)
    expected = _sign(
        _canonical_payload(
            account_id=request.account_id,
            profile=request.profile,
            file_name=request.file_name,
            file_sha256=request.file_sha256,
            period_start=request.period_start,
            period_end=request.period_end,
            statement_balance=request.statement_balance,
            statement_balance_date=request.statement_balance_date,
            rows=request.rows,
        )
    )
    if not hmac.compare_digest(expected, request.signature):
        raise InvalidImportSignatureError(
            "assinatura inválida — o conteúdo não corresponde exatamente à prévia original"
        )
    _check_account_matches_profile(account, request.profile)

    included = set(request.included_row_indexes)
    known = {row.row_index for row in request.rows}
    if not included <= known:
        raise ImportRowRejectedError(f"linhas inexistentes na prévia: {sorted(included - known)}")
    chosen = sorted(
        (row for row in request.rows if row.row_index in included),
        key=lambda row: (row.entry_date or date.min, row.row_index),
    )
    for row in chosen:
        if row.error:
            raise ImportRowRejectedError(
                f"linha {row.row_index}: {row.error} — não pode ser incluída"
            )
        if row.is_duplicate:
            raise ImportRowRejectedError(f"linha {row.row_index}: já foi importada nesta conta")

    opening: Decimal | None = None
    if request.create_opening_adjustment:
        if request.statement_balance is None or request.statement_balance_date is None:
            raise InvalidCashflowEntryError(
                "este arquivo não informa saldo final: o saldo inicial não pode ser calculado"
            )
        has_entries = db.execute(
            select(CashflowEntry.id).where(CashflowEntry.account_id == account.id).limit(1)
        ).first()
        if has_entries:
            raise InvalidCashflowEntryError(
                f"a conta {account.name} já tem lançamentos: o saldo inicial só é criado "
                "na primeira importação"
            )
        importable = {r.row_index for r in request.rows if not r.error and not r.is_duplicate}
        if importable - included:
            raise InvalidCashflowEntryError(
                "para criar o saldo inicial, todas as linhas válidas do arquivo precisam ser incluídas"
            )

    source = _SOURCE[request.profile]
    created: list[CashflowEntry] = []
    with db.begin_nested():
        batch = CashflowImportBatch(
            user_id=user_id,
            account_id=account.id,
            profile=request.profile,
            file_name=request.file_name,
            file_sha256=request.file_sha256,
            period_start=request.period_start,
            period_end=request.period_end,
            rows_total=len(request.rows),
            rows_imported=len(chosen),
            statement_balance=request.statement_balance,
            statement_balance_date=request.statement_balance_date,
        )
        db.add(batch)
        db.flush()
        for row in chosen:
            entry = CashflowEntry(
                account_id=account.id,
                entry_date=row.entry_date,
                amount=row.amount,
                currency_code=account.currency_code,
                description=row.description,
                source=source,
                nature=CashflowNature.UNCLASSIFIED,
                external_id=row.external_id,
                import_fingerprint=row.import_fingerprint,
                import_batch_id=batch.id,
            )
            db.add(entry)
            created.append(entry)
        try:
            db.flush()
        except IntegrityError as exc:
            # Corrida com outra importação do mesmo arquivo: o índice
            # único recusa, e o lote inteiro é desfeito.
            raise ImportRowRejectedError(
                "alguma linha já foi importada nesta conta por outra operação — gere a prévia de novo"
            ) from exc

        if request.create_opening_adjustment:
            in_statement = sum(
                (e.amount for e in created if e.entry_date <= request.statement_balance_date),
                start=Decimal(0),
            )
            opening = request.statement_balance - in_statement
            if opening != 0:
                first_day = min(
                    [request.period_start or date.max, *(e.entry_date for e in created)]
                )
                db.add(
                    CashflowEntry(
                        account_id=account.id,
                        entry_date=first_day,
                        amount=opening,
                        currency_code=account.currency_code,
                        description=OPENING_BALANCE_DESCRIPTION,
                        source=source,
                        nature=CashflowNature.ADJUSTMENT,
                        import_batch_id=batch.id,
                    )
                )
                db.flush()

        # Primeiro as transferências (pagamento de fatura), depois as
        # regras: uma regra de texto não pode classificar como gasto o
        # que é só dinheiro mudando de conta.
        pairs = cashflow_transfer_service.match_invoice_payments(db, user_id, dry_run=False)
        new_ids = {e.id for e in created}
        applied = classification.apply_rules(
            db, user_id, RuleApplyRequest(), dry_run=False, only_entry_ids=new_ids
        )

    system_balance: Decimal | None = None
    difference: Decimal | None = None
    if request.statement_balance is not None and request.statement_balance_date is not None:
        system_balance = _account_balance(db, account.id, request.statement_balance_date)
        difference = system_balance - request.statement_balance
    return CashflowImportCommitResult(
        batch_id=batch.id,
        imported_count=len(created),
        not_included_count=len(request.rows) - len(created),
        opening_adjustment=opening,
        matched_transfers=[to_match(sent, received) for sent, received in pairs],
        rules_applied_count=len(applied.changes),
        statement_balance=request.statement_balance,
        statement_balance_date=request.statement_balance_date,
        system_balance=system_balance,
        balance_difference=difference,
    )


def to_match(sent: CashflowEntry, received: CashflowEntry) -> CashflowTransferMatch:
    return CashflowTransferMatch(
        transfer_group_id=sent.transfer_group_id,
        sent_entry_id=sent.id,
        received_entry_id=received.id,
        amount=received.amount.quantize(Decimal("0.0001")),
        sent_date=sent.entry_date,
        received_date=received.entry_date,
    )


def list_batches(db: Session, user_id: UUID) -> list[CashflowImportBatch]:
    stmt = (
        select(CashflowImportBatch)
        .where(CashflowImportBatch.user_id == user_id)
        .order_by(CashflowImportBatch.created_at.desc(), CashflowImportBatch.id)
    )
    return list(db.execute(stmt).scalars().all())
