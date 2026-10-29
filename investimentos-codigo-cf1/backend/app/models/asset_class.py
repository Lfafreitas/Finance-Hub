from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AssetClass(Base):
    """Tabela de referência (não enum) para classe de ativo.

    Decisão consciente, ao contrário de TransactionType: novas classes
    de ativo (ex.: adicionar "COE" ou "Debênture Incentivada" amanhã)
    são principalmente metadado/taxonomia — não exigem lógica nova no
    Financial Engine na mesma medida que um novo TransactionType exige.
    Por isso ficam em dado (seed via migration), não em enum de código,
    permitindo adicionar uma classe nova sem deploy.
    """

    __tablename__ = "asset_classes"

    code: Mapped[str] = mapped_column(String(30), primary_key=True)  # ex.: STOCK_BR, ETF_US
    label: Mapped[str] = mapped_column(String(100), nullable=False)
