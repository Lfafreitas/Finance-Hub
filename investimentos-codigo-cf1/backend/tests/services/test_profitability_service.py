import uuid
from datetime import date
from decimal import Decimal

from app.domain.financial_engine.types import PositionResult, TransactionFact
from app.models.enums import TransactionType
from app.services.profitability_service import (
    ScopeAssetInput,
    compute_position_profitability,
    compute_scope_profitability,
)

ACCOUNT_ID = uuid.uuid4()
ASSET_ID = uuid.uuid4()


def fact(
    transaction_type,
    quantity=None,
    unit_price=None,
    fees=Decimal(0),
    gross_amount=Decimal(0),
    day=1,
    month=1,
    asset_id=None,
):
    return TransactionFact(
        id=uuid.uuid4(),
        account_id=ACCOUNT_ID,
        asset_id=asset_id or ASSET_ID,
        transaction_type=transaction_type,
        quantity=quantity,
        unit_price=unit_price,
        fees=fees,
        gross_amount=gross_amount,
        currency_code="BRL",
        transaction_date=date(2026, month, day),
    )


def make_position_result(**overrides) -> PositionResult:
    defaults = {
        "account_id": ACCOUNT_ID,
        "asset_id": ASSET_ID,
        "quantity": Decimal(0),
        "average_cost": Decimal(0),
        "total_cost_basis": Decimal(0),
        "realized_gain": Decimal(0),
        "dividends_received": Decimal(0),
        "realized_cost_basis": Decimal(0),
    }
    defaults.update(overrides)
    return PositionResult(**defaults)


class TestPosicaoAberta:
    def test_posicao_aberta_bloqueia_xirr_mas_permite_retorno_realizado(self):
        facts = [fact(TransactionType.BUY, quantity=Decimal(100), unit_price=Decimal(10), day=1)]
        position = make_position_result(
            quantity=Decimal(50), realized_gain=Decimal(50), realized_cost_basis=Decimal(500)
        )

        result = compute_position_profitability(facts, position)

        assert result.is_closed is False
        assert result.xirr is None
        assert result.cagr is None
        assert result.realized_return_pct == Decimal("0.1")  # 50/500
        assert "posição ainda aberta" in result.unavailable_reason


class TestPosicaoFechadaDuasDatas:
    def test_xirr_e_cagr_batem_no_caso_degenerado(self):
        facts = [
            fact(
                TransactionType.BUY, quantity=Decimal(100), unit_price=Decimal(10), day=1, month=1
            ),
            fact(
                TransactionType.SELL, quantity=Decimal(100), unit_price=Decimal(12), day=1, month=7
            ),
        ]
        position = make_position_result(
            quantity=Decimal(0), realized_gain=Decimal(200), realized_cost_basis=Decimal(1000)
        )

        result = compute_position_profitability(facts, position)

        assert result.is_closed is True
        assert result.xirr is not None
        assert result.cagr is not None
        assert abs(result.xirr - result.cagr) < Decimal("0.0001")
        assert result.realized_return_pct == Decimal("0.2")


class TestPosicaoFechadaTresDatas:
    def test_cagr_bloqueado_com_fluxo_intermediario_mas_xirr_calculado(self):
        facts = [
            fact(TransactionType.BUY, quantity=Decimal(50), unit_price=Decimal(10), day=1, month=1),
            fact(TransactionType.BUY, quantity=Decimal(50), unit_price=Decimal(12), day=1, month=3),
            fact(
                TransactionType.SELL, quantity=Decimal(100), unit_price=Decimal(15), day=1, month=7
            ),
        ]
        position = make_position_result(
            quantity=Decimal(0), realized_gain=Decimal(400), realized_cost_basis=Decimal(1100)
        )

        result = compute_position_profitability(facts, position)

        assert result.is_closed is True
        assert result.xirr is not None
        assert result.cagr is None  # 3 datas distintas -> CAGR não se aplica


class TestSemFluxoDeEntradaConhecido:
    def test_ativo_so_com_bonificacao_tem_xirr_indisponivel_mas_continua_fechado(self):
        """Regra 2 da autorização: quantidade final zero = fechado,
        independente de o XIRR em si ser calculável.
        """
        facts = [
            fact(TransactionType.BONUS_SHARES, quantity=Decimal(10), day=1, month=1),
            fact(TransactionType.SELL, quantity=Decimal(10), unit_price=Decimal(5), day=1, month=2),
        ]
        position = make_position_result(
            quantity=Decimal(0), realized_gain=Decimal(50), realized_cost_basis=Decimal(0)
        )

        result = compute_position_profitability(facts, position)

        assert result.is_closed is True  # continua fechado
        assert result.xirr is None
        assert "sem fluxo de entrada e saída" in result.unavailable_reason
        # custo realizado zero -> percentual indefinido, mas não crasha
        assert result.realized_return_pct is None
        assert "custo de aquisição realizado é zero" in result.unavailable_reason


