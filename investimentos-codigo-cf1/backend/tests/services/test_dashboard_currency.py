"""Moeda-1: o dashboard nunca soma moedas diferentes.

Todo valor monetário vive em `totals_by_currency` (um bloco por
moeda). A moeda de uma posição é a das suas Transactions ativas; uma
posição com mais de uma moeda é marcada como inconsistente, não tem
valor monetário e fica fora de todos os blocos. `fx_rate_to_brl` nunca
é usado para consolidar.
"""

from datetime import date
from decimal import Decimal

from app.models.enums import TransactionSource, TransactionStatus, TransactionType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction
from app.schemas.dashboard import DashboardSummary
from app.services import dashboard_service
from tests.test_persistence import make_account, make_asset, make_institution, make_user

OLD_TOP_LEVEL_FIELDS = {
    "total_cost_basis",
    "total_realized_gain",
    "total_dividends_received",
    "net_contributions",
    "total_realized_cost_basis",
    "realized_return_pct",
    "is_closed",
    "xirr",
    "cagr",
    "profitability_unavailable_reason",
    "market_value",
    "unrealized_pnl",
    "current_return",
    "allocation",
    "contribution_evolution",
    "market_data_unavailable_reason",
}


def _setup(db, tag):
    user = make_user(db, email=f"moeda-{tag}@example.com")
    account = make_account(db, user, make_institution(db, name=f"Inst Moeda {tag}"))
    return user, account


def _tx(
    db,
    account,
    kind,
    currency,
    *,
    asset=None,
    qty=None,
    price=None,
    gross=None,
    day=1,
    month=1,
    fx=None,
):
    quantity = Decimal(qty) if qty is not None else None
    unit_price = Decimal(price) if price is not None else None
    if gross is None:
        gross = quantity * unit_price if quantity is not None and unit_price is not None else 0
    tx = Transaction(
        account_id=account.id,
        asset_id=asset.id if asset is not None else None,
        transaction_type=kind,
        quantity=quantity,
        unit_price=unit_price,
        fees=Decimal(0),
        gross_amount=Decimal(gross),
        currency_code=currency,
        fx_rate_to_brl=Decimal(fx) if fx is not None else None,
        transaction_date=date(2026, month, day),
        source=TransactionSource.MANUAL,
        status=TransactionStatus.ACTIVE,
    )
    db.add(tx)
    db.flush()
    return tx


BUY, SELL, DEPOSIT, WITHDRAWAL = (
    TransactionType.BUY,
    TransactionType.SELL,
    TransactionType.DEPOSIT,
    TransactionType.WITHDRAWAL,
)


def _blocks(summary):
    return {block.currency_code: block for block in summary.totals_by_currency}


