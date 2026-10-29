from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BenchmarkRate(Base):
    """Taxa diária de uma referência pública (hoje só o CDI, série 12 do
    Banco Central), em % ao dia como a fonte publica. Não pertence a
    usuário: é dado de mercado.
    """

    __tablename__ = "benchmark_rates"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    rate_date: Mapped[date] = mapped_column(Date, primary_key=True)
    daily_rate: Mapped[Decimal] = mapped_column(Numeric(14, 10), nullable=False)
