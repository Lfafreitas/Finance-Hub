import io
from decimal import Decimal

import openpyxl
import pytest

from app.models.enums import TransactionType
from app.services.exceptions import ImportParsingError
from app.services.imports.csv_parser import parse_csv
from app.services.imports.ofx_parser import parse_ofx
from app.services.imports.xlsx_parser import parse_xlsx

VALID_OFX = b"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

<OFX>
<SIGNONMSGSRSV1>
<SONRS>
<STATUS>
<CODE>0
<SEVERITY>INFO
</STATUS>
<DTSERVER>20260101120000
<LANGUAGE>POR
</SONRS>
</SIGNONMSGSRSV1>
<BANKMSGSRSV1>
<STMTTRNRS>
<TRNUID>1
<STATUS>
<CODE>0
<SEVERITY>INFO
</STATUS>
<STMTRS>
<CURDEF>BRL
<BANKACCTFROM>
<BANKID>001
<ACCTID>12345
<ACCTTYPE>CHECKING
</BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>20260101
<DTEND>20260131
<STMTTRN>
<TRNTYPE>CREDIT
<DTPOSTED>20260105
<TRNAMT>1000.00
<FITID>ABC123
<MEMO>Deposito
</STMTTRN>
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20260110
<TRNAMT>-250.50
<FITID>ABC124
<MEMO>Saque
</STMTTRN>
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""


class TestParserCSV:
    def test_compra_e_deposito_validos(self):
        content = (
            b"data,tipo,ativo,quantidade,preco_unitario,taxas,valor,moeda\n"
            b"2026-01-05,COMPRA,PETR4,100,32.00,4.90,3204.90,BRL\n"
            b"2026-01-10,DEPOSITO,,,,,1000.00,BRL\n"
        )
        rows = parse_csv(content)
        assert len(rows) == 2
        assert rows[0].transaction_type == TransactionType.BUY
        assert rows[0].asset_ticker == "PETR4"
        assert rows[0].quantity == Decimal(100)
        assert rows[1].transaction_type == TransactionType.DEPOSIT
        assert rows[1].asset_ticker is None

    def test_coluna_obrigatoria_ausente(self):
        content = b"tipo,valor\nCOMPRA,100\n"
        with pytest.raises(ImportParsingError, match="colunas obrigatórias"):
            parse_csv(content)

    def test_tipo_desconhecido(self):
        content = b"data,tipo,valor\n2026-01-01,TIPOINVALIDO,100\n"
        with pytest.raises(ImportParsingError, match="não reconhecido"):
            parse_csv(content)

    def test_compra_sem_ativo_e_erro(self):
        content = b"data,tipo,quantidade,preco_unitario,valor\n2026-01-01,COMPRA,10,10,100\n"
        with pytest.raises(ImportParsingError, match="exige o campo 'ativo'"):
            parse_csv(content)

    def test_data_invalida(self):
        content = b"data,tipo,valor\n05/01/2026,DEPOSITO,100\n"
        with pytest.raises(ImportParsingError, match="data inválida"):
            parse_csv(content)

    def test_arquivo_vazio(self):
        with pytest.raises(ImportParsingError):
            parse_csv(b"")


class TestParserXLSX:
    def _build_xlsx(self, rows: list[list]) -> bytes:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(
            ["data", "tipo", "ativo", "quantidade", "preco_unitario", "taxas", "valor", "moeda"]
        )
        for row in rows:
            ws.append(row)
        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    def test_compra_valida(self):
        content = self._build_xlsx(
            [["2026-01-05", "COMPRA", "PETR4", 100, 32.0, 4.9, 3204.9, "BRL"]]
        )
        rows = parse_xlsx(content)
        assert len(rows) == 1
        assert rows[0].transaction_type == TransactionType.BUY
        assert rows[0].quantity == Decimal(100)

    def test_linha_em_branco_e_ignorada(self):
        content = self._build_xlsx(
            [
                ["2026-01-05", "COMPRA", "PETR4", 100, 32.0, 4.9, 3204.9, "BRL"],
                [None, None, None, None, None, None, None, None],
                ["2026-01-06", "DEPOSITO", None, None, None, None, 500.0, "BRL"],
            ]
        )
        rows = parse_xlsx(content)
        assert len(rows) == 2


class TestParserOFX:
    def test_extrato_bancario_valido(self):
        rows = parse_ofx(VALID_OFX)
        assert len(rows) == 2
        assert rows[0].transaction_type == TransactionType.DEPOSIT
        assert rows[0].native_reference == "ABC123"
        assert rows[0].gross_amount == Decimal("1000.00")
        assert rows[1].transaction_type == TransactionType.WITHDRAWAL
        assert rows[1].native_reference == "ABC124"
        assert rows[1].gross_amount == Decimal("250.50")

    def test_arquivo_invalido(self):
        with pytest.raises(ImportParsingError):
            parse_ofx(b"isso nao e um ofx valido")


class TestXlsxCelulasTipadas:
    """Planilha real: a coluna de data é uma CÉLULA DE DATA do Excel
    (o openpyxl entrega `datetime`), e os números são células numéricas.
    """

    def _build(self, rows):
        import io

        wb = openpyxl.Workbook()
        ws = wb.active
        for row in rows:
            ws.append(row)
        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    def test_celula_de_data_e_numeros_nativos(self):
        from datetime import date, datetime
        from decimal import Decimal

        content = self._build(
            [
                [
                    "data",
                    "tipo",
                    "ativo",
                    "quantidade",
                    "preco_unitario",
                    "taxas",
                    "valor",
                    "moeda",
                ],
                [
                    datetime(2026, 1, 5),  # noqa: DTZ001 — célula de data do Excel é naive
                    "COMPRA",
                    "PETR4",
                    100,
                    30.55,
                    1.5,
                    3055,
                    "BRL",
                ],
                [date(2026, 1, 6), "DEPOSITO", None, None, None, None, 250.75, "BRL"],
            ]
        )

        rows = parse_xlsx(content)

        assert rows[0].transaction_date == date(2026, 1, 5)
        assert rows[0].quantity == Decimal(100)
        assert rows[0].unit_price == Decimal("30.55")
        assert rows[0].fees == Decimal("1.5")
        assert rows[1].transaction_date == date(2026, 1, 6)
        assert rows[1].gross_amount == Decimal("250.75")
