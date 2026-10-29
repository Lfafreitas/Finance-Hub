"""Leitura determinística da descrição de um lançamento de caixa.

Puro: recebe o texto como o banco escreveu e devolve os pedaços que as
regras de classificação usam. Nada aqui consulta banco, rede ou modelo
estatístico — os formatos foram verificados nos arquivos reais (CF-0,
seções 13 e 14) e cada passo é uma transformação de texto explicável.

O campo que as regras comparam é `match_text`: minúsculo, sem acento,
sem prefixo de intermediador de pagamento, sem código no fim e sem os
sufixos de parcela e de canal. Assim "Dm*Spotify P46c9",
"Dm *Spotify" e "Ebn *Spotify" viram todos "spotify".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Intermediadores de pagamento: o que vem antes do "*" é só o meio, o
# estabelecimento é o que vem depois. Marketplaces e aplicativos
# (amazonmktplc, 99food, uber, shopee...) NÃO entram aqui: neles o
# prefixo é a parte útil para classificar.
_PAYMENT_INTERMEDIARIES = frozenset(
    {"mp", "dm", "pg", "pag", "ebn", "zp", "evo", "ec", "mlp", "nuv", "app", "pagseguro"}
)

_INSTALLMENT_SUFFIX = re.compile(r"\s+-\s+(?:parcela\s+)?(\d{1,2})/(\d{1,2})$", re.IGNORECASE)
_CHANNEL_SUFFIX = re.compile(r"\s+-\s+(nupay)$", re.IGNORECASE)
_PARENTHETICAL_SUFFIX = re.compile(r"\s*\([^)]*\)\s*$")
_DOCUMENT_IN_TEXT = re.compile(
    r"(?:^|\s-\s)([\d•*]{3}\.[\d•*]{3}\.[\d•*]{3}-[\d•*]{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})(?:\s-\s|$)"
)
_INSTITUTION = re.compile(r"^(.*?)\s+Ag[êe]ncia:", re.IGNORECASE)
_SEGMENT_SEPARATOR = " - "

# Primeiro segmento de uma linha de extrato de CONTA (normalizado).
_ACCOUNT_MOVEMENTS = (
    "transferencia ",
    "compra no debito",
    "pagamento de fatura",
    "pagamento de boleto",
    "pix no credito",
    "resgate ",
    "aplicacao ",
    "deposito ",
    "estorno ",
    "reembolso ",
)


def normalize_text(text: str) -> str:
    """Minúsculas, sem acento, espaços colapsados. É a forma em que
    padrões de regra e textos de lançamento são comparados.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(without_accents.casefold().split())


@dataclass(frozen=True)
class ParsedDescription:
    """`movement` só existe em linha de extrato de conta ("Transferência
    enviada pelo Pix", "Compra no débito"...). `counterparty` é a pessoa
    ou o estabelecimento, como veio. `installment` é (parcela, total).
    """

    movement: str | None
    counterparty: str
    document: str | None
    institution: str | None
    installment: tuple[int, int] | None
    channel: str | None
    match_text: str


def _is_code_token(token: str) -> bool:
    """Código de transação colado no nome: só dígitos (4+) ou mistura
    de letras e dígitos com pelo menos dois dígitos e 5+ caracteres
    ("p46c9", "hmeyt9hqd8", "123456789").
    """
    if not token.isalnum():
        return False
    digits = sum(ch.isdigit() for ch in token)
    if token.isdigit():
        return len(token) >= 4
    return len(token) >= 5 and digits >= 2


def _merchant_key(name: str) -> str:
    text = normalize_text(name)
    if "*" in text:
        prefix, _, rest = text.partition("*")
        prefix, rest = prefix.strip(), rest.strip()
        if prefix in _PAYMENT_INTERMEDIARIES and rest:
            text = rest
        else:
            text = f"{prefix} {rest}".strip()
    tokens = text.split()
    # Nunca remove o primeiro token: "99food" tem dígitos e é o nome.
    while len(tokens) > 1 and _is_code_token(tokens[-1]):
        tokens.pop()
    return " ".join(tokens)


def parse_description(description: str) -> ParsedDescription:
    text = " ".join(description.split())
    installment: tuple[int, int] | None = None

    match = _INSTALLMENT_SUFFIX.search(text)
    if match:
        number, total = int(match.group(1)), int(match.group(2))
        if 1 <= number <= total:
            installment = (number, total)
            text = text[: match.start()]

    channel: str | None = None
    match = _CHANNEL_SUFFIX.search(text)
    if match:
        channel = match.group(1)
        text = text[: match.start()]

    segments = [segment.strip() for segment in text.split(_SEGMENT_SEPARATOR)]
    first = normalize_text(segments[0])
    is_account_line = any(
        first == movement.strip() or first.startswith(movement) for movement in _ACCOUNT_MOVEMENTS
    )

    if not is_account_line:
        counterparty = text.strip()
        return ParsedDescription(
            movement=None,
            counterparty=counterparty,
            document=None,
            institution=None,
            installment=installment,
            channel=channel,
            match_text=_merchant_key(counterparty),
        )

    movement = segments[0]
    rest = text[len(segments[0]) :].removeprefix(_SEGMENT_SEPARATOR.rstrip()).strip()
    document: str | None = None
    institution: str | None = None
    # O documento separa o nome (antes) da instituição (depois). A
    # instituição pode conter " - " ("NU PAGAMENTOS - IP"), por isso a
    # leitura é pela posição do documento, não por contagem de segmentos.
    found = _DOCUMENT_IN_TEXT.search(rest)
    if found:
        document = found.group(1)
        name_part = rest[: found.start()]
        bank = _INSTITUTION.match(rest[found.end() :].strip())
        if bank:
            institution = bank.group(1).strip()
    else:
        name_part = rest
    names = [name_part.strip().removeprefix("-").strip()]
    # "NOME (Transferência enviada)": o parêntese repete o movimento.
    counterparty = _PARENTHETICAL_SUFFIX.sub("", _SEGMENT_SEPARATOR.join(names)).strip()
    key = (
        f"{normalize_text(movement)} {_merchant_key(counterparty)}".strip()
        if counterparty
        else first
    )
    return ParsedDescription(
        movement=movement,
        counterparty=counterparty,
        document=document,
        institution=institution,
        installment=installment,
        channel=channel,
        match_text=key,
    )
