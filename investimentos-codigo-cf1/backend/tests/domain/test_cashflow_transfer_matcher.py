"""CF-3: casamento de pagamento de fatura (puro)."""

import uuid
from datetime import date
from decimal import Decimal

from app.domain.cashflow_engine import TransferCandidate, find_invoice_payment_pairs
from app.models.enums import AccountType

NUBANK = uuid.uuid4()
OTHER_BANK = uuid.uuid4()
CHECKING = uuid.uuid4()
CARD = uuid.uuid4()


def sent(amount="-1190.60", day=30, institution=NUBANK, text="pagamento de fatura", **kwargs):
    values = {
        "entry_id": uuid.uuid4(),
        "account_id": CHECKING,
        "account_type": AccountType.CHECKING,
        "institution_id": institution,
        "currency_code": "BRL",
        "entry_date": date(2026, 8, day),
        "amount": Decimal(amount),
        "match_text": text,
    }
    values.update(kwargs)
    return TransferCandidate(**values)


def received(amount="1190.60", day=30, institution=NUBANK, text="pagamento recebido", **kwargs):
    return sent(
        amount,
        day,
        institution,
        text,
        **{"account_id": CARD, "account_type": AccountType.CREDIT_CARD, **kwargs},
    )


class TestCasaSemAmbiguidade:
    def test_mesmo_valor_mesmo_dia_mesmo_banco(self):
        out, incoming = sent(), received()

        assert find_invoice_payment_pairs([incoming, out]) == [(out, incoming)]

    def test_aceita_ate_tres_dias_de_diferenca(self):
        out = sent(day=27)

        assert len(find_invoice_payment_pairs([out, received(day=30)])) == 1
        assert find_invoice_payment_pairs([sent(day=26), received(day=30)]) == []

    def test_dois_pagamentos_distintos_casam_cada_um_com_o_seu(self):
        a_out, a_in = sent("-100", 5), received("100", 5)
        b_out, b_in = sent("-200", 20), received("200", 20)

        pairs = find_invoice_payment_pairs([b_in, a_out, b_out, a_in])

        assert pairs == [(a_out, a_in), (b_out, b_in)]


class TestNaoCasa:
    def test_valores_diferentes(self):
        assert find_invoice_payment_pairs([sent("-100"), received("100.01")]) == []

    def test_bancos_diferentes(self):
        assert find_invoice_payment_pairs([sent(), received(institution=OTHER_BANK)]) == []

    def test_moedas_diferentes(self):
        assert find_invoice_payment_pairs([sent(), received(currency_code="USD")]) == []

    def test_texto_que_nao_e_pagamento_de_fatura(self):
        assert find_invoice_payment_pairs([sent(text="pagamento de boleto"), received()]) == []
        assert find_invoice_payment_pairs([sent(), received(text="estorno")]) == []

    def test_saida_precisa_ser_negativa_e_entrada_positiva(self):
        assert find_invoice_payment_pairs([sent("1190.60"), received("-1190.60")]) == []

    def test_pagamento_recebido_fora_de_cartao_nao_e_fatura(self):
        not_card = received(account_type=AccountType.SAVINGS)

        assert find_invoice_payment_pairs([sent(), not_card]) == []

    def test_saida_em_conta_de_cartao_nao_e_pagamento(self):
        from_card = sent(account_type=AccountType.CREDIT_CARD)

        assert find_invoice_payment_pairs([from_card, received()]) == []

    def test_duas_saidas_para_uma_entrada_e_ambiguo(self):
        assert find_invoice_payment_pairs([sent(day=29), sent(day=30), received()]) == []

    def test_uma_saida_para_duas_entradas_e_ambiguo(self):
        assert find_invoice_payment_pairs([sent(), received(day=29), received(day=30)]) == []

    def test_ambiguidade_em_um_valor_nao_impede_o_outro(self):
        clear_out, clear_in = sent("-50", 10), received("50", 10)
        candidates = [sent(day=29), sent(day=30), received(), clear_out, clear_in]

        assert find_invoice_payment_pairs(candidates) == [(clear_out, clear_in)]

    def test_lista_vazia(self):
        assert find_invoice_payment_pairs([]) == []
