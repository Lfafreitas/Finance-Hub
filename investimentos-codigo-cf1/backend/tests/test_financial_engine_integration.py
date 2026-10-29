from datetime import date
from decimal import Decimal

from app.domain.financial_engine.position import PositionCalculator
from app.models import Transaction
from app.models.enums import TransactionSource, TransactionStatus, TransactionType
from app.repositories.transactions import get_active_transactions
from tests.test_persistence import make_account, make_asset, make_institution, make_user


class TestRevertidaNaoVazaParaOFinancialEngine:
    def test_transacao_reversed_e_excluida_pelo_repositorio_antes_do_engine(self, db_session):
        """Prova de ponta a ponta (banco real -> repositório -> engine):
        uma SELL marcada REVERSED não pode influenciar o cálculo de
        posição, porque o repositório nem a converte para TransactionFact.
        """
        user = make_user(db_session, email="reversed-e2e@example.com")
        institution = make_institution(db_session, name="Inst Reversed E2E")
        account = make_account(db_session, user, institution, name="Conta Reversed E2E")
        asset = make_asset(db_session, ticker="TEST3")

        db_session.add(
            Transaction(
                account_id=account.id,
                asset_id=asset.id,
                transaction_type=TransactionType.BUY,
                quantity=Decimal(100),
                unit_price=Decimal(10),
                fees=Decimal(0),
                gross_amount=Decimal(1000),
                currency_code="BRL",
                transaction_date=date(2026, 1, 1),
                source=TransactionSource.MANUAL,
            )
        )
        db_session.flush()

        # Uma venda lançada errada, depois estornada.
        venda_errada = Transaction(
            account_id=account.id,
            asset_id=asset.id,
            transaction_type=TransactionType.SELL,
            quantity=Decimal(100),
            unit_price=Decimal(999),  # preço absurdo, lançamento errado
            fees=Decimal(0),
            gross_amount=Decimal(0),
            currency_code="BRL",
            transaction_date=date(2026, 1, 2),
            source=TransactionSource.MANUAL,
        )
        db_session.add(venda_errada)
        db_session.flush()
        venda_errada.status = TransactionStatus.REVERSED
        db_session.flush()

        facts = get_active_transactions(db_session, account.id, asset.id)
        result = PositionCalculator.calculate(facts)

        # Se a REVERSED tivesse sido considerada, a posição estaria
        # zerada (venda de 100 de uma posição de 100). Como foi
        # excluída, a posição original de 100 continua intacta.
        assert result.quantity == Decimal(100)
        assert result.realized_gain == Decimal(0)


class TestSemDuplaContagemEmTransferencias:
    def test_transferencia_e_neutra_no_agregado_mas_visivel_por_conta(self, db_session):
        """Regra 3 da Fase 5: a soma dos fluxos de TRANSFER_OUT/IN das
        DUAS contas envolvidas deve ser zero (nenhum valor criado nem
        perdido), mas cada conta individualmente enxerga seu próprio
        lado do evento.
        """
        user = make_user(db_session, email="transfer-agregado@example.com")
        institution = make_institution(db_session, name="Inst Transfer Agregado")
        conta_origem = make_account(db_session, user, institution, name="Origem Agregado")
        conta_destino = make_account(db_session, user, institution, name="Destino Agregado")

        saida = Transaction(
            account_id=conta_origem.id,
            asset_id=None,
            transaction_type=TransactionType.TRANSFER_OUT,
            fees=Decimal(0),
            gross_amount=Decimal("5000.00"),
            currency_code="BRL",
            transaction_date=date(2026, 2, 1),
            source=TransactionSource.MANUAL,
        )
        db_session.add(saida)
        db_session.flush()

        entrada = Transaction(
            account_id=conta_destino.id,
            asset_id=None,
            transaction_type=TransactionType.TRANSFER_IN,
            fees=Decimal(0),
            gross_amount=Decimal("5000.00"),
            currency_code="BRL",
            transaction_date=date(2026, 2, 1),
            source=TransactionSource.MANUAL,
            linked_transaction_id=saida.id,
        )
        db_session.add(entrada)
        db_session.flush()
        saida.linked_transaction_id = entrada.id
        db_session.flush()

        facts_origem = get_active_transactions(db_session, conta_origem.id)
        facts_destino = get_active_transactions(db_session, conta_destino.id)

        # Convenção de sinal de fluxo de caixa por conta: OUT é saída
        # (negativo), IN é entrada (positivo) — replicando aqui só para
        # provar a propriedade aritmética, sem introduzir um novo
        # agregador no Financial Engine (fora do escopo aprovado).
        fluxo_origem = sum(
            (
                -f.gross_amount
                if f.transaction_type == TransactionType.TRANSFER_OUT
                else f.gross_amount
            )
            for f in facts_origem
        )
        fluxo_destino = sum(
            (
                -f.gross_amount
                if f.transaction_type == TransactionType.TRANSFER_OUT
                else f.gross_amount
            )
            for f in facts_destino
        )

        assert fluxo_origem == Decimal("-5000.00")
        assert fluxo_destino == Decimal("5000.00")
        # Consolidado (as duas contas juntas): net zero — não é aporte
        # nem retirada externa, é movimentação interna.
        assert fluxo_origem + fluxo_destino == Decimal(0)
