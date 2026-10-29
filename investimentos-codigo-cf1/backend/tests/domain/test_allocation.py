"""Alocação-alvo: peso atual × alvo, por classe, numa moeda."""

from decimal import Decimal

from app.domain.analytics.allocation import ClassValue, allocation, targets_are_valid

D = Decimal
CURRENT = [
    ClassValue("ETF_US", "ETF (Exterior)", D("600")),
    ClassValue("BOND", "Bond / Treasury", D("300")),
    ClassValue("REIT", "REIT", D("100")),
]


def test_sem_alvo_so_mostra_o_peso_atual():
    rows = {r.asset_class: r for r in allocation(CURRENT, {}, {})}

    assert rows["ETF_US"].current_weight == D("0.6000")
    assert rows["ETF_US"].target_weight is None and rows["ETF_US"].gap is None
    assert rows["ETF_US"].value_gap is None


def test_desvio_em_pontos_e_em_valor():
    targets = {"ETF_US": D("0.5"), "BOND": D("0.3"), "REIT": D("0.2")}
    rows = {r.asset_class: r for r in allocation(CURRENT, targets, {})}

    assert rows["ETF_US"].gap == D("0.1000")  # 10 p.p. acima
    assert rows["ETF_US"].value_gap == D("-100.00")
    assert rows["REIT"].gap == D("-0.1000")
    assert rows["REIT"].value_gap == D("100.00")  # falta 100 para o alvo
    assert rows["BOND"].gap == D("0.0000")


def test_classe_com_alvo_sem_posicao_e_classe_sem_alvo():
    targets = {"ETF_US": D("0.8"), "STOCK_US": D("0.2")}
    rows = {r.asset_class: r for r in allocation(CURRENT, targets, {"STOCK_US": "Ação (Exterior)"})}

    assert rows["STOCK_US"].label == "Ação (Exterior)"
    assert rows["STOCK_US"].current_weight == D("0") and rows["STOCK_US"].value_gap == D("200.00")
    # Há alvos e o REIT não está neles: alvo zero, todo o valor acima.
    assert rows["REIT"].target_weight == D("0") and rows["REIT"].value_gap == D("-100.00")


def test_ordem_pelo_alvo_e_depois_pelo_valor():
    targets = {"REIT": D("0.5"), "ETF_US": D("0.5")}
    order = [r.asset_class for r in allocation(CURRENT, targets, {})]

    assert order == ["ETF_US", "REIT", "BOND"]


def test_alvos_validos_somam_cem_por_cento():
    assert targets_are_valid({})
    assert targets_are_valid({"A": D("0.3333"), "B": D("0.3333"), "C": D("0.3334")})
    assert not targets_are_valid({"A": D("0.5"), "B": D("0.4")})
    assert not targets_are_valid({"A": D("1.2"), "B": D("-0.2")})
