"""Fatura-PDF: leitura da fatura do cartão em PDF e conferência com o
resumo da própria fatura. Faturas fictícias (tests/fatura_pdf_helpers).
"""

from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import CashflowImportProfile
from app.services.cashflow_imports.nubank_card_pdf import (
    parse_card_pdf,
    parse_fatura_lines,
    pdf_lines,
    resolve_year,
)
from app.services.cashflow_imports.parsers import detect_profile, parse_statement
from app.services.exceptions import ImportParsingError
from tests.fatura_pdf_helpers import FATURA_LINES, build_pdf, cells, fatura_pdf

D = Decimal


def lines(*, drop=(), replace=None, add=()):
    """A fatura fictícia como células, com linhas tiradas/trocadas."""
    out = []
    for line in cells(FATURA_LINES):
        if any(line[0] == d[0] and line[-1] == d[-1] for d in drop):
            continue
        for old, new in (replace or {}).items():
            if tuple(line) == old:
                line = new
        out.append(line)
    return out + [list(a) for a in add]


def by_description(parsed):
    return {r.description: r for r in parsed.rows}


class TestLeitura:
    def test_linhas_no_sinal_do_livro_com_ano_e_sem_o_final_do_cartao(self):
        parsed = parse_fatura_lines(cells(FATURA_LINES))
        rows = by_description(parsed)

        assert parsed.profile is CashflowImportProfile.NUBANK_CARD_PDF
        assert parsed.currency_code == "BRL"
        assert [(r.entry_date, r.amount) for r in parsed.rows] == [
            (date(2025, 12, 30), D("-50.00")),  # "30 DEZ" numa fatura de 2026
            (date(2026, 1, 3), D("-35.40")),
            (date(2026, 1, 10), D("-100.00")),
            (date(2026, 1, 12), D("20.00")),  # estorno devolve
            (date(2026, 1, 15), D("1.46")),  # desconto de antecipação devolve
            (date(2026, 1, 5), D("300.00")),  # pagamento entra no cartão
            (date(2026, 1, 8), D("-141.54")),  # Pix no crédito parcelado é compra
        ]
        assert "Loja Exemplo - Parcela 2/3" in rows  # sem "•••• 1234"
        assert [r.row_index for r in parsed.rows] == list(range(7))
        assert all(r.error is None and r.external_id is None for r in parsed.rows)

    def test_pagamento_vira_pagamento_recebido_como_no_csv(self):
        rows = by_description(parse_fatura_lines(cells(FATURA_LINES)))

        assert rows["Pagamento recebido"].amount == D("300.00")
        assert not any(r.startswith("Pagamento em") for r in rows)

    def test_saldo_restante_e_linha_zerada_ficam_de_fora(self):
        zero = lines(add=[["20 JAN", "Anuidade Exemplo", "R$ 0,00"]])

        rows = by_description(parse_fatura_lines(zero))

        assert not any(r.startswith("Saldo restante") for r in rows)
        assert "Anuidade Exemplo" not in rows
        assert len(rows) == 7

    def test_estorno_usa_o_texto_do_csv_na_chave(self):
        quoted = lines(
            replace={
                ("12 JAN", "Estorno de Loja Devolvida", "-R$ 20,00"): [
                    "12 JAN",
                    'Estorno de "Loja Devolvida"',
                    "−R$ 20,00",
                ]
            }
        )

        rows = parse_fatura_lines(quoted).rows
        refund = next(r for r in rows if r.description.startswith("Estorno"))

        assert refund.description == 'Estorno de "Loja Devolvida"'
        assert refund.dedupe_text == "Loja Devolvida"
        assert refund.amount == D("20.00")  # sinal "−" (U+2212) também é lido
        assert all(r.dedupe_text is None for r in rows if r is not refund)

    def test_periodo_vencimento_total_e_fatura_anterior(self):
        parsed = parse_fatura_lines(cells(FATURA_LINES))

        assert (parsed.period_start, parsed.period_end) == (date(2025, 12, 30), date(2026, 1, 30))
        assert parsed.statement_due_date == date(2026, 2, 6)
        # O "Total a pagar" das simulações de parcelamento não é o total.
        assert parsed.statement_total == D("305.48")
        assert parsed.statement_previous == D("300.00")
        assert parsed.statement_balance is None  # fatura não é saldo de conta

    def test_conferencias_passaram_e_ficam_registradas(self):
        checks = parse_fatura_lines(cells(FATURA_LINES)).checks

        assert [(c.label, c.expected, c.found, c.ok) for c in checks] == [
            ("Compras, estornos e créditos", D("305.48"), D("305.48"), True),
            ("Pagamentos recebidos", D("-300.00"), D("-300.00"), True),
        ]

    def test_valor_com_milhar(self):
        big = lines(
            replace={
                ("10 JAN", "•••• 1234", "Mercado Exemplo", "R$ 100,00"): [
                    "10 JAN",
                    "•••• 1234",
                    "Mercado Exemplo",
                    "R$ 1.100,00",
                ],
                (
                    "Total de compras de todos os cartões, 30 DEZ a 30 JAN",
                    "R$ 326,94",
                ): ["Total de compras de todos os cartões, 30 DEZ a 30 JAN", "R$ 1.326,94"],
            }
        )

        rows = by_description(parse_fatura_lines(big))

        assert rows["Mercado Exemplo"].amount == D("-1100.00")

    def test_sem_outros_lancamentos_o_total_e_so_o_de_compras(self):
        simple = [
            ["FATURA 06 MAI 2025", "EMISSÃO E ENVIO 29 ABR 2025"],
            ["RESUMO DA FATURA ATUAL"],
            ["Fatura anterior", "R$ 0,00"],
            ["Pagamento recebido", "R$ 0,00"],
            ["Total de compras de todos os cartões, 30 MAR a 29 ABR", "R$ 10,00"],
            ["Total a pagar", "R$ 10,00"],
            ["TRANSAÇÕES", "DE 30 MAR A 29 ABR"],
            ["02 ABR", "Padaria", "R$ 10,00"],
        ]

        parsed = parse_fatura_lines(simple)

        assert [(r.entry_date, r.amount) for r in parsed.rows] == [(date(2025, 4, 2), D("-10.00"))]


