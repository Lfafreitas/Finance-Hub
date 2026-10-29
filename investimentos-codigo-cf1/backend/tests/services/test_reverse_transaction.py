"""Fase 10b, unidade 2: reverse_transaction."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.enums import TransactionSource, TransactionStatus, TransactionType
from app.models.transaction import Transaction
from app.schemas.transaction import TransferCreate
from app.services.exceptions import (
    AccountNotFoundError,
    ReversalInvalidatesHistoryError,
    TransactionAlreadyReversedError,
    TransactionNotFoundError,
    UnsupportedReversalError,
)
from app.services.transaction_service import (
    create_transfer,
    get_position,
    reverse_transaction,
)
from tests.test_persistence import make_account, make_asset, make_institution, make_user

T0 = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
D1 = date(2026, 4, 1)
D2 = date(2026, 4, 2)

_counter = {"n": 0}


def _tx(db, account, asset, ttype, qty=None, price=None, day=D1, gross=None, fees="0"):
    """created_at cresce a cada chamada: ordem de criação == ordem de gravação."""
    _counter["n"] += 1
    quantity = Decimal(qty) if qty is not None else None
    unit_price = Decimal(price) if price is not None else None
    if gross is None:
        gross = quantity * unit_price if quantity is not None and unit_price is not None else 0
    tx = Transaction(
        account_id=account.id,
        asset_id=asset.id if asset is not None else None,
        transaction_type=ttype,
        quantity=quantity,
        unit_price=unit_price,
        fees=Decimal(fees),
        gross_amount=Decimal(gross),
        currency_code="BRL",
        transaction_date=day,
        source=TransactionSource.MANUAL,
        status=TransactionStatus.ACTIVE,
        created_at=T0 + timedelta(seconds=_counter["n"]),
    )
    db.add(tx)
    db.flush()
    return tx


def _setup(db, tag):
    user = make_user(db, email=f"rev-{tag}@example.com")
    account = make_account(db, user, make_institution(db, name=f"Inst Rev {tag}"))
    asset = make_asset(db, ticker=f"RV{tag}")
    return user, account, asset


def _count(db):
    return db.execute(select(func.count()).select_from(Transaction)).scalar_one()


class TestReversaoValida:
    def test_reverte_active_marca_reversed_sem_criar_nova(self, db_session):
        user, account, asset = _setup(db_session, "a1")
        buy = _tx(db_session, account, asset, TransactionType.BUY, "10", "10")
        before = _count(db_session)

        result = reverse_transaction(db_session, user.id, buy.id)

        assert result.id == buy.id
        assert result.status == TransactionStatus.REVERSED
        assert _count(db_session) == before

    def test_nao_altera_campos_financeiros(self, db_session):
        user, account, asset = _setup(db_session, "a2")
        buy = _tx(db_session, account, asset, TransactionType.BUY, "10", "10", fees="1.5")
        snapshot = (buy.quantity, buy.unit_price, buy.fees, buy.gross_amount, buy.transaction_date)

        reverse_transaction(db_session, user.id, buy.id)
        db_session.expire_all()

        fresh = db_session.get(Transaction, buy.id)
        assert (
            fresh.quantity,
            fresh.unit_price,
            fresh.fees,
            fresh.gross_amount,
            fresh.transaction_date,
        ) == snapshot

    def test_buy_sem_dependencia_pode_ser_revertido(self, db_session):
        user, account, asset = _setup(db_session, "a3")
        _tx(db_session, account, asset, TransactionType.BUY, "100", "10")
        second_buy = _tx(db_session, account, asset, TransactionType.BUY, "20", "10")
        _tx(db_session, account, asset, TransactionType.SELL, "50", "12")

        reverse_transaction(db_session, user.id, second_buy.id)

        position = get_position(db_session, user.id, account.id, asset.id)
        assert position.quantity == Decimal(50)

    def test_reverter_sell_e_sempre_valido_e_restaura_posicao(self, db_session):
        user, account, asset = _setup(db_session, "a4")
        _tx(db_session, account, asset, TransactionType.BUY, "100", "10")
        sell = _tx(db_session, account, asset, TransactionType.SELL, "50", "12")

        reverse_transaction(db_session, user.id, sell.id)

        assert get_position(db_session, user.id, account.id, asset.id).quantity == Decimal(100)

    def test_unica_transacao_do_ativo_pode_ser_revertida(self, db_session):
        user, account, asset = _setup(db_session, "a5")
        buy = _tx(db_session, account, asset, TransactionType.BUY, "10", "10")

        reverse_transaction(db_session, user.id, buy.id)

        assert get_position(db_session, user.id, account.id, asset.id) is None

    def test_provento_pode_ser_revertido(self, db_session):
        user, account, asset = _setup(db_session, "a6")
        _tx(db_session, account, asset, TransactionType.BUY, "10", "10")
        dividend = _tx(db_session, account, asset, TransactionType.DIVIDEND, gross="5")

        reverse_transaction(db_session, user.id, dividend.id)

        assert get_position(db_session, user.id, account.id, asset.id).dividends_received == 0

    def test_transacao_sem_ativo_deposito_pode_ser_revertida(self, db_session):
        user, account, _asset = _setup(db_session, "a7")
        deposit = _tx(db_session, account, None, TransactionType.DEPOSIT, gross="500")

        result = reverse_transaction(db_session, user.id, deposit.id)

        assert result.status == TransactionStatus.REVERSED

    def test_deposito_nao_e_validado_contra_posicoes_de_ativos(self, db_session):
        # Reverter um DEPOSIT não deve olhar (nem quebrar por causa de)
        # outras transações da conta.
        user, account, asset = _setup(db_session, "a8")
        _tx(db_session, account, asset, TransactionType.BUY, "10", "10")
        deposit = _tx(db_session, account, None, TransactionType.DEPOSIT, gross="500")

        assert reverse_transaction(db_session, user.id, deposit.id).status == (
            TransactionStatus.REVERSED
        )


class TestHistoricoInvalido:
    def test_buy_com_sell_dependente_e_rejeitado(self, db_session):
        user, account, asset = _setup(db_session, "b1")
        buy = _tx(db_session, account, asset, TransactionType.BUY, "100", "10")
        _tx(db_session, account, asset, TransactionType.SELL, "50", "12")

        with pytest.raises(ReversalInvalidatesHistoryError):
            reverse_transaction(db_session, user.id, buy.id)

        db_session.expire_all()
        assert db_session.get(Transaction, buy.id).status == TransactionStatus.ACTIVE

    def test_reversao_parcialmente_suficiente_ainda_e_rejeitada(self, db_session):
        # BUY 100 + BUY 30 + SELL 110: reverter o BUY de 30 deixa 100 < 110.
        user, account, asset = _setup(db_session, "b2")
        _tx(db_session, account, asset, TransactionType.BUY, "100", "10")
        small = _tx(db_session, account, asset, TransactionType.BUY, "30", "10")
        _tx(db_session, account, asset, TransactionType.SELL, "110", "12")

        with pytest.raises(ReversalInvalidatesHistoryError):
            reverse_transaction(db_session, user.id, small.id)

    def test_bonus_com_sell_dependente_e_rejeitado(self, db_session):
        user, account, asset = _setup(db_session, "b3")
        _tx(db_session, account, asset, TransactionType.BUY, "10", "10")
        bonus = _tx(db_session, account, asset, TransactionType.BONUS_SHARES, "10", None)
        _tx(db_session, account, asset, TransactionType.SELL, "15", "12", day=D2)

        with pytest.raises(ReversalInvalidatesHistoryError):
            reverse_transaction(db_session, user.id, bonus.id)

    def test_mensagem_de_erro_vem_do_engine(self, db_session):
        user, account, asset = _setup(db_session, "b4")
        buy = _tx(db_session, account, asset, TransactionType.BUY, "100", "10")
        _tx(db_session, account, asset, TransactionType.SELL, "50", "12")

        with pytest.raises(ReversalInvalidatesHistoryError, match="só há 0 em posição"):
            reverse_transaction(db_session, user.id, buy.id)

    def test_multiplas_operacoes_reverter_em_ordem_valida(self, db_session):
        user, account, asset = _setup(db_session, "b5")
        buy = _tx(db_session, account, asset, TransactionType.BUY, "100", "10")
        sell = _tx(db_session, account, asset, TransactionType.SELL, "50", "12")

        with pytest.raises(ReversalInvalidatesHistoryError):
            reverse_transaction(db_session, user.id, buy.id)

        # Reverte primeiro o SELL; agora o BUY pode ser revertido.
        reverse_transaction(db_session, user.id, sell.id)
        reverse_transaction(db_session, user.id, buy.id)

        assert get_position(db_session, user.id, account.id, asset.id) is None


class TestOrdenacaoNoHistoricoHipotetico:
    def test_mesmo_dia_respeita_created_at_como_desempate(self, db_session):
        # Mesmo dia; created_at: BUY(10) < SELL(5) < BUY(3).
        user, account, asset = _setup(db_session, "c1")
        big_buy = _tx(db_session, account, asset, TransactionType.BUY, "10", "10")
        _tx(db_session, account, asset, TransactionType.SELL, "5", "12")
        late_buy = _tx(db_session, account, asset, TransactionType.BUY, "3", "10")

        # Sem o BUY de 10, o SELL (que vem antes do BUY de 3) fica sem posição.
        with pytest.raises(ReversalInvalidatesHistoryError):
            reverse_transaction(db_session, user.id, big_buy.id)

        # Sem o BUY de 3, tudo continua válido (o SELL só depende do BUY de 10).
        assert reverse_transaction(db_session, user.id, late_buy.id).status == (
            TransactionStatus.REVERSED
        )

    def test_data_anterior_prevalece_sobre_created_at(self, db_session):
        # BUY gravado DEPOIS, mas com data anterior ao SELL: continua sendo dependência.
        user, account, asset = _setup(db_session, "c2")
        _tx(db_session, account, asset, TransactionType.SELL, "5", "12", day=D2)
        # (o SELL só pôde ser gravado porque o teste insere direto, sem D-A3)
        buy = _tx(db_session, account, asset, TransactionType.BUY, "10", "10", day=D1)

        with pytest.raises(ReversalInvalidatesHistoryError):
            reverse_transaction(db_session, user.id, buy.id)


class TestValidacoesDeAcesso:
    def test_ja_revertida_e_rejeitada(self, db_session):
        user, account, asset = _setup(db_session, "d1")
        buy = _tx(db_session, account, asset, TransactionType.BUY, "10", "10")
        reverse_transaction(db_session, user.id, buy.id)

        with pytest.raises(TransactionAlreadyReversedError):
            reverse_transaction(db_session, user.id, buy.id)

    def test_transacao_inexistente(self, db_session):
        import uuid

        user, _account, _asset = _setup(db_session, "d2")

        with pytest.raises(TransactionNotFoundError):
            reverse_transaction(db_session, user.id, uuid.uuid4())

    def test_ownership_outro_usuario_nao_pode_reverter(self, db_session):
        _owner, account, asset = _setup(db_session, "d3")
        buy = _tx(db_session, account, asset, TransactionType.BUY, "10", "10")
        intruder = make_user(db_session, email="rev-intruder@example.com")

        with pytest.raises(AccountNotFoundError):
            reverse_transaction(db_session, intruder.id, buy.id)

        db_session.expire_all()
        assert db_session.get(Transaction, buy.id).status == TransactionStatus.ACTIVE

    @pytest.mark.parametrize("leg", ["out", "in"])
    def test_pernas_de_transferencia_sao_rejeitadas(self, db_session, leg):
        user, account, _asset = _setup(db_session, f"d4{leg}")
        other = make_account(
            db_session, user, make_institution(db_session, name=f"Inst Dest {leg}"), name="Destino"
        )
        transfer_out, transfer_in = create_transfer(
            db_session,
            user.id,
            TransferCreate(
                from_account_id=account.id,
                to_account_id=other.id,
                gross_amount=Decimal(100),
                transaction_date=D1,
            ),
        )
        target = transfer_out if leg == "out" else transfer_in

        with pytest.raises(UnsupportedReversalError):
            reverse_transaction(db_session, user.id, target.id)

        db_session.expire_all()
        assert db_session.get(Transaction, transfer_out.id).status == TransactionStatus.ACTIVE
        assert db_session.get(Transaction, transfer_in.id).status == TransactionStatus.ACTIVE
