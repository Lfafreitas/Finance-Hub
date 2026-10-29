"""CF-2: motor de regras e quebra por categoria (puros)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.domain.cashflow_engine import (
    CashEntryFact,
    CashflowSummaryCalculator,
    CategoryBreakdownCalculator,
    RuleSpec,
    RuleTarget,
    first_matching_rule,
    rule_matches,
)
from app.models.enums import (
    AccountType,
    CashflowNature,
    RuleDirection,
    RuleMatchType,
)

ACCOUNT = uuid.uuid4()
OTHER_ACCOUNT = uuid.uuid4()
CATEGORY = uuid.uuid4()
N = CashflowNature


def rule(pattern, *, priority=100, order=0, match_type=RuleMatchType.CONTAINS, **kwargs):
    kwargs.setdefault("set_category_id", CATEGORY)
    return RuleSpec(
        rule_id=uuid.uuid4(),
        priority=priority,
        order=order,
        match_type=match_type,
        pattern=pattern,
        **kwargs,
    )


def target(text, amount="-10", account=ACCOUNT):
    return RuleTarget(match_text=text, amount=Decimal(amount), account_id=account)


class TestRuleMatches:
    def test_contains_ignora_caixa_e_acento_nos_dois_lados(self):
        assert rule_matches(rule("SPOTIFY"), target("spotify"))
        assert rule_matches(rule("débito"), target("compra no debito super central"))
        assert rule_matches(rule("  uber  "), target("uber uber trip help.u"))

    def test_contains_nao_casa_texto_diferente(self):
        assert not rule_matches(rule("spotify"), target("amazon br iv"))

    def test_equals_exige_o_texto_inteiro(self):
        exact = rule("pagamento de fatura", match_type=RuleMatchType.EQUALS)

        assert rule_matches(exact, target("pagamento de fatura"))
        assert not rule_matches(exact, target("pagamento de fatura atrasada"))

    def test_starts_with(self):
        starts = rule("99food", match_type=RuleMatchType.STARTS_WITH)

        assert rule_matches(starts, target("99food loja exemplo"))
        assert not rule_matches(starts, target("transferencia enviada pelo pix 99food"))

    def test_direcao_separa_entrada_de_saida(self):
        only_in = rule("fulano", direction=RuleDirection.IN)
        only_out = rule("fulano", direction=RuleDirection.OUT)

        assert rule_matches(only_in, target("fulano", "50"))
        assert not rule_matches(only_in, target("fulano", "-50"))
        assert rule_matches(only_out, target("fulano", "-50"))
        assert not rule_matches(only_out, target("fulano", "50"))

    def test_regra_de_uma_conta_nao_casa_em_outra(self):
        scoped = rule("uber", account_id=ACCOUNT)

        assert rule_matches(scoped, target("uber"))
        assert not rule_matches(scoped, target("uber", account=OTHER_ACCOUNT))


class TestPrimeiraRegraDecide:
    def test_menor_prioridade_vence(self):
        general = rule("amazon", priority=100)
        specific = rule("amazon br vi", priority=10)

        chosen = first_matching_rule([general, specific], target("amazon br vi"))

        assert chosen is specific

    def test_empate_de_prioridade_vence_a_criada_antes(self):
        first = rule("uber", priority=50, order=1)
        second = rule("uber", priority=50, order=2)

        assert first_matching_rule([second, first], target("uber uber trip")) is first

    def test_regra_que_nao_casa_e_pulada(self):
        miss = rule("spotify", priority=1)
        hit = rule("uber", priority=99)

        assert first_matching_rule([miss, hit], target("uber uber trip")) is hit

    def test_nenhuma_regra_casa(self):
        assert first_matching_rule([rule("spotify")], target("amazon")) is None
        assert first_matching_rule([], target("amazon")) is None


class TestRegraInvalida:
    def test_padrao_vazio(self):
        with pytest.raises(ValueError, match="vazio"):
            rule("   ")

    def test_regra_nao_classifica_como_transferencia(self):
        with pytest.raises(ValueError, match="transferência"):
            rule("x", set_nature=N.TRANSFER)

    def test_regra_nao_classifica_como_nao_classificado(self):
        with pytest.raises(ValueError, match="natureza"):
            rule("x", set_nature=N.UNCLASSIFIED)

    def test_regra_so_com_natureza_e_valida(self):
        assert rule("x", set_category_id=None, set_nature=N.INCOME).set_nature is N.INCOME


FOOD = uuid.uuid4()
MARKET = uuid.uuid4()
RESTAURANT = uuid.uuid4()
TRANSPORT = uuid.uuid4()
SALARY = uuid.uuid4()
TREE = {FOOD: None, MARKET: FOOD, RESTAURANT: FOOD, TRANSPORT: None, SALARY: None}
JAN = (date(2026, 1, 1), date(2026, 1, 31))


def fact(amount, nature, category=None, day=10, currency="BRL", counterparty=None, month=1):
    return CashEntryFact(
        account_id=ACCOUNT,
        account_type=AccountType.CHECKING,
        currency_code=currency,
        entry_date=date(2026, month, day),
        amount=Decimal(amount),
        nature=nature,
        counterparty_account_type=counterparty,
        category_id=category,
    )


def _facts():
    return [
        fact("3000", N.INCOME, SALARY),
        fact("-200", N.EXPENSE, MARKET),
        fact("-150", N.EXPENSE, RESTAURANT),
        fact("-30", N.EXPENSE, FOOD),
        fact("40", N.EXPENSE, RESTAURANT),  # estorno
        fact("-90", N.EXPENSE, TRANSPORT),
        fact("-12.90", N.EXPENSE),
        fact("100", N.INCOME),
        fact("-500", N.THIRD_PARTY),
        fact("-700", N.TRANSFER, counterparty=AccountType.BROKERAGE),
        fact("-999", N.UNCLASSIFIED),
    ]


class TestQuebraPorCategoria:
    def _by_category(self):
        rows = CategoryBreakdownCalculator.calculate(_facts(), *JAN, TREE)["BRL"]
        return {row.category_id: row for row in rows}

    def test_subcategoria_tem_proprio_igual_ao_total(self):
        rows = self._by_category()

        assert (rows[MARKET].own_expenses, rows[MARKET].total_expenses) == (
            Decimal(200),
            Decimal(200),
        )
        assert rows[RESTAURANT].own_expenses == Decimal(110)

    def test_categoria_pai_soma_as_filhas_ao_que_e_dela(self):
        rows = self._by_category()

        assert rows[FOOD].own_expenses == Decimal(30)
        assert rows[FOOD].total_expenses == Decimal(340)

    def test_sem_categoria_e_uma_linha_propria(self):
        rows = self._by_category()

        assert rows[None].own_expenses == Decimal("12.90")
        assert rows[None].own_income == Decimal(100)

    def test_renda_e_gasto_nao_se_misturam(self):
        rows = self._by_category()

        assert (rows[SALARY].own_income, rows[SALARY].own_expenses) == (Decimal(3000), Decimal(0))
        assert rows[TRANSPORT].own_income == Decimal(0)

    def test_terceiros_transferencia_e_nao_classificado_ficam_fora(self):
        rows = CategoryBreakdownCalculator.calculate(_facts(), *JAN, TREE)["BRL"]

        assert sum(row.own_expenses for row in rows) == Decimal("442.90")
        assert sum(row.own_income for row in rows) == Decimal(3100)

    def test_soma_das_linhas_e_o_gasto_e_a_renda_do_resumo(self):
        rows = CategoryBreakdownCalculator.calculate(_facts(), *JAN, TREE)["BRL"]
        summary = CashflowSummaryCalculator.calculate(_facts(), *JAN)["BRL"]

        assert sum(row.own_expenses for row in rows) == summary.expenses
        assert sum(row.own_income for row in rows) == summary.income

    def test_pai_sem_lancamento_proprio_aparece_pelo_total_das_filhas(self):
        facts = [fact("-80", N.EXPENSE, MARKET)]

        rows = {
            r.category_id: r
            for r in CategoryBreakdownCalculator.calculate(facts, *JAN, TREE)["BRL"]
        }

        assert (rows[FOOD].own_expenses, rows[FOOD].total_expenses) == (Decimal(0), Decimal(80))

    def test_fora_do_periodo_nao_entra(self):
        facts = [fact("-80", N.EXPENSE, MARKET), fact("-999", N.EXPENSE, MARKET, month=2)]

        rows = CategoryBreakdownCalculator.calculate(facts, *JAN, TREE)["BRL"]

        assert sum(row.own_expenses for row in rows) == Decimal(80)

    def test_moedas_ficam_separadas(self):
        facts = [fact("-80", N.EXPENSE, MARKET), fact("-7", N.EXPENSE, MARKET, currency="USD")]

        result = CategoryBreakdownCalculator.calculate(facts, *JAN, TREE)

        assert list(result) == ["BRL", "USD"]
        assert {r.category_id: r.total_expenses for r in result["USD"]}[FOOD] == Decimal(7)

    def test_categoria_desconhecida_e_erro(self):
        with pytest.raises(ValueError, match="desconhecida"):
            CategoryBreakdownCalculator.calculate([fact("-1", N.EXPENSE, uuid.uuid4())], *JAN, TREE)

    def test_transferencia_com_categoria_e_fato_invalido(self):
        with pytest.raises(ValueError, match="categoria"):
            fact("-1", N.TRANSFER, MARKET, counterparty=AccountType.SAVINGS)
