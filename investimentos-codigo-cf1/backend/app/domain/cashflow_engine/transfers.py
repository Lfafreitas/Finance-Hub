"""Casamento de pagamento de fatura (CF-3): puro e conservador.

O extrato da conta traz "Pagamento de fatura" (saída) e a fatura do
cartão traz "Pagamento recebido" (entrada): são as duas pontas da
mesma transferência conta -> cartão. Nos arquivos reais elas têm o
mesmo valor e o mesmo dia.

Só casa quando NÃO HÁ dúvida: cada ponta tem exatamente uma candidata.
Qualquer ambiguidade (dois pagamentos iguais na mesma janela) fica para
decisão manual — casar errado esconderia um gasto ou criaria um.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.models.enums import AccountType

PAYMENT_SENT_TEXT = "pagamento de fatura"
PAYMENT_RECEIVED_TEXT = "pagamento recebido"
DEFAULT_MAX_DAYS = 3


@dataclass(frozen=True)
class TransferCandidate:
    entry_id: UUID
    account_id: UUID
    account_type: AccountType
    institution_id: UUID
    currency_code: str
    entry_date: date
    amount: Decimal
    match_text: str


def _is_payment_sent(candidate: TransferCandidate) -> bool:
    return (
        candidate.account_type not in (AccountType.CREDIT_CARD, AccountType.BROKERAGE)
        and candidate.amount < 0
        and candidate.match_text == PAYMENT_SENT_TEXT
    )


def _is_payment_received(candidate: TransferCandidate) -> bool:
    return (
        candidate.account_type is AccountType.CREDIT_CARD
        and candidate.amount > 0
        and candidate.match_text == PAYMENT_RECEIVED_TEXT
    )


def _compatible(sent: TransferCandidate, received: TransferCandidate, max_days: int) -> bool:
    return (
        sent.institution_id == received.institution_id
        and sent.currency_code == received.currency_code
        and sent.amount == -received.amount
        and abs((sent.entry_date - received.entry_date).days) <= max_days
    )


def find_invoice_payment_pairs(
    candidates: Iterable[TransferCandidate], max_days: int = DEFAULT_MAX_DAYS
) -> list[tuple[TransferCandidate, TransferCandidate]]:
    """Pares (saída na conta, entrada no cartão) sem ambiguidade."""
    items = list(candidates)
    sent = [c for c in items if _is_payment_sent(c)]
    received = [c for c in items if _is_payment_received(c)]
    options = {s.entry_id: [r for r in received if _compatible(s, r, max_days)] for s in sent}
    reverse = {r.entry_id: [s for s in sent if _compatible(s, r, max_days)] for r in received}
    pairs = [
        (s, options[s.entry_id][0])
        for s in sent
        if len(options[s.entry_id]) == 1 and len(reverse[options[s.entry_id][0].entry_id]) == 1
    ]
    return sorted(pairs, key=lambda pair: (pair[0].entry_date, str(pair[0].entry_id)))
