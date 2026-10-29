"""Fase 10b, unidade 4: matcher (candidate detection, comparison,
classification). Testes puros e determinísticos — sem banco, exceto a
classe `TestSchemaReal`, que confirma o mapeamento de linhas reais.
"""

import uuid
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domain.reconciliation.matcher import (
    COMPARED_FIELDS,
    EXCLUDED_TYPES,
    build_match_reason,
    classify,
    compare_transactions,
    is_candidate,
    match,
)
from app.domain.reconciliation.types import MatchClassification, TransactionSnapshot
from app.models.enums import TransactionSource, TransactionType
from tests.test_immutability import make_transaction
from tests.test_persistence import make_account, make_institution, make_user

ACCOUNT = uuid.UUID(int=1000)
ASSET = uuid.UUID(int=2000)
D = date(2026, 6, 10)
MANUAL = TransactionSource.MANUAL
CSV = TransactionSource.IMPORT_CSV

_n = {"i": 0}


def snap(**overrides) -> TransactionSnapshot:
    """BUY 100 @ 30 (gross 3000), MANUAL, BRL. ids crescentes por chamada."""
    _n["i"] += 1
    data = {
        "id": uuid.UUID(int=_n["i"]),
        "account_id": ACCOUNT,
        "asset_id": ASSET,
        "transaction_type": TransactionType.BUY,
        "quantity": Decimal(100),
        "unit_price": Decimal(30),
        "fees": Decimal(0),
        "gross_amount": Decimal(3000),
        "currency_code": "BRL",
        "transaction_date": D,
        "source": MANUAL,
        "fx_rate_to_brl": None,
    }
    data.update(overrides)
    return TransactionSnapshot(**data)


def pair(a_overrides=None, b_overrides=None):
    return snap(**(a_overrides or {})), snap(**(b_overrides or {}))


class TestCandidatoMesmaSource:
    def test_identicas_nao_sao_candidatas(self):
        a, b = pair()
        assert not is_candidate(a, b)

    def test_identicas_com_notes_e_referencia_diferentes_continuam_nao_candidatas(self):
        # `notes`/`external_reference` nem fazem parte do snapshot: não
        # tornam duas operações idênticas "divergentes".
        a, b = pair()
        assert not is_candidate(a, b)

    @pytest.mark.parametrize(
        "override",
        [
            {"quantity": Decimal(105)},
            {"unit_price": Decimal(31)},
            {"fees": Decimal("2.5")},
            {"gross_amount": Decimal(3100)},
            {"transaction_date": D + timedelta(days=1)},
            {"fx_rate_to_brl": Decimal("5.20")},
        ],
    )
    def test_divergentes_dentro_da_tolerancia_sao_candidatas(self, override):
        a, b = pair(b_overrides=override)
        assert is_candidate(a, b)

    def test_mesma_source_divergente_outras_sources(self):
        for source in TransactionSource:
            a, b = pair({"source": source}, {"source": source, "quantity": Decimal(105)})
            assert is_candidate(a, b), source


class TestCandidatoFontesDiferentes:
    def test_identicas_de_fontes_diferentes_sao_candidatas(self):
        a, b = pair({"source": MANUAL}, {"source": CSV})
        assert is_candidate(a, b)

    def test_divergentes_dentro_de_10pct_sao_candidatas(self):
        # gross 3000 vs 3150 (5%)
        a, b = pair({"source": MANUAL}, {"source": CSV, "gross_amount": Decimal(3150)})
        assert is_candidate(a, b)

    def test_acima_de_10pct_nao_e_candidata(self):
        a, b = pair({"source": MANUAL}, {"source": CSV, "gross_amount": Decimal(4000)})
        assert not is_candidate(a, b)


