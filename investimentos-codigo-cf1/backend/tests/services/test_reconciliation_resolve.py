"""Fase 10b, unidade 6: resolução de ReconciliationLog
(IGNORE/KEEP_BOTH/MERGE). Endpoints são testados separadamente em
tests/api/test_reconciliation_api.py.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import (
    ReconciliationStatus,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.models.reconciliation_log import ReconciliationLog
from app.models.transaction import Transaction
from app.schemas.reconciliation import ReconciliationDecision
from app.services.exceptions import (
    InvalidMergeSurvivorError,
    ReconciliationAlreadyResolvedError,
    ReconciliationLogNotFoundError,
    ReversalInvalidatesHistoryError,
    TransactionAlreadyReversedError,
)
from app.services.reconciliation_service import resolve_reconciliation
from tests.test_persistence import make_account, make_asset, make_institution, make_user

D = date(2026, 8, 1)
MANUAL = TransactionSource.MANUAL
CSV = TransactionSource.IMPORT_CSV
DEC = ReconciliationDecision


def _tx(db, account, asset, source, qty="100", price="30", gross=None, day=D):
    quantity, unit_price = Decimal(qty), Decimal(price)
    tx = Transaction(
        account_id=account.id,
        asset_id=asset.id,
        transaction_type=TransactionType.BUY,
        quantity=quantity,
        unit_price=unit_price,
        fees=Decimal(0),
        gross_amount=Decimal(gross) if gross is not None else quantity * unit_price,
        currency_code="BRL",
        transaction_date=day,
        source=source,
        status=TransactionStatus.ACTIVE,
    )
    db.add(tx)
    db.flush()
    return tx


def _setup(db, tag):
    user = make_user(db, email=f"resolve-{tag}@example.com")
    account = make_account(db, user, make_institution(db, name=f"Inst Resolve {tag}"))
    asset = make_asset(db, ticker=f"RS{tag}")
    return user, account, asset


def _pending_log(db, user, a, b, reason="EQUIVALENT: todos os campos comparados são iguais"):
    first, second = sorted([a.id, b.id])
    log = ReconciliationLog(
        user_id=user.id, transaction_a_id=first, transaction_b_id=second, match_reason=reason
    )
    db.add(log)
    db.flush()
    return log


class TestIgnore:
    def test_altera_somente_o_log(self, db_session):
        user, account, asset = _setup(db_session, "i1")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)

        result = resolve_reconciliation(db_session, user.id, log.id, DEC.IGNORE)

        assert result.status == ReconciliationStatus.IGNORED
        assert result.resolved_at is not None
        assert result.surviving_transaction_id is None
        assert result.reversed_transaction_id is None
        assert db_session.get(Transaction, a.id).status == TransactionStatus.ACTIVE
        assert db_session.get(Transaction, b.id).status == TransactionStatus.ACTIVE

    def test_nao_altera_campos_financeiros_das_transactions(self, db_session):
        user, account, asset = _setup(db_session, "i2")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        before = (a.quantity, a.gross_amount, b.quantity, b.gross_amount)
        log = _pending_log(db_session, user, a, b)

        resolve_reconciliation(db_session, user.id, log.id, DEC.IGNORE)
        db_session.expire_all()

        fa, fb = db_session.get(Transaction, a.id), db_session.get(Transaction, b.id)
        assert (fa.quantity, fa.gross_amount, fb.quantity, fb.gross_amount) == before


class TestKeepBoth:
    def test_altera_somente_o_log(self, db_session):
        user, account, asset = _setup(db_session, "k1")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)

        result = resolve_reconciliation(db_session, user.id, log.id, DEC.KEEP_BOTH)

        assert result.status == ReconciliationStatus.KEPT_BOTH
        assert result.resolved_at is not None
        assert result.surviving_transaction_id is None
        assert result.reversed_transaction_id is None
        assert db_session.get(Transaction, a.id).status == TransactionStatus.ACTIVE
        assert db_session.get(Transaction, b.id).status == TransactionStatus.ACTIVE


class TestMergeSucesso:
    def test_merge_com_survivor_a(self, db_session):
        user, account, asset = _setup(db_session, "m1")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)

        result = resolve_reconciliation(
            db_session, user.id, log.id, DEC.MERGE, surviving_transaction_id=a.id
        )

        assert result.status == ReconciliationStatus.MERGED
        assert result.surviving_transaction_id == a.id
        assert result.reversed_transaction_id == b.id
        assert result.resolved_at is not None
        assert db_session.get(Transaction, a.id).status == TransactionStatus.ACTIVE
        assert db_session.get(Transaction, b.id).status == TransactionStatus.REVERSED

    def test_merge_com_survivor_b(self, db_session):
        user, account, asset = _setup(db_session, "m2")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)

        result = resolve_reconciliation(
            db_session, user.id, log.id, DEC.MERGE, surviving_transaction_id=b.id
        )

        assert result.surviving_transaction_id == b.id
        assert result.reversed_transaction_id == a.id
        assert db_session.get(Transaction, a.id).status == TransactionStatus.REVERSED
        assert db_session.get(Transaction, b.id).status == TransactionStatus.ACTIVE

    def test_merge_deixa_exatamente_uma_active_e_uma_reversed(self, db_session):
        user, account, asset = _setup(db_session, "m3")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)

        resolve_reconciliation(
            db_session, user.id, log.id, DEC.MERGE, surviving_transaction_id=a.id
        )

        statuses = {
            db_session.get(Transaction, a.id).status,
            db_session.get(Transaction, b.id).status,
        }
        assert statuses == {TransactionStatus.ACTIVE, TransactionStatus.REVERSED}

    def test_merge_nao_cria_nenhuma_transaction_nova(self, db_session):
        from sqlalchemy import func, select

        user, account, asset = _setup(db_session, "m4")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)
        before = db_session.execute(select(func.count()).select_from(Transaction)).scalar_one()

        resolve_reconciliation(
            db_session, user.id, log.id, DEC.MERGE, surviving_transaction_id=a.id
        )

        after = db_session.execute(select(func.count()).select_from(Transaction)).scalar_one()
        assert after == before

    def test_merge_nao_altera_campos_financeiros_da_sobrevivente(self, db_session):
        user, account, asset = _setup(db_session, "m5")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        before = (a.quantity, a.unit_price, a.gross_amount, a.fees, a.transaction_date)
        log = _pending_log(db_session, user, a, b)

        resolve_reconciliation(
            db_session, user.id, log.id, DEC.MERGE, surviving_transaction_id=a.id
        )
        db_session.expire_all()

        fresh = db_session.get(Transaction, a.id)
        assert (
            fresh.quantity,
            fresh.unit_price,
            fresh.gross_amount,
            fresh.fees,
            fresh.transaction_date,
        ) == before


class TestMergeValidacoes:
    def test_sem_surviving_transaction_id_falha(self, db_session):
        user, account, asset = _setup(db_session, "v1")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)

        with pytest.raises(InvalidMergeSurvivorError):
            resolve_reconciliation(
                db_session, user.id, log.id, DEC.MERGE, surviving_transaction_id=None
            )

        db_session.expire_all()
        assert db_session.get(ReconciliationLog, log.id).status == ReconciliationStatus.PENDING

    def test_survivor_fora_do_par_falha(self, db_session):
        user, account, asset = _setup(db_session, "v2")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        outsider = _tx(db_session, account, asset, MANUAL, gross="99999")
        log = _pending_log(db_session, user, a, b)

        with pytest.raises(InvalidMergeSurvivorError):
            resolve_reconciliation(
                db_session, user.id, log.id, DEC.MERGE, surviving_transaction_id=outsider.id
            )

        db_session.expire_all()
        assert db_session.get(ReconciliationLog, log.id).status == ReconciliationStatus.PENDING
        assert db_session.get(Transaction, outsider.id).status == TransactionStatus.ACTIVE

    def test_survivor_de_transaction_de_outro_usuario_falha(self, db_session):
        user, account, asset = _setup(db_session, "v3")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)
        alheia_id = uuid.uuid4()  # nem existe -- não pertence ao par de qualquer forma

        with pytest.raises(InvalidMergeSurvivorError):
            resolve_reconciliation(
                db_session, user.id, log.id, DEC.MERGE, surviving_transaction_id=alheia_id
            )


class TestMergeHistoricoInvalido:
    """Teste de atomicidade (§9 da aprovação): reverse_transaction falha
    porque a Transaction escolhida para reversão tem um SELL dependente.
    """

    def test_falha_por_historico_invalido_nao_altera_nada(self, db_session):
        user, account, asset = _setup(db_session, "h1")
        buy = _tx(db_session, account, asset, MANUAL, qty="100", price="10", gross="1000")
        buy_csv = _tx(db_session, account, asset, CSV, qty="100", price="10", gross="1000")
        # SELL que depende do BUY (torna a reversão do BUY inválida).
        sell = Transaction(
            account_id=account.id,
            asset_id=asset.id,
            transaction_type=TransactionType.SELL,
            quantity=Decimal(150),
            unit_price=Decimal(12),
            fees=Decimal(0),
            gross_amount=Decimal(1800),
            currency_code="BRL",
            transaction_date=D,
            source=MANUAL,
            status=TransactionStatus.ACTIVE,
        )
        db_session.add(sell)
        db_session.flush()
        log = _pending_log(db_session, user, buy, buy_csv)

        # SAVEPOINT: isola o rollback do que reverse_transaction já
        # tenha preparado, sem desfazer o setup do teste — mesmo efeito
        # prático de uma request real revertida por get_db.
        with pytest.raises(ReversalInvalidatesHistoryError), db_session.begin_nested():
            resolve_reconciliation(
                db_session, user.id, log.id, DEC.MERGE, surviving_transaction_id=buy_csv.id
            )

        db_session.expire_all()
        assert db_session.get(Transaction, buy.id).status == TransactionStatus.ACTIVE
        assert db_session.get(Transaction, buy_csv.id).status == TransactionStatus.ACTIVE
        assert db_session.get(Transaction, sell.id).status == TransactionStatus.ACTIVE

        reloaded = db_session.get(ReconciliationLog, log.id)
        assert reloaded.status == ReconciliationStatus.PENDING
        assert reloaded.surviving_transaction_id is None
        assert reloaded.reversed_transaction_id is None
        assert reloaded.resolved_at is None

    def test_apos_falha_o_merge_pode_ser_tentado_de_novo_com_outro_survivor(self, db_session):
        # Confirma que a falha deixou o log genuinamente PENDING e
        # utilizável — não "meio resolvido". Aqui a dependência é
        # assimétrica de propósito: só reverter `buy_small` funciona.
        user, account, asset = _setup(db_session, "h2")
        buy_small = _tx(db_session, account, asset, MANUAL, qty="40", price="10", gross="400")
        buy_big = _tx(db_session, account, asset, CSV, qty="200", price="10", gross="2000")
        sell = Transaction(
            account_id=account.id,
            asset_id=asset.id,
            transaction_type=TransactionType.SELL,
            quantity=Decimal(100),
            unit_price=Decimal(12),
            fees=Decimal(0),
            gross_amount=Decimal(1200),
            currency_code="BRL",
            transaction_date=D,
            source=MANUAL,
            status=TransactionStatus.ACTIVE,
        )
        db_session.add(sell)
        db_session.flush()
        log = _pending_log(db_session, user, buy_small, buy_big)

        # Tentativa 1: sobrevivente = buy_small -> reverte buy_big (200)
        # -> só sobra buy_small (40), insuficiente para o SELL de 100.
        with pytest.raises(ReversalInvalidatesHistoryError), db_session.begin_nested():
            resolve_reconciliation(
                db_session, user.id, log.id, DEC.MERGE, surviving_transaction_id=buy_small.id
            )

        db_session.expire_all()
        assert db_session.get(ReconciliationLog, log.id).status == ReconciliationStatus.PENDING
        assert db_session.get(Transaction, buy_big.id).status == TransactionStatus.ACTIVE

        # Tentativa 2: sobrevivente = buy_big -> reverte buy_small (40)
        # -> sobra buy_big (200), suficiente para o SELL de 100.
        result = resolve_reconciliation(
            db_session, user.id, log.id, DEC.MERGE, surviving_transaction_id=buy_big.id
        )

        assert result.status == ReconciliationStatus.MERGED
        assert db_session.get(Transaction, buy_small.id).status == TransactionStatus.REVERSED
        assert db_session.get(Transaction, buy_big.id).status == TransactionStatus.ACTIVE


class TestFalhaInesperadaDuranteAResolucao:
    def test_transaction_ja_reversed_no_meio_do_processo_nao_deixa_log_meio_resolvido(
        self, db_session
    ):
        # Simula uma falha "inesperada" dentro de reverse_transaction:
        # a Transaction que seria revertida já está REVERSED (ex.: uma
        # segunda resolução concorrente chegou primeiro). O log
        # permanece PENDING -- não fica com status MERGED parcial.
        user, account, asset = _setup(db_session, "e1")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)
        b.status = TransactionStatus.REVERSED
        db_session.flush()

        with pytest.raises(TransactionAlreadyReversedError), db_session.begin_nested():
            resolve_reconciliation(
                db_session, user.id, log.id, DEC.MERGE, surviving_transaction_id=a.id
            )

        db_session.expire_all()
        assert db_session.get(ReconciliationLog, log.id).status == ReconciliationStatus.PENDING
        assert db_session.get(Transaction, a.id).status == TransactionStatus.ACTIVE


class TestEstadoNaoPodeSerResolvidoDeNovo:
    @pytest.mark.parametrize(
        "status",
        [
            ReconciliationStatus.IGNORED,
            ReconciliationStatus.KEPT_BOTH,
            ReconciliationStatus.MERGED,
            ReconciliationStatus.STALE,
        ],
    )
    def test_status_resolvido_nao_pode_ser_resolvido_novamente(self, db_session, status):
        from datetime import UTC, datetime

        user, account, asset = _setup(db_session, f"s{status.value}")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)
        log.status = status
        if status != ReconciliationStatus.STALE:
            log.resolved_at = datetime(2026, 1, 1, tzinfo=UTC)
        if status == ReconciliationStatus.MERGED:
            log.surviving_transaction_id = a.id
            log.reversed_transaction_id = b.id
        db_session.flush()

        with pytest.raises(ReconciliationAlreadyResolvedError):
            resolve_reconciliation(db_session, user.id, log.id, DEC.IGNORE)

    def test_pending_pode_ser_resolvido(self, db_session):
        user, account, asset = _setup(db_session, "s5")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        log = _pending_log(db_session, user, a, b)

        result = resolve_reconciliation(db_session, user.id, log.id, DEC.IGNORE)

        assert result.status == ReconciliationStatus.IGNORED


class TestOwnership:
    def test_usuario_nao_acessa_log_de_outro(self, db_session):
        user, _account, _asset = _setup(db_session, "o1")
        other_user, other_account, other_asset = _setup(db_session, "o1b")
        a = _tx(db_session, other_account, other_asset, MANUAL)
        b = _tx(db_session, other_account, other_asset, CSV)
        log = _pending_log(db_session, other_user, a, b)

        with pytest.raises(ReconciliationLogNotFoundError):
            resolve_reconciliation(db_session, user.id, log.id, DEC.IGNORE)

        db_session.expire_all()
        assert db_session.get(ReconciliationLog, log.id).status == ReconciliationStatus.PENDING

    def test_log_inexistente(self, db_session):
        user, _account, _asset = _setup(db_session, "o2")

        with pytest.raises(ReconciliationLogNotFoundError):
            resolve_reconciliation(db_session, user.id, uuid.uuid4(), DEC.IGNORE)
