"""Coerência dos campos de uma Transaction com o tipo dela, checada
em todo ponto de entrada (manual, importação, correção, transferência)
ANTES de gravar — Transaction é imutável, então dado malformado que
entra não sai mais e quebra o cálculo de posição do par.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import TransactionSource, TransactionType
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate, TransferCreate
from app.services import dashboard_service, transaction_service
from app.services.exceptions import InvalidTransactionDataError
from tests.test_persistence import make_account, make_asset, make_institution, make_user

DAY = date(2026, 4, 1)


def _setup(db, tag):
    user = make_user(db, email=f"valid-{tag}@example.com")
    account = make_account(db, user, make_institution(db, name=f"Inst Valid {tag}"))
    asset = make_asset(db, ticker=f"VL{tag}")
    return user, account, asset


def _payload(account, asset, kind, **overrides):
    data = {
        "account_id": account.id,
        "asset_id": asset.id if asset is not None else None,
        "transaction_type": kind,
        "quantity": Decimal(10),
        "unit_price": Decimal(5),
        "fees": Decimal(0),
        "gross_amount": Decimal(50),
        "currency_code": "BRL",
        "transaction_date": DAY,
    }
    data.update(overrides)
    return TransactionCreate(**data)


INVALID_CASES = [
    ("buy_sem_ativo", "BUY", {"asset_id": None}),
    ("buy_sem_quantidade", "BUY", {"quantity": None}),
    ("buy_sem_preco", "BUY", {"unit_price": None}),
    ("buy_quantidade_negativa", "BUY", {"quantity": Decimal(-10)}),
    ("buy_quantidade_zero", "BUY", {"quantity": Decimal(0)}),
    ("buy_preco_negativo", "BUY", {"unit_price": Decimal(-5)}),
    ("buy_taxa_negativa", "BUY", {"fees": Decimal(-1)}),
    ("buy_valor_negativo", "BUY", {"gross_amount": Decimal(-50)}),
    ("sell_quantidade_negativa", "SELL", {"quantity": Decimal(-10)}),
    ("sell_sem_ativo", "SELL", {"asset_id": None}),
    ("bonificacao_sem_quantidade", "BONUS_SHARES", {"quantity": None, "unit_price": None}),
    ("bonificacao_negativa", "BONUS_SHARES", {"quantity": Decimal(-1), "unit_price": None}),
    ("desdobramento_zero", "STOCK_SPLIT", {"quantity": Decimal(0), "unit_price": None}),
    ("grupamento_positivo", "REVERSE_SPLIT", {"quantity": Decimal(5), "unit_price": None}),
    ("grupamento_sem_quantidade", "REVERSE_SPLIT", {"quantity": None, "unit_price": None}),
    ("deposito_com_ativo", "DEPOSIT", {"quantity": None, "unit_price": None}),
    ("retirada_com_ativo", "WITHDRAWAL", {"quantity": None, "unit_price": None}),
    ("cambio_com_ativo", "FX_CONVERSION", {"quantity": None, "unit_price": None}),
    ("dividendo_valor_negativo", "DIVIDEND", {"gross_amount": Decimal(-1), "quantity": None}),
    ("dividendo_quantidade_negativa", "DIVIDEND", {"quantity": Decimal(-1)}),
    ("taxa_avulsa_negativa", "FEE", {"gross_amount": Decimal(-3), "quantity": None}),
]


class TestCriacaoManualRejeitaDadoIncoerente:
    @pytest.mark.parametrize(
        ("kind", "overrides"), [c[1:] for c in INVALID_CASES], ids=[c[0] for c in INVALID_CASES]
    )
    def test_rejeita_e_nao_grava(self, db_session, kind, overrides):
        user, account, asset = _setup(db_session, "m")

        with pytest.raises(InvalidTransactionDataError):
            transaction_service.create_transaction(
                db_session, user.id, _payload(account, asset, kind, **overrides)
            )

        assert db_session.query(Transaction).filter_by(account_id=account.id).count() == 0

    def test_dado_incoerente_nunca_chega_a_derrubar_o_dashboard(self, db_session):
        """O cenário que a validação existe para impedir: um BUY sem
        quantidade gravado faria o PositionCalculator levantar em TODO
        cálculo do par — o dashboard inteiro viraria erro 500.
        """
        user, account, asset = _setup(db_session, "d")
        transaction_service.create_transaction(db_session, user.id, _payload(account, asset, "BUY"))
        with pytest.raises(InvalidTransactionDataError):
            transaction_service.create_transaction(
                db_session, user.id, _payload(account, asset, "BUY", quantity=None)
            )

        summary = dashboard_service.get_dashboard_summary(db_session, user.id)

        assert summary.totals_by_currency[0].total_cost_basis == Decimal(50)


class TestTiposValidosContinuamAceitos:
    @pytest.mark.parametrize(
        ("kind", "overrides", "with_asset"),
        [
            ("BUY", {}, True),
            ("BUY", {"unit_price": Decimal(0), "gross_amount": Decimal(0)}, True),
            ("DIVIDEND", {"quantity": None, "unit_price": None}, True),
            ("JCP", {"quantity": None, "unit_price": None}, True),
            ("INCOME", {"quantity": None, "unit_price": None}, False),
            ("FEE", {"quantity": None, "unit_price": None}, False),
            ("DEPOSIT", {"quantity": None, "unit_price": None}, False),
            ("WITHDRAWAL", {"quantity": None, "unit_price": None}, False),
            ("BONUS_SHARES", {"unit_price": None, "gross_amount": Decimal(0)}, True),
        ],
    )
    def test_aceita(self, db_session, kind, overrides, with_asset):
        user, account, asset = _setup(db_session, "ok")

        created = transaction_service.create_transaction(
            db_session, user.id, _payload(account, asset if with_asset else None, kind, **overrides)
        )

        assert created.id is not None

    def test_grupamento_com_variacao_negativa(self, db_session):
        user, account, asset = _setup(db_session, "rs")
        transaction_service.create_transaction(db_session, user.id, _payload(account, asset, "BUY"))

        transaction_service.create_transaction(
            db_session,
            user.id,
            _payload(
                account,
                asset,
                "REVERSE_SPLIT",
                quantity=Decimal(-5),
                unit_price=None,
                gross_amount=Decimal(0),
            ),
        )

        position = transaction_service.get_position(db_session, user.id, account.id, asset.id)
        assert position.quantity == Decimal(5)
        assert position.total_cost_basis == Decimal(50)


class TestOutrosPontosDeEntrada:
    def test_importacao_passa_pela_mesma_validacao(self, db_session):
        user, account, asset = _setup(db_session, "i")

        with pytest.raises(InvalidTransactionDataError):
            transaction_service.create_imported_transaction(
                db_session,
                user.id,
                account_id=account.id,
                asset_id=asset.id,
                transaction_type=TransactionType.BUY,
                quantity=Decimal(-10),
                unit_price=Decimal(5),
                fees=Decimal(0),
                gross_amount=Decimal(50),
                currency_code="BRL",
                transaction_date=DAY,
                source=TransactionSource.IMPORT_CSV,
                external_reference="ref-invalida:0",
            )

        assert db_session.query(Transaction).filter_by(account_id=account.id).count() == 0

    def test_correcao_passa_pela_mesma_validacao(self, db_session):
        user, account, asset = _setup(db_session, "c")
        original = transaction_service.create_transaction(
            db_session, user.id, _payload(account, asset, "BUY")
        )

        with pytest.raises(InvalidTransactionDataError):
            transaction_service.correct_transaction(
                db_session,
                user.id,
                original.id,
                _payload(account, asset, "BUY", quantity=Decimal(-10)),
            )

        db_session.expire_all()
        assert original.status.value == "ACTIVE"

    @pytest.mark.parametrize(
        "overrides",
        [{"gross_amount": Decimal(0)}, {"gross_amount": Decimal(-10)}, {"fees": Decimal(-1)}],
    )
    def test_transferencia_rejeita_valor_nao_positivo_e_taxa_negativa(self, db_session, overrides):
        user = make_user(db_session, email="valid-transfer@example.com")
        institution = make_institution(db_session, name="Inst Valid Transfer")
        origem = make_account(db_session, user, institution, name="Origem Valid")
        destino = make_account(db_session, user, institution, name="Destino Valid")
        data = {
            "from_account_id": origem.id,
            "to_account_id": destino.id,
            "gross_amount": Decimal(100),
            "transaction_date": DAY,
        }
        data.update(overrides)

        with pytest.raises(InvalidTransactionDataError):
            transaction_service.create_transfer(db_session, user.id, TransferCreate(**data))

        assert db_session.query(Transaction).count() == 0
