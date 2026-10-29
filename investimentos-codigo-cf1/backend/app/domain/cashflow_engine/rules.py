"""Motor de regras de classificação: puro e determinístico.

A primeira regra que casa decide sozinha. A ordem é `(priority,
order)`, onde `order` é o desempate estável que o chamador fornece
(a posição por data de criação). Regras não se combinam — assim, para
qualquer lançamento, existe UMA regra que explica a classificação.

Toda regra define a natureza: uma regra que só desse categoria
deixaria o lançamento fora de gasto e de renda sem que isso ficasse
visível.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.domain.cashflow_engine.description import normalize_text
from app.models.enums import CashflowNature, RuleDirection, RuleMatchType


@dataclass(frozen=True)
class RuleSpec:
    rule_id: UUID
    priority: int
    order: int
    match_type: RuleMatchType
    pattern: str
    direction: RuleDirection = RuleDirection.ANY
    account_id: UUID | None = None
    set_nature: CashflowNature = CashflowNature.EXPENSE
    set_category_id: UUID | None = None
    tag_ids: frozenset[UUID] = frozenset()

    def __post_init__(self) -> None:
        if not normalize_text(self.pattern):
            raise ValueError("regra com padrão vazio")
        if self.set_nature is CashflowNature.TRANSFER:
            raise ValueError("regra não classifica como transferência")
        if self.set_nature is CashflowNature.UNCLASSIFIED:
            raise ValueError("regra precisa definir uma natureza")


@dataclass(frozen=True)
class RuleTarget:
    """O que uma regra enxerga de um lançamento."""

    match_text: str
    amount: Decimal
    account_id: UUID


def rule_matches(rule: RuleSpec, target: RuleTarget) -> bool:
    if rule.account_id is not None and rule.account_id != target.account_id:
        return False
    if rule.direction is RuleDirection.IN and target.amount <= 0:
        return False
    if rule.direction is RuleDirection.OUT and target.amount >= 0:
        return False
    pattern = normalize_text(rule.pattern)
    text = normalize_text(target.match_text)
    if rule.match_type is RuleMatchType.EQUALS:
        return text == pattern
    if rule.match_type is RuleMatchType.STARTS_WITH:
        return text.startswith(pattern)
    return pattern in text


def first_matching_rule(rules: Iterable[RuleSpec], target: RuleTarget) -> RuleSpec | None:
    for rule in sorted(rules, key=lambda item: (item.priority, item.order)):
        if rule_matches(rule, target):
            return rule
    return None
