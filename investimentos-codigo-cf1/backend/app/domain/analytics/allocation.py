"""Alocação-alvo: peso atual de cada classe × o alvo do usuário.

Função pura. Peso atual pelo valor de mercado (ativo sem cotação entra
pelo custo, como no resto do app), dentro de UMA moeda. A distância em
valor é só a tradução do desvio em dinheiro — "quanto o peso está longe
do alvo" —, não uma ordem de compra ou venda.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_ZERO = Decimal(0)
_Q4 = Decimal("0.0001")
_CENT = Decimal("0.01")
TOLERANCE = Decimal("0.0001")  # soma dos alvos tem de dar 100% com esta folga


@dataclass(frozen=True)
class ClassValue:
    asset_class: str
    label: str
    value: Decimal


@dataclass(frozen=True)
class AllocationRow:
    asset_class: str
    label: str
    value: Decimal
    current_weight: Decimal
    target_weight: Decimal | None
    gap: Decimal | None  # atual − alvo (positivo = acima do alvo)
    value_gap: Decimal | None  # alvo × total − valor atual (positivo = falta para o alvo)


def targets_are_valid(targets: dict[str, Decimal]) -> bool:
    """Vazio (sem alvo) vale; senão, cada peso entre 0 e 1 e a soma 100%."""
    if not targets:
        return True
    if any(w < 0 or w > 1 for w in targets.values()):
        return False
    return abs(sum(targets.values(), start=_ZERO) - 1) <= TOLERANCE


def allocation(
    current: list[ClassValue], targets: dict[str, Decimal], labels: dict[str, str]
) -> list[AllocationRow]:
    total = sum((c.value for c in current), start=_ZERO)
    values = {c.asset_class: c for c in current}
    classes = set(values) | set(targets)
    rows = []
    for code in classes:
        item = values.get(code)
        value = item.value if item else _ZERO
        weight = (value / total).quantize(_Q4, rounding=ROUND_HALF_UP) if total > 0 else _ZERO
        target = targets.get(code) if targets else None
        if targets and target is None:
            target = _ZERO  # há alvos e esta classe não está neles: alvo zero
        rows.append(
            AllocationRow(
                asset_class=code,
                label=item.label if item else labels.get(code, code),
                value=value,
                current_weight=weight,
                target_weight=target,
                gap=(weight - target) if target is not None else None,
                value_gap=(
                    (target * total - value).quantize(_CENT, rounding=ROUND_HALF_UP)
                    if target is not None
                    else None
                ),
            )
        )
    rows.sort(key=lambda r: (-(r.target_weight or _ZERO), -r.value, r.asset_class))
    return rows
