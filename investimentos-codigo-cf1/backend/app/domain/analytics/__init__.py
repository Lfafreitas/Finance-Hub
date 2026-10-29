"""Análises da carteira (Análises-1): cenários, concentração e ritmo de
aporte. Funções puras, sem banco: recebem números e datas, devolvem
números. Toda premissa usada volta junto com o resultado.
"""

from app.domain.analytics.concentration import (
    ConcentrationResult,
    Slice,
    WeightItem,
    concentration,
)
from app.domain.analytics.contributions import ContributionPace, contribution_pace
from app.domain.analytics.scenarios import (
    Holding,
    HoldingAssumption,
    ScenarioResult,
    asset_group,
    portfolio_scenarios,
)

__all__ = [
    "ConcentrationResult",
    "ContributionPace",
    "Holding",
    "HoldingAssumption",
    "ScenarioResult",
    "Slice",
    "WeightItem",
    "asset_group",
    "concentration",
    "contribution_pace",
    "portfolio_scenarios",
]
