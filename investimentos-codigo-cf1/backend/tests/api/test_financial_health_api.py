"""GET /performance/financial-health: reserva em meses de gasto e taxa de
poupança, com os meses fechados (o mês corrente fica de fora).
"""

from decimal import Decimal

from tests.api.test_visual_api import TODAY, _day_in, _month, w  # noqa: F401


def test_cobertura_e_poupanca_com_meses_fechados(w):  # noqa: F811
    w["entry"]("savings", "12000", _day_in(3), "Saldo inicial", "ADJUSTMENT")
    w["entry"]("checking", "5000", _day_in(2), "Salário", "INCOME")
    w["entry"]("card", "-2000", _day_in(2, 12), "Compra", "EXPENSE")
    w["entry"]("checking", "5000", _day_in(1), "Salário", "INCOME")
    w["entry"]("card", "-4000", _day_in(1, 12), "Compra", "EXPENSE")
    w["entry"]("card", "-9999", _day_in(0, 1), "Mês corrente", "EXPENSE")  # não entra

    body = w["client"].get("/performance/financial-health").json()

    (brl,) = body["currencies"]
    assert brl["currency_code"] == "BRL"
    # O mês só com o saldo inicial (sem renda nem gasto) não entra na média.
    assert brl["months"] == [f"{y}-{m:02d}" for y, m in (_month(2), _month(1))]
    assert Decimal(brl["avg_expenses"]) == Decimal(3000)  # 6.000 / 2
    assert Decimal(brl["reserve"]) == Decimal(12000)
    assert Decimal(brl["coverage_months"]) == Decimal(4)
    assert Decimal(brl["savings_rate"]) == Decimal("0.4")  # (10.000 − 6.000) / 10.000
    assert brl["complete"] is True


def test_sem_classificacao_avisa_que_e_teto(w):  # noqa: F811
    w["entry"]("savings", "3000", _day_in(1), "Saldo", "ADJUSTMENT")
    w["entry"]("checking", "4000", _day_in(1), "Salário", "INCOME")
    w["entry"]("card", "-1000", _day_in(1, 12), "Compra", "EXPENSE")
    w["entry"]("card", "-500", _day_in(1, 13), "Algo", "UNCLASSIFIED")

    (brl,) = w["client"].get("/performance/financial-health").json()["currencies"]
    y, m = _month(1)
    assert brl["complete"] is False and brl["incomplete_months"] == [f"{y}-{m:02d}"]
    assert Decimal(brl["coverage_months"]) == Decimal(3)


def test_sem_movimento_nem_reserva_fica_vazio(w):  # noqa: F811
    assert w["client"].get("/performance/financial-health").json()["currencies"] == []
