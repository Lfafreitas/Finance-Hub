"""Tipos do matcher de reconciliação (Fase 10b, unidade 4).

Tudo aqui é dado puro e imutável — sem ORM, sem sessão, sem I/O.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.models.enums import TransactionSource, TransactionType


class MatchClassification(str, enum.Enum):
    """Resultado da classificação de um par candidato.

    EQUIVALENT NÃO é autorização de merge nem de alteração de dados:
    apenas diz que nenhum dos campos comparados difere. DIVERGENT diz
    que existe pelo menos uma diferença efetiva. Quem decide o que
    fazer é sempre o usuário.
    """

    EQUIVALENT = "EQUIVALENT"
    DIVERGENT = "DIVERGENT"


@dataclass(frozen=True)
class TransactionSnapshot:
    """Espelho puro (sem ORM) dos campos de uma Transaction que o
    matcher precisa. Pré-condição de quem constrói: é uma Transaction
    ACTIVE — o matcher não conhece `status`, do mesmo modo que
    `TransactionFact` (Financial Engine) não conhece.
    """

    id: UUID
    account_id: UUID
    asset_id: UUID | None
    transaction_type: TransactionType
    quantity: Decimal | None
    unit_price: Decimal | None
    fees: Decimal
    gross_amount: Decimal
    currency_code: str
    transaction_date: date
    source: TransactionSource
    fx_rate_to_brl: Decimal | None = None

    @classmethod
    def from_transaction(cls, row: Any) -> TransactionSnapshot:
        """Mapeamento campo a campo a partir de qualquer objeto com os
        mesmos atributos (ex.: `Transaction` ORM). Só lê atributos —
        nunca escreve na Transaction.
        """
        return cls(
            id=row.id,
            account_id=row.account_id,
            asset_id=row.asset_id,
            transaction_type=row.transaction_type,
            quantity=row.quantity,
            unit_price=row.unit_price,
            fees=row.fees,
            gross_amount=row.gross_amount,
            currency_code=row.currency_code,
            transaction_date=row.transaction_date,
            source=row.source,
            fx_rate_to_brl=row.fx_rate_to_brl,
        )


@dataclass(frozen=True)
class FieldComparison:
    """Comparação de UM campo entre A e B.

    `value_a`/`value_b` são os valores efetivamente comparados (para
    `fx_rate_to_brl`, já com a taxa implícita 1 aplicada a BRL nulo).
    `absolute_difference` e `relative_difference` só existem quando
    fazem sentido (campos numéricos com os dois lados presentes; para
    `transaction_date`, a diferença absoluta é em DIAS e não há
    relativa). A diferença relativa é sempre em relação ao MAIOR valor
    absoluto dos dois lados — a mesma referência da tolerância de
    candidatura, para os números serem coerentes entre si.
    """

    field: str
    equal: bool
    value_a: Any
    value_b: Any
    absolute_difference: Decimal | None = None
    relative_difference: Decimal | None = None


@dataclass(frozen=True)
class ComparisonResult:
    """Resultado da comparação campo a campo, na ordem fixa de
    `COMPARED_FIELDS`. Responde: quais campos são iguais, quais
    diferem, com que valores e com que diferença.
    """

    fields: tuple[FieldComparison, ...]

    @property
    def equal_fields(self) -> tuple[FieldComparison, ...]:
        return tuple(f for f in self.fields if f.equal)

    @property
    def differing_fields(self) -> tuple[FieldComparison, ...]:
        return tuple(f for f in self.fields if not f.equal)

    @property
    def is_identical(self) -> bool:
        return not self.differing_fields


@dataclass(frozen=True)
class MatchResult:
    """Par candidato já comparado e classificado. `transaction_a` e
    `transaction_b` seguem a ordem canônica (menor id primeiro), então
    o resultado é o mesmo qualquer que seja a ordem em que o par foi
    passado ao matcher.
    """

    transaction_a: TransactionSnapshot
    transaction_b: TransactionSnapshot
    comparison: ComparisonResult
    classification: MatchClassification
    match_reason: str