class TestConferencia:
    def test_compra_que_faltou_ler_recusa_o_arquivo(self):
        missing = lines(drop=[["03 JAN", "R$ 35,40"]])

        with pytest.raises(ImportParsingError) as exc:
            parse_fatura_lines(missing)

        message = str(exc.value)
        assert "não confere" in message
        assert "lidos R$ 270,08, a fatura diz R$ 305,48" in message
        assert "Nada foi importado" in message
        assert "Pagamentos" not in message  # só a conferência que falhou

    def test_um_centavo_de_diferenca_ja_recusa(self):
        off = lines(
            replace={
                ("03 JAN", "Lanche - NuPay", "R$ 35,40"): ["03 JAN", "Lanche - NuPay", "R$ 35,41"]
            }
        )

        with pytest.raises(ImportParsingError, match="não confere"):
            parse_fatura_lines(off)

    def test_pagamento_que_faltou_ler_recusa_o_arquivo(self):
        missing = lines(drop=[["05 JAN", "-R$ 300,00"]])

        with pytest.raises(ImportParsingError, match="Pagamentos recebidos: lidos R\\$ 0,00"):
            parse_fatura_lines(missing)

    def test_outros_lancamentos_entram_na_conta(self):
        # Sem "Outros lançamentos" no resumo, estorno e desconto sobram.
        without = lines(drop=[["Outros lançamentos", "-R$ 21,46"]])

        with pytest.raises(ImportParsingError, match="a fatura diz R\\$ 326,94"):
            parse_fatura_lines(without)

    def test_saldo_restante_com_valor_que_a_fatura_soma_recusa(self):
        carried = lines(
            replace={
                ("06 JAN", "Saldo restante da fatura anterior", "R$ 0,00"): [
                    "06 JAN",
                    "Saldo restante da fatura anterior",
                    "R$ 50,00",
                ],
                (
                    "Total de compras de todos os cartões, 30 DEZ a 30 JAN",
                    "R$ 326,94",
                ): ["Total de compras de todos os cartões, 30 DEZ a 30 JAN", "R$ 376,94"],
            }
        )

        with pytest.raises(ImportParsingError, match="não confere"):
            parse_fatura_lines(carried)

    def test_pagamento_nao_conta_como_compra(self):
        # Um pagamento lido como compra fecharia as compras errado.
        as_purchase = lines(
            replace={
                ("05 JAN", "Pagamento em 05 JAN", "-R$ 300,00"): [
                    "05 JAN",
                    "Pagamento via boleto",
                    "-R$ 300,00",
                ]
            }
        )

        with pytest.raises(ImportParsingError, match="Compras, estornos e créditos"):
            parse_fatura_lines(as_purchase)

    def test_linha_datada_sem_valor_recusa(self):
        broken = lines(add=[["20 JAN", "Compra sem valor"]])

        with pytest.raises(ImportParsingError, match="sem valor legível"):
            parse_fatura_lines(broken)

    def test_sem_resumo_nao_importa(self):
        no_summary = [c for c in cells(FATURA_LINES) if not c[0].startswith("RESUMO")]

        with pytest.raises(ImportParsingError, match="resumo da fatura"):
            parse_fatura_lines(no_summary)

    def test_sem_cabecalho_nao_e_fatura(self):
        with pytest.raises(ImportParsingError, match="não parece uma fatura"):
            parse_fatura_lines(cells(FATURA_LINES)[1:])

    def test_sem_secao_de_transacoes_nao_importa(self):
        no_tx = [c for c in cells(FATURA_LINES) if not c[0].startswith("TRANSAÇÕES")]

        with pytest.raises(ImportParsingError, match="TRANSAÇÕES"):
            parse_fatura_lines(no_tx)


