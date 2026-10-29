"""Proventos (Fase 9) — transforma os eventos DIVIDEND/JCP/INCOME já
registrados em uma visão analítica: por mês, por ano, por ativo, por
instituição, por tipo, com totais e médias.

Regra de moeda (nova nesta fase, mesma filosofia da Fase 8): toda
agregação é feita SEPARADA POR MOEDA — nunca soma BRL com USD.
Consolidado só existe quando há exatamente uma moeda em todo o escopo;
caso contrário, `None` + motivo explícito, sem inventar câmbio.

`aggregate_dividends` é pura (sem sessão de banco) — recebe os fatos já
extraídos e os lookups (ticker/nome de ativo, nome de instituição) já
resolvidos por quem chama. `get_dividends_summary` é quem toca o banco,
no mesmo padrão do `dashboard_service`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.financial_engine.types import TransactionFact
from app.models.account import Account
from app.models.asset import Asset
from app.models.enums import TransactionType
from app.models.portfolio import Portfolio
from app.repositories.accounts import get_institutions_by_id, list_accounts
from app.repositories.transactions import get_active_transactions
from app.schemas.dividends import (
    DividendsByAsset,
    DividendsByInstitution,
    DividendsByMonth,
    DividendsByType,
    DividendsByYear,
    DividendsCurrencyTotals,
    DividendsSummary,
)
from app.services.exceptions import PortfolioNotFoundError

_DIVIDEND_TYPES = {TransactionType.DIVIDEND, TransactionType.JCP, TransactionType.INCOME}

# Janela de "últimos 12 meses" definida como os 365 dias corridos que
# terminam na data de referência (inclusive) — convenção simples e
# determinística, documentada aqui em vez de tentar aritmética de mês
# calendário (que teria que lidar com dias 29-31 de forma arbitrária).
_LAST_12_MONTHS_WINDOW_DAYS = 365


@dataclass(frozen=True)
class DividendFact:
    """Um evento de provento já filtrado (ACTIVE) e líquido de taxas."""

    transaction_type: TransactionType
    transaction_date: date
    amount: Decimal
    currency_code: str
    asset_id: UUID | None
    account_id: UUID


def extract_dividend_facts(
    facts_by_account: dict[UUID, list[TransactionFact]],
) -> list[DividendFact]:
    """Filtra DIVIDEND/JCP/INCOME de um conjunto de TransactionFact já
    obtido via `get_active_transactions` — REVERSED nunca chega aqui
    (mesmo filtro centralizado das fases anteriores).
    """
    result: list[DividendFact] = []
    for account_id, facts in facts_by_account.items():
        for fact in facts:
            if fact.transaction_type in _DIVIDEND_TYPES:
                result.append(
                    DividendFact(
                        transaction_type=fact.transaction_type,
                        transaction_date=fact.transaction_date,
                        amount=fact.gross_amount - fact.fees,
                        currency_code=fact.currency_code,
                        asset_id=fact.asset_id,
                        account_id=account_id,
                    )
                )
    return result


def _months_elapsed(first: date, last: date) -> int:
    """Meses corridos entre duas datas, inclusive — jan a jan = 1 mês,
    jan a fev = 2 meses. Usado só para `average_monthly` (D-F3).
    """
    return (last.year - first.year) * 12 + (last.month - first.month) + 1


def aggregate_dividends(
    dividend_facts: list[DividendFact],
    asset_lookup: dict[UUID, tuple[str, str]],
    account_institution_lookup: dict[UUID, tuple[UUID, str]],
    reference_date: date,
    portfolio_id: UUID | None = None,
) -> DividendsSummary:
    """Função pura: todo o cálculo de agregação, sem tocar banco.

    `asset_lookup`: asset_id -> (ticker, nome)
    `account_institution_lookup`: account_id -> (institution_id, nome da instituição)
    """
    by_currency: dict[str, list[DividendFact]] = {}
    for fact in dividend_facts:
        by_currency.setdefault(fact.currency_code, []).append(fact)

    totals_by_currency: list[DividendsCurrencyTotals] = []
    cutoff_12m = reference_date - timedelta(days=_LAST_12_MONTHS_WINDOW_DAYS)

    for currency_code, facts in by_currency.items():
        total_received = sum((f.amount for f in facts), Decimal(0))
        total_current_year = sum(
            (f.amount for f in facts if f.transaction_date.year == reference_date.year), Decimal(0)
        )
        total_last_12_months = sum(
            (f.amount for f in facts if cutoff_12m <= f.transaction_date <= reference_date),
            Decimal(0),
        )

        dates = [f.transaction_date for f in facts]
        months_elapsed = _months_elapsed(min(dates), max(dates))
        average_monthly = total_received / months_elapsed if months_elapsed > 0 else Decimal(0)
        average_monthly_last_12_months = total_last_12_months / Decimal(12)

        totals_by_currency.append(
            DividendsCurrencyTotals(
                currency_code=currency_code,
                total_received=total_received,
                total_current_year=total_current_year,
                total_last_12_months=total_last_12_months,
                average_monthly=average_monthly,
                average_monthly_last_12_months=average_monthly_last_12_months,
            )
        )

    consolidated_total_received: Decimal | None = None
    consolidation_unavailable_reason: str | None = None
    if len(by_currency) == 1:
        consolidated_total_received = next(iter(totals_by_currency)).total_received
    elif len(by_currency) > 1:
        moedas = ", ".join(sorted(by_currency))
        consolidation_unavailable_reason = (
            f"proventos em mais de uma moeda ({moedas}) — sem câmbio histórico para "
            "consolidar em um único total (fase futura)"
        )

    by_month_map: dict[tuple[str, str], Decimal] = {}
    by_year_map: dict[tuple[int, str], Decimal] = {}
    by_asset_map: dict[tuple[UUID | None, str], Decimal] = {}
    by_institution_map: dict[tuple[UUID, str], Decimal] = {}
    by_type_map: dict[tuple[TransactionType, str], Decimal] = {}

    for fact in dividend_facts:
        month_key = (fact.transaction_date.strftime("%Y-%m"), fact.currency_code)
        by_month_map[month_key] = by_month_map.get(month_key, Decimal(0)) + fact.amount

        year_key = (fact.transaction_date.year, fact.currency_code)
        by_year_map[year_key] = by_year_map.get(year_key, Decimal(0)) + fact.amount

        asset_key = (fact.asset_id, fact.currency_code)
        by_asset_map[asset_key] = by_asset_map.get(asset_key, Decimal(0)) + fact.amount

        if fact.account_id in account_institution_lookup:
            institution_id, _name = account_institution_lookup[fact.account_id]
            inst_key = (institution_id, fact.currency_code)
            by_institution_map[inst_key] = (
                by_institution_map.get(inst_key, Decimal(0)) + fact.amount
            )

        type_key = (fact.transaction_type, fact.currency_code)
        by_type_map[type_key] = by_type_map.get(type_key, Decimal(0)) + fact.amount

    by_month = [
        DividendsByMonth(month=month, currency_code=currency, amount=amount)
        for (month, currency), amount in sorted(by_month_map.items())
    ]
    by_year = [
        DividendsByYear(year=year, currency_code=currency, amount=amount)
        for (year, currency), amount in sorted(by_year_map.items())
    ]
    by_asset = [
        DividendsByAsset(
            asset_id=asset_id,
            asset_ticker=asset_lookup[asset_id][0],
            asset_name=asset_lookup[asset_id][1],
            currency_code=currency,
            amount=amount,
        )
        for (asset_id, currency), amount in by_asset_map.items()
        if asset_id is not None and asset_id in asset_lookup
    ]
    institution_names = {inst_id: name for inst_id, name in account_institution_lookup.values()}
    by_institution = [
        DividendsByInstitution(
            institution_id=institution_id,
            institution_name=institution_names.get(institution_id, ""),
            currency_code=currency,
            amount=amount,
        )
        for (institution_id, currency), amount in by_institution_map.items()
    ]
    by_type = [
        DividendsByType(
            transaction_type=transaction_type.value, currency_code=currency, amount=amount
        )
        for (transaction_type, currency), amount in by_type_map.items()
    ]

    return DividendsSummary(
        portfolio_id=portfolio_id,
        totals_by_currency=totals_by_currency,
        consolidated_total_received=consolidated_total_received,
        consolidation_unavailable_reason=consolidation_unavailable_reason,
        by_month=by_month,
        by_year=by_year,
        by_asset=by_asset,
        by_institution=by_institution,
        by_type=by_type,
    )


def _accounts_in_scope(db: Session, user_id: UUID, portfolio_id: UUID | None) -> list[Account]:
    """Mesma lógica de `dashboard_service._accounts_in_scope`,
    duplicada aqui de propósito nesta fase para não tocar em código da
    Fase 7 sem necessidade — ver observação não-bloqueante no relatório
    final sobre extrair isso para um lugar compartilhado.
    """
    accounts = list_accounts(db, user_id)
    if portfolio_id is None:
        return accounts

    portfolio = db.get(Portfolio, portfolio_id)
    if portfolio is None or portfolio.user_id != user_id:
        raise PortfolioNotFoundError(f"portfolio {portfolio_id} não encontrado")

    return [a for a in accounts if a.portfolio_id == portfolio_id]


def get_dividends_summary(
    db: Session, user_id: UUID, portfolio_id: UUID | None = None, reference_date: date | None = None
) -> DividendsSummary:
    accounts = _accounts_in_scope(db, user_id, portfolio_id)
    facts_by_account = {account.id: get_active_transactions(db, account.id) for account in accounts}
    dividend_facts = extract_dividend_facts(facts_by_account)

    asset_ids = {f.asset_id for f in dividend_facts if f.asset_id is not None}
    asset_lookup: dict[UUID, tuple[str, str]] = {}
    for asset_id in asset_ids:
        asset = db.get(Asset, asset_id)
        if asset is not None:
            asset_lookup[asset_id] = (asset.ticker, asset.name)

    institutions = get_institutions_by_id(db, {a.institution_id for a in accounts})
    account_institution_lookup: dict[UUID, tuple[UUID, str]] = {
        account.id: (account.institution_id, institutions[account.institution_id].name)
        for account in accounts
        if account.institution_id in institutions
    }

    return aggregate_dividends(
        dividend_facts=dividend_facts,
        asset_lookup=asset_lookup,
        account_institution_lookup=account_institution_lookup,
        reference_date=reference_date or date.today(),
        portfolio_id=portfolio_id,
    )
