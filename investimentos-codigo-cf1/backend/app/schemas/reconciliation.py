"""Schemas de reconciliação — Fase 10b (unidade 6) e Fase 11 (unidade backend 2)."""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.domain.reconciliation.types import FieldComparison, MatchClassification
from app.models.enums import ReconciliationStatus


class ReconciliationDecision(str, enum.Enum):
    """Decisão do usuário sobre um `ReconciliationLog PENDING`.

    Valores de API, propositalmente diferentes dos nomes de status do
    model: a decisão é o VERBO ("ignore", "mantenha as duas", "faça o
    merge"); o status é o ESTADO resultante (`IGNORED`, `KEPT_BOTH`,
    `MERGED`). Ver `ReconciliationStatus` em `app.models.enums`.
    """

    IGNORE = "IGNORE"
    KEEP_BOTH = "KEEP_BOTH"
    MERGE = "MERGE"


class ReconciliationResolveRequest(BaseModel):
    """Corpo de POST /reconciliation/{id}/resolve.

    `surviving_transaction_id` é OBRIGATÓRIO em MERGE e PROIBIDO nas
    demais decisões — não é um "opcional" solto, é condicionado à
    decisão escolhida.
    """

    decision: ReconciliationDecision
    surviving_transaction_id: UUID | None = None

    @model_validator(mode="after")
    def _survivor_conforme_decisao(self) -> ReconciliationResolveRequest:
        if self.decision == ReconciliationDecision.MERGE:
            if self.surviving_transaction_id is None:
                raise ValueError("MERGE exige surviving_transaction_id")
        elif self.surviving_transaction_id is not None:
            raise ValueError(
                f"surviving_transaction_id não é aceito para a decisão {self.decision}"
            )
        return self


class ReconciliationLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    transaction_a_id: UUID
    transaction_b_id: UUID
    match_reason: str
    status: ReconciliationStatus
    surviving_transaction_id: UUID | None
    reversed_transaction_id: UUID | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


def _to_display_str(value: Any) -> str | None:
    """Converte um valor bruto do domínio (Decimal, date, str, None)
    para o formato de exibição já usado em todo o resto da API:
    números e datas chegam como string pronta; o frontend NUNCA recebe
    Decimal/date cru para não precisar (e não ser tentado a) fazer
    aritmética ou interpretação sobre eles.
    """
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        # Notação posicional SEMPRE: `str(Decimal("0E-8"))` devolveria
        # "0E-8" (notação científica) para uma diferença zero entre
        # dois NUMERIC(20, 8) — ilegível na UI. Mesma convenção do
        # `_fmt` usado pelo matcher para o `match_reason`.
        return format(value, "f")
    return str(value)


class FieldComparisonRead(BaseModel):
    """Comparação de UM campo entre as Transactions A e B de um par —
    Fase 11, unidade backend 2. Espelha `FieldComparison`
    (`app.domain.reconciliation.types`), só convertendo os valores para
    string de exibição. Não recalcula nem reinterpreta nada: é
    serialização pura do que o matcher já produziu.
    """

    field: str
    equal: bool
    value_a: str | None
    value_b: str | None
    absolute_difference: str | None = None
    relative_difference: str | None = None

    @classmethod
    def from_domain(cls, comparison: FieldComparison) -> FieldComparisonRead:
        return cls(
            field=comparison.field,
            equal=comparison.equal,
            value_a=_to_display_str(comparison.value_a),
            value_b=_to_display_str(comparison.value_b),
            absolute_difference=_to_display_str(comparison.absolute_difference),
            relative_difference=_to_display_str(comparison.relative_difference),
        )


class ReconciliationComparisonRead(BaseModel):
    """Resposta de GET /reconciliation/{id}/comparison — Fase 11,
    unidade backend 2. `match_reason` é informação complementar (o
    texto já guardado no log); `fields` é a fonte estrutural para a
    UI montar a comparação campo a campo.
    """

    reconciliation_id: UUID
    classification: MatchClassification
    match_reason: str
    fields: list[FieldComparisonRead]


class ReconciliationScanRequest(BaseModel):
    """Corpo de POST /reconciliation/scan — Fase 11, unidade backend 3.

    Escopo mutuamente exclusivo (conta, portfolio, ou nenhum dos dois
    para todas as contas do usuário) — a validação em si continua
    sendo responsabilidade do `scan_for_reconciliation` já existente
    (`InvalidScanScopeError`), para não duplicar a regra aqui.
    """

    account_id: UUID | None = None
    portfolio_id: UUID | None = None


class ReconciliationScanResult(BaseModel):
    """Resposta de POST /reconciliation/scan: os `ReconciliationLog`
    PENDING criados POR ESTA execução (pares já registrados antes, em
    qualquer status, não aparecem aqui). `created_count` é
    `len(created)`, exposto para a UI não precisar contar.
    """

    created_count: int
    created: list[ReconciliationLogRead]
