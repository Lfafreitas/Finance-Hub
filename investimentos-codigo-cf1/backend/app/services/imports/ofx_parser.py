"""Parser de OFX (Fase 10a) — escopo: EXTRATOS BANCÁRIOS (`STMTTRN`),
mapeados para DEPOSIT/WITHDRAWAL pelo sinal do valor, usando o `FITID`
nativo do arquivo como referência (não um hash — é um ID de verdade).

OFX de INVESTIMENTO (BUYSTOCK/SELLSTOCK/INCOME, com CUSIP/ticker de
ativo) fica explicitamente FORA do escopo desta fase — exigiria mapear
identificadores de ativo (CUSIP/ISIN) que não temos ainda, e é um
formato mais raro de corretora brasileira exportar. Documentado como
limitação conhecida, não implementado silenciosamente como se
funcionasse.
"""

from __future__ import annotations

import io
from decimal import Decimal

from ofxparse import OfxParser

from app.models.enums import TransactionType
from app.services.exceptions import ImportParsingError
from app.services.imports.common import ParsedRow


def parse_ofx(content: bytes, currency_code: str = "BRL") -> list[ParsedRow]:
    try:
        ofx = OfxParser.parse(io.BytesIO(content))
    except Exception as exc:
        raise ImportParsingError(f"arquivo OFX inválido ou corrompido: {exc}") from exc

    account = getattr(ofx, "account", None)
    statement = getattr(account, "statement", None) if account else None
    transactions = getattr(statement, "transactions", None) if statement else None

    if not transactions:
        raise ImportParsingError(
            "OFX não contém um extrato bancário (STMTTRN) reconhecido — "
            "OFX de investimento (BUYSTOCK/SELLSTOCK) não é suportado nesta fase"
        )

    rows: list[ParsedRow] = []
    for index, txn in enumerate(transactions, start=1):
        amount = Decimal(str(txn.amount))
        transaction_type = TransactionType.DEPOSIT if amount >= 0 else TransactionType.WITHDRAWAL

        rows.append(
            ParsedRow(
                source_row_number=index,
                transaction_type=transaction_type,
                asset_ticker=None,
                quantity=None,
                unit_price=None,
                fees=Decimal(0),
                gross_amount=abs(amount),
                currency_code=currency_code,
                transaction_date=txn.date.date(),
                native_reference=txn.id,
            )
        )

    if not rows:
        raise ImportParsingError("OFX não contém nenhuma transação")

    return rows