class TestAno:
    @pytest.mark.parametrize(
        ("day", "month", "reference", "expected"),
        [
            (30, 12, date(2026, 1, 30), date(2025, 12, 30)),
            (5, 1, date(2026, 1, 30), date(2026, 1, 5)),
            (30, 1, date(2026, 1, 30), date(2026, 1, 30)),
            # Poucos dias depois da emissão ainda é do mesmo ano.
            (8, 2, date(2026, 1, 30), date(2026, 2, 8)),
            (11, 2, date(2026, 1, 30), date(2025, 2, 11)),
        ],
    )
    def test_data_sem_ano(self, day, month, reference, expected):
        assert resolve_year(day, month, reference) == expected

    def test_sem_data_de_emissao_usa_o_vencimento(self):
        no_issue = lines(
            replace={("FATURA 06 FEV 2026", "EMISSÃO E ENVIO 30 JAN 2026"): ["FATURA 06 FEV 2026"]}
        )

        rows = parse_fatura_lines(no_issue).rows

        assert rows[0].entry_date == date(2025, 12, 30)


class TestPdf:
    def test_pdf_de_verdade_em_duas_paginas(self):
        content = fatura_pdf(split_at=12)

        assert detect_profile(content) is CashflowImportProfile.NUBANK_CARD_PDF
        parsed = parse_statement(content)
        assert parsed.rows == parse_fatura_lines(cells(FATURA_LINES)).rows

    def test_celulas_na_mesma_altura_viram_uma_linha_em_ordem(self):
        content = build_pdf([[[(300, "direita"), (40, "esquerda")], [(40, "abaixo")]]])

        assert pdf_lines(content) == [["esquerda", "direita"], ["abaixo"]]

    def test_pdf_quebrado_e_erro_de_leitura(self):
        with pytest.raises(ImportParsingError):
            parse_card_pdf(b"%PDF-1.4 isto nao e um pdf")

    def test_pdf_que_nao_e_fatura(self):
        content = build_pdf([[[(40, "Contrato de aluguel")]]])

        with pytest.raises(ImportParsingError, match="não parece uma fatura"):
            parse_card_pdf(content)


CARD_OFX = b"""OFXHEADER:100
DATA:OFXSGML
<OFX>
<CREDITCARDMSGSRSV1><CCSTMTTRNRS><CCSTMTRS>
<CURDEF>BRL</CURDEF>
<BANKTRANLIST>
<DTSTART>20250929000000[-3:BRT]</DTSTART>
<DTEND>20251030000000[-3:BRT]</DTEND>
<STMTTRN>
<TRNTYPE>DEBIT</TRNTYPE>
<DTPOSTED>20251002000000[-3:BRT]</DTPOSTED>
<TRNAMT>-4.00</TRNAMT>
<FITID>aaaa-1</FITID>
<MEMO>IOF de compra internacional</MEMO>
</STMTTRN>
<STMTTRN>
<TRNTYPE>DEBIT</TRNTYPE>
<DTPOSTED>20251002000000[-3:BRT]</DTPOSTED>
<TRNAMT>-114.50</TRNAMT>
<FITID>aaaa-1</FITID>
<MEMO>Assinatura Exemplo</MEMO>
</STMTTRN>
<STMTTRN>
<TRNTYPE>CREDIT</TRNTYPE>
<DTPOSTED>20250929000000[-3:BRT]</DTPOSTED>
<TRNAMT>1250.00</TRNAMT>
<FITID>bbbb-2</FITID>
<MEMO>Pagamento recebido</MEMO>
</STMTTRN>
</BANKTRANLIST>
<LEDGERBAL><BALAMT>-987.82</BALAMT><DTASOF>20251030000000[-3:BRT]</DTASOF></LEDGERBAL>
</CCSTMTRS></CCSTMTTRNRS></CREDITCARDMSGSRSV1>
</OFX>
"""


class TestOfxDoCartao:
    def test_detecta_e_le_no_sinal_do_livro(self):
        assert detect_profile(CARD_OFX) is CashflowImportProfile.NUBANK_CARD_OFX

        parsed = parse_statement(CARD_OFX)

        assert [(r.entry_date, r.amount, r.description) for r in parsed.rows] == [
            (date(2025, 10, 2), D("-4.00"), "IOF de compra internacional"),
            (date(2025, 10, 2), D("-114.50"), "Assinatura Exemplo"),
            (date(2025, 9, 29), D("1250.00"), "Pagamento recebido"),
        ]
        assert parsed.currency_code == "BRL"
        assert (parsed.period_start, parsed.period_end) == (date(2025, 9, 29), date(2025, 10, 30))

    def test_fitid_repetido_nao_e_chave_nem_erro_e_nao_ha_saldo(self):
        parsed = parse_statement(CARD_OFX)

        assert all(r.external_id is None and r.error is None for r in parsed.rows)
        assert parsed.statement_balance is None

    def test_ofx_da_conta_continua_sendo_da_conta(self):
        account = CARD_OFX.replace(b"CCSTMTRS", b"STMTRS")

        assert detect_profile(account) is CashflowImportProfile.NUBANK_ACCOUNT_OFX
