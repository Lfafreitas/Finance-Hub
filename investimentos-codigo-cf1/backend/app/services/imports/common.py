"""Tipos e utilitários compartilhados pelos parsers de importação
(CSV/XLSX/OFX). Cada parser é puro: recebe bytes, devolve uma lista de
`ParsedRow` — nada aqui toca banco. A resolução de `asset_id`, cálculo
de `external_reference`/fingerprint e checagem de duplicata acontecem
depois, em `app/services/import_service.py` (que já precisa de banco).

Formato de CSV/XLSX aceito nesta fase (10a) — fixo e documentado, não
detecção automática de layout de corretora (fora do escopo desta
etapa): colunas obrigatórias `data`, `tipo`, `valor`, `moeda`; colunas
`ativo`, `quantidade`, `preco_unitario`, `taxas` obrigatórias apenas
para tipos que envolvem um ativo (BUY/SELL/proventos/eventos
societários) — `taxas` é opcional em qualquer caso, default 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from app.models.enums import TransactionType
from app.services.exceptions import ImportParsingError

# Rótulo em português (como aparece no arquivo) -> TransactionType.
# Só os tipos que fazem sentido vir de um extrato/nota externa — não
# inclui TRANSFER_OUT/IN (D-A2 já trata transferência à parte) nem
# REVERSED (não é um tipo de lançamento, é um estado).
TYPE_LABELS: dict[str, TransactionType] = {
    "COMPRA": TransactionType.BUY,
    "VENDA": TransactionType.SELL,
    "DEPOSITO": TransactionType.DEPOSIT,
    "RETIRADA": TransactionType.WITHDRAWAL,
    "DIVIDENDO": TransactionType.DIVIDEND,
    "JCP": TransactionType.JCP,
    "RENDIMENTO": TransactionType.INCOME,
    "TAXA": TransactionType.FEE,
    "BONIFICACAO": TransactionType.BONUS_SHARES,
    "DESDOBRAMENTO": TransactionType.STOCK_SPLIT,
    "GRUPAMENTO": TransactionType.REVERSE_SPLIT,
}

_TYPES_REQUIRING_ASSET = {
    TransactionType.BUY,
    TransactionType.SELL,
    TransactionType.DIVIDEND,
    TransactionType.JCP,
    TransactionType.INCOME,
    TransactionType.BONUS_SHARES,
    TransactionType.STOCK_SPLIT,
    TransactionType.REVERSE_SPLIT,
}
_TYPES_REQUIRING_QUANTITY_PRICE = {TransactionType.BUY, TransactionType.SELL}


@dataclass(frozen=True)
class ParsedRow:
    """Uma linha já normalizada, mas ainda sem `asset_id` resolvido
    nem `external_reference` calculado — isso é trabalho do
    `import_service`, que tem acesso ao banco.
    """

    source_row_number: int  # 1-based, posição original no arquivo (para mensagens de erro)
    transaction_type: TransactionType
    asset_ticker: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    fees: Decimal
    gross_amount: Decimal
    currency_code: str
    transaction_date: date
    native_reference: str | None = None  # FITID (OFX) — None para CSV/XLSX


def parse_decimal(value: str | None, field_name: str, row_number: int) -> Decimal | None:
    if value is None or value.strip() == "":
        return None
    try:
        return Decimal(value.strip().replace(",", "."))
    except InvalidOperation as exc:
        raise ImportParsingError(
            f"linha {row_number}: valor inválido em '{field_name}': '{value}'"
        ) from exc


def parse_date(value: str | None, row_number: int) -> date:
    if value is None or value.strip() == "":
        raise ImportParsingError(f"linha {row_number}: campo 'data' obrigatório e ausente")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ImportParsingError(
            f"linha {row_number}: data inválida '{value}' — use o formato AAAA-MM-DD"
        ) from exc


def resolve_transaction_type(value: str | None, row_number: int) -> TransactionType:
    if value is None or value.strip() == "":
        raise ImportParsingError(f"linha {row_number}: campo 'tipo' obrigatório e ausente")
    label = value.strip().upper()
    if label not in TYPE_LABELS:
        aceitos = ", ".join(sorted(TYPE_LABELS))
        raise ImportParsingError(
            f"linha {row_number}: tipo '{value}' não reconhecido — aceitos: {aceitos}"
        )
    return TYPE_LABELS[label]


def build_row(
    *,
    source_row_number: int,
    transaction_type: TransactionType,
    asset_ticker: str | None,
    quantity: Decimal | None,
    unit_price: Decimal | None,
    fees: Decimal | None,
    gross_amount: Decimal | None,
    currency_code: str | None,
    transaction_date: date,
    native_reference: str | None = None,
) -> ParsedRow:
    if gross_amount is None:
        raise ImportParsingError(f"linha {source_row_number}: campo 'valor' obrigatório e ausente")

    if transaction_type in _TYPES_REQUIRING_ASSET and not asset_ticker:
        raise ImportParsingError(
            f"linha {source_row_number}: tipo {transaction_type.value} exige o campo 'ativo'"
        )
    if transaction_type in _TYPES_REQUIRING_QUANTITY_PRICE and (
        quantity is None or unit_price is None
    ):
        raise ImportParsingError(
            f"linha {source_row_number}: tipo {transaction_type.value} exige 'quantidade' e 'preco_unitario'"
        )

    return ParsedRow(
        source_row_number=source_row_number,
        transaction_type=transaction_type,
        asset_ticker=asset_ticker.strip().upper() if asset_ticker else None,
        quantity=quantity,
        unit_price=unit_price,
        fees=fees if fees is not None else Decimal(0),
        gross_amount=gross_amount,
        currency_code=(currency_code or "BRL").strip().upper(),
        transaction_date=transaction_date,
        native_reference=native_reference,
    )
