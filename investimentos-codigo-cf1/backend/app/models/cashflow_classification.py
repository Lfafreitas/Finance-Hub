"""Classificação do livro de caixa (CF-2): categorias, tags e regras.

Tudo aqui é CLASSIFICAÇÃO — nada altera o fato de um lançamento.
"""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import CashflowNature, RuleDirection, RuleMatchType


class CashflowCategory(Base, TimestampMixin):
    """Categoria em até DOIS níveis (categoria e subcategoria). O limite
    de profundidade é garantido por trigger: o pai de uma subcategoria
    nunca tem pai.
    """

    __tablename__ = "cashflow_categories"
    __table_args__ = (
        CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name="ck_cashflow_categories_not_own_parent"
        ),
        Index(
            "uq_cashflow_categories_root_name",
            "user_id",
            "name",
            unique=True,
            postgresql_where=text("parent_id IS NULL"),
        ),
        Index(
            "uq_cashflow_categories_child_name",
            "user_id",
            "parent_id",
            "name",
            unique=True,
            postgresql_where=text("parent_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cashflow_categories.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)


class CashflowTag(Base, TimestampMixin):
    """Marcador livre, ortogonal à categoria. `tag_group` separa
    dimensões (ex.: "beneficiário", "canal"); vazio = sem grupo.
    """

    __tablename__ = "cashflow_tags"
    __table_args__ = (
        UniqueConstraint("user_id", "tag_group", "name", name="uq_cashflow_tags_group_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    tag_group: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(80), nullable=False)


cashflow_entry_tags = Table(
    "cashflow_entry_tags",
    Base.metadata,
    Column("entry_id", UUID(as_uuid=True), ForeignKey("cashflow_entries.id"), primary_key=True),
    Column(
        "tag_id",
        UUID(as_uuid=True),
        ForeignKey("cashflow_tags.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
)


class CashflowRule(Base, TimestampMixin):
    """Regra determinística de classificação. A primeira regra ativa
    que casa — em ordem de `priority`, depois `created_at` — decide
    sozinha; regras não se combinam. Toda regra define a natureza
    (nunca TRANSFER nem UNCLASSIFIED); categoria e tags são opcionais.
    """

    __tablename__ = "cashflow_rules"
    __table_args__ = (
        CheckConstraint(
            "set_nature NOT IN ('TRANSFER', 'UNCLASSIFIED')",
            name="ck_cashflow_rules_sets_a_real_nature",
        ),
        CheckConstraint("length(btrim(pattern)) > 0", name="ck_cashflow_rules_pattern_not_blank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    match_type: Mapped[RuleMatchType] = mapped_column(
        Enum(RuleMatchType, name="cashflow_rule_match_type"), nullable=False
    )
    pattern: Mapped[str] = mapped_column(String(200), nullable=False)
    direction: Mapped[RuleDirection] = mapped_column(
        Enum(RuleDirection, name="cashflow_rule_direction"),
        nullable=False,
        default=RuleDirection.ANY,
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=True, index=True
    )

    set_nature: Mapped[CashflowNature] = mapped_column(
        Enum(CashflowNature, name="cashflow_nature", create_type=False), nullable=False
    )
    set_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cashflow_categories.id"), nullable=True, index=True
    )


cashflow_rule_tags = Table(
    "cashflow_rule_tags",
    Base.metadata,
    Column(
        "rule_id",
        UUID(as_uuid=True),
        ForeignKey("cashflow_rules.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        UUID(as_uuid=True),
        ForeignKey("cashflow_tags.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
)
