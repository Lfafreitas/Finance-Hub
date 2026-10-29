"""CF-2: leitura da descrição. Os formatos são os dos arquivos reais do
Nubank (conta e fatura); os nomes de pessoas são fictícios.
"""

import pytest

from app.domain.cashflow_engine import normalize_text, parse_description


class TestNormalizeText:
    def test_minusculas_sem_acento_e_espacos_colapsados(self):
        assert (
            normalize_text("  Transferência   ENVIADA\tpelo Pix ")
            == "transferencia enviada pelo pix"
        )

    def test_cedilha_e_til(self):
        assert normalize_text("Aplicação Poupança São João") == "aplicacao poupanca sao joao"


class TestFaturaDoCartao:
    @pytest.mark.parametrize(
        "title",
        ["Dm*Spotify P46c9", "Dm *Spotify", "Dm*Spotify", "Ebn *Spotify"],
    )
    def test_as_quatro_grafias_do_spotify_viram_a_mesma_chave(self, title):
        assert parse_description(title).match_text == "spotify"

    def test_parcela_sai_do_nome_e_vira_campo(self):
        parsed = parse_description("Loja Grande - NuPay - Parcela 5/6")

        assert parsed.installment == (5, 6)
        assert parsed.channel == "NuPay"
        assert parsed.counterparty == "Loja Grande"
        assert parsed.match_text == "loja grande"
        assert parsed.movement is None

    def test_parcela_sem_canal(self):
        parsed = parse_description("Converse All Star-Coop - Parcela 5/7")

        assert parsed.installment == (5, 7)
        assert parsed.channel is None
        assert parsed.match_text == "converse all star-coop"

    def test_canal_sem_parcela(self):
        parsed = parse_description("Amazon BR IV - NuPay")

        assert parsed.installment is None
        assert parsed.channel == "NuPay"
        assert parsed.match_text == "amazon br iv"

    def test_marketplace_mantem_o_prefixo_que_e_a_parte_util(self):
        assert (
            parse_description("Amazonmktplc*Lojinha - Parcela 3/5").match_text
            == "amazonmktplc lojinha"
        )

    def test_aplicativo_com_digitos_no_nome_nao_perde_o_nome(self):
        parsed = parse_description("99food *Loja Exemplo")

        assert parsed.match_text == "99food loja exemplo"

    def test_codigo_no_fim_e_removido(self):
        assert parse_description("Airbnb * Hmeyt9hqd8 - Parcela 5/6").match_text == "airbnb"
        assert parse_description("Bus Tarifa*123456789").match_text == "bus tarifa"
        assert parse_description("Bus Tarifa*87654321").match_text == "bus tarifa"

    def test_nome_de_uma_palavra_que_parece_codigo_nao_some(self):
        assert parse_description("Kabum2024").match_text == "kabum2024"

    def test_uber_mantem_o_texto_do_estabelecimento(self):
        assert parse_description("Uber Uber *Trip Help.U").match_text == "uber uber trip help.u"

    def test_fracao_que_nao_e_parcela_fica_no_nome(self):
        parsed = parse_description("Loja 24/7 - 9/3")

        assert parsed.installment is None
        assert parsed.match_text == "loja 24/7 - 9/3"

    def test_pagamento_recebido_e_texto_simples(self):
        parsed = parse_description("Pagamento recebido")

        assert (parsed.movement, parsed.match_text) == (None, "pagamento recebido")


class TestExtratoDaConta:
    def test_pix_enviado_para_pessoa(self):
        parsed = parse_description(
            "Transferência enviada pelo Pix - Fulano de Tal Souza - •••.123.456-•• - "
            "BCO BRADESCO S.A. (0237) Agência: 1234 Conta: 11111-1"
        )

        assert parsed.movement == "Transferência enviada pelo Pix"
        assert parsed.counterparty == "Fulano de Tal Souza"
        assert parsed.document == "•••.123.456-••"
        assert parsed.institution == "BCO BRADESCO S.A. (0237)"
        assert parsed.match_text == "transferencia enviada pelo pix fulano de tal souza"

    def test_pix_para_empresa_traz_cnpj_completo(self):
        parsed = parse_description(
            "Transferência enviada pelo Pix - Barbearia Exemplo - 12.345.678/0001-90 - "
            "PAGSEGURO INTERNET IP S.A. (0290) Agência: 1 Conta: 12345678-9"
        )

        assert parsed.document == "12.345.678/0001-90"
        assert parsed.counterparty == "Barbearia Exemplo"

    def test_mesma_pessoa_em_grafias_diferentes_tem_o_mesmo_documento(self):
        upper = parse_description(
            "Transferência recebida pelo Pix - FULANO DE TAL SOUZA - •••.123.456-•• - "
            "BCO BRADESCO S.A. (0237) Agência: 1234 Conta: 11111-1"
        )
        lower = parse_description(
            "Transferência Recebida - Fulano de Tal Souza - •••.123.456-•• - "
            "NU PAGAMENTOS - IP (0260) Agência: 1 Conta: 987654321-0"
        )

        assert upper.document == lower.document
        assert upper.counterparty.casefold() == lower.counterparty.casefold()
        assert lower.institution == "NU PAGAMENTOS - IP (0260)"

    def test_envio_para_o_titular_sem_banco(self):
        parsed = parse_description(
            "Transferência enviada pelo Pix - TITULAR DA CONTA EXEMPLO (Transferência enviada)"
        )

        assert parsed.counterparty == "TITULAR DA CONTA EXEMPLO"
        assert parsed.document is None
        assert parsed.institution is None
        assert parsed.match_text == "transferencia enviada pelo pix titular da conta exemplo"

    def test_open_banking_e_um_movimento_proprio(self):
        parsed = parse_description(
            "Transferência recebida pelo Pix via Open Banking - TITULAR EXEMPLO - •••.123.456-•• - "
            "ITAÚ UNIBANCO S.A. (0341) Agência: 4321 Conta: 22222-2"
        )

        assert parsed.movement == "Transferência recebida pelo Pix via Open Banking"
        assert parsed.institution == "ITAÚ UNIBANCO S.A. (0341)"

    def test_compra_no_debito(self):
        parsed = parse_description("Compra no débito - SUPER CENTRAL")

        assert parsed.movement == "Compra no débito"
        assert parsed.counterparty == "SUPER CENTRAL"
        assert parsed.match_text == "compra no debito super central"

    def test_pagamento_de_fatura_nao_tem_contraparte(self):
        parsed = parse_description("Pagamento de fatura")

        assert parsed.movement == "Pagamento de fatura"
        assert parsed.counterparty == ""
        assert parsed.match_text == "pagamento de fatura"

    def test_pix_no_credito_parcelado(self):
        parsed = parse_description("Pix no Crédito - Fulano de Tal Souza - 2/5")

        assert parsed.movement == "Pix no Crédito"
        assert parsed.installment == (2, 5)
        assert parsed.counterparty == "Fulano de Tal Souza"
        assert parsed.match_text == "pix no credito fulano de tal souza"

    def test_espacos_extras_nao_mudam_o_resultado(self):
        a = parse_description("Compra no débito - SUPER CENTRAL")
        b = parse_description("  Compra no  débito -   SUPER   CENTRAL ")

        assert a == b
