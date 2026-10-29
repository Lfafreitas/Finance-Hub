from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import TransactionSource, TransactionStatus, TransactionType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction
from app.services import dashboard_service
from app.services.exceptions import PortfolioNotFoundError
from tests.test_persistence import make_account, make_asset, make_institution, make_user


def _brl(summary):
    """O bloco BRL de `totals_by_currency` — a única fonte de totais."""
    assert [block.currency_code for block in summary.totals_by_currency] == ["BRL"]
    return summary.totals_by_currency[0]


def _deposit(db, account, amount, day=1, month=1):
    txn = Transaction(
        account_id=account.id,
        asset_id=None,
        transaction_type=TransactionType.DEPOSIT,
        fees=Decimal(0),
        gross_amount=Decimal(amount),
        currency_code="BRL",
        transaction_date=date(2026, month, day),
        source=TransactionSource.MANUAL,
    )
    db.add(txn)
    db.flush()
    return txn


def _buy(db, account, asset, quantity, unit_price, day=1, month=1):
    txn = Transaction(
        account_id=account.id,
        asset_id=asset.id,
        transaction_type=TransactionType.BUY,
        quantity=Decimal(quantity),
        unit_price=Decimal(unit_price),
        fees=Decimal(0),
        gross_amount=Decimal(quantity) * Decimal(unit_price),
        currency_code="BRL",
        transaction_date=date(2026, month, day),
        source=TransactionSource.MANUAL,
    )
    db.add(txn)
    db.flush()
    return txn


class TestValoresDeMercadoSemCotacao:
    def test_sem_cotacao_os_valores_de_mercado_ficam_none_com_motivo(self, db_session):
        user = make_user(db_session, email="dash-market@example.com")
        institution = make_institution(db_session, name="Inst Dash Market")
        account = make_account(db_session, user, institution, name="Conta Dash Market")
        asset = make_asset(db_session, ticker="DASH1")

        _deposit(db_session, account, 1000)
        _buy(db_session, account, asset, 10, 50)

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)

        assert _brl(summary).market_value is None
        assert _brl(summary).unrealized_pnl is None
        assert _brl(summary).current_return is None
        assert "DASH1" in _brl(summary).market_data_unavailable_reason
        assert summary.positions[0].market_value is None
        assert summary.positions[0].unrealized_pnl is None
        assert "DASH1" in summary.positions[0].unavailable_reason


class TestAgregacaoDePosicoes:
    def test_soma_custo_de_aquisicao_de_duas_contas(self, db_session):
        user = make_user(db_session, email="dash-agg@example.com")
        institution = make_institution(db_session, name="Inst Dash Agg")
        conta_a = make_account(db_session, user, institution, name="Conta A Dash Agg")
        conta_b = make_account(db_session, user, institution, name="Conta B Dash Agg")
        asset = make_asset(db_session, ticker="DASH2")

        _buy(db_session, conta_a, asset, 10, 10)  # custo 100
        _buy(db_session, conta_b, asset, 5, 20)  # custo 100

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)

        assert _brl(summary).total_cost_basis == Decimal(200)
        assert len(summary.positions) == 2


class TestDistribuicaoPorCustoDeAquisicao:
    def test_percentual_calculado_por_custo_nao_por_mercado(self, db_session):
        user = make_user(db_session, email="dash-alloc@example.com")
        institution = make_institution(db_session, name="Inst Dash Alloc")
        account = make_account(db_session, user, institution, name="Conta Dash Alloc")
        asset1 = make_asset(db_session, ticker="ALLOC1")
        asset2 = make_asset(db_session, ticker="ALLOC2")

        _buy(db_session, account, asset1, 10, 10)  # custo 100 -> 25%
        _buy(db_session, account, asset2, 10, 30)  # custo 300 -> 75%

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)
        by_ticker = {a.asset_ticker: a.percentage for a in _brl(summary).allocation}

        assert by_ticker["ALLOC1"] == pytest.approx(Decimal(25), abs=Decimal("0.01"))
        assert by_ticker["ALLOC2"] == pytest.approx(Decimal(75), abs=Decimal("0.01"))