class TestEscopoCombinado:
    def test_escopo_fechado_mesma_moeda_combina_fluxos(self):
        asset_2 = uuid.uuid4()
        facts_1 = [
            fact(
                TransactionType.BUY, quantity=Decimal(100), unit_price=Decimal(10), day=1, month=1
            ),
            fact(
                TransactionType.SELL, quantity=Decimal(100), unit_price=Decimal(12), day=1, month=6
            ),
        ]
        facts_2 = [
            fact(
                TransactionType.BUY,
                quantity=Decimal(50),
                unit_price=Decimal(20),
                day=1,
                month=2,
                asset_id=asset_2,
            ),
            fact(
                TransactionType.SELL,
                quantity=Decimal(50),
                unit_price=Decimal(22),
                day=1,
                month=6,
                asset_id=asset_2,
            ),
        ]
        position_1 = make_position_result(
            quantity=Decimal(0), realized_gain=Decimal(200), realized_cost_basis=Decimal(1000)
        )
        position_2 = make_position_result(
            asset_id=asset_2,
            quantity=Decimal(0),
            realized_gain=Decimal(100),
            realized_cost_basis=Decimal(1000),
        )

        inputs = [
            ScopeAssetInput(position=position_1, facts=facts_1, currency_code="BRL"),
            ScopeAssetInput(position=position_2, facts=facts_2, currency_code="BRL"),
        ]
        result = compute_scope_profitability(inputs)

        assert result.is_closed is True
        assert result.xirr is not None
        assert result.realized_return_pct == Decimal("0.15")  # (200+100)/(1000+1000)

    def test_escopo_com_posicao_aberta_bloqueia_xirr_do_escopo(self):
        facts_1 = [fact(TransactionType.BUY, quantity=Decimal(100), unit_price=Decimal(10), day=1)]
        position_1 = make_position_result(quantity=Decimal(100), realized_gain=Decimal(0))

        result = compute_scope_profitability(
            [ScopeAssetInput(position=position_1, facts=facts_1, currency_code="BRL")]
        )

        assert result.is_closed is False
        assert result.xirr is None
        assert "posição aberta" in result.unavailable_reason

    def test_escopo_com_moedas_diferentes_nao_combina_nem_inventa_fx(self):
        asset_usd = uuid.uuid4()
        facts_1 = [
            fact(
                TransactionType.BUY, quantity=Decimal(100), unit_price=Decimal(10), day=1, month=1
            ),
            fact(
                TransactionType.SELL, quantity=Decimal(100), unit_price=Decimal(12), day=1, month=6
            ),
        ]
        facts_2 = [
            fact(
                TransactionType.BUY,
                quantity=Decimal(10),
                unit_price=Decimal(100),
                day=1,
                month=1,
                asset_id=asset_usd,
            ),
            fact(
                TransactionType.SELL,
                quantity=Decimal(10),
                unit_price=Decimal(110),
                day=1,
                month=6,
                asset_id=asset_usd,
            ),
        ]
        position_1 = make_position_result(
            quantity=Decimal(0), realized_gain=Decimal(200), realized_cost_basis=Decimal(1000)
        )
        position_2 = make_position_result(
            asset_id=asset_usd,
            quantity=Decimal(0),
            realized_gain=Decimal(100),
            realized_cost_basis=Decimal(1000),
        )

        inputs = [
            ScopeAssetInput(position=position_1, facts=facts_1, currency_code="BRL"),
            ScopeAssetInput(position=position_2, facts=facts_2, currency_code="USD"),
        ]
        result = compute_scope_profitability(inputs)

        assert result.is_closed is True  # ambos fechados
        assert result.xirr is None  # mas não combina moeda diferente
        assert "moedas diferentes" in result.unavailable_reason
        # o retorno percentual agregado (que não depende de câmbio, só soma valores
        # já em suas próprias moedas) - aqui simplificado por serem valores nominais
        assert result.realized_return_pct is not None

    def test_escopo_vazio(self):
        result = compute_scope_profitability([])
        assert result.is_closed is True
        assert result.xirr is None
        assert result.realized_return_pct is None
        assert "sem posições" in result.unavailable_reason
