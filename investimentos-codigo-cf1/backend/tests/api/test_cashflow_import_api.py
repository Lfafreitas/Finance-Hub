"""CF-3: importação do extrato e da fatura, deduplicação, saldo,
casamento de pagamento de fatura e ligação de transferências.
"""

import uuid
from datetime import date, timedelta

import pytest

from app.models import CashflowEntry
from app.models.cashflow_import_batch import CashflowImportBatch
from app.models.enums import AccountType
from tests.cashflow_helpers import make_typed_account
from tests.services.test_cashflow_import_parsers import ACCOUNT_CSV as _ACCOUNT_CSV
from tests.services.test_cashflow_import_parsers import CARD_CSV as _CARD_CSV
from tests.services.test_cashflow_import_parsers import OFX as _OFX
from tests.test_persistence import make_institution, make_user

# Mesmos arquivos do teste de leitura, um ano antes: independem do
# relógio de quem roda.
ACCOUNT_CSV = _ACCOUNT_CSV.replace(b"/2026", b"/2025")
CARD_CSV = _CARD_CSV.replace(b"2026-", b"2025-")
OFX = _OFX.replace(b"2026", b"2025")


@pytest.fixture()
def imp(api_client, db_session):
    client, user = api_client
    inst = make_institution(db_session, name=f"Nubank {uuid.uuid4().hex[:6]}")

    def account(name, account_type=AccountType.CHECKING, currency="BRL", institution=inst):
        return make_typed_account(db_session, user, institution, name, account_type, currency)

    world = {
        "client": client,
        "user": user,
        "db": db_session,
        "inst": inst,
        "account": account,
        "checking": account("Conta"),
        "card": account("Cartão", AccountType.CREDIT_CARD),
        "brokerage": account("Corretora", AccountType.BROKERAGE),
    }

    def preview(content, acct="checking", name="arquivo.csv", **form):
        return client.post(
            "/cashflow/imports/preview",
            data={"account_id": str(world[acct].id), **form},
            files={"file": (name, content, "application/octet-stream")},
        )

    def commit(body, include=None, **extra):
        rows = body["rows"]
        chosen = (
            include
            if include is not None
            else [r["row_index"] for r in rows if not r["error"] and not r["is_duplicate"]]
        )
        payload = {k: v for k, v in body.items() if k != "file_already_imported"}
        return client.post(
            "/cashflow/imports/commit", json={**payload, "included_row_indexes": chosen, **extra}
        )

    def entries(acct=None, **params):
        query = {"limit": 500, **params}
        if acct:
            query["account_id"] = str(world[acct].id)
        return client.get("/cashflow/entries", params=query).json()

    world.update(preview=preview, commit=commit, entries=entries)
    return world


