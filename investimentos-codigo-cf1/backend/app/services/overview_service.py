"""Patrimônio por moeda (Visual-1).

Junta os dois livros sem misturar as regras de cada um: o valor dos
investimentos vem do resumo do dashboard; disponível, reserva e cartão
vêm dos saldos do livro de caixa. Moedas nunca se somam.

Diferente do card "Patrimônio a mercado" do dashboard (que só publica
total quando TODA posição tem cotação), aqui a posição sem cotação entra
pelo custo — e a resposta diz quais (`unpriced`) e marca a base como
MIXED. É uma estimativa declarada, não um valor de mercado.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.schemas.overview import CurrencyOverview, Overview, OverviewPart
from app.services import cashflow_service
from app.services.dashboard_service import get_dashboard_summary

_VARIABLE = {"STOCK_BR", "ETF_BR", "BDR", "STOCK_US", "ETF_US", "FII", "REIT", "CRYPTO"}
_FIXED = {"TESOURO_DIRETO", "CDB", "LCI", "LCA", "DEBENTURE", "BOND", "SAVINGS"}
_FUND = {"FUND"}
GROUP_LABELS = {
    "VARIABLE": "Renda variável",
    "FIXED": "Renda fixa",
    "FUND": "Fundos",
    "OTHER": "Outros",
    "RESERVE": "Reserva",
    "LIQUID": "Disponível em conta",
}
# Mesma ordem dos slots de cor da tela (cor segue a fatia, nunca a posição).
_ORDER = ["VARIABLE", "FIXED", "RESERVE", "LIQUID", "FUND", "OTHER"]
_ZERO = Decimal(0)
_WEIGHT = Decimal("0.0001")


def investment_group(asset_class_code: str) -> str:
    if asset_class_code in _VARIABLE:
        return "VARIABLE"
    if asset_class_code in _FIXED:
        return "FIXED"
    if asset_class_code in _FUND:
        return "FUND"
    return "OTHER"


def _parts(values: dict[str, Decimal]) -> list[OverviewPart]:
    positive = {k: v for k, v in values.items() if v > 0}
    total = sum(positive.values(), start=_ZERO)
    if total <= 0:
        return []
    return [
        OverviewPart(
            key=key,
            label=GROUP_LABELS[key],
            value=positive[key],
            weight=(positive[key] / total).quantize(_WEIGHT, rounding=ROUND_HALF_UP),
        )
        for key in _ORDER
        if key in positive
    ]


def get_overview(db: Session, user_id: UUID, *, as_of: date | None = None) -> Overview:
    as_of = as_of or date.today()
    summary = get_dashboard_summary(db, user_id, None, as_of)
    balances = cashflow_service.get_balances(db, user_id, as_of)
    assets = {
        a.id: a
        for a in db.execute(
            select(Asset).where(Asset.id.in_({p.asset_id for p in summary.positions}))
        ).scalars()
    }
    blocks = {b.currency_code: b for b in summary.totals_by_currency}
    cash = {c.currency_code: c for c in balances.totals_by_currency}

    result: list[CurrencyOverview] = []
    for currency in sorted(set(blocks) | set(cash)):
        block = blocks.get(currency)
        groups: dict[str, Decimal] = {}
        value = cost = unrealized = _ZERO
        unpriced: list[str] = []
        priced_any = False
        for position in summary.positions:
            if position.currency_code != currency or position.quantity <= 0:
                continue
            position_cost = position.total_cost_basis or _ZERO
            cost += position_cost
            if position.market_value is not None:
                position_value = position.market_value
                unrealized += position.unrealized_pnl or _ZERO
                priced_any = True
            else:
                position_value = position_cost
                unpriced.append(position.asset_ticker)
            value += position_value
            group = investment_group(assets[position.asset_id].asset_class_code)
            groups[group] = groups.get(group, _ZERO) + position_value

        balance = cash.get(currency)
        liquid = balance.liquid if balance else _ZERO
        reserve = balance.reserve if balance else _ZERO
        card = balance.card if balance else _ZERO
        if block is None and liquid == reserve == card == 0:
            # Conta de caixa sem nenhum saldo: nada a mostrar nesta moeda.
            continue

        realized = block.total_realized_gain if block else _ZERO
        dividends = block.total_dividends_received if block else _ZERO
        gain = unrealized + realized + dividends
        basis = "MARKET" if not unpriced else ("MIXED" if priced_any else "COST")
        if value == 0:
            basis = "MARKET"
        result.append(
            CurrencyOverview(
                currency_code=currency,
                total=value + liquid + reserve + card,
                investments_value=value,
                investments_cost=cost,
                investments_basis=basis,
                unpriced=sorted(set(unpriced)),
                result=gain,
                result_pct=(
                    (gain / cost).quantize(_WEIGHT, rounding=ROUND_HALF_UP) if cost > 0 else None
                ),
                result_complete=not unpriced,
                net_contributions=block.net_contributions if block else _ZERO,
                liquid=liquid,
                reserve=reserve,
                card=card,
                parts=_parts({**groups, "RESERVE": reserve, "LIQUID": liquid}),
                investment_groups=_parts(groups),
            )
        )
    return Overview(as_of=as_of, totals_by_currency=result)