class TestMoedasNuncaSaoSomadas:
    def test_brl_e_usd_ficam_em_blocos_separados(self, db_session):
        """O caso que motivou a correção: R$ 1.000 + US$ 1.000 apareciam
        como custo total 2.000 e alocação 50/50.
        """
        user, account = _setup(db_session, "1")
        br = make_asset(db_session, ticker="MOEBR1")
        us = make_asset(db_session, ticker="MOEUS1", country="US", currency_code="USD")
        _tx(db_session, account, BUY, "BRL", asset=br, qty=10, price=100)
        _tx(db_session, account, BUY, "USD", asset=us, qty=10, price=100, fx="5.20")

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)

        assert [b.currency_code for b in summary.totals_by_currency] == ["BRL", "USD"]
        blocks = _blocks(summary)
        assert blocks["BRL"].total_cost_basis == Decimal(1000)
        assert blocks["USD"].total_cost_basis == Decimal(1000)
        # Nenhum valor do resumo é a soma (2000) nem a conversão (6200).
        dumped = summary.model_dump_json()
        assert "2000" not in dumped
        assert "6200" not in dumped
        assert "5200" not in dumped

    def test_alocacao_soma_100_dentro_de_cada_moeda(self, db_session):
        user, account = _setup(db_session, "2")
        br1 = make_asset(db_session, ticker="MOEBR2A")
        br2 = make_asset(db_session, ticker="MOEBR2B")
        us = make_asset(db_session, ticker="MOEUS2", country="US", currency_code="USD")
        _tx(db_session, account, BUY, "BRL", asset=br1, qty=10, price=10)  # 100 -> 25%
        _tx(db_session, account, BUY, "BRL", asset=br2, qty=10, price=30)  # 300 -> 75%
        _tx(db_session, account, BUY, "USD", asset=us, qty=10, price=500)  # 5000 -> 100% do USD

        blocks = _blocks(dashboard_service.get_dashboard_summary(db_session, user.id))

        brl = {a.asset_ticker: a.percentage for a in blocks["BRL"].allocation}
        usd = {a.asset_ticker: a.percentage for a in blocks["USD"].allocation}
        assert brl == {"MOEBR2A": Decimal(25), "MOEBR2B": Decimal(75)}
        assert usd == {"MOEUS2": Decimal(100)}
        assert sum(brl.values()) == Decimal(100)

    def test_resultado_realizado_e_proventos_por_moeda(self, db_session):
        user, account = _setup(db_session, "3")
        br = make_asset(db_session, ticker="MOEBR3")
        us = make_asset(db_session, ticker="MOEUS3", country="US", currency_code="USD")
        _tx(db_session, account, BUY, "BRL", asset=br, qty=10, price=10, day=1)
        _tx(db_session, account, SELL, "BRL", asset=br, qty=5, price=14, day=2)  # +20
        _tx(db_session, account, TransactionType.DIVIDEND, "BRL", asset=br, gross=7, day=3)
        _tx(db_session, account, BUY, "USD", asset=us, qty=10, price=10, day=1)
        _tx(db_session, account, SELL, "USD", asset=us, qty=5, price=8, day=2)  # -10
        _tx(db_session, account, TransactionType.DIVIDEND, "USD", asset=us, gross=3, day=3)

        blocks = _blocks(dashboard_service.get_dashboard_summary(db_session, user.id))

        assert blocks["BRL"].total_realized_gain == Decimal(20)
        assert blocks["BRL"].total_dividends_received == Decimal(7)
        assert blocks["BRL"].total_realized_cost_basis == Decimal(50)
        assert blocks["BRL"].total_cost_basis == Decimal(50)
        assert blocks["USD"].total_realized_gain == Decimal(-10)
        assert blocks["USD"].total_dividends_received == Decimal(3)

    def test_fx_rate_to_brl_nao_altera_nada(self, db_session):
        user, account = _setup(db_session, "4")
        us = make_asset(db_session, ticker="MOEUS4", country="US", currency_code="USD")
        _tx(db_session, account, BUY, "USD", asset=us, qty=10, price=100, fx="5.20")
        _tx(db_session, account, DEPOSIT, "USD", gross=1000, fx="5.20")

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)

        assert [b.currency_code for b in summary.totals_by_currency] == ["USD"]
        usd = summary.totals_by_currency[0]
        assert usd.total_cost_basis == Decimal(1000)
        assert usd.net_contributions == Decimal(1000)

    def test_moeda_da_posicao_vem_das_transacoes_nao_do_cadastro_do_ativo(self, db_session):
        """Ativo cadastrado em BRL, transações lançadas em USD: os
        valores são USD e vão para o bloco USD.
        """
        user, account = _setup(db_session, "5")
        asset = make_asset(db_session, ticker="MOECAD5")  # cadastro: BRL
        _tx(db_session, account, BUY, "USD", asset=asset, qty=10, price=100)

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)

        assert [b.currency_code for b in summary.totals_by_currency] == ["USD"]
        assert summary.positions[0].currency_code == "USD"


