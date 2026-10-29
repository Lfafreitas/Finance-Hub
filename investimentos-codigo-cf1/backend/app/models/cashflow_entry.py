import uuid

from sqlalchemy import (
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import CashflowEntryStatus, CashflowNature, TransactionSource


class CashflowEntry(Base, TimestampMixin):
    """Lançamento do livro de CAIXA (CF-1) — separado de `Transaction`,
    que é o livro de investimentos. Os dois nunca se misturam: uma
    conta BROKERAGE não recebe `CashflowEntry` e uma conta de caixa
    não recebe `Transaction`.

    Fato x classificação:

    - FATO (imutável, trigger de banco): conta, data, valor, moeda,
      descrição, origem. Erro de fato se corrige com estorno
      (`status` ACTIVE -> REVERSED) e um lançamento novo. Um
      lançamento excluído pode ser restaurado (REVERSED -> ACTIVE).
    - CLASSIFICAÇÃO (mutável): `nature`, `counterparty_account_id`,
      `transfer_group_id`, `notes`.

    `amount` é assinado na moeda da conta: positivo entra, negativo
    sai. `entry_date` é a data de competência (data da compra, não a
    do pagamento da fatura).

    Transferência: `nature = TRANSFER` exige contraparte e grupo.
    Entre duas contas de caixa são duas pernas com o mesmo
    `transfer_group_id` e valores opostos. Para/de uma conta BROKERAGE
    existe UMA perna só, no lado do caixa — a outra ponta pertence ao
    livro de investimentos.
    """

    __tablename__ = "cashflow_entries"
    __table_args__ = (
        CheckConstraint("amount <> 0", name="ck_cashflow_entries_amount_nonzero"),
        CheckConstraint(
            "(nature = 'TRANSFER') = (counterparty_account_id IS NOT NULL)",
            name="ck_cashflow_entries_transfer_has_counterparty",
        ),
        CheckConstraint(
            "(nature = 'TRANSFER') = (transfer_group_id IS NOT NULL)",
            name="ck_cashflow_entries_transfer_has_group",
        ),
        CheckConstraint(
            "counterparty_account_id IS NULL OR counterparty_account_id <> account_id",
            name="ck_cashflow_entries_counterparty_differs",
        ),
        CheckConstraint(
            "nature <> 'TRANSFER' OR category_id IS NULL",
            name="ck_cashflow_entries_transfer_has_no_category",
        ),
        Index("ix_cashflow_entries_account_date", "account_id", "entry_date"),
        # CF-3 — deduplicação da importação. Valem também para
        # lançamentos estornados: reimportar não recria o que o usuário
        # estornou.
        Index(
            "uq_cashflow_entries_account_external_id",
            "account_id",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
        Index(
            "uq_cashflow_entries_account_fingerprint",
            "account_id",
            "import_fingerprint",
            unique=True,
            postgresql_where=text("import_fingerprint IS NOT NULL"),
        ),
        # Edição-2 — um lançamento é substituído por uma edição no máximo
        # uma vez.
        Index(
            "uq_cashflow_entries_corrects_entry_id",
            "corrects_entry_id",
            unique=True,
            postgresql_where=text("corrects_entry_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True
    )
    entry_date: Mapped[object] = mapped_column(Date, nullable=False)
    amount: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code"), nullable=False
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[TransactionSource] = mapped_column(
        Enum(TransactionSource, name="transaction_source", create_type=False), nullable=False
    )

    # CF-3 — de onde o lançamento veio. Fato: imutável como o resto.
    # `external_id` é o identificador que o banco deu à linha (extrato
    # da conta). `import_fingerprint` é a chave por conteúdo, usada
    # quando o arquivo não traz identificador (fatura do cartão).
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    import_fingerprint: Mapped[str | None] = mapped_column(String(80), nullable=True)
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cashflow_import_batches.id", name="fk_cashflow_entries_import_batch_id"),
        nullable=True,
        index=True,
    )

    # Edição-2 — preenchido no lançamento criado por uma edição: aponta
    # para o que ele substituiu (que fica REVERSED). Fato, imutável.
    corrects_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cashflow_entries.id", name="fk_cashflow_entries_corrects_entry_id"),
        nullable=True,
    )

    nature: Mapped[CashflowNature] = mapped_column(
        Enum(CashflowNature, name="cashflow_nature"), nullable=False
    )
    counterparty_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=True, index=True
    )
    transfer_group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # CF-2 — classificação. `classified_by_rule_id` diz POR QUE o
    # lançamento está classificado assim: preenchido = a regra decidiu;
    # nulo com natureza/categoria definidas = decisão manual, que
    # nenhuma regra sobrescreve.
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cashflow_categories.id", name="fk_cashflow_entries_category_id"),
        nullable=True,
        index=True,
    )
    classified_by_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "cashflow_rules.id",
            name="fk_cashflow_entries_classified_by_rule_id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    status: Mapped[CashflowEntryStatus] = mapped_column(
        Enum(CashflowEntryStatus, name="cashflow_entry_status"),
        nullable=False,
        default=CashflowEntryStatus.ACTIVE,
    )