class TestPrevia:
    def test_mostra_as_linhas_sem_gravar_nada(self, imp):
        response = imp["preview"](ACCOUNT_CSV, name="NU_extrato.csv")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["profile"] == "NUBANK_ACCOUNT_CSV"
        assert body["file_name"] == "NU_extrato.csv"
        assert len(body["file_sha256"]) == 64
        assert (body["period_start"], body["period_end"]) == ("2025-08-02", "2025-08-30")
        assert body["statement_balance"] is None
        assert body["file_already_imported"] is False
        assert [r["amount"] for r in body["rows"]] == ["-650.40", "1380.25", "-54.30", "-1190.60"]
        assert body["rows"][2]["match_text"] == "compra no debito super central"
        assert body["rows"][0]["external_id"] == "0a000001-0000-4000-8000-000000000001"
        assert {(r["is_duplicate"], r["error"]) for r in body["rows"]} == {(False, None)}
        assert imp["entries"]() == []
        assert imp["db"].query(CashflowImportBatch).count() == 0

    def test_ofx_traz_saldo_e_periodo(self, imp):
        body = imp["preview"](OFX, name="extrato.ofx").json()

        assert body["profile"] == "NUBANK_ACCOUNT_OFX"
        assert (body["statement_balance"], body["statement_balance_date"]) == (
            "89.20",
            "2025-08-31",
        )
        assert (body["period_start"], body["period_end"]) == ("2025-08-01", "2025-08-31")

    def test_fatura_tem_chave_por_conteudo_e_sinal_do_livro(self, imp):
        body = imp["preview"](CARD_CSV, acct="card").json()

        rows = body["rows"]
        assert body["profile"] == "NUBANK_CARD_CSV"
        assert [r["amount"] for r in rows] == ["-29.80", "175.45", "-175.45", "-49.90", "1190.60"]
        assert {r["external_id"] for r in rows} == {None}
        assert all(r["import_fingerprint"].endswith(":0") for r in rows)
        assert len({r["import_fingerprint"] for r in rows}) == 5

    def test_compras_identicas_no_mesmo_dia_sao_linhas_distintas(self, imp):
        content = b'date,title,amount\n2025-09-01,Padaria,"10,00"\n2025-09-01,Padaria,"10,00"\n'

        rows = imp["preview"](content, acct="card").json()["rows"]

        assert [r["import_fingerprint"][-2:] for r in rows] == [":0", ":1"]
        assert rows[0]["import_fingerprint"][:-2] == rows[1]["import_fingerprint"][:-2]

    def test_regra_existente_aparece_como_sugestao(self, imp):
        client = imp["client"]
        category = client.post("/cashflow/categories", json={"name": "Mercado"}).json()
        rule = client.post(
            "/cashflow/rules",
            json={
                "name": "Central",
                "pattern": "central",
                "set_nature": "EXPENSE",
                "set_category_id": category["id"],
            },
        ).json()

        rows = imp["preview"](ACCOUNT_CSV).json()["rows"]

        assert (rows[2]["suggested_rule_id"], rows[2]["suggested_rule_name"]) == (
            rule["id"],
            "Central",
        )
        assert (rows[2]["suggested_nature"], rows[2]["suggested_category_id"]) == (
            "EXPENSE",
            category["id"],
        )
        assert rows[0]["suggested_rule_id"] is None

    def test_arquivo_de_cartao_em_conta_e_vice_versa_e_400(self, imp):
        card_in_account = imp["preview"](CARD_CSV, acct="checking")
        account_in_card = imp["preview"](ACCOUNT_CSV, acct="card")

        assert (card_in_account.status_code, account_in_card.status_code) == (400, 400)
        assert "cartão de crédito" in card_in_account.json()["detail"]

    def test_conta_de_investimentos_inexistente_ou_alheia(self, imp):
        stranger = make_user(imp["db"], email="imp-stranger@example.com")
        imp["foreign"] = make_typed_account(imp["db"], stranger, imp["inst"], "Alheia")

        assert imp["preview"](ACCOUNT_CSV, acct="brokerage").status_code == 400
        assert imp["preview"](ACCOUNT_CSV, acct="foreign").status_code == 404

    def test_moeda_do_ofx_diferente_da_conta_e_400(self, imp):
        imp["usd"] = imp["account"]("Conta USD", currency="USD")

        response = imp["preview"](OFX, acct="usd")

        assert response.status_code == 400
        assert "BRL" in response.json()["detail"]

    def test_formato_desconhecido_e_400_e_perfil_forcado_errado_tambem(self, imp):
        unknown = imp["preview"](b"a,b,c\n1,2,3\n")
        forced = imp["preview"](ACCOUNT_CSV, profile="NUBANK_ACCOUNT_OFX")

        assert (unknown.status_code, forced.status_code) == (400, 400)

    def test_linha_com_data_futura_vira_erro(self, imp):
        future = (date.today() + timedelta(days=2)).strftime("%d/%m/%Y")
        content = f"Data,Valor,Identificador,Descrição\n{future},-10.00,id-f,Futuro\n".encode()

        rows = imp["preview"](content).json()["rows"]

        assert rows[0]["error"] == "data no futuro"

    def test_identificador_repetido_no_arquivo_vira_erro_na_segunda_linha(self, imp):
        content = (
            "Data,Valor,Identificador,Descrição\n"
            "05/08/2025,-10.00,mesmo-id,Primeira\n"
            "06/08/2025,-20.00,mesmo-id,Segunda\n"
        ).encode()

        rows = imp["preview"](content).json()["rows"]

        assert [r["error"] for r in rows] == [None, "identificador repetido dentro do arquivo"]


