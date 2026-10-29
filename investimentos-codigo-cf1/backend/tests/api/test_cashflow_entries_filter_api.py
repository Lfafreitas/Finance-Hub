"""CF-5: filtros e contagem da listagem de lançamentos. A contagem
responde sempre sobre o mesmo conjunto que a listagem devolve.
"""

from app.models.cashflow_classification import CashflowCategory
from tests.api.test_cashflow_classification_api import D1, D2, D3, cf  # noqa: F401
from tests.test_persistence import make_user


def _classify(cf, entry, nature, category=None):  # noqa: F811
    response = cf["client"].put(
        f"/cashflow/entries/{entry['id']}/classification",
        json={"nature": nature, "category_id": category},
    )
    assert response.status_code == 200, response.text


def _both(cf, **params):  # noqa: F811
    """Descrições da listagem + total da contagem, com os mesmos filtros."""
    listed = cf["client"].get("/cashflow/entries", params=params)
    counted = cf["client"].get("/cashflow/entries/count", params=params)
    assert listed.status_code == 200, listed.text
    assert counted.status_code == 200, counted.text
    return sorted(e["description"] for e in listed.json()), counted.json()["total"]


def _world(cf):  # noqa: F811
    food = cf["category"]("Alimentação")
    market = cf["category"]("Mercado", food["id"])
    home = cf["category"]("Moradia")
    a = cf["entry"]("Mercado Exemplo", "-100", when=D1)
    b = cf["entry"]("Padaria 100% Trigo", "-20", when=D2)
    c = cf["entry"]("Aluguel", "-900", when=D3)
    d = cf["entry"]("Salário", "3000", when=D3)
    e = cf["entry"]("Compra_no cartão", "-50", acct="card", when=D2)
    _classify(cf, a, "EXPENSE", market["id"])
    _classify(cf, b, "EXPENSE", food["id"])
    _classify(cf, c, "EXPENSE", home["id"])
    _classify(cf, d, "INCOME")
    return {"food": food, "market": market, "home": home, "a": a, "b": b, "c": c, "d": d, "e": e}


class TestFiltros:
    def test_sem_filtro_lista_e_conta_tudo(self, cf):  # noqa: F811
        _world(cf)

        names, total = _both(cf)

        assert total == 5
        assert len(names) == 5

    def test_por_natureza(self, cf):  # noqa: F811
        _world(cf)

        assert _both(cf, nature="EXPENSE") == (
            ["Aluguel", "Mercado Exemplo", "Padaria 100% Trigo"],
            3,
        )
        assert _both(cf, nature="INCOME") == (["Salário"], 1)
        assert _both(cf, nature="UNCLASSIFIED") == (["Compra_no cartão"], 1)

    def test_categoria_mae_inclui_as_filhas_e_filha_nao_inclui_a_mae(self, cf):  # noqa: F811
        w = _world(cf)

        assert _both(cf, category_id=w["food"]["id"]) == (
            ["Mercado Exemplo", "Padaria 100% Trigo"],
            2,
        )
        assert _both(cf, category_id=w["market"]["id"]) == (["Mercado Exemplo"], 1)
        assert _both(cf, category_id=w["home"]["id"]) == (["Aluguel"], 1)

    def test_sem_categoria(self, cf):  # noqa: F811
        _world(cf)

        assert _both(cf, uncategorized=True) == (["Compra_no cartão", "Salário"], 2)
        assert _both(cf, uncategorized=True, nature="INCOME") == (["Salário"], 1)

    def test_busca_ignora_maiusculas_e_combina_com_conta_e_periodo(self, cf):  # noqa: F811
        _world(cf)

        assert _both(cf, search="mercado") == (["Mercado Exemplo"], 1)
        assert _both(cf, search="  ALUGUEL ") == (["Aluguel"], 1)
        assert _both(cf, search="a", account_id=str(cf["card"].id)) == (["Compra_no cartão"], 1)
        assert _both(cf, search="a", start=D3, end=D3) == (["Aluguel", "Salário"], 2)
        assert _both(cf, search="não existe") == ([], 0)

    def test_busca_trata_curingas_como_texto(self, cf):  # noqa: F811
        _world(cf)

        assert _both(cf, search="100%") == (["Padaria 100% Trigo"], 1)
        assert _both(cf, search="%") == (["Padaria 100% Trigo"], 1)
        assert _both(cf, search="_") == (["Compra_no cartão"], 1)
        assert _both(cf, search="a_u") == ([], 0)

    def test_busca_em_branco_e_o_mesmo_que_sem_busca(self, cf):  # noqa: F811
        _world(cf)

        assert _both(cf, search="   ")[1] == 5

    def test_estornado_so_entra_quando_pedido(self, cf):  # noqa: F811
        w = _world(cf)
        assert cf["client"].post(f"/cashflow/entries/{w['c']['id']}/reverse").status_code == 200

        assert _both(cf, nature="EXPENSE")[1] == 2
        assert _both(cf, nature="EXPENSE", include_reversed=True)[1] == 3

    def test_contagem_ignora_a_paginacao(self, cf):  # noqa: F811
        _world(cf)
        client = cf["client"]

        page = client.get("/cashflow/entries", params={"limit": 2, "offset": 2}).json()

        assert len(page) == 2
        assert client.get("/cashflow/entries/count").json() == {"total": 5}


class TestErros:
    def test_categoria_e_sem_categoria_juntos_e_400(self, cf):  # noqa: F811
        w = _world(cf)
        params = {"category_id": w["food"]["id"], "uncategorized": True}

        for path in ("/cashflow/entries", "/cashflow/entries/count"):
            response = cf["client"].get(path, params=params)
            assert response.status_code == 400
            assert "não os dois" in response.json()["detail"]

    def test_categoria_inexistente_ou_de_outro_usuario_e_404(self, cf):  # noqa: F811
        stranger = make_user(cf["db"], email="cf5-stranger@example.com")
        foreign = CashflowCategory(user_id=stranger.id, name="Alheia")
        cf["db"].add(foreign)
        cf["db"].flush()

        for path in ("/cashflow/entries", "/cashflow/entries/count"):
            response = cf["client"].get(path, params={"category_id": str(foreign.id)})
            assert response.status_code == 404

    def test_periodo_invertido_e_400_e_natureza_invalida_e_422(self, cf):  # noqa: F811
        client = cf["client"]

        assert (
            client.get("/cashflow/entries/count", params={"start": D3, "end": D1}).status_code
            == 400
        )
        assert client.get("/cashflow/entries/count", params={"nature": "X"}).status_code == 422
        assert client.get("/cashflow/entries", params={"search": "x" * 101}).status_code == 422

    def test_sem_conta_de_caixa_conta_zero(self, api_client):
        client, _ = api_client

        assert client.get("/cashflow/entries/count").json() == {"total": 0}


class TestPreviaDasRegras:
    def test_cada_mudanca_traz_a_moeda_e_a_data_do_lancamento(self, cf):  # noqa: F811
        usd = cf["account"]("Conta Dólar", currency="USD")
        cf["usd"] = usd
        cf["entry"]("Spotify", "-9.99", acct="usd", when=D2)
        cf["entry"]("Spotify", "-21.90", when=D1)
        cf["rule"]("spotify")

        changes = cf["client"].post("/cashflow/rules/preview").json()["changes"]

        assert sorted((c["currency_code"], c["entry_date"], c["amount"]) for c in changes) == [
            ("BRL", D1, "-21.9000"),
            ("USD", D2, "-9.9900"),
        ]
