"""Schemas de classificação do livro de caixa (CF-2)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import CashflowNature, RuleDirection, RuleMatchType


def _clean(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("não pode ser vazio")
    return cleaned


class CategoryWrite(BaseModel):
    name: str = Field(max_length=80)
    parent_id: UUID | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _clean(value)


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    parent_id: UUID | None


class TagWrite(BaseModel):
    name: str = Field(max_length=80)
    tag_group: str = Field(default="", max_length=40)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _clean(value)

    @field_validator("tag_group")
    @classmethod
    def _group(cls, value: str) -> str:
        return " ".join(value.split())


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    tag_group: str


class EntryClassificationWrite(BaseModel):
    """Classificação MANUAL completa de um lançamento: substitui
    natureza, categoria e tags de uma vez. Depois dela, nenhuma regra
    volta a mexer no lançamento.
    """

    nature: CashflowNature
    category_id: UUID | None = None
    tag_ids: list[UUID] = Field(default_factory=list)


class RuleWrite(BaseModel):
    name: str = Field(max_length=120)
    priority: int = Field(default=100, ge=0, le=100000)
    is_active: bool = True
    match_type: RuleMatchType = RuleMatchType.CONTAINS
    pattern: str = Field(max_length=200)
    direction: RuleDirection = RuleDirection.ANY
    account_id: UUID | None = None
    set_nature: CashflowNature
    set_category_id: UUID | None = None
    tag_ids: list[UUID] = Field(default_factory=list)

    @field_validator("name", "pattern")
    @classmethod
    def _text(cls, value: str) -> str:
        return _clean(value)


class RuleRead(BaseModel):
    id: UUID
    name: str
    priority: int
    is_active: bool
    match_type: RuleMatchType
    pattern: str
    direction: RuleDirection
    account_id: UUID | None
    set_nature: CashflowNature
    set_category_id: UUID | None
    tag_ids: list[UUID]


class RuleApplyRequest(BaseModel):
    """`reevaluate` falso (padrão): só lançamentos ainda não
    classificados. Verdadeiro: também os que uma regra classificou
    antes — eles são reavaliados do zero com as regras atuais.
    Classificação manual e transferências nunca são tocadas.
    """

    reevaluate: bool = False
    account_id: UUID | None = None
    start: date | None = None
    end: date | None = None


class RuleApplyChange(BaseModel):
    entry_id: UUID
    description: str
    match_text: str
    amount: Decimal
    currency_code: str
    entry_date: date
    rule_id: UUID | None
    rule_name: str | None
    nature: CashflowNature
    category_id: UUID | None
    tag_ids: list[UUID]


class RuleApplyResult(BaseModel):
    """`changes` lista só os lançamentos cuja classificação mudou (ou
    mudaria, na prévia). `examined` é quantos foram avaliados.
    """

    applied: bool
    examined: int
    changes: list[RuleApplyChange]


class CategoryTotalsRead(BaseModel):
    category_id: UUID | None
    category_name: str | None
    parent_id: UUID | None
    own_expenses: Decimal
    own_income: Decimal
    total_expenses: Decimal
    total_income: Decimal


class CurrencyCategoryBreakdown(BaseModel):
    """`expenses` e `income` são os totais da moeda no período — iguais
    aos do resumo e à soma dos `own_*` das linhas.
    """

    currency_code: str
    expenses: Decimal
    income: Decimal
    categories: list[CategoryTotalsRead]


class CategoryBreakdown(BaseModel):
    start: date
    end: date
    totals_by_currency: list[CurrencyCategoryBreakdown]
