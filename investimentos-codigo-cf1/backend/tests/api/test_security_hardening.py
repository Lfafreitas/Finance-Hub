"""Endurecimento de borda: Host confiável, CORS restrito, teto de
upload, segredo HMAC e assinatura cobrindo o erro da linha.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from tests.test_persistence import make_account, make_institution

ORIGIN_OK = "http://localhost:5173"
ORIGIN_EVIL = "https://evil.example"


def _setup_account(db_session, user, name):
    return make_account(db_session, user, make_institution(db_session, name=f"Inst {name}"), name)


class TestHostConfiavel:
    def test_host_desconhecido_e_recusado(self, api_client):
        """DNS rebinding: o request chega em 127.0.0.1 mas com o Host
        do domínio do atacante.
        """
        client, _user = api_client

        response = client.get("/accounts", headers={"Host": "evil.example"})

        assert response.status_code == 400

    @pytest.mark.parametrize("host", ["localhost", "localhost:8000", "127.0.0.1:8000"])
    def test_hosts_locais_sao_aceitos(self, api_client, host):
        client, _user = api_client

        assert client.get("/health", headers={"Host": host}).status_code == 200

    def test_padrao_de_producao_nao_inclui_testserver(self):
        assert Settings.model_fields["allowed_hosts"].default == ["localhost", "127.0.0.1"]


class TestCors:
    def test_origem_do_frontend_pode_ler_a_resposta(self, api_client):
        client, _user = api_client

        response = client.get("/accounts", headers={"Origin": ORIGIN_OK})

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == ORIGIN_OK

    def test_outra_origem_nao_recebe_cabecalho_de_permissao(self, api_client):
        client, _user = api_client

        response = client.get("/accounts", headers={"Origin": ORIGIN_EVIL})

        assert "access-control-allow-origin" not in response.headers

    def test_preflight_de_post_json_do_frontend_e_aceito(self, api_client):
        client, _user = api_client

        response = client.options(
            "/reconciliation/scan",
            headers={
                "Origin": ORIGIN_OK,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == ORIGIN_OK

    def test_preflight_de_outra_origem_e_recusado(self, api_client):
        client, _user = api_client

        response = client.options(
            "/reconciliation/scan",
            headers={"Origin": ORIGIN_EVIL, "Access-Control-Request-Method": "POST"},
        )

        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers


class TestSegredoHmac:
    def test_producao_com_segredo_padrao_nao_sobe(self):
        with pytest.raises(ValidationError):
            Settings(environment="production")

    def test_producao_com_segredo_proprio_sobe(self):
        assert Settings(environment="production", import_hmac_secret="x" * 40).environment

    def test_desenvolvimento_aceita_o_segredo_padrao(self):
        assert Settings(environment="development").import_hmac_secret


class TestTetoDeUpload:
    def test_arquivo_acima_do_teto_e_413(self, api_client, db_session, monkeypatch):
        client, user = api_client
        account = _setup_account(db_session, user, "Conta Teto Upload")
        monkeypatch.setattr(settings, "import_max_upload_bytes", 64)

        response = client.post(
            "/imports/preview",
            data={"account_id": str(account.id), "source_format": "CSV"},
            files={"file": ("grande.csv", b"data,tipo,valor\n" + b"x" * 200, "text/csv")},
        )

        assert response.status_code == 413

    def test_arquivo_exatamente_no_teto_e_processado(self, api_client, db_session, monkeypatch):
        client, user = api_client
        account = _setup_account(db_session, user, "Conta Teto Upload Exato")
        content = b"data,tipo,valor,moeda\n2026-01-05,DEPOSITO,100.00,BRL\n"
        monkeypatch.setattr(settings, "import_max_upload_bytes", len(content))

        response = client.post(
            "/imports/preview",
            data={"account_id": str(account.id), "source_format": "CSV"},
            files={"file": ("ok.csv", content, "text/csv")},
        )

        assert response.status_code == 200, response.text


class TestAssinaturaCobreErroDaLinha:
    def test_apagar_o_erro_de_uma_linha_invalida_a_assinatura(self, api_client, db_session):
        """Linha com ativo não cadastrado vem da preview com `error`.
        O cliente não pode limpar esse campo e comitar com a mesma
        assinatura — antes, isso gravava um BUY sem `asset_id`.
        """
        client, user = api_client
        account = _setup_account(db_session, user, "Conta Assinatura Erro")
        csv_content = (
            b"data,tipo,ativo,quantidade,preco_unitario,taxas,valor,moeda\n"
            b"2026-01-05,COMPRA,NAOEXISTE9,10,5,0,50.00,BRL\n"
        )
        preview = client.post(
            "/imports/preview",
            data={"account_id": str(account.id), "source_format": "CSV"},
            files={"file": ("extrato.csv", csv_content, "text/csv")},
        ).json()
        assert preview["rows"][0]["error"] is not None
        rows = [dict(preview["rows"][0], error=None)]

        commit = client.post(
            "/imports/commit",
            json={
                "account_id": preview["account_id"],
                "source_format": preview["source_format"],
                "rows": rows,
                "signature": preview["signature"],
                "included_row_indexes": [0],
            },
        )

        assert commit.status_code == 409
        assert client.get(f"/accounts/{account.id}/transactions").json() == []
