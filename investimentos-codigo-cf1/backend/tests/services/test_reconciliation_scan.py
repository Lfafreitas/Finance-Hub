"""Fase 10b, unidade 5: serviço de scan de reconciliação.

Não testa resolve/IGNORE/KEEP_BOTH/MERGE/reverse_transaction — isso é
de unidades futuras. Aqui só: descoberta de pares e criação de
ReconciliationLog PENDING.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.enums import (
    ReconciliationStatus,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.models.portfolio import Portfolio
from app.models.reconciliation_log import ReconciliationLog
from app.models.transaction import Transaction
from app.services.exceptions import (
    AccountNotFoundError,
    InvalidScanScopeError,
    PortfolioNotFoundError,
)
from app.services.reconciliation_service import scan_for_reconciliation
from tests.test_persistence import make_account, make_asset, make_institution, make_user

D = date(2026, 7, 1)
MANUAL = TransactionSource.MANUAL
CSV = TransactionSource.IMPORT_CSV


def _tx(db, account, asset, source, qty="100", price="30", gross=None, day=D, status=None):
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
        status=status or TransactionStatus.ACTIVE,
    )
    db.add(tx)
    db.flush()
    return tx


def _setup(db, tag):
    user = make_user(db, email=f"scan-{tag}@example.com")
    account = make_account(db, user, make_institution(db, name=f"Inst Scan {tag}"))
    asset = make_asset(db, ticker=f"SC{tag}")
    return user, account, asset


def _make_portfolio(db, user, name="Geral"):
    portfolio = Portfolio(user_id=user.id, name=name)
    db.add(portfolio)
    db.flush()
    return portfolio


class TestEscopoPorConta:
    def test_scan_por_account_id_encontra_par_de_fontes_diferentes(self, db_session):
        user, account, asset = _setup(db_session, "a1")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)

        created = scan_for_reconciliation(db_session, user.id, account_id=account.id)

        assert len(created) == 1
        assert {created[0].transaction_a_id, created[0].transaction_b_id} == {a.id, b.id}
        assert created[0].status == ReconciliationStatus.PENDING

    def test_account_id_inexistente_ou_de_outro_usuario(self, db_session):
        user, _account, _asset = _setup(db_session, "a2")
        _other_user, other_account, _ = _setup(db_session, "a2b")

        with pytest.raises(AccountNotFoundError):
            scan_for_reconciliation(db_session, user.id, account_id=other_account.id)
        with pytest.raises(AccountNotFoundError):
            scan_for_reconciliation(db_session, user.id, account_id=uuid.uuid4())


class TestEscopoPorPortfolio:
    def test_scan_por_portfolio_id_cobre_contas_do_portfolio(self, db_session):
        user, account1, asset = _setup(db_session, "p1")
        account2 = make_account(db_session, user, make_institution(db_session, name="Inst P1b"))
        portfolio = _make_portfolio(db_session, user)
        account1.portfolio_id = portfolio.id
        account2.portfolio_id = portfolio.id
        db_session.flush()
        a = _tx(db_session, account1, asset, MANUAL)
        asset2 = make_asset(db_session, ticker="SCP1B")
        b = _tx(db_session, account2, asset2, CSV)

        created = scan_for_reconciliation(db_session, user.id, portfolio_id=portfolio.id)

        # Contas diferentes -> não é candidato, mesmo no mesmo portfolio.
        assert created == []
        assert db_session.get(Transaction, a.id).status == TransactionStatus.ACTIVE
        assert db_session.get(Transaction, b.id).status == TransactionStatus.ACTIVE

    def test_scan_por_portfolio_encontra_par_dentro_da_mesma_conta(self, db_session):
        user, account, asset = _setup(db_session, "p2")
        portfolio = _make_portfolio(db_session, user)
        account.portfolio_id = portfolio.id
        db_session.flush()
        _tx(db_session, account, asset, MANUAL)
        _tx(db_session, account, asset, CSV)

        created = scan_for_reconciliation(db_session, user.id, portfolio_id=portfolio.id)

        assert len(created) == 1

    def test_conta_fora_do_portfolio_nao_entra_no_scan(self, db_session):
        user, account, asset = _setup(db_session, "p3")
        outside_account = make_account(db_session, user, make_institution(db_session, name="Fora"))
        portfolio = _make_portfolio(db_session, user)
        account.portfolio_id = portfolio.id
        db_session.flush()
        _tx(db_session, account, asset, MANUAL)
        _tx(db_session, outside_account, asset, CSV)  # mesmo asset, conta fora do portfolio

        created = scan_for_reconciliation(db_session, user.id, portfolio_id=portfolio.id)

        assert created == []

    def test_portfolio_id_inexistente_ou_de_outro_usuario(self, db_session):
        user, _account, _asset = _setup(db_session, "p4")
        other_user, _oa, _oasset = _setup(db_session, "p4b")
        other_portfolio = _make_portfolio(db_session, other_user)

        with pytest.raises(PortfolioNotFoundError):
            scan_for_reconciliation(db_session, user.id, portfolio_id=other_portfolio.id)
        with pytest.raises(PortfolioNotFoundError):
            scan_for_reconciliation(db_session, user.id, portfolio_id=uuid.uuid4())

    def test_scan_nao_inclui_conta_de_outro_usuario_mesmo_se_apontar_para_o_portfolio(
        self, db_session
    ):
        # Cenário defensivo: só é alcançável por inconsistência de dados
        # (o schema não impede um portfolio_id "vazado" para outro
        # usuário), mas o scan nunca deve misturar dados entre usuários.
        user, account, asset = _setup(db_session, "p5b")
        portfolio = _make_portfolio(db_session, user)
        account.portfolio_id = portfolio.id
        _intruder, intruder_account, intruder_asset = _setup(db_session, "p5c")
        intruder_account.portfolio_id = portfolio.id  # aponta pro portfolio de outro usuário
        db_session.flush()
        _tx(db_session, account, asset, MANUAL)
        _tx(db_session, account, asset, CSV)
        _tx(db_session, intruder_account, intruder_asset, MANUAL)
        _tx(db_session, intruder_account, intruder_asset, CSV)

        created = scan_for_reconciliation(db_session, user.id, portfolio_id=portfolio.id)

        assert len(created) == 1
        for tx_id in (created[0].transaction_a_id, created[0].transaction_b_id):
            assert db_session.get(Transaction, tx_id).account_id == account.id

    def test_account_id_e_portfolio_id_juntos_e_invalido(self, db_session):
        user, account, _asset = _setup(db_session, "p5")
        portfolio = _make_portfolio(db_session, user)

        with pytest.raises(InvalidScanScopeError):
            scan_for_reconciliation(
                db_session, user.id, account_id=account.id, portfolio_id=portfolio.id
            )


class TestEscopoGlobal:
    def test_scan_global_cobre_todas_as_contas_do_usuario(self, db_session):
        user, account1, asset1 = _setup(db_session, "g1")
        account2 = make_account(db_session, user, make_institution(db_session, name="Inst G1b"))
        _tx(db_session, account1, asset1, MANUAL)
        _tx(db_session, account1, asset1, CSV)
        _tx(db_session, account2, asset1, MANUAL)
        _tx(db_session, account2, asset1, CSV)

        created = scan_for_reconciliation(db_session, user.id)

        assert len(created) == 2

    def test_isolamento_entre_usuarios_no_scan_global(self, db_session):
        user_a, account_a, asset_a = _setup(db_session, "g2a")
        _user_b, account_b, asset_b = _setup(db_session, "g2b")
        _tx(db_session, account_a, asset_a, MANUAL)
        _tx(db_session, account_a, asset_a, CSV)
        _tx(db_session, account_b, asset_b, MANUAL)
        _tx(db_session, account_b, asset_b, CSV)

        created_a = scan_for_reconciliation(db_session, user_a.id)

        assert len(created_a) == 1
        (log,) = created_a
        for tx_id in (log.transaction_a_id, log.transaction_b_id):
            assert db_session.get(Transaction, tx_id).account_id == account_a.id

    def test_usuario_sem_contas_devolve_lista_vazia(self, db_session):
        user = make_user(db_session, email="scan-sem-conta@example.com")

        assert scan_for_reconciliation(db_session, user.id) == []


class TestClassificacaoNoLog:
    def test_equivalent_entre_fontes_diferentes_gera_pending(self, db_session):
        user, account, asset = _setup(db_session, "c1")
        _tx(db_session, account, asset, MANUAL)
        _tx(db_session, account, asset, CSV)

        (log,) = scan_for_reconciliation(db_session, user.id, account_id=account.id)

        assert log.status == ReconciliationStatus.PENDING
        assert log.match_reason.startswith("EQUIVALENT")

    def test_divergent_entre_fontes_diferentes_gera_pending(self, db_session):
        user, account, asset = _setup(db_session, "c2")
        _tx(db_session, account, asset, MANUAL, qty="100", gross="3000")
        _tx(db_session, account, asset, CSV, qty="105", gross="3150")

        (log,) = scan_for_reconciliation(db_session, user.id, account_id=account.id)

        assert log.status == ReconciliationStatus.PENDING
        assert log.match_reason.startswith("DIVERGENT")

    def test_mesma_source_identica_nao_gera_log(self, db_session):
        user, account, asset = _setup(db_session, "c3")
        _tx(db_session, account, asset, MANUAL)
        _tx(db_session, account, asset, MANUAL)

        assert scan_for_reconciliation(db_session, user.id, account_id=account.id) == []

    def test_mesma_source_divergente_gera_log(self, db_session):
        user, account, asset = _setup(db_session, "c4")
        _tx(db_session, account, asset, MANUAL, qty="100", gross="3000")
        _tx(db_session, account, asset, MANUAL, qty="105", gross="3150")

        assert len(scan_for_reconciliation(db_session, user.id, account_id=account.id)) == 1

    def test_nenhum_merge_ou_reversao_automatica(self, db_session):
        user, account, asset = _setup(db_session, "c5")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)

        (log,) = scan_for_reconciliation(db_session, user.id, account_id=account.id)

        assert log.surviving_transaction_id is None
        assert log.reversed_transaction_id is None
        assert db_session.get(Transaction, a.id).status == TransactionStatus.ACTIVE
        assert db_session.get(Transaction, b.id).status == TransactionStatus.ACTIVE


class TestReversedForaDoScan:
    def test_transacao_reversed_nao_entra_no_matching(self, db_session):
        user, account, asset = _setup(db_session, "r1")
        _tx(db_session, account, asset, MANUAL)
        _tx(db_session, account, asset, CSV, status=TransactionStatus.REVERSED)

        assert scan_for_reconciliation(db_session, user.id, account_id=account.id) == []

    def test_com_apenas_uma_active_nao_ha_par_possivel(self, db_session):
        user, account, asset = _setup(db_session, "r2")
        _tx(db_session, account, asset, MANUAL)

        assert scan_for_reconciliation(db_session, user.id, account_id=account.id) == []

    def test_sem_nenhuma_transacao_devolve_vazio(self, db_session):
        user, account, _asset = _setup(db_session, "r3")

        assert scan_for_reconciliation(db_session, user.id, account_id=account.id) == []


class TestParesNaoDuplicados:
    def test_par_ja_existente_nao_e_recriado(self, db_session):
        user, account, asset = _setup(db_session, "d1")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        first = scan_for_reconciliation(db_session, user.id, account_id=account.id)
        assert len(first) == 1

        second = scan_for_reconciliation(db_session, user.id, account_id=account.id)

        assert second == []
        count = (
            db_session.execute(
                select(ReconciliationLog).where(
                    ReconciliationLog.transaction_a_id.in_([a.id, b.id]),
                    ReconciliationLog.transaction_b_id.in_([a.id, b.id]),
                )
            )
            .scalars()
            .all()
        )
        assert len(count) == 1

    def test_par_ja_resolvido_nao_e_reapresentado(self, db_session):
        from datetime import UTC, datetime

        user, account, asset = _setup(db_session, "d2")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        first_id, second_id = sorted([a.id, b.id])
        db_session.add(
            ReconciliationLog(
                user_id=user.id,
                transaction_a_id=first_id,
                transaction_b_id=second_id,
                match_reason="resolvido manualmente antes do scan",
                status=ReconciliationStatus.IGNORED,
                resolved_at=datetime(2026, 6, 1, tzinfo=UTC),
            )
        )
        db_session.flush()

        created = scan_for_reconciliation(db_session, user.id, account_id=account.id)

        assert created == []

    def test_par_a_b_e_b_a_resulta_em_apenas_um_log(self, db_session):
        # A ordem de criação no banco não determina qual é "A" ou "B":
        # o resultado final é sempre um único log, com o par canônico.
        user, account, asset = _setup(db_session, "d3")
        first = _tx(db_session, account, asset, CSV)  # id potencialmente maior ou menor
        second = _tx(db_session, account, asset, MANUAL)

        created = scan_for_reconciliation(db_session, user.id, account_id=account.id)

        assert len(created) == 1
        assert created[0].transaction_a_id < created[0].transaction_b_id
        assert {created[0].transaction_a_id, created[0].transaction_b_id} == {first.id, second.id}


class TestMultiplasTransacoes:
    def test_multiplas_transacoes_geram_todos_os_pares_validos_sem_duplicacao(self, db_session):
        user, account, asset = _setup(db_session, "m1")
        # 3 MANUAL idênticas entre si (não candidatas na mesma source) +
        # 1 CSV idêntica (candidata a cada uma das 3 MANUAL).
        m1 = _tx(db_session, account, asset, MANUAL)
        m2 = _tx(db_session, account, asset, MANUAL)
        m3 = _tx(db_session, account, asset, MANUAL)
        c1 = _tx(db_session, account, asset, CSV)

        created = scan_for_reconciliation(db_session, user.id, account_id=account.id)

        pairs = {frozenset((log.transaction_a_id, log.transaction_b_id)) for log in created}
        assert pairs == {
            frozenset((m1.id, c1.id)),
            frozenset((m2.id, c1.id)),
            frozenset((m3.id, c1.id)),
        }
        assert len(created) == 3  # nenhuma combinação MANUAL-MANUAL, nenhuma duplicata

    def test_transacoes_de_tipos_diferentes_nao_cruzam(self, db_session):
        user, account, asset = _setup(db_session, "m2")
        _tx(db_session, account, asset, MANUAL)
        sell = Transaction(
            account_id=account.id,
            asset_id=asset.id,
            transaction_type=TransactionType.SELL,
            quantity=Decimal(10),
            unit_price=Decimal(30),
            fees=Decimal(0),
            gross_amount=Decimal(300),
            currency_code="BRL",
            transaction_date=D,
            source=CSV,
            status=TransactionStatus.ACTIVE,
        )
        db_session.add(sell)
        db_session.flush()

        assert scan_for_reconciliation(db_session, user.id, account_id=account.id) == []


class TestNaoAlteraTransactions:
    def test_scan_nao_altera_nenhum_campo_das_transactions(self, db_session):
        user, account, asset = _setup(db_session, "n1")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV, qty="105", gross="3150")
        snapshot_a = (a.status, a.quantity, a.gross_amount, a.transaction_type)
        snapshot_b = (b.status, b.quantity, b.gross_amount, b.transaction_type)

        scan_for_reconciliation(db_session, user.id, account_id=account.id)
        db_session.expire_all()

        assert (
            db_session.get(Transaction, a.id).status,
            db_session.get(Transaction, a.id).quantity,
            db_session.get(Transaction, a.id).gross_amount,
            db_session.get(Transaction, a.id).transaction_type,
        ) == snapshot_a
        assert (
            db_session.get(Transaction, b.id).status,
            db_session.get(Transaction, b.id).quantity,
            db_session.get(Transaction, b.id).gross_amount,
            db_session.get(Transaction, b.id).transaction_type,
        ) == snapshot_b
