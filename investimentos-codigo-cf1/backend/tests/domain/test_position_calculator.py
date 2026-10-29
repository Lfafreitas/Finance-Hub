import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.domain.financial_engine.position import PositionCalculator
from app.domain.financial_engine.types import TransactionFact
from app.models.enums import TransactionType

ACCOUNT_ID = uuid.uuid4()
ASSET_ID = uuid.uuid4()


def fact(
    transaction_type,
    quantity=None,
    unit_price=None,
    fees=Decimal(0),
    gross_amount=Decimal(0),
    day=1,
):
    return TransactionFact(
        id=uuid.uuid4(),
        account_id=ACCOUNT_ID,
        asset_id=ASSET_ID,
        transaction_type=transaction_type,
        quantity=quantity,
        unit_price=unit_price,
        fees=fees,
        gross_amount=gross_amount,
        currency_code="BRL",
        transaction_date=date(2026, 1, day),
    )


class TestCompraSimples:
    def test_uma_compra_define_preco_medio_igual_ao_preco_pago_mais_taxas(self):
        facts = [
            fact(
                TransactionType.BUY, quantity=Decimal(100), unit_price=Decimal(10), fees=Decimal(2)
            )
        ]
        result = PositionCalculator.calculate(facts)

        assert result.quantity == Decimal(100)
        assert result.total_cost_basis == Decimal(1002)
        assert result.average_cost == Decimal("10.02")
        assert result.realized_gain == Decimal(0)


class TestComprasMultiplas:
    def test_duas_compras_precos_diferentes_pondera_corretamente(self):
        facts = [
            fact(
                TransactionType.BUY,
                quantity=Decimal(100),
                unit_price=Decimal(10),
                fees=Decimal(2),
                day=1,
            ),
            fact(
                TransactionType.BUY,
                quantity=Decimal(100),
                unit_price=Decimal(12),
                fees=Decimal(2),
                day=2,
            ),
        ]
        result = PositionCalculator.calculate(facts)

        assert result.quantity == Decimal(200)
        assert result.total_cost_basis == Decimal(2204)
        assert result.average_cost == Decimal("11.02")


class TestVendaParcial:
    def test_venda_parcial_calcula_ganho_realizado_e_preserva_preco_medio(self):
        facts = [
            fact(
                TransactionType.BUY,
                quantity=Decimal(100),
                unit_price=Decimal(10),
                fees=Decimal(2),
                day=1,
            ),
            fact(
                TransactionType.BUY,
                quantity=Decimal(100),
                unit_price=Decimal(12),
                fees=Decimal(2),
                day=2,
            ),
            fact(
                TransactionType.SELL,
                quantity=Decimal(50),
                unit_price=Decimal(15),
                fees=Decimal(1),
                day=3,
            ),
        ]
        result = PositionCalculator.calculate(facts)

        assert result.quantity == Decimal(150)
        assert result.realized_gain == Decimal("198.00")
        assert result.average_cost == Decimal("11.02")
        assert result.total_cost_basis == Decimal("1653.00")
        assert result.realized_cost_basis == Decimal("551.00")  # 50 x 11.02 (custo médio na venda)

    def test_venda_total_zera_quantidade(self):
        facts = [
            fact(
                TransactionType.BUY,
                quantity=Decimal(100),
                unit_price=Decimal(10),
                fees=Decimal(0),
                day=1,
            ),
            fact(
                TransactionType.SELL,
                quantity=Decimal(100),
                unit_price=Decimal(12),
                fees=Decimal(0),
                day=2,
            ),
        ]
        result = PositionCalculator.calculate(facts)

        assert result.quantity == Decimal(0)
        assert result.total_cost_basis == Decimal(0)
        assert result.realized_gain == Decimal(200)
        assert result.realized_cost_basis == Decimal(1000)  # 100 x 10 (custo médio único)

    def test_vender_mais_do_que_a_posicao_e_rejeitado(self):
        facts = [
            fact(TransactionType.BUY, quantity=Decimal(10), unit_price=Decimal(10), day=1),
            fact(TransactionType.SELL, quantity=Decimal(11), unit_price=Decimal(10), day=2),
        ]
        with pytest.raises(ValueError, match="só há"):
            PositionCalculator.calculate(facts)


class TestEventosSocietarios:
    def test_bonificacao_aumenta_quantidade_sem_alterar_custo_total(self):
        facts = [
            fact(TransactionType.BUY, quantity=Decimal(100), unit_price=Decimal(10), day=1),
            fact(TransactionType.BONUS_SHARES, quantity=Decimal(10), day=2),
        ]
        result = PositionCalculator.calculate(facts)

        assert result.quantity == Decimal(110)
        assert result.total_cost_basis == Decimal(1000)
        assert result.average_cost == pytest.approx(Decimal("9.0909090909"), abs=Decimal("0.0001"))

    def test_desdobramento_dobra_quantidade_e_reduz_preco_medio_pela_metade(self):
        facts = [
            fact(TransactionType.BUY, quantity=Decimal(100), unit_price=Decimal(10), day=1),
            fact(TransactionType.STOCK_SPLIT, quantity=Decimal(100), day=2),  # 2-for-1: +100
        ]
        result = PositionCalculator.calculate(facts)

        assert result.quantity == Decimal(200)
        assert result.total_cost_basis == Decimal(1000)
        assert result.average_cost == Decimal(5)

    def test_grupamento_reduz_quantidade_sem_alterar_custo_total(self):
        facts = [
            fact(TransactionType.BUY, quantity=Decimal(100), unit_price=Decimal(10), day=1),
            fact(TransactionType.REVERSE_SPLIT, quantity=Decimal(-90), day=2),  # 10-for-1
        ]
        result = PositionCalculator.calculate(facts)

        assert result.quantity == Decimal(10)
        assert result.total_cost_basis == Decimal(1000)
        assert result.average_cost == Decimal(100)


