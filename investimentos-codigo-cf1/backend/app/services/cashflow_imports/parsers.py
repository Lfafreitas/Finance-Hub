"""Leitura dos arquivos do banco para o livro de caixa (CF-3).

Só transforma bytes em linhas normalizadas — não consulta banco de
dados, não decide duplicidade, não classifica. Cada perfil foi escrito
contra um arquivo real (CF-0, seções 13 e 14).

Uma linha que não dá para ler NÃO derruba o arquivo: ela sai com
`error` preenchido e não pode ser importada; as demais seguem.
"""

from __future__ import annotations

import csv
import html
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from app.domain.cashflow_engine import normalize_text
from app.models.enums import CashflowImportProfile
from app.services.exceptions import ImportParsingError

_ACCOUNT_CSV_HEADER = "data,valor,identificador,descricao"
_CARD_CSV_HEADER = "date,title,amount"
_MAX_DECIMALS = 4


@dataclass(frozen=True)
class StatementRow:
    """`amount` já está no sinal do livro: positivo entra, negativo sai."""

    row_index: int
    entry_date: date | None
    amount: Decimal | None
    description: str
    external_id: str | None = None
    error: str | None = None
    # Texto usado na chave de duplicidade quando difere da descrição
    # (fatura em PDF: "Estorno de X" é "X" no CSV do mesmo mês).
    dedupe_text: str | None = None


@dataclass(frozen=True)
class StatementCheck:
    """Uma conferência do arquivo contra o total que ele mesmo declara."""

    label: str
    expected: Decimal
    found: Decimal

    @property
    def ok(self) -> bool:
        return self.expected == self.found


@dataclass(frozen=True)
class ParsedStatement:
    profile: CashflowImportProfile
    rows: list[StatementRow] = field(default_factory=list)
    currency_code: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    statement_balance: Decimal | None = None
    statement_balance_date: date | None = None
    # Fatura: conferências feitas na leitura (todas passaram — se uma
    # falha, o arquivo é recusado), vencimento e total a pagar.
    checks: tuple[StatementCheck, ...] = ()
    statement_due_date: date | None = None
    statement_previous: Decimal | None = None
    statement_total: Decimal | None = None


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportParsingError("o arquivo não está em UTF-8") from exc


def detect_profile(content: bytes) -> CashflowImportProfile:
    if content.lstrip()[:5] == b"%PDF-":
        return CashflowImportProfile.NUBANK_CARD_PDF
    text = _decode(content).lstrip()
    if text.upper().startswith("OFXHEADER") or "<OFX>" in text[:2000].upper():
        if "<CCSTMTRS>" in text.upper():
            return CashflowImportProfile.NUBANK_CARD_OFX
        return CashflowImportProfile.NUBANK_ACCOUNT_OFX
    first_line = normalize_text(text.splitlines()[0]) if text else ""
    header = first_line.replace(" ", "")
    if header == _ACCOUNT_CSV_HEADER:
        return CashflowImportProfile.NUBANK_ACCOUNT_CSV
    if header == _CARD_CSV_HEADER:
        return CashflowImportProfile.NUBANK_CARD_CSV
    raise ImportParsingError(
        "formato não reconhecido: esperado extrato da conta Nubank (CSV ou OFX) "
        "ou fatura do cartão Nubank (CSV, OFX ou PDF)"
    )


class _RowError(ValueError):
    """Problema de leitura com mensagem própria para a linha."""


def _br_date(raw: str) -> date:
    """`DD/MM/AAAA`."""
    day, month, year = raw.strip().split("/")
    return date(int(year), int(month), int(day))


