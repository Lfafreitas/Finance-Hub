import uuid

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import AccountType


class Account(Base, TimestampMixin):
    """Conta de um usuário em uma instituição (ex.: "XP - Ações",
    "Nubank - Conta corrente"). Uma conta pode conter ativos de
    diferentes classes (seção 5 do requisito) — a restrição de classe
    de ativo é responsabilidade do domínio/aplicação, não do schema.

    Fase 5: referencia `Portfolio` via `portfolio_id` (nullable, 1
    Account -> 0 ou 1 Portfolio). Uma conta sem carteira nomeada cai
    na visão consolidada do usuário.

    CF-1: `account_type` decide a qual livro a conta pertence —
    BROKERAGE é o livro de investimentos (`Transaction`); os demais
    tipos são o livro de caixa (`CashflowEntry`). Ver `AccountType`.
    """

    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("user_id", "institution_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    institution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("institutions.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code"), nullable=False
    )
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=True, index=True
    )
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, name="account_type"),
        nullable=False,
        default=AccountType.BROKERAGE,
        server_default=AccountType.BROKERAGE.value,
    )
