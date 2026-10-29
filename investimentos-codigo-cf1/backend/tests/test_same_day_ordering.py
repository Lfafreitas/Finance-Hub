"""Fase 10b, unidade 1: ordenação determinística de Transactions no
mesmo dia. `created_at` é só desempate técnico (ordem de gravação),
não a ordem econômica real das operações.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.domain.financial_engine.position import PositionCalculator
from app.models.enums import TransactionSource, TransactionStatus, TransactionType
from app.models.transaction import Transaction
from app.repositories.transactions import (
    TRANSACTION_ORDER,
    get_active_transactions,
    list_transactions,
)
from tests.test_persistence import make_account, make_asset, make_institution, make_user

DAY = date(2026, 3, 10)
T0 = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


def _tx(db, account, asset, ttype, qty, price, created_at, day=DAY, status=None):
    tx = Transaction(
        account_id=account.id,
        asset_id=asset.id,
        transaction_type=ttype,
        quantity=Decimal(qty),
        unit_price=Decimal(price),
        fees=Decimal(0),
        gross_amount=Decimal(qty) * Decimal(price),
        currency_code="BRL",
        transaction_date=day,
        source=TransactionSource.MANUAL,
        status=status or TransactionStatus.ACTIVE,
        created_at=created_at,
    )
    db.add(tx)
    db.flush()
    return tx


def _setup(db):
    user = make_user(db, email="ordering@example.com")
    account = make_account(db, user, make_institution(db, name="Inst Ordering"))
    asset = make_asset(db, ticker="ORD1")
    return account, asset


def test_transaction_order_documenta_desempate_tecnico():
    assert [c.key for c in TRANSACTION_ORDER] == ["transaction_date", "created_at"]


def test_mesmo_dia_desempata_por_created_at_nao_por_ordem_de_insercao(db_session):
    account, asset = _setup(db_session)
    # Inserida PRIMEIRO no banco, mas com created_at MAIS TARDIO.
    late = _tx(db_session, account, asset, TransactionType.SELL, "5", "12", T0 + timedelta(hours=1))
    early = _tx(db_session, account, asset, TransactionType.BUY, "10", "10", T0)

    facts = get_active_transactions(db_session, account.id, asset.id)

    assert [f.id for f in facts] == [early.id, late.id]


def test_data_continua_sendo_o_criterio_principal(db_session):
    account, asset = _setup(db_session)
    # created_at mais antigo, mas transaction_date mais recente.
    later_day = _tx(
        db_session, account, asset, TransactionType.BUY, "1", "10", T0, day=date(2026, 3, 11)
    )
    earlier_day = _tx(
        db_session,
        account,
        asset,
        TransactionType.BUY,
        "1",
        "10",
        T0 + timedelta(days=5),
        day=date(2026, 3, 9),
    )

    facts = get_active_transactions(db_session, account.id, asset.id)

    assert [f.id for f in facts] == [earlier_day.id, later_day.id]


def test_multiplas_transacoes_no_mesmo_dia_ordem_estavel(db_session):
    account, asset = _setup(db_session)
    txs = [
        _tx(db_session, account, asset, TransactionType.BUY, "1", "10", T0 + timedelta(minutes=m))
        for m in (30, 10, 20, 0)
    ]
    expected = sorted(txs, key=lambda t: t.created_at)

    first = [f.id for f in get_active_transactions(db_session, account.id, asset.id)]
    second = [f.id for f in get_active_transactions(db_session, account.id, asset.id)]

    assert first == second == [t.id for t in expected]


def test_list_transactions_usa_mesma_ordenacao(db_session):
    account, asset = _setup(db_session)
    late = _tx(db_session, account, asset, TransactionType.SELL, "1", "12", T0 + timedelta(hours=1))
    early = _tx(db_session, account, asset, TransactionType.BUY, "1", "10", T0)

    assert [t.id for t in list_transactions(db_session, account.id, asset.id)] == [
        early.id,
        late.id,
    ]


def test_desempate_afeta_resultado_do_engine_de_forma_deterministica(db_session):
    account, asset = _setup(db_session)
    # SELL gravado antes no banco, mas created_at posterior ao BUY: sem
    # desempate por created_at o Engine poderia ver SELL primeiro e falhar.
    _tx(db_session, account, asset, TransactionType.SELL, "5", "12", T0 + timedelta(minutes=1))
    _tx(db_session, account, asset, TransactionType.BUY, "10", "10", T0)

    position = PositionCalculator.calculate(get_active_transactions(db_session, account.id))

    assert position.quantity == Decimal(5)


def test_reversed_continua_fora_do_calculo_mas_visivel_no_historico(db_session):
    account, asset = _setup(db_session)
    _tx(db_session, account, asset, TransactionType.BUY, "1", "10", T0)
    reversed_tx = _tx(
        db_session,
        account,
        asset,
        TransactionType.BUY,
        "1",
        "10",
        T0 + timedelta(minutes=1),
        status=TransactionStatus.REVERSED,
    )

    assert reversed_tx.id not in [f.id for f in get_active_transactions(db_session, account.id)]
    assert reversed_tx.id in [t.id for t in list_transactions(db_session, account.id)]
