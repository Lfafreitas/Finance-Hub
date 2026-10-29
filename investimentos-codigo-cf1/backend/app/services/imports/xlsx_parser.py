"""Parser de XLSX (Fase 10a). Mesmo formato de colunas do CSV (ver
`common.py`) — só muda o mecanismo de leitura (openpyxl em vez de
texto).
"""

from __future__ import annotations

import io
from datetime import date, datetime

import openpyxl

from app.services.exceptions import ImportParsingError
from app.services.imports.common import (
    ParsedRow,
    build_row,
    parse_date,
    parse_decimal,
    resolve_transaction_type,
)

_REQUIRED_COLUMNS = {"data", "tipo", "valor"}


def _cell_to_str(value) -> str | None:
    if value is None:
        return None
    # Célula formatada como DATA no Excel chega do openpyxl como
    # `datetime` (ou `date`); `str()` daria "2026-01-05 00:00:00", que
    # `parse_date` (AAAA-MM-DD) rejeita. Normaliza para a data ISO —
    # é o caso mais comum numa planilha real, não uma exceção.
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def parse_xlsx(content: bytes) -> list[ParsedRow]:
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl lança várias exceções distintas para arquivo inválido
        raise ImportParsingError(f"arquivo XLSX inválido ou corrompido: {exc}") from exc

    sheet = workbook.active
    rows_iter = sheet.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration as exc:
        raise ImportParsingError("planilha XLSX vazia") from exc

    header = [str(c).strip().lower() if c is not None else "" for c in header_row]
    missing = _REQUIRED_COLUMNS - set(header)
    if missing:
        raise ImportParsingError(f"XLSX sem as colunas obrigatórias: {', '.join(sorted(missing))}")

    rows: list[ParsedRow] = []
    for row_number, raw_row in enumerate(rows_iter, start=2):
        normalized = {
            header[i]: _cell_to_str(v)
            for i, v in enumerate(raw_row)
            if i < len(header) and header[i]
        }
        if all(v is None for v in normalized.values()):
            continue  # linha em branco no meio da planilha

        transaction_type = resolve_transaction_type(normalized.get("tipo"), row_number)
        rows.append(
            build_row(
                source_row_number=row_number,
                transaction_type=transaction_type,
                asset_ticker=normalized.get("ativo"),
                quantity=parse_decimal(normalized.get("quantidade"), "quantidade", row_number),
                unit_price=parse_decimal(
                    normalized.get("preco_unitario"), "preco_unitario", row_number
                ),
                fees=parse_decimal(normalized.get("taxas"), "taxas", row_number),
                gross_amount=parse_decimal(normalized.get("valor"), "valor", row_number),
                currency_code=normalized.get("moeda"),
                transaction_date=parse_date(normalized.get("data"), row_number),
            )
        )

    if not rows:
        raise ImportParsingError("XLSX não contém nenhuma linha de dado")

    return rows
