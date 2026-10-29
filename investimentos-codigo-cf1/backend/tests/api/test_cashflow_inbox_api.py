"""Pasta Entrada: extratos e faturas soltos na pasta entram pelo mesmo
caminho da tela de importação, e só saem da pasta depois de gravados.
"""

from datetime import date

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import CashflowEntry
from app.models.cashflow_import_batch import CashflowImportBatch
from app.models.enums import AccountType
from app.services import cashflow_inbox_service
from tests.api.test_cashflow_import_api import (
    ACCOUNT_CSV,
    CARD_CSV,
    imp,  # noqa: F401 (fixture)
)
from tests.api.test_fatura_pdf_api import PAYMENT_FROM_CHECKING, PDF
from tests.fatura_pdf_helpers import FATURA_LINES, fatura_pdf


@pytest.fixture()
def inbox(tmp_path, monkeypatch):
    folder = tmp_path / "Entrada"
    folder.mkdir()
    monkeypatch.setattr(settings, "inbox_dir", folder)
    return folder


def run(imp):  # noqa: F811
    response = imp["client"].post("/cashflow/inbox/process")
    assert response.status_code == 200, response.text
    return {f["file_name"]: f for f in response.json()["files"]}


def card_entries(imp):  # noqa: F811
    return (
        imp["db"]
        .execute(select(CashflowEntry).where(CashflowEntry.account_id == imp["card"].id))
        .scalars()
        .all()
    )


class TestListagem:
    def test_lista_so_extratos_e_faturas_da_raiz(self, imp, inbox):  # noqa: F811
        for name in ("b.ofx", "A.csv", "fatura.PDF", "nota.txt", "~$aberto.csv", ".oculto.ofx"):
            (inbox / name).write_bytes(b"x")
        (inbox / "importados").mkdir()
        (inbox / "importados" / "velho.csv").write_bytes(b"x")

        body = imp["client"].get("/cashflow/inbox").json()

        assert body["files"] == ["A.csv", "b.ofx", "fatura.PDF"]
        assert body["exists"] is True
        assert body["inbox_dir"] == str(inbox)

    def test_pasta_que_nao_existe_e_lista_vazia(self, imp, tmp_path, monkeypatch):  # noqa: F811
        monkeypatch.setattr(settings, "inbox_dir", tmp_path / "nao-existe")

        body = imp["client"].get("/cashflow/inbox").json()

        assert (body["exists"], body["files"]) == (False, [])
        assert run(imp) == {}


