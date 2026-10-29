"""Orquestração da importação (Fase 10a).

Fluxo: parser (puro, `app/services/imports/`) → resolução de ativo →
cálculo de external_reference (FITID para OFX; fingerprint SHA-256 +
índice de ocorrência para CSV/XLSX) → checagem de duplicidade exata e
"possível" → ordenação cronológica → assinatura HMAC (preview) /
verificação HMAC + commit tudo-ou-nada (commit).

Nunca insere em `Transaction` diretamente — todo INSERT passa por
`transaction_service.create_imported_transaction` (D-G2), que já
reaplica a mesma validação de posse de conta e D-A3 da criação manual.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.asset import Asset
from app.models.enums import TransactionSource, TransactionStatus
from app.models.transaction import Transaction
from app.schemas.imports import (
    ImportCommitRequest,
    ImportCommitResult,
    ImportPreviewResponse,
    ImportRow,
)
from app.services import transaction_service
from app.services.exceptions import (
    ImportParsingError,
    ImportRowRejectedError,
    InvalidImportSignatureError,
)
from app.services.imports.common import ParsedRow
from app.services.imports.csv_parser import parse_csv
from app.services.imports.ofx_parser import parse_ofx
from app.services.imports.xlsx_parser import parse_xlsx
from app.services.transaction_service import (
    _get_investment_account,  # reaproveitado de propósito (D-G2)
)

_SOURCE_FORMAT_TO_ENUM: dict[str, TransactionSource] = {
    "CSV": TransactionSource.IMPORT_CSV,
    "XLSX": TransactionSource.IMPORT_XLSX,
    "OFX": TransactionSource.IMPORT_OFX,
}


def _parse_file(source_format: str, content: bytes, account_currency: str) -> list[ParsedRow]:
    if source_format == "CSV":
        return parse_csv(content)
    if source_format == "XLSX":
        return parse_xlsx(content)
    if source_format == "OFX":
        return parse_ofx(content, currency_code=account_currency)
    raise ImportParsingError(f"formato de importação não suportado: {source_format}")


def _content_fingerprint(
    account_id: UUID,
    row: ParsedRow,
    asset_id: UUID | None,
) -> str:
    """SHA-256 dos campos normalizados disponíveis (seção 2.2 da
    proposta aprovada) — nunca do texto bruto da linha do arquivo.
    """
    canonical = "|".join(
        [
            str(account_id),
            row.transaction_date.isoformat(),
            row.transaction_type.value,
            str(asset_id) if asset_id else "",
            str(Decimal(row.quantity).normalize()) if row.quantity is not None else "",
            str(Decimal(row.unit_price).normalize()) if row.unit_price is not None else "",
            str(Decimal(row.fees).normalize()),
            str(Decimal(row.gross_amount).normalize()),
            row.currency_code,
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _resolve_assets(db: Session, tickers: set[str]) -> dict[str, list[tuple[UUID, str]]]:
    """ticker -> [(asset_id, moeda do ativo), ...]. Devolve TODOS os
    ativos com aquele ticker: a unicidade do cadastro é (ticker, país),
    então o mesmo ticker pode existir em dois países — e escolher um
    deles em silêncio poderia lançar a operação no ativo errado.
    """
    if not tickers:
        return {}
    stmt = (
        select(Asset.ticker, Asset.id, Asset.currency_code)
        .where(Asset.ticker.in_(tickers))
        .order_by(Asset.country)
    )
    found: dict[str, list[tuple[UUID, str]]] = {}
    for ticker, asset_id, currency_code in db.execute(stmt):
        found.setdefault(ticker, []).append((asset_id, currency_code))
    return found


def _canonical_payload_bytes(account_id: UUID, source_format: str, rows: list[ImportRow]) -> bytes:
    """Serialização determinística usada tanto para assinar (preview)
    quanto para verificar (commit) — mesma ordem de campos sempre,
    Decimal/date/UUID convertidos para string antes do JSON.
    """
    payload = {
        "account_id": str(account_id),
        "source_format": source_format,
        "rows": [
            {
                "row_index": r.row_index,
                "transaction_type": r.transaction_type.value,
                "asset_id": str(r.asset_id) if r.asset_id else None,
                "quantity": str(r.quantity) if r.quantity is not None else None,
                "unit_price": str(r.unit_price) if r.unit_price is not None else None,
                "fees": str(r.fees),
                "gross_amount": str(r.gross_amount),
                "currency_code": r.currency_code,
                "transaction_date": r.transaction_date.isoformat(),
                "external_reference": r.external_reference,
                # `error` faz parte do conteúdo assinado: o commit
                # recusa linhas com erro, então um cliente não pode
                # simplesmente apagar o erro de uma linha (ex.: ativo
                # não cadastrado) e reenviar com a mesma assinatura.
                "error": r.error,
            }
            for r in rows
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(payload_bytes: bytes) -> str:
    return hmac.new(
        settings.import_hmac_secret.encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()


def generate_preview(
    db: Session, user_id: UUID, account_id: UUID, source_format: str, content: bytes
) -> ImportPreviewResponse:
    account = _get_investment_account(db, account_id, user_id)

    parsed_rows = _parse_file(source_format, content, account.currency_code)

    tickers = {r.asset_ticker for r in parsed_rows if r.asset_ticker}
    asset_by_ticker = _resolve_assets(db, tickers)

    # Fingerprint + índice de ocorrência DENTRO deste lote (seção 2.3) —
    # linhas legitimamente idênticas no mesmo arquivo não se bloqueiam
    # umas às outras.
    occurrence_counter: dict[str, int] = {}
    enriched: list[tuple[ParsedRow, UUID | None, str, str | None]] = []
    for row in parsed_rows:
        asset_id = None
        error = None
        if row.asset_ticker:
            candidates = asset_by_ticker.get(row.asset_ticker, [])
            if not candidates:
                error = (
                    f"ativo '{row.asset_ticker}' não cadastrado — cadastre manualmente "
                    "antes de importar"
                )
            elif len(candidates) > 1:
                error = (
                    f"ticker '{row.asset_ticker}' existe em mais de um país — o arquivo não "
                    "diz qual; lance esta operação manualmente"
                )
            else:
                asset_id, asset_currency = candidates[0]
                if row.currency_code != asset_currency:
                    # Mesma regra que o commit aplica (Moeda-3), só que
                    # avisada já na preview: sem conversão nem
                    # inferência — a linha não pode ser incluída.
                    error = (
                        f"moeda da linha ({row.currency_code}) difere da moeda do ativo "
                        f"{row.asset_ticker} ({asset_currency}) — informe a coluna 'moeda' "
                        "correta no arquivo"
                    )

        if row.native_reference is not None:
            external_reference = row.native_reference
        else:
            fingerprint = _content_fingerprint(account_id, row, asset_id)
            occurrence = occurrence_counter.get(fingerprint, 0)
            occurrence_counter[fingerprint] = occurrence + 1
            external_reference = f"{fingerprint}:{occurrence}"

        enriched.append((row, asset_id, external_reference, error))

    # Ordena cronologicamente ANTES de atribuir row_index final —
    # commit reordena de novo como defesa em profundidade (mesmo
    # critério, resultado idêntico se o conteúdo não mudou).
    enriched.sort(key=lambda item: item[0].transaction_date)

    external_refs = [ref for _row, _asset_id, ref, _error in enriched]
    existing_refs = set()
    if external_refs:
        stmt = select(Transaction.external_reference).where(
            Transaction.account_id == account_id,
            Transaction.external_reference.in_(external_refs),
        )
        existing_refs = {r for (r,) in db.execute(stmt)}

    rows: list[ImportRow] = []
    for index, (row, asset_id, external_reference, error) in enumerate(enriched):
        is_exact_duplicate = external_reference in existing_refs

        possible_duplicate = False
        duplicate_reason = None
        if not is_exact_duplicate and error is None:
            stmt = select(Transaction.id).where(
                Transaction.account_id == account_id,
                Transaction.status == TransactionStatus.ACTIVE,
                Transaction.transaction_type == row.transaction_type,
                Transaction.transaction_date == row.transaction_date,
                Transaction.asset_id == asset_id,
                Transaction.quantity == row.quantity,
                Transaction.unit_price == row.unit_price,
                Transaction.gross_amount == row.gross_amount,
            )
            match = db.execute(stmt).first()
            if match is not None:
                possible_duplicate = True
                duplicate_reason = (
                    "encontrada 1 transação ativa existente com os mesmos dados — "
                    "verifique antes de confirmar (pode ser a mesma já lançada por outra via)"
                )

        rows.append(
            ImportRow(
                row_index=index,
                transaction_type=row.transaction_type,
                asset_ticker=row.asset_ticker,
                asset_id=asset_id,
                quantity=row.quantity,
                unit_price=row.unit_price,
                fees=row.fees,
                gross_amount=row.gross_amount,
                currency_code=row.currency_code,
                transaction_date=row.transaction_date,
                external_reference=external_reference,
                is_exact_duplicate=is_exact_duplicate,
                possible_duplicate=possible_duplicate,
                duplicate_reason=duplicate_reason,
                error=error,
            )
        )

    signature = _sign(_canonical_payload_bytes(account_id, source_format, rows))
    return ImportPreviewResponse(
        account_id=account_id, source_format=source_format, rows=rows, signature=signature
    )


def commit_import(db: Session, user_id: UUID, request: ImportCommitRequest) -> ImportCommitResult:
    if request.source_format not in _SOURCE_FORMAT_TO_ENUM:
        raise ImportParsingError(f"source_format inválido: {request.source_format}")

    expected_signature = _sign(
        _canonical_payload_bytes(request.account_id, request.source_format, request.rows)
    )
    if not hmac.compare_digest(expected_signature, request.signature):
        raise InvalidImportSignatureError(
            "assinatura inválida — o conteúdo não corresponde exatamente à preview original"
        )

    # Defesa em profundidade: reordena de novo por transaction_date,
    # não confia que a ordem sobreviveu à ida e volta com o cliente.
    ordered_rows = sorted(request.rows, key=lambda r: r.transaction_date)
    included = {i for i in request.included_row_indexes}

    source = _SOURCE_FORMAT_TO_ENUM[request.source_format]
    created_ids: list[UUID] = []

    # Tudo-ou-nada garantido AQUI, por SAVEPOINT: se qualquer linha
    # falhar, as linhas já gravadas deste lote são desfeitas antes de a
    # exceção sair — sem depender de o chamador reverter a sessão.
    with db.begin_nested():
        for row in ordered_rows:
            if row.row_index not in included:
                continue
            if row.error:
                raise ImportRowRejectedError(
                    f"linha {row.row_index}: {row.error} — não pode ser incluída"
                )

            try:
                transaction = transaction_service.create_imported_transaction(
                    db,
                    user_id,
                    account_id=request.account_id,
                    asset_id=row.asset_id,
                    transaction_type=row.transaction_type,
                    quantity=row.quantity,
                    unit_price=row.unit_price,
                    fees=row.fees,
                    gross_amount=row.gross_amount,
                    currency_code=row.currency_code,
                    transaction_date=row.transaction_date,
                    source=source,
                    external_reference=row.external_reference,
                )
            except Exception as exc:
                # Tudo-ou-nada: a exceção atravessa o SAVEPOINT acima,
                # que desfaz o lote inteiro.
                raise ImportRowRejectedError(f"linha {row.row_index}: {exc}") from exc

            created_ids.append(transaction.id)

    return ImportCommitResult(
        imported_count=len(created_ids),
        excluded_count=len(request.rows) - len(created_ids),
        transaction_ids=created_ids,
    )
