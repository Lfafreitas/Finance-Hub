"""Schemas de cadastro (ativos, instituições, contas, carteiras) —
o mínimo que as telas de importação e de lançamento manual precisam
para não depender de inserção direta no banco.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import AccountType, InstitutionType


def _clean(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("não pode ser vazio")
    return cleaned


class CurrencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str


class AssetClassRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ticker: str
    name: str
    asset_class_code: str
    country: str
    currency_code: str
    maturity_date: date | None = None
    annual_rate: Decimal | None = None


class AssetCreate(BaseModel):
    """`ticker` e `country` são normalizados para maiúsculas — é assim
    que a importação procura o ativo (`build_row` faz `upper()` no
    ticker do arquivo).
    """

    ticker: str = Field(max_length=30)
    name: str = Field(max_length=200)
    asset_class_code: str = Field(max_length=30)
    country: str = Field(min_length=2, max_length=2)
    currency_code: str = Field(min_length=3, max_length=3)
    # Só renda fixa. Taxa como fração (0.0385 = 3,85% a.a.). Na edição,
    # campo ausente no corpo mantém o valor gravado; null apaga.
    maturity_date: date | None = None
    annual_rate: Decimal | None = Field(default=None, ge=0, le=1, max_digits=9, decimal_places=6)

    @field_validator("ticker", "country", "currency_code", "asset_class_code")
    @classmethod
    def _upper(cls, value: str) -> str:
        return _clean(value).upper()

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _clean(value)


class InstitutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    institution_type: InstitutionType
    country: str


class InstitutionCreate(BaseModel):
    name: str = Field(max_length=150)
    institution_type: InstitutionType
    country: str = Field(min_length=2, max_length=2)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _clean(value)

    @field_validator("country")
    @classmethod
    def _country(cls, value: str) -> str:
        return _clean(value).upper()


class AccountCreate(BaseModel):
    """`user_id` nunca vem do cliente — é o usuário resolvido pela
    dependency de autenticação.

    `account_type` tem BROKERAGE como padrão: até o CF-1 toda conta
    era de investimentos, e quem não informa o tipo continua criando
    uma. Carteira (`portfolio_id`) só existe no livro de investimentos.
    """

    name: str = Field(max_length=150)
    institution_id: UUID
    currency_code: str = Field(min_length=3, max_length=3)
    portfolio_id: UUID | None = None
    account_type: AccountType = AccountType.BROKERAGE

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _clean(value)

    @field_validator("currency_code")
    @classmethod
    def _currency(cls, value: str) -> str:
        return _clean(value).upper()


class PortfolioCreate(BaseModel):
    name: str = Field(max_length=100)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _clean(value)
