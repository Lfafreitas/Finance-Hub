"""CF-2: categorias, tags, classificação manual, regras e quebra por
categoria — pela API. Descrições no formato real do Nubank, com nomes
fictícios.
"""

import uuid
from datetime import date, timedelta

import pytest

from app.models import CashflowEntry
from app.models.cashflow_classification import CashflowCategory, CashflowRule, CashflowTag
from app.models.enums import AccountType
from tests.cashflow_helpers import make_typed_account
from tests.test_persistence import make_institution, make_user

TODAY = date.today()
D1 = (TODAY - timedelta(days=5)).isoformat()
D2 = (TODAY - timedelta(days=4)).isoformat()
D3 = (TODAY - timedelta(days=3)).isoformat()

PIX_BARBER = (
    "Transferência enviada pelo Pix - Barbearia Exemplo - 12.345.678/0001-90 - "
    "PAGSEGURO INTERNET IP S.A. (0290) Agência: 1 Conta: 12345678-9"
)
PIX_FRIEND_IN = (
    "Transferência recebida pelo Pix - FULANO DE TAL SOUZA - •••.123.456-•• - "
    "BCO BRADESCO S.A. (0237) Agência: 1234 Conta: 11111-1"
)


@pytest.fixture()
def cf(api_client, db_session):
    client, user = api_client
    inst = make_institution(db_session, name=f"Banco CF2 {uuid.uuid4().hex[:6]}")

    def account(name, account_type=AccountType.CHECKING, currency="BRL"):
        return make_typed_account(db_session, user, inst, name, account_type, currency)

    world = {
        "client": client,
        "user": user,
        "db": db_session,
        "account": account,
        "checking": account("Corrente"),
        "card": account("Cartão", AccountType.CREDIT_CARD),
        "savings": account("Reserva", AccountType.SAVINGS),
    }

    def entry(description, amount, acct="checking", when=D1, **extra):
        body = {
            "account_id": str(world[acct].id),
            "entry_date": when,
            "amount": amount,
            "description": description,
        }
        body.update(extra)
        response = client.post("/cashflow/entries", json=body)
        assert response.status_code == 201, response.text
        return response.json()

    def category(name, parent=None):
        response = client.post("/cashflow/categories", json={"name": name, "parent_id": parent})
        assert response.status_code == 201, response.text
        return response.json()

    def tag(name, group=""):
        response = client.post("/cashflow/tags", json={"name": name, "tag_group": group})
        assert response.status_code == 201, response.text
        return response.json()

    def rule(pattern, nature="EXPENSE", **extra):
        body = {"name": f"regra {pattern}", "pattern": pattern, "set_nature": nature}
        body.update(extra)
        response = client.post("/cashflow/rules", json=body)
        assert response.status_code == 201, response.text
        return response.json()

    world.update(entry=entry, category=category, tag=tag, rule=rule)
    return world


