"""Visual-1: regras de "onde dá para melhorar"."""

from datetime import date
from decimal import Decimal

from app.domain.cashflow_engine.insights import SpendFact, spending_insights


def _spend(day, amount, cat="food", label="Alimentação", text="mercado exemplo", expense=True):
    return SpendFact(
        entry_date=day,
        amount=Decimal(str(-amount)),
        expense=expense,
        category_key=cat,
        category_label=label,
        match_text=text,
    )


def _history(amount_per_month, cat="food", label="Alimentação", text="mercado exemplo"):
    return [_spend(date(2026, m, 10), amount_per_month, cat, label, text) for m in (7, 8, 9)]


class TestAcimaDoNormal:
    def test_categoria_que_subiu_20_e_50_acima_da_media(self):
        facts = _history(300) + [_spend(date(2026, 10, 5), 400)]

        result = spending_insights(facts, 2026, 10)

        (change,) = result.above_normal
        assert (change.key, change.label) == ("food", "Alimentação")
        assert (change.current, change.average, change.difference) == (
            Decimal("400.00"),
            Decimal("300.00"),
            Decimal("100.00"),
        )
        assert result.history_months == 3

    def test_subida_pequena_em_valor_nao_conta(self):
        facts = _history(100) + [_spend(date(2026, 10, 5), 149.99)]

        assert spending_insights(facts, 2026, 10).above_normal == ()

    def test_subida_pequena_em_proporcao_nao_conta(self):
        facts = _history(1000) + [_spend(date(2026, 10, 5), 1199)]

        assert spending_insights(facts, 2026, 10).above_normal == ()

    def test_exatamente_no_limite_conta(self):
        facts = _history(250) + [_spend(date(2026, 10, 5), 300)]

        assert len(spending_insights(facts, 2026, 10).above_normal) == 1

    def test_media_inclui_mes_sem_gasto_na_categoria(self):
        facts = [
            _spend(date(2026, 8, 10), 300),
            _spend(date(2026, 9, 10), 300),
            _spend(date(2026, 7, 10), 50, cat="home", label="Moradia", text="aluguel"),
            _spend(date(2026, 10, 5), 300),
        ]

        (change,) = spending_insights(facts, 2026, 10).above_normal
        assert change.average == Decimal("200.00")

    def test_sem_categoria_com_historico_tambem_nao_e_comparado(self):
        facts = _history(100, cat=None, label=None) + [
            _spend(date(2026, 10, 5), 900, cat=None, label=None)
        ]

        assert spending_insights(facts, 2026, 10).above_normal == ()

    def test_menos_de_2_meses_de_historico_nao_compara(self):
        facts = [_spend(date(2026, 9, 10), 100), _spend(date(2026, 10, 5), 900)]

        result = spending_insights(facts, 2026, 10)

        assert result.history_months == 1
        assert result.above_normal == ()

    def test_sem_categoria_nao_e_comparado_e_categoria_nova_tambem_nao(self):
        facts = _history(300) + [
            _spend(date(2026, 10, 5), 900, cat=None, label=None),
            _spend(date(2026, 10, 6), 900, cat="trip", label="Viagem", text="hotel"),
        ]

        assert spending_insights(facts, 2026, 10).above_normal == ()

    def test_no_maximo_3_e_maior_diferenca_primeiro(self):
        facts = []
        for i, extra in enumerate([100, 400, 200, 300]):
            facts += _history(500, cat=f"c{i}", label=f"Cat {i}", text=f"t{i}")
            facts.append(
                _spend(date(2026, 10, 5), 500 + extra, cat=f"c{i}", label=f"Cat {i}", text=f"t{i}")
            )

        result = spending_insights(facts, 2026, 10)

        assert [c.label for c in result.above_normal] == ["Cat 1", "Cat 3", "Cat 2"]

    def test_mes_de_janeiro_olha_o_ano_anterior(self):
        facts = [_spend(date(2025, m, 10), 100) for m in (10, 11, 12)] + [
            _spend(date(2026, 1, 5), 300)
        ]

        (change,) = spending_insights(facts, 2026, 1).above_normal
        assert change.average == Decimal("100.00")


