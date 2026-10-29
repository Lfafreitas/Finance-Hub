"""XIRR, CAGR e TWR — puros, sem I/O.

TWR usa a Convenção B, aprovada explicitamente: o fluxo externo de um
sub-período é tratado como ocorrendo IMEDIATAMENTE APÓS o valor medido
no fim do sub-período anterior — nunca como se tivesse ocorrido no fim
do sub-período anterior (isso distorceria a rentabilidade ao misturar
o efeito do aporte com o desempenho do período que já passou). Ver a
classe `TWRSubPeriod` para a semântica temporal completa, exigida
explicitamente antes da implementação.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from pyxirr import InvalidPaymentsError, xirr


@dataclass(frozen=True)
class CashFlow:
    """Um fluxo de caixa externo para fins de XIRR.

    Convenção de sinal: NEGATIVO quando dinheiro sai do bolso do
    investidor (aporte/compra inicial), POSITIVO quando volta
    (retirada, provento recebido em caixa, ou o valor de mercado final
    da posição na data de corte — este último fornecido por quem
    chama, nunca calculado aqui: ver decisão D3, o Financial Engine não
    busca cotação).
    """

    when: date
    amount: Decimal


class XIRRCalculator:
    @staticmethod
    def calculate(flows: list[CashFlow]) -> Decimal:
        """Levanta ValueError para entradas inválidas (regra 7:
        "validar entradas") e para ausência de convergência do solver
        (regra 7: "tratar ausência de solução"), em vez de deixar
        vazar uma exceção interna da biblioteca.
        """
        if len(flows) < 2:
            raise ValueError("XIRR requer ao menos 2 fluxos de caixa (um de saída, um de entrada)")

        amounts = [f.amount for f in flows]
        if all(a >= 0 for a in amounts) or all(a <= 0 for a in amounts):
            raise ValueError(
                "XIRR requer ao menos um fluxo negativo e um positivo "
                "(não é possível calcular retorno sem entrada E saída de caixa)"
            )

        dates = [f.when for f in flows]

        try:
            result = xirr(dates, [float(a) for a in amounts])
        except InvalidPaymentsError as exc:
            raise ValueError(f"XIRR: fluxos de caixa inválidos ({exc})") from exc

        if result is None:
            raise ValueError("XIRR: solver não convergiu para uma solução com estes fluxos")
        if not math.isfinite(result):
            # Todos os fluxos na MESMA data: não há período para
            # anualizar e o solver devolve infinito. Não é uma taxa.
            raise ValueError("XIRR: fluxos sem intervalo de tempo entre si — taxa indefinida")

        return Decimal(str(result))


class CAGRCalculator:
    @staticmethod
    def calculate(
        begin_value: Decimal, end_value: Decimal, begin_date: date, end_date: date
    ) -> Decimal:
        """Caso particular de retorno sem fluxo de caixa intermediário
        — usado quando não há aporte/retirada entre as duas datas.
        """
        if begin_value <= 0:
            raise ValueError("CAGR requer valor inicial positivo")
        if end_date <= begin_date:
            raise ValueError("CAGR requer end_date posterior a begin_date")

        days = (end_date - begin_date).days
        ratio = end_value / begin_value
        years = Decimal(days) / Decimal(365)
        # Decimal suporta potência com expoente fracionário nativamente
        # (usa o contexto de precisão) — nunca precisamos passar por
        # float, nem para essa etapa intermediária do cálculo.
        result = ratio ** (Decimal(1) / years) - 1
        return result


@dataclass(frozen=True)
class TWRSubPeriod:
    """Um sub-período do TWR, delimitado por um fluxo de caixa externo.

    SEMÂNTICA TEMPORAL (Convenção B, aprovada) — modelo conceitual de
    4 instantes ao redor de cada fluxo:

        (1) valor imediatamente ANTES do fluxo
                = `value_before_flow`
                = o valor no FIM do sub-período anterior (ou o capital
                  inicial, no primeiro sub-período de todos)
        (2) fluxo externo
                = `external_flow`
                = ocorre neste exato instante, entre (1) e (3)
        (3) valor imediatamente DEPOIS do fluxo
                = value_before_flow + external_flow (derivado, não é
                  um campo — é o começo "de fato" deste sub-período)
        (4) evolução até o próximo fluxo/data de avaliação
                = `value_at_period_end`
                = o valor no fim DESTE sub-período, já refletindo
                  desempenho de mercado desde (3)

    A rentabilidade deste sub-período isola o desempenho de mercado
    entre (3) e (4):

        r_i = value_at_period_end / (value_before_flow + external_flow) - 1

    Por isso o tamanho do fluxo nunca contamina r_i por si só — ele
    entra no denominador (a nova base de capital), não no numerador.

    CONVENÇÃO DE SINAL (diferente de `CashFlow`, usada no XIRR):
    `external_flow` é POSITIVO quando capital é ADICIONADO à carteira
    (aporte, ou TRANSFER_IN naquela conta) e NEGATIVO quando capital é
    REMOVIDO (retirada, ou TRANSFER_OUT naquela conta) — é a
    perspectiva da CARTEIRA ganhando/perdendo capital, o oposto da
    perspectiva do investidor usada no XIRR. Não confundir os dois.

    CASOS ESPECIAIS TRATADOS por `TWRCalculator.calculate`:

    - DEPOSIT: `external_flow` positivo no sub-período correspondente.
    - WITHDRAWAL: `external_flow` negativo.
    - Múltiplos fluxos na MESMA data: não há granularidade intradiária
      no domínio (`Transaction.transaction_date` é uma data, não um
      timestamp) — quem monta a lista de `TWRSubPeriod` deve somar
      algebricamente todos os fluxos daquela data em um único
      `external_flow` antes de chamar o calculador. O calculador NÃO
      tenta sequenciar fluxos do mesmo dia — não há como fazer isso
      sem inventar uma ordem arbitrária.
    - `external_flow = 0` é válido: sub-período sem nenhum aporte ou
      retirada (só passagem de tempo/avaliação).
    - Primeiro sub-período sem capital: `value_before_flow = 0` e o
      primeiro `external_flow` é o aporte inicial — cálculo normal,
      sem caso especial.
    - Retirada que ZERA a carteira: se
      `value_before_flow + external_flow == 0` E `value_at_period_end
      == 0`, o sub-período não tem capital para render nada — tratado
      como neutro (fator 1, ou seja, r_i = 0), não como erro.
    - Denominador zero em qualquer OUTRA situação (carteira zerada mas
      `value_at_period_end != 0`, ou uma base negativa): é uma
      inconsistência de dado, não um caso de negócio válido —
      `ValueError` explícito, nunca uma divisão silenciosa.
    - TRANSFER_IN/TRANSFER_OUT no PORTFOLIO CONSOLIDADO (regra já
      aprovada, reforçada aqui): uma transferência entre contas do
      mesmo usuário se cancela no agregado — NÃO deve virar
      `external_flow` na lista de sub-períodos usada para o TWR
      consolidado (não é aporte nem retirada externa, é movimentação
      interna). É responsabilidade de quem monta a lista (fora deste
      módulo) excluir essas transações ao calcular o TWR consolidado.
    - TRANSFER_IN/TRANSFER_OUT em uma ACCOUNT INDIVIDUAL: ali, sim,
      contam como `external_flow` normal daquela conta (dinheiro
      realmente entrou/saiu DAQUELA conta especificamente, mesmo que
      não tenha saído do usuário como um todo).
    """

    value_before_flow: Decimal
    external_flow: Decimal
    value_at_period_end: Decimal


class TWRCalculator:
    @staticmethod
    def calculate(sub_periods: list[TWRSubPeriod]) -> Decimal:
        if not sub_periods:
            raise ValueError("TWR requer ao menos um sub-período")

        factor = Decimal(1)
        for i, period in enumerate(sub_periods):
            base = period.value_before_flow + period.external_flow

            if base == 0:
                if period.value_at_period_end == 0:
                    # Carteira zerada por uma retirada total — sem
                    # capital, sem retorno a medir. Neutro, não é erro.
                    continue
                raise ValueError(
                    f"sub-período {i}: base de capital é zero (value_before_flow="
                    f"{period.value_before_flow}, external_flow={period.external_flow}) "
                    f"mas value_at_period_end={period.value_at_period_end} — "
                    "inconsistente (capital surgiu do nada)"
                )
            if base < 0:
                raise ValueError(
                    f"sub-período {i}: base de capital negativa ({base}) — "
                    "value_before_flow + external_flow não pode ser negativo"
                )

            r_i = period.value_at_period_end / base - 1
            factor *= 1 + r_i

        return factor - 1
