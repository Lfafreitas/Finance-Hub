"""Agenda da carteira: vencimentos de renda fixa.

Função pura: recebe as posições de renda fixa já somadas por ativo e
moeda e devolve a lista de vencimentos em ordem de data. Moedas nunca
se somam (cada item tem a sua).

A estimativa no vencimento é só uma referência: juros compostos da taxa
anual informada no cadastro, desde a primeira compra, sobre o custo.
Não considera imposto, IOF nem a convenção exata de cada emissor — a
tela diz isso.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")

# Classes de renda fixa (as mesmas que o patrimônio chama de "renda fixa",
# menos a poupança, que não vence).
FIXED_INCOME_CLASSES = frozenset({"TESOURO_DIRETO", "CDB", "LCI", "LCA", "DEBENTURE", "BOND"})


@dataclass(frozen=True)
class FixedIncomeHolding:
    ticker: str
    name: str
    asset_class: str
    currency_code: str
    quantity: Decimal
    cost: Decimal
    value: Decimal | None
    maturity_date: date | None
    annual_rate: Decimal | None
    first_purchase: date | None


@dataclass(frozen=True)
class Maturity:
    ticker: str
    name: str
    currency_code: str
    maturity_date: date
    days_left: int  # negativo = já venceu e ainda aparece na carteira
    annual_rate: Decimal | None
    cost: Decimal
    value: Decimal | None
    estimated_at_maturity: Decimal | None


@dataclass(frozen=True)
class Agenda:
    maturities: list[Maturity]
    missing_maturity: list[str]  # renda fixa na carteira sem vencimento informado


def estimate_at_maturity(
    cost: Decimal, annual_rate: Decimal | None, start: date | None, maturity: date
) -> Decimal | None:
    """Custo corrigido por juros compostos da taxa anual, de `start` até o
    vencimento (base 365 dias). None quando falta taxa ou data de início.
    """
    if annual_rate is None or start is None or start > maturity or cost <= 0:
        return None
    years = Decimal((maturity - start).days) / Decimal(365)
    factor = Decimal(str((1 + float(annual_rate)) ** float(years)))
    return (cost * factor).quantize(_CENT, rounding=ROUND_HALF_UP)


def build_agenda(holdings: list[FixedIncomeHolding], today: date) -> Agenda:
    maturities: list[Maturity] = []
    missing: list[str] = []
    for h in holdings:
        if h.quantity <= 0:
            continue
        if h.maturity_date is None:
            if h.asset_class in FIXED_INCOME_CLASSES:
                missing.append(h.ticker)
            continue
        maturities.append(
            Maturity(
                ticker=h.ticker,
                name=h.name,
                currency_code=h.currency_code,
                maturity_date=h.maturity_date,
                days_left=(h.maturity_date - today).days,
                annual_rate=h.annual_rate,
                cost=h.cost,
                value=h.value,
                estimated_at_maturity=estimate_at_maturity(
                    h.cost, h.annual_rate, h.first_purchase, h.maturity_date
                ),
            )
        )
    maturities.sort(key=lambda m: (m.maturity_date, m.ticker))
    return Agenda(maturities=maturities, missing_maturity=sorted(set(missing)))
