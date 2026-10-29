"""Análises-1: ritmo de aporte."""

from datetime import date
from decimal import Decimal

from app.domain.analytics.contributions import contribution_pace

REF = date(2026, 10, 8)


def _pace(result, name):
    return next(p for p in result.projections if p.pace == name)


def test_aportes_reais_do_inter():
    events = [
        (date(2026, 8, 26), Decimal("100.00")),
        (date(2026, 9, 9), Decimal("50.65")),
        (date(2026, 10, 7), Decimal("200.59")),
    ]

    result = contribution_pace(events, REF)

    assert result.total_year == Decimal("351.24")
    assert [(m.month, m.amount) for m in result.months] == [
        ("2026-08", Decimal("100.00")),
        ("2026-09", Decimal("50.65")),
        ("2026-10", Decimal("200.59")),
    ]
    assert result.remaining_months == 2
    average = _pace(result, "AVERAGE")
    assert (average.monthly, average.remaining_total, average.year_end_total) == (
        Decimal("117.08"),
        Decimal("234.16"),
        Decimal("585.40"),
    )
    last3 = _pace(result, "LAST_3")
    assert last3.monthly == Decimal("117.08")
    last = _pace(result, "LAST_MONTH")
    assert (last.monthly, last.year_end_total) == (Decimal("200.59"), Decimal("752.42"))


def test_meses_sem_aporte_aparecem_com_zero_e_contam_na_media():
    events = [(date(2026, 3, 1), Decimal(300)), (date(2026, 6, 1), Decimal(100))]

    result = contribution_pace(events, date(2026, 6, 30))

    assert [m.amount for m in result.months] == [Decimal("300.00"), 0, 0, Decimal("100.00")]
    assert _pace(result, "AVERAGE").monthly == Decimal("100.00")  # 400 / 4
    assert _pace(result, "LAST_3").monthly == Decimal("33.33")  # abr+mai+jun
    assert _pace(result, "LAST_MONTH").monthly == Decimal("100.00")


def test_mes_corrente_sem_aporte_tem_ritmo_zero():
    result = contribution_pace([(date(2026, 9, 10), Decimal(100))], REF)

    assert _pace(result, "LAST_MONTH").monthly == Decimal("0.00")
    assert _pace(result, "LAST_MONTH").year_end_total == Decimal("100.00")


def test_retirada_desconta():
    events = [(date(2026, 10, 1), Decimal(500)), (date(2026, 10, 5), Decimal(-200))]

    result = contribution_pace(events, REF)

    assert result.total_year == Decimal("300.00")


def test_outros_anos_e_datas_depois_da_referencia_ficam_de_fora():
    events = [
        (date(2025, 12, 20), Decimal(999)),
        (date(2026, 10, 1), Decimal(100)),
        (date(2026, 10, 20), Decimal(777)),
    ]

    result = contribution_pace(events, REF)

    assert result.total_year == Decimal("100.00")
    assert [m.month for m in result.months] == ["2026-10"]


def test_em_dezembro_nao_ha_meses_restantes():
    result = contribution_pace([(date(2026, 12, 1), Decimal(100))], date(2026, 12, 15))

    assert result.remaining_months == 0
    assert all(p.year_end_total == Decimal("100.00") for p in result.projections)
    assert all(p.remaining_total == Decimal("0.00") for p in result.projections)


def test_sem_aporte_no_ano_nao_ha_ritmo():
    assert contribution_pace([], REF) is None
    assert contribution_pace([(date(2025, 5, 1), Decimal(10))], REF) is None


def test_com_menos_de_3_meses_os_ultimos_3_usam_so_os_meses_que_existem():
    result = contribution_pace([(date(2026, 10, 2), Decimal(150))], REF)

    assert _pace(result, "LAST_3").monthly == Decimal("150.00")
    assert _pace(result, "AVERAGE").monthly == Decimal("150.00")
