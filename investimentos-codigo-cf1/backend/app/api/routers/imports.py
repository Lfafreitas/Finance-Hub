from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.core.config import settings
from app.schemas.imports import ImportCommitRequest, ImportCommitResult, ImportPreviewResponse
from app.services import import_service, reconciliation_service
from app.services.exceptions import (
    AccountNotFoundError,
    ImportParsingError,
    ImportRowRejectedError,
    InvalidImportSignatureError,
    NotAnInvestmentAccountError,
)

router = APIRouter()

_ERROR_STATUS = {
    AccountNotFoundError: 404,
    ImportParsingError: 400,
    NotAnInvestmentAccountError: 400,
    InvalidImportSignatureError: 409,
    ImportRowRejectedError: 422,
}
_DOMAIN_ERRORS = tuple(_ERROR_STATUS.keys())

_VALID_FORMATS = {"CSV", "XLSX", "OFX"}


def _raise_as_http(exc: Exception):
    status_code = _ERROR_STATUS.get(type(exc), 400)
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/imports/preview", response_model=ImportPreviewResponse)
async def preview_import(
    account_id: UUID = Form(...),
    source_format: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    normalized_format = source_format.strip().upper()
    if normalized_format not in _VALID_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"source_format deve ser um de {sorted(_VALID_FORMATS)} (recebido: {source_format})",
        )

    # Lê no máximo o teto + 1 byte: suficiente para saber se estourou,
    # sem nunca carregar um arquivo arbitrariamente grande na memória.
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
        return import_service.generate_preview(db, user_id, account_id, normalized_format, content)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)


@router.post("/imports/commit", response_model=ImportCommitResult)
def commit_import(
    request: ImportCommitRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        result = import_service.commit_import(db, user_id, request)
    except _DOMAIN_ERRORS as exc:
        _raise_as_http(exc)

    # Fase 10b, unidade 7 (ponto crítico da retomada): o commit
    # financeiro do import precisa estar REALMENTE confirmado no banco
    # ANTES de agendar a BackgroundTask de reconciliação — senão a
    # sessão independente que ela abre não enxergaria as Transactions
    # recém-importadas (get_db só comitaria depois que a BackgroundTask
    # já tivesse rodado). Por isso este `db.commit()` explícito aqui,
    # só neste endpoint: get_db ainda vai chamar commit() de novo ao
    # final do request, mas nesse ponto não há mais nada pendente — é
    # um commit vazio, inofensivo. Nenhuma mudança no mecanismo geral
    # de `get_db` foi necessária.
    db.commit()

    # Uma ÚNICA tarefa por LOTE — nunca uma chamada síncrona por linha
    # dentro deste endpoint. Só agenda se algo foi de fato importado.
    if result.transaction_ids:
        background_tasks.add_task(
            reconciliation_service.run_batch_reconciliation_task,
            user_id,
            request.account_id,
            result.transaction_ids,
        )

    return result
