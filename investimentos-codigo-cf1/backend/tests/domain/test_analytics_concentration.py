"""Análises-1: concentração."""

from decimal import Decimal

from app.domain.analytics.concentration import Slice, concentration


def _slice(asset, value, cls="ETF_US", account="XP"):
    return Slice(
        asset_key=asset,
        asset_label=asset,
        class_key=cls,
        class_label=f"classe {cls}",
        account_key=account,
        account_label=account,
        value=Decimal(value),
    )


def test_pesos_por_ativo_classe_e_conta_somam_o_mesmo_ativo_em_contas_diferentes():
    result = concentration(
        [
            _slice("QQQ", "168.75", account="Inter"),
            _slice("QQQ", "144.29", account="XP"),
            _slice("SPY", "126.32", account="Inter"),
            _slice("VNQ", "10.35", cls="REIT", account="Inter"),
        ]
    )

    assert result.total == Decimal("449.71")
    assert [(w.key, w.value, w.weight) for w in result.by_asset] == [
        ("QQQ", Decimal("313.04"), Decimal("0.6961")),
        ("SPY", Decimal("126.32"), Decimal("0.2809")),
        ("VNQ", Decimal("10.35"), Decimal("0.0230")),
    ]
    assert [(w.key, w.weight) for w in result.by_class] == [
        ("ETF_US", Decimal("0.9770")),
        ("REIT", Decimal("0.0230")),
    ]
    assert [w.key for w in result.by_account] == ["Inter", "XP"]
    assert result.by_class[0].label == "classe ETF_US"


def test_ativo_acima_de_40_porcento_e_sinalizado_e_exatamente_40_nao():
    above = concentration([_slice("A", "40.01"), _slice("B", "59.99", cls="REIT")])
    exact = concentration([_slice("A", "40"), _slice("B", "30", cls="REIT"), _slice("C", "30")])

    assert any("B sozinho é mais de 40%" in f for f in above.flags)
    assert not any("sozinho" in f for f in exact.flags)


def test_tres_maiores_acima_de_75_porcento_so_com_mais_de_tres_ativos():
    four = concentration(
        [_slice("A", "30"), _slice("B", "30"), _slice("C", "20"), _slice("D", "20", cls="REIT")]
    )
    three = concentration([_slice("A", "34"), _slice("B", "33"), _slice("C", "33", cls="REIT")])

    assert four.top3_weight == Decimal("0.8000")
    assert any("3 maiores" in f for f in four.flags)
    assert not any("3 maiores" in f for f in three.flags)
    assert three.top3_weight == Decimal("1.0000")


def test_carteira_numa_classe_so():
    result = concentration([_slice("A", "50"), _slice("B", "50")])

    assert "toda a carteira está numa classe só (classe ETF_US)" in result.flags


def test_um_ativo_so_nao_gera_sinal_de_concentracao():
    assert concentration([_slice("A", "100")]).flags == ()


def test_sem_valor_nao_ha_concentracao():
    assert concentration([]) is None
    assert concentration([_slice("A", "0")]) is None


def test_empate_de_valor_ordena_pelo_nome():
    result = concentration([_slice("B", "50"), _slice("A", "50")])

    assert [w.key for w in result.by_asset] == ["A", "B"]
