"""Fatura-PDF: fatura do cartão em PDF e em OFX pela mesma importação
do livro de caixa (prévia assinada + commit), sem duplicar o CSV.
"""

from decimal import Decimal

from sqlalchemy import select

from app.models import CashflowEntry
from app.models.cashflow_import_batch import CashflowImportBatch
from app.models.enums import TransactionSource
from tests.api.test_cashflow_import_api import imp  # noqa: F401 (fixture)
from tests.fatura_pdf_helpers import FATURA_LINES, fatura_pdf
from tests.services.test_fatura_pdf import CARD_OFX

PDF = fatura_pdf(split_at=12)

# O mesmo mês no CSV do app: estorno sem o "Estorno de", pagamento como
# "Pagamento recebido". O Pix parcelado o CSV escreve de outro jeito
# (e com um centavo de diferença), então não está aqui.
SAME_MONTH_CSV = (
    "date,title,amount\n"
    '2025-12-30,Loja Exemplo - Parcela 2/3,"50,00"\n'
    '2026-01-03,Lanche - NuPay,"35,40"\n'
    '2026-01-10,Mercado Exemplo,"100,00"\n'
    '2026-01-12,Loja Devolvida,"- 20,00"\n'
    '2026-01-15,Desconto Antecipação Loja Exemplo,"- 1,46"\n'
    '2026-01-05,Pagamento recebido,"- 300,00"\n'
).encode()

PAYMENT_FROM_CHECKING = (
    "Data,Valor,Identificador,Descrição\n05/01/2026,-300.00,id-pag-1,Pagamento de fatura\n"
).encode()


def preview_pdf(imp, content=PDF, acct="card"):  # noqa: F811
    return imp["preview"](content, acct=acct, name="fatura.pdf")


class TestPreviaDoPdf:
    def test_mostra_as_linhas_e_as_conferencias(self, imp):  # noqa: F811
        response = preview_pdf(imp)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["profile"] == "NUBANK_CARD_PDF"
        assert [(r["entry_date"], r["amount"], r["description"]) for r in body["rows"]] == [
            ("2025-12-30", "-50.00", "Loja Exemplo - Parcela 2/3"),
            ("2026-01-03", "-35.40", "Lanche - NuPay"),
            ("2026-01-10", "-100.00", "Mercado Exemplo"),
            ("2026-01-12", "20.00", "Estorno de Loja Devolvida"),
            ("2026-01-15", "1.46", "Desconto Antecipação Loja Exemplo"),
            ("2026-01-05", "300.00", "Pagamento recebido"),
            ("2026-01-08", "-141.54", "Pessoa Exemplo - Parcela 1/5"),
        ]
        assert all(not r["error"] and not r["is_duplicate"] for r in body["rows"])
        assert [(c["label"], c["ok"]) for c in body["checks"]] == [
            ("Compras, estornos e créditos", True),
            ("Pagamentos recebidos", True),
        ]
        assert (body["statement_due_date"], body["statement_total"]) == ("2026-02-06", "305.48")
        assert body["statement_previous"] == "300.00"
        assert (body["period_start"], body["period_end"]) == ("2025-12-30", "2026-01-30")
        assert body["statement_balance"] is None

    def test_fatura_que_nao_confere_e_recusada_e_nada_e_gravado(self, imp):  # noqa: F811
        broken = [line for line in FATURA_LINES if line[-1][1] != "R$ 35,40"]

        response = preview_pdf(imp, fatura_pdf(broken))

        assert response.status_code == 400
        assert "não confere" in response.json()["detail"]
        assert imp["db"].execute(select(CashflowImportBatch)).first() is None

    def test_pdf_em_conta_que_nao_e_cartao_e_400(self, imp):  # noqa: F811
        response = preview_pdf(imp, acct="checking")

        assert response.status_code == 400
        assert "cartão de crédito" in response.json()["detail"]

    def test_perfil_pdf_forcado_em_arquivo_que_nao_e_pdf_e_400(self, imp):  # noqa: F811
        response = imp["preview"](SAME_MONTH_CSV, acct="card", profile="NUBANK_CARD_PDF")

        assert response.status_code == 400


class TestCommitDoPdf:
    def test_grava_como_fato_importado_de_pdf(self, imp):  # noqa: F811
        result = imp["commit"](preview_pdf(imp).json())

        assert result.status_code == 200, result.text
        assert result.json()["imported_count"] == 7
        db = imp["db"]
        entries = db.execute(
            select(CashflowEntry).where(CashflowEntry.account_id == imp["card"].id)
        ).scalars()
        entries = list(entries)
        assert {e.source for e in entries} == {TransactionSource.IMPORT_PDF}
        assert sum(e.amount for e in entries) == Decimal("-5.48")  # 300 pagos - 305,48
        (batch,) = db.execute(select(CashflowImportBatch)).scalars()
        assert batch.profile.value == "NUBANK_CARD_PDF"
        assert (batch.rows_total, batch.rows_imported) == (7, 7)

    def test_reimportar_o_pdf_nao_duplica(self, imp):  # noqa: F811
        imp["commit"](preview_pdf(imp).json())

        again = preview_pdf(imp).json()

        assert again["file_already_imported"] is True
        assert all(r["is_duplicate"] for r in again["rows"])

    def test_csv_e_depois_pdf_do_mesmo_mes_nao_duplicam(self, imp):  # noqa: F811
        imp["commit"](imp["preview"](SAME_MONTH_CSV, acct="card").json())

        rows = preview_pdf(imp).json()["rows"]

        new = [r["description"] for r in rows if not r["is_duplicate"]]
        assert new == ["Pessoa Exemplo - Parcela 1/5"]

    def test_pdf_e_depois_csv_do_mesmo_mes_nao_duplicam(self, imp):  # noqa: F811
        imp["commit"](preview_pdf(imp).json())

        rows = imp["preview"](SAME_MONTH_CSV, acct="card").json()["rows"]

        assert all(r["is_duplicate"] for r in rows)

    def test_pagamento_da_fatura_casa_com_a_conta(self, imp):  # noqa: F811
        imp["commit"](imp["preview"](PAYMENT_FROM_CHECKING).json())

        result = imp["commit"](preview_pdf(imp).json()).json()

        (match,) = result["matched_transfers"]
        assert match["amount"] == "300.0000"
        assert (match["sent_date"], match["received_date"]) == ("2026-01-05", "2026-01-05")


class TestOfxDoCartao:
    def test_importa_e_reimportar_nao_duplica(self, imp):  # noqa: F811
        body = imp["preview"](CARD_OFX, acct="card", name="fatura.ofx").json()

        assert body["profile"] == "NUBANK_CARD_OFX"
        assert body["statement_balance"] is None
        assert all(r["import_fingerprint"] and not r["external_id"] for r in body["rows"])
        result = imp["commit"](body)
        assert result.status_code == 200, result.text
        assert result.json()["imported_count"] == 3

        again = imp["preview"](CARD_OFX, acct="card", name="fatura.ofx").json()
        assert all(r["is_duplicate"] for r in again["rows"])

    def test_ofx_do_cartao_em_conta_corrente_e_400(self, imp):  # noqa: F811
        response = imp["preview"](CARD_OFX, acct="checking", name="fatura.ofx")

        assert response.status_code == 400
