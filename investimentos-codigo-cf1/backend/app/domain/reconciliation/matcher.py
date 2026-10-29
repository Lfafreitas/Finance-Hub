"""Matcher de reconciliação — Fase 10b, unidade 4.

Três etapas estritamente separadas, cada uma numa função pública:

1. `is_candidate`         — CANDIDATE DETECTION: este par PODE ser o
                            mesmo evento? (critério de busca, nada mais)
2. `compare_transactions` — COMPARISON: campo a campo, o que é igual e
                            o que difere, e quanto.
3. `classify`             — CLASSIFICATION: EQUIVALENT ou DIVERGENT.

`match` só compõe as três. Nada aqui grava, altera ou corrige nada:
nem Transaction, nem ReconciliationLog. A tolerância de 10% serve
EXCLUSIVAMENTE para achar candidatos — nunca aceita nem corrige uma
divergência (uma diferença de 5% é DIVERGENT, não "quase igual").

O módulo é puro: sem ORM, sem sessão, sem I/O.
"""

from __future__ import annotations

from decimal import Decimal

from app.domain.reconciliation.types import (
    ComparisonResult,
    FieldComparison,
    MatchClassification,
    MatchResult,
    TransactionSnapshot,
)
from app.models.enums import TransactionType
from app.models.reconciliation_log import canonical_pair

# --- Parâmetros aprovados -------------------------------------------------

DATE_TOLERANCE_DAYS = 1
GROSS_AMOUNT_TOLERANCE = Decimal("0.10")

# Tipos fora da reconciliação (transferências têm seu próprio vínculo
# TRANSFER_OUT <-> TRANSFER_IN; conversão cambial não é um evento
# comparável nesta fase). Qualquer outro membro de TransactionType é
# elegível.
EXCLUDED_TYPES = frozenset(
    {
        TransactionType.TRANSFER_IN,
        TransactionType.TRANSFER_OUT,
        TransactionType.FX_CONVERSION,
    }
)

# Campos comparados, em ordem fixa (a ordem do resultado é determinística).
# Ficam de fora, de propósito: `id`; `account_id`, `transaction_type` e
# `asset_id` (invariantes de candidatura — já são iguais num par
# candidato); `source` (define a regra de candidatura, e diferir é o
# esperado entre fontes); `external_reference` (por construção difere
# entre fontes/ocorrências) e `notes` (texto livre, não financeiro).
COMPARED_FIELDS = (
    "transaction_date",
    "quantity",
    "unit_price",
    "gross_amount",
    "fees",
    "currency_code",
    "fx_rate_to_brl",
)


# --- Diferenças numéricas --------------------------------------------------


def _reference(a: Decimal, b: Decimal) -> Decimal:
    """Referência das diferenças relativas e da tolerância: o MAIOR
    valor absoluto dos dois lados. É simétrica (A/B e B/A dão o mesmo
    resultado) e, com ela, os dois limites "naturais" de 10% são
    candidatos: 100↔110 (10 <= 11) e 100↔90 (10 <= 10).
    """
    return max(abs(a), abs(b))


def _relative_difference(a: Decimal, b: Decimal) -> Decimal | None:
    difference = abs(a - b)
    if difference == 0:
        return Decimal(0)
    reference = _reference(a, b)
    return difference / reference  # reference > 0 aqui: difference > 0 implica algum lado != 0


def _within_gross_tolerance(a: Decimal, b: Decimal) -> bool:
    """`|a - b| <= 10% * max(|a|, |b|)`, em aritmética Decimal exata
    (sem divisão, para o limite exato não sofrer arredondamento).
    Ambos zero: diferença 0 <= 0, dentro. Um zero e outro não: só a
    diferença 0 passaria, então fora.
    """
    return abs(a - b) <= GROSS_AMOUNT_TOLERANCE * _reference(a, b)


# --- 1. Candidate detection ------------------------------------------------


def _comparable_value(tx: TransactionSnapshot, field: str):
    value = getattr(tx, field)
    if field == "fx_rate_to_brl" and value is None and tx.currency_code == "BRL":
        # Semântica aprovada (Fase 5): BRL pode ficar NULL e é
        # implicitamente 1. Só vale para BRL — para outra moeda, NULL
        # significa "taxa não informada" e continua diferente de um valor.
        return Decimal(1)
    return value