class TestCategorias:
    def test_cria_categoria_e_subcategoria(self, cf):
        food = cf["category"]("  Alimentação  ")
        market = cf["category"]("Mercado", food["id"])

        assert food == {"id": food["id"], "name": "Alimentação", "parent_id": None}
        assert market["parent_id"] == food["id"]
        assert {c["name"] for c in cf["client"].get("/cashflow/categories").json()} == {
            "Alimentação",
            "Mercado",
        }

    def test_terceiro_nivel_e_400(self, cf):
        food = cf["category"]("Alimentação")
        market = cf["category"]("Mercado", food["id"])

        response = cf["client"].post(
            "/cashflow/categories", json={"name": "Feira", "parent_id": market["id"]}
        )

        assert response.status_code == 400
        assert "dois níveis" in response.json()["detail"]

    def test_categoria_com_filhas_nao_vira_subcategoria(self, cf):
        food = cf["category"]("Alimentação")
        cf["category"]("Mercado", food["id"])
        other = cf["category"]("Casa")

        response = cf["client"].put(
            f"/cashflow/categories/{food['id']}",
            json={"name": "Alimentação", "parent_id": other["id"]},
        )

        assert response.status_code == 400

    def test_mesmo_nome_no_mesmo_nivel_e_409_e_em_niveis_diferentes_e_aceito(self, cf):
        food = cf["category"]("Alimentação")
        cf["category"]("Outros", food["id"])
        health = cf["category"]("Saúde")
        client = cf["client"]

        duplicate_root = client.post("/cashflow/categories", json={"name": "Saúde"})
        duplicate_child = client.post(
            "/cashflow/categories", json={"name": "Outros", "parent_id": food["id"]}
        )
        same_name_other_parent = client.post(
            "/cashflow/categories", json={"name": "Outros", "parent_id": health["id"]}
        )

        assert (duplicate_root.status_code, duplicate_child.status_code) == (409, 409)
        assert same_name_other_parent.status_code == 201

    def test_renomeia_e_move(self, cf):
        food = cf["category"]("Alimentação")
        loose = cf["category"]("Padaria")

        response = cf["client"].put(
            f"/cashflow/categories/{loose['id']}",
            json={"name": "Padarias", "parent_id": food["id"]},
        )

        assert response.status_code == 200
        assert response.json() == {"id": loose["id"], "name": "Padarias", "parent_id": food["id"]}

    def test_exclui_so_categoria_sem_uso(self, cf):
        client = cf["client"]
        parent = cf["category"]("Com filha")
        cf["category"]("Filha", parent["id"])
        with_entry = cf["category"]("Com lançamento")
        with_rule = cf["category"]("Com regra")
        free = cf["category"]("Livre")
        entry = cf["entry"]("Padaria", "-10")
        client.put(
            f"/cashflow/entries/{entry['id']}/classification",
            json={"nature": "EXPENSE", "category_id": with_entry["id"]},
        )
        cf["rule"]("padaria", set_category_id=with_rule["id"])

        results = {
            name: client.delete(f"/cashflow/categories/{c['id']}")
            for name, c in [
                ("parent", parent),
                ("entry", with_entry),
                ("rule", with_rule),
                ("free", free),
            ]
        }

        assert results["free"].status_code == 204
        assert "subcategorias" in results["parent"].json()["detail"]
        assert "lançamentos" in results["entry"].json()["detail"]
        assert "regras" in results["rule"].json()["detail"]
        assert {r.status_code for k, r in results.items() if k != "free"} == {409}

    def test_arvore_inicial_e_idempotente_e_preserva_o_que_existe(self, cf):
        client = cf["client"]
        mine = cf["category"]("Alimentação")

        first = client.post("/cashflow/categories/defaults").json()
        second = client.post("/cashflow/categories/defaults").json()

        assert len(first) == len(second) == 29
        roots = [c for c in first if c["parent_id"] is None]
        assert len(roots) == 15
        assert [c["id"] for c in roots if c["name"] == "Alimentação"] == [mine["id"]]
        children = {c["name"] for c in first if c["parent_id"] == mine["id"]}
        assert children == {"Mercado", "Restaurantes e delivery"}

    def test_categoria_de_outro_usuario_e_404(self, cf):
        stranger = make_user(cf["db"], email="cf2-stranger@example.com")
        foreign = CashflowCategory(user_id=stranger.id, name="Alheia")
        cf["db"].add(foreign)
        cf["db"].flush()
        client = cf["client"]

        assert (
            client.put(f"/cashflow/categories/{foreign.id}", json={"name": "x"}).status_code == 404
        )
        assert client.delete(f"/cashflow/categories/{foreign.id}").status_code == 404
        assert (
            client.post(
                "/cashflow/categories", json={"name": "y", "parent_id": str(foreign.id)}
            ).status_code
            == 404
        )
        assert client.get("/cashflow/categories").json() == []