class TestToleranciaDe10PorCento:
    """`|a - b| <= 10% * max(|a|, |b|)` — referência: o maior valor."""

    @pytest.mark.parametrize(
        ("x", "y", "expected"),
        [
            # 100↔110: 10 <= 11 (dentro)
            ("100", "110", True),
            # 100↔90: 10 <= 10 — EXATAMENTE no limite, dentro
            ("100", "90", True),
            # 90.00↔100.00 e centavos: 9.99 <= 10 dentro; 10.01 > 10 fora
            ("100", "90.01", True),
            ("100", "89.99", False),
            # limite superior: 100/0.9 = 111.111...; 111.11 dentro, 111.12 fora
            ("100", "111.11", True),
            ("100", "111.12", False),
            ("100", "100", True),
            # ordem de grandeza diferente
            ("100", "1000", False),
        ],
    )
    @pytest.mark.parametrize("swap", [False, True])
    def test_limites_exatos_e_simetria(self, x, y, expected, swap):
        gx, gy = (Decimal(y), Decimal(x)) if swap else (Decimal(x), Decimal(y))
        a, b = pair({"source": MANUAL, "gross_amount": gx}, {"source": CSV, "gross_amount": gy})

        assert is_candidate(a, b) is expected

    def test_ambos_zero_dentro_da_tolerancia(self):
        a, b = pair(
            {"source": MANUAL, "gross_amount": Decimal(0)},
            {"source": CSV, "gross_amount": Decimal(0)},
        )
        assert is_candidate(a, b)

    def test_um_zero_e_outro_nao_fica_fora(self):
        a, b = pair(
            {"source": MANUAL, "gross_amount": Decimal(0)},
            {"source": CSV, "gross_amount": Decimal("0.01")},
        )
        assert not is_candidate(a, b)

    def test_tolerancia_e_so_de_candidatura_5pct_continua_divergente(self):
        a, b = pair({"source": MANUAL}, {"source": CSV, "gross_amount": Decimal(3150)})

        result = match(a, b)

        assert result is not None
        assert result.classification == MatchClassification.DIVERGENT


class TestTolerianciaDeData:
    @pytest.mark.parametrize(
        ("delta", "expected"), [(0, True), (1, True), (-1, True), (2, False), (-2, False)]
    )
    def test_mais_ou_menos_um_dia(self, delta, expected):
        a, b = pair(
            {"source": MANUAL}, {"source": CSV, "transaction_date": D + timedelta(days=delta)}
        )
        assert is_candidate(a, b) is expected


class TestCriteriosEstruturais:
    def test_tipos_diferentes_nao_sao_candidatos(self):
        a, b = pair({"source": MANUAL}, {"source": CSV, "transaction_type": TransactionType.SELL})
        assert not is_candidate(a, b)

    def test_assets_diferentes_nao_sao_candidatos(self):
        a, b = pair({"source": MANUAL}, {"source": CSV, "asset_id": uuid.UUID(int=2001)})
        assert not is_candidate(a, b)

    def test_asset_nulo_vs_asset_presente_nao_e_candidato(self):
        a, b = pair({"source": MANUAL}, {"source": CSV, "asset_id": None})
        assert not is_candidate(a, b)

    def test_ambos_sem_asset_contam_como_mesmo_asset(self):
        a, b = pair(
            {"source": MANUAL, "asset_id": None, "transaction_type": TransactionType.DEPOSIT},
            {"source": CSV, "asset_id": None, "transaction_type": TransactionType.DEPOSIT},
        )
        assert is_candidate(a, b)

    def test_contas_diferentes_nao_sao_candidatas(self):
        a, b = pair({"source": MANUAL}, {"source": CSV, "account_id": uuid.UUID(int=1001)})
        assert not is_candidate(a, b)

    def test_mesma_transaction_nao_e_candidata_dela_mesma(self):
        a = snap()
        assert not is_candidate(a, a)

    @pytest.mark.parametrize("ttype", sorted(EXCLUDED_TYPES, key=lambda t: t.value))
    def test_tipos_excluidos_nao_sao_candidatos(self, ttype):
        a, b = pair(
            {"source": MANUAL, "transaction_type": ttype, "asset_id": None},
            {"source": CSV, "transaction_type": ttype, "asset_id": None},
        )
        assert not is_candidate(a, b)

    def test_excluidos_sao_exatamente_transferencias_e_fx_conversion(self):
        assert EXCLUDED_TYPES == {
            TransactionType.TRANSFER_IN,
            TransactionType.TRANSFER_OUT,
            TransactionType.FX_CONVERSION,
        }

    @pytest.mark.parametrize(
        "ttype", [t for t in TransactionType if t not in EXCLUDED_TYPES], ids=lambda t: t.value
    )
    def test_todos_os_demais_tipos_do_enum_real_sao_elegiveis(self, ttype):
        a, b = pair(
            {"source": MANUAL, "transaction_type": ttype},
            {"source": CSV, "transaction_type": ttype},
        )
        assert is_candidate(a, b)


