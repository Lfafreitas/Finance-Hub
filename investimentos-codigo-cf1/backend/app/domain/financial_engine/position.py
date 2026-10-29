"""PositionCalculator — cálculo de posição e preço médio.

Método: custo médio ponderado (decisão D5, aprovada), uniforme para
ativos BR e exterior. Nunca FIFO. Regras tributárias específicas (ex.:
FIFO exigido pelo IRS em certos casos) são responsabilidade de um
futuro Tax Engine, não deste módulo.

Convenção adotada para eventos societários (BONUS_SHARES, STOCK_SPLIT,
REVERSE_SPLIT) — não havia uma regra financeira pronta para isso no
material aprovado, então documento aqui a convenção de representação
de dado que estou assumindo, sem inventar fórmula nova:

    `quantity` representa a VARIAÇÃO de quantidade do evento (positiva
    para bonificação/desdobramento, negativa para grupamento/reverse
    split). `unit_price`/`fees` não se aplicam a esses tipos (devem
    vir None/0) porque nenhum dinheiro muda de mãos. O custo total da
    posição não muda — só é redistribuído pela nova quantidade.

Nenhum cálculo aqui considera transações REVERSED: essa exclusão é
feita antes, na camada de acesso a dado (ver `types.py`).
"""

from __future__ import annotations

from decimal import Decimal

from app.domain.financial_engine.types import PositionResult, TransactionFact
from app.models.enums import TransactionType

_PROCEEDS_ONLY_TYPES = {
    TransactionType.DIVIDEND,
    TransactionType.JCP,
    TransactionType.INCOME,
}


class PositionCalculator:
    @staticmethod
    def calculate(facts: list[TransactionFact]) -> PositionResult:
        """Pré-condições: todas as `facts` pertencem ao MESMO
        (account_id, asset_id); nenhuma tem `asset_id` None; já vêm
        ordenadas cronologicamente pelo chamador.
        """
        if not facts:
            raise ValueError("PositionCalculator.calculate requer ao menos uma transação")

        account_id = facts[0].account_id
        asset_id = facts[0].asset_id
        if asset_id is None:
            raise ValueError("PositionCalculator não processa transações sem asset_id")

        quantity = Decimal(0)
        cost_basis = Decimal(0)
        realized_gain = Decimal(0)
        dividends_received = Decimal(0)
        realized_cost_basis = Decimal(0)

        for fact in facts:
            if fact.account_id != account_id or fact.asset_id != asset_id:
                raise ValueError("todas as facts devem pertencer ao mesmo (account_id, asset_id)")

            if fact.transaction_type == TransactionType.BUY:
                if fact.quantity is None or fact.unit_price is None:
                    raise ValueError(f"BUY {fact.id} sem quantity/unit_price")
                quantity += fact.quantity
                cost_basis += fact.quantity * fact.unit_price + fact.fees

            elif fact.transaction_type == TransactionType.SELL:
                if fact.quantity is None or fact.unit_price is None:
                    raise ValueError(f"SELL {fact.id} sem quantity/unit_price")
                if fact.quantity > quantity:
                    raise ValueError(
                        f"SELL {fact.id} vende {fact.quantity} mas só há {quantity} em posição"
                    )
                average_cost = (cost_basis / quantity) if quantity > 0 else Decimal(0)
                net_proceeds = fact.quantity * fact.unit_price - fact.fees
                if fact.quantity == quantity:
                    # Venda que ZERA a posição: remove exatamente TODO o
                    # custo remanescente. `quantity * (cost_basis /
                    # quantity)` nem sempre devolve `cost_basis` em
                    # Decimal (a divisão é arredondada na precisão do
                    # contexto) e deixaria um resíduo como 1E-26 — ou
                    # NEGATIVO — de custo numa posição sem nenhuma
                    # unidade. A regra é a mesma (custo médio
                    # ponderado); só o arredondamento é eliminado.
                    cost_removed = cost_basis
                else:
                    cost_removed = fact.quantity * average_cost
                realized_gain += net_proceeds - cost_removed
                realized_cost_basis += cost_removed
                cost_basis -= cost_removed
                quantity -= fact.quantity

            elif fact.transaction_type in (
                TransactionType.BONUS_SHARES,
                TransactionType.STOCK_SPLIT,
                TransactionType.REVERSE_SPLIT,
            ):
                if fact.quantity is None:
                    raise ValueError(f"{fact.transaction_type} {fact.id} sem quantity")
                new_quantity = quantity + fact.quantity
                if new_quantity < 0:
                    raise ValueError(
                        f"{fact.transaction_type} {fact.id} resultaria em quantidade negativa"
                    )
                quantity = new_quantity
                # custo total não muda — só é redistribuído (average
                # recalculado implicitamente pela razão cost_basis/quantity
                # no PositionResult final).

            elif fact.transaction_type in _PROCEEDS_ONLY_TYPES:
                dividends_received += fact.gross_amount - fact.fees

            elif fact.transaction_type == TransactionType.FEE:
                # Taxa avulsa não ligada a uma compra/venda específica
                # (ex.: custódia): reduz o resultado, não a posição.
                realized_gain -= fact.gross_amount + fact.fees

            else:
                raise ValueError(
                    f"PositionCalculator não sabe processar {fact.transaction_type} "
                    f"(fact {fact.id}) — tipo não afeta posição de ativo ou não "
                    "deveria aparecer numa lista filtrada por asset_id"
                )

        average_cost = (cost_basis / quantity) if quantity > 0 else Decimal(0)

        return PositionResult(
            account_id=account_id,
            asset_id=asset_id,
            quantity=quantity,
            average_cost=average_cost,
            total_cost_basis=cost_basis,
            realized_gain=realized_gain,
            dividends_received=dividends_received,
            realized_cost_basis=realized_cost_basis,
        )
