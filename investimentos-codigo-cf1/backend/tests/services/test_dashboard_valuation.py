"""Fase 12: valoração a mercado no dashboard, por moeda.

Regras: cotação mais recente até a data de referência; sem conversão
de moeda; total do bloco só quando TODA posição aberta foi valorada;
posição aberta com cotação ganha XIRR com o valor de mercado como
fluxo final.
"""

from datetime import date
from decimal import Decimal

from app.models.asset_price import AssetPrice
from app.models.enums import PriceSource, TransactionSource, TransactionStatus, TransactionType
from app.models.transaction import Transaction
from app.services import dashboard_service
from tests.test_persistence import make_account, make_asset, make_institution, make_user

REF = date(2026, 6, 30)
BUY, SELL = TransactionType.BUY, TransactionType.SELL


def _setup(db, tag):
    user = make_user(db, email=f"val-{tag}@example.com")
    account = make_account(db, user, make_institution(db, name=f"Inst Val {tag}"))
    return user, account


def _tx(db, account, asset, kind, qty, price, currency="BRL", day=date(2026, 1, 2)):
    tx = Transaction(
        account_id=account.id,
        asset_id=asset.id,
        transaction_type=kind,
        quantity=Decimal(qty),
        unit_price=Decimal(price),
        fees=Decimal(0),
        gross_amount=Decimal(qty) * Decimal(price),
        currency_code=currency,
        transaction_date=day,
        source=TransactionSource.MANUAL,
        status=TransactionStatus.ACTIVE,
    )
    db.add(tx)
    db.flush()
    return tx


def _price(db, asset, price, day, currency=None):
    row = AssetPrice(
        asset_id=asset.id,
        price_date=day,
        price=Decimal(price),
        currency_code=currency or asset.currency_code,
        source=PriceSource.MANUAL,
    )
    db.add(row)
    db.flush()
    return row


def _summary(db, user):
    return dashboard_service.get_dashboard_summary(db, user.id, reference_date=REF)


def _block(summary, currency="BRL"):
    return next(b for b in summary.totals_by_currency if b.currency_code == currency)


class TestPosicaoValorada:
    def test_valor_de_mercado_pnl_e_retorno_da_posicao(self, db_session):
        user, account = _setup(db_session, "1")
        asset = make_asset(db_session, ticker="VAL1")
        _tx(db_session, account, asset, BUY, 100, 30)
        _price(db_session, asset, "33", date(2026, 6, 29))

        position = _summary(db_session, user).positions[0]

        assert position.market_price == Decimal(33)
        assert position.market_price_date == date(2026, 6, 29)
        assert position.market_value == Decimal(3300)
        assert position.unrealized_pnl == Decimal(300)
        assert position.unrealized_return_pct == Decimal("0.1")
        assert position.unavailable_reason is None

    def test_usa_a_cotacao_mais_recente_ate_a_data_de_referencia(self, db_session):
        user, account = _setup(db_session, "2")
        asset = make_asset(db_session, ticker="VAL2")
        _tx(db_session, account, asset, BUY, 10, 10)
        _price(db_session, asset, "11", date(2026, 3, 1))
        _price(db_session, asset, "12", date(2026, 6, 30))  # no dia de referência: vale
        _price(db_session, asset, "99", date(2026, 7, 1))  # depois da referência: ignorada

        position = _summary(db_session, user).positions[0]

        assert position.market_price == Decimal(12)
        assert position.market_price_date == date(2026, 6, 30)
        assert position.market_value == Decimal(120)

    def test_so_cotacao_futura_e_o_mesmo_que_nao_ter_cotacao(self, db_session):
        user, account = _setup(db_session, "3")
        asset = make_asset(db_session, ticker="VAL3")
        _tx(db_session, account, asset, BUY, 10, 10)
        _price(db_session, asset, "99", date(2026, 7, 1))

        position = _summary(db_session, user).positions[0]

        assert position.market_value is None
        assert "VAL3" in position.unavailable_reason

    def test_posicao_zerada_vale_zero_sem_precisar_de_cotacao(self, db_session):
        user, account = _setup(db_session, "4")
        asset = make_asset(db_session, ticker="VAL4")
        _tx(db_session, account, asset, BUY, 10, 10)
        _tx(db_session, account, asset, SELL, 10, 12, day=date(2026, 3, 1))

        summary = _summary(db_session, user)

        position = summary.positions[0]
        assert position.market_value == Decimal(0)
        assert position.unrealized_pnl == Decimal(0)
        assert position.market_price is None
        assert position.unavailable_reason is None
        assert _block(summary).market_value == Decimal(0)

    def test_cotacao_em_moeda_diferente_da_posicao_nao_e_convertida(self, db_session):
        """Posição (legada) em USD num ativo cotado em BRL: a cotação
        não é aplicada nem convertida.
        """
        user, account = _setup(db_session, "5")
        asset = make_asset(db_session, ticker="VAL5")  # ativo e cotação em BRL
        _tx(db_session, account, asset, BUY, 10, 10, currency="USD")
        _price(db_session, asset, "50", date(2026, 6, 1))

        summary = _summary(db_session, user)

        position = summary.positions[0]
        assert position.market_value is None
        assert "BRL" in position.unavailable_reason and "USD" in position.unavailable_reason
        assert _block(summary, "USD").market_value is None

    def test_posicao_inconsistente_continua_sem_nenhum_valor(self, db_session):
        user, account = _setup(db_session, "6")
        asset = make_asset(db_session, ticker="VAL6")
        _tx(db_session, account, asset, BUY, 10, 10, currency="BRL")
        _tx(db_session, account, asset, BUY, 10, 10, currency="USD")
        _price(db_session, asset, "50", date(2026, 6, 1))

        position = _summary(db_session, user).positions[0]

        assert position.currency_code is None
        assert position.market_value is None
        assert position.market_price is None
        assert position.unrealized_pnl is None