class TestAportesPorMoeda:
    def test_depositos_e_retiradas_em_moedas_diferentes(self, db_session):
        user, account = _setup(db_session, "6")
        _tx(db_session, account, DEPOSIT, "BRL", gross=1000, day=1)
        _tx(db_session, account, DEPOSIT, "USD", gross=200, day=2)
        _tx(db_session, account, WITHDRAWAL, "BRL", gross=300, day=3)
        _tx(db_session, account, DEPOSIT, "USD", gross=50, day=4)

        blocks = _blocks(dashboard_service.get_dashboard_summary(db_session, user.id))

        assert blocks["BRL"].net_contributions == Decimal(700)
        assert blocks["USD"].net_contributions == Decimal(250)
        assert [p.cumulative_net_contribution for p in blocks["BRL"].contribution_evolution] == [
            Decimal(1000),
            Decimal(700),
        ]
        assert [
            (p.date.day, p.cumulative_net_contribution)
            for p in blocks["USD"].contribution_evolution
        ] == [
            (2, Decimal(200)),
            (4, Decimal(250)),
        ]

    def test_moeda_so_com_caixa_gera_bloco_sem_alocacao(self, db_session):
        user, account = _setup(db_session, "7")
        _tx(db_session, account, DEPOSIT, "USD", gross=500)

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)

        assert [b.currency_code for b in summary.totals_by_currency] == ["USD"]
        usd = summary.totals_by_currency[0]
        assert usd.net_contributions == Decimal(500)
        assert usd.total_cost_basis == Decimal(0)
        assert usd.allocation == []
        assert summary.positions == []

    def test_transferencia_interna_continua_neutra_e_externa_conta_na_moeda_dela(self, db_session):
        user = make_user(db_session, email="moeda-8@example.com")
        institution = make_institution(db_session, name="Inst Moeda 8")
        portfolio = Portfolio(user_id=user.id, name="Carteira Moeda 8")
        db_session.add(portfolio)
        db_session.flush()
        origem = make_account(db_session, user, institution, name="Origem Moeda 8")
        origem.portfolio_id = portfolio.id
        destino = make_account(db_session, user, institution, name="Destino Moeda 8")
        db_session.flush()
        _tx(db_session, origem, DEPOSIT, "BRL", gross=1000, day=1)
        _tx(db_session, origem, DEPOSIT, "USD", gross=400, day=1)
        saida = _tx(db_session, origem, TransactionType.TRANSFER_OUT, "BRL", gross=300, day=2)
        entrada = _tx(db_session, destino, TransactionType.TRANSFER_IN, "BRL", gross=300, day=2)
        saida.linked_transaction_id = entrada.id
        entrada.linked_transaction_id = saida.id
        db_session.flush()

        consolidado = _blocks(dashboard_service.get_dashboard_summary(db_session, user.id))
        so_origem = _blocks(
            dashboard_service.get_dashboard_summary(db_session, user.id, portfolio.id)
        )

        assert consolidado["BRL"].net_contributions == Decimal(1000)  # neutra
        assert so_origem["BRL"].net_contributions == Decimal(700)  # saiu do escopo
        assert consolidado["USD"].net_contributions == Decimal(400)
        assert so_origem["USD"].net_contributions == Decimal(400)  # intocado pela transferência BRL


class TestRentabilidadePorMoeda:
    def test_xirr_calculado_por_moeda(self, db_session):
        """Posição FECHADA em BRL + posição ABERTA em USD: antes, o
        escopo inteiro era "aberto" e ninguém tinha XIRR. Agora o
        bloco BRL é fechado e tem XIRR; o USD continua aberto.
        """
        user, account = _setup(db_session, "9")
        br = make_asset(db_session, ticker="MOEBR9")
        us = make_asset(db_session, ticker="MOEUS9", country="US", currency_code="USD")
        _tx(db_session, account, BUY, "BRL", asset=br, qty=100, price=10, day=1)
        _tx(db_session, account, SELL, "BRL", asset=br, qty=100, price=12, day=1, month=6)
        _tx(db_session, account, BUY, "USD", asset=us, qty=10, price=100, day=1)

        blocks = _blocks(dashboard_service.get_dashboard_summary(db_session, user.id))

        assert blocks["BRL"].is_closed is True
        assert blocks["BRL"].xirr is not None
        assert blocks["BRL"].realized_return_pct == Decimal("0.2")
        assert blocks["USD"].is_closed is False
        assert blocks["USD"].xirr is None
        assert "posição aberta" in blocks["USD"].profitability_unavailable_reason

    def test_duas_moedas_fechadas_tem_xirr_cada_uma(self, db_session):
        """Antes: "ativos em moedas diferentes no escopo" bloqueava o
        XIRR de tudo. Separado por moeda, cada bloco calcula o seu.
        """
        user, account = _setup(db_session, "10")
        br = make_asset(db_session, ticker="MOEBR10")
        us = make_asset(db_session, ticker="MOEUS10", country="US", currency_code="USD")
        _tx(db_session, account, BUY, "BRL", asset=br, qty=10, price=10, day=1)
        _tx(db_session, account, SELL, "BRL", asset=br, qty=10, price=12, day=20)
        _tx(db_session, account, BUY, "USD", asset=us, qty=10, price=10, day=1)
        _tx(db_session, account, SELL, "USD", asset=us, qty=10, price=9, day=20)

        blocks = _blocks(dashboard_service.get_dashboard_summary(db_session, user.id))

        assert blocks["BRL"].xirr is not None and blocks["BRL"].xirr > 0
        assert blocks["USD"].xirr is not None and blocks["USD"].xirr < 0
        assert blocks["BRL"].profitability_unavailable_reason is None
        assert blocks["USD"].profitability_unavailable_reason is None


