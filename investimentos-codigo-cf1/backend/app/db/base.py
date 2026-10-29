from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base declarativa. Todo model do domínio herda daqui."""


class TimestampMixin:
    """Timestamps de auditoria de quando o REGISTRO foi criado/alterado
    no nosso sistema — não confundir com a data do EVENTO financeiro
    (ex.: `Transaction.transaction_date`), que é um dado de negócio
    diferente e não é coberto por este mixin.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