def _check_scale(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise InvalidOperation
    if -value.as_tuple().exponent > _MAX_DECIMALS:
        raise InvalidOperation
    return value


def _point_decimal(raw: str) -> Decimal:
    """Número com ponto decimal e sinal colado ("-650.40")."""
    return _check_scale(Decimal(raw.strip()))


def _comma_decimal(raw: str) -> Decimal:
    """Número brasileiro, como na fatura: "1.190,60", "- 175,45"."""
    cleaned = raw.replace(" ", "").replace(".", "").replace(",", ".")
    return _check_scale(Decimal(cleaned))


def _row(index: int, description: str, external_id: str | None, build) -> StatementRow:
    """Monta a linha; qualquer problema de leitura vira `error`."""
    try:
        entry_date, amount = build()
    except (ValueError, InvalidOperation, KeyError, TypeError) as exc:
        reason = str(exc) if isinstance(exc, _RowError) else "data ou valor ilegível"
        return StatementRow(index, None, None, description, external_id, error=reason)
    if amount == 0:
        return StatementRow(index, entry_date, amount, description, external_id, error="valor zero")
    if not description:
        return StatementRow(
            index, entry_date, amount, description, external_id, error="sem descrição"
        )
    return StatementRow(index, entry_date, amount, description, external_id)


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


def parse_account_csv(content: bytes) -> ParsedStatement:
    reader = csv.reader(io.StringIO(_decode(content)))
    lines = [line for line in reader if any(cell.strip() for cell in line)]
    if not lines or normalize_text(",".join(lines[0])).replace(" ", "") != _ACCOUNT_CSV_HEADER:
        raise ImportParsingError(
            "cabeçalho inesperado: esperado Data,Valor,Identificador,Descrição"
        )
    rows: list[StatementRow] = []
    for index, cells in enumerate(lines[1:]):
        padded = [*cells, "", "", "", ""][:4]
        raw_date, raw_amount, external_id, description = (cell.strip() for cell in padded)
        description = _clean(description)

        def build(raw_date=raw_date, raw_amount=raw_amount, external_id=external_id):
            if not external_id:
                raise _RowError("linha sem identificador do banco")
            return _br_date(raw_date), _point_decimal(raw_amount)

        rows.append(_row(index, description, external_id or None, build))
    dates = [r.entry_date for r in rows if r.entry_date]
    return ParsedStatement(
        profile=CashflowImportProfile.NUBANK_ACCOUNT_CSV,
        rows=rows,
        period_start=min(dates, default=None),
        period_end=max(dates, default=None),
    )


def parse_card_csv(content: bytes) -> ParsedStatement:
    reader = csv.reader(io.StringIO(_decode(content)))
    lines = [line for line in reader if any(cell.strip() for cell in line)]
    if not lines or normalize_text(",".join(lines[0])).replace(" ", "") != _CARD_CSV_HEADER:
        raise ImportParsingError("cabeçalho inesperado: esperado date,title,amount")
    rows: list[StatementRow] = []
    for index, cells in enumerate(lines[1:]):
        padded = [*cells, "", "", ""][:3]
        raw_date, title, raw_amount = (cell.strip() for cell in padded)

        def build(raw_date=raw_date, raw_amount=raw_amount):
            # Na fatura a compra é positiva; no livro, saída é negativa.
            return date.fromisoformat(raw_date), -_comma_decimal(raw_amount)

        rows.append(_row(index, _clean(title), None, build))
    dates = [r.entry_date for r in rows if r.entry_date]
    return ParsedStatement(
        profile=CashflowImportProfile.NUBANK_CARD_CSV,
        rows=rows,
        period_start=min(dates, default=None),
        period_end=max(dates, default=None),
    )


def _tag(block: str, name: str) -> str | None:
    """Valor de `<NAME>`: até o próximo `<` ou o fim da linha — o OFX
    1.x (SGML) aceita a tag sem fechamento.
    """
    match = re.search(rf"<{name}>([^<\r\n]*)", block, re.IGNORECASE)
    return html.unescape(match.group(1)).strip() if match else None


def _ofx_date(raw: str | None) -> date:
    if not raw or len(raw) < 8:
        raise ValueError("data ilegível")
    return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))


