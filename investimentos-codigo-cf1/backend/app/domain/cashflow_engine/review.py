"""Revisão do que falta classificar (Painel-1).

Junta os lançamentos não classificados pelo mesmo texto de regra
(`match_text` — o mesmo que as regras comparam) e sugere a classificação
que você já deu a esse mesmo texto antes. A sugestão é só o seu próprio
histórico: nada é inventado e nada sai do computador.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.models.enums import CashflowNature

_ZERO = Decimal(0)


@dataclass(frozen=True)
class PendingEntry:
    id: UUID
    account_id: UUID
    match_text: str
    description: str
    currency_code: str
    amount: Decimal
    entry_date: date


@dataclass(frozen=True)
class KnownClassification:
    match_text: str
    nature: CashflowNature
    category_id: UUID | None
    entry_date: date


@dataclass(frozen=True)
class Suggestion:
    nature: CashflowNature
    category_id: UUID | None
    evidence: int
    share: Decimal


@dataclass
class PendingGroup:
    match_text: str
    currency_code: str
    entries: list[PendingEntry] = field(default_factory=list)
    suggestion: Suggestion | None = None

    @property
    def count(self) -> int:
        return len(self.entries)

    @property
    def total(self) -> Decimal:
        return sum((e.amount for e in self.entries), start=_ZERO)

    @property
    def inflows(self) -> int:
        return sum(1 for e in self.entries if e.amount > 0)

    @property
    def outflows(self) -> int:
        return sum(1 for e in self.entries if e.amount < 0)


def suggest(history: list[KnownClassification]) -> Suggestion | None:
    """A classificação mais frequente; empate vai para a mais recente."""
    if not history:
        return None
    counts = Counter((k.nature, k.category_id) for k in history)
    latest: dict[tuple, date] = {}
    for item in history:
        key = (item.nature, item.category_id)
        latest[key] = max(latest.get(key, item.entry_date), item.entry_date)
    (nature, category_id), evidence = max(
        counts.items(), key=lambda pair: (pair[1], latest[pair[0]])
    )
    return Suggestion(
        nature=nature,
        category_id=category_id,
        evidence=evidence,
        share=(Decimal(evidence) / Decimal(len(history))).quantize(Decimal("0.0001")),
    )


def group_pending(
    pending: list[PendingEntry], known: list[KnownClassification]
) -> list[PendingGroup]:
    """Grupos por (texto, moeda), maiores primeiro (quantidade, depois
    valor). Classificação de transferência nunca é sugerida aqui: ela
    precisa da outra ponta.
    """
    history: dict[str, list[KnownClassification]] = {}
    for item in known:
        if item.nature in (CashflowNature.UNCLASSIFIED, CashflowNature.TRANSFER):
            continue
        history.setdefault(item.match_text, []).append(item)

    groups: dict[tuple[str, str], PendingGroup] = {}
    for entry in pending:
        key = (entry.match_text, entry.currency_code)
        group = groups.setdefault(key, PendingGroup(entry.match_text, entry.currency_code))
        group.entries.append(entry)
    for group in groups.values():
        group.entries.sort(key=lambda e: (e.entry_date, e.amount), reverse=True)
        group.suggestion = suggest(history.get(group.match_text, []))
    return sorted(
        groups.values(),
        key=lambda g: (-g.count, -abs(g.total), g.match_text, g.currency_code),
    )
