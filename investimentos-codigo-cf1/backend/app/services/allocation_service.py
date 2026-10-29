"""Alocação-alvo: grava os alvos do usuário e compara com o peso atual.

O peso atual por classe vem dos indicadores (KPIs-1): valor de mercado,
sem cotação pelo custo, por moeda.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.analytics.allocation import ClassValue, allocation, targets_are_valid
from app.models.allocation_target import AllocationTarget
from app.models.asset_class import AssetClass
from app.models.currency import Currency
from app.schemas.performance import (
    AllocationRead,
    AllocationRowRead,
    AllocationTargetsWrite,
    CurrencyAllocation,
)
from app.services.exceptions import InvalidAllocationTargetError
from app.services.performance_service import get_kpis

_ZERO = Decimal(0)


def _targets(db: Session, user_id: UUID) -> dict[str, dict[str, Decimal]]:
    out: dict[str, dict[str, Decimal]] = {}
    for t in db.execute(
        select(AllocationTarget).where(AllocationTarget.user_id == user_id)
    ).scalars():
        out.setdefault(t.currency_code, {})[t.asset_class_code] = t.target_weight
    return out


def get_allocation(db: Session, user_id: UUID, *, today: date | None = None) -> AllocationRead:
    kpis = get_kpis(db, user_id, today=today)
    targets = _targets(db, user_id)
    labels = dict(db.execute(select(AssetClass.code, AssetClass.label)).all())
    blocks = {b.currency_code: b for b in kpis.totals_by_currency}
    currencies = list(blocks) + sorted(c for c in targets if c not in blocks)
    out = []
    for currency in currencies:
        block = blocks.get(currency)
        current = [
            ClassValue(g.asset_class, g.label, g.value) for g in (block.groups if block else [])
        ]
        rows = allocation(current, targets.get(currency, {}), labels)
        out.append(
            CurrencyAllocation(
                currency_code=currency,
                total=sum((c.value for c in current), start=_ZERO),
                has_targets=bool(targets.get(currency)),
                rows=[AllocationRowRead(**r.__dict__) for r in rows],
            )
        )
    return AllocationRead(currencies=out)


def set_targets(
    db: Session, user_id: UUID, currency_code: str, payload: AllocationTargetsWrite
) -> None:
    currency_code = currency_code.upper()
    if db.get(Currency, currency_code) is None:
        raise InvalidAllocationTargetError(f"moeda {currency_code} não cadastrada")
    weights: dict[str, Decimal] = {}
    for item in payload.targets:
        code = item.asset_class_code.strip().upper()
        if code in weights:
            raise InvalidAllocationTargetError(f"classe {code} repetida")
        if db.get(AssetClass, code) is None:
            raise InvalidAllocationTargetError(f"classe de ativo {code} não cadastrada")
        weights[code] = item.target_weight
    if not targets_are_valid(weights):
        raise InvalidAllocationTargetError("os alvos precisam somar 100%")
    db.execute(
        delete(AllocationTarget).where(
            AllocationTarget.user_id == user_id, AllocationTarget.currency_code == currency_code
        )
    )
    for code, weight in weights.items():
        if weight > 0:
            db.add(
                AllocationTarget(
                    user_id=user_id,
                    currency_code=currency_code,
                    asset_class_code=code,
                    target_weight=weight,
                )
            )
    db.flush()