class TestFiltroPorPortfolio:
    def test_filtra_apenas_contas_do_portfolio(self, db_session):
        user = make_user(db_session, email="dash-portfolio@example.com")
        institution = make_institution(db_session, name="Inst Dash Portfolio")
        portfolio = Portfolio(user_id=user.id, name="Aposentadoria Dash")
        db_session.add(portfolio)
        db_session.flush()

        conta_dentro = make_account(db_session, user, institution, name="Conta Dentro Portfolio")
        conta_dentro.portfolio_id = portfolio.id
        conta_fora = make_account(db_session, user, institution, name="Conta Fora Portfolio")
        db_session.flush()

        _deposit(db_session, conta_dentro, 1000)
        _deposit(db_session, conta_fora, 5000)

        summary_portfolio = dashboard_service.get_dashboard_summary(
            db_session, user.id, portfolio.id
        )
        summary_consolidado = dashboard_service.get_dashboard_summary(db_session, user.id, None)

        assert _brl(summary_portfolio).net_contributions == Decimal(1000)
        assert _brl(summary_consolidado).net_contributions == Decimal(6000)

    def test_portfolio_de_outro_usuario_e_rejeitado(self, db_session):
        user = make_user(db_session, email="dash-portfolio-owner@example.com")
        outro_user = make_user(db_session, email="dash-portfolio-outro@example.com")
        portfolio_de_outro = Portfolio(user_id=outro_user.id, name="Não é sua")
        db_session.add(portfolio_de_outro)
        db_session.flush()

        with pytest.raises(PortfolioNotFoundError):
            dashboard_service.get_dashboard_summary(db_session, user.id, portfolio_de_outro.id)


class TestNeutralidadeDeTransferencia:
    def test_transferencia_interna_ao_escopo_nao_conta_como_aporte(self, db_session):
        user = make_user(db_session, email="dash-transfer@example.com")
        institution = make_institution(db_session, name="Inst Dash Transfer")
        origem = make_account(db_session, user, institution, name="Origem Dash Transfer")
        destino = make_account(db_session, user, institution, name="Destino Dash Transfer")

        _deposit(db_session, origem, 1000)

        saida = Transaction(
            account_id=origem.id,
            asset_id=None,
            transaction_type=TransactionType.TRANSFER_OUT,
            fees=Decimal(0),
            gross_amount=Decimal(300),
            currency_code="BRL",
            transaction_date=date(2026, 1, 2),
            source=TransactionSource.MANUAL,
        )
        db_session.add(saida)
        db_session.flush()
        entrada = Transaction(
            account_id=destino.id,
            asset_id=None,
            transaction_type=TransactionType.TRANSFER_IN,
            fees=Decimal(0),
            gross_amount=Decimal(300),
            currency_code="BRL",
            transaction_date=date(2026, 1, 2),
            source=TransactionSource.MANUAL,
            linked_transaction_id=saida.id,
        )
        db_session.add(entrada)
        db_session.flush()
        saida.linked_transaction_id = entrada.id
        db_session.flush()

        # Consolidado (as duas contas no escopo): transferência é neutra.
        summary = dashboard_service.get_dashboard_summary(db_session, user.id)
        assert _brl(summary).net_contributions == Decimal(1000)

    def test_transferencia_para_fora_do_escopo_conta_como_saida(self, db_session):
        """Mesmo cenário, mas agora o escopo é um portfolio que contém
        só a conta de ORIGEM — a transferência sai do escopo, então
        deve contar como retirada daquele portfolio.
        """
        user = make_user(db_session, email="dash-transfer-scope@example.com")
        institution = make_institution(db_session, name="Inst Dash Transfer Scope")
        portfolio = Portfolio(user_id=user.id, name="Só Origem")
        db_session.add(portfolio)
        db_session.flush()

        origem = make_account(db_session, user, institution, name="Origem Scope")
        origem.portfolio_id = portfolio.id
        destino = make_account(
            db_session, user, institution, name="Destino Scope"
        )  # fora do portfolio
        db_session.flush()

        _deposit(db_session, origem, 1000)

        saida = Transaction(
            account_id=origem.id,
            asset_id=None,
            transaction_type=TransactionType.TRANSFER_OUT,
            fees=Decimal(0),
            gross_amount=Decimal(300),
            currency_code="BRL",
            transaction_date=date(2026, 1, 2),
            source=TransactionSource.MANUAL,
        )
        db_session.add(saida)
        db_session.flush()
        entrada = Transaction(
            account_id=destino.id,
            asset_id=None,
            transaction_type=TransactionType.TRANSFER_IN,
            fees=Decimal(0),
            gross_amount=Decimal(300),
            currency_code="BRL",
            transaction_date=date(2026, 1, 2),
            source=TransactionSource.MANUAL,
            linked_transaction_id=saida.id,
        )
        db_session.add(entrada)
        db_session.flush()
        saida.linked_transaction_id = entrada.id
        db_session.flush()

        summary = dashboard_service.get_dashboard_summary(db_session, user.id, portfolio.id)
        assert _brl(summary).net_contributions == Decimal(700)  # 1000 - 300 (saiu do escopo)


