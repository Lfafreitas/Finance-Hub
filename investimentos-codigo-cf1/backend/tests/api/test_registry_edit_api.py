"""Edição e exclusão de cadastros: o que muda sempre, o que só muda
enquanto não foi usado, e o que nunca se exclui.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import Account, Asset, AssetPrice, Institution, Portfolio, Transaction
from app.models.enums import AccountType, PriceSource, TransactionSource, TransactionType
from tests.cashflow_helpers import make_typed_account
from tests.test_persistence import make_asset, make_institution, make_user

YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


@pytest.fixture()
def reg(api_client, db_session):
    client, user = api_client
    inst = make_institution(db_session, name=f"Inst Edit {uuid.uuid4().hex[:6]}")
    return {"client": client, "user": user, "inst": inst, "db": db_session}


def _account_body(inst, **overrides):
    body = {
        "name": "Conta Editada",
        "institution_id": str(inst.id),
        "currency_code": "BRL",
        "account_type": "BROKERAGE",
    }
    body.update(overrides)
    return body


def _asset_body(**overrides):
    body = {
        "ticker": "EDIT3",
        "name": "Ativo Editado",
        "asset_class_code": "STOCK_BR",
        "country": "BR",
        "currency_code": "BRL",
    }
    body.update(overrides)
    return body


def _deposit(db, account):
    db.add(
        Transaction(
            account_id=account.id,
            transaction_type=TransactionType.DEPOSIT,
            gross_amount=Decimal(100),
            currency_code=account.currency_code,
            transaction_date=date(2026, 1, 1),
            source=TransactionSource.MANUAL,
        )
    )
    db.flush()


def _cash_entry(client, account):
    response = client.post(
        "/cashflow/entries",
        json={
            "account_id": str(account.id),
            "entry_date": YESTERDAY,
            "amount": "-10",
            "description": "x",
        },
    )
    assert response.status_code == 201, response.text


class TestInstituicao:
    def test_edita_nome_tipo_e_pais(self, reg):
        response = reg["client"].put(
            f"/institutions/{reg['inst'].id}",
            json={"name": "  Banco Novo  ", "institution_type": "BANK", "country": "us"},
        )

        assert response.status_code == 200, response.text
        assert response.json()["name"] == "Banco Novo"
        assert response.json()["institution_type"] == "BANK"
        assert response.json()["country"] == "US"

    def test_exclui_instituicao_sem_contas(self, reg):
        response = reg["client"].delete(f"/institutions/{reg['inst'].id}")

        assert response.status_code == 204
        assert reg["db"].get(Institution, reg["inst"].id) is None

    def test_instituicao_com_conta_nao_e_excluida(self, reg):
        make_typed_account(reg["db"], reg["user"], reg["inst"], "Conta X", AccountType.BROKERAGE)

        response = reg["client"].delete(f"/institutions/{reg['inst'].id}")

        assert response.status_code == 409
        assert "tem contas" in response.json()["detail"]
        assert reg["db"].get(Institution, reg["inst"].id) is not None

    def test_instituicao_inexistente_e_404(self, reg):
        ghost = uuid.uuid4()
        body = {"name": "x", "institution_type": "BANK", "country": "BR"}

        assert reg["client"].put(f"/institutions/{ghost}", json=body).status_code == 404
        assert reg["client"].delete(f"/institutions/{ghost}").status_code == 404


class TestCarteira:
    def test_renomeia(self, reg):
        client = reg["client"]
        created = client.post("/portfolios", json={"name": "Antiga"}).json()

        response = client.put(f"/portfolios/{created['id']}", json={"name": "Nova"})

        assert response.status_code == 200
        assert response.json() == {"id": created["id"], "name": "Nova"}

    def test_nome_duplicado_e_409_e_o_nome_antigo_fica(self, reg):
        client = reg["client"]
        client.post("/portfolios", json={"name": "Ocupado"})
        created = client.post("/portfolios", json={"name": "Livre"}).json()

        response = client.put(f"/portfolios/{created['id']}", json={"name": "Ocupado"})

        assert response.status_code == 409
        assert {p["name"] for p in client.get("/portfolios").json()} == {"Ocupado", "Livre"}

    def test_exclui_carteira_sem_contas_e_recusa_com_conta(self, reg):
        client = reg["client"]
        empty = client.post("/portfolios", json={"name": "Vazia"}).json()
        used = client.post("/portfolios", json={"name": "Usada"}).json()
        client.post("/accounts", json=_account_body(reg["inst"], portfolio_id=used["id"]))

        assert client.delete(f"/portfolios/{empty['id']}").status_code == 204
        refused = client.delete(f"/portfolios/{used['id']}")

        assert refused.status_code == 409
        assert "contas vinculadas" in refused.json()["detail"]
        assert [p["name"] for p in client.get("/portfolios").json()] == ["Usada"]

    def test_carteira_de_outro_usuario_e_404(self, reg):
        stranger = make_user(reg["db"], email="edit-stranger@example.com")
        foreign = Portfolio(user_id=stranger.id, name="Alheia")
        reg["db"].add(foreign)
        reg["db"].flush()

        assert reg["client"].put(f"/portfolios/{foreign.id}", json={"name": "x"}).status_code == 404
        assert reg["client"].delete(f"/portfolios/{foreign.id}").status_code == 404
        assert reg["db"].get(Portfolio, foreign.id).name == "Alheia"


class TestConta:
    def test_edita_nome_instituicao_e_carteira(self, reg):
        client = reg["client"]
        account = make_typed_account(
            reg["db"], reg["user"], reg["inst"], "Conta A", AccountType.BROKERAGE
        )
        other_inst = make_institution(reg["db"], name="Outra Inst Edit")
        portfolio = client.post("/portfolios", json={"name": "LP Edit"}).json()

        response = client.put(
            f"/accounts/{account.id}",
            json=_account_body(other_inst, name="Conta B", portfolio_id=portfolio["id"]),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["name"] == "Conta B"
        assert body["institution_name"] == "Outra Inst Edit"
        assert body["portfolio_id"] == portfolio["id"]

    def test_conta_sem_uso_troca_moeda_e_livro(self, reg):
        account = make_typed_account(
            reg["db"], reg["user"], reg["inst"], "Conta Vazia", AccountType.BROKERAGE
        )

        response = reg["client"].put(
            f"/accounts/{account.id}",
            json=_account_body(reg["inst"], currency_code="USD", account_type="CHECKING"),
        )

        assert response.status_code == 200, response.text
        assert response.json()["currency_code"] == "USD"
        assert response.json()["account_type"] == "CHECKING"

    def test_conta_com_transaction_nao_troca_moeda_nem_livro_mas_troca_nome(self, reg):
        account = make_typed_account(
            reg["db"], reg["user"], reg["inst"], "Conta Usada", AccountType.BROKERAGE
        )
        _deposit(reg["db"], account)
        url = f"/accounts/{account.id}"

        currency = reg["client"].put(url, json=_account_body(reg["inst"], currency_code="USD"))
        ledger = reg["client"].put(url, json=_account_body(reg["inst"], account_type="CHECKING"))
        rename = reg["client"].put(url, json=_account_body(reg["inst"], name="Renomeada"))

        assert currency.status_code == 409
        assert "moeda" in currency.json()["detail"]
        assert ledger.status_code == 409
        assert "tipo entre investimentos e caixa" in ledger.json()["detail"]
        assert rename.status_code == 200
        reg["db"].refresh(account)
        assert (account.name, account.currency_code, account.account_type) == (
            "Renomeada",
            "BRL",
            AccountType.BROKERAGE,
        )

    def test_conta_de_caixa_com_lancamento_troca_entre_tipos_de_caixa(self, reg):
        account = make_typed_account(reg["db"], reg["user"], reg["inst"], "Corrente Edit")
        _cash_entry(reg["client"], account)
        url = f"/accounts/{account.id}"

        to_savings = reg["client"].put(url, json=_account_body(reg["inst"], account_type="SAVINGS"))
        to_brokerage = reg["client"].put(
            url, json=_account_body(reg["inst"], account_type="BROKERAGE")
        )

        assert to_savings.status_code == 200
        assert to_savings.json()["account_type"] == "SAVINGS"
        assert to_brokerage.status_code == 409
        assert "tipo entre investimentos e caixa" in to_brokerage.json()["detail"]

    def test_corretora_que_e_contraparte_de_aporte_nao_vira_conta_de_caixa(self, reg):
        client = reg["client"]
        checking = make_typed_account(reg["db"], reg["user"], reg["inst"], "Corrente Aporte")
        brokerage = make_typed_account(
            reg["db"], reg["user"], reg["inst"], "Corretora Aporte", AccountType.BROKERAGE
        )
        transfer = client.post(
            "/cashflow/transfers",
            json={
                "from_account_id": str(checking.id),
                "to_account_id": str(brokerage.id),
                "entry_date": YESTERDAY,
                "amount": "700",
                "description": "aporte",
            },
        )
        assert transfer.status_code == 201

        response = client.put(
            f"/accounts/{brokerage.id}",
            json=_account_body(reg["inst"], name="Corretora Aporte", account_type="CHECKING"),
        )

        assert response.status_code == 409
        assert "tipo entre investimentos e caixa" in response.json()["detail"]
        assert client.delete(f"/accounts/{brokerage.id}").status_code == 409

    def test_carteira_em_conta_de_caixa_e_400(self, reg):
        client = reg["client"]
        account = make_typed_account(reg["db"], reg["user"], reg["inst"], "Corrente Cart")
        portfolio = client.post("/portfolios", json={"name": "Cart Edit"}).json()

        response = client.put(
            f"/accounts/{account.id}",
            json=_account_body(reg["inst"], account_type="CHECKING", portfolio_id=portfolio["id"]),
        )

        assert response.status_code == 400

    def test_nome_duplicado_na_instituicao_e_409(self, reg):
        make_typed_account(reg["db"], reg["user"], reg["inst"], "Ocupada", AccountType.BROKERAGE)
        account = make_typed_account(
            reg["db"], reg["user"], reg["inst"], "Livre", AccountType.BROKERAGE
        )

        response = reg["client"].put(
            f"/accounts/{account.id}", json=_account_body(reg["inst"], name="Ocupada")
        )

        assert response.status_code == 409
        reg["db"].refresh(account)
        assert account.name == "Livre"

    def test_exclui_conta_sem_uso_e_recusa_conta_usada(self, reg):
        empty = make_typed_account(
            reg["db"], reg["user"], reg["inst"], "Sem uso", AccountType.BROKERAGE
        )
        used = make_typed_account(
            reg["db"], reg["user"], reg["inst"], "Com uso", AccountType.BROKERAGE
        )
        _deposit(reg["db"], used)

        assert reg["client"].delete(f"/accounts/{empty.id}").status_code == 204
        refused = reg["client"].delete(f"/accounts/{used.id}")

        assert refused.status_code == 409
        assert "não pode ser excluída" in refused.json()["detail"]
        assert reg["db"].get(Account, empty.id) is None
        assert reg["db"].get(Account, used.id) is not None

    def test_conta_de_outro_usuario_e_404_e_fica_intacta(self, reg):
        stranger = make_user(reg["db"], email="edit-stranger2@example.com")
        foreign = make_typed_account(
            reg["db"], stranger, reg["inst"], "Alheia", AccountType.BROKERAGE
        )

        put = reg["client"].put(f"/accounts/{foreign.id}", json=_account_body(reg["inst"]))
        delete = reg["client"].delete(f"/accounts/{foreign.id}")

        assert (put.status_code, delete.status_code) == (404, 404)
        reg["db"].refresh(foreign)
        assert foreign.name == "Alheia"

    def test_instituicao_ou_moeda_inexistente_e_400(self, reg):
        account = make_typed_account(
            reg["db"], reg["user"], reg["inst"], "Conta Ref", AccountType.BROKERAGE
        )
        url = f"/accounts/{account.id}"

        bad_inst = reg["client"].put(
            url, json=_account_body(reg["inst"], institution_id=str(uuid.uuid4()))
        )
        bad_currency = reg["client"].put(url, json=_account_body(reg["inst"], currency_code="ZZZ"))

        assert (bad_inst.status_code, bad_currency.status_code) == (400, 400)


class TestAtivo:
    def test_edita_ticker_nome_classe_e_pais(self, reg):
        asset = make_asset(reg["db"], ticker="OLD3")

        response = reg["client"].put(
            f"/assets/{asset.id}",
            json=_asset_body(ticker="new3", name="Novo Nome", asset_class_code="fii"),
        )

        assert response.status_code == 200, response.text
        assert response.json()["ticker"] == "NEW3"
        assert response.json()["name"] == "Novo Nome"
        assert response.json()["asset_class_code"] == "FII"

    def test_ativo_sem_uso_troca_de_moeda(self, reg):
        asset = make_asset(reg["db"], ticker="CUR3")

        response = reg["client"].put(
            f"/assets/{asset.id}", json=_asset_body(ticker="CUR3", currency_code="USD")
        )

        assert response.status_code == 200
        assert response.json()["currency_code"] == "USD"

    def test_ativo_com_transaction_nao_troca_moeda_mas_troca_ticker(self, reg):
        asset = make_asset(reg["db"], ticker="USED3")
        account = make_typed_account(
            reg["db"], reg["user"], reg["inst"], "Conta Ativo", AccountType.BROKERAGE
        )
        reg["db"].add(
            Transaction(
                account_id=account.id,
                asset_id=asset.id,
                transaction_type=TransactionType.BUY,
                quantity=Decimal(10),
                unit_price=Decimal(5),
                gross_amount=Decimal(50),
                currency_code="BRL",
                transaction_date=date(2026, 1, 1),
                source=TransactionSource.MANUAL,
            )
        )
        reg["db"].flush()
        url = f"/assets/{asset.id}"

        currency = reg["client"].put(url, json=_asset_body(ticker="USED3", currency_code="USD"))
        ticker = reg["client"].put(url, json=_asset_body(ticker="USED4"))
        delete = reg["client"].delete(url)

        assert currency.status_code == 409
        assert "moeda" in currency.json()["detail"]
        assert ticker.status_code == 200
        assert delete.status_code == 409
        reg["db"].refresh(asset)
        assert (asset.ticker, asset.currency_code) == ("USED4", "BRL")

    def test_ativo_com_cotacao_nao_troca_moeda_nem_e_excluido(self, reg):
        asset = make_asset(reg["db"], ticker="PRC3")
        reg["db"].add(
            AssetPrice(
                asset_id=asset.id,
                price_date=date(2026, 1, 2),
                price=Decimal(10),
                currency_code="BRL",
                source=PriceSource.MANUAL,
            )
        )
        reg["db"].flush()
        url = f"/assets/{asset.id}"

        currency = reg["client"].put(url, json=_asset_body(ticker="PRC3", currency_code="USD"))
        delete = reg["client"].delete(url)

        assert (currency.status_code, delete.status_code) == (409, 409)

    def test_ticker_duplicado_no_pais_e_409(self, reg):
        make_asset(reg["db"], ticker="DUP3")
        asset = make_asset(reg["db"], ticker="FREE3")

        response = reg["client"].put(f"/assets/{asset.id}", json=_asset_body(ticker="DUP3"))

        assert response.status_code == 409
        reg["db"].refresh(asset)
        assert asset.ticker == "FREE3"

    def test_exclui_ativo_sem_uso(self, reg):
        asset = make_asset(reg["db"], ticker="DEL3")

        assert reg["client"].delete(f"/assets/{asset.id}").status_code == 204
        assert reg["db"].get(Asset, asset.id) is None

    def test_classe_ou_moeda_inexistente_e_400_e_ativo_inexistente_404(self, reg):
        asset = make_asset(reg["db"], ticker="REF3")
        url = f"/assets/{asset.id}"

        assert reg["client"].put(url, json=_asset_body(asset_class_code="NADA")).status_code == 400
        assert reg["client"].put(url, json=_asset_body(currency_code="ZZZ")).status_code == 400
        assert reg["client"].put(f"/assets/{uuid.uuid4()}", json=_asset_body()).status_code == 404
        assert reg["client"].delete(f"/assets/{uuid.uuid4()}").status_code == 404


class TestCors:
    def test_delete_e_liberado_para_a_origem_do_frontend(self, reg):
        response = reg["client"].options(
            "/assets/x",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "DELETE",
            },
        )

        assert response.status_code == 200
        assert "DELETE" in response.headers["access-control-allow-methods"]
