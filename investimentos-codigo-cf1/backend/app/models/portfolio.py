import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Portfolio(Base, TimestampMixin):
    """Agrupador ESTRUTURAL de `Account`s (ex.: "Geral", "Brasil",
    "Aposentadoria"). Responsabilidade única: delimitar o escopo de
    contas que entra em um cálculo agregado do Financial Engine.

    Portfolio NÃO calcula nada — não tem quantidade, preço, valor ou
    rentabilidade próprios. É só o filtro. Uma `Account` pertence a, no
    máximo, um Portfolio (`Account.portfolio_id`, nullable); uma conta
    sem carteira nomeada cai automaticamente na visão consolidada do
    usuário (quando o filtro de portfolio é nulo, soma-se tudo).
    """

    __tablename__ = "portfolios"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