class TestTags:
    def test_cria_lista_edita_e_duplica(self, cf):
        client = cf["client"]
        person = cf["tag"]("Fulano", "beneficiário")
        cf["tag"]("Online", "canal")

        duplicate = client.post(
            "/cashflow/tags", json={"name": "Fulano", "tag_group": "beneficiário"}
        )
        same_name_other_group = client.post(
            "/cashflow/tags", json={"name": "Fulano", "tag_group": "canal"}
        )
        renamed = client.put(
            f"/cashflow/tags/{person['id']}",
            json={"name": "Fulano de Tal", "tag_group": "beneficiário"},
        )

        assert duplicate.status_code == 409
        assert same_name_other_group.status_code == 201
        assert renamed.json()["name"] == "Fulano de Tal"
        assert [t["tag_group"] for t in client.get("/cashflow/tags").json()] == [
            "beneficiário",
            "canal",
            "canal",
        ]

    def test_excluir_tag_tira_dos_lancamentos_sem_mexer_no_resto(self, cf):
        client = cf["client"]
        tag = cf["tag"]("Online", "canal")
        entry = cf["entry"]("Loja", "-10")
        client.put(
            f"/cashflow/entries/{entry['id']}/classification",
            json={"nature": "EXPENSE", "tag_ids": [tag["id"]]},
        )

        assert client.delete(f"/cashflow/tags/{tag['id']}").status_code == 204

        after = client.get(f"/cashflow/entries/{entry['id']}").json()
        assert (after["tag_ids"], after["nature"]) == ([], "EXPENSE")

    def test_tag_de_outro_usuario_e_404(self, cf):
        stranger = make_user(cf["db"], email="cf2-stranger-tag@example.com")
        foreign = CashflowTag(user_id=stranger.id, name="Alheia", tag_group="")
        cf["db"].add(foreign)
        cf["db"].flush()
        entry = cf["entry"]("Loja", "-10")

        response = cf["client"].put(
            f"/cashflow/entries/{entry['id']}/classification",
            json={"nature": "EXPENSE", "tag_ids": [str(foreign.id)]},
        )

        assert response.status_code == 404
        assert cf["client"].delete(f"/cashflow/tags/{foreign.id}").status_code == 404


