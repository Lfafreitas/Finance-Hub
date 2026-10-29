import uuid
from datetime import date
from decimal import Decimal

from app.models.enums import TransactionType
from app.services.dividends_service import DividendFact, aggregate_dividends

ACCOUNT_ID = uuid.uuid4()
INSTITUTION_ID = uuid.uuid4()
ASSET_ID = uuid.uuid4()


def dfact(
    transaction_type,
    amount,
    day=1,
    month=1,
    year=2026,
    currency="BRL",
    asset_id=None,
    account_id=None,
):
    return DividendFact(
        transaction_type=transaction_type,
        transaction_date=date(year, month, day),
        amount=Decimal(amount),
        currency_code=currency,
        asset_id=asset_id if asset_id is not None else ASSET_ID,
        account_id=account_id or ACCOUNT_ID,
    )


ASSET_LOOKUP = {ASSET_ID: ("PETR4", "Petrobras")}
INSTITUTION_LOOKUP = {ACCOUNT_ID: (INSTITUTION_ID, "XP Investimentos")}


class TestTotaisBasicos:
    def test_soma_total_recebido(self):
        facts = [
            dfact(TransactionType.DIVIDEND, "50.00", day=1, month=1),
            dfact(TransactionType.JCP, "30.00", day=1, month=2),
        ]
        summary = aggregate_dividends(
            facts, ASSET_LOOKUP, INSTITUTION_LOOKUP, reference_date=date(2026, 3, 1)
        )

        totals = summary.totals_by_currency[0]
        assert totals.currency_code == "BRL"
        assert totals.total_received == Decimal("80.00")

    def test_consolidado_disponivel_com_moeda_unica(self):
        facts = [dfact(TransactionType.DIVIDEND, "50.00")]
        summary = aggregate_dividends(
            facts, ASSET_LOOKUP, INSTITUTION_LOOKUP, reference_date=date(2026, 3, 1)
        )

        assert summary.consolidated_total_received == Decimal("50.00")
        assert summary.consolidation_unavailable_reason is None


class TestMoedaMista:
    def test_nao_consolida_moedas_diferentes_sem_fx(self):
        facts = [
            dfact(TransactionType.DIVIDEND, "100.00", currency="BRL"),
            dfact(TransactionType.DIVIDEND, "50.00", currency="USD"),
        ]
        summary = aggregate_dividends(
            facts, ASSET_LOOKUP, INSTITUTION_LOOKUP, reference_date=date(2026, 3, 1)
        )

        assert summary.consolidated_total_received is None
        assert "BRL" in summary.consolidation_unavailable_reason
        assert "USD" in summary.consolidation_unavailable_reason
        # mas os totais por moeda individual continuam disponíveis
        by_currency = {t.currency_code: t.total_received for t in summary.totals_by_currency}
        assert by_currency["BRL"] == Decimal("100.00")
        assert by_currency["USD"] == Decimal("50.00")

    def test_by_month_nunca_mistura_moedas_no_mesmo_valor(self):
        facts = [
            dfact(TransactionType.DIVIDEND, "100.00", currency="BRL", month=1),
            dfact(TransactionType.DIVIDEND, "50.00", currency="USD", month=1),
        ]
        summary = aggregate_dividends(
            facts, ASSET_LOOKUP, INSTITUTION_LOOKUP, reference_date=date(2026, 3, 1)
        )

        entries = {(e.month, e.currency_code): e.amount for e in summary.by_month}
        assert entries[("2026-01", "BRL")] == Decimal("100.00")
        assert entries[("2026-01", "USD")] == Decimal("50.00")


class TestMediaMensal:
    def test_media_mensal_um_unico_mes(self):
        """D-F3: proventos só em setembro -> average_monthly é o total
        de setembro (meses_corridos = 1), não uma janela fixa de 12.
        """
        facts = [dfact(TransactionType.DIVIDEND, "120.00", day=15, month=9)]
        summary = aggregate_dividends(
            facts, ASSET_LOOKUP, INSTITUTION_LOOKUP, reference_date=date(2026, 9, 20)
        )

        totals = summary.totals_by_currency[0]
        assert totals.average_monthly == Decimal("120.00")

    def test_media_mensal_periodo_de_tres_meses(self):
        facts = [
            dfact(TransactionType.DIVIDEND, "100.00", month=1, day=1),
            dfact(TransactionType.DIVIDEND, "100.00", month=3, day=1),
        ]
        summary = aggregate_dividends(
            facts, ASSET_LOOKUP, INSTITUTION_LOOKUP, reference_date=date(2026, 4, 1)
        )

        totals = summary.totals_by_currency[0]
        # jan -> mar = 3 meses corridos; total 200 / 3
        assert totals.average_monthly == (Decimal("200.00") / Decimal(3))

    def test_average_monthly_last_12_months_sempre_divide_por_12(self):
        facts = [dfact(TransactionType.DIVIDEND, "1200.00", day=1, month=1)]
        summary = aggregate_dividends(
            facts, ASSET_LOOKUP, INSTITUTION_LOOKUP, reference_date=date(2026, 6, 1)
        )

        totals = summary.totals_by_currency[0]
        assert totals.average_monthly_last_12_months == Decimal("100.00")  # 1200/12
        assert totals.average_monthly == Decimal(
            "1200.00"
        )  # 1 único mês corrido — não confundir os dois