def _sell(db, account, asset, quantity, unit_price, day=1, month=1):
    txn = Transaction(
        account_id=account.id,
        asset_id=asset.id,
        transaction_type=TransactionType.SELL,
        quantity=Decimal(quantity),
        unit_price=Decimal(unit_price),
        fees=Decimal(0),
        gross_amount=Decimal(quantity) * Decimal(unit_price),
        currency_code="BRL",
        transaction_date=date(2026, month, day),
        source=TransactionSource.MANUAL,
    )
    db.add(txn)
    db.flush()
    return txn


class TestRentabilidadeFase8:
    def test_posicao_fechada_traz_xirr_no_summary(self, db_session):
        user = make_user(db_session, email="rent-fechada@example.com")
        institution = make_institution(db_session, name="Inst Rent Fechada")
        account = make_account(db_session, user, institution, name="Conta Rent Fechada")
        asset = make_asset(db_session, ticker="RENT1")

        _buy(db_session, account, asset, 100, 10, day=1, month=1)
        _sell(db_session, account, asset, 100, 12, day=1, month=6)

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)
        position = next(p for p in summary.positions if p.asset_id == asset.id)

        assert position.is_closed is True
        assert position.xirr is not None
        assert position.realized_cost_basis == Decimal(1000)
        assert position.realized_return_pct == Decimal("0.2")
        assert _brl(summary).is_closed is True
        assert _brl(summary).xirr is not None

    def test_posicao_aberta_mantem_xirr_none_no_summary(self, db_session):
        user = make_user(db_session, email="rent-aberta@example.com")
        institution = make_institution(db_session, name="Inst Rent Aberta")
        account = make_account(db_session, user, institution, name="Conta Rent Aberta")
        asset = make_asset(db_session, ticker="RENT2")

        _buy(db_session, account, asset, 100, 10, day=1, month=1)

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)
        position = next(p for p in summary.positions if p.asset_id == asset.id)

        assert position.is_closed is False
        assert position.xirr is None
        assert _brl(summary).is_closed is False
        assert _brl(summary).xirr is None
        assert "posição aberta" in _brl(summary).profitability_unavailable_reason

    def test_transacao_reversed_nao_entra_na_agregacao(self, db_session):
        user = make_user(db_session, email="dash-reversed@example.com")
        institution = make_institution(db_session, name="Inst Dash Reversed")
        account = make_account(db_session, user, institution, name="Conta Dash Reversed")

        _deposit(db_session, account, 1000)
        errado = _deposit(db_session, account, 99999, day=2)
        errado.status = TransactionStatus.REVERSED
        db_session.flush()

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)
        assert _brl(summary).net_contributions == Decimal(1000)
