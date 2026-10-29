from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.cashflow_engine.facts import CashEntryFact
from app.models.enums import AccountType, CashflowNature

# Zero na escala do livro (NUMERIC(18,4)): um termo sem lançamento sai
# como "0.0000", igual aos demais, em vez de "0".
_ZERO = Decimal("0.0000")
_LIQUID_TYPES = {AccountType.CHECKING, AccountType.CASH}


class CashflowIdentityError(Exception):
    """A identidade do caixa não fechou — indica defeito no motor, nunca
    um dado do usuário. Nenhum número é devolvido nesse caso.
    """


@dataclass(frozen=True)
class PeriodSummary:
    """Resumo de UMA moeda em um período (datas inclusivas).

    Lado das origens (por natureza):

    - `income`: soma de INCOME (devolução de renda entra negativa).
    - `third_party_net`: entradas menos saídas de terceiros.
    - `adjustments_net`, `unclassified_net`: líquidos.
    - `internal_transfers_net`: transferências entre contas de caixa.
      É zero quando as duas pernas estão no período; diferente de zero
      denuncia perna órfã.

    Lado dos destinos:

    - `expenses`: quanto foi gasto (positivo). Estorno reduz.
    - `net_invested`: aportes menos resgates (contraparte BROKERAGE).
    - `liquid_variation`: variação de CHECKING + CASH.
    - `reserve_variation`: variação de SAVINGS.
    - `card_balance_variation`: variação do saldo do cartão (negativa
      quando a dívida cresce).

    Identidade, garantida por construção e conferida a cada cálculo:

        income + third_party_net + adjustments_net + unclassified_net
            + internal_transfers_net
        = expenses + net_invested + liquid_variation + reserve_variation
            + card_balance_variation
    """

    currency_code: str
    entry_count: int
    income: Decimal
    third_party_net: Decimal
    adjustments_net: Decimal
    unclassified_net: Decimal
    internal_transfers_net: Decimal
    expenses: Decimal
    net_invested: Decimal
    liquid_variation: Decimal
    reserve_variation: Decimal
    card_balance_variation: Decimal

    @property
    def sources_total(self) -> Decimal:
        return (
            self.income
            + self.third_party_net
            + self.adjustments_net
            + self.unclassified_net
            + self.internal_transfers_net
        )

    @property
    def uses_total(self) -> Decimal:
        return (
            self.expenses
            + self.net_invested
            + self.liquid_variation
            + self.reserve_variation
            + self.card_balance_variation
        )


class _Accumulator:
    def __init__(self) -> None:
        self.entry_count = 0
        self.by_nature: dict[CashflowNature, Decimal] = {}
        self.to_brokerage = _ZERO
        self.internal = _ZERO
        self.liquid = _ZERO
        self.reserve = _ZERO
        self.card = _ZERO

    def add(self, fact: CashEntryFact) -> None:
        self.entry_count += 1
        if fact.nature is CashflowNature.TRANSFER:
            if fact.counterparty_account_type is AccountType.BROKERAGE:
                self.to_brokerage += fact.amount
            else:
                self.internal += fact.amount
        else:
            self.by_nature[fact.nature] = self.by_nature.get(fact.nature, _ZERO) + fact.amount

        if fact.account_type in _LIQUID_TYPES:
            self.liquid += fact.amount
        elif fact.account_type is AccountType.SAVINGS:
            self.reserve += fact.amount
        elif fact.account_type is AccountType.CREDIT_CARD:
            self.card += fact.amount
        else:  # pragma: no cover - CashEntryFact já recusa BROKERAGE
            raise ValueError(f"tipo de conta fora do livro de caixa: {fact.account_type}")

    def build(self, currency_code: str) -> PeriodSummary:
        summary = PeriodSummary(
            currency_code=currency_code,
            entry_count=self.entry_count,
            income=self.by_nature.get(CashflowNature.INCOME, _ZERO),
            third_party_net=self.by_nature.get(CashflowNature.THIRD_PARTY, _ZERO),
            adjustments_net=self.by_nature.get(CashflowNature.ADJUSTMENT, _ZERO),
            unclassified_net=self.by_nature.get(CashflowNature.UNCLASSIFIED, _ZERO),
            internal_transfers_net=self.internal,
            # Saída é negativa no livro; gasto e aporte são mostrados
            # como "quanto saiu", por isso o sinal invertido.
            expenses=-self.by_nature.get(CashflowNature.EXPENSE, _ZERO),
            net_invested=-self.to_brokerage,
            liquid_variation=self.liquid,
            reserve_variation=self.reserve,
            card_balance_variation=self.card,
        )
        if summary.sources_total != summary.uses_total:
            raise CashflowIdentityError(
                f"identidade do caixa não fechou em {currency_code}: "
                f"origens {summary.sources_total} != destinos {summary.uses_total}"
            )
        return summary


class CashflowSummaryCalculator:
    @staticmethod
    def calculate(
        facts: Iterable[CashEntryFact], start: date, end: date
    ) -> dict[str, PeriodSummary]:
        """Um `PeriodSummary` por moeda que teve lançamento no período.
        Moedas nunca são somadas entre si.
        """
        if start > end:
            raise ValueError("início do período depois do fim")
        accumulators: dict[str, _Accumulator] = {}
        for fact in facts:
            if start <= fact.entry_date <= end:
                accumulators.setdefault(fact.currency_code, _Accumulator()).add(fact)
        return {
            currency: accumulators[currency].build(currency) for currency in sorted(accumulators)
        }
