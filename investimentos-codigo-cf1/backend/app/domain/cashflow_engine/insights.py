"""Onde dá para melhorar os gastos (Visual-1).

Regras determinísticas, cada uma explicável pelos próprios lançamentos.
Nenhum julgamento sobre o que é gasto "bom" ou "ruim": o sistema só
mostra o que mudou em relação ao seu próprio histórico.

- ACIMA DO NORMAL: categoria em que o mês gastou pelo menos 20% e
  pelo menos `MIN_DIFFERENCE` a mais que a média dos 3 meses anteriores.
  Exige pelo menos 2 desses meses com gasto registrado.
- SE REPETE TODO MÊS: mesmo texto de descrição com gasto em cada um dos
  3 últimos meses (o atual e os 2 anteriores) — assinaturas e contas.
- GASTOS PEQUENOS: compras abaixo de `SMALL_LIMIT` no mês, quando são
  pelo menos `SMALL_MIN_COUNT`.
- ONDE ESTÁ O GASTO: as 3 maiores categorias e quanto do total somam.
- NÃO CLASSIFICADO: saídas ainda sem natureza, para dizer quanto da
  análise está incompleta.

Gasto é o lançamento EXPENSE com o sinal invertido (saída = positivo);
estorno de compra (EXPENSE positivo) reduz o gasto da sua categoria.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

ABOVE_RATIO = Decimal("0.20")
MIN_DIFFERENCE = Decimal(50)
MIN_HISTORY_MONTHS = 2
SMALL_LIMIT = Decimal(30)
SMALL_MIN_COUNT = 5
TOP_N = 3
_MONEY = Decimal("0.01")
_SHARE = Decimal("0.0001")


@dataclass(frozen=True)
class SpendFact:
    """Um lançamento de saída do caixa, em UMA moeda."""

    entry_date: date
    amount: Decimal  # assinado, como no livro: saída negativa
    expense: bool  # natureza EXPENSE (False = ainda não classificado)
    category_key: str | None  # categoria-mãe; None = sem categoria
    category_label: str | None
    match_text: str


@dataclass(frozen=True)
class CategoryChange:
    key: str
    label: str
    current: Decimal
    average: Decimal
    difference: Decimal


@dataclass(frozen=True)
class RecurringItem:
    label: str
    monthly_average: Decimal


@dataclass(frozen=True)
class CategoryShare:
    key: str | None
    label: str | None
    amount: Decimal
    share: Decimal


@dataclass(frozen=True)
class SpendingInsights:
    month: str
    expenses: Decimal
    history_months: int
    above_normal: tuple[CategoryChange, ...]
    recurring: tuple[RecurringItem, ...]
    recurring_total: Decimal
    small_count: int
    small_total: Decimal
    top_categories: tuple[CategoryShare, ...]
    top_share: Decimal | None
    unclassified_outflow: Decimal
    unclassified_share: Decimal | None


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _share(part: Decimal, whole: Decimal) -> Decimal:
    return (part / whole).quantize(_SHARE, rounding=ROUND_HALF_UP)


def _month_key(day: date) -> tuple[int, int]:
    return day.year, day.month


def _previous(year: int, month: int, back: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) - back
    return index // 12, index % 12 + 1


def spending_insights(facts: Iterable[SpendFact], year: int, month: int) -> SpendingInsights:
    facts = list(facts)
    current = (year, month)
    history = [_previous(year, month, back) for back in (1, 2, 3)]

    spend_by_month: dict[tuple[int, int], dict[str | None, Decimal]] = {}
    labels: dict[str | None, str | None] = {}
    texts: dict[str, dict[tuple[int, int], Decimal]] = {}
    small_count = 0
    small_total = Decimal(0)
    unclassified = Decimal(0)
    for fact in facts:
        key = _month_key(fact.entry_date)
        if not fact.expense:
            if key == current and fact.amount < 0:
                unclassified += -fact.amount
            continue
        spend = -fact.amount
        bucket = spend_by_month.setdefault(key, {})
        bucket[fact.category_key] = bucket.get(fact.category_key, Decimal(0)) + spend
        labels[fact.category_key] = fact.category_label
        if fact.match_text:
            per_text = texts.setdefault(fact.match_text, {})
            per_text[key] = per_text.get(key, Decimal(0)) + spend
        if key == current and 0 < spend < SMALL_LIMIT:
            small_count += 1
            small_total += spend

    current_spend = spend_by_month.get(current, {})
    expenses = sum(current_spend.values(), start=Decimal(0))

    with_history = [m for m in history if sum(spend_by_month.get(m, {}).values(), Decimal(0)) > 0]
    above: list[CategoryChange] = []
    if len(with_history) >= MIN_HISTORY_MONTHS:
        for key, amount in current_spend.items():
            if key is None:
                continue
            average = sum(
                (spend_by_month.get(m, {}).get(key, Decimal(0)) for m in history), Decimal(0)
            ) / len(history)
            difference = amount - average
            if average > 0 and difference >= MIN_DIFFERENCE and difference >= average * ABOVE_RATIO:
                above.append(
                    CategoryChange(
                        key=key,
                        label=labels.get(key) or "",
                        current=_money(amount),
                        average=_money(average),
                        difference=_money(difference),
                    )
                )
    above.sort(key=lambda c: (-c.difference, c.label))

    window = [current, history[0], history[1]]
    recurring = [
        RecurringItem(
            label=text,
            monthly_average=_money(sum((per_month[m] for m in window), Decimal(0)) / len(window)),
        )
        for text, per_month in texts.items()
        if all(per_month.get(m, Decimal(0)) > 0 for m in window)
    ]
    recurring.sort(key=lambda r: (-r.monthly_average, r.label))

    positives = sorted(
        ((k, v) for k, v in current_spend.items() if v > 0),
        key=lambda kv: (-kv[1], kv[0] is None, kv[0] or ""),
    )
    top = (
        tuple(
            CategoryShare(
                key=key,
                label=labels.get(key),
                amount=_money(amount),
                share=_share(amount, expenses),
            )
            for key, amount in positives[:TOP_N]
        )
        if expenses > 0
        else ()
    )
    top_share = (
        _share(sum((amount for _, amount in positives[:TOP_N]), Decimal(0)), expenses)
        if expenses > 0 and len(positives) > 1
        else None
    )
    outflow = expenses + unclassified
    return SpendingInsights(
        month=f"{year}-{month:02d}",
        expenses=_money(expenses),
        history_months=len(with_history),
        above_normal=tuple(above[:TOP_N]),
        recurring=tuple(recurring),
        recurring_total=_money(sum((r.monthly_average for r in recurring), Decimal(0))),
        small_count=small_count if small_count >= SMALL_MIN_COUNT else 0,
        small_total=_money(small_total) if small_count >= SMALL_MIN_COUNT else Decimal("0.00"),
        top_categories=top,
        top_share=top_share,
        unclassified_outflow=_money(unclassified),
        unclassified_share=_share(unclassified, outflow) if outflow > 0 else None,
    )