class TestComparacao:
    def test_ordem_e_conjunto_de_campos_fixos(self):
        a, b = pair()
        assert tuple(f.field for f in compare_transactions(a, b).fields) == COMPARED_FIELDS

    def test_idênticas_todos_iguais(self):
        result = compare_transactions(*pair())

        assert result.is_identical
        assert result.differing_fields == ()
        assert len(result.equal_fields) == len(COMPARED_FIELDS)

    def test_quantidade_divergente_com_valores_e_diferencas(self):
        a, b = pair(b_overrides={"quantity": Decimal(105)})

        result = compare_transactions(a, b)

        (diff,) = result.differing_fields
        assert diff.field == "quantity"
        assert (diff.value_a, diff.value_b) == (Decimal(100), Decimal(105))
        assert diff.absolute_difference == Decimal(5)
        assert diff.relative_difference == Decimal(5) / Decimal(105)  # ref = maior valor
        assert "unit_price" in [f.field for f in result.equal_fields]

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("quantity", Decimal(101)),
            ("unit_price", Decimal("30.5")),
            ("gross_amount", Decimal(3050)),
            ("fees", Decimal(1)),
            ("fx_rate_to_brl", Decimal("5.2")),
            ("transaction_date", D + timedelta(days=1)),
        ],
    )
    def test_cada_campo_divergente_e_identificado_sozinho(self, field, value):
        a, b = pair(b_overrides={field: value})

        result = compare_transactions(a, b)

        assert [f.field for f in result.differing_fields] == [field]

    def test_combinacao_de_divergencias(self):
        a, b = pair(
            b_overrides={
                "quantity": Decimal(105),
                "gross_amount": Decimal(3150),
                "fees": Decimal(2),
            }
        )

        result = compare_transactions(a, b)

        assert [f.field for f in result.differing_fields] == ["quantity", "gross_amount", "fees"]

    def test_data_reporta_diferenca_em_dias_sem_relativa(self):
        a, b = pair(b_overrides={"transaction_date": D + timedelta(days=1)})

        (diff,) = compare_transactions(a, b).differing_fields

        assert diff.absolute_difference == Decimal(1)
        assert diff.relative_difference is None

    def test_moeda_diferente_sem_diferenca_numerica(self):
        # Mesma taxa nos dois lados para isolar `currency_code`.
        rate = {"fx_rate_to_brl": Decimal("5.2")}
        a, b = pair({**rate, "currency_code": "USD"}, {**rate, "currency_code": "EUR"})

        (diff,) = compare_transactions(a, b).differing_fields

        assert diff.field == "currency_code"
        assert (diff.value_a, diff.value_b) == ("USD", "EUR")
        assert diff.absolute_difference is None and diff.relative_difference is None

    def test_brl_para_usd_sem_taxa_diverge_em_moeda_e_em_taxa(self):
        # BRL nulo vale 1; USD nulo é "não informado" — as duas divergem.
        a, b = pair(b_overrides={"currency_code": "USD"})

        assert [f.field for f in compare_transactions(a, b).differing_fields] == [
            "currency_code",
            "fx_rate_to_brl",
        ]

    def test_escala_decimal_nao_gera_divergencia(self):
        a, b = pair(b_overrides={"quantity": Decimal("100.00000000"), "fees": Decimal("0.0000")})

        assert compare_transactions(a, b).is_identical

    def test_nulos_iguais_sao_iguais_e_nulo_vs_valor_diverge(self):
        both_null = compare_transactions(*pair({"unit_price": None}, {"unit_price": None}))
        one_null = compare_transactions(*pair({"unit_price": None}, {}))

        assert both_null.is_identical
        (diff,) = one_null.differing_fields
        assert diff.field == "unit_price"
        assert diff.value_a is None and diff.absolute_difference is None

    def test_fx_nulo_em_brl_equivale_a_taxa_1(self):
        result = compare_transactions(
            *pair({"fx_rate_to_brl": None}, {"fx_rate_to_brl": Decimal(1)})
        )

        assert result.is_identical

    def test_fx_nulo_em_moeda_estrangeira_nao_equivale_a_nada(self):
        usd = {"currency_code": "USD"}
        result = compare_transactions(
            *pair({**usd, "fx_rate_to_brl": None}, {**usd, "fx_rate_to_brl": Decimal(1)})
        )

        assert [f.field for f in result.differing_fields] == ["fx_rate_to_brl"]

    def test_valores_zero_sem_divisao_por_zero(self):
        a, b = pair({"fees": Decimal(0)}, {"fees": Decimal(0)})
        (fees,) = [f for f in compare_transactions(a, b).fields if f.field == "fees"]

        assert fees.equal and fees.relative_difference == 0

        a, b = pair({"fees": Decimal(0)}, {"fees": Decimal(3)})
        (fees,) = [f for f in compare_transactions(a, b).fields if f.field == "fees"]
        assert fees.absolute_difference == 3 and fees.relative_difference == 1


