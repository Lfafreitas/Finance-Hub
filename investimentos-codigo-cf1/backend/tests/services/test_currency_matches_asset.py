"""Moeda-3: `Transaction.currency_code == Asset.currency_code` em toda
transação ligada a um ativo — criação manual, correção e importação.
Sem conversão e sem inferência: divergência é rejeição.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import TransactionSource, TransactionStatus, TransactionType
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate, TransferCreate
from app.services import transaction_service
from app.services.exceptions import CurrencyMismatchError
from tests.test_persistence import make_account, make_asset, make_institution, make_user

DAY = date(2026, 5, 4)


def _setup(db, tag):
    user = make_user(db, email=f"moeda3-{tag}@example.com")
    account = make_account(db, user, make_institution(db, name=f"Inst Moeda3 {tag}"))
    brl = make_asset(db, ticker=f"M3BR{tag}")
    usd = make_asset(db, ticker=f"M3US{tag}", country="US", currency_code="USD")
    return user, account, brl, usd


def _payload(account, asset, currency, kind="BUY", **overrides):
    data = {
        "account_id": account.id,
        "asset_id": asset.id if asset is not None else None,
        "transaction_type": kind,
        "quantity": Decimal(10),
        "unit_price": Decimal(5),
        "gross_amount": Decimal(50),
        "currency_code": currency,
        "transaction_date": DAY,
    }
    data.update(overrides)
    return TransactionCreate(**data)


def _count(db, account):
    return db.query(Transaction).filter_by(account_id=account.id).count()


class TestCriacaoManual:
    def test_brl_em_ativo_usd_e_rejeitado_e_nada_e_gravado(self, db_session):
        user, account, _brl, usd = _setup(db_session, "1")

        with pytest.raises(CurrencyMismatchError) as exc_info:
            transaction_service.create_transaction(
                db_session, user.id, _payload(account, usd, "BRL")
            )

        assert "BRL" in str(exc_info.value)
        assert "USD" in str(exc_info.value)
        assert usd.ticker in str(exc_info.value)
        assert _count(db_session, account) == 0

    def test_usd_em_ativo_brl_e_rejeitado(self, db_session):
        user, account, brl, _usd = _setup(db_session, "2")

        with pytest.raises(CurrencyMismatchError):
            transaction_service.create_transaction(
                db_session, user.id, _payload(account, brl, "USD")
            )

        assert _count(db_session, account) == 0

    @pytest.mark.parametrize("currency", ["BRL", "USD"])
    def test_mesma_moeda_do_ativo_e_aceita(self, db_session, currency):
        user, account, brl, usd = _setup(db_session, f"3{currency}")
        asset = brl if currency == "BRL" else usd

        created = transaction_service.create_transaction(
            db_session, user.id, _payload(account, asset, currency)
        )

        assert created.currency_code == currency

    @pytest.mark.parametrize(
        ("kind", "overrides"),
        [
            ("DIVIDEND", {"quantity": None, "unit_price": None}),
            ("JCP", {"quantity": None, "unit_price": None}),
            ("INCOME", {"quantity": None, "unit_price": None}),
            ("FEE", {"quantity": None, "unit_price": None}),
            ("BONUS_SHARES", {"unit_price": None, "gross_amount": Decimal(0)}),
            ("STOCK_SPLIT", {"unit_price": None, "gross_amount": Decimal(0)}),
        ],
    )
    def test_todo_tipo_ligado_a_ativo_e_validado(self, db_session, kind, overrides):
        user, account, _brl, usd = _setup(db_session, f"4{kind[:3]}")

        with pytest.raises(CurrencyMismatchError):
            transaction_service.create_transaction(
                db_session, user.id, _payload(account, usd, "BRL", kind=kind, **overrides)
            )

        assert _count(db_session, account) == 0

    @pytest.mark.parametrize("currency", ["BRL", "USD"])
    def test_movimento_sem_ativo_fica_livre_em_qualquer_moeda(self, db_session, currency):
        """Decisão 4: DEPOSIT/WITHDRAWAL preservam a moeda informada no
        próprio movimento, mesmo diferente da moeda da conta (BRL).
        """
        user, account, _brl, _usd = _setup(db_session, f"5{currency}")

        created = transaction_service.create_transaction(
            db_session,
            user.id,
            _payload(account, None, currency, kind="DEPOSIT", quantity=None, unit_price=None),
        )

        assert created.currency_code == currency


class TestCorrecao:
    def test_correcao_para_moeda_errada_e_rejeitada_e_original_segue_ativa(self, db_session):
        user, account, _brl, usd = _setup(db_session, "6")
        original = transaction_service.create_transaction(
            db_session, user.id, _payload(account, usd, "USD")
        )

        with pytest.raises(CurrencyMismatchError):
            transaction_service.correct_transaction(
                db_session, user.id, original.id, _payload(account, usd, "BRL")
            )

        db_session.expire_all()
        assert original.status == TransactionStatus.ACTIVE
        assert _count(db_session, account) == 1

    def test_correcao_de_dado_legado_exige_a_moeda_do_ativo(self, db_session):
        """Uma Transaction antiga gravada na moeda errada continua
        existindo; corrigi-la só é aceito na moeda do ativo.
        """
        user, account, _brl, usd = _setup(db_session, "7")
        legado = Transaction(
            account_id=account.id,
            asset_id=usd.id,
            transaction_type=TransactionType.BUY,
            quantity=Decimal(10),
            unit_price=Decimal(5),
            fees=Decimal(0),
            gross_amount=Decimal(50),
            currency_code="BRL",
            transaction_date=DAY,
            source=TransactionSource.IMPORT_CSV,
            status=TransactionStatus.ACTIVE,
        )
        db_session.add(legado)
        db_session.flush()

        with pytest.raises(CurrencyMismatchError):
            transaction_service.correct_transaction(
                db_session, user.id, legado.id, _payload(account, usd, "BRL")
            )
        corrected = transaction_service.correct_transaction(
            db_session, user.id, legado.id, _payload(account, usd, "USD")
        )

        db_session.expire_all()
        assert legado.status == TransactionStatus.REVERSED
        assert corrected.currency_code == "USD"


class TestImportacaoETransferencia:
    def _import(self, db, user, account, asset, currency):
        return transaction_service.create_imported_transaction(
            db,
            user.id,
            account_id=account.id,
            asset_id=asset.id,
            transaction_type=TransactionType.BUY,
            quantity=Decimal(10),
            unit_price=Decimal(5),
            fees=Decimal(0),
            gross_amount=Decimal(50),
            currency_code=currency,
            transaction_date=DAY,
            source=TransactionSource.IMPORT_CSV,
            external_reference=f"m3-{currency}:0",
        )

    def test_importacao_passa_pela_mesma_validacao(self, db_session):
        user, account, _brl, usd = _setup(db_session, "8")

        with pytest.raises(CurrencyMismatchError):
            self._import(db_session, user, account, usd, "BRL")

        assert _count(db_session, account) == 0
        assert self._import(db_session, user, account, usd, "USD").currency_code == "USD"

    def test_transferencia_nao_e_afetada(self, db_session):
        user = make_user(db_session, email="moeda3-transfer@example.com")
        institution = make_institution(db_session, name="Inst Moeda3 Transfer")
        origem = make_account(db_session, user, institution, name="Origem M3")
        destino = make_account(db_session, user, institution, name="Destino M3")

        out, incoming = transaction_service.create_transfer(
            db_session,
            user.id,
            TransferCreate(
                from_account_id=origem.id,
                to_account_id=destino.id,
                gross_amount=Decimal(100),
                transaction_date=DAY,
            ),
        )

        assert (out.currency_code, incoming.currency_code) == ("BRL", "BRL")
