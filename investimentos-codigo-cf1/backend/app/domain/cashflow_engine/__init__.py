"""Motor PURO do livro de caixa (CF-1): sem banco, sem FastAPI, sem
relógio. Recebe fatos já carregados e devolve números.

Regras fixas:

- nunca soma moedas diferentes — todo resultado é por moeda;
- nunca converte câmbio;
- só fatos ACTIVE chegam aqui (o service filtra os REVERSED);
- saldo, resumo e identidade são sempre calculados, nunca persistidos.
"""

from app.domain.cashflow_engine.balance import AccountBalance, BalanceCalculator
from app.domain.cashflow_engine.breakdown import CategoryBreakdownCalculator, CategoryTotals
from app.domain.cashflow_engine.description import (
    ParsedDescription,
    normalize_text,
    parse_description,
)
from app.domain.cashflow_engine.facts import CashEntryFact
from app.domain.cashflow_engine.rules import (
    RuleSpec,
    RuleTarget,
    first_matching_rule,
    rule_matches,
)
from app.domain.cashflow_engine.summary import (
    CashflowIdentityError,
    CashflowSummaryCalculator,
    PeriodSummary,
)
from app.domain.cashflow_engine.transfers import TransferCandidate, find_invoice_payment_pairs

__all__ = [
    "AccountBalance",
    "BalanceCalculator",
    "CashEntryFact",
    "CashflowIdentityError",
    "CashflowSummaryCalculator",
    "CategoryBreakdownCalculator",
    "CategoryTotals",
    "ParsedDescription",
    "PeriodSummary",
    "RuleSpec",
    "RuleTarget",
    "TransferCandidate",
    "find_invoice_payment_pairs",
    "first_matching_rule",
    "normalize_text",
    "parse_description",
    "rule_matches",
]
