from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class PositionSummary(BaseModel):
    """Uma posição (conta, ativo).

    `currency_code` é a moeda EFETIVAMENTE registrada nas Transactions
    ativas do par — nunca a do cadastro do ativo. Quando o par tem
    Transactions ativas em mais de uma moeda, a posição é
    INCONSISTENTE: `currency_code` fica `None`,
    `currency_inconsistency_reason` diz quais moedas foram encontradas,
    e todo campo monetário e de rentabilidade fica `None` — o engine
    teria somado moedas diferentes, e um número assim não é exibido.
    `quantity` (e `is_closed`, que só depende dela) continua válida:
    quantidade não tem moeda.
    """

    account_id: UUID
    asset_id: UUID
    asset_ticker: str
    asset_name: str
    currency_code: str | None
    currency_inconsistency_reason: str | None = None
    quantity: Decimal
    average_cost: Decimal | None
    total_cost_basis: Decimal | None
    realized_gain: Decimal | None
    dividends_received: Decimal | None
    # Fase 8 — rentabilidade realizada (não depende de cotação).
    realized_cost_basis: Decimal | None = None
    realized_return_pct: Decimal | None = None
    is_closed: bool = False
    xirr: Decimal | None = None
    cagr: Decimal | None = None
    profitability_unavailable_reason: str | None = None
    # Fase 12 — valoração a mercado. Preenchidos quando existe uma
    # cotação do ativo (até a data de referência) NA MOEDA da posição;
    # senão ficam `None` e `unavailable_reason` diz por quê — nunca
    # aproximados nem zerados. Posição zerada vale 0 sem precisar de
    # cotação. `market_price_date` é a data da cotação usada: a
    # valoração é "a preços de" essa data, não necessariamente de hoje.
    market_price: Decimal | None = None
    market_price_date: date | None = None
    market_value: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    unrealized_return_pct: Decimal | None = None
    unavailable_reason: str | None = None


class AllocationSlice(BaseModel):
    """Distribuição por CUSTO DE AQUISIÇÃO (D-C4) — não é valor de
    mercado. O rótulo na UI precisa deixar isso explícito. `percentage`
    é sempre relativo ao custo total da MESMA moeda (o bloco em que a
    fatia está) — nunca ao de outra moeda.
    """

    asset_id: UUID
    asset_ticker: str
    asset_name: str
    cost_basis: Decimal
    percentage: Decimal


class ContributionPoint(BaseModel):
    """Um ponto da evolução do CAPITAL APORTADO acumulado (D-C3) — não
    é patrimônio, não reflete desempenho de mercado.
    """

    date: date
    cumulative_net_contribution: Decimal


class DashboardCurrencyTotals(BaseModel):
    """Tudo o que é dinheiro no dashboard, para UMA moeda.

    Regra da correção de moedas: valores de moedas diferentes nunca são
    somados nem convertidos (`fx_rate_to_brl` não é usado aqui). Cada
    bloco agrega só as posições consistentes daquela moeda e só os
    movimentos de caixa lançados nela.
    """

    currency_code: str
    total_cost_basis: Decimal
    total_realized_gain: Decimal
    total_dividends_received: Decimal
    net_contributions: Decimal
    # Fase 8 — rentabilidade realizada agregada das posições DESTA
    # moeda. `is_closed` só reflete quantidade final zero em todas elas
    # (D-D3) — independente de o XIRR em si ter sido calculável.
    total_realized_cost_basis: Decimal = Decimal(0)
    realized_return_pct: Decimal | None = None
    is_closed: bool = False
    xirr: Decimal | None = None
    cagr: Decimal | None = None
    profitability_unavailable_reason: str | None = None
    # Fase 12 — só preenchidos quando TODAS as posições abertas desta
    # moeda têm cotação: uma soma parcial apresentada como total seria
    # um número errado. `current_return` = P&L não realizado / custo
    # das posições abertas (fração; 0.10 = 10%). `market_data_as_of` é
    # a cotação MAIS ANTIGA usada — o total é tão atual quanto ela.
    market_value: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    current_return: Decimal | None = None
    market_data_as_of: date | None = None
    market_data_unavailable_reason: str | None = None
    allocation: list[AllocationSlice]
    contribution_evolution: list[ContributionPoint]


class DashboardSummary(BaseModel):
    """`totals_by_currency` é a ÚNICA fonte de totais (um bloco por
    moeda, ordenado pelo código). Não existe total no nível de cima:
    com mais de uma moeda ele não teria significado, e com uma só ele
    duplicaria o bloco. `positions` lista todas as posições do escopo,
    inclusive as inconsistentes (que não entram em bloco nenhum).
    """

    portfolio_id: UUID | None
    positions: list[PositionSummary]
    totals_by_currency: list[DashboardCurrencyTotals]
