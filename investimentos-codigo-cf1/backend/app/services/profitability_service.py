"""Rentabilidade (Fase 8) — retorno absoluto realizado + XIRR/CAGR de
histórico fechado (D-D1). Fase 12: com uma cotação, a posição ABERTA
também tem XIRR/CAGR — o valor de mercado entra como fluxo final
(`terminal`), fornecido por quem chama. TWR continua de fora: precisa
de valorações em CADA data de fluxo, ou seja, de histórico de cotações.

Funções puras: recebem `TransactionFact`/`PositionResult` já obtidos
pelo repositório/Financial Engine, não abrem sessão de banco. Isso
mantém a lógica de rentabilidade tão testável quanto o resto do
Financial Engine, mesmo vivendo em `app/services/` (aqui porque
combina dado de mais de um ativo — não é uma regra pura de UM ativo
como `PositionCalculator`, mas também não deveria precisar de Postgres
para ser testada).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.financial_engine.performance import CAGRCalculator, CashFlow, XIRRCalculator
from app.domain.financial_engine.types import PositionResult, TransactionFact
from app.models.enums import TransactionType

_PROCEEDS_TYPES = {TransactionType.DIVIDEND, TransactionType.JCP, TransactionType.INCOME}
_NO_CASH_FLOW_TYPES = {
    TransactionType.BONUS_SHARES,
    TransactionType.STOCK_SPLIT,
    TransactionType.REVERSE_SPLIT,
    # DEPOSIT/WITHDRAWAL/TRANSFER_IN/TRANSFER_OUT ficam de fora de
    # propósito (D-E2): este é o XIRR "dos ativos", não "da carteira
    # completa" — sem CashHolding não há como saber quanto caixa ficou
    # parado numa conta fechada em ativos mas nunca sacada.
    TransactionType.DEPOSIT,
    TransactionType.WITHDRAWAL,
    TransactionType.TRANSFER_IN,
    TransactionType.TRANSFER_OUT,
}


@dataclass(frozen=True)
class ProfitabilityResult:
    is_closed: bool
    realized_return_pct: Decimal | None
    xirr: Decimal | None
    cagr: Decimal | None
    unavailable_reason: str | None


@dataclass(frozen=True)
class ScopeAssetInput:
    """Um ativo dentro de um escopo (conta/portfolio) a combinar."""

    position: PositionResult
    facts: list[TransactionFact]
    currency_code: str
    # Valor de mercado da posição ABERTA como fluxo final (data da
    # cotação, valor positivo). `None` = sem cotação utilizável.
    terminal: CashFlow | None = None


def asset_cash_flows(facts: list[TransactionFact]) -> list[CashFlow]:
    """Fluxos de caixa DOS ATIVOS (seção 3 da proposta aprovada):
    BUY/SELL/DIVIDEND/JCP/INCOME/FEE. Eventos societários e
    DEPOSIT/WITHDRAWAL/TRANSFER_* não geram fluxo aqui (ver
    `_NO_CASH_FLOW_TYPES`).
    """
    flows: list[CashFlow] = []
    for fact in facts:
        if fact.transaction_type == TransactionType.BUY:
            flows.append(
                CashFlow(
                    when=fact.transaction_date,
                    amount=-(fact.quantity * fact.unit_price + fact.fees),
                )
            )
        elif fact.transaction_type == TransactionType.SELL:
            flows.append(
                CashFlow(
                    when=fact.transaction_date,
                    amount=(fact.quantity * fact.unit_price - fact.fees),
                )
            )
        elif fact.transaction_type in _PROCEEDS_TYPES:
            flows.append(
                CashFlow(when=fact.transaction_date, amount=(fact.gross_amount - fact.fees))
            )
        elif fact.transaction_type == TransactionType.FEE:
            flows.append(
                CashFlow(when=fact.transaction_date, amount=-(fact.gross_amount + fact.fees))
            )
        elif fact.transaction_type in _NO_CASH_FLOW_TYPES:
            continue
        else:
            raise ValueError(
                f"tipo de transação não tratado em asset_cash_flows: {fact.transaction_type}"
            )
    return flows


def _flows_by_distinct_date(flows: list[CashFlow]) -> dict[date, Decimal]:
    by_date: dict[date, Decimal] = {}
    for flow in flows:
        by_date[flow.when] = by_date.get(flow.when, Decimal(0)) + flow.amount
    return by_date


def _xirr_and_cagr(flows: list[CashFlow]) -> tuple[Decimal | None, Decimal | None, str | None]:
    """XIRR sempre que os fluxos tiverem os dois sinais (independente
    de quantas datas distintas existirem). CAGR (correção da revisão)
    SÓ quando os fluxos couberem em exatamente 2 datas distintas — uma
    de entrada, uma de saída — senão só XIRR se aplica.
    """
    try:
        xirr = XIRRCalculator.calculate(flows)
    except ValueError:
        return None, None, "sem fluxo de entrada e saída conhecidos — XIRR não calculável"

    cagr: Decimal | None = None
    by_date = _flows_by_distinct_date(flows)
    if len(by_date) == 2:
        begin_date, end_date = sorted(by_date)
        begin_value = -by_date[begin_date]
        end_value = by_date[end_date]
        if begin_value > 0:
            try:
                cagr = CAGRCalculator.calculate(begin_value, end_value, begin_date, end_date)
            except ValueError:
                cagr = None

    return xirr, cagr, None


def _terminal_problem(facts: list[TransactionFact], terminal: CashFlow) -> str | None:
    """O fluxo final só fecha a conta se a cotação NÃO é anterior à
    última movimentação: senão ela precifica uma quantidade que mudou
    depois, e o "fluxo final" cairia no meio do histórico.
    """
    last_movement = max(fact.transaction_date for fact in facts)
    if terminal.when < last_movement:
        return (
            f"cotação de {terminal.when.isoformat()} é anterior à última movimentação "
            f"({last_movement.isoformat()})"
        )
    return None


def compute_position_profitability(
    facts: list[TransactionFact], position: PositionResult, terminal: CashFlow | None = None
) -> ProfitabilityResult:
    """Rentabilidade de UMA posição (account, asset).

    `terminal` (Fase 12): valor de mercado da posição aberta, na data
    da cotação. Com ele, XIRR/CAGR medem o retorno ATÉ a cotação.

    D-D3/regra 2 (revisão): `is_closed` reflete só a quantidade final
    (zero ou não) — um XIRR indisponível por falta de fluxo de entrada
    conhecido NÃO torna a posição "aberta", só torna o XIRR, em si,
    indisponível.
    """
    is_closed = position.quantity == 0
    reasons: list[str] = []

    realized_return_pct: Decimal | None = None
    if position.realized_cost_basis > 0:
        realized_return_pct = (
            position.realized_gain + position.dividends_received
        ) / position.realized_cost_basis
    elif position.realized_gain != 0 or position.dividends_received != 0:
        reasons.append("custo de aquisição realizado é zero — retorno percentual não é definível")

    xirr: Decimal | None = None
    cagr: Decimal | None = None
    if not is_closed and terminal is None:
        reasons.append("posição ainda aberta — sem cotação para medir o retorno até hoje")
    elif not is_closed and (problem := _terminal_problem(facts, terminal)) is not None:
        reasons.append(f"posição ainda aberta — {problem}")
    else:
        flows = asset_cash_flows(facts)
        if not is_closed:
            flows.append(terminal)
        xirr, cagr, xirr_reason = _xirr_and_cagr(flows)
        if xirr_reason:
            reasons.append(xirr_reason)

    return ProfitabilityResult(
        is_closed=is_closed,
        realized_return_pct=realized_return_pct,
        xirr=xirr,
        cagr=cagr,
        unavailable_reason="; ".join(reasons) if reasons else None,
    )


def compute_scope_profitability(inputs: list[ScopeAssetInput]) -> ProfitabilityResult:
    """Rentabilidade combinada de um escopo (conta/portfolio) com um ou
    mais ativos. D-D3: fechado só quando TODOS os ativos do escopo têm
    quantidade final zero. Regra nova 1: só combina XIRR entre ativos
    de MESMA moeda — sem FX histórico, nunca converte nem inventa taxa.
    """
    if not inputs:
        return ProfitabilityResult(
            is_closed=True,
            realized_return_pct=None,
            xirr=None,
            cagr=None,
            unavailable_reason="sem posições no escopo",
        )

    reasons: list[str] = []
    total_realized_gain = sum((i.position.realized_gain for i in inputs), Decimal(0))
    total_dividends = sum((i.position.dividends_received for i in inputs), Decimal(0))
    total_realized_cost_basis = sum((i.position.realized_cost_basis for i in inputs), Decimal(0))

    realized_return_pct: Decimal | None = None
    if total_realized_cost_basis > 0:
        realized_return_pct = (total_realized_gain + total_dividends) / total_realized_cost_basis
    elif total_realized_gain != 0 or total_dividends != 0:
        reasons.append(
            "custo de aquisição realizado é zero no escopo — retorno percentual não é definível"
        )

    is_closed = all(i.position.quantity == 0 for i in inputs)
    xirr: Decimal | None = None
    cagr: Decimal | None = None

    open_without_terminal = [
        i
        for i in inputs
        if i.position.quantity != 0
        and (i.terminal is None or _terminal_problem(i.facts, i.terminal) is not None)
    ]
    if open_without_terminal:
        reasons.append(
            "escopo ainda tem posição aberta sem cotação utilizável — "
            "retorno até hoje não calculável"
        )
    else:
        currencies = {i.currency_code for i in inputs}
        if len(currencies) > 1:
            reasons.append(
                "ativos em moedas diferentes no escopo — sem câmbio histórico para combinar"
            )
        else:
            combined_flows: list[CashFlow] = []
            for asset_input in inputs:
                combined_flows.extend(asset_cash_flows(asset_input.facts))
                if asset_input.position.quantity != 0:
                    combined_flows.append(asset_input.terminal)
            xirr, cagr, xirr_reason = _xirr_and_cagr(combined_flows)
            if xirr_reason:
                reasons.append(xirr_reason)

    return ProfitabilityResult(
        is_closed=is_closed,
        realized_return_pct=realized_return_pct,
        xirr=xirr,
        cagr=cagr,
        unavailable_reason="; ".join(reasons) if reasons else None,
    )
