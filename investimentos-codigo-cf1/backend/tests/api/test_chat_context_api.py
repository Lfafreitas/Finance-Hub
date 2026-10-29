"""GET /insights/chat-context: resumo da carteira para levar ao Claude."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from app.core.config import settings
from app.models.cashflow_entry import CashflowEntry
from app.models.enums import AccountType, CashflowNature, TransactionSource
from tests.api.test_kpis_api import _buy
from tests.cashflow_helpers import make_typed_account
from tests.test_persistence import make_asset, make_institution

TODAY = date.today()


def test_contexto_com_investimentos_alocacao_e_sem_moedas_somadas(
    api_client, db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "insights_dir", tmp_path)
    client, user = api_client
    inst = make_institution(db_session, name=f"Corretora C {uuid.uuid4().hex[:6]}")
    account = make_typed_account(db_session, user, inst, "Conta", AccountType.BROKERAGE, "USD")
    tag = uuid.uuid4().hex[:4].upper()
    etf = make_asset(db_session, f"E{tag}", "ETF_US", "US", "USD")
    _buy(client, account, etf, "2", "100", (TODAY - timedelta(days=5)).isoformat())
    client.put(
        "/performance/allocation/USD",
        json={"targets": [{"asset_class_code": "ETF_US", "target_weight": "1"}]},
    )

    text = client.get("/insights/chat-context").json()["text"]

    assert text.startswith("# Minha carteira")
    assert "nunca são somados" in text
    assert f"| {etf.ticker} | ETF (Exterior) | 100,0% |" in text
    assert "US$ 200,00" in text
    assert "(alvo 100,0%)" in text
    assert len(text) <= 6000


def test_contexto_nao_leva_descricao_de_extrato(api_client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "insights_dir", tmp_path)
    client, user = api_client
    inst = make_institution(db_session, name=f"Banco X {uuid.uuid4().hex[:6]}")
    conta = make_typed_account(
        db_session, user, inst, "Conta corrente", AccountType.CHECKING, "BRL"
    )
    db_session.add(
        CashflowEntry(
            account_id=conta.id,
            entry_date=TODAY - timedelta(days=1),
            amount=Decimal("-42.50"),
            currency_code="BRL",
            description="PADARIA SEGREDO DO USUARIO",
            source=TransactionSource.MANUAL,
            nature=CashflowNature.EXPENSE,
        )
    )
    db_session.flush()

    text = client.get("/insights/chat-context").json()["text"]

    assert "SEGREDO" not in text
    assert "## Patrimônio por moeda" in text


def test_resumo_traz_reserva_em_meses_e_empresas_por_tras_dos_etfs(
    api_client, db_session, tmp_path, monkeypatch
):
    """Só totais do caixa (nunca descrição de extrato) e a exposição às
    empresas dos ETFs, quando a análise trouxe a composição.
    """
    from app.core.config import settings
    from tests.api.test_insights_api import _write
    from tests.api.test_insights_v3_api import _portfolio, _v3

    monkeypatch.setattr(settings, "insights_dir", tmp_path)
    client, user = api_client
    qqq, _vnq = _portfolio(client, db_session, user)
    _write(tmp_path, "2026-10-24.json", _v3(qqq=qqq))

    text = client.get("/insights/chat-context").json()["text"]

    assert "## Empresas por trás dos ETFs (USD)" in text
    assert "NVIDIA 5,0%" in text and "Microsoft 4,0%" in text


def test_resumo_traz_cobertura_da_reserva_sem_descricoes(
    api_client, db_session, tmp_path, monkeypatch
):
    from tests.api.test_visual_api import _day_in

    monkeypatch.setattr(settings, "insights_dir", tmp_path)
    client, user = api_client
    inst = make_institution(db_session, name=f"Banco R {uuid.uuid4().hex[:6]}")
    conta = make_typed_account(db_session, user, inst, "Conta", AccountType.CHECKING, "BRL")
    caixinha = make_typed_account(db_session, user, inst, "Caixinha", AccountType.SAVINGS, "BRL")
    for account, amount, description, nature in (
        (caixinha, "9000", "Saldo", CashflowNature.ADJUSTMENT),
        (conta, "4000", "SALARIO EMPRESA SEGREDO", CashflowNature.INCOME),
        (conta, "-3000", "ALUGUEL SEGREDO", CashflowNature.EXPENSE),
    ):
        db_session.add(
            CashflowEntry(
                account_id=account.id,
                entry_date=_day_in(1),
                amount=Decimal(amount),
                currency_code="BRL",
                description=description,
                source=TransactionSource.MANUAL,
                nature=nature,
            )
        )
    db_session.flush()

    text = client.get("/insights/chat-context").json()["text"]

    assert "## Reserva e poupança (meses fechados)" in text
    assert "cobre 3,0 meses de gasto" in text and "taxa de poupança +25,0%" in text
    assert "SEGREDO" not in text