class TestCommit:
    def test_grava_as_linhas_como_fato_importado(self, imp):
        body = imp["preview"](ACCOUNT_CSV, name="NU_extrato.csv").json()

        response = imp["commit"](body)

        assert response.status_code == 200, response.text
        result = response.json()
        assert (result["imported_count"], result["not_included_count"]) == (4, 0)
        assert result["statement_balance"] is None
        assert result["balance_difference"] is None
        entries = imp["entries"]()
        assert len(entries) == 4
        assert {e["source"] for e in entries} == {"IMPORT_CSV"}
        assert {e["nature"] for e in entries} == {"UNCLASSIFIED"}
        assert {e["currency_code"] for e in entries} == {"BRL"}
        (batch,) = imp["client"].get("/cashflow/imports").json()
        assert (batch["id"], batch["file_name"]) == (result["batch_id"], "NU_extrato.csv")
        assert (batch["rows_total"], batch["rows_imported"]) == (4, 4)
        assert batch["file_sha256"] == body["file_sha256"]

    def test_reimportar_o_mesmo_arquivo_nao_duplica(self, imp):
        imp["commit"](imp["preview"](ACCOUNT_CSV).json())

        again = imp["preview"](ACCOUNT_CSV).json()
        forced = imp["commit"](again, include=[0])

        assert again["file_already_imported"] is True
        assert {r["is_duplicate"] for r in again["rows"]} == {True}
        assert forced.status_code == 422
        assert "já foi importada" in forced.json()["detail"]
        assert len(imp["entries"]()) == 4

    def test_csv_e_depois_ofx_do_mesmo_mes_nao_duplicam(self, imp):
        imp["commit"](imp["preview"](ACCOUNT_CSV).json(), include=[0, 1, 3])

        ofx = imp["preview"](OFX, name="extrato.ofx").json()

        assert ofx["file_already_imported"] is False
        assert [r["is_duplicate"] for r in ofx["rows"]] == [True, False]
        result = imp["commit"](ofx).json()
        assert result["imported_count"] == 1
        assert len(imp["entries"]()) == 4
        assert {r["is_duplicate"] for r in imp["preview"](ACCOUNT_CSV).json()["rows"]} == {True}

    def test_fatura_reimportada_nao_duplica(self, imp):
        imp["commit"](imp["preview"](CARD_CSV, acct="card").json())

        again = imp["preview"](CARD_CSV, acct="card").json()

        assert {r["is_duplicate"] for r in again["rows"]} == {True}
        assert len(imp["entries"]("card")) == 5

    def test_lancamento_estornado_nao_volta_na_reimportacao(self, imp):
        imp["commit"](imp["preview"](ACCOUNT_CSV).json())
        target = next(e for e in imp["entries"]() if e["amount"] == "-54.3000")
        imp["client"].post(f"/cashflow/entries/{target['id']}/reverse")

        again = imp["preview"](ACCOUNT_CSV).json()

        assert {r["is_duplicate"] for r in again["rows"]} == {True}

    def test_so_as_linhas_escolhidas_entram(self, imp):
        body = imp["preview"](ACCOUNT_CSV).json()

        result = imp["commit"](body, include=[1, 2]).json()

        assert (result["imported_count"], result["not_included_count"]) == (2, 2)
        assert sorted(e["amount"] for e in imp["entries"]()) == ["-54.3000", "1380.2500"]

    def test_linha_com_erro_incluida_derruba_o_lote_inteiro(self, imp):
        content = (
            "Data,Valor,Identificador,Descrição\n"
            "05/08/2025,-10.00,id-1,Boa\n"
            "05/08/2025,zero,id-2,Ruim\n"
        ).encode()
        body = imp["preview"](content).json()

        response = imp["commit"](body, include=[0, 1])

        assert response.status_code == 422
        assert imp["entries"]() == []
        assert imp["db"].query(CashflowImportBatch).count() == 0

    def test_linha_legivel_mas_com_erro_nao_entra_nem_apagando_o_erro(self, imp):
        future = (date.today() + timedelta(days=2)).strftime("%d/%m/%Y")
        content = f"Data,Valor,Identificador,Descrição\n{future},-10.00,id-f,Futuro\n".encode()
        body = imp["preview"](content).json()
        cleaned = {**body, "rows": [{**body["rows"][0], "error": None}]}

        included = imp["commit"](body, include=[0])
        tampered = imp["commit"](cleaned, include=[0])

        assert included.status_code == 422
        assert "data no futuro" in included.json()["detail"]
        assert tampered.status_code == 409
        assert imp["entries"]() == []

    def test_linha_que_nao_existe_na_previa_e_422(self, imp):
        body = imp["preview"](ACCOUNT_CSV).json()

        assert imp["commit"](body, include=[0, 99]).status_code == 422
        assert imp["entries"]() == []

    @pytest.mark.parametrize(
        "tamper",
        [
            lambda b: b["rows"][0].update(amount="-1.00"),
            lambda b: b["rows"][0].update(description="Outra coisa"),
            lambda b: b["rows"][0].update(entry_date="2025-08-03"),
            lambda b: b["rows"][0].update(external_id="outro-id"),
            lambda b: b.update(statement_balance="999999.00"),
            lambda b: b.update(file_sha256="0" * 64),
            lambda b: b["rows"].pop(),
        ],
    )
    def test_previa_adulterada_e_recusada(self, imp, tamper):
        body = imp["preview"](OFX).json()
        tamper(body)

        response = imp["commit"](body, include=[0])

        assert response.status_code == 409
        assert imp["entries"]() == []

    def test_apagar_o_erro_ou_a_marca_de_duplicata_quebra_a_assinatura(self, imp):
        content = b"Data,Valor,Identificador,Descri\xc3\xa7\xc3\xa3o\n05/08/2025,zero,id-2,Ruim\n"
        with_error = imp["preview"](content).json()
        with_error["rows"][0].update(error=None, amount="-10.00", entry_date="2025-08-05")
        imp["commit"](imp["preview"](ACCOUNT_CSV).json())
        duplicate = imp["preview"](ACCOUNT_CSV).json()
        duplicate["rows"][0]["is_duplicate"] = False

        assert imp["commit"](with_error, include=[0]).status_code == 409
        assert imp["commit"](duplicate, include=[0]).status_code == 409

    def test_previa_de_uma_conta_nao_serve_para_outra(self, imp):
        imp["other"] = imp["account"]("Outra conta")
        body = imp["preview"](ACCOUNT_CSV).json()
        body["account_id"] = str(imp["other"].id)

        assert imp["commit"](body, include=[0]).status_code == 409

    def test_sugestoes_nao_fazem_parte_da_assinatura(self, imp):
        body = imp["preview"](ACCOUNT_CSV).json()
        body["rows"][0]["suggested_nature"] = "INCOME"
        body["rows"][0]["match_text"] = "qualquer"

        assert imp["commit"](body, include=[0]).status_code == 200

    def test_regras_sao_aplicadas_so_nos_lancamentos_novos(self, imp):
        client = imp["client"]
        old = client.post(
            "/cashflow/entries",
            json={
                "account_id": str(imp["checking"].id),
                "entry_date": "2025-07-01",
                "amount": "-5",
                "description": "Compra no débito - SUPER CENTRAL ANTIGO",
            },
        ).json()
        rule = client.post(
            "/cashflow/rules", json={"name": "Central", "pattern": "central", "set_nature": "EXPENSE"}
        ).json()

        result = imp["commit"](imp["preview"](ACCOUNT_CSV).json()).json()

        assert result["rules_applied_count"] == 1
        new = next(e for e in imp["entries"]() if e["amount"] == "-54.3000")
        assert (new["nature"], new["classified_by_rule_id"]) == ("EXPENSE", rule["id"])
        assert client.get(f"/cashflow/entries/{old['id']}").json()["nature"] == "UNCLASSIFIED"