class TestPosicaoComMoedasMisturadas:
    def _mixed(self, db_session, tag, second_kind=BUY, **second):
        user, account = _setup(db_session, tag)
        asset = make_asset(db_session, ticker=f"MOEMIX{tag}")
        _tx(db_session, account, BUY, "BRL", asset=asset, qty=10, price=10, day=1)
        _tx(db_session, account, second_kind, "USD", asset=asset, day=2, **second)
        return user, account, asset

    def test_posicao_inconsistente_e_marcada_e_sem_valores_monetarios(self, db_session):
        user, _account, asset = self._mixed(db_session, "11", qty=5, price=20)

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)

        position = summary.positions[0]
        assert position.asset_id == asset.id
        assert position.currency_code is None
        assert "BRL, USD" in position.currency_inconsistency_reason
        assert position.quantity == Decimal(15)  # quantidade não tem moeda
        assert position.is_closed is False
        for field in (
            "average_cost",
            "total_cost_basis",
            "realized_gain",
            "dividends_received",
            "realized_cost_basis",
            "realized_return_pct",
            "xirr",
            "cagr",
            "market_value",
            "unrealized_pnl",
        ):
            assert getattr(position, field) is None, field
        assert position.profitability_unavailable_reason == position.currency_inconsistency_reason

    def test_posicao_inconsistente_fica_fora_de_todos_os_blocos(self, db_session):
        user, account, _asset = self._mixed(db_session, "12", qty=5, price=20)
        ok = make_asset(db_session, ticker="MOEOK12")
        _tx(db_session, account, BUY, "BRL", asset=ok, qty=10, price=30)

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)

        assert len(summary.positions) == 2
        assert [b.currency_code for b in summary.totals_by_currency] == ["BRL"]
        brl = summary.totals_by_currency[0]
        assert brl.total_cost_basis == Decimal(300)  # só o ativo consistente
        assert [a.asset_ticker for a in brl.allocation] == ["MOEOK12"]
        assert brl.allocation[0].percentage == Decimal(100)

    def test_so_posicao_inconsistente_nao_gera_bloco_nenhum(self, db_session):
        user, _account, _asset = self._mixed(db_session, "13", qty=5, price=20)

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)

        assert summary.totals_by_currency == []
        assert len(summary.positions) == 1

    def test_posicao_inconsistente_fechada_nao_entra_no_xirr_do_bloco(self, db_session):
        user, account = _setup(db_session, "14")
        mixed = make_asset(db_session, ticker="MOEMIX14")
        _tx(db_session, account, BUY, "BRL", asset=mixed, qty=10, price=10, day=1)
        _tx(db_session, account, SELL, "USD", asset=mixed, qty=10, price=50, day=20)
        ok = make_asset(db_session, ticker="MOEOK14")
        _tx(db_session, account, BUY, "BRL", asset=ok, qty=10, price=10, day=1)
        _tx(db_session, account, SELL, "BRL", asset=ok, qty=10, price=11, day=20)

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)

        brl = _blocks(summary)["BRL"]
        assert list(_blocks(summary)) == ["BRL"]
        assert brl.total_realized_gain == Decimal(10)  # só o ativo consistente
        assert brl.total_realized_cost_basis == Decimal(100)
        mixed_position = next(p for p in summary.positions if p.asset_id == mixed.id)
        assert mixed_position.is_closed is True  # quantidade zero continua verdade
        assert mixed_position.xirr is None
        assert mixed_position.realized_gain is None

    def test_evento_societario_em_outra_moeda_tambem_marca_inconsistencia(self, db_session):
        user, _account, _asset = self._mixed(
            db_session, "15", second_kind=TransactionType.BONUS_SHARES, qty=1
        )

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)

        assert summary.positions[0].currency_code is None
        assert summary.positions[0].quantity == Decimal(11)
        assert summary.totals_by_currency == []

    def test_transacao_reversed_em_outra_moeda_nao_conta(self, db_session):
        """Só Transactions ATIVAS determinam a moeda: corrigir o dado
        (revertendo o lançamento errado) devolve a posição aos totais.
        """
        user, account = _setup(db_session, "16")
        asset = make_asset(db_session, ticker="MOEREV16")
        _tx(db_session, account, BUY, "BRL", asset=asset, qty=10, price=10, day=1)
        errada = _tx(db_session, account, BUY, "USD", asset=asset, qty=5, price=20, day=2)
        errada.status = TransactionStatus.REVERSED
        db_session.flush()

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)

        assert summary.positions[0].currency_code == "BRL"
        assert summary.positions[0].currency_inconsistency_reason is None
        assert _blocks(summary)["BRL"].total_cost_basis == Decimal(100)

    def test_mesmo_ativo_em_contas_de_moedas_diferentes_nao_e_inconsistencia(self, db_session):
        """A consistência é por (conta, ativo): o mesmo ativo em BRL
        numa conta e em USD em outra são duas posições válidas.
        """
        user, account = _setup(db_session, "17")
        outra = make_account(
            db_session, user, make_institution(db_session, name="Inst Moeda 17b"), name="Outra 17"
        )
        asset = make_asset(db_session, ticker="MOEDUAL17")
        _tx(db_session, account, BUY, "BRL", asset=asset, qty=10, price=10)
        _tx(db_session, outra, BUY, "USD", asset=asset, qty=10, price=20)

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)

        assert sorted(p.currency_code for p in summary.positions) == ["BRL", "USD"]
        blocks = _blocks(summary)
        assert blocks["BRL"].total_cost_basis == Decimal(100)
        assert blocks["USD"].total_cost_basis == Decimal(200)


