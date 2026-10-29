"""Fase 10b, unidade 7: integração import -> BackgroundTask ->
sessão independente.

IMPORTANTE sobre a infra de testes usada aqui: o fixture padrão do
projeto (`db_session`/`api_client`) vincula a sessão a uma CONEXÃO que
já tem uma transação externa aberta (`connection.begin()` em
`tests/conftest.py`). Nesse arranjo, `session.commit()` não emite um
COMMIT real no banco — só finaliza a unit-of-work do ORM, mantendo a
transação externa aberta até o rollback do teardown. Isso é exatamente
o que dá o isolamento entre testes, mas torna esse fixture INADEQUADO
para provar visibilidade entre sessões REALMENTE independentes — que é
o próprio objeto desta unidade (commit do import ANTES da
BackgroundTask, que abre sua PRÓPRIA sessão/conexão).

Por isso, os testes deste arquivo usam `get_session()` (a mesma fábrica
que a BackgroundTask de produção usa) para toda a preparação de dados
e para o cliente HTTP, SEM nenhum `dependency_overrides` — o app usa o
`get_db` de produção de verdade, com commit/rollback reais por request,
contra o banco de teste (via `DATABASE_URL`). Cada teste limpa
explicitamente o que criou ao final (`_cleanup_user`); institutions/
assets (cadastro global/compartilhado) ficam, como em qualquer outro
teste que usa `make_institution`/`make_asset`.
"""

