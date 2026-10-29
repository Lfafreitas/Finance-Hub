"""CF-3: leitura dos arquivos do Nubank. Os arquivos de teste têm o
formato dos reais (CF-0, seções 13 e 14), com nomes fictícios.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import CashflowImportProfile
from app.services.cashflow_imports.parsers import (
    detect_profile,
    parse_account_csv,
    parse_account_ofx,
    parse_card_csv,
    parse_statement,
)
from app.services.exceptions import ImportParsingError

D = Decimal
ACCOUNT_CSV = (
    "Data,Valor,Identificador,Descrição\n"
    "02/08/2026,-650.40,0a000001-0000-4000-8000-000000000001,"
    "Transferência enviada pelo Pix - TITULAR EXEMPLO (Transferência enviada)\n"
    "05/08/2026,1380.25,0a000002-0000-4000-8000-000000000002,"
    "Transferência recebida pelo Pix via Open Banking - TITULAR EXEMPLO - •••.123.456-•• - "
    "ITAÚ UNIBANCO S.A. (0341) Agência: 4321 Conta: 22222-2\n"
    "20/08/2026,-54.30,0a000003-0000-4000-8000-000000000003,Compra no débito - SUPER CENTRAL\n"
    "30/08/2026,-1190.60,0a000004-0000-4000-8000-000000000004,Pagamento de fatura\n"
).encode()

CARD_CSV = (
    b"date,title,amount\n"
    b'2026-09-26,Uber Uber *Trip Help.U,"29,80"\n'
    b'2026-09-01,Amazon BR IV - NuPay,"- 175,45"\n'
    b'2026-09-01,Amazon BR IV - NuPay,"175,45"\n'
    b'2026-08-30,Loja Grande - NuPay - Parcela 5/6,"49,90"\n'
    b'2026-08-30,Pagamento recebido,"- 1.190,60"\n'
)

OFX = """OFXHEADER:100
DATA:OFXSGML
VERSION:102
ENCODING:UTF-8
<OFX>
<BANKMSGSRSV1>
<STMTTRNRS>
<STMTRS>
<CURDEF>BRL</CURDEF>
<BANKACCTFROM>
<BANKID>0260</BANKID>
<ACCTID>000000000-0</ACCTID>
<ACCTTYPE>CHECKING</ACCTTYPE>
</BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>20260801000000[-3:BRT]</DTSTART>
<DTEND>20260831000000[-3:BRT]</DTEND>
<STMTTRN>
<TRNTYPE>DEBIT</TRNTYPE>
<DTPOSTED>20260802000000[-3:BRT]</DTPOSTED>
<TRNAMT>-650.40</TRNAMT>
<FITID>0a000001-0000-4000-8000-000000000001</FITID>
<MEMO>Transferência enviada pelo Pix - TITULAR EXEMPLO (Transferência enviada)</MEMO>
</STMTTRN>
<STMTTRN>
<TRNTYPE>DEBIT</TRNTYPE>
<DTPOSTED>20260820000000[-3:BRT]</DTPOSTED>
<TRNAMT>-54.30</TRNAMT>
<FITID>0a000003-0000-4000-8000-000000000003</FITID>
<MEMO>Compra no débito - LOJA A &amp; B</MEMO>
</STMTTRN>
</BANKTRANLIST>
<LEDGERBAL>
<BALAMT>89.20</BALAMT>
<DTASOF>20260831000000[-3:BRT]</DTASOF>
</LEDGERBAL>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
""".encode()


class TestDeteccao:
    def test_reconhece_os_tres_formatos(self):
        assert detect_profile(ACCOUNT_CSV) is CashflowImportProfile.NUBANK_ACCOUNT_CSV
        assert detect_profile(CARD_CSV) is CashflowImportProfile.NUBANK_CARD_CSV
        assert detect_profile(OFX) is CashflowImportProfile.NUBANK_ACCOUNT_OFX

    def test_aceita_bom_e_cabecalho_sem_acento(self):
        with_bom = b"\xef\xbb\xbf" + ACCOUNT_CSV.replace("Descrição".encode(), b"Descricao")

        assert detect_profile(with_bom) is CashflowImportProfile.NUBANK_ACCOUNT_CSV

    def test_formato_desconhecido_e_erro(self):
        with pytest.raises(ImportParsingError, match="não reconhecido"):
            detect_profile(b"data,tipo,ativo,quantidade\n2026-01-01,COMPRA,PETR4,10\n")

    def test_arquivo_que_nao_e_utf8_e_erro(self):
        with pytest.raises(ImportParsingError, match="UTF-8"):
            detect_profile(b"Data,Valor,Identificador,Descri\xe7\xe3o\n")


class TestExtratoDaContaCsv:
    def test_le_data_valor_identificador_e_descricao(self):
        parsed = parse_account_csv(ACCOUNT_CSV)

        first = parsed.rows[0]
        assert parsed.profile is CashflowImportProfile.NUBANK_ACCOUNT_CSV
        assert len(parsed.rows) == 4
        assert (first.row_index, first.entry_date, first.amount) == (
            0,
            date(2026, 8, 2),
            D("-650.40"),
        )
        assert first.external_id == "0a000001-0000-4000-8000-000000000001"
        assert first.description.startswith("Transferência enviada pelo Pix - TITULAR EXEMPLO")
        assert parsed.rows[1].amount == D("1380.25")
        assert all(row.error is None for row in parsed.rows)

    def test_periodo_vem_das_datas_e_nao_ha_saldo(self):
        parsed = parse_account_csv(ACCOUNT_CSV)

        assert (parsed.period_start, parsed.period_end) == (date(2026, 8, 2), date(2026, 8, 30))
        assert parsed.statement_balance is None

    def test_linha_ruim_vira_erro_sem_derrubar_as_outras(self):
        content = (
            "Data,Valor,Identificador,Descrição\n"
            "31/02/2026,-10.00,id-1,Data impossível\n"
            "05/08/2026,dez,id-2,Valor ilegível\n"
            "05/08/2026,-10.00,,Sem identificador\n"
            "05/08/2026,0.00,id-4,Valor zero\n"
            "05/08/2026,-1.23456,id-5,Casas demais\n"
            "05/08/2026,-10.00,id-6,\n"
            "05/08/2026,-10.00,id-7,Linha boa\n"
        ).encode()

        rows = parse_account_csv(content).rows

        assert [row.error is None for row in rows] == [False] * 6 + [True]
        assert rows[0].error == rows[1].error == rows[4].error == "data ou valor ilegível"
        assert rows[2].error == "linha sem identificador do banco"
        assert rows[3].error == "valor zero"
        assert rows[5].error == "sem descrição"
        assert rows[6].amount == D("-10.00")

    def test_linhas_em_branco_sao_ignoradas(self):
        content = ACCOUNT_CSV + b"\n\n"

        assert len(parse_account_csv(content).rows) == 4

    def test_cabecalho_errado_e_erro(self):
        with pytest.raises(ImportParsingError, match="cabeçalho"):
            parse_account_csv(CARD_CSV)


class TestFaturaDoCartaoCsv:
    def test_compra_vira_saida_e_estorno_e_pagamento_viram_entrada(self):
        rows = parse_card_csv(CARD_CSV).rows

        assert [row.amount for row in rows] == [
            D("-29.80"),
            D("175.45"),
            D("-175.45"),
            D("-49.90"),
            D("1190.60"),
        ]

    def test_data_iso_titulo_e_sem_identificador(self):
        parsed = parse_card_csv(CARD_CSV)

        assert parsed.rows[0].entry_date == date(2026, 9, 26)
        assert parsed.rows[3].description == "Loja Grande - NuPay - Parcela 5/6"
        assert {row.external_id for row in parsed.rows} == {None}
        assert (parsed.period_start, parsed.period_end) == (date(2026, 8, 30), date(2026, 9, 26))

    def test_valor_ou_data_ilegivel_vira_erro_na_linha(self):
        content = (
            b'date,title,amount\n26/09/2026,Data errada,"10,00"\n2026-09-26,Valor errado,"abc"\n'
        )

        rows = parse_card_csv(content).rows

        assert [row.error for row in rows] == ["data ou valor ilegível"] * 2

    def test_cabecalho_errado_e_erro(self):
        with pytest.raises(ImportParsingError, match="cabeçalho"):
            parse_card_csv(ACCOUNT_CSV)


class TestExtratoDaContaOfx:
    def test_le_lancamentos_com_o_mesmo_identificador_do_csv(self):
        parsed = parse_account_ofx(OFX)

        assert [(r.entry_date, r.amount, r.external_id) for r in parsed.rows] == [
            (date(2026, 8, 2), D("-650.40"), "0a000001-0000-4000-8000-000000000001"),
            (date(2026, 8, 20), D("-54.30"), "0a000003-0000-4000-8000-000000000003"),
        ]
        assert parsed.rows[0].external_id == parse_account_csv(ACCOUNT_CSV).rows[0].external_id

    def test_le_saldo_final_periodo_e_moeda(self):
        parsed = parse_account_ofx(OFX)

        assert (parsed.statement_balance, parsed.statement_balance_date) == (
            D("89.20"),
            date(2026, 8, 31),
        )
        assert (parsed.period_start, parsed.period_end) == (date(2026, 8, 1), date(2026, 8, 31))
        assert parsed.currency_code == "BRL"

    def test_entidade_html_na_descricao_e_decodificada(self):
        assert parse_account_ofx(OFX).rows[1].description == "Compra no débito - LOJA A & B"

    def test_tags_sem_fechamento_tambem_sao_lidas(self):
        sgml = (
            OFX.decode()
            .replace("</TRNAMT>", "")
            .replace("</FITID>", "")
            .replace("</DTPOSTED>", "")
            .replace("</MEMO>", "")
            .replace("</BALAMT>", "")
            .replace("</DTASOF>", "")
            .encode()
        )

        parsed = parse_account_ofx(sgml)

        assert parsed.rows[0].amount == D("-650.40")
        assert parsed.statement_balance == D("89.20")

    def test_ofx_sem_saldo_nao_inventa_saldo(self):
        without = OFX.decode().split("<LEDGERBAL>")[0] + "</STMTRS></OFX>"

        assert parse_account_ofx(without.encode()).statement_balance is None

    def test_ofx_que_nao_e_extrato_bancario_e_erro(self):
        with pytest.raises(ImportParsingError, match="extrato bancário"):
            parse_account_ofx(b"OFXHEADER:100\n<OFX><INVSTMTRS></INVSTMTRS></OFX>")


class TestParseStatement:
    def test_sem_perfil_detecta_e_com_perfil_obedece(self):
        assert parse_statement(CARD_CSV).profile is CashflowImportProfile.NUBANK_CARD_CSV
        assert parse_statement(ACCOUNT_CSV, CashflowImportProfile.NUBANK_ACCOUNT_CSV).rows[
            0
        ].amount == D("-650.40")

    def test_perfil_errado_para_o_arquivo_e_erro(self):
        with pytest.raises(ImportParsingError):
            parse_statement(ACCOUNT_CSV, CashflowImportProfile.NUBANK_CARD_CSV)
