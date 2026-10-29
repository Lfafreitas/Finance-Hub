import uuid

from sqlalchemy import Date, Enum, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import TransactionSource, TransactionStatus, TransactionType


class Transaction(Base, TimestampMixin):
    """O evento financeiro original — a FONTE DA VERDADE do sistema
    (seção 35/3.4 da arquitetura aprovada).

    Princípios de design:

    - Não depende de `Position` para existir: `asset_id` é opcional
      (nulo em aportes/retiradas de dinheiro puro), mas a Transaction
      em si nunca referencia uma posição calculada.
    - Imutabilidade: reforçada por um TRIGGER de banco (migration
      seguinte) — qualquer UPDATE que altere um campo financeiro de
      uma transação já existente é rejeitado pelo Postgres, não só
      pela aplicação. Correção/estorno usam `status` +
      `reverses_transaction_id` (ver classe `TransactionStatus`).
    - `source` e `external_reference` existem para o futuro
      Reconciliation Engine comparar a mesma transação vinda de fontes
      diferentes (ex.: import CSV vs. API Pluggy).
    """

    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_account_asset_date", "account_id", "asset_id", "transaction_date"),
        # Índice único PARCIAL: só se aplica quando external_reference
        # não é nulo (transações manuais, sem referência externa, não
        # entram nessa checagem de duplicidade).
        Index(
            "uq_transactions_account_external_ref",
            "account_id",
            "external_reference",
            unique=True,
            postgresql_where=text("external_reference IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id"), nullable=True, index=True
    )
    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type"), nullable=False
    )

    # Quantidade e preço unitário: NUMERIC(20,8) para suportar frações
    # de ação (fractional investing no exterior) e preços com muitas
    # casas decimais sem perda de precisão. NUNCA float (float binário
    # não representa exatamente valores decimais monetários).
    quantity: Mapped[object | None] = mapped_column(Numeric(20, 8), nullable=True)
    unit_price: Mapped[object | None] = mapped_column(Numeric(20, 8), nullable=True)

    # Valores monetários agregados: NUMERIC(18,4). Quatro casas
    # decimais (em vez de 2) para acomodar valores intermediários de
    # cálculo (ex.: rateio de taxas, JCP fracionado) sem arredondar
    # precocemente — arredondamento para exibição é responsabilidade
    # da camada de apresentação/Financial Engine, não da persistência.
    fees: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    gross_amount: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False)

    currency_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code"), nullable=False
    )
    transaction_date: Mapped[object] = mapped_column(Date, nullable=False)

    source: Mapped[TransactionSource] = mapped_column(
        Enum(TransactionSource, name="transaction_source"), nullable=False
    )
    external_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Estorno/correção — ver TransactionStatus para a regra de transição.
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, name="transaction_status"),
        nullable=False,
        default=TransactionStatus.ACTIVE,
    )
    reverses_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True, index=True
    )

    # --- Vínculo de transferência (TRANSFER_OUT <-> TRANSFER_IN) ---------
    # Semântica: liga as duas pernas de uma mesma transferência entre
    # contas. Pode ficar NULL enquanto a segunda perna ainda não existe
    # (ex.: importação assíncrona). Uma vez preenchido, é imutável (não
    # pode ser trocado nem apagado depois) — reforçado pelo trigger de
    # imutabilidade. Consistência do par (tipo complementar, referência
    # simétrica, sem autovínculo) é validada por um trigger de banco
    # separado, deferido para o fim da transação (COMMIT), porque as
    # duas pernas costumam ser gravadas em statements distintos.
    # A FK é DEFERRABLE INITIALLY DEFERRED no banco (migration
    # acfec251182b): as duas pernas se referenciam mutuamente e só
    # ficam consistentes no fim da transação. Declarada igual aqui
    # para o model espelhar o schema real (`alembic check` limpo).
    linked_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "transactions.id",
            name="fk_transactions_linked_transaction_id",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=True,
        index=True,
    )

    # --- Câmbio do evento (não é cotação de mercado nem série histórica) -
    # Semântica obrigatória: quantos BRL equivalem a 1 unidade da moeda
    # desta Transaction, NAQUELE evento específico. Ex.: currency_code
    # = 'USD' e fx_rate_to_brl = 5.20 significa 1 USD = R$5,20 na data
    # e no contexto desta transação — não é uma cotação "atual" nem vem
    # de uma tabela de séries de câmbio (isso é Quote/FxRate, fase
    # futura). Para transações em BRL, o valor correto é NULL — BRL é
    # tratado como taxa implícita 1, nunca 1.0 armazenado explicitamente
    # (evita redundância e uma falsa impressão de "câmbio registrado"
    # onde não existe conversão nenhuma). Imutável como qualquer outro
    # campo financeiro.
    fx_rate_to_brl: Mapped[object | None] = mapped_column(Numeric(18, 8), nullable=True)
