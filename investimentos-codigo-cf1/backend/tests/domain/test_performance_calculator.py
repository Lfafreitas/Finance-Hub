from datetime import date
from decimal import Decimal

import pytest

from app.domain.financial_engine.performance import CAGRCalculator, CashFlow, XIRRCalculator


class TestXIRR:
    def test_um_aporte_e_um_resgate_bate_com_cagr_equivalente(self):
        flows = [
            CashFlow(when=date(2026, 1, 1), amount=Decimal(-10000)),
            CashFlow(when=date(2026, 7, 1), amount=Decimal(10800)),
        ]
        xirr_result = XIRRCalculator.calculate(flows)
        cagr_result = CAGRCalculator.calculate(
            begin_value=Decimal(10000),
            end_value=Decimal(10800),
            begin_date=date(2026, 1, 1),
            end_date=date(2026, 7, 1),
        )

        assert xirr_result == pytest.approx(cagr_result, abs=Decimal("0.0001"))

    def test_multiplos_fluxos_em_datas_irregulares(self):
        flows = [
            CashFlow(when=date(2026, 1, 1), amount=Decimal(-10000)),
            CashFlow(when=date(2026, 3, 15), amount=Decimal(-2000)),
            CashFlow(when=date(2026, 8, 10), amount=Decimal(500)),
            CashFlow(when=date(2026, 12, 31), amount=Decimal(13200)),
        ]
        result = XIRRCalculator.calculate(flows)
        assert result > Decimal(0)  # cenário com ganho — só confirma que converge e é plausível

    def test_menos_de_dois_fluxos_e_rejeitado(self):
        with pytest.raises(ValueError, match="ao menos 2"):
            XIRRCalculator.calculate([CashFlow(when=date(2026, 1, 1), amount=Decimal(-100))])

    def test_todos_fluxos_negativos_e_rejeitado(self):
        flows = [
            CashFlow(when=date(2026, 1, 1), amount=Decimal(-100)),
            CashFlow(when=date(2026, 6, 1), amount=Decimal(-50)),
        ]
        with pytest.raises(ValueError, match="fluxo negativo e um positivo"):
            XIRRCalculator.calculate(flows)

    def test_todos_fluxos_positivos_e_rejeitado(self):
        flows = [
            CashFlow(when=date(2026, 1, 1), amount=Decimal(100)),
            CashFlow(when=date(2026, 6, 1), amount=Decimal(50)),
        ]
        with pytest.raises(ValueError, match="fluxo negativo e um positivo"):
            XIRRCalculator.calculate(flows)


class TestCAGR:
    def test_crescimento_um_ano_e_direto(self):
        result = CAGRCalculator.calculate(
            begin_value=Decimal(1000),
            end_value=Decimal(1100),
            begin_date=date(2025, 1, 1),
            end_date=date(2026, 1, 1),
        )
        assert result == pytest.approx(Decimal("0.1"), abs=Decimal("0.005"))

    def test_valor_inicial_zero_ou_negativo_e_rejeitado(self):
        with pytest.raises(ValueError, match="valor inicial positivo"):
            CAGRCalculator.calculate(
                begin_value=Decimal(0),
                end_value=Decimal(100),
                begin_date=date(2026, 1, 1),
                end_date=date(2026, 6, 1),
            )

    def test_data_final_antes_da_inicial_e_rejeitada(self):
        with pytest.raises(ValueError, match="posterior"):
            CAGRCalculator.calculate(
                begin_value=Decimal(100),
                end_value=Decimal(110),
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 1, 1),
            )


class TestXirrSemIntervaloDeTempo:
    def test_todos_os_fluxos_na_mesma_data_nao_tem_taxa(self):
        """Compra e venda no mesmo dia: o solver devolve infinito. Isso
        não é uma taxa e não pode sair da API como "Infinity".
        """
        flows = [
            CashFlow(when=date(2026, 1, 5), amount=Decimal(-100)),
            CashFlow(when=date(2026, 1, 5), amount=Decimal(110)),
        ]

        with pytest.raises(ValueError, match="sem intervalo de tempo"):
            XIRRCalculator.calculate(flows)
