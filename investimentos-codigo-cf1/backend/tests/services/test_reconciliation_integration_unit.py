"""Fase 10b, unidade 7: integração síncrona pós-criação/correção
(check_after_creation) e a checagem em lote usada pelo import
(check_batch_after_import), no nível de service — sem passar pela API
e sem precisar de commits reais (tudo roda na MESMA sessão/transação
de teste, exatamente como a checagem síncrona roda na mesma sessão do
request).
"""

import logging
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.enums import (
    ReconciliationStatus,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.models.reconciliation_log import ReconciliationLog
from app.models.transaction import Transaction
from app.services import reconciliation_service
from app.services.reconciliation_service import (
    _create_reconciliation_log_safe,
    check_after_creation,
    check_batch_after_import,
)
from tests.test_persistence import make_account, make_asset, make_institution, make_user

D = date(2026, 9, 1)
MANUAL = TransactionSource.MANUAL
CSV = TransactionSource.IMPORT_CSV


def _tx(db, account, asset, source, qty="100", price="30", gross=None, ttype=TransactionType.BUY):
    quantity, unit_price = Decimal(qty), Decimal(price)
    tx = Transaction(
        account_id=account.id,
        asset_id=asset.id,
        transaction_type=ttype,
        quantity=quantity,
        unit_price=unit_price,
        fees=Decimal(0),
        gross_amount=Decimal(gross) if gross is not None else quantity * unit_price,
        currency_code="BRL",
        transaction_date=D,
        source=source,
        status=TransactionStatus.ACTIVE,
    )
    db.add(tx)
    db.flush()
    return tx


def _setup(db, tag):
    user = make_user(db, email=f"chk-{tag}@example.com")
    account = make_account(db, user, make_institution(db, name=f"Inst Chk {tag}"))
    asset = make_asset(db, ticker=f"CK{tag}")
    return user, account, asset


class TestCheckAfterCreationCriacaoNormal:
    def test_encontra_candidato_e_cria_pending(self, db_session):
        user, account, asset = _setup(db_session, "n1")
        existing = _tx(db_session, account, asset, MANUAL)
        new = _tx(db_session, account, asset, CSV)

        created = check_after_creation(db_session, user.id, new)

        assert len(created) == 1
        assert created[0].status == ReconciliationStatus.PENDING
        assert {created[0].transaction_a_id, created[0].transaction_b_id} == {existing.id, new.id}

    def test_sem_candidato_nao_cria_nada(self, db_session):
        user, account, asset = _setup(db_session, "n2")
        new = _tx(db_session, account, asset, MANUAL)

        assert check_after_creation(db_session, user.id, new) == []

    def test_mesma_source_identica_nao_gera_log(self, db_session):
        user, account, asset = _setup(db_session, "n3")
        _tx(db_session, account, asset, MANUAL)
        new = _tx(db_session, account, asset, MANUAL)

        assert check_after_creation(db_session, user.id, new) == []

    def test_nao_recompara_transactions_pre_existentes_entre_si(self, db_session):
        # Duas MANUAL já existentes e idênticas entre si (não deveriam
        # nunca virar log); a nova (CSV) é candidata às duas.
        user, account, asset = _setup(db_session, "n4")
        m1 = _tx(db_session, account, asset, MANUAL)
        m2 = _tx(db_session, account, asset, MANUAL)
        new = _tx(db_session, account, asset, CSV)

        created = check_after_creation(db_session, user.id, new)

        pairs = {frozenset((c.transaction_a_id, c.transaction_b_id)) for c in created}
        assert pairs == {frozenset((m1.id, new.id)), frozenset((m2.id, new.id))}


class TestCheckAfterCreationFalhaInterna:
    def test_falha_do_matcher_nao_impede_a_transaction_de_existir(self, db_session, monkeypatch):
        user, account, asset = _setup(db_session, "f1")
        _tx(db_session, account, asset, MANUAL)
        new = _tx(db_session, account, asset, CSV)

        def _boom(*_args, **_kwargs):
            raise RuntimeError("falha simulada no matcher")

        monkeypatch.setattr(reconciliation_service, "match", _boom)

        result = check_after_creation(db_session, user.id, new)

        assert result == []  # best-effort: não propaga
        db_session.expire_all()
        assert db_session.get(Transaction, new.id) is not None
        assert db_session.get(Transaction, new.id).status == TransactionStatus.ACTIVE

    def test_falha_interna_nao_transforma_a_transaction_em_reversed(self, db_session, monkeypatch):
        user, account, asset = _setup(db_session, "f2")
        _tx(db_session, account, asset, MANUAL)
        new = _tx(db_session, account, asset, CSV)
        monkeypatch.setattr(
            reconciliation_service,
            "match",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        check_after_creation(db_session, user.id, new)

        db_session.expire_all()
        assert db_session.get(Transaction, new.id).status == TransactionStatus.ACTIVE

    def test_falha_interna_nao_deixa_log_parcial(self, db_session, monkeypatch):
        # Faz o matcher estourar só na SEGUNDA comparação -- garante
        # que nada da primeira tentativa (que teria criado um log)
        # sobrevive fora do savepoint quando a chamada inteira falha.
        user, account, asset = _setup(db_session, "f3")
        _tx(db_session, account, asset, MANUAL)
        _tx(db_session, account, asset, MANUAL, qty="105", gross="3150")
        new = _tx(db_session, account, asset, CSV)

        calls = {"n": 0}
        real_match = reconciliation_service.match

        def _match_boom_on_second(a, b):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("boom na segunda comparação")
            return real_match(a, b)

        monkeypatch.setattr(reconciliation_service, "match", _match_boom_on_second)

        result = check_after_creation(db_session, user.id, new)

        assert result == []
        db_session.expire_all()
        remaining = (
            db_session.query(ReconciliationLog)
            .filter(
                ReconciliationLog.transaction_a_id.in_([new.id])
                | ReconciliationLog.transaction_b_id.in_([new.id])
            )
            .all()
        )
        assert remaining == []

    def test_falha_interna_e_registrada_no_logger(self, db_session, monkeypatch, caplog):
        user, account, asset = _setup(db_session, "f4")
        _tx(db_session, account, asset, MANUAL)
        new = _tx(db_session, account, asset, CSV)
        monkeypatch.setattr(
            reconciliation_service,
            "match",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        with caplog.at_level(logging.ERROR, logger="app.services.reconciliation_service"):
            check_after_creation(db_session, user.id, new)

        assert any(
            "Falha na checagem de reconciliação pós-criação" in record.message
            for record in caplog.records
        )
        assert str(user.id) in caplog.text
        assert str(new.id) in caplog.text

    def test_transaction_sem_asset_nao_quebra(self, db_session):
        user, account, _asset = _setup(db_session, "f5")
        deposit = Transaction(
            account_id=account.id,
            asset_id=None,
            transaction_type=TransactionType.DEPOSIT,
            fees=Decimal(0),
            gross_amount=Decimal(500),
            currency_code="BRL",
            transaction_date=D,
            source=MANUAL,
            status=TransactionStatus.ACTIVE,
        )
        db_session.add(deposit)
        db_session.flush()

        assert check_after_creation(db_session, user.id, deposit) == []


class TestConcorrenciaEIntegrityError:
    def test_conflito_de_par_ja_existente_e_tratado_sem_propagar(self, db_session):
        user, account, asset = _setup(db_session, "c1")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)
        first, second = sorted([a.id, b.id])
        # Simula que OUTRO processo já criou este par entre a checagem
        # de existência e a tentativa de inserção.
        db_session.add(
            ReconciliationLog(
                user_id=user.id,
                transaction_a_id=first,
                transaction_b_id=second,
                match_reason="criado por outro processo",
            )
        )
        db_session.flush()

        result = _create_reconciliation_log_safe(
            db_session, user.id, (first, second), "tentativa concorrente"
        )

        assert result is None  # tratado como benigno, não propaga
        rows = (
            db_session.query(ReconciliationLog)
            .filter(
                ReconciliationLog.transaction_a_id == first,
                ReconciliationLog.transaction_b_id == second,
            )
            .all()
        )
        assert len(rows) == 1  # um único log, não duplicado
        assert rows[0].match_reason == "criado por outro processo"  # o original, intacto

    def test_duas_chamadas_de_check_after_creation_resultam_em_um_unico_log(self, db_session):
        # Simula duas "rodadas" de checagem (ex.: duas requisições)
        # encontrando o mesmo par: a segunda não duplica.
        user, account, asset = _setup(db_session, "c2")
        a = _tx(db_session, account, asset, MANUAL)
        b = _tx(db_session, account, asset, CSV)

        first_round = check_after_creation(db_session, user.id, b)
        second_round = check_after_creation(db_session, user.id, b)

        assert len(first_round) == 1
        assert second_round == []
        rows = (
            db_session.query(ReconciliationLog)
            .filter(
                ReconciliationLog.transaction_a_id.in_([a.id, b.id]),
                ReconciliationLog.transaction_b_id.in_([a.id, b.id]),
            )
            .all()
        )
        assert len(rows) == 1

    def test_integrity_error_inesperado_nao_e_mascarado(self, db_session):
        # FK quebrada (Transactions que não existem) -- não é o
        # conflito de UNIQUE esperado, então deve subir.
        ghost_a, ghost_b = uuid.uuid4(), uuid.uuid4()
        pair = tuple(sorted([ghost_a, ghost_b]))

        with pytest.raises(IntegrityError) as exc_info:
            _create_reconciliation_log_safe(db_session, uuid.uuid4(), pair, "fk quebrada")

        assert "uq_reconciliation_logs_pair" not in str(exc_info.value.orig)

    def test_apos_integrity_error_inesperado_sessao_continua_utilizavel(self, db_session):
        # O savepoint interno garante que só o INSERT problemático é
        # desfeito -- a sessão segue usável para o resto do teste.
        ghost_a, ghost_b = uuid.uuid4(), uuid.uuid4()
        pair = tuple(sorted([ghost_a, ghost_b]))
        with pytest.raises(IntegrityError):
            _create_reconciliation_log_safe(db_session, uuid.uuid4(), pair, "fk quebrada")

        user = make_user(db_session, email="chk-c4@example.com")
        assert user.id is not None


class TestIsolamentoEntreUsuarios:
    def test_check_after_creation_nunca_atravessa_contas_de_outro_usuario(self, db_session):
        user_a, account_a, asset_a = _setup(db_session, "u1a")
        _user_b, account_b, asset_b = _setup(db_session, "u1b")
        _tx(db_session, account_a, asset_a, MANUAL)
        new_a = _tx(db_session, account_a, asset_a, CSV)
        _tx(db_session, account_b, asset_b, MANUAL)
        _tx(db_session, account_b, asset_b, CSV)

        created = check_after_creation(db_session, user_a.id, new_a)

        assert len(created) == 1
        assert created[0].user_id == user_a.id
        for tx_id in (created[0].transaction_a_id, created[0].transaction_b_id):
            assert db_session.get(Transaction, tx_id).account_id == account_a.id

    def test_check_batch_after_import_nunca_cria_log_para_outro_usuario(self, db_session):
        user_a, account_a, asset_a = _setup(db_session, "u2a")
        _user_b, account_b, asset_b = _setup(db_session, "u2b")
        existing_a = _tx(db_session, account_a, asset_a, MANUAL)
        imported_a = _tx(db_session, account_a, asset_a, CSV)
        _tx(db_session, account_b, asset_b, MANUAL)
        imported_b_like = _tx(db_session, account_b, asset_b, CSV)

        created = check_batch_after_import(db_session, user_a.id, [imported_a.id])

        assert len(created) == 1
        assert created[0].user_id == user_a.id
        assert {created[0].transaction_a_id, created[0].transaction_b_id} == {
            existing_a.id,
            imported_a.id,
        }
        # Nada tocou as Transactions do usuário B.
        assert imported_b_like.id not in (created[0].transaction_a_id, created[0].transaction_b_id)


class TestCheckBatchAfterImport:
    def test_lote_gera_logs_entre_novas_e_pre_existentes_e_entre_si(self, db_session):
        user, account, asset = _setup(db_session, "b1")
        pre_existing = _tx(db_session, account, asset, MANUAL)
        new1 = _tx(db_session, account, asset, CSV)
        new2 = _tx(db_session, account, asset, CSV, qty="105", gross="3150")

        created = check_batch_after_import(db_session, user.id, [new1.id, new2.id])

        pairs = {frozenset((c.transaction_a_id, c.transaction_b_id)) for c in created}
        assert frozenset((pre_existing.id, new1.id)) in pairs
        assert frozenset((pre_existing.id, new2.id)) in pairs

    def test_lote_sem_candidatos_nao_cria_logs(self, db_session):
        user, account, asset = _setup(db_session, "b2")
        new = _tx(db_session, account, asset, MANUAL)

        assert check_batch_after_import(db_session, user.id, [new.id]) == []

    def test_id_inexistente_no_lote_e_ignorado_sem_quebrar_o_resto(self, db_session):
        user, account, asset = _setup(db_session, "b3")
        _tx(db_session, account, asset, MANUAL)
        new = _tx(db_session, account, asset, CSV)

        created = check_batch_after_import(db_session, user.id, [uuid.uuid4(), new.id])

        assert len(created) == 1

    def test_falha_em_uma_transaction_do_lote_nao_impede_as_demais(self, db_session, monkeypatch):
        # Uma falha real do matcher ao processar a PRIMEIRA Transaction
        # do lote (isolada por `check_after_creation`) não impede que a
        # SEGUNDA seja checada normalmente no mesmo `check_batch_after_import`.
        user, account, asset = _setup(db_session, "b4")
        pre1 = _tx(db_session, account, asset, MANUAL)
        pre2 = _tx(db_session, account, asset, MANUAL, qty="200", gross="6000")
        new1 = _tx(db_session, account, asset, CSV)
        new2 = _tx(db_session, account, asset, CSV, qty="200", gross="6000")

        real_match = reconciliation_service.match

        def _fail_for_new1(a, b):
            if a.id == new1.id:
                raise RuntimeError("falha simulada só quando new1 é o alvo da rodada")
            return real_match(a, b)

        monkeypatch.setattr(reconciliation_service, "match", _fail_for_new1)

        created = check_batch_after_import(db_session, user.id, [new1.id, new2.id])

        pairs = {frozenset((c.transaction_a_id, c.transaction_b_id)) for c in created}
        assert frozenset((pre1.id, new1.id)) not in pairs  # essa falhou, best-effort
        assert frozenset((pre2.id, new2.id)) in pairs  # essa continuou normalmente