class TestCarga:
    def test_extrato_vai_para_a_conta_e_fatura_para_o_cartao(self, imp, inbox):  # noqa: F811
        (inbox / "extrato.csv").write_bytes(ACCOUNT_CSV)
        (inbox / "fatura.pdf").write_bytes(PDF)

        files = run(imp)

        statement, invoice = files["extrato.csv"], files["fatura.pdf"]
        assert (statement["status"], statement["account_name"]) == ("IMPORTED", "Conta")
        assert statement["imported_count"] == 4
        assert statement["profile"] == "NUBANK_ACCOUNT_CSV"
        assert (invoice["status"], invoice["account_name"]) == ("IMPORTED", "Cartão")
        assert invoice["imported_count"] == 7
        assert "confere" in invoice["message"]
        assert len(card_entries(imp)) == 7

    def test_aceitos_saem_da_pasta_para_importados_com_registro(self, imp, inbox):  # noqa: F811
        (inbox / "fatura.pdf").write_bytes(PDF)

        files = run(imp)

        moved = files["fatura.pdf"]["moved_to"]
        assert moved.startswith("importados")
        assert (inbox / moved).read_bytes() == PDF
        assert not (inbox / "fatura.pdf").exists()
        log = (inbox / "importados" / "registro.txt").read_text(encoding="utf-8")
        assert "fatura.pdf  ->  Cartão: 7 novo(s), 0 já existia(m)" in log

    def test_carregar_de_novo_nao_duplica_e_tira_da_pasta(self, imp, inbox):  # noqa: F811
        (inbox / "fatura.pdf").write_bytes(PDF)
        run(imp)
        (inbox / "fatura.pdf").write_bytes(PDF)

        files = run(imp)

        assert files["fatura.pdf"]["status"] == "NOTHING_NEW"
        assert files["fatura.pdf"]["duplicate_count"] == 7
        assert len(card_entries(imp)) == 7
        assert not (inbox / "fatura.pdf").exists()
        # O segundo arquivo não sobrescreve o primeiro em importados/.
        done = list((inbox / "importados").glob("*/fatura*.pdf"))
        assert sorted(p.name for p in done) == ["fatura (2).pdf", "fatura.pdf"]

    def test_fatura_que_nao_confere_fica_na_pasta_e_nada_e_gravado(self, imp, inbox):  # noqa: F811
        broken = [line for line in FATURA_LINES if line[-1][1] != "R$ 35,40"]
        (inbox / "fatura.pdf").write_bytes(fatura_pdf(broken))

        files = run(imp)

        assert files["fatura.pdf"]["status"] == "REFUSED"
        assert "não confere" in files["fatura.pdf"]["message"]
        assert files["fatura.pdf"]["moved_to"] is None
        assert (inbox / "fatura.pdf").exists()
        assert imp["db"].execute(select(CashflowImportBatch)).first() is None

    def test_formato_desconhecido_fica_na_pasta(self, imp, inbox):  # noqa: F811
        (inbox / "planilha.csv").write_bytes(b"coluna1,coluna2\n1,2\n")

        files = run(imp)

        assert files["planilha.csv"]["status"] == "REFUSED"
        assert "formato não reconhecido" in files["planilha.csv"]["message"]
        assert (inbox / "planilha.csv").exists()

    def test_um_arquivo_recusado_nao_impede_os_outros(self, imp, inbox):  # noqa: F811
        (inbox / "a-ruim.csv").write_bytes(b"x,y\n")
        (inbox / "b-fatura.csv").write_bytes(CARD_CSV)

        files = run(imp)

        assert files["a-ruim.csv"]["status"] == "REFUSED"
        assert files["b-fatura.csv"]["status"] == "IMPORTED"
        assert len(card_entries(imp)) == 5

    def test_duas_contas_candidatas_nao_adivinha(self, imp, inbox):  # noqa: F811
        imp["account"]("Outro cartão", AccountType.CREDIT_CARD)
        (inbox / "fatura.pdf").write_bytes(PDF)

        files = run(imp)

        assert files["fatura.pdf"]["status"] == "NO_ACCOUNT"
        assert "mais de uma" in files["fatura.pdf"]["message"]
        assert (inbox / "fatura.pdf").exists()
        assert card_entries(imp) == []

    def test_conta_de_outro_banco_nao_serve(self, imp, inbox):  # noqa: F811
        from tests.test_persistence import make_institution

        other = make_institution(imp["db"], name="Banco Qualquer")
        imp["db"].delete(imp["card"])
        imp["db"].flush()
        imp["account"]("Cartão de outro banco", AccountType.CREDIT_CARD, institution=other)
        (inbox / "fatura.pdf").write_bytes(PDF)

        files = run(imp)

        assert files["fatura.pdf"]["status"] == "NO_ACCOUNT"
        assert "nenhum" in files["fatura.pdf"]["message"]

    def test_pagamento_da_fatura_casa_com_o_extrato(self, imp, inbox):  # noqa: F811
        (inbox / "1-extrato.csv").write_bytes(PAYMENT_FROM_CHECKING)
        (inbox / "2-fatura.pdf").write_bytes(PDF)

        files = run(imp)

        assert files["2-fatura.pdf"]["matched_transfers"] == 1

    def test_linha_com_erro_e_contada_e_o_resto_entra(self, imp, inbox):  # noqa: F811
        future = CARD_CSV + f'{date.today().year + 1}-01-02,Compra futura,"10,00"\n'.encode()
        (inbox / "fatura.csv").write_bytes(future)

        files = run(imp)

        assert files["fatura.csv"]["status"] == "IMPORTED"
        assert (files["fatura.csv"]["imported_count"], files["fatura.csv"]["error_rows"]) == (5, 1)

    def test_arquivo_grande_demais_e_recusado(self, imp, inbox, monkeypatch):  # noqa: F811
        monkeypatch.setattr(settings, "import_max_upload_bytes", 10)
        (inbox / "fatura.pdf").write_bytes(PDF)

        files = run(imp)

        assert files["fatura.pdf"]["status"] == "REFUSED"
        assert "limite" in files["fatura.pdf"]["message"]


class TestOrdem:
    def test_processar_nao_move_nada_antes_do_commit(self, imp, inbox):  # noqa: F811
        (inbox / "fatura.pdf").write_bytes(PDF)

        result, pending = cashflow_inbox_service.process_inbox(imp["db"], imp["user"].id)

        assert result.files[0].status == "IMPORTED"
        assert (inbox / "fatura.pdf").exists()
        assert [p.path.name for p in pending] == ["fatura.pdf"]

    def test_recusado_nao_entra_na_lista_de_mover(self, imp, inbox):  # noqa: F811
        (inbox / "ruim.csv").write_bytes(b"x\n")

        _result, pending = cashflow_inbox_service.process_inbox(imp["db"], imp["user"].id)

        assert pending == []
