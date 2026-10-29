"""CDI do Banco Central: leitura da resposta."""

from datetime import date
from decimal import Decimal

import pytest

from app.services.market_data.bcb import parse_sgs
from app.services.market_data.yahoo import MarketDataError


def test_le_data_brasileira_e_taxa_em_porcento_ao_dia():
    rows = parse_sgs(
        [{"data": "02/10/2026", "valor": "0.055131"}, {"data": "01/10/2026", "valor": "0,055131"}]
    )

    assert rows == [
        (date(2026, 10, 1), Decimal("0.055131")),
        (date(2026, 10, 2), Decimal("0.055131")),
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"erro": "x"},
        [{"data": "2026-10-01", "valor": "0.05"}],
        [{"data": "01/10/2026"}],
        [{"data": "01/10/2026", "valor": "abc"}],
        [{"data": "01/10/2026", "valor": "5.5"}],  # 5,5% ao dia: absurdo
        [{"data": "01/10/2026", "valor": "-0.01"}],
        [{"data": "01/10/2026", "valor": "NaN"}],
    ],
)
def test_resposta_fora_do_formato_recusa(payload):
    with pytest.raises(MarketDataError):
        parse_sgs(payload)
