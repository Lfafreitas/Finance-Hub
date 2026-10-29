"""Parser de CSV (Fase 10a). Formato fixo documentado em `common.py` —
não há detecção automática de layout de corretora nesta fase.
"""

from __future__ import annotations

import csv
import io

from app.services.exceptions import ImportParsingError
from app.services.imports.common import (
    ParsedRow,
    build_row,
    parse_date,
    parse_decimal,
    resolve_transaction_type,
)

_REQUIRED_COLUMNS = {"data", "tipo", "valor"}


def parse_csv(content: bytes) -> list[ParsedRow]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportParsingError("arquivo CSV não está em UTF-8 — reexporte em UTF-8") from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ImportParsingError("arquivo CSV vazio ou sem cabeçalho")

    header = {name.strip().lower() for name in reader.fieldnames}
    missing = _REQUIRED_COLUMNS - header
    if missing:
        raise ImportParsingError(f"CSV sem as colunas obrigatórias: {', '.join(sorted(missing))}")

    rows: list[ParsedRow] = []
    for row_number, raw_row in enumerate(reader, start=2):  # linha 1 é o cabeçalho
        normalized = {k.strip().lower(): v for k, v in raw_row.items() if k}
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
        raise ImportParsingError("CSV não contém nenhuma linha de dado")

    return rows