class TestFormaDoContrato:
    def test_uma_moeda_gera_um_unico_bloco(self, db_session):
        user, account = _setup(db_session, "18")
        asset = make_asset(db_session, ticker="MOEUNI18")
        _tx(db_session, account, DEPOSIT, "BRL", gross=1000)
        _tx(db_session, account, BUY, "BRL", asset=asset, qty=10, price=10)

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)

        assert [b.currency_code for b in summary.totals_by_currency] == ["BRL"]
        assert summary.positions[0].currency_code == "BRL"
        assert summary.positions[0].currency_inconsistency_reason is None

    def test_escopo_vazio_gera_lista_vazia(self, db_session):
        user, _account = _setup(db_session, "19")

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)

        assert summary.totals_by_currency == []
        assert summary.positions == []

    def test_blocos_em_ordem_alfabetica_de_moeda(self, db_session):
        user, account = _setup(db_session, "20")
        _tx(db_session, account, DEPOSIT, "USD", gross=1, day=1)
        _tx(db_session, account, DEPOSIT, "BRL", gross=1, day=2)

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)

        assert [b.currency_code for b in summary.totals_by_currency] == ["BRL", "USD"]

    def test_nenhum_campo_antigo_sobrevive_no_topo(self):
        assert OLD_TOP_LEVEL_FIELDS.isdisjoint(DashboardSummary.model_fields)
        assert set(DashboardSummary.model_fields) == {
            "portfolio_id",
            "positions",
            "totals_by_currency",
        }
