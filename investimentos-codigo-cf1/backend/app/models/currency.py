from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Currency(Base):
    """Tabela de referência de moedas (ISO 4217).

    Nota de escopo: o histórico de cotações de câmbio (FxRate) é uma
    entidade FUTURA (fase de Câmbio) e não é criada aqui. Esta tabela
    é apenas o cadastro mínimo de moedas — uma dependência necessária
    para Account/Asset/Transaction poderem declarar em qual moeda
    operam, o que já é exigido nesta fase (múltiplas moedas).
    """

    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)  # ex.: BRL, USD
    name: Mapped[str] = mapped_column(String(50), nullable=False)
