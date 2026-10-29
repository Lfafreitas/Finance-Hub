"""Trava do acesso remoto (Face ID)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuthStatus(BaseModel):
    """`remote`: aberto fora deste computador (celular). `unlocked`: pode
    ver os dados (no computador, sempre). `has_passkeys`: já existe algum
    aparelho cadastrado (senão o celular mostra o cadastro).
    """

    remote: bool
    unlocked: bool
    has_passkeys: bool
    idle_minutes: int


class PairingCodeRead(BaseModel):
    code: str
    expires_at: datetime


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterOptionsRequest(_Strict):
    code: str = Field(min_length=1, max_length=20)


class RegisterVerifyRequest(_Strict):
    challenge_id: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(default="iPhone", max_length=60)
    credential: dict[str, Any]


class LoginVerifyRequest(_Strict):
    challenge_id: str = Field(min_length=1, max_length=100)
    credential: dict[str, Any]


class WebAuthnOptions(BaseModel):
    """`options`: JSON do WebAuthn, entregue como está ao navegador."""

    challenge_id: str
    options: dict[str, Any]


class PasskeyRead(BaseModel):
    id: UUID
    name: str
    rp_id: str
    created_at: datetime
    last_used_at: datetime | None