class TestSaldoDoExtrato:
    def test_primeira_importacao_cria_o_saldo_inicial_e_a_conta_bate_com_o_banco(self, imp):
        body = imp["preview"](OFX, name="extrato.ofx").json()

        result = imp["commit"](body, create_opening_adjustment=True).json()

        assert result["opening_adjustment"] == "793.90"
        assert (result["statement_balance"], result["system_balance"]) == ("89.20", "89.2000")
        assert result["balance_difference"] == "0.0000"
        opening = next(e for e in imp["entries"]() if e["nature"] == "ADJUSTMENT")
        assert (opening["entry_date"], opening["amount"]) == ("2025-08-01", "793.9000")
        assert opening["description"] == "Saldo inicial (conferido com o extrato)"
        balances = imp["client"].get("/cashflow/balances?as_of=2025-08-31").json()
        assert {a["account_name"]: a["balance"] for a in balances["accounts"]}["Conta"] == "89.2000"

    def test_sem_pedir_o_saldo_inicial_a_diferenca_e_informada(self, imp):
        result = imp["commit"](imp["preview"](OFX).json()).json()

        assert result["opening_adjustment"] is None
        assert (result["system_balance"], result["balance_difference"]) == (
            "-704.7000",
            "-793.9000",
        )

    def test_saldo_inicial_exige_arquivo_com_saldo(self, imp):
        response = imp["commit"](imp["preview"](ACCOUNT_CSV).json(), create_opening_adjustment=True)

        assert response.status_code == 400
        assert "não informa saldo" in response.json()["detail"]
        assert imp["entries"]() == []

    def test_saldo_inicial_so_na_primeira_importacao(self, imp):
        imp["commit"](imp["preview"](ACCOUNT_CSV).json(), include=[2])

        response = imp["commit"](imp["preview"](OFX).json(), create_opening_adjustment=True)

        assert response.status_code == 400
        assert "já tem lançamentos" in response.json()["detail"]
        assert len(imp["entries"]()) == 1

    def test_saldo_inicial_exige_todas_as_linhas_validas(self, imp):
        body = imp["preview"](OFX).json()

        response = imp["commit"](body, include=[0], create_opening_adjustment=True)

        assert response.status_code == 400
        assert imp["entries"]() == []


