import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Account, Asset, Institution, Transaction, User
from app.models.enums import InstitutionType, TransactionSource, TransactionType


def make_user(session, email="dono@example.com") -> User:
    user = User(email=email, password_hash="hash", full_name="Usuário Teste")
    session.add(user)
    session.flush()
    return user


def make_institution(session, name="XP Investimentos") -> Institution:
    institution = Institution(name=name, institution_type=InstitutionType.BROKER, country="BR")
    session.add(institution)
    session.flush()
    return institution


def make_account(session, user, institution, name="XP - Ações") -> Account:
    account = Account(
        user_id=user.id, institution_id=institution.id, name=name, currency_code="BRL"
    )
    session.add(account)
    session.flush()
    return account


def make_asset(
    session, ticker="PETR4", asset_class_code="STOCK_BR", country="BR", currency_code="BRL"
) -> Asset:
    asset = Asset(
        ticker=ticker,
        name=f"Ativo {ticker}",
        asset_class_code=asset_class_code,
        country=country,
        currency_code=currency_code,
    )
    session.add(asset)
    session.flush()
    return asset


class TestFundacaoRelacionamentos:
    def test_cria_grafo_completo_user_institution_account_asset_transaction(self, db_session):
        user = make_user(db_session)
        institution = make_institution(db_session)
        account = make_account(db_session, user, institution)
        asset = make_asset(db_session)

        transaction = Transaction(
            account_id=account.id,
            asset_id=asset.id,
            transaction_type=TransactionType.BUY,
            quantity=Decimal("100.00000000"),
            unit_price=Decimal("32.50000000"),
            fees=Decimal("4.90"),
            gross_amount=Decimal("3250.00"),
            currency_code="BRL",
            transaction_date=date(2026, 1, 15),
            source=TransactionSource.MANUAL,
        )
        db_session.add(transaction)
        db_session.flush()

        persisted = db_session.get(Transaction, transaction.id)
        assert persisted is not None
        assert persisted.account_id == account.id
        assert persisted.asset_id == asset.id

    def test_transaction_de_aporte_sem_asset_e_valida(self, db_session):
        """Aporte/retirada de dinheiro puro não referencia nenhum ativo
        — confirma que Transaction não depende de Position/Asset para
        representar um evento financeiro válido.
        """
        user = make_user(db_session, email="outro@example.com")
        institution = make_institution(db_session, name="Nubank")
        account = make_account(db_session, user, institution, name="Nubank - Conta corrente")

        deposito = Transaction(
            account_id=account.id,
            asset_id=None,
            transaction_type=TransactionType.DEPOSIT,
            quantity=None,
            unit_price=None,
            fees=Decimal(0),
            gross_amount=Decimal("1000.00"),
            currency_code="BRL",
            transaction_date=date(2026, 2, 1),
            source=TransactionSource.MANUAL,
        )
        db_session.add(deposito)
        db_session.flush()

        assert deposito.id is not None
        assert deposito.asset_id is None


class TestIntegridadeReferencial:
    def test_account_exige_user_existente(self, db_session):
        institution = make_institution(db_session)
        account = Account(
            user_id=uuid.uuid4(),  # usuário inexistente
            institution_id=institution.id,
            name="Conta órfã",
            currency_code="BRL",
        )
        db_session.add(account)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_transaction_exige_currency_valida(self, db_session):
        user = make_user(db_session, email="moeda@example.com")
        institution = make_institution(db_session, name="Inter")
        account = make_account(db_session, user, institution, name="Inter - Conta")

        transacao = Transaction(
            account_id=account.id,
            asset_id=None,
            transaction_type=TransactionType.DEPOSIT,
            fees=Decimal(0),
            gross_amount=Decimal("100.00"),
            currency_code="XYZ",  # moeda não cadastrada
            transaction_date=date(2026, 1, 1),
            source=TransactionSource.MANUAL,
        )
        db_session.add(transacao)
        with pytest.raises(IntegrityError):
            db_session.flush()


class TestUniqueConstraints:
    def test_email_duplicado_e_rejeitado(self, db_session):
        make_user(db_session, email="duplicado@example.com")
        db_session.flush()
        with pytest.raises(IntegrityError):
            make_user(db_session, email="duplicado@example.com")

    def test_asset_ticker_pais_duplicado_e_rejeitado(self, db_session):
        make_asset(db_session, ticker="VALE3")
        db_session.flush()
        with pytest.raises(IntegrityError):
            make_asset(db_session, ticker="VALE3")

    def test_external_reference_duplicado_na_mesma_conta_e_rejeitado(self, db_session):
        """Índice único parcial: previne a mesma transação (mesma
        referência externa) ser importada duas vezes na mesma conta —
        a base da futura detecção de duplicidade/reconciliação.
        """
        user = make_user(db_session, email="dedup@example.com")
        institution = make_institution(db_session, name="Pluggy-Banco")
        account = make_account(db_session, user, institution, name="Conta Dedup")

        base_kwargs = {
            "account_id": account.id,
            "asset_id": None,
            "transaction_type": TransactionType.DEPOSIT,
            "fees": Decimal(0),
            "gross_amount": Decimal("500.00"),
            "currency_code": "BRL",
            "transaction_date": date(2026, 3, 1),
            "source": TransactionSource.API_PLUGGY,
            "external_reference": "pluggy-txn-123",
        }
        db_session.add(Transaction(**base_kwargs))
        db_session.flush()

        with pytest.raises(IntegrityError):
            db_session.add(Transaction(**base_kwargs))
            db_session.flush()

    def test_external_reference_nulo_permite_multiplas_transacoes(self, db_session):
        """O índice único é PARCIAL — não deve afetar transações
        manuais, que nunca têm external_reference.
        """
        user = make_user(db_session, email="manual@example.com")
        institution = make_institution(db_session, name="Corretora Manual")
        account = make_account(db_session, user, institution, name="Conta Manual")

        for _ in range(2):
            db_session.add(
                Transaction(
                    account_id=account.id,
                    asset_id=None,
                    transaction_type=TransactionType.DEPOSIT,
                    fees=Decimal(0),
                    gross_amount=Decimal("10.00"),
                    currency_code="BRL",
                    transaction_date=date(2026, 3, 2),
                    source=TransactionSource.MANUAL,
                    external_reference=None,
                )
            )
        db_session.flush()  # não deve levantar IntegrityError


class TestPrecisaoNumerica:
    def test_quantidade_fracionaria_preserva_precisao_exata(self, db_session):
        """Fundamental para ativos fracionários (ex.: fractional shares
        no exterior): Decimal não pode perder precisão como float faria.
        """
        user = make_user(db_session, email="fracao@example.com")
        institution = make_institution(db_session, name="Avenue")
        account = make_account(db_session, user, institution, name="Avenue - Global")
        asset = make_asset(
            db_session,
            ticker="AAPL",
            asset_class_code="STOCK_US",
            country="US",
            currency_code="USD",
        )

        quantidade_exata = Decimal("0.12345678")
        transacao = Transaction(
            account_id=account.id,
            asset_id=asset.id,
            transaction_type=TransactionType.BUY,
            quantity=quantidade_exata,
            unit_price=Decimal("189.99000000"),
            fees=Decimal(0),
            gross_amount=Decimal("23.45"),
            currency_code="USD",
            transaction_date=date(2026, 1, 10),
            source=TransactionSource.MANUAL,
        )
        db_session.add(transacao)
        db_session.flush()
        db_session.refresh(transacao)

        assert transacao.quantity == quantidade_exata
