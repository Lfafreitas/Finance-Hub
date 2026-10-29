import uuid

from sqlalchemy import Date, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import CashflowImportProfile


class CashflowImportBatch(Base, TimestampMixin):
    """Registro de UMA importação confirmada no livro de caixa.

    Decisão 14: o arquivo do banco NÃO é guardado — só o hash dele
    (`file_sha256`), o nome e os números do lote. O hash serve para
    avisar "este arquivo já foi importado"; a deduplicação de verdade é
    por lançamento.

    `statement_balance` é o saldo final informado pelo próprio arquivo
    (só o OFX traz), guardado para conferência.
    """

    __tablename__ = "cashflow_import_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True
    )
    profile: Mapped[CashflowImportProfile] = mapped_column(
        Enum(CashflowImportProfile, name="cashflow_import_profile"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    period_start: Mapped[object | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[object | None] = mapped_column(Date, nullable=True)
    rows_total: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_imported: Mapped[int] = mapped_column(Integer, nullable=False)
    statement_balance: Mapped[object | None] = mapped_column(Numeric(18, 4), nullable=True)
    statement_balance_date: Mapped[object | None] = mapped_column(Date, nullable=True)
