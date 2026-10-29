from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

PREDICTED_UNAVAILABLE_REASON = (
    "Sem calendário de proventos — depende de fonte de dado externa (fase futura)."
)


class DividendsByMonth(BaseModel):
    month: str  # "YYYY-MM"
    currency_code: str
    amount: Decimal


class DividendsByYear(BaseModel):
    year: int
    currency_code: str
    amount: Decimal


class DividendsByAsset(BaseModel):
    asset_id: UUID
    asset_ticker: str
    asset_name: str
    currency_code: str
    amount: Decimal


class DividendsByInstitution(BaseModel):
    institution_id: UUID
    institution_name: str
    currency_code: str
    amount: Decimal


class DividendsByType(BaseModel):
    transaction_type: str  # "DIVIDEND" | "JCP" | "INCOME"
    currency_code: str
    amount: Decimal


class DividendsCurrencyTotals(BaseModel):
    """Totais de UMA moeda — nunca somados com outra sem câmbio."""

    currency_code: str
    total_received: Decimal
    total_current_year: Decimal
    total_last_12_months: Decimal
    # D-F3: dois campos formais, sem ambiguidade.
    average_monthly: Decimal  # total_received / meses corridos entre a 1ª e a última ocorrência
    average_monthly_last_12_months: Decimal  # total_last_12_months / 12 (janela fixa)


class DividendsSummary(BaseModel):
    portfolio_id: UUID | None
    totals_by_currency: list[DividendsCurrencyTotals]
    # Só preenchido quando TODOS os proventos do escopo estão na MESMA
    # moeda — nunca soma BRL com USD sem câmbio histórico (regra nova
    # desta fase, mesma filosofia da Fase 8).
    consolidated_total_received: Decimal | None = None
    consolidation_unavailable_reason: str | None = None
    by_month: list[DividendsByMonth]
    by_year: list[DividendsByYear]
    by_asset: list[DividendsByAsset]
    by_institution: list[DividendsByInstitution]
    by_type: list[DividendsByType]
    predicted: Decimal | None = None
    predicted_unavailable_reason: str = PREDICTED_UNAVAILABLE_REASON