class TestPagamentoDeFatura:
    def test_conta_e_fatura_importadas_viram_uma_transferencia(self, imp):
        first = imp["commit"](imp["preview"](ACCOUNT_CSV).json()).json()
        second = imp["commit"](imp["preview"](CARD_CSV, acct="card").json()).json()

        assert first["matched_transfers"] == []
        (match,) = second["matched_transfers"]
        assert match["amount"] == "1190.6000"
        assert (match["sent_date"], match["received_date"]) == ("2025-08-30", "2025-08-30")
        sent = imp["client"].get(f"/cashflow/entries/{match['sent_entry_id']}").json()
        received = imp["client"].get(f"/cashflow/entries/{match['received_entry_id']}").json()
        assert (sent["nature"], received["nature"]) == ("TRANSFER", "TRANSFER")
        assert (
            sent["transfer_group_id"] == received["transfer_group_id"] == match["transfer_group_id"]
        )
        assert sent["counterparty_account_id"] == str(imp["card"].id)
        assert received["counterparty_account_id"] == str(imp["checking"].id)
        assert (sent["amount"], sent["description"]) == ("-1190.6000", "Pagamento de fatura")

    def test_pagamento_casado_nao_e_gasto_e_a_identidade_fecha(self, imp):
        imp["commit"](imp["preview"](ACCOUNT_CSV).json())
        imp["commit"](imp["preview"](CARD_CSV, acct="card").json())

        summary = imp["client"].get("/cashflow/summary?start=2025-08-01&end=2025-09-30").json()

        (brl,) = summary["totals_by_currency"]
        assert brl["internal_transfers_net"] == "0.0000"
        assert brl["expenses"] == "0.0000"
        assert brl["liquid_variation"] == "-515.0500"
        assert brl["card_balance_variation"] == "1110.9000"
        assert brl["unclassified_net"] == "595.8500"

    def test_regra_de_texto_nao_classifica_o_pagamento_como_gasto(self, imp):
        client = imp["client"]
        client.post(
            "/cashflow/rules",
            json={"name": "pega tudo", "pattern": "pagamento", "set_nature": "EXPENSE"},
        )
        imp["commit"](imp["preview"](CARD_CSV, acct="card").json())

        result = imp["commit"](imp["preview"](ACCOUNT_CSV).json()).json()

        assert len(result["matched_transfers"]) == 1
        # O casamento vem antes das regras: a regra nem chega a ser aplicada.
        assert result["rules_applied_count"] == 0
        payment = next(e for e in imp["entries"]("checking") if e["amount"] == "-1190.6000")
        assert payment["nature"] == "TRANSFER"

    def test_cartao_de_outro_banco_nao_casa(self, imp):
        other_bank = make_institution(imp["db"], name="Outro Banco")
        imp["other_card"] = imp["account"](
            "Cartão outro", AccountType.CREDIT_CARD, institution=other_bank
        )
        imp["commit"](imp["preview"](ACCOUNT_CSV).json())

        result = imp["commit"](imp["preview"](CARD_CSV, acct="other_card").json()).json()

        assert result["matched_transfers"] == []

    def test_previa_do_casamento_nao_grava_e_aplicar_grava(self, imp):
        client = imp["client"]
        for acct, amount, text in [
            ("checking", "-90", "Pagamento de fatura"),
            ("card", "90", "Pagamento recebido"),
        ]:
            client.post(
                "/cashflow/entries",
                json={
                    "account_id": str(imp[acct].id),
                    "entry_date": "2025-08-10",
                    "amount": amount,
                    "description": text,
                },
            )

        dry = client.post("/cashflow/transfers/match").json()
        untouched = {e["nature"] for e in imp["entries"]()}
        applied = client.post("/cashflow/transfers/match?dry_run=false").json()

        assert (dry["applied"], len(dry["matches"]), dry["matches"][0]["transfer_group_id"]) == (
            False,
            1,
            None,
        )
        assert untouched == {"UNCLASSIFIED"}
        assert applied["applied"] is True
        assert applied["matches"][0]["transfer_group_id"] is not None
        assert {e["nature"] for e in imp["entries"]()} == {"TRANSFER"}

    def test_lancamento_classificado_a_mao_nao_e_casado(self, imp):
        client = imp["client"]
        imp["commit"](imp["preview"](ACCOUNT_CSV).json())
        payment = next(e for e in imp["entries"]() if e["amount"] == "-1190.6000")
        client.put(f"/cashflow/entries/{payment['id']}/nature", json={"nature": "EXPENSE"})

        result = imp["commit"](imp["preview"](CARD_CSV, acct="card").json()).json()

        assert result["matched_transfers"] == []
        assert client.get(f"/cashflow/entries/{payment['id']}").json()["nature"] == "EXPENSE"


