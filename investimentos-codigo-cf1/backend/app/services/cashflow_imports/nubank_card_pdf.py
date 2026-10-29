"""Fatura do cartão Nubank em PDF (perfil NUBANK_CARD_PDF).

Lê a seção TRANSAÇÕES da fatura e CONFERE com o resumo da própria
fatura antes de deixar importar:

1. compras: a soma de todas as linhas que não são pagamento (compras,
   parcelas, Pix no crédito parcelado, estornos, créditos, descontos de
   antecipação) tem de ser igual a "Total de compras de todos os
   cartões" + "Outros lançamentos";
2. pagamentos: a soma das linhas "Pagamento em DD MMM" tem de ser igual
   a "Pagamento recebido".

Qualquer diferença, de um centavo que seja, recusa o arquivo inteiro:
uma linha lida errado (ou pulada) nunca entra calada no livro.

A leitura tem duas camadas:

- `pdf_lines`: PDF -> linhas de texto (células em ordem da esquerda
  para a direita), com pdfminer.six;
- `parse_fatura_lines`: linhas -> `ParsedStatement`. Pura, testável sem
  PDF.

As datas da fatura vêm sem ano ("30 MAR"). O ano sai da data de
emissão da fatura: uma data que cairia depois dela é do ano anterior
(fatura de fevereiro com compra em "30 DEZ").

Descrições, para casar com o CSV/OFX do mesmo mês:

- "Pagamento em 31 MAR" vira "Pagamento recebido" — o mesmo texto do
  CSV/OFX, e o que o casamento de pagamento de fatura procura;
- "Estorno de X" fica como está, mas a chave de duplicidade usa "X",
  que é como o CSV escreve o estorno;
- "Saldo restante da fatura anterior" não é gasto novo: fica de fora
  (se tiver valor e esse valor fizer parte do total, a conferência
  recusa o arquivo).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.models.enums import CashflowImportProfile
from app.services.cashflow_imports.parsers import ParsedStatement, StatementCheck, StatementRow
from app.services.exceptions import ImportParsingError

MAX_PAGES = 40

_MONTHS = {
    "JAN": 1,
    "FEV": 2,
    "MAR": 3,
    "ABR": 4,
    "MAI": 5,
    "JUN": 6,
    "JUL": 7,
    "AGO": 8,
    "SET": 9,
    "OUT": 10,
    "NOV": 11,
    "DEZ": 12,
}
_DAY = re.compile(r"^(\d{2}) ([A-Z]{3})$")
_FULL_DATE = re.compile(r"(\d{2}) ([A-Z]{3}) (\d{4})")
_MONEY = re.compile(r"^([−-])?\s*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})$")
_CARD_SUFFIX = re.compile(r"^•+\s*\d{4}$")
_PERIOD = re.compile(r"DE (\d{2}) ([A-Z]{3}) A (\d{2}) ([A-Z]{3})")

PAYMENT_PREFIX = "Pagamento em "
PAYMENT_DESCRIPTION = "Pagamento recebido"
CARRIED_BALANCE = "Saldo restante da fatura anterior"
REFUND_PREFIX = "Estorno de "
# Folga para uma linha datada logo depois da emissão (pagamento feito
# entre a emissão e o vencimento). Datas além disso são do ano anterior.
_SLACK = timedelta(days=10)


def _money(text: str) -> Decimal | None:
    match = _MONEY.match(text.strip())
    if not match:
        return None
    value = Decimal(match.group(2).replace(".", "").replace(",", "."))
    return -value if match.group(1) else value


def _brl(value: Decimal) -> str:
    text = f"{abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {text}" if value < 0 else f"R$ {text}"


def _full_date(text: str) -> date | None:
    match = _FULL_DATE.search(text)
    if not match or match.group(2) not in _MONTHS:
        return None
    return date(int(match.group(3)), _MONTHS[match.group(2)], int(match.group(1)))


def resolve_year(day: int, month: int, reference: date) -> date:
    """Data sem ano de uma fatura emitida em `reference`."""
    candidate = date(reference.year, month, day)
    if candidate > reference + _SLACK:
        candidate = date(reference.year - 1, month, day)
    return candidate


@dataclass(frozen=True)
class _Summary:
    previous: Decimal | None = None
    paid: Decimal | None = None
    purchases: Decimal | None = None
    others: Decimal = Decimal(0)
    due: Decimal | None = None


_SUMMARY_LABELS = {
    "Fatura anterior": "previous",
    "Pagamento recebido": "paid",
    "Outros lançamentos": "others",
    "Total a pagar": "due",
}


def _read_summary(lines: list[list[str]]) -> _Summary:
    """O quadro "RESUMO DA FATURA ATUAL". Só ele: "Total a pagar"
    também aparece nas simulações de parcelamento da primeira página.
    """
    values: dict[str, Decimal] = {}
    inside = False
    for cells in lines:
        head = cells[0]
        if head.startswith("RESUMO DA FATURA"):
            inside = True
            continue
        if not inside:
            continue
        if head.startswith("TRANSAÇÕES"):
            break
        if len(cells) != 2:
            continue
        value = _money(cells[1])
        if value is None:
            continue
        if head.startswith("Total de compras de todos os cartões"):
            values.setdefault("purchases", value)
        elif head in _SUMMARY_LABELS:
            values.setdefault(_SUMMARY_LABELS[head], value)
        if "due" in values:
            break
    return _Summary(**values)


def _dedupe_text(description: str) -> str | None:
    if description.startswith(REFUND_PREFIX):
        return description[len(REFUND_PREFIX) :].strip().strip('"').strip()
    return None


def parse_fatura_lines(lines: list[list[str]]) -> ParsedStatement:
    """Linhas da fatura (células da esquerda para a direita) ->
    lançamentos no sinal do livro, já conferidos com o resumo.
    """
    lines = [[c.strip() for c in cells if c.strip()] for cells in lines]
    lines = [cells for cells in lines if cells]

    due_date: date | None = None
    issued: date | None = None
    for cells in lines:
        if cells[0].startswith("FATURA "):
            due_date = _full_date(cells[0])
            issued = next((_full_date(c) for c in cells[1:] if c.startswith("EMISSÃO")), None)
            if due_date:
                break
    if due_date is None:
        raise ImportParsingError("este PDF não parece uma fatura do cartão Nubank")
    reference = issued or due_date

    summary = _read_summary(lines)
    if summary.purchases is None or summary.paid is None:
        raise ImportParsingError(
            "não encontrei o resumo da fatura (Total de compras e Pagamento recebido): "
            "sem ele não dá para conferir, e nada foi importado"
        )

    start = next((i for i, cells in enumerate(lines) if cells[0].startswith("TRANSAÇÕES")), None)
    if start is None:
        raise ImportParsingError("não encontrei a seção TRANSAÇÕES da fatura")

    period_start: date | None = None
    period_end: date | None = None
    period = _PERIOD.search(" ".join(lines[start]))
    if period and period.group(2) in _MONTHS and period.group(4) in _MONTHS:
        period_end = resolve_year(int(period.group(3)), _MONTHS[period.group(4)], reference)
        period_start = resolve_year(int(period.group(1)), _MONTHS[period.group(2)], period_end)

    rows: list[StatementRow] = []
    purchases_total = Decimal(0)
    payments_total = Decimal(0)
    for cells in lines[start + 1 :]:
        day = _DAY.match(cells[0])
        if not day or len(cells) < 2:
            continue  # subtotal, título de seção, nota, rodapé
        if day.group(2) not in _MONTHS:
            raise ImportParsingError(f"mês desconhecido na linha da fatura: {' '.join(cells)}")
        amount = _money(cells[-1])
        if amount is None:
            raise ImportParsingError(
                f"linha da fatura sem valor legível: {' '.join(cells)} — nada foi importado"
            )
        description = " ".join(c for c in cells[1:-1] if not _CARD_SUFFIX.match(c))
        description = " ".join(description.split())
        if not description:
            raise ImportParsingError(f"linha da fatura sem descrição: {' '.join(cells)}")
        entry_date = resolve_year(int(day.group(1)), _MONTHS[day.group(2)], reference)

        if description.startswith(CARRIED_BALANCE):
            continue
        if description.startswith(PAYMENT_PREFIX):
            payments_total += amount
            kind_description, dedupe = PAYMENT_DESCRIPTION, None
        else:
            purchases_total += amount
            kind_description, dedupe = description, _dedupe_text(description)
        if amount == 0:
            continue
        rows.append(
            StatementRow(
                row_index=len(rows),
                entry_date=entry_date,
                # Na fatura a compra é positiva; no livro, saída é negativa.
                amount=-amount,
                description=kind_description,
                dedupe_text=dedupe,
            )
        )

    expected_purchases = summary.purchases + summary.others
    checks = (
        StatementCheck(
            label="Compras, estornos e créditos",
            expected=expected_purchases,
            found=purchases_total,
        ),
        StatementCheck(label="Pagamentos recebidos", expected=summary.paid, found=payments_total),
    )
    failed = [c for c in checks if not c.ok]
    if failed:
        detail = "; ".join(
            f"{c.label}: lidos {_brl(c.found)}, a fatura diz {_brl(c.expected)}" for c in failed
        )
        raise ImportParsingError(
            f"a fatura de {due_date:%m/%Y} não confere com o próprio resumo ({detail}). "
            "Nada foi importado."
        )

    return ParsedStatement(
        profile=CashflowImportProfile.NUBANK_CARD_PDF,
        rows=rows,
        currency_code="BRL",
        period_start=period_start,
        period_end=period_end,
        checks=checks,
        statement_due_date=due_date,
        statement_previous=summary.previous,
        statement_total=summary.due,
    )


def pdf_lines(content: bytes) -> list[list[str]]:
    """Texto do PDF agrupado em linhas pela altura na página."""
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LAParams, LTTextLine
        from pdfminer.pdfdocument import PDFPasswordIncorrect
        from pdfminer.psexceptions import PSException
    except ImportError as exc:  # pragma: no cover - depende da instalação
        raise ImportParsingError(
            "para ler fatura em PDF, instale a dependência nova do backend: "
            "na pasta backend, pip install -e ."
        ) from exc

    out: list[list[str]] = []
    try:
        pages = extract_pages(
            io.BytesIO(content),
            laparams=LAParams(line_margin=0.2, char_margin=1.0),
            maxpages=MAX_PAGES,
        )
        for page in pages:
            items: list[tuple[float, float, str]] = []

            def walk(obj, items=items) -> None:
                if isinstance(obj, LTTextLine):
                    text = obj.get_text().strip()
                    if text:
                        items.append((round(obj.y0), obj.x0, text))
                elif hasattr(obj, "__iter__"):
                    for child in obj:
                        walk(child)

            walk(page)
            items.sort(key=lambda t: (-t[0], t[1]))
            grouped: list[tuple[float, list[tuple[float, str]]]] = []
            for y, x, text in items:
                if grouped and abs(grouped[-1][0] - y) <= 3:
                    grouped[-1][1].append((x, text))
                else:
                    grouped.append((y, [(x, text)]))
            out += [[text for _x, text in sorted(cells)] for _y, cells in grouped]
    except PDFPasswordIncorrect as exc:
        raise ImportParsingError("o PDF está protegido por senha") from exc
    except (PSException, ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
        # PSException é a base de todos os erros do pdfminer.
        raise ImportParsingError("não consegui ler este PDF") from exc
    return out


def parse_card_pdf(content: bytes) -> ParsedStatement:
    return parse_fatura_lines(pdf_lines(content))