class TestClassificacao:
    def test_equivalent_quando_nada_difere(self):
        assert classify(compare_transactions(*pair())) == MatchClassification.EQUIVALENT

    def test_divergent_quando_qualquer_campo_difere(self):
        result = compare_transactions(*pair(b_overrides={"fees": Decimal("0.0001")}))

        assert classify(result) == MatchClassification.DIVERGENT

    def test_classificacao_so_tem_dois_valores(self):
        assert {c.value for c in MatchClassification} == {"EQUIVALENT", "DIVERGENT"}

    def test_fontes_diferentes_identicas_sao_equivalent(self):
        result = match(*pair({"source": MANUAL}, {"source": CSV}))

        assert result is not None
        assert result.classification == MatchClassification.EQUIVALENT
        assert result.match_reason == "EQUIVALENT: todos os campos comparados são iguais"

    def test_100_a_30_vs_105_a_30_do_handoff_e_divergent(self):
        a, b = pair(
            {"source": MANUAL},
            {"source": CSV, "quantity": Decimal(105), "gross_amount": Decimal(3150)},
        )

        result = match(a, b)

        assert result.classification == MatchClassification.DIVERGENT
        assert [f.field for f in result.comparison.differing_fields] == ["quantity", "gross_amount"]


class TestMatchComposicao:
    def test_nao_candidato_devolve_none(self):
        assert match(*pair()) is None  # mesma source, idênticas

    def test_ordem_canonica_independe_da_ordem_de_entrada(self):
        a, b = pair({"source": MANUAL}, {"source": CSV, "quantity": Decimal(105)})

        forward, backward = match(a, b), match(b, a)

        assert forward == backward
        assert forward.transaction_a.id < forward.transaction_b.id

    def test_match_reason_lista_campos_divergentes_com_valores_e_diferencas(self):
        a, b = pair(
            {"source": MANUAL},
            {"source": CSV, "quantity": Decimal(105), "transaction_date": D + timedelta(days=1)},
        )

        reason = match(a, b).match_reason

        assert reason.startswith("DIVERGENT: ")
        assert "transaction_date: 2026-06-10 != 2026-06-11 (abs=1 dias)" in reason
        assert "quantity: 100 != 105 (abs=5, rel=" in reason
        assert "unit_price" not in reason

    def test_determinismo_mesma_entrada_mesma_saida(self):
        a, b = pair(
            {"source": MANUAL}, {"source": CSV, "fees": Decimal(2), "quantity": Decimal(99)}
        )

        results = [match(a, b) for _ in range(5)]

        assert all(r == results[0] for r in results)

    def test_nao_altera_os_snapshots(self):
        a, b = pair({"source": MANUAL}, {"source": CSV, "quantity": Decimal(105)})
        before = (replace(a), replace(b))

        match(a, b)

        assert (a, b) == before

    def test_build_match_reason_e_puro(self):
        comparison = compare_transactions(*pair(b_overrides={"fees": Decimal(2)}))

        text = build_match_reason(classify(comparison), comparison)

        assert text == "DIVERGENT: fees: 0 != 2 (abs=2, rel=1)"


class TestSchemaReal:
    """Linhas reais do banco: nulos e zero como o schema realmente permite."""

    def test_deposito_sem_asset_quantidade_ou_preco(self, db_session):
        user = make_user(db_session, email="matcher-schema@example.com")
        account = make_account(db_session, user, make_institution(db_session, name="Inst Matcher"))
        row_a = make_transaction(db_session, account, source=MANUAL)
        row_b = make_transaction(db_session, account, source=CSV)

        a = TransactionSnapshot.from_transaction(row_a)
        b = TransactionSnapshot.from_transaction(row_b)

        assert a.asset_id is None and a.quantity is None and a.unit_price is None
        assert a.fx_rate_to_brl is None
        result = match(a, b)
        assert result is not None
        assert result.classification == MatchClassification.EQUIVALENT

    def test_gross_zero_real_no_banco(self, db_session):
        user = make_user(db_session, email="matcher-zero@example.com")
        account = make_account(db_session, user, make_institution(db_session, name="Inst Zero"))
        row_a = make_transaction(db_session, account, source=MANUAL, gross_amount=Decimal(0))
        row_b = make_transaction(db_session, account, source=CSV, gross_amount=Decimal(0))

        result = match(
            TransactionSnapshot.from_transaction(row_a), TransactionSnapshot.from_transaction(row_b)
        )

        assert result is not None

    def test_from_transaction_nao_altera_a_linha(self, db_session):
        user = make_user(db_session, email="matcher-ro@example.com")
        account = make_account(db_session, user, make_institution(db_session, name="Inst RO"))
        row = make_transaction(db_session, account)
        before = (row.status, row.gross_amount, row.transaction_date)

        TransactionSnapshot.from_transaction(row)

        assert (row.status, row.gross_amount, row.transaction_date) == before
