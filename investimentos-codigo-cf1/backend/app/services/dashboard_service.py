from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.financial_engine.performance import CashFlow
from app.domain.financial_engine.position import PositionCalculator
from app.domain.financial_engine.types import PositionResult, TransactionFact
from app.domain.financial_engine.valuation import PriceQuote, ValuationCalculator, ValuationResult
from app.models.account import Account
from app.models.asset import Asset
from app.models.asset_price import AssetPrice
from app.models.enums import TransactionType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction
from app.repositories.accounts import list_accounts
from app.repositories.prices import get_latest_prices
from app.repositories.transactions import get_active_transactions
from app.schemas.dashboard import (
    AllocationSlice,
    ContributionPoint,
    DashboardCurrencyTotals,
    DashboardSummary,
    PositionSummary,
)
from app.services.exceptions import PortfolioNotFoundError
from app.services.profitability_service import (
    ScopeAssetInput,
    compute_position_profitability,
    compute_scope_profitability,
)

_EXTERNAL_FLOW_TYPES = {TransactionType.DEPOSIT, TransactionType.WITHDRAWAL}
_TRANSFER_TYPES = {TransactionType.TRANSFER_IN, TransactionType.TRANSFER_OUT}


def _accounts_in_scope(db: Session, user_id: UUID, portfolio_id: UUID | None) -> list[Account]:
    accounts = list_accounts(db, user_id)
    if portfolio_id is None:
        return accounts

    portfolio = db.get(Portfolio, portfolio_id)
    if portfolio is None or portfolio.user_id != user_id:
        raise PortfolioNotFoundError(f"portfolio {portfolio_id} não encontrado")

    return [a for a in accounts if a.portfolio_id == portfolio_id]


def _linked_accounts_map(
    db: Session, facts_by_account: dict[UUID, list[TransactionFact]]
) -> dict[UUID, UUID]:
    """Para cada TRANSFER_IN/OUT com linked_transaction_id preenchido,
    descobre a qual conta a outra perna pertence — em UMA consulta em
    lote, não uma por transação.
    """
    linked_ids: set[UUID] = set()
    for facts in facts_by_account.values():
        for fact in facts:
            if fact.transaction_type in _TRANSFER_TYPES and fact.linked_transaction_id is not None:
                linked_ids.add(fact.linked_transaction_id)

    if not linked_ids:
        return {}

    stmt = select(Transaction.id, Transaction.account_id).where(Transaction.id.in_(linked_ids))
    return {row.id: row.account_id for row in db.execute(stmt)}


def _external_flow_events(
    facts_by_account: dict[UUID, list[TransactionFact]],
    scope_account_ids: set[UUID],
    linked_accounts: dict[UUID, UUID],
) -> list[tuple[date, Decimal, str]]:
    """Lista (data, valor_com_sinal, moeda) de todo fluxo externo ao
    ESCOPO (não ao usuário inteiro): DEPOSIT/WITHDRAWAL sempre contam;
    TRANSFER_IN/OUT só contam se a outra perna estiver FORA do escopo
    (dentro do escopo, as duas pernas se cancelam — mesma regra já
    validada na Fase 5, generalizada aqui para um escopo arbitrário —
    conta única, portfolio, ou consolidado quando o escopo é todas as
    contas do usuário).

    A moeda é a do PRÓPRIO movimento (`Transaction.currency_code`, que
    é NOT NULL no banco) — nunca derivada da conta, nunca um padrão.
    """
    events: list[tuple[date, Decimal, str]] = []
    for facts in facts_by_account.values():
        for fact in facts:
            if fact.transaction_type == TransactionType.DEPOSIT:
                events.append((fact.transaction_date, fact.gross_amount, fact.currency_code))
            elif fact.transaction_type == TransactionType.WITHDRAWAL:
                events.append((fact.transaction_date, -fact.gross_amount, fact.currency_code))
            elif fact.transaction_type in _TRANSFER_TYPES:
                counterpart_account = (
                    linked_accounts.get(fact.linked_transaction_id)
                    if fact.linked_transaction_id is not None
                    else None
                )
                counterpart_in_scope = (
                    counterpart_account is not None and counterpart_account in scope_account_ids
                )
                if counterpart_in_scope:
                    continue  # interno ao escopo, neutro
                sign = 1 if fact.transaction_type == TransactionType.TRANSFER_IN else -1
                events.append((fact.transaction_date, sign * fact.gross_amount, fact.currency_code))
    return events