import logging
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.db.session import get_session
from app.main import app
from app.models.account import Account
from app.models.asset import Asset
from app.models.enums import (
    ReconciliationStatus,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.models.institution import Institution
from app.models.reconciliation_log import ReconciliationLog
from app.models.transaction import Transaction
from app.models.user import User
from tests.test_persistence import make_account, make_asset, make_institution, make_user

_KNOWN_ASSET_TICKERS = [
    "ORD1",
    "TND1",
    "SOLO1",
    "LOT1",
    "LOT2",
    "UNI1",
    "UNI2",
    "UNI3",
    "FLR1",
    "SF1",
    "SF2",
    "ISO1",
]


def _cleanup_known_assets() -> None:
    """Remove os Assets fixos usados pelos testes deste arquivo, quando
    nenhuma Transaction real ainda os referencia. Necessário além da
    limpeza "via Transaction" em `_cleanup_user`: um teste que espera
    falha do commit (ex.: tudo-ou-nada) cria o Asset mas NUNCA chega a
    criar uma Transaction que o referencie, então ele nunca apareceria
    nessa outra rota de limpeza.
    """
    session = get_session()
    try:
        for ticker in _KNOWN_ASSET_TICKERS:
            asset = session.execute(
                select(Asset).where(Asset.ticker == ticker)
            ).scalar_one_or_none()
            if asset is None:
                continue
            still_used = session.execute(
                select(Transaction.id).where(Transaction.asset_id == asset.id)
            ).first()
            if still_used is None:
                session.delete(asset)
        session.commit()
    finally:
        session.close()


_KNOWN_INSTITUTION_NAMES = [
    "Inst Ordem",
    "Inst TudoNada",
    "Inst SemCand",
    "Inst Lote",
    "Inst UmaTarefa",
    "Inst FalhaRecon",
    "Inst SessaoFecha",
    "Inst IsoA",
    "Inst IsoB",
    "Inst Alheia",
]


def _cleanup_known_institutions() -> None:
    """Remove as Institutions fixas usadas pelos testes deste arquivo,
    quando nenhuma Account real ainda as referencia. Evita que rodar
    este arquivo mais de uma vez contra o mesmo banco acumule lixo
    (aqui os commits são reais, ao contrário do resto da suíte).
    """
    session = get_session()
    try:
        for name in _KNOWN_INSTITUTION_NAMES:
            institution = session.execute(
                select(Institution).where(Institution.name == name)
            ).scalar_one_or_none()
            if institution is None:
                continue
            still_used = session.execute(
                select(Account.id).where(Account.institution_id == institution.id)
            ).first()
            if still_used is None:
                session.delete(institution)
        session.commit()
    finally:
        session.close()


def _cleanup_user(user_id: UUID) -> None:
    session = get_session()
    try:
        account_ids = list(
            session.execute(select(Account.id).where(Account.user_id == user_id)).scalars()
        )
        asset_ids: set[UUID] = set()
        if account_ids:
            tx_ids = list(
                session.execute(
                    select(Transaction.id).where(Transaction.account_id.in_(account_ids))
                ).scalars()
            )
            if tx_ids:
                asset_ids = set(
                    session.execute(
                        select(Transaction.asset_id).where(
                            Transaction.id.in_(tx_ids), Transaction.asset_id.is_not(None)
                        )
                    ).scalars()
                )
                session.execute(
                    delete(ReconciliationLog).where(
                        ReconciliationLog.transaction_a_id.in_(tx_ids)
                        | ReconciliationLog.transaction_b_id.in_(tx_ids)
                    )
                )
                session.execute(delete(Transaction).where(Transaction.id.in_(tx_ids)))
            session.execute(delete(Account).where(Account.id.in_(account_ids)))
        session.execute(delete(User).where(User.id == user_id))
        if asset_ids:
            session.execute(delete(Asset).where(Asset.id.in_(asset_ids)))
        session.commit()
    finally:
        session.close()


@pytest.fixture()
def real_client():
    """Cliente HTTP contra o `get_db` de PRODUÇÃO, sem nenhum
    dependency_override -- cada request abre e comita sua própria
    sessão de verdade, exatamente como em produção. Garante que existe
    (e ao final remove) o usuário único exigido por
    `get_current_user_id`.
    """
    session = get_session()
    try:
        user = session.execute(
            select(User).where(User.email == settings.single_user_email)
        ).scalar_one_or_none()
        if user is None:
            user = User(email=settings.single_user_email, password_hash="x", full_name="Owner Real")
            session.add(user)
            session.commit()
        user_id = user.id
    finally:
        session.close()

    try:
        yield TestClient(app), user_id
    finally:
        _cleanup_user(user_id)
        _cleanup_known_assets()
        _cleanup_known_institutions()


def _setup_account_and_assets(
    user_id: UUID, institution_name: str, tickers: list[str] | None = None
) -> UUID:
    """Cria (com COMMIT real) uma Institution + Account para `user_id`,
    e cada Asset em `tickers`. Devolve só o `account_id` -- o suficiente
    para montar as chamadas HTTP; a sessão é fechada logo em seguida.
    """
    session = get_session()
    try:
        institution = make_institution(session, name=institution_name)
        account = make_account(
            session, session.get(User, user_id), institution, name=institution_name
        )
        for ticker in tickers or []:
            make_asset(session, ticker=ticker)
        session.commit()
        return account.id
    finally:
        session.close()


def _csv(*linhas_valor: tuple[str, str, str, str, str]) -> bytes:
    """Monta um CSV de COMPRA. Cada linha: (data, ativo, quantidade, preco, valor)."""
    header = b"data,tipo,ativo,quantidade,preco_unitario,taxas,valor,moeda\n"
    rows = b"".join(
        f"{data},COMPRA,{ativo},{qtd},{preco},0,{valor},BRL\n".encode()
        for data, ativo, qtd, preco, valor in linhas_valor
    )
    return header + rows


def _preview_e_commit(client, account_id, csv_bytes):
    preview = client.post(
        "/imports/preview",
        data={"account_id": str(account_id), "source_format": "CSV"},
        files={"file": ("extrato.csv", csv_bytes, "text/csv")},
    ).json()
    commit = client.post(
        "/imports/commit",
        json={
            "account_id": preview["account_id"],
            "source_format": preview["source_format"],
            "rows": preview["rows"],
            "signature": preview["signature"],
            "included_row_indexes": [r["row_index"] for r in preview["rows"]],
        },
    )
    return commit


class TestOrdemCriticaImportBackgroundTaskSessaoIndependente:
    """O teste do §10 da aprovação: prova, de ponta a ponta, que uma
    sessão TOTALMENTE NOVA (aberta depois que a resposta do commit já
    voltou) enxerga as Transactions recém-importadas -- exatamente o
    conflito de ordem identificado na retomada da Fase 10b.
    """

    def test_nova_sessao_enxerga_transactions_e_cria_reconciliationlog(self, real_client):
        client, user_id = real_client
        account_id = _setup_account_and_assets(user_id, "Inst Ordem", ["ORD1"])

        first_commit = _preview_e_commit(
            client, account_id, _csv(("2026-09-05", "ORD1", "100", "30", "3000"))
        )
        assert first_commit.status_code == 200, first_commit.text
        existing_transaction_id = first_commit.json()["transaction_ids"][0]

        # PASSO CRÍTICO: um SEGUNDO import, com uma linha equivalente
        # (mesmo ativo/tipo/valor). Isso dispara:
        #   IMPORT COMMIT -> TRANSACTIONS EXISTEM NO BANCO ->
        #   BACKGROUND TASK -> NOVA SESSÃO -> MATCHER ENXERGA AS
        #   TRANSACTIONS (a pré-existente E a recém-importada).
        second_commit = _preview_e_commit(
            client, account_id, _csv(("2026-09-06", "ORD1", "100", "30", "3000"))
        )
        assert second_commit.status_code == 200, second_commit.text
        new_transaction_id = second_commit.json()["transaction_ids"][0]

        # A PROVA: consulta com uma sessão TOTALMENTE NOVA, aberta
        # SÓ AGORA. Se o commit explícito não tivesse acontecido antes
        # de agendar a tarefa, esta consulta encontraria zero logs (a
        # tarefa teria rodado sem ver as Transactions).
        verification_session = get_session()
        try:
            logs = (
                verification_session.execute(
                    select(ReconciliationLog).where(ReconciliationLog.user_id == user_id)
                )
                .scalars()
                .all()
            )
            assert len(logs) == 1
            log = logs[0]
            assert log.status == ReconciliationStatus.PENDING
            assert {log.transaction_a_id, log.transaction_b_id} == {
                UUID(existing_transaction_id),
                UUID(new_transaction_id),
            }

            # E a MESMA sessão nova também enxerga as Transactions em
            # si (não só o efeito colateral do log).
            fetched = verification_session.get(Transaction, UUID(new_transaction_id))
            assert fetched is not None
            assert fetched.gross_amount == 3000
        finally:
            verification_session.close()


class TestImportacaoContinuaTudoOuNada:
    def test_commit_com_assinatura_invalidada_nao_importa_nada(self, real_client):
        client, user_id = real_client
        account_id = _setup_account_and_assets(user_id, "Inst TudoNada", ["TND1"])

        preview = client.post(
            "/imports/preview",
            data={"account_id": str(account_id), "source_format": "CSV"},
            files={
                "file": (
                    "misto.csv",
                    _csv(("2026-09-05", "TND1", "10", "10", "100")),
                    "text/csv",
                )
            },
        ).json()
        # Assinatura correta, mas conteúdo alterado depois do preview.
        tampered_rows = [dict(r) for r in preview["rows"]]
        tampered_rows[0]["gross_amount"] = "999999.00"

        commit = client.post(
            "/imports/commit",
            json={
                "account_id": preview["account_id"],
                "source_format": preview["source_format"],
                "rows": tampered_rows,
                "signature": preview["signature"],
                "included_row_indexes": [r["row_index"] for r in tampered_rows],
            },
        )

        assert commit.status_code == 409  # assinatura não bate mais
        verification_session = get_session()
        try:
            rows = (
                verification_session.execute(
                    select(Transaction).where(Transaction.account_id == account_id)
                )
                .scalars()
                .all()
            )
            assert rows == []
        finally:
            verification_session.close()


class TestBackgroundTaskAgendamento:
    def test_import_sem_candidatos_nao_cria_logs(self, real_client):
        client, user_id = real_client
        account_id = _setup_account_and_assets(user_id, "Inst SemCand", ["SOLO1"])

        commit = _preview_e_commit(
            client, account_id, _csv(("2026-09-05", "SOLO1", "10", "10", "100"))
        )

        assert commit.status_code == 200, commit.text
        verification_session = get_session()
        try:
            logs = (
                verification_session.execute(
                    select(ReconciliationLog).where(ReconciliationLog.user_id == user_id)
                )
                .scalars()
                .all()
            )
            assert logs == []
        finally:
            verification_session.close()

    def test_lote_importado_pode_gerar_varios_reconciliationlogs(self, real_client):
        client, user_id = real_client
        account_id = _setup_account_and_assets(user_id, "Inst Lote", ["LOT1", "LOT2"])

        base = _preview_e_commit(
            client,
            account_id,
            _csv(
                ("2026-09-01", "LOT1", "50", "10", "500"),
                ("2026-09-01", "LOT2", "20", "5", "100"),
            ),
        )
        assert base.status_code == 200, base.text

        commit = _preview_e_commit(
            client,
            account_id,
            _csv(
                ("2026-09-02", "LOT1", "50", "10", "500"),
                ("2026-09-02", "LOT2", "20", "5", "100"),
            ),
        )

        assert commit.status_code == 200, commit.text
        verification_session = get_session()
        try:
            logs = (
                verification_session.execute(
                    select(ReconciliationLog).where(ReconciliationLog.user_id == user_id)
                )
                .scalars()
                .all()
            )
            assert len(logs) == 2
            assert all(log.status == ReconciliationStatus.PENDING for log in logs)
        finally:
            verification_session.close()

    def test_reconciliacao_nao_e_executada_uma_vez_por_linha(self, real_client, monkeypatch):
        # Garante UMA tarefa por LOTE: instrumenta
        # run_batch_reconciliation_task para contar quantas vezes é
        # chamada (deve ser 1 por commit, não 1 por linha).
        from app.api.routers import imports as imports_router_module

        client, user_id = real_client
        account_id = _setup_account_and_assets(user_id, "Inst UmaTarefa", ["UNI1", "UNI2", "UNI3"])
        calls = []
        original = imports_router_module.reconciliation_service.run_batch_reconciliation_task

        def _spy(uid, aid, transaction_ids):
            calls.append(len(transaction_ids))
            return original(uid, aid, transaction_ids)

        monkeypatch.setattr(
            imports_router_module.reconciliation_service, "run_batch_reconciliation_task", _spy
        )

        commit = _preview_e_commit(
            client,
            account_id,
            _csv(
                ("2026-09-02", "UNI1", "1", "10", "10"),
                ("2026-09-02", "UNI2", "1", "10", "10"),
                ("2026-09-02", "UNI3", "1", "10", "10"),
            ),
        )

        assert commit.status_code == 200, commit.text
        assert calls == [3]  # UMA chamada, com as 3 transaction_ids do lote


class TestFalhaDaReconciliacaoNaoDesfazImport:
    def test_falha_na_reconciliacao_nao_desfaz_import_ja_confirmado(
        self, real_client, monkeypatch, caplog
    ):
        from app.services import reconciliation_service

        client, user_id = real_client
        account_id = _setup_account_and_assets(user_id, "Inst FalhaRecon", ["FLR1"])

        def _boom(*_args, **_kwargs):
            raise RuntimeError("falha simulada na reconciliação em lote")

        monkeypatch.setattr(reconciliation_service, "check_batch_after_import", _boom)

        with caplog.at_level(logging.ERROR, logger="app.services.reconciliation_service"):
            commit = _preview_e_commit(
                client, account_id, _csv(("2026-09-05", "FLR1", "10", "10", "100"))
            )

        assert commit.status_code == 200, commit.text
        assert commit.json()["imported_count"] == 1

        verification_session = get_session()
        try:
            transactions = (
                verification_session.execute(
                    select(Transaction).where(Transaction.account_id == account_id)
                )
                .scalars()
                .all()
            )
            assert len(transactions) == 1  # o import continua confirmado
        finally:
            verification_session.close()

        assert any(
            "Falha na reconciliação em lote pós-import" in record.message
            for record in caplog.records
        )

    def test_falha_da_background_task_nao_deixa_sessao_travada(self, real_client, monkeypatch):
        # Confirma que, mesmo com a checagem estourando, a sessão da
        # tarefa é fechada (session.close() no finally) -- não há como
        # inspecionar "sessões abertas" diretamente sem acoplar ao
        # pool, então validamos o efeito observável: uma chamada real
        # subsequente continua funcionando normalmente (nenhuma
        # conexão ficou presa).
        from app.services import reconciliation_service

        client, user_id = real_client
        account_id = _setup_account_and_assets(user_id, "Inst SessaoFecha", ["SF1", "SF2"])

        def _boom(*_args, **_kwargs):
            raise RuntimeError("falha simulada")

        monkeypatch.setattr(reconciliation_service, "check_batch_after_import", _boom)
        first = _preview_e_commit(client, account_id, _csv(("2026-09-05", "SF1", "1", "1", "1")))
        assert first.status_code == 200

        monkeypatch.undo()  # restaura a função real

        second = _preview_e_commit(client, account_id, _csv(("2026-09-06", "SF2", "1", "1", "1")))
        assert second.status_code == 200


class TestIsolamentoEntreUsuariosNoImport:
    def test_import_de_um_usuario_nunca_dispara_sobre_transactions_de_outro(self, real_client):
        client, user_id = real_client
        account_id = _setup_account_and_assets(user_id, "Inst IsoA", ["ISO1"])

        outro_session = get_session()
        outro_user = make_user(outro_session, email="outro-import-real@example.com")
        outro_institution = make_institution(outro_session, name="Inst IsoB")
        outro_account = make_account(outro_session, outro_user, outro_institution, name="Inst IsoB")
        outro_tx = Transaction(
            account_id=outro_account.id,
            asset_id=None,
            transaction_type=TransactionType.DEPOSIT,
            fees=Decimal(0),
            gross_amount=Decimal(100),
            currency_code="BRL",
            transaction_date="2026-09-05",
            source=TransactionSource.MANUAL,
            status=TransactionStatus.ACTIVE,
        )
        outro_session.add(outro_tx)
        outro_session.commit()
        outro_user_id, outro_tx_id = outro_user.id, outro_tx.id
        outro_session.close()

        try:
            commit = _preview_e_commit(
                client, account_id, _csv(("2026-09-05", "ISO1", "10", "10", "100"))
            )
            assert commit.status_code == 200, commit.text

            verification_session = get_session()
            try:
                logs = verification_session.execute(select(ReconciliationLog)).scalars().all()
                for log in logs:
                    assert log.user_id != outro_user_id
                outro_still_active = verification_session.get(Transaction, outro_tx_id)
                assert outro_still_active.status == TransactionStatus.ACTIVE
            finally:
                verification_session.close()
        finally:
            _cleanup_user(outro_user_id)


class TestOwnershipDoAccountIdNoImport:
    def test_import_em_conta_de_outro_usuario_e_rejeitado(self, real_client):
        client, _user_id = real_client
        outro_session = get_session()
        outro_user = make_user(outro_session, email="outro-account-import@example.com")
        outro_institution = make_institution(outro_session, name="Inst Alheia")
        outro_account = make_account(
            outro_session, outro_user, outro_institution, name="Inst Alheia"
        )
        outro_session.commit()
        outro_user_id, outro_account_id = outro_user.id, outro_account.id
        outro_session.close()

        try:
            response = client.post(
                "/imports/preview",
                data={"account_id": str(outro_account_id), "source_format": "CSV"},
                files={"file": ("x.csv", _csv(("2026-09-05", "OWN1", "1", "1", "1")), "text/csv")},
            )

            assert response.status_code == 404
        finally:
            _cleanup_user(outro_user_id)
