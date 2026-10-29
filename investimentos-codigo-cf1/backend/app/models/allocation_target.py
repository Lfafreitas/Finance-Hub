import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AllocationTarget(Base, TimestampMixin):
    """Peso-alvo de uma classe de ativo numa moeda, definido pelo
    usuário (0.30 = 30%). É a régua dele — o app só mostra a distância
    entre o peso atual e o alvo, nunca recomenda comprar ou vender.
    """

    __tablename__ = "allocation_targets"
    __table_args__ = (
        CheckConstraint(
            "target_weight >= 0 AND target_weight <= 1", name="ck_allocation_target_range"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    currency_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code"), primary_key=True
    )
    asset_class_code: Mapped[str] = mapped_column(
        String(30), ForeignKey("asset_classes.code"), primary_key=True
    )
    target_weight: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
