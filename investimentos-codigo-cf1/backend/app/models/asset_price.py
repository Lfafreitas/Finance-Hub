import uuid

from sqlalchemy import CheckConstraint, Date, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import PriceSource


class AssetPrice(Base, TimestampMixin):
    """Cotação de UM ativo em UMA data (Fase 12 — motor de cotações).

    É uma OBSERVAÇÃO de mercado, não um evento do usuário: como o
    cadastro de ativos, é global. Diferente de `Transaction`, pode ser
    corrigida — uma cotação digitada errada é substituída pela certa
    para a mesma (ativo, data, fonte); nenhum cálculo é persistido a
    partir dela, então corrigir a cotação corrige tudo o que deriva.

    `currency_code` é gravado em cada cotação (não só deduzido do
    ativo) para a linha se descrever sozinha; o service garante que é a
    moeda do ativo. Não existe conversão de câmbio aqui.

    `source` separa as origens: hoje só MANUAL. Um provedor externo
    futuro grava com a própria fonte, sem sobrescrever o que o usuário
    digitou.
    """

    __tablename__ = "asset_prices"
    __table_args__ = (
        UniqueConstraint(
            "asset_id", "price_date", "source", name="uq_asset_prices_asset_date_source"
        ),
        CheckConstraint("price > 0", name="ck_asset_prices_price_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True
    )
    price_date: Mapped[object] = mapped_column(Date, nullable=False)
    # Mesma precisão de `Transaction.unit_price`.
    price: Mapped[object] = mapped_column(Numeric(20, 8), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code"), nullable=False
    )
    source: Mapped[PriceSource] = mapped_column(
        Enum(PriceSource, name="price_source"), nullable=False, default=PriceSource.MANUAL
    )