@dataclass
class _CurrencyAccumulator:
    """Acumuladores de UMA moeda. Nada aqui recebe valor de outra."""

    total_cost_basis: Decimal = Decimal(0)
    total_realized_gain: Decimal = Decimal(0)
    total_dividends: Decimal = Decimal(0)
    total_realized_cost_basis: Decimal = Decimal(0)
    cost_basis_by_asset: dict[UUID, Decimal] = field(default_factory=dict)
    scope_asset_inputs: list[ScopeAssetInput] = field(default_factory=list)
    contribution_evolution: list[ContributionPoint] = field(default_factory=list)
    net_contributions: Decimal = Decimal(0)
    # Fase 12: soma só do que foi valorado; `unpriced_tickers` lista as
    # posições ABERTAS sem valoração — se não estiver vazia, o bloco não
    # publica total a mercado.
    market_value: Decimal = Decimal(0)
    unrealized_pnl: Decimal = Decimal(0)
    price_dates: list[date] = field(default_factory=list)
    unpriced_tickers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _PositionValuation:
    """Valoração de UMA posição, ou o motivo de não haver."""

    valuation: ValuationResult | None = None
    quote: PriceQuote | None = None
    unavailable_reason: str | None = None


def _value_position(
    position: PositionResult, currency_code: str, ticker: str, price: AssetPrice | None
) -> _PositionValuation:
    """Aplica a cotação à posição. Nenhuma conversão de moeda: cotação
    em moeda diferente da posição é tratada como ausência de cotação,
    com o motivo explícito.
    """
    if position.quantity == 0:
        # Posição zerada: vale zero, sem precisar de cotação.
        zero = ValuationResult(
            market_value=Decimal(0), unrealized_pnl=Decimal(0), unrealized_return_pct=None
        )
        return _PositionValuation(valuation=zero)
    if price is None:
        return _PositionValuation(unavailable_reason=f"sem cotação cadastrada para {ticker}")
    if price.currency_code != currency_code:
        return _PositionValuation(
            unavailable_reason=(
                f"cotação de {ticker} está em {price.currency_code}, mas a posição está em "
                f"{currency_code} — nenhuma conversão é feita"
            )
        )
    quote = PriceQuote(
        price=price.price, price_date=price.price_date, currency_code=price.currency_code
    )
    return _PositionValuation(valuation=ValuationCalculator.calculate(position, quote), quote=quote)


def _position_currencies(asset_facts: list[TransactionFact]) -> list[str]:
    """Moedas efetivamente registradas nas Transactions ATIVAS do par
    (conta, ativo), em ordem alfabética. TODAS contam — inclusive
    eventos societários, que não movimentam dinheiro mas carregam
    `currency_code`: uma moeda diferente ali também evidencia dado
    inconsistente, sem exceção escondida na regra.
    """
    return sorted({fact.currency_code for fact in asset_facts})