class TestTotalDoBloco:
    def test_bloco_soma_as_posicoes_quando_todas_tem_cotacao(self, db_session):
        user, account = _setup(db_session, "7")
        a = make_asset(db_session, ticker="VAL7A")
        b = make_asset(db_session, ticker="VAL7B")
        _tx(db_session, account, a, BUY, 100, 30)  # custo 3000
        _tx(db_session, account, b, BUY, 10, 100)  # custo 1000
        _price(db_session, a, "33", date(2026, 6, 20))  # 3300
        _price(db_session, b, "90", date(2026, 6, 10))  # 900

        block = _block(_summary(db_session, user))

        assert block.market_value == Decimal(4200)
        assert block.unrealized_pnl == Decimal(200)
        assert block.current_return == Decimal(200) / Decimal(4000)
        assert block.market_data_unavailable_reason is None
        # O total é tão atual quanto a cotação MAIS ANTIGA usada.
        assert block.market_data_as_of == date(2026, 6, 10)

    def test_uma_posicao_aberta_sem_cotacao_bloqueia_o_total_do_bloco(self, db_session):
        """Soma parcial não é publicada como total."""
        user, account = _setup(db_session, "8")
        a = make_asset(db_session, ticker="VAL8A")
        b = make_asset(db_session, ticker="VAL8B")
        _tx(db_session, account, a, BUY, 100, 30)
        _tx(db_session, account, b, BUY, 10, 100)
        _price(db_session, a, "33", date(2026, 6, 20))

        summary = _summary(db_session, user)

        block = _block(summary)
        assert block.market_value is None
        assert block.unrealized_pnl is None
        assert block.current_return is None
        assert block.market_data_as_of is None
        assert block.market_data_unavailable_reason == "sem cotação utilizável para: VAL8B"
        # ...mas a posição que TEM cotação continua valorada individualmente.
        valued = next(p for p in summary.positions if p.asset_ticker == "VAL8A")
        assert valued.market_value == Decimal(3300)

    def test_blocos_de_moedas_diferentes_sao_independentes(self, db_session):
        user, account = _setup(db_session, "9")
        br = make_asset(db_session, ticker="VAL9BR")
        us = make_asset(db_session, ticker="VAL9US", country="US", currency_code="USD")
        _tx(db_session, account, br, BUY, 10, 10)
        _tx(db_session, account, us, BUY, 10, 100, currency="USD")
        _price(db_session, us, "110", date(2026, 6, 20))

        summary = _summary(db_session, user)

        assert _block(summary, "USD").market_value == Decimal(1100)
        assert _block(summary, "USD").unrealized_pnl == Decimal(100)
        assert _block(summary, "BRL").market_value is None
        assert "VAL9BR" in _block(summary, "BRL").market_data_unavailable_reason
        assert "1100" not in _block(summary, "BRL").model_dump_json()

    def test_mesmo_ativo_em_duas_contas_e_valorado_em_cada_posicao(self, db_session):
        user, account = _setup(db_session, "10")
        outra = make_account(
            db_session, user, make_institution(db_session, name="Inst Val 10b"), name="Outra Val 10"
        )
        asset = make_asset(db_session, ticker="VAL10")
        _tx(db_session, account, asset, BUY, 10, 10)
        _tx(db_session, outra, asset, BUY, 5, 20)
        _price(db_session, asset, "30", date(2026, 6, 20))

        summary = _summary(db_session, user)

        assert sorted(p.market_value for p in summary.positions) == [Decimal(150), Decimal(300)]
        assert _block(summary).market_value == Decimal(450)
        assert _block(summary).unrealized_pnl == Decimal(250)