def is_candidate(a: TransactionSnapshot, b: TransactionSnapshot) -> bool:
    """O par PODE ser o mesmo evento?

    Critérios (todos obrigatórios): transações distintas; mesma
    `account_id`; mesmo `transaction_type`, fora de `EXCLUDED_TYPES`;
    mesmo `asset_id` (dois `None` contam como mesmo); datas a no máximo
    `DATE_TOLERANCE_DAYS` de distância; `gross_amount` dentro de 10%.

    Regra de fonte: fontes DIFERENTES podem ser candidatas mesmo se
    idênticas (a igualdade é decidida na comparação). Na MESMA fonte,
    um par idêntico NÃO é candidato — é indistinguível de uma operação
    repetida legítima; só divergências entram.
    """
    if a.id == b.id:
        return False
    if a.account_id != b.account_id:
        return False
    if a.transaction_type != b.transaction_type or a.transaction_type in EXCLUDED_TYPES:
        return False
    if a.asset_id != b.asset_id:
        return False
    if abs((a.transaction_date - b.transaction_date).days) > DATE_TOLERANCE_DAYS:
        return False
    if not _within_gross_tolerance(a.gross_amount, b.gross_amount):
        return False
    # Mesma fonte E idêntico => operação repetida legítima, não candidato.
    return not (a.source == b.source and compare_transactions(a, b).is_identical)


# --- 2. Comparison ---------------------------------------------------------


def _compare_field(a: TransactionSnapshot, b: TransactionSnapshot, field: str) -> FieldComparison:
    value_a = _comparable_value(a, field)
    value_b = _comparable_value(b, field)
    equal = value_a == value_b  # Decimal compara por valor: 10.0 == 10.00

    absolute: Decimal | None = None
    relative: Decimal | None = None
    if field == "transaction_date":
        absolute = Decimal(abs((value_a - value_b).days))
    elif isinstance(value_a, Decimal) and isinstance(value_b, Decimal):
        absolute = abs(value_a - value_b)
        relative = _relative_difference(value_a, value_b)

    return FieldComparison(
        field=field,
        equal=equal,
        value_a=value_a,
        value_b=value_b,
        absolute_difference=absolute,
        relative_difference=relative,
    )


def compare_transactions(a: TransactionSnapshot, b: TransactionSnapshot) -> ComparisonResult:
    """Compara objetivamente `COMPARED_FIELDS`, na ordem fixa. Não
    decide nada: só relata igualdades, diferenças, valores de A e B e
    as diferenças absoluta/relativa quando fazem sentido.
    """
    return ComparisonResult(fields=tuple(_compare_field(a, b, f) for f in COMPARED_FIELDS))


# --- 3. Classification -----------------------------------------------------


def classify(comparison: ComparisonResult) -> MatchClassification:
    """EQUIVALENT se nenhum campo comparado difere; DIVERGENT caso
    contrário. Não há meio-termo nem limiar: qualquer diferença
    efetiva é DIVERGENT.
    """
    if comparison.is_identical:
        return MatchClassification.EQUIVALENT
    return MatchClassification.DIVERGENT


# --- Composição ------------------------------------------------------------


def _fmt(value) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def build_match_reason(classification: MatchClassification, comparison: ComparisonResult) -> str:
    """Texto objetivo e determinístico para o futuro `match_reason`:
    lista, campo a campo, os valores de A e B e as diferenças.
    """
    if classification == MatchClassification.EQUIVALENT:
        return "EQUIVALENT: todos os campos comparados são iguais"

    parts = []
    for item in comparison.differing_fields:
        text = f"{item.field}: {_fmt(item.value_a)} != {_fmt(item.value_b)}"
        details = []
        if item.absolute_difference is not None:
            unit = " dias" if item.field == "transaction_date" else ""
            details.append(f"abs={_fmt(item.absolute_difference)}{unit}")
        if item.relative_difference is not None:
            details.append(f"rel={_fmt(item.relative_difference)}")
        if details:
            text += f" ({', '.join(details)})"
        parts.append(text)
    return "DIVERGENT: " + "; ".join(parts)


def match(a: TransactionSnapshot, b: TransactionSnapshot) -> MatchResult | None:
    """Compõe as três etapas. Devolve `None` se o par não é candidato.
    O resultado usa a ordem canônica (menor id como A), então
    `match(x, y)` e `match(y, x)` são iguais.
    """
    if not is_candidate(a, b):
        return None

    first_id, _second_id = canonical_pair(a.id, b.id)
    first, second = (a, b) if a.id == first_id else (b, a)

    comparison = compare_transactions(first, second)
    classification = classify(comparison)
    return MatchResult(
        transaction_a=first,
        transaction_b=second,
        comparison=comparison,
        classification=classification,
        match_reason=build_match_reason(classification, comparison),
    )