class TestRecorrentes:
    def test_mesmo_texto_nos_3_ultimos_meses(self):
        facts = [
            _spend(date(2026, m, 13), 12.9, cat="sub", label="Assinaturas", text="spotify")
            for m in (8, 9, 10)
        ] + [_spend(date(2026, 10, 2), 99, text="farmacia")]

        result = spending_insights(facts, 2026, 10)

        assert [(r.label, r.monthly_average) for r in result.recurring] == [
            ("spotify", Decimal("12.90"))
        ]
        assert result.recurring_total == Decimal("12.90")

    def test_faltando_um_mes_nao_e_recorrente(self):
        facts = [_spend(date(2026, m, 13), 12.9, text="spotify") for m in (7, 8, 10)]

        assert spending_insights(facts, 2026, 10).recurring == ()

    def test_media_de_valores_diferentes_e_ordem_pelo_maior(self):
        facts = [
            _spend(date(2026, 8, 1), 100, text="luz"),
            _spend(date(2026, 9, 1), 130, text="luz"),
            _spend(date(2026, 10, 1), 160, text="luz"),
            *[_spend(date(2026, m, 1), 50, text="internet") for m in (8, 9, 10)],
        ]

        result = spending_insights(facts, 2026, 10)

        assert [(r.label, r.monthly_average) for r in result.recurring] == [
            ("luz", Decimal("130.00")),
            ("internet", Decimal("50.00")),
        ]
        assert result.recurring_total == Decimal("180.00")


class TestPequenosEConcentracao:
    def test_cinco_ou_mais_gastos_pequenos_no_mes(self):
        facts = [_spend(date(2026, 10, d), 20, text=f"cafe {d}") for d in range(1, 6)]
        facts.append(_spend(date(2026, 10, 9), 30, text="exatamente o limite"))
        facts.append(_spend(date(2026, 9, 9), 10, text="mes anterior"))

        result = spending_insights(facts, 2026, 10)

        assert (result.small_count, result.small_total) == (5, Decimal("100.00"))

    def test_quatro_gastos_pequenos_nao_viram_alerta(self):
        facts = [_spend(date(2026, 10, d), 20, text=f"cafe {d}") for d in range(1, 5)]

        result = spending_insights(facts, 2026, 10)

        assert (result.small_count, result.small_total) == (0, Decimal("0.00"))

    def test_tres_maiores_categorias_e_quanto_somam(self):
        facts = [
            _spend(date(2026, 10, 1), 500, cat="home", label="Moradia"),
            _spend(date(2026, 10, 2), 300, cat="food", label="Alimentação"),
            _spend(date(2026, 10, 3), 100, cat="fun", label="Lazer"),
            _spend(date(2026, 10, 4), 100, cat=None, label=None),
        ]

        result = spending_insights(facts, 2026, 10)

        assert result.expenses == Decimal("1000.00")
        assert [(c.label, c.share) for c in result.top_categories] == [
            ("Moradia", Decimal("0.5000")),
            ("Alimentação", Decimal("0.3000")),
            ("Lazer", Decimal("0.1000")),
        ]
        assert result.top_share == Decimal("0.9000")

    def test_estorno_reduz_o_gasto_da_categoria(self):
        facts = [
            _spend(date(2026, 10, 1), 500, cat="home", label="Moradia"),
            _spend(date(2026, 10, 2), -200, cat="home", label="Moradia"),
        ]

        result = spending_insights(facts, 2026, 10)

        assert result.expenses == Decimal("300.00")
        assert result.top_share is None  # uma categoria só

    def test_nao_classificado_mostra_quanto_falta_classificar(self):
        facts = [
            _spend(date(2026, 10, 1), 300),
            _spend(date(2026, 10, 2), 100, expense=False, cat=None, label=None),
            SpendFact(date(2026, 10, 3), Decimal(500), False, None, None, "salario"),
        ]

        result = spending_insights(facts, 2026, 10)

        assert result.unclassified_outflow == Decimal("100.00")
        assert result.unclassified_share == Decimal("0.2500")
        assert result.expenses == Decimal("300.00")

    def test_mes_sem_nada(self):
        result = spending_insights([], 2026, 10)

        assert result.expenses == Decimal("0.00")
        assert result.top_categories == ()
        assert result.top_share is None
        assert result.unclassified_share is None
