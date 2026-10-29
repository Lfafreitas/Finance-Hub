"""Agenda da carteira: vencimentos de renda fixa das posições atuais.

As posições (quantidade, custo, valor) vêm do dashboard — nenhuma regra
de posição é refeita aqui. Do cadastro do ativo vêm vencimento e taxa;
das transações, a data da primeira compra (para a estimativa).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.analytics.agenda import FixedIncomeHolding, build_agenda
from app.models.asset import Asset
from app.models.enums import TransactionStatus, TransactionType
from app.models.transaction import Transaction
from app.repositories.accounts import list_accounts
from app.schemas.performance import AgendaRead, MaturityRead
from app.services.dashboard_service import get_dashboard_summary

_ZERO = Decimal(0)


def _first_purchases(db: Session, account_ids: list[UUID], asset_ids: set[UUID]) -> dict:
    if not account_ids or not asset_ids:
        return {}
    rows = db.execute(
        select(Transaction.asset_id, func.min(Transaction.transaction_date))
        .where(Transaction.account_id.in_(account_ids))
        .where(Transaction.asset_id.in_(asset_ids))
        .where(Transaction.transaction_type == TransactionType.BUY)
        .where(Transaction.status == TransactionStatus.ACTIVE)
        .group_by(Transaction.asset_id)
    ).all()
    return dict(rows)


def get_agenda(db: Session, user_id: UUID, *, today: date | None = None) -> AgendaRead:
    today = today or date.today()
    summary = get_dashboard_summary(db, user_id, None, today)

    merged: dict[tuple[str, UUID], list] = {}
    for p in summary.positions:
        if p.currency_code is None or p.quantity <= 0:
            continue
        merged.setdefault((p.currency_code, p.asset_id), []).append(p)

    asset_ids = {asset_id for _currency, asset_id in merged}
    assets = {a.id: a for a in db.execute(select(Asset).where(Asset.id.in_(asset_ids))).scalars()}
    firsts = _first_purchases(db, [a.id for a in list_accounts(db, user_id)], asset_ids)

    holdings = []
    for (currency, asset_id), positions in merged.items():
        asset = assets[asset_id]
        values = [p.market_value for p in positions]
        holdings.append(
            FixedIncomeHolding(
                ticker=asset.ticker,
                name=asset.name,
                asset_class=asset.asset_class_code,
                currency_code=currency,
                quantity=sum((p.quantity for p in positions), start=_ZERO),
                cost=sum((p.total_cost_basis or 0 for p in positions), start=_ZERO),
                value=sum(values, start=_ZERO) if all(v is not None for v in values) else None,
                maturity_date=asset.maturity_date,
                annual_rate=asset.annual_rate,
                first_purchase=firsts.get(asset_id),
            )
        )

    agenda = build_agenda(holdings, today)
    return AgendaRead(
        as_of=today,
        maturities=[MaturityRead(**m.__dict__) for m in agenda.maturities],
        missing_maturity=agenda.missing_maturity,
    )