class TestRentabilidadeComCotacao:
    def test_posicao_aberta_com_cotacao_ganha_xirr_e_cagr(self, db_session):
        user, account = _setup(db_session, "11")
        asset = make_asset(db_session, ticker="VAL11")
        _tx(db_session, account, asset, BUY, 100, 10, day=date(2025, 6, 30))
        _price(db_session, asset, "11", date(2026, 6, 30))  # +10% em exatamente 1 ano

        summary = _summary(db_session, user)

        position = summary.positions[0]
        assert position.is_closed is False
        assert abs(position.xirr - Decimal("0.10")) < Decimal("0.0001")
        assert abs(position.cagr - Decimal("0.10")) < Decimal("0.0001")
        assert position.profitability_unavailable_reason is None
        assert abs(_block(summary).xirr - Decimal("0.10")) < Decimal("0.0001")

    def test_posicao_aberta_sem_cotacao_continua_sem_xirr(self, db_session):
        user, account = _setup(db_session, "12")
        asset = make_asset(db_session, ticker="VAL12")
        _tx(db_session, account, asset, BUY, 100, 10)

        summary = _summary(db_session, user)

        assert summary.positions[0].xirr is None
        assert "sem cotação" in summary.positions[0].profitability_unavailable_reason
        assert _block(summary).xirr is None

    def test_cotacao_anterior_a_ultima_movimentacao_valora_mas_nao_gera_xirr(self, db_session):
        """A cotação de março precifica a posição atual (com a data
        visível), mas não pode ser o "fluxo final" de um histórico que
        tem uma compra em maio.
        """
        user, account = _setup(db_session, "13")
        asset = make_asset(db_session, ticker="VAL13")
        _tx(db_session, account, asset, BUY, 10, 10, day=date(2026, 1, 2))
        _tx(db_session, account, asset, BUY, 10, 12, day=date(2026, 5, 2))
        _price(db_session, asset, "11", date(2026, 3, 1))

        summary = _summary(db_session, user)

        position = summary.positions[0]
        assert position.market_value == Decimal(220)
        assert position.xirr is None
        assert "anterior à última movimentação" in position.profitability_unavailable_reason
        assert _block(summary).xirr is None

    def test_escopo_com_fechada_e_aberta_valorada_combina_os_fluxos(self, db_session):
        user, account = _setup(db_session, "14")
        fechada = make_asset(db_session, ticker="VAL14F")
        aberta = make_asset(db_session, ticker="VAL14A")
        _tx(db_session, account, fechada, BUY, 10, 10, day=date(2025, 6, 30))
        _tx(db_session, account, fechada, SELL, 10, 11, day=date(2026, 6, 30))
        _tx(db_session, account, aberta, BUY, 10, 10, day=date(2025, 6, 30))
        _price(db_session, aberta, "11", date(2026, 6, 30))

        block = _block(_summary(db_session, user))

        assert block.is_closed is False  # `is_closed` continua sendo só quantidade
        assert abs(block.xirr - Decimal("0.10")) < Decimal("0.0001")
