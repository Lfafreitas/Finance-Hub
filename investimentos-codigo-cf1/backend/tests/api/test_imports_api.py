from tests.test_persistence import make_account, make_institution


def _setup_account(db_session, user, name="Conta Imports API"):
    institution = make_institution(db_session, name=f"Inst {name}")
    return make_account(db_session, user, institution, name=name)


class TestImportsAPI:
    def test_preview_via_upload_multipart(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Imports Preview")

        csv_content = (
            b"data,tipo,ativo,quantidade,preco_unitario,taxas,valor,moeda\n"
            b"2026-01-05,DEPOSITO,,,,,100.00,BRL\n"
        )

        response = client.post(
            "/imports/preview",
            data={"account_id": str(account.id), "source_format": "csv"},
            files={"file": ("extrato.csv", csv_content, "text/csv")},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["rows"]) == 1
        assert body["rows"][0]["gross_amount"] == "100.00"
        assert "signature" in body

    def test_preview_depois_commit_completo(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Imports Commit")

        csv_content = (
            b"data,tipo,ativo,quantidade,preco_unitario,taxas,valor,moeda\n"
            b"2026-01-05,DEPOSITO,,,,,250.00,BRL\n"
        )

        preview = client.post(
            "/imports/preview",
            data={"account_id": str(account.id), "source_format": "CSV"},
            files={"file": ("extrato.csv", csv_content, "text/csv")},
        ).json()

        commit = client.post(
            "/imports/commit",
            json={
                "account_id": preview["account_id"],
                "source_format": preview["source_format"],
                "rows": preview["rows"],
                "signature": preview["signature"],
                "included_row_indexes": [r["row_index"] for r in preview["rows"]],
            },
        )

        assert commit.status_code == 200, commit.text
        result = commit.json()
        assert result["imported_count"] == 1
        assert result["excluded_count"] == 0

        history = client.get(f"/accounts/{account.id}/transactions").json()
        assert len(history) == 1
        assert history[0]["gross_amount"] == "250.0000"

    def test_commit_com_assinatura_adulterada_e_rejeitado(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Imports Assinatura")

        csv_content = (
            b"data,tipo,ativo,quantidade,preco_unitario,taxas,valor,moeda\n"
            b"2026-01-05,DEPOSITO,,,,,100.00,BRL\n"
        )
        preview = client.post(
            "/imports/preview",
            data={"account_id": str(account.id), "source_format": "CSV"},
            files={"file": ("extrato.csv", csv_content, "text/csv")},
        ).json()

        preview["rows"][0]["gross_amount"] = "999999.00"

        commit = client.post(
            "/imports/commit",
            json={
                "account_id": preview["account_id"],
                "source_format": preview["source_format"],
                "rows": preview["rows"],
                "signature": preview["signature"],
                "included_row_indexes": [0],
            },
        )
        assert commit.status_code == 409

    def test_formato_invalido_e_rejeitado(self, api_client, db_session):
        client, user = api_client
        account = _setup_account(db_session, user, name="Conta Imports Formato Invalido")

        response = client.post(
            "/imports/preview",
            data={"account_id": str(account.id), "source_format": "PDF"},
            files={"file": ("nota.pdf", b"conteudo", "application/pdf")},
        )
        assert response.status_code == 400

    def test_conta_de_outro_usuario_e_rejeitada(self, api_client, db_session):
        client, _user = api_client
        from tests.test_persistence import make_user

        outro = make_user(db_session, email="outro-imports-api@example.com")
        institution = make_institution(db_session, name="Inst Outro Imports API")
        conta_de_outro = make_account(
            db_session, outro, institution, name="Conta De Outro Imports API"
        )

        csv_content = b"data,tipo,ativo,quantidade,preco_unitario,taxas,valor,moeda\n2026-01-05,DEPOSITO,,,,,100.00,BRL\n"
        response = client.post(
            "/imports/preview",
            data={"account_id": str(conta_de_outro.id), "source_format": "CSV"},
            files={"file": ("extrato.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 404
