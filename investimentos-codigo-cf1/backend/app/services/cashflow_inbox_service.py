"""Pasta Entrada: carregar extratos e faturas soltando o arquivo numa pasta.

O usuário salva o arquivo do banco (extrato da conta em OFX/CSV, fatura
do cartão em PDF/OFX/CSV) em `settings.inbox_dir`. Aqui cada arquivo
passa pelo MESMO caminho da tela "Importar extrato": prévia (com a
conferência da fatura em PDF) e commit tudo-ou-nada, com as mesmas
chaves de duplicidade — então carregar a pasta duas vezes não duplica.

- A conta de destino sai do formato: extrato -> a conta corrente do
  Nubank; fatura -> o cartão do Nubank. Sem exatamente uma conta
  candidata, o arquivo fica na pasta e nada é gravado.
- Entra o que é válido e novo; linha com erro (data no futuro, valor
  zero) é só contada. Saldo inicial nunca é criado aqui.
- Arquivo recusado (formato desconhecido, fatura que não confere com o
  resumo) fica na pasta, com o motivo na resposta.
- Os aceitos (inclusive "nada novo") vão para `importados/AAAA-MM-DD/`
  DEPOIS do commit (`move_processed`): um arquivo nunca sai da pasta
  sem que o que ele trouxe esteja gravado.

O arquivo em si não é guardado no banco (decisão 14): só o hash e os
dados normalizados, como na importação pela tela.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.account import Account
from app.models.enums import AccountType, CashflowImportProfile
from app.models.institution import Institution
from app.schemas.cashflow_imports import CashflowImportCommitRequest
from app.schemas.cashflow_inbox import InboxFileResult, InboxListing, InboxRunResult
from app.services import cashflow_import_service
from app.services.cashflow_imports.parsers import detect_profile
from app.services.exceptions import (
    ImportParsingError,
    ImportRowRejectedError,
    InvalidCashflowEntryError,
    InvalidImportSignatureError,
)

EXTENSIONS = {".ofx", ".csv", ".pdf"}
DONE_DIR = "importados"
LOG_NAME = "registro.txt"

_CARD_PROFILES = {
    CashflowImportProfile.NUBANK_CARD_CSV,
    CashflowImportProfile.NUBANK_CARD_OFX,
    CashflowImportProfile.NUBANK_CARD_PDF,
}
_REFUSED = (
    ImportParsingError,
    ImportRowRejectedError,
    InvalidCashflowEntryError,
    InvalidImportSignatureError,
)


@dataclass
class _Pending:
    path: Path
    result: InboxFileResult


def inbox_dir() -> Path:
    return Path(settings.inbox_dir)


def pending_files(folder: Path | None = None) -> list[Path]:
    """Arquivos esperando na pasta (sem subpastas, sem temporários)."""
    folder = folder or inbox_dir()
    if not folder.is_dir():
        return []
    return sorted(
        (
            p
            for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in EXTENSIONS and not p.name.startswith(("~$", "."))
        ),
        key=lambda p: p.name.lower(),
    )


def list_inbox() -> InboxListing:
    folder = inbox_dir()
    return InboxListing(
        inbox_dir=str(folder),
        exists=folder.is_dir(),
        files=[p.name for p in pending_files(folder)],
    )


def _nubank_accounts(db: Session, user_id: UUID, account_type: AccountType) -> list[Account]:
    rows = db.execute(
        select(Account, Institution.name)
        .join(Institution, Institution.id == Account.institution_id)
        .where(Account.user_id == user_id, Account.account_type == account_type)
        .order_by(Account.name)
    ).all()
    return [account for account, name in rows if "nubank" in (name or "").lower()]


def _target(
    db: Session, user_id: UUID, profile: CashflowImportProfile
) -> tuple[Account | None, str | None]:
    if profile in _CARD_PROFILES:
        kind, label = AccountType.CREDIT_CARD, "cartão de crédito do Nubank"
    else:
        kind, label = AccountType.CHECKING, "conta corrente do Nubank"
    candidates = _nubank_accounts(db, user_id, kind)
    if len(candidates) == 1:
        return candidates[0], None
    if not candidates:
        return None, f"nenhuma {label} cadastrada: cadastre em Cadastros e carregue de novo"
    names = ", ".join(a.name for a in candidates)
    return None, f"mais de uma {label} ({names}): importe este arquivo pela tela"


def process_inbox(
    db: Session, user_id: UUID, *, folder: Path | None = None, today: date | None = None
) -> tuple[InboxRunResult, list[_Pending]]:
    """Importa cada arquivo da pasta. Não move nada: quem chama dá o
    commit e depois chama `move_processed` com a lista devolvida.
    """
    folder = folder or inbox_dir()
    results: list[InboxFileResult] = []
    to_move: list[_Pending] = []
    for path in pending_files(folder):
        result = _process_file(db, user_id, path, today)
        results.append(result)
        if result.status in ("IMPORTED", "NOTHING_NEW"):
            to_move.append(_Pending(path, result))
    return InboxRunResult(inbox_dir=str(folder), files=results), to_move


def _process_file(db: Session, user_id: UUID, path: Path, today: date | None) -> InboxFileResult:
    base = {"file_name": path.name}
    try:
        size = path.stat().st_size
        if size > settings.import_max_upload_bytes:
            return InboxFileResult(
                **base,
                status="REFUSED",
                message=f"arquivo maior que o limite de {settings.import_max_upload_bytes} bytes",
            )
        content = path.read_bytes()
    except OSError as exc:
        return InboxFileResult(**base, status="REFUSED", message=f"não consegui ler: {exc}")

    try:
        profile = detect_profile(content)
    except ImportParsingError as exc:
        return InboxFileResult(**base, status="REFUSED", message=str(exc))
    account, problem = _target(db, user_id, profile)
    if account is None:
        return InboxFileResult(**base, status="NO_ACCOUNT", profile=profile, message=problem)
    base.update(profile=profile, account_id=account.id, account_name=account.name)

    try:
        with db.begin_nested():
            preview = cashflow_import_service.generate_preview(
                db, user_id, account.id, path.name, content, profile, today=today
            )
            rows = preview.rows
            new = [r.row_index for r in rows if r.error is None and not r.is_duplicate]
            counts = {
                "duplicate_count": sum(1 for r in rows if r.is_duplicate),
                "error_rows": sum(1 for r in rows if r.error is not None),
            }
            if not new:
                return InboxFileResult(
                    **base, **counts, status="NOTHING_NEW", message="nada novo neste arquivo"
                )
            request = CashflowImportCommitRequest(
                **preview.model_dump(
                    exclude={
                        "file_already_imported",
                        "checks",
                        "statement_due_date",
                        "statement_previous",
                        "statement_total",
                    }
                ),
                included_row_indexes=new,
                create_opening_adjustment=False,
            )
            committed = cashflow_import_service.commit_import(db, user_id, request)
    except _REFUSED as exc:
        return InboxFileResult(**base, status="REFUSED", message=str(exc))

    checks = [f"{c.label}: confere" for c in preview.checks if c.ok]
    return InboxFileResult(
        **base,
        **counts,
        status="IMPORTED",
        imported_count=committed.imported_count,
        matched_transfers=len(committed.matched_transfers),
        balance_difference=committed.balance_difference,
        message="; ".join(checks) or None,
    )


def _free_name(folder: Path, name: str) -> Path:
    target = folder / name
    stem, suffix = target.stem, target.suffix
    n = 2
    while target.exists():
        target = folder / f"{stem} ({n}){suffix}"
        n += 1
    return target


def move_processed(
    pending: list[_Pending], folder: Path | None = None, *, now: datetime | None = None
) -> None:
    """Depois do commit: leva os arquivos aceitos para importados/ e
    anota no registro. Falha ao mover não desfaz nada (a próxima carga
    reconhece as linhas como já importadas).
    """
    if not pending:
        return
    folder = folder or inbox_dir()
    now = now or datetime.now().astimezone()  # hora local, para o nome da pasta
    done = folder / DONE_DIR / now.strftime("%Y-%m-%d")
    lines = []
    for item in pending:
        try:
            done.mkdir(parents=True, exist_ok=True)
            target = _free_name(done, item.path.name)
            shutil.move(str(item.path), str(target))
            item.result.moved_to = str(target.relative_to(folder))
        except OSError as exc:
            item.result.message = f"importado, mas não consegui mover o arquivo: {exc}"
        r = item.result
        lines.append(
            f"{now:%Y-%m-%d %H:%M}  {r.file_name}  ->  {r.account_name}: "
            f"{r.imported_count} novo(s), {r.duplicate_count} já existia(m)"
        )
    try:
        with open(folder / DONE_DIR / LOG_NAME, "a", encoding="utf-8") as log:
            log.write("\n".join(lines) + "\n")
    except OSError:
        pass