def _manual(imp, acct, amount, when="2025-08-10", description="mov"):
    response = imp["client"].post(
        "/cashflow/entries",
        json={
            "account_id": str(imp[acct].id),
            "entry_date": when,
            "amount": amount,
            "description": description,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestLigarTransferencia:
    def test_liga_dois_lancamentos_existentes(self, imp):
        client = imp["client"]
        imp["savings"] = imp["account"]("Reserva", AccountType.SAVINGS)
        out = _manual(imp, "checking", "-500")
        incoming = _manual(imp, "savings", "500", when="2025-08-12")
        category = client.post("/cashflow/categories", json={"name": "Qualquer"}).json()
        tag = client.post("/cashflow/tags", json={"name": "t"}).json()
        client.put(
            f"/cashflow/entries/{out['id']}/classification",
            json={"nature": "EXPENSE", "category_id": category["id"], "tag_ids": [tag["id"]]},
        )

        response = client.post(
            f"/cashflow/entries/{out['id']}/transfer",
            json={"counterparty_entry_id": incoming["id"]},
        )

        assert response.status_code == 200, response.text
        a, b = response.json()["entries"]
        assert {a["nature"], b["nature"]} == {"TRANSFER"}
        assert a["transfer_group_id"] == b["transfer_group_id"]
        assert (a["counterparty_account_id"], b["counterparty_account_id"]) == (
            str(imp["savings"].id),
            str(imp["checking"].id),
        )
        assert (a["category_id"], a["tag_ids"]) == (None, [])
        assert (a["amount"], a["entry_date"]) == ("-500.0000", "2025-08-10")

    def test_marca_aporte_em_conta_de_investimentos(self, imp):
        client = imp["client"]
        out = _manual(imp, "checking", "-700")

        response = client.post(
            f"/cashflow/entries/{out['id']}/transfer",
            json={"investment_account_id": str(imp["brokerage"].id)},
        )
        summary = client.get("/cashflow/summary?start=2025-08-01&end=2025-08-31").json()

        assert response.status_code == 200, response.text
        (leg,) = response.json()["entries"]
        assert (leg["nature"], leg["counterparty_account_id"]) == (
            "TRANSFER",
            str(imp["brokerage"].id),
        )
        assert summary["totals_by_currency"][0]["net_invested"] == "700.0000"

    def test_recusas_ao_ligar(self, imp):
        client = imp["client"]
        imp["savings"] = imp["account"]("Reserva", AccountType.SAVINGS)
        imp["usd"] = imp["account"]("USD", currency="USD")
        out = _manual(imp, "checking", "-500")
        url = f"/cashflow/entries/{out['id']}/transfer"

        def link(other):
            return client.post(url, json={"counterparty_entry_id": other["id"]})

        different_amount = link(_manual(imp, "savings", "499.99"))
        same_account = link(_manual(imp, "checking", "500"))
        other_currency = link(_manual(imp, "usd", "500"))
        too_far = link(_manual(imp, "savings", "500", when="2025-08-25"))
        same_sign = link(_manual(imp, "savings", "-500"))
        itself = client.post(url, json={"counterparty_entry_id": out["id"]})
        both = client.post(
            url,
            json={
                "counterparty_entry_id": out["id"],
                "investment_account_id": str(imp["brokerage"].id),
            },
        )
        neither = client.post(url, json={})
        cash_as_investment = client.post(
            url, json={"investment_account_id": str(imp["savings"].id)}
        )
        missing = client.post(url, json={"counterparty_entry_id": str(uuid.uuid4())})

        assert {
            r.status_code
            for r in (
                different_amount,
                same_account,
                other_currency,
                too_far,
                same_sign,
                itself,
                both,
                neither,
                cash_as_investment,
            )
        } == {400}
        assert "não se anulam" in different_amount.json()["detail"]
        assert "mesma conta" in same_account.json()["detail"]
        assert "conta de caixa" in cash_as_investment.json()["detail"]
        assert missing.status_code == 404
        assert client.get(f"/cashflow/entries/{out['id']}").json()["nature"] == "UNCLASSIFIED"

    def test_nao_liga_o_que_ja_e_transferencia_nem_estornado(self, imp):
        client = imp["client"]
        imp["savings"] = imp["account"]("Reserva", AccountType.SAVINGS)
        out = _manual(imp, "checking", "-500")
        incoming = _manual(imp, "savings", "500")
        client.post(
            f"/cashflow/entries/{out['id']}/transfer",
            json={"counterparty_entry_id": incoming["id"]},
        )
        other_in = _manual(imp, "savings", "500")
        gone = _manual(imp, "checking", "-500")
        client.post(f"/cashflow/entries/{gone['id']}/reverse")

        again = client.post(
            f"/cashflow/entries/{out['id']}/transfer",
            json={"counterparty_entry_id": other_in["id"]},
        )
        reversed_entry = client.post(
            f"/cashflow/entries/{gone['id']}/transfer",
            json={"counterparty_entry_id": other_in["id"]},
        )

        assert (again.status_code, reversed_entry.status_code) == (400, 409)

    def test_desfazer_devolve_as_pernas_a_nao_classificado_sem_tocar_no_fato(self, imp):
        client = imp["client"]
        imp["savings"] = imp["account"]("Reserva", AccountType.SAVINGS)
        out = _manual(imp, "checking", "-500")
        incoming = _manual(imp, "savings", "500")
        client.post(
            f"/cashflow/entries/{out['id']}/transfer",
            json={"counterparty_entry_id": incoming["id"]},
        )

        response = client.delete(f"/cashflow/entries/{incoming['id']}/transfer")
        not_transfer = client.delete(f"/cashflow/entries/{incoming['id']}/transfer")

        assert response.status_code == 200, response.text
        legs = response.json()["entries"]
        assert {leg["id"] for leg in legs} == {out["id"], incoming["id"]}
        assert {
            (leg["nature"], leg["counterparty_account_id"], leg["transfer_group_id"])
            for leg in legs
        } == {("UNCLASSIFIED", None, None)}
        assert sorted(leg["amount"] for leg in legs) == ["-500.0000", "500.0000"]
        assert not_transfer.status_code == 400

    def test_lancamento_de_outro_usuario_e_404(self, imp):
        from decimal import Decimal

        stranger = make_user(imp["db"], email="imp-link-stranger@example.com")
        account = make_typed_account(imp["db"], stranger, imp["inst"], "Alheia link")
        foreign = CashflowEntry(
            account_id=account.id,
            entry_date=date(2025, 8, 10),
            amount=Decimal(500),
            currency_code="BRL",
            description="alheio",
            source="MANUAL",
            nature="UNCLASSIFIED",
        )
        imp["db"].add(foreign)
        imp["db"].flush()
        out = _manual(imp, "checking", "-500")

        response = imp["client"].post(
            f"/cashflow/entries/{out['id']}/transfer",
            json={"counterparty_entry_id": str(foreign.id)},
        )

        assert response.status_code == 404
        imp["db"].refresh(foreign)
        assert foreign.nature.value == "UNCLASSIFIED"


class TestFatoImportadoImutavel:
    @pytest.mark.parametrize("field", ["external_id", "import_fingerprint", "import_batch_id"])
    def test_campos_de_origem_nao_mudam(self, imp, field):
        from sqlalchemy.exc import IntegrityError

        imp["commit"](imp["preview"](ACCOUNT_CSV).json())
        entry = imp["db"].query(CashflowEntry).first()

        setattr(entry, field, None if field != "import_fingerprint" else "x:0")

        with pytest.raises(IntegrityError, match="registro histórico protegido"):
            imp["db"].flush()

    def test_o_banco_recusa_o_mesmo_identificador_na_mesma_conta(self, imp):
        from decimal import Decimal

        from sqlalchemy.exc import IntegrityError

        imp["commit"](imp["preview"](ACCOUNT_CSV).json())
        duplicate = CashflowEntry(
            account_id=imp["checking"].id,
            entry_date=date(2025, 8, 2),
            amount=Decimal(-1),
            currency_code="BRL",
            description="x",
            source="IMPORT_CSV",
            nature="UNCLASSIFIED",
            external_id="0a000001-0000-4000-8000-000000000001",
        )
        imp["db"].add(duplicate)

        with pytest.raises(IntegrityError, match="uq_cashflow_entries_account_external_id"):
            imp["db"].flush()
