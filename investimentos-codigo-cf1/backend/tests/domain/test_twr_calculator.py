from decimal import Decimal

import pytest

from app.domain.financial_engine.performance import TWRCalculator, TWRSubPeriod


class TestExemploNumericoRevisado:
    def test_exemplo_aprovado_1000_1100_aporte_500_1600_1700(self):
        """R$1.000 -> R$1.100 (sem fluxo); aporta R$500 (fica R$1.600
        imediatamente); R$1.600 -> R$1.700. TWR esperado = 16,875%.
        """
        sub_periods = [
            TWRSubPeriod(
                value_before_flow=Decimal(1000),
                external_flow=Decimal(0),
                value_at_period_end=Decimal(1100),
            ),
            TWRSubPeriod(
                value_before_flow=Decimal(1100),
                external_flow=Decimal(500),
                value_at_period_end=Decimal(1700),
            ),
        ]
        result = TWRCalculator.calculate(sub_periods)
        assert result == pytest.approx(Decimal("0.16875"), abs=Decimal("0.00001"))


class TestTamanhoDoAporteNaoContaminaRetorno:
    def test_aporte_maior_ou_menor_nao_muda_a_taxa_do_subperiodo_isolado(self):
        """O tamanho do fluxo só deve afetar a BASE (denominador), nunca
        a taxa de retorno de mercado medida depois dele — desde que o
        crescimento percentual do sub-período seja o mesmo.
        """
        pequeno = TWRSubPeriod(
            value_before_flow=Decimal(1000),
            external_flow=Decimal(100),
            value_at_period_end=Decimal(1100) * Decimal("1.10"),  # +10% sobre a base de 1100
        )
        grande = TWRSubPeriod(
            value_before_flow=Decimal(1000),
            external_flow=Decimal(9000),
            value_at_period_end=Decimal(10000) * Decimal("1.10"),  # +10% sobre a base de 10000
        )

        r_pequeno = TWRCalculator.calculate([pequeno])
        r_grande = TWRCalculator.calculate([grande])

        assert r_pequeno == pytest.approx(Decimal("0.10"), abs=Decimal("0.0001"))
        assert r_grande == pytest.approx(Decimal("0.10"), abs=Decimal("0.0001"))
        assert r_pequeno == pytest.approx(r_grande, abs=Decimal("0.0001"))


class TestAportesRetiradasEmDatasDiferentes:
    def test_retirada_no_meio_do_periodo(self):
        # 1000 -> 1200 (sub 1, +20%); retira 300 (base=900); 900 -> 990 (sub 2, +10%)
        sub_periods = [
            TWRSubPeriod(Decimal(1000), Decimal(0), Decimal(1200)),
            TWRSubPeriod(Decimal(1200), Decimal(-300), Decimal(990)),
        ]
        result = TWRCalculator.calculate(sub_periods)
        expected = (Decimal("1.20") * Decimal("1.10")) - 1
        assert result == pytest.approx(expected, abs=Decimal("0.0001"))


class TestMultiplosFluxos:
    def test_tres_subperiodos_com_aporte_e_retirada(self):
        sub_periods = [
            TWRSubPeriod(Decimal(1000), Decimal(0), Decimal(1100)),  # +10%
            TWRSubPeriod(
                Decimal(1100), Decimal(500), Decimal(1440)
            ),  # base 1600, +(-10%)? -> 1440/1600=0.9
            TWRSubPeriod(Decimal(1440), Decimal(-200), Decimal(1364)),  # base 1240, 1364/1240=1.10
        ]
        result = TWRCalculator.calculate(sub_periods)
        expected = (Decimal("1.10") * Decimal("0.90") * Decimal("1.10")) - 1
        assert result == pytest.approx(expected, abs=Decimal("0.0001"))


class TestCasosEspeciais:
    def test_fluxo_zero_e_valido(self):
        sub_periods = [TWRSubPeriod(Decimal(1000), Decimal(0), Decimal(1050))]
        result = TWRCalculator.calculate(sub_periods)
        assert result == pytest.approx(Decimal("0.05"), abs=Decimal("0.0001"))

    def test_primeiro_periodo_sem_capital_inicial(self):
        # Carteira começa em zero; primeiro fluxo é o aporte inicial.
        sub_periods = [TWRSubPeriod(Decimal(0), Decimal(1000), Decimal(1100))]
        result = TWRCalculator.calculate(sub_periods)
        assert result == pytest.approx(Decimal("0.10"), abs=Decimal("0.0001"))

    def test_retirada_total_zera_carteira_e_e_tratada_como_neutra(self):
        sub_periods = [
            TWRSubPeriod(Decimal(1000), Decimal(0), Decimal(1100)),
            TWRSubPeriod(Decimal(1100), Decimal(-1100), Decimal(0)),  # zera tudo
        ]
        result = TWRCalculator.calculate(sub_periods)
        # sub-período 2 é neutro (fator 1) — resultado = só o sub-período 1
        assert result == pytest.approx(Decimal("0.10"), abs=Decimal("0.0001"))

    def test_base_zero_com_valor_final_nao_zero_e_erro(self):
        sub_periods = [TWRSubPeriod(Decimal(1000), Decimal(-1000), Decimal(50))]
        with pytest.raises(ValueError, match="inconsistente"):
            TWRCalculator.calculate(sub_periods)

    def test_base_negativa_e_erro(self):
        sub_periods = [TWRSubPeriod(Decimal(100), Decimal(-500), Decimal(0))]
        with pytest.raises(ValueError, match="negativa"):
            TWRCalculator.calculate(sub_periods)

    def test_lista_vazia_e_erro(self):
        with pytest.raises(ValueError, match="ao menos um"):
            TWRCalculator.calculate([])


class TestTransferenciasSemDuplaContagem:
    def test_transferencia_interna_excluida_do_consolidado_nao_distorce_twr(self):
        """No PORTFOLIO CONSOLIDADO, uma transferência entre contas do
        mesmo usuário não deve entrar como external_flow — quem monta
        a lista de sub-períodos já a exclui. Este teste prova que,
        seguindo essa regra, uma transferência interna não aparece
        como aporte/retirada artificial no TWR consolidado.
        """
        # Sem a transferência (visão consolidada correta): patrimônio total
        # não muda por causa da transferência interna, só a composição.
        sub_periods_consolidado = [
            TWRSubPeriod(Decimal(1000), Decimal(0), Decimal(1050)),  # +5%, sem fluxo
        ]
        result = TWRCalculator.calculate(sub_periods_consolidado)
        assert result == pytest.approx(Decimal("0.05"), abs=Decimal("0.0001"))

    def test_transferencia_conta_individual_conta_como_fluxo_externo_daquela_conta(self):
        """Na CONTA INDIVIDUAL (origem da transferência), o mesmo evento
        conta como saída de capital — external_flow negativo.
        """
        # Conta perde R$300 de patrimônio só pela saída (TRANSFER_OUT),
        # sem nenhum desempenho de mercado embutido.
        sub_periods_conta_origem = [
            TWRSubPeriod(Decimal(1000), Decimal(-300), Decimal(700)),
        ]
        result = TWRCalculator.calculate(sub_periods_conta_origem)
        assert result == pytest.approx(Decimal(0), abs=Decimal("0.0001"))
