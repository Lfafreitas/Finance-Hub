"""Anotações do usuário (pensamentos sobre a carteira ou qualquer assunto) e
as fontes de leitura que a análise diária resume no Jornal.

Ficam só no computador. Uma nota só vai para o Claude (conversa e análise
diária) quando `share_with_claude` está marcado.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Note(Base, TimestampMixin):
    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Trecho destacado na leitura e de onde veio.
    quote: Mapped[str | None] = mapped_column(Text)
    source_title: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(500))
    tickers: Mapped[str] = mapped_column(String(220), nullable=False, default="")
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    share_with_claude: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ReadingSource(Base, TimestampMixin):
    __tablename__ = "reading_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    # O que procurar ali (ex.: "pranchas novas do Brasil").
    focus: Mapped[str | None] = mapped_column(String(300))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
