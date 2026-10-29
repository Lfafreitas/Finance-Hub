import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import ReconciliationStatus


def canonical_pair(first: uuid.UUID, second: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Ordena um par de ids de Transaction como (min, max).

    `uuid.UUID` compara pelo valor inteiro dos 128 bits, que é a mesma
    ordem (bytes big-endian) usada pelo Postgres para o tipo `uuid` —
    então o `CHECK (transaction_a_id < transaction_b_id)` do banco e
    este helper concordam. Um par nunca é de uma Transaction com ela
    mesma.
    """
    if first == second:
        raise ValueError("um par de reconciliação exige duas Transactions distintas")
    return (first, second) if first < second else (second, first)


class ReconciliationLog(Base, TimestampMixin):
    """Registro AUDITÁVEL de um possível conflito entre duas
    Transactions (Reconciliation Engine, Fase 10b). Nunca altera
    nenhuma Transaction por si só: apenas registra que o par foi
    detectado, por quê, e — depois — o que o usuário decidiu.

    Integridade reforçada no banco (não só na aplicação):

    - o par é CANÔNICO: `transaction_a_id < transaction_b_id`
      (min/max). Isso impede par consigo mesmo e faz (A,B) e (B,A)
      serem o mesmo registro para o `UNIQUE(transaction_a_id,
      transaction_b_id)` — o mesmo par nunca é reapresentado;
    - `MERGED` exige sobrevivente e revertida, distintas e ambas
      pertencentes ao par; qualquer outro status não pode ter
      nenhuma das duas;
    - `resolved_at` é nulo em PENDING e obrigatório em
      IGNORED/KEPT_BOTH/MERGED (STALE não é decisão humana, então não
      é restrito).

    Regras que dependem de outras tabelas (o par pertence ao mesmo
    usuário/conta, transição de status permitida) ficam no service.
    """

    __tablename__ = "reconciliation_logs"
    __table_args__ = (
        UniqueConstraint(
            "transaction_a_id", "transaction_b_id", name="uq_reconciliation_logs_pair"
        ),
        Index("ix_reconciliation_logs_user_status", "user_id", "status"),
        CheckConstraint(
            "transaction_a_id < transaction_b_id", name="ck_reconciliation_logs_canonical_pair"
        ),
        CheckConstraint(
            "(status = 'MERGED' "
            " AND surviving_transaction_id IS NOT NULL "
            " AND reversed_transaction_id IS NOT NULL "
            " AND surviving_transaction_id <> reversed_transaction_id "
            " AND surviving_transaction_id IN (transaction_a_id, transaction_b_id) "
            " AND reversed_transaction_id IN (transaction_a_id, transaction_b_id)) "
            "OR (status <> 'MERGED' "
            " AND surviving_transaction_id IS NULL "
            " AND reversed_transaction_id IS NULL)",
            name="ck_reconciliation_logs_merge_consistency",
        ),
        CheckConstraint(
            "(status = 'PENDING' AND resolved_at IS NULL) "
            "OR (status IN ('IGNORED', 'KEPT_BOTH', 'MERGED') AND resolved_at IS NOT NULL) "
            "OR status = 'STALE'",
            name="ck_reconciliation_logs_resolved_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    transaction_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False, index=True
    )
    transaction_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False, index=True
    )
    # Descrição objetiva do motivo da candidatura e dos campos que
    # divergem — preenchida pelo matcher (unidade futura).
    match_reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReconciliationStatus] = mapped_column(
        Enum(ReconciliationStatus, name="reconciliation_status"),
        nullable=False,
        default=ReconciliationStatus.PENDING,
    )
    surviving_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True
    )
    reversed_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