class TestClassificacaoManual:
    def test_define_natureza_categoria_e_tags_de_uma_vez(self, cf):
        category = cf["category"]("Cuidados pessoais")
        tag = cf["tag"]("Recorrente")
        entry = cf["entry"](PIX_BARBER, "-40")

        response = cf["client"].put(
            f"/cashflow/entries/{entry['id']}/classification",
            json={
                "nature": "EXPENSE",
                "category_id": category["id"],
                "tag_ids": [tag["id"], tag["id"]],
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert (body["nature"], body["category_id"], body["tag_ids"]) == (
            "EXPENSE",
            category["id"],
            [tag["id"]],
        )
        assert body["classified_by_rule_id"] is None
        assert body["amount"] == "-40.0000"
        assert body["description"] == PIX_BARBER

    def test_lancamento_devolve_o_texto_que_as_regras_enxergam(self, cf):
        entry = cf["entry"](PIX_BARBER, "-40")

        assert entry["match_text"] == "transferencia enviada pelo pix barbearia exemplo"
        assert entry["tag_ids"] == []
        assert entry["category_id"] is None

    def test_substitui_as_tags_anteriores(self, cf):
        a, b = cf["tag"]("A"), cf["tag"]("B")
        entry = cf["entry"]("Loja", "-10")
        url = f"/cashflow/entries/{entry['id']}/classification"
        cf["client"].put(url, json={"nature": "EXPENSE", "tag_ids": [a["id"]]})

        body = cf["client"].put(url, json={"nature": "EXPENSE", "tag_ids": [b["id"]]}).json()

        assert body["tag_ids"] == [b["id"]]

    def test_transferencia_nao_recebe_categoria(self, cf):
        client = cf["client"]
        category = cf["category"]("Qualquer")
        transfer = client.post(
            "/cashflow/transfers",
            json={
                "from_account_id": str(cf["checking"].id),
                "to_account_id": str(cf["savings"].id),
                "entry_date": D1,
                "amount": "100",
                "description": "guardar",
            },
        ).json()
        leg = transfer["entries"][0]["id"]
        entry = cf["entry"]("Loja", "-10")

        on_leg = client.put(
            f"/cashflow/entries/{leg}/classification",
            json={"nature": "EXPENSE", "category_id": category["id"]},
        )
        to_transfer = client.put(
            f"/cashflow/entries/{entry['id']}/classification", json={"nature": "TRANSFER"}
        )

        assert (on_leg.status_code, to_transfer.status_code) == (400, 400)

    def test_categoria_inexistente_e_404_e_estornado_e_409(self, cf):
        client = cf["client"]
        entry = cf["entry"]("Loja", "-10")
        url = f"/cashflow/entries/{entry['id']}/classification"

        missing = client.put(url, json={"nature": "EXPENSE", "category_id": str(uuid.uuid4())})
        client.post(f"/cashflow/entries/{entry['id']}/reverse")
        reversed_entry = client.put(url, json={"nature": "EXPENSE"})

        assert (missing.status_code, reversed_entry.status_code) == (404, 409)


class TestRegras:
    def test_cria_lista_em_ordem_de_prioridade_e_edita(self, cf):
        client = cf["client"]
        category = cf["category"]("Assinaturas")
        tag = cf["tag"]("Recorrente")
        late = cf["rule"]("amazon", priority=200)
        early = cf["rule"](
            "spotify", priority=10, set_category_id=category["id"], tag_ids=[tag["id"]]
        )

        listed = client.get("/cashflow/rules").json()
        updated = client.put(
            f"/cashflow/rules/{late['id']}",
            json={"name": "Amazon", "pattern": "amazon br", "set_nature": "EXPENSE", "priority": 5},
        )

        assert [r["id"] for r in listed] == [early["id"], late["id"]]
        assert early["tag_ids"] == [tag["id"]]
        assert early["match_type"] == "CONTAINS"
        assert early["direction"] == "ANY"
        assert updated.json()["priority"] == 5
        assert [r["id"] for r in client.get("/cashflow/rules").json()] == [late["id"], early["id"]]

    @pytest.mark.parametrize("nature", ["TRANSFER", "UNCLASSIFIED"])
    def test_regra_precisa_de_uma_natureza_de_verdade(self, cf, nature):
        response = cf["client"].post(
            "/cashflow/rules", json={"name": "x", "pattern": "x", "set_nature": nature}
        )

        assert response.status_code == 400

    def test_regra_invalida(self, cf):
        client = cf["client"]
        brokerage = cf["account"]("Corretora", AccountType.BROKERAGE)
        base = {"name": "x", "pattern": "x", "set_nature": "EXPENSE"}

        assert client.post("/cashflow/rules", json={**base, "pattern": "   "}).status_code == 422
        assert client.post("/cashflow/rules", json={"name": "x", "pattern": "x"}).status_code == 422
        assert (
            client.post(
                "/cashflow/rules", json={**base, "set_category_id": str(uuid.uuid4())}
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/cashflow/rules", json={**base, "account_id": str(uuid.uuid4())}
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/cashflow/rules", json={**base, "account_id": str(brokerage.id)}
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/cashflow/rules", json={**base, "tag_ids": [str(uuid.uuid4())]}
            ).status_code
            == 404
        )

    def test_regra_de_outro_usuario_e_404(self, cf):
        stranger = make_user(cf["db"], email="cf2-stranger-rule@example.com")
        foreign = CashflowRule(
            user_id=stranger.id,
            name="alheia",
            pattern="x",
            match_type="CONTAINS",
            set_nature="EXPENSE",
        )
        cf["db"].add(foreign)
        cf["db"].flush()
        body = {"name": "x", "pattern": "x", "set_nature": "EXPENSE"}

        assert cf["client"].put(f"/cashflow/rules/{foreign.id}", json=body).status_code == 404
        assert cf["client"].delete(f"/cashflow/rules/{foreign.id}").status_code == 404
        assert cf["client"].get("/cashflow/rules").json() == []


def _statement(cf):
    """Um mês no formato real: conta e fatura."""
    return {
        "barber": cf["entry"](PIX_BARBER, "-40"),
        "friend_in": cf["entry"](PIX_FRIEND_IN, "50", when=D2),
        "market": cf["entry"]("Compra no débito - SUPER CENTRAL", "-54.30", when=D2),
        "spotify_a": cf["entry"]("Dm*Spotify P46c9", "-12.90", acct="card"),
        "spotify_b": cf["entry"]("Ebn *Spotify", "-12.90", acct="card", when=D2),
        "uber": cf["entry"]("Uber Uber *Trip Help.U", "-29.80", acct="card", when=D3),
        "refund": cf["entry"]("Amazon BR IV - NuPay", "175.45", acct="card", when=D3),
        "purchase": cf["entry"]("Amazon BR IV - NuPay", "-175.45", acct="card", when=D3),
        "unknown": cf["entry"]("Posto Exemplo", "-92.35", acct="card", when=D3),
    }


class TestAplicarRegras:
    def test_previa_nao_grava_e_aplicar_grava_o_mesmo(self, cf):
        client = cf["client"]
        entries = _statement(cf)
        subs = cf["category"]("Assinaturas")
        rule = cf["rule"]("spotify", set_category_id=subs["id"])

        preview = client.post("/cashflow/rules/preview").json()
        still = client.get(f"/cashflow/entries/{entries['spotify_a']['id']}").json()
        applied = client.post("/cashflow/rules/apply").json()

        assert (preview["applied"], applied["applied"]) == (False, True)
        assert preview["examined"] == applied["examined"] == 9
        assert preview["changes"] == applied["changes"]
        assert still["nature"] == "UNCLASSIFIED"
        assert {c["entry_id"] for c in applied["changes"]} == {
            entries["spotify_a"]["id"],
            entries["spotify_b"]["id"],
        }
        change = applied["changes"][0]
        assert (
            change["rule_id"],
            change["rule_name"],
            change["nature"],
            change["category_id"],
        ) == (
            rule["id"],
            "regra spotify",
            "EXPENSE",
            subs["id"],
        )
        assert change["match_text"] == "spotify"
        after = client.get(f"/cashflow/entries/{entries['spotify_b']['id']}").json()
        assert (after["nature"], after["category_id"], after["classified_by_rule_id"]) == (
            "EXPENSE",
            subs["id"],
            rule["id"],
        )

    def test_primeira_regra_por_prioridade_decide_sozinha(self, cf):
        client = cf["client"]
        entries = _statement(cf)
        general = cf["category"]("Compras diversas")
        tag = cf["tag"]("Online", "canal")
        cf["rule"]("amazon", priority=100, set_category_id=general["id"])
        specific = cf["rule"]("amazon br iv", priority=10, tag_ids=[tag["id"]])

        client.post("/cashflow/rules/apply")

        purchase = client.get(f"/cashflow/entries/{entries['purchase']['id']}").json()
        assert purchase["classified_by_rule_id"] == specific["id"]
        assert purchase["category_id"] is None
        assert purchase["tag_ids"] == [tag["id"]]

    def test_direcao_separa_gasto_de_recebimento_da_mesma_pessoa(self, cf):
        client = cf["client"]
        entries = _statement(cf)
        cf["entry"](PIX_FRIEND_IN.replace("recebida", "enviada"), "-30", when=D3)
        cf["rule"]("fulano de tal souza", nature="THIRD_PARTY", direction="IN")

        result = client.post("/cashflow/rules/apply").json()

        assert [c["entry_id"] for c in result["changes"]] == [entries["friend_in"]["id"]]
        assert result["changes"][0]["nature"] == "THIRD_PARTY"

    def test_regra_restrita_a_uma_conta(self, cf):
        client = cf["client"]
        cf["entry"]("Uber Uber *Trip Help.U", "-10")
        on_card = cf["entry"]("Uber Uber *Trip Help.U", "-20", acct="card")
        cf["rule"]("uber", account_id=str(cf["card"].id))

        result = client.post("/cashflow/rules/apply").json()

        assert [c["entry_id"] for c in result["changes"]] == [on_card["id"]]

    def test_classificacao_manual_nunca_e_sobrescrita(self, cf):
        client = cf["client"]
        entries = _statement(cf)
        mine = cf["category"]("Minha escolha")
        client.put(
            f"/cashflow/entries/{entries['spotify_a']['id']}/classification",
            json={"nature": "THIRD_PARTY", "category_id": mine["id"]},
        )
        client.put(f"/cashflow/entries/{entries['uber']['id']}/nature", json={"nature": "INCOME"})
        cf["rule"]("spotify")
        cf["rule"]("uber")

        result = client.post("/cashflow/rules/apply", json={"reevaluate": True}).json()

        assert [c["entry_id"] for c in result["changes"]] == [entries["spotify_b"]["id"]]
        kept = client.get(f"/cashflow/entries/{entries['spotify_a']['id']}").json()
        assert (kept["nature"], kept["category_id"]) == ("THIRD_PARTY", mine["id"])
        assert client.get(f"/cashflow/entries/{entries['uber']['id']}").json()["nature"] == "INCOME"

    def test_reclassificar_a_mao_tira_o_lancamento_do_alcance_das_regras(self, cf):
        client = cf["client"]
        entries = _statement(cf)
        rule = cf["rule"]("spotify")
        client.post("/cashflow/rules/apply")
        target = entries["spotify_a"]["id"]
        assert (
            client.get(f"/cashflow/entries/{target}").json()["classified_by_rule_id"] == rule["id"]
        )

        client.put(f"/cashflow/entries/{target}/nature", json={"nature": "ADJUSTMENT"})
        result = client.post("/cashflow/rules/apply", json={"reevaluate": True}).json()

        after = client.get(f"/cashflow/entries/{target}").json()
        assert (after["nature"], after["classified_by_rule_id"]) == ("ADJUSTMENT", None)
        assert target not in {c["entry_id"] for c in result["changes"]}

    def test_classificacao_completa_a_mao_tambem_tira_do_alcance_das_regras(self, cf):
        client = cf["client"]
        entries = _statement(cf)
        cf["rule"]("spotify")
        client.post("/cashflow/rules/apply")
        target = entries["spotify_a"]["id"]

        manual = client.put(
            f"/cashflow/entries/{target}/classification", json={"nature": "THIRD_PARTY"}
        ).json()
        result = client.post("/cashflow/rules/apply", json={"reevaluate": True}).json()

        assert manual["classified_by_rule_id"] is None
        assert target not in {c["entry_id"] for c in result["changes"]}
        assert client.get(f"/cashflow/entries/{target}").json()["nature"] == "THIRD_PARTY"

    def test_sem_reavaliar_o_que_a_regra_ja_classificou_fica_como_esta(self, cf):
        client = cf["client"]
        entries = _statement(cf)
        rule = cf["rule"]("spotify")
        client.post("/cashflow/rules/apply")
        other = cf["category"]("Outra")
        client.put(
            f"/cashflow/rules/{rule['id']}",
            json={
                "name": "spotify",
                "pattern": "spotify",
                "set_nature": "EXPENSE",
                "set_category_id": other["id"],
            },
        )

        untouched = client.post("/cashflow/rules/apply").json()
        reevaluated = client.post("/cashflow/rules/apply", json={"reevaluate": True}).json()

        assert untouched["changes"] == []
        assert untouched["examined"] == 7
        assert reevaluated["examined"] == 9
        assert {c["category_id"] for c in reevaluated["changes"]} == {other["id"]}
        assert len(reevaluated["changes"]) == 2
        assert (
            client.get(f"/cashflow/entries/{entries['spotify_a']['id']}").json()["category_id"]
            == other["id"]
        )

    def test_reavaliar_sem_regra_que_case_devolve_a_nao_classificado(self, cf):
        client = cf["client"]
        entries = _statement(cf)
        tag = cf["tag"]("Recorrente")
        rule = cf["rule"]("spotify", tag_ids=[tag["id"]])
        client.post("/cashflow/rules/apply")
        client.put(
            f"/cashflow/rules/{rule['id']}",
            json={
                "name": "spotify",
                "pattern": "spotify",
                "set_nature": "EXPENSE",
                "is_active": False,
            },
        )

        result = client.post("/cashflow/rules/apply", json={"reevaluate": True}).json()

        assert len(result["changes"]) == 2
        assert {(c["nature"], c["rule_id"]) for c in result["changes"]} == {("UNCLASSIFIED", None)}
        after = client.get(f"/cashflow/entries/{entries['spotify_a']['id']}").json()
        assert (after["nature"], after["classified_by_rule_id"], after["tag_ids"]) == (
            "UNCLASSIFIED",
            None,
            [],
        )

    def test_excluir_a_regra_mantem_a_classificacao_como_decisao_manual(self, cf):
        client = cf["client"]
        entries = _statement(cf)
        rule = cf["rule"]("spotify")
        client.post("/cashflow/rules/apply")

        assert client.delete(f"/cashflow/rules/{rule['id']}").status_code == 204
        result = client.post("/cashflow/rules/apply", json={"reevaluate": True}).json()

        cf["db"].expire_all()
        after = client.get(f"/cashflow/entries/{entries['spotify_a']['id']}").json()
        assert (after["nature"], after["classified_by_rule_id"]) == ("EXPENSE", None)
        assert result["changes"] == []

    def test_transferencia_e_estornado_nunca_sao_avaliados(self, cf):
        client = cf["client"]
        client.post(
            "/cashflow/transfers",
            json={
                "from_account_id": str(cf["checking"].id),
                "to_account_id": str(cf["card"].id),
                "entry_date": D1,
                "amount": "100",
                "description": "Pagamento de fatura",
            },
        )
        gone = cf["entry"]("Pagamento de fatura avulso", "-5")
        client.post(f"/cashflow/entries/{gone['id']}/reverse")
        cf["rule"]("pagamento de fatura")

        result = client.post("/cashflow/rules/apply").json()

        assert (result["examined"], result["changes"]) == (0, [])

    def test_filtros_de_conta_e_periodo(self, cf):
        client = cf["client"]
        entries = _statement(cf)
        cf["rule"]("spotify")

        by_date = client.post("/cashflow/rules/preview", json={"start": D2, "end": D2}).json()
        by_account = client.post(
            "/cashflow/rules/preview", json={"account_id": str(cf["checking"].id)}
        ).json()
        inverted = client.post("/cashflow/rules/preview", json={"start": D3, "end": D1})

        assert [c["entry_id"] for c in by_date["changes"]] == [entries["spotify_b"]["id"]]
        assert (by_account["examined"], by_account["changes"]) == (3, [])
        assert inverted.status_code == 400

    def test_lancamentos_de_outro_usuario_nao_sao_tocados(self, cf):
        stranger = make_user(cf["db"], email="cf2-stranger-apply@example.com")
        inst = make_institution(cf["db"], name="Banco Alheio CF2")
        account = make_typed_account(cf["db"], stranger, inst, "Alheia")
        from decimal import Decimal

        foreign = CashflowEntry(
            account_id=account.id,
            entry_date=date(2026, 1, 1),
            amount=Decimal("-12.90"),
            currency_code="BRL",
            description="Dm*Spotify",
            source="MANUAL",
            nature="UNCLASSIFIED",
        )
        cf["db"].add(foreign)
        cf["db"].flush()
        cf["rule"]("spotify")

        result = cf["client"].post("/cashflow/rules/apply").json()

        cf["db"].refresh(foreign)
        assert result["examined"] == 0
        assert foreign.nature.value == "UNCLASSIFIED"


class TestQuebraPorCategoria:
    def test_gasto_por_categoria_fecha_com_o_resumo(self, cf):
        client = cf["client"]
        _statement(cf)
        food = cf["category"]("Alimentação")
        market = cf["category"]("Mercado", food["id"])
        subs = cf["category"]("Assinaturas")
        cf["rule"]("central", set_category_id=market["id"])
        cf["rule"]("spotify", set_category_id=subs["id"])
        cf["rule"]("amazon")
        cf["rule"]("fulano de tal", nature="THIRD_PARTY")
        client.post("/cashflow/rules/apply")

        breakdown = client.get(f"/cashflow/summary/categories?start={D1}&end={D3}").json()
        summary = client.get(f"/cashflow/summary?start={D1}&end={D3}").json()

        (block,) = breakdown["totals_by_currency"]
        rows = {r["category_name"]: r for r in block["categories"]}
        assert block["currency_code"] == "BRL"
        assert block["expenses"] == summary["totals_by_currency"][0]["expenses"] == "80.1000"
        assert rows["Mercado"]["own_expenses"] == "54.3000"
        assert rows["Mercado"]["parent_id"] == food["id"]
        assert (rows["Alimentação"]["own_expenses"], rows["Alimentação"]["total_expenses"]) == (
            "0.0000",
            "54.3000",
        )
        assert rows["Assinaturas"]["own_expenses"] == "25.8000"
        assert rows[None]["own_expenses"] == "0.0000"
        assert [r["category_name"] for r in block["categories"]] == [
            "Alimentação",
            "Assinaturas",
            "Mercado",
            None,
        ]
        assert summary["totals_by_currency"][0]["third_party_net"] == "50.0000"
        assert summary["totals_by_currency"][0]["unclassified_net"] == "-162.1500"

    def test_quebra_que_nao_fecha_com_o_resumo_nao_devolve_numero(self, cf, monkeypatch):
        from decimal import Decimal

        from app.domain.cashflow_engine import CategoryBreakdownCalculator, CategoryTotals
        from app.services import cashflow_classification_service as service

        cf["entry"]("Loja", "-10", nature="EXPENSE")
        wrong = Decimal("9.9900")
        monkeypatch.setattr(
            CategoryBreakdownCalculator,
            "calculate",
            staticmethod(
                lambda *_args, **_kwargs: {
                    "BRL": [CategoryTotals(None, wrong, wrong * 0, wrong, wrong * 0)]
                }
            ),
        )

        with pytest.raises(RuntimeError, match="não fecha com o resumo"):
            service.get_category_breakdown(
                cf["db"], cf["user"].id, TODAY - timedelta(days=9), TODAY
            )

    def test_periodo_invertido_e_400_e_sem_lancamentos_e_vazio(self, cf):
        client = cf["client"]

        assert client.get(f"/cashflow/summary/categories?start={D3}&end={D1}").status_code == 400
        assert (
            client.get(f"/cashflow/summary/categories?start={D1}&end={D3}").json()[
                "totals_by_currency"
            ]
            == []
        )