def get_dashboard_summary(
    db: Session,
    user_id: UUID,
    portfolio_id: UUID | None = None,
    reference_date: date | None = None,
) -> DashboardSummary:
    """Resumo do escopo, com todo valor monetário SEPARADO POR MOEDA.

    `reference_date` (padrão: hoje) é a data até a qual uma cotação
    pode ser usada na valoração a mercado.

    Valores de moedas diferentes nunca são somados nem convertidos:
    cada moeda tem seu próprio bloco em `totals_by_currency`. A moeda
    de uma posição é a das suas Transactions ativas; uma posição com
    mais de uma moeda é devolvida marcada como inconsistente e fica
    fora de todos os blocos (ver `PositionSummary`).
    """
    accounts = _accounts_in_scope(db, user_id, portfolio_id)
    scope_account_ids = {a.id for a in accounts}

    # Uma única leitura de transações ACTIVE por conta, reaproveitada
    # para posições, aportes e evolução — evita repetir a mesma
    # consulta várias vezes dentro desta função.
    facts_by_account = {account.id: get_active_transactions(db, account.id) for account in accounts}
    linked_accounts = _linked_accounts_map(db, facts_by_account)

    positions: list[PositionSummary] = []
    by_currency: dict[str, _CurrencyAccumulator] = {}
    asset_cache: dict[UUID, Asset] = {}
    latest_prices = get_latest_prices(
        db,
        {f.asset_id for facts in facts_by_account.values() for f in facts if f.asset_id},
        reference_date or date.today(),
    )

    for account in accounts:
        facts = facts_by_account[account.id]
        asset_ids = {f.asset_id for f in facts if f.asset_id is not None}

        for asset_id in asset_ids:
            asset_facts = [f for f in facts if f.asset_id == asset_id]
            result = PositionCalculator.calculate(asset_facts)

            if asset_id not in asset_cache:
                asset_cache[asset_id] = db.get(Asset, asset_id)
            asset = asset_cache[asset_id]

            currencies = _position_currencies(asset_facts)
            if len(currencies) > 1:
                # O engine não conhece moeda: custo, resultado e
                # proventos acima somaram moedas diferentes. Só a
                # quantidade é aproveitável; nada entra em total algum.
                reason = (
                    f"transações ativas em mais de uma moeda ({', '.join(currencies)}) — "
                    "valores não calculados e posição fora dos totais até a correção dos dados"
                )
                positions.append(
                    PositionSummary(
                        account_id=account.id,
                        asset_id=asset_id,
                        asset_ticker=asset.ticker,
                        asset_name=asset.name,
                        currency_code=None,
                        currency_inconsistency_reason=reason,
                        quantity=result.quantity,
                        average_cost=None,
                        total_cost_basis=None,
                        realized_gain=None,
                        dividends_received=None,
                        realized_cost_basis=None,
                        is_closed=result.quantity == 0,
                        profitability_unavailable_reason=reason,
                    )
                )
                continue

            currency_code = currencies[0]
            valued = _value_position(
                result, currency_code, asset.ticker, latest_prices.get(asset_id)
            )
            # Posição aberta e valorada: o valor de mercado entra como
            # fluxo final do XIRR, na data da cotação.
            terminal = (
                CashFlow(when=valued.quote.price_date, amount=valued.valuation.market_value)
                if valued.quote is not None
                else None
            )
            profitability = compute_position_profitability(asset_facts, result, terminal)
            positions.append(
                PositionSummary(
                    account_id=account.id,
                    asset_id=asset_id,
                    asset_ticker=asset.ticker,
                    asset_name=asset.name,
                    currency_code=currency_code,
                    quantity=result.quantity,
                    average_cost=result.average_cost,
                    total_cost_basis=result.total_cost_basis,
                    realized_gain=result.realized_gain,
                    dividends_received=result.dividends_received,
                    realized_cost_basis=result.realized_cost_basis,
                    realized_return_pct=profitability.realized_return_pct,
                    is_closed=profitability.is_closed,
                    xirr=profitability.xirr,
                    cagr=profitability.cagr,
                    profitability_unavailable_reason=profitability.unavailable_reason,
                    market_price=valued.quote.price if valued.quote else None,
                    market_price_date=valued.quote.price_date if valued.quote else None,
                    market_value=valued.valuation.market_value if valued.valuation else None,
                    unrealized_pnl=valued.valuation.unrealized_pnl if valued.valuation else None,
                    unrealized_return_pct=(
                        valued.valuation.unrealized_return_pct if valued.valuation else None
                    ),
                    unavailable_reason=valued.unavailable_reason,
                )
            )
            totals = by_currency.setdefault(currency_code, _CurrencyAccumulator())
            if valued.valuation is None:
                totals.unpriced_tickers.append(asset.ticker)
            else:
                totals.market_value += valued.valuation.market_value
                totals.unrealized_pnl += valued.valuation.unrealized_pnl
                if valued.quote is not None:
                    totals.price_dates.append(valued.quote.price_date)
            totals.total_cost_basis += result.total_cost_basis
            totals.total_realized_gain += result.realized_gain
            totals.total_dividends += result.dividends_received
            totals.total_realized_cost_basis += result.realized_cost_basis
            totals.cost_basis_by_asset[asset_id] = (
                totals.cost_basis_by_asset.get(asset_id, Decimal(0)) + result.total_cost_basis
            )
            totals.scope_asset_inputs.append(
                ScopeAssetInput(
                    position=result,
                    facts=asset_facts,
                    currency_code=currency_code,
                    terminal=terminal,
                )
            )

    events = _external_flow_events(facts_by_account, scope_account_ids, linked_accounts)
    events.sort(key=lambda e: e[0])
    for event_date, amount, currency_code in events:
        totals = by_currency.setdefault(currency_code, _CurrencyAccumulator())
        totals.net_contributions += amount
        totals.contribution_evolution.append(
            ContributionPoint(date=event_date, cumulative_net_contribution=totals.net_contributions)
        )

    totals_by_currency: list[DashboardCurrencyTotals] = []
    for currency_code in sorted(by_currency):
        totals = by_currency[currency_code]

        allocation: list[AllocationSlice] = []
        if totals.total_cost_basis > 0:
            for asset_id, cost in totals.cost_basis_by_asset.items():
                if cost <= 0:
                    continue
                asset = asset_cache[asset_id]
                allocation.append(
                    AllocationSlice(
                        asset_id=asset_id,
                        asset_ticker=asset.ticker,
                        asset_name=asset.name,
                        cost_basis=cost,
                        # Denominador = custo total DESTA moeda.
                        percentage=(cost / totals.total_cost_basis) * Decimal(100),
                    )
                )

        profitability = compute_scope_profitability(totals.scope_asset_inputs)

        # Total a mercado só quando TODA posição aberta do bloco foi
        # valorada — soma parcial não é publicada como total.
        fully_priced = not totals.unpriced_tickers
        market_reason = (
            None
            if fully_priced
            else "sem cotação utilizável para: " + ", ".join(sorted(set(totals.unpriced_tickers)))
        )
        current_return = (
            totals.unrealized_pnl / totals.total_cost_basis
            if fully_priced and totals.total_cost_basis > 0
            else None
        )
        totals_by_currency.append(
            DashboardCurrencyTotals(
                currency_code=currency_code,
                total_cost_basis=totals.total_cost_basis,
                total_realized_gain=totals.total_realized_gain,
                total_dividends_received=totals.total_dividends,
                net_contributions=totals.net_contributions,
                total_realized_cost_basis=totals.total_realized_cost_basis,
                realized_return_pct=profitability.realized_return_pct,
                is_closed=profitability.is_closed,
                xirr=profitability.xirr,
                cagr=profitability.cagr,
                profitability_unavailable_reason=profitability.unavailable_reason,
                market_value=totals.market_value if fully_priced else None,
                unrealized_pnl=totals.unrealized_pnl if fully_priced else None,
                current_return=current_return,
                market_data_as_of=(
                    min(totals.price_dates) if fully_priced and totals.price_dates else None
                ),
                market_data_unavailable_reason=market_reason,
                allocation=allocation,
                contribution_evolution=totals.contribution_evolution,
            )
        )

    return DashboardSummary(
        portfolio_id=portfolio_id,
        positions=positions,
        totals_by_currency=totals_by_currency,
    )