def parse_account_ofx(content: bytes) -> ParsedStatement:
    text = _decode(content)
    if "<STMTRS>" not in text.upper():
        raise ImportParsingError("OFX sem extrato bancário (<STMTRS>)")
    rows: list[StatementRow] = []
    blocks = re.findall(r"<STMTTRN>(.*?)</STMTTRN>", text, re.IGNORECASE | re.DOTALL)
    for index, block in enumerate(blocks):
        external_id = _tag(block, "FITID")
        description = _clean(_tag(block, "MEMO") or _tag(block, "NAME"))

        def build(block=block, external_id=external_id):
            if not external_id:
                raise _RowError("linha sem identificador do banco")
            return _ofx_date(_tag(block, "DTPOSTED")), _point_decimal(_tag(block, "TRNAMT") or "")

        rows.append(_row(index, description, external_id or None, build))

    def optional_date(name: str, source: str) -> date | None:
        try:
            return _ofx_date(_tag(source, name))
        except ValueError:
            return None

    balance: Decimal | None = None
    balance_date: date | None = None
    ledger = re.search(r"<LEDGERBAL>(.*?)</LEDGERBAL>", text, re.IGNORECASE | re.DOTALL)
    if ledger:
        try:
            balance = _point_decimal(_tag(ledger.group(1), "BALAMT") or "")
            balance_date = optional_date("DTASOF", ledger.group(1))
        except InvalidOperation:
            balance = None
    if balance is not None and balance_date is None:
        balance = None
    currency = _tag(text, "CURDEF")
    return ParsedStatement(
        profile=CashflowImportProfile.NUBANK_ACCOUNT_OFX,
        rows=rows,
        currency_code=currency.upper() if currency else None,
        period_start=optional_date("DTSTART", text),
        period_end=optional_date("DTEND", text),
        statement_balance=balance,
        statement_balance_date=balance_date,
    )


def parse_card_ofx(content: bytes) -> ParsedStatement:
    """Fatura do cartão em OFX (`<CCSTMTRS>`). O valor já vem no sinal do
    livro (compra negativa, pagamento positivo).

    O `FITID` NÃO serve de chave aqui: no arquivo real o IOF de compra
    internacional repete o identificador da compra. A chave é a mesma da
    fatura em CSV (conteúdo + ordem), e por isso importar o CSV, o OFX ou
    o PDF do mesmo mês não duplica. Não há saldo de conta: o
    `LEDGERBAL` do cartão é o da fatura, não o do livro.
    """
    text = _decode(content)
    if "<CCSTMTRS>" not in text.upper():
        raise ImportParsingError("OFX sem fatura de cartão (<CCSTMTRS>)")
    rows: list[StatementRow] = []
    blocks = re.findall(r"<STMTTRN>(.*?)</STMTTRN>", text, re.IGNORECASE | re.DOTALL)
    for index, block in enumerate(blocks):
        description = _clean(_tag(block, "MEMO") or _tag(block, "NAME"))

        def build(block=block):
            return _ofx_date(_tag(block, "DTPOSTED")), _point_decimal(_tag(block, "TRNAMT") or "")

        rows.append(_row(index, description, None, build))
    currency = _tag(text, "CURDEF")
    try:
        start = _ofx_date(_tag(text, "DTSTART"))
        end = _ofx_date(_tag(text, "DTEND"))
    except ValueError:
        start = end = None
    return ParsedStatement(
        profile=CashflowImportProfile.NUBANK_CARD_OFX,
        rows=rows,
        currency_code=currency.upper() if currency else None,
        period_start=start,
        period_end=end,
    )


def _parse_card_pdf(content: bytes) -> ParsedStatement:
    # Import tardio: o módulo do PDF usa os tipos deste.
    from app.services.cashflow_imports.nubank_card_pdf import parse_card_pdf

    return parse_card_pdf(content)


_PARSERS = {
    CashflowImportProfile.NUBANK_ACCOUNT_CSV: parse_account_csv,
    CashflowImportProfile.NUBANK_ACCOUNT_OFX: parse_account_ofx,
    CashflowImportProfile.NUBANK_CARD_CSV: parse_card_csv,
    CashflowImportProfile.NUBANK_CARD_OFX: parse_card_ofx,
    CashflowImportProfile.NUBANK_CARD_PDF: _parse_card_pdf,
}


def parse_statement(
    content: bytes, profile: CashflowImportProfile | None = None
) -> ParsedStatement:
    """Lê o arquivo no perfil informado ou, sem perfil, no detectado."""
    return _PARSERS[profile or detect_profile(content)](content)
