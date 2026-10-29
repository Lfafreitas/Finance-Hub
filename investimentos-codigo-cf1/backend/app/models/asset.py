import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Asset(Base, TimestampMixin):
    """Cadastro global de ativos negociáveis (ações, FIIs, ETFs, renda
    fixa etc.). Não pertence a um usuário — é compartilhado.

    Decisão de unicidade: (ticker, country) é único. Isso assume que o
    mesmo ticker no mesmo país sempre se refere ao mesmo ativo — regra
    simples e suficiente para o MVP, mas que precisará de revisão caso
    o sistema passe a suportar múltiplas bolsas dentro do mesmo país
    com tickers colidentes (não é um caso comum no escopo atual).

    Dívida documentada para expansão futura (não implementada agora):
    identificar ativos também por *exchange*/mercado e por código
    ISIN, caso a unicidade por (ticker, country) se mostre
    insuficiente.
    """

    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("ticker", "country", name="uq_asset_ticker_country"),
        CheckConstraint(
            "annual_rate IS NULL OR (annual_rate >= 0 AND annual_rate <= 1)",
            name="ck_asset_annual_rate_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_class_code: Mapped[str] = mapped_column(
        String(30), ForeignKey("asset_classes.code"), nullable=False
    )
    country: Mapped[str] = mapped_column(String(2), nullable=False)  # ISO 3166-1 alpha-2
    currency_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code"), nullable=False
    )
    # Renda fixa (CD, título): vencimento e taxa anual contratada (fração,
    # 0.0385 = 3,85% a.a.). Vazios para os demais ativos. Alimentam a
    # agenda de vencimentos; não mudam nenhum cálculo de posição.
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    annual_rate: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
