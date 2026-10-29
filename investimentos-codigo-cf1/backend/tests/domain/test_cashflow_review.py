"""Painel-1: grupos do que falta classificar e sugestão pelo histórico."""

import uuid
from datetime import date
from decimal import Decimal

from app.domain.cashflow_engine.review import (
    KnownClassification,
    PendingEntry,
    group_pending,
    suggest,
)
from app.models.enums import CashflowNature as N

ACC = uuid.uuid4()
FOOD = uuid.uuid4()
RIDE = uuid.uuid4()


def pending(text, amount, day=1, currency="BRL"):
    return PendingEntry(
        id=uuid.uuid4(),
        account_id=ACC,
        match_text=text,
        description=text.upper(),
        currency_code=currency,
        amount=Decimal(amount),
        entry_date=date(2026, 9, day),
    )


def known(text, nature, category=None, day=1):
    return KnownClassification(text, nature, category, date(2026, 8, day))


class TestSugestao:
    def test_a_mais_frequente_vence(self):
        result = suggest(
            [
                known("uber", N.EXPENSE, RIDE),
                known("uber", N.EXPENSE, RIDE),
                known("uber", N.THIRD_PARTY),
            ]
        )

        assert (result.nature, result.category_id, result.evidence) == (N.EXPENSE, RIDE, 2)
        assert result.share == Decimal("0.6667")

    def test_empate_vai_para_a_mais_recente(self):
        result = suggest([known("x", N.EXPENSE, FOOD, day=1), known("x", N.INCOME, None, day=9)])

        assert result.nature is N.INCOME

    def test_sem_historico_nao_sugere(self):
        assert suggest([]) is None


class TestGrupos:
    def test_junta_pelo_texto_e_ordena_por_quantidade_e_valor(self):
        groups = group_pending(
            [
                pending("uber", "-10", 1),
                pending("uber", "-12", 5),
                pending("mercado", "-300", 2),
                pending("salario", "5000", 3),
            ],
            [],
        )

        assert [(g.match_text, g.count) for g in groups] == [
            ("uber", 2),
            ("salario", 1),
            ("mercado", 1),
        ]
        uber = groups[0]
        assert uber.total == Decimal(-22)
        assert (uber.inflows, uber.outflows) == (0, 2)
        assert [e.entry_date.day for e in uber.entries] == [5, 1]  # mais recente primeiro

    def test_moedas_diferentes_sao_grupos_diferentes(self):
        groups = group_pending([pending("x", "-1"), pending("x", "-1", currency="USD")], [])

        assert sorted(g.currency_code for g in groups) == ["BRL", "USD"]

    def test_sugestao_ignora_transferencia_e_nao_classificado(self):
        groups = group_pending(
            [pending("pix fulano", "-50")],
            [
                known("pix fulano", N.TRANSFER),
                known("pix fulano", N.TRANSFER),
                known("pix fulano", N.UNCLASSIFIED),
                known("pix fulano", N.THIRD_PARTY),
            ],
        )

        assert groups[0].suggestion.nature is N.THIRD_PARTY
        assert groups[0].suggestion.evidence == 1

    def test_historico_de_outro_texto_nao_conta(self):
        groups = group_pending([pending("uber", "-10")], [known("uber eats", N.EXPENSE, FOOD)])

        assert groups[0].suggestion is None