class TestJanelasTemporais:
    def test_ultimos_12_meses_exclui_o_que_esta_fora_da_janela(self):
        facts = [
            dfact(TransactionType.DIVIDEND, "100.00", year=2025, month=1, day=1),  # fora da janela
            dfact(TransactionType.DIVIDEND, "50.00", year=2026, month=6, day=1),  # dentro
        ]
        summary = aggregate_dividends(
            facts, ASSET_LOOKUP, INSTITUTION_LOOKUP, reference_date=date(2026, 6, 15)
        )

        totals = summary.totals_by_currency[0]
        assert totals.total_last_12_months == Decimal("50.00")
        assert totals.total_received == Decimal("150.00")  # total geral inclui os dois

    def test_total_no_ano_corrente(self):
        facts = [
            dfact(TransactionType.DIVIDEND, "100.00", year=2025, month=12, day=31),
            dfact(TransactionType.DIVIDEND, "70.00", year=2026, month=1, day=5),
        ]
        summary = aggregate_dividends(
            facts, ASSET_LOOKUP, INSTITUTION_LOOKUP, reference_date=date(2026, 3, 1)
        )

        totals = summary.totals_by_currency[0]
        assert totals.total_current_year == Decimal("70.00")


class TestQuebras:
    def test_by_type_separa_dividend_jcp_income(self):
        facts = [
            dfact(TransactionType.DIVIDEND, "10.00"),
            dfact(TransactionType.JCP, "20.00"),
            dfact(TransactionType.INCOME, "30.00"),
        ]
        summary = aggregate_dividends(
            facts, ASSET_LOOKUP, INSTITUTION_LOOKUP, reference_date=date(2026, 3, 1)
        )

        by_type = {e.transaction_type: e.amount for e in summary.by_type}
        assert by_type["DIVIDEND"] == Decimal("10.00")
        assert by_type["JCP"] == Decimal("20.00")
        assert by_type["INCOME"] == Decimal("30.00")

    def test_by_asset_e_by_institution(self):
        facts = [dfact(TransactionType.DIVIDEND, "40.00")]
        summary = aggregate_dividends(
            facts, ASSET_LOOKUP, INSTITUTION_LOOKUP, reference_date=date(2026, 3, 1)
        )

        assert summary.by_asset[0].asset_ticker == "PETR4"
        assert summary.by_asset[0].amount == Decimal("40.00")
        assert summary.by_institution[0].institution_name == "XP Investimentos"
        assert summary.by_institution[0].amount == Decimal("40.00")

    def test_by_year_agrega_por_ano(self):
        facts = [
            dfact(TransactionType.DIVIDEND, "10.00", year=2025, month=12),
            dfact(TransactionType.DIVIDEND, "20.00", year=2026, month=1),
        ]
        summary = aggregate_dividends(
            facts, ASSET_LOOKUP, INSTITUTION_LOOKUP, reference_date=date(2026, 3, 1)
        )

        by_year = {e.year: e.amount for e in summary.by_year}
        assert by_year[2025] == Decimal("10.00")
        assert by_year[2026] == Decimal("20.00")


class TestPrevisto:
    def test_previsto_e_sempre_none_com_motivo(self):
        facts = [dfact(TransactionType.DIVIDEND, "10.00")]
        summary = aggregate_dividends(
            facts, ASSET_LOOKUP, INSTITUTION_LOOKUP, reference_date=date(2026, 3, 1)
        )

        assert summary.predicted is None
        assert "calendário de proventos" in summary.predicted_unavailable_reason


class TestSemProventos:
    def test_lista_vazia_nao_gera_totais(self):
        summary = aggregate_dividends(
            [], ASSET_LOOKUP, INSTITUTION_LOOKUP, reference_date=date(2026, 3, 1)
        )

        assert summary.totals_by_currency == []
        assert summary.consolidated_total_received is None
        assert summary.by_month == []