class TestProventos:
    def test_dividendo_nao_afeta_quantidade_nem_custo_mas_soma_proventos(self):
        facts = [
            fact(TransactionType.BUY, quantity=Decimal(100), unit_price=Decimal(10), day=1),
            fact(TransactionType.DIVIDEND, gross_amount=Decimal(50), day=2),
            fact(TransactionType.JCP, gross_amount=Decimal(20), fees=Decimal(3), day=3),
        ]
        result = PositionCalculator.calculate(facts)

        assert result.quantity == Decimal(100)
        assert result.total_cost_basis == Decimal(1000)
        assert result.dividends_received == Decimal(67)  # 50 + (20-3)


class TestTaxaAvulsa:
    def test_fee_avulsa_reduz_resultado_sem_afetar_posicao(self):
        facts = [
            fact(TransactionType.BUY, quantity=Decimal(100), unit_price=Decimal(10), day=1),
            fact(TransactionType.FEE, gross_amount=Decimal(15), day=2),
        ]
        result = PositionCalculator.calculate(facts)

        assert result.quantity == Decimal(100)
        assert result.realized_gain == Decimal(-15)


class TestPrecondicoes:
    def test_lista_vazia_e_rejeitada(self):
        with pytest.raises(ValueError, match="ao menos uma"):
            PositionCalculator.calculate([])

    def test_fact_sem_asset_id_e_rejeitada(self):
        f = fact(TransactionType.DEPOSIT, gross_amount=Decimal(100))
        f = TransactionFact(**{**f.__dict__, "asset_id": None})
        with pytest.raises(ValueError, match="asset_id"):
            PositionCalculator.calculate([f])

    def test_misturar_contas_diferentes_e_rejeitado(self):
        f1 = fact(TransactionType.BUY, quantity=Decimal(10), unit_price=Decimal(10), day=1)
        f2 = TransactionFact(
            **{
                **fact(
                    TransactionType.BUY, quantity=Decimal(10), unit_price=Decimal(10), day=2
                ).__dict__,
                "account_id": uuid.uuid4(),
            }
        )
        with pytest.raises(ValueError, match="mesmo"):
            PositionCalculator.calculate([f1, f2])


class TestLiquidacaoTotalSemResiduo:
    """`quantity * (cost_basis / quantity)` nem sempre devolve
    `cost_basis` em Decimal. Uma posição zerada precisa ficar com custo
    EXATAMENTE zero — nunca 1E-26, muito menos negativo.
    """

    def test_venda_total_com_custo_medio_dizima_zera_o_custo_exatamente(self):
        facts = [
            fact(
                TransactionType.BUY,
                quantity=Decimal(3),
                unit_price=Decimal(10),
                fees=Decimal(1),
                day=1,
            ),
            fact(TransactionType.SELL, quantity=Decimal(3), unit_price=Decimal(12), day=2),
        ]

        result = PositionCalculator.calculate(facts)

        assert result.quantity == 0
        assert result.total_cost_basis == 0
        assert str(result.total_cost_basis) == "0"
        assert result.realized_cost_basis == Decimal(31)
        assert result.realized_gain == Decimal(5)

    def test_vendas_parciais_ate_zerar_fecham_exatamente(self):
        facts = [
            fact(
                TransactionType.BUY,
                quantity=Decimal(7),
                unit_price=Decimal("13.37"),
                fees=Decimal("0.55"),
                day=1,
            ),
            fact(TransactionType.SELL, quantity=Decimal(3), unit_price=Decimal(12), day=2),
            fact(TransactionType.SELL, quantity=Decimal(4), unit_price=Decimal(12), day=3),
        ]

        result = PositionCalculator.calculate(facts)

        custo_total = Decimal(7) * Decimal("13.37") + Decimal("0.55")
        assert result.total_cost_basis == 0
        assert result.realized_cost_basis == custo_total
        assert result.realized_gain == Decimal(84) - custo_total

    def test_recompra_apos_zerar_comeca_de_custo_limpo(self):
        facts = [
            fact(
                TransactionType.BUY,
                quantity=Decimal(3),
                unit_price=Decimal(10),
                fees=Decimal(1),
                day=1,
            ),
            fact(TransactionType.SELL, quantity=Decimal(3), unit_price=Decimal(12), day=2),
            fact(TransactionType.BUY, quantity=Decimal(2), unit_price=Decimal(20), day=3),
        ]

        result = PositionCalculator.calculate(facts)

        assert result.total_cost_basis == Decimal(40)
        assert result.average_cost == Decimal(20)
