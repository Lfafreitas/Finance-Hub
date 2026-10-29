from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Transaction
from app.models.enums import TransactionSource, TransactionStatus, TransactionType
from tests.test_persistence import make_account, make_institution, make_user


def make_transaction(session, account, **overrides) -> Transaction:
    defaults = {
        "account_id": account.id,
        "asset_id": None,
        "transaction_type": TransactionType.DEPOSIT,
        "fees": Decimal(0),
        "gross_amount": Decimal("100.00"),
        "currency_code": "BRL",
        "transaction_date": date(2026, 1, 1),
        "source": TransactionSource.MANUAL,
    }
    defaults.update(overrides)
    transacao = Transaction(**defaults)
    session.add(transacao)
    session.flush()
    return transacao


class TestImutabilidadeFinanceira:
    @pytest.mark.parametrize(
        "campo,valor",
        [
            ("gross_amount", Decimal("999.99")),
            ("fees", Decimal("50.00")),
            ("currency_code", "USD"),
            ("transaction_date", date(2030, 1, 1)),
            ("source", TransactionSource.IMPORT_CSV),
            ("external_reference", "algo-novo"),
        ],
    )
    def test_alterar_campo_financeiro_e_bloqueado_pelo_trigger(self, db_session, campo, valor):
        user = make_user(db_session, email=f"imut-{campo}@example.com")
        institution = make_institution(db_session, name=f"Inst {campo}")
        account = make_account(db_session, user, institution, name=f"Conta {campo}")
        transacao = make_transaction(db_session, account)

        setattr(transacao, campo, valor)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_alterar_notes_e_permitido(self, db_session):
        user = make_user(db_session, email="notes@example.com")
        institution = make_institution(db_session, name="Inst Notes")
        account = make_account(db_session, user, institution, name="Conta Notes")
        transacao = make_transaction(db_session, account, notes="original")

        transacao.notes = "nota corrigida"
        db_session.flush()  # não deve levantar

        db_session.refresh(transacao)
        assert transacao.notes == "nota corrigida"


class TestFluxoDeEstorno:
    def test_reversao_active_para_reversed_e_permitida(self, db_session):
        user = make_user(db_session, email="estorno@example.com")
        institution = make_institution(db_session, name="Inst Estorno")
        account = make_account(db_session, user, institution, name="Conta Estorno")
        transacao = make_transaction(db_session, account)
        assert transacao.status == TransactionStatus.ACTIVE

        transacao.status = TransactionStatus.REVERSED
        db_session.flush()  # não deve levantar

        db_session.refresh(transacao)
        assert transacao.status == TransactionStatus.REVERSED

    def test_reversed_para_active_e_bloqueado(self, db_session):
        user = make_user(db_session, email="reativar@example.com")
        institution = make_institution(db_session, name="Inst Reativar")
        account = make_account(db_session, user, institution, name="Conta Reativar")
        transacao = make_transaction(db_session, account)
        transacao.status = TransactionStatus.REVERSED
        db_session.flush()

        transacao.status = TransactionStatus.ACTIVE
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_correcao_completa_preserva_original_e_cria_ajuste_rastreavel(self, db_session):
        """Fluxo de correção completo: a original vira REVERSED (sem
        perder nenhum dado) e uma nova Transaction correta é criada
        apontando para ela via reverses_transaction_id.
        """
        user = make_user(db_session, email="correcao@example.com")
        institution = make_institution(db_session, name="Inst Correcao")
        account = make_account(db_session, user, institution, name="Conta Correcao")

        original = make_transaction(db_session, account, gross_amount=Decimal("100.00"))
        original.status = TransactionStatus.REVERSED
        db_session.flush()

        ajuste = make_transaction(
            db_session,
            account,
            gross_amount=Decimal("150.00"),
            reverses_transaction_id=original.id,
        )
        db_session.flush()

        db_session.refresh(original)
        assert original.status == TransactionStatus.REVERSED
        assert original.gross_amount == Decimal("100.00")  # dado original intacto
        assert ajuste.reverses_transaction_id == original.id
        assert ajuste.gross_amount == Decimal("150.00")
        assert ajuste.status == TransactionStatus.ACTIVE

    def test_reverses_transaction_id_e_imutavel_apos_criado(self, db_session):
        user = make_user(db_session, email="imut-ref@example.com")
        institution = make_institution(db_session, name="Inst ImutRef")
        account = make_account(db_session, user, institution, name="Conta ImutRef")
        original = make_transaction(db_session, account)
        ajuste = make_transaction(db_session, account, reverses_transaction_id=original.id)

        outra_original = make_transaction(db_session, account)
        ajuste.reverses_transaction_id = outra_original.id
        with pytest.raises(IntegrityError):
            db_session.flush()
