"""Anotações e fontes de leitura."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _url(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if not cleaned.startswith(("https://", "http://")) or any(ch.isspace() for ch in cleaned):
        raise ValueError("link precisa começar com http:// ou https:// e não ter espaço")
    return cleaned


def _tickers(value: list[str]) -> list[str]:
    cleaned: list[str] = []
    for raw in value:
        ticker = raw.strip().upper()
        if not ticker:
            continue
        if len(ticker) > 20 or "," in ticker:
            raise ValueError("código de ativo com até 20 caracteres, sem vírgula")
        if ticker not in cleaned:
            cleaned.append(ticker)
    return cleaned


class NoteWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, max_length=120)
    body: str = Field(default="", max_length=10000)
    quote: str | None = Field(default=None, max_length=2000)
    source_title: str | None = Field(default=None, max_length=200)
    source_url: str | None = Field(default=None, max_length=500)
    tickers: list[str] = Field(default_factory=list, max_length=10)
    pinned: bool = False
    share_with_claude: bool = False

    @field_validator("source_url")
    @classmethod
    def _check_url(cls, value: str | None) -> str | None:
        return _url(value)

    @field_validator("tickers")
    @classmethod
    def _check_tickers(cls, value: list[str]) -> list[str]:
        return _tickers(value)

    @field_validator("title", "quote", "source_title")
    @classmethod
    def _empty_is_none(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def _has_content(self) -> NoteWrite:
        if not (self.body or self.quote or self.title):
            raise ValueError("a anotação está vazia")
        return self


class NoteRead(BaseModel):
    id: UUID
    title: str | None
    body: str
    quote: str | None
    source_title: str | None
    source_url: str | None
    tickers: list[str]
    pinned: bool
    share_with_claude: bool
    created_at: datetime
    updated_at: datetime


class SourceWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=1, max_length=500)
    focus: str | None = Field(default=None, max_length=300)
    active: bool = True

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        checked = _url(value)
        if checked is None:
            raise ValueError("informe o link da fonte")
        return checked

    @field_validator("focus")
    @classmethod
    def _empty_is_none(cls, value: str | None) -> str | None:
        return value or None


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    url: str
    focus: str | None
    active: bool
