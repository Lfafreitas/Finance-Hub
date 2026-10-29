"""Concentração da carteira (Análises-1): quanto cada ativo, classe e
conta pesa, e sinais objetivos de concentração alta.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

SINGLE_ASSET_LIMIT = Decimal("0.40")
TOP3_LIMIT = Decimal("0.75")
_PLACES = Decimal("0.0001")


@dataclass(frozen=True)
class WeightItem:
    key: str
    label: str
    value: Decimal
    weight: Decimal


@dataclass(frozen=True)
class ConcentrationResult:
    total: Decimal
    by_asset: tuple[WeightItem, ...]
    by_class: tuple[WeightItem, ...]
    by_account: tuple[WeightItem, ...]
    by_group: tuple[WeightItem, ...]
    top3_weight: Decimal
    flags: tuple[str, ...]


@dataclass(frozen=True)
class Slice:
    asset_key: str
    asset_label: str
    class_key: str
    class_label: str
    account_key: str
    account_label: str
    value: Decimal
    # Renda variável / renda fixa / fundos (Visual-1).
    group_key: str = ""
    group_label: str = ""


def _group(slices: Iterable[Slice], total: Decimal, key_of, label_of) -> tuple[WeightItem, ...]:
    values: dict[str, Decimal] = {}
    labels: dict[str, str] = {}
    for item in slices:
        key = key_of(item)
        values[key] = values.get(key, Decimal(0)) + item.value
        labels[key] = label_of(item)
    items = [
        WeightItem(
            key=key,
            label=labels[key],
            value=value,
            weight=(value / total).quantize(_PLACES, rounding=ROUND_HALF_UP),
        )
        for key, value in values.items()
    ]
    return tuple(sorted(items, key=lambda w: (-w.value, w.label)))


def concentration(slices: list[Slice]) -> ConcentrationResult | None:
    slices = [s for s in slices if s.value > 0]
    total = sum((s.value for s in slices), start=Decimal(0))
    if total <= 0:
        return None
    by_asset = _group(slices, total, lambda s: s.asset_key, lambda s: s.asset_label)
    by_class = _group(slices, total, lambda s: s.class_key, lambda s: s.class_label)
    by_account = _group(slices, total, lambda s: s.account_key, lambda s: s.account_label)
    by_group = _group(slices, total, lambda s: s.group_key, lambda s: s.group_label)
    top3_value = sum((w.value for w in by_asset[:3]), start=Decimal(0))
    top3 = (top3_value / total).quantize(_PLACES, rounding=ROUND_HALF_UP)

    flags: list[str] = []
    largest = by_asset[0]
    if len(by_asset) > 1 and largest.value / total > SINGLE_ASSET_LIMIT:
        flags.append(
            f"{largest.label} sozinho é mais de {int(SINGLE_ASSET_LIMIT * 100)}% da carteira"
        )
    if len(by_asset) > 3 and top3_value / total > TOP3_LIMIT:
        flags.append(f"os 3 maiores ativos somam mais de {int(TOP3_LIMIT * 100)}% da carteira")
    if len(by_class) == 1 and len(by_asset) > 1:
        flags.append(f"toda a carteira está numa classe só ({by_class[0].label})")
    return ConcentrationResult(
        total=total,
        by_asset=by_asset,
        by_class=by_class,
        by_account=by_account,
        by_group=by_group,
        top3_weight=top3,
        flags=tuple(flags),
    )
