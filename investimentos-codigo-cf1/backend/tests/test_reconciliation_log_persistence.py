"""Fase 10b, unidade 3: persistência e integridade de ReconciliationLog.

Só o modelo/schema — nenhum matcher, scan ou resolução existe ainda.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.models import ReconciliationLog, Transaction
from app.models.enums import ReconciliationStatus, TransactionStatus
from app.models.reconciliation_log import canonical_pair
from tests.test_immutability import make_transaction
from tests.test_persistence import make_account, make_institution, make_user

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
S = ReconciliationStatus


def _setup(db, tag):
    user = make_user(db, email=f"rlog-{tag}@example.com")
    account = make_account(db, user, make_institution(db, name=f"Inst RLog {tag}"))
    tx1 = make_transaction(db, account)
    tx2 = make_transaction(db, account)
    a, b = canonical_pair(tx1.id, tx2.id)
    return user, account, a, b


def _log(user, a, b, **overrides):
    data = {
        "user_id": user.id,
        "transaction_a_id": a,
        "transaction_b_id": b,
        "match_reason": "quantity: 100 != 105",
    }
    data.update(overrides)
    return ReconciliationLog(**data)


def _persist(db, log):
    db.add(log)
    db.flush()
    return log


class TestCanonicalPair:
    def test_ordena_min_max_independente_da_ordem_de_entrada(self):
        x, y = uuid.UUID(int=5), uuid.UUID(int=9)

        assert canonical_pair(x, y) == canonical_pair(y, x) == (x, y)

    def test_par_consigo_mesmo_e_rejeitado(self):
        x = uuid.uuid4()

        with pytest.raises(ValueError):
            canonical_pair(x, x)

    def test_ordem_python_coincide_com_ordem_do_postgres(self, db_session):
        # Garante que o helper e o CHECK (a < b) do banco concordam.
        _user, _account, a, b = _setup(db_session, "ord")
        order = (
            db_session.execute(
                select(Transaction.id).where(Transaction.id.in_([a, b])).order_by(Transaction.id)
            )
            .scalars()
            .all()
        )

        assert order == [a, b]


class TestEnum:
    def test_estados_exatamente_os_aprovados(self):
        assert [s.value for s in ReconciliationStatus] == [
            "PENDING",
            "IGNORED",
            "KEPT_BOTH",
            "MERGED",
            "STALE",
        ]


class TestPersistencia:
    def test_persiste_com_defaults_pending(self, db_session):
        user, _account, a, b = _setup(db_session, "p1")

        log = _persist(db_session, _log(user, a, b))
        db_session.refresh(log)

        assert log.status == S.PENDING
        assert log.resolved_at is None
        assert log.surviving_transaction_id is None
        assert log.reversed_transaction_id is None
        assert log.match_reason == "quantity: 100 != 105"
        assert log.created_at is not None

    def test_nao_altera_as_transactions_do_par(self, db_session):
        user, _account, a, b = _setup(db_session, "p2")

        _persist(db_session, _log(user, a, b))
        db_session.expire_all()

        assert db_session.get(Transaction, a).status == TransactionStatus.ACTIVE
        assert db_session.get(Transaction, b).status == TransactionStatus.ACTIVE

    def test_indice_user_status_existe(self, db_session):
        indexes = inspect(db_session.get_bind()).get_indexes("reconciliation_logs")

        by_name = {i["name"]: i["column_names"] for i in indexes}
        assert by_name["ix_reconciliation_logs_user_status"] == ["user_id", "status"]

    def test_unique_constraint_do_par_existe(self, db_session):
        uniques = inspect(db_session.get_bind()).get_unique_constraints("reconciliation_logs")

        assert {"transaction_a_id", "transaction_b_id"} in [set(u["column_names"]) for u in uniques]


class TestParCanonicoEUnico:
    def test_par_duplicado_e_rejeitado(self, db_session):
        user, _account, a, b = _setup(db_session, "u1")
        _persist(db_session, _log(user, a, b))

        with pytest.raises(IntegrityError):
            _persist(db_session, _log(user, a, b, match_reason="outra"))

    def test_par_duplicado_e_rejeitado_mesmo_com_outro_status(self, db_session):
        # IGNORED/KEPT_BOTH/MERGED "não reapresentam o mesmo par": o
        # UNIQUE vale independente do status do registro existente.
        user, _account, a, b = _setup(db_session, "u2")
        _persist(db_session, _log(user, a, b, status=S.IGNORED, resolved_at=NOW))

        with pytest.raises(IntegrityError):
            _persist(db_session, _log(user, a, b))

    def test_par_invertido_nao_canonico_e_rejeitado(self, db_session):
        user, _account, a, b = _setup(db_session, "u3")

        with pytest.raises(IntegrityError):
            _persist(db_session, _log(user, b, a))  # (max, min)

    def test_par_invertido_nao_burla_o_unique(self, db_session):
        user, _account, a, b = _setup(db_session, "u4")
        _persist(db_session, _log(user, a, b))

        with pytest.raises(IntegrityError):
            _persist(db_session, _log(user, b, a))

    def test_transaction_com_ela_mesma_e_rejeitada(self, db_session):
        user, _account, a, _b = _setup(db_session, "u5")

        with pytest.raises(IntegrityError):
            _persist(db_session, _log(user, a, a))


class TestConsistenciaDoMerge:
    def test_merged_valido_persiste(self, db_session):
        user, _account, a, b = _setup(db_session, "m1")

        log = _persist(
            db_session,
            _log(
                user,
                a,
                b,
                status=S.MERGED,
                surviving_transaction_id=a,
                reversed_transaction_id=b,
                resolved_at=NOW,
            ),
        )

        assert log.status == S.MERGED

    def test_merged_aceita_sobrevivente_como_b(self, db_session):
        user, _account, a, b = _setup(db_session, "m2")

        log = _persist(
            db_session,
            _log(
                user,
                a,
                b,
                status=S.MERGED,
                surviving_transaction_id=b,
                reversed_transaction_id=a,
                resolved_at=NOW,
            ),
        )

        assert log.surviving_transaction_id == b

    @pytest.mark.parametrize(
        "case",
        [
            "sem_sobrevivente",
            "sem_revertida",
            "sobrevivente_igual_revertida",
            "sobrevivente_fora_do_par",
            "revertida_fora_do_par",
        ],
    )
    def test_merged_invalido_e_rejeitado(self, db_session, case):
        user, account, a, b = _setup(db_session, f"m3{case}")
        outsider = make_transaction(db_session, account).id
        fields = {
            "sem_sobrevivente": {"surviving_transaction_id": None, "reversed_transaction_id": b},
            "sem_revertida": {"surviving_transaction_id": a, "reversed_transaction_id": None},
            "sobrevivente_igual_revertida": {
                "surviving_transaction_id": a,
                "reversed_transaction_id": a,
            },
            "sobrevivente_fora_do_par": {
                "surviving_transaction_id": outsider,
                "reversed_transaction_id": b,
            },
            "revertida_fora_do_par": {
                "surviving_transaction_id": a,
                "reversed_transaction_id": outsider,
            },
        }[case]

        with pytest.raises(IntegrityError):
            _persist(db_session, _log(user, a, b, status=S.MERGED, resolved_at=NOW, **fields))

    @pytest.mark.parametrize("status", [S.PENDING, S.IGNORED, S.KEPT_BOTH, S.STALE])
    @pytest.mark.parametrize("field", ["surviving_transaction_id", "reversed_transaction_id"])
    def test_status_nao_merged_nao_pode_ter_sobrevivente_nem_revertida(
        self, db_session, status, field
    ):
        user, _account, a, b = _setup(db_session, f"m4{status.value}{field[:4]}")
        resolved = None if status == S.PENDING else NOW

        with pytest.raises(IntegrityError):
            _persist(
                db_session, _log(user, a, b, status=status, resolved_at=resolved, **{field: a})
            )


class TestResolvedAt:
    def test_pending_com_resolved_at_e_rejeitado(self, db_session):
        user, _account, a, b = _setup(db_session, "r1")

        with pytest.raises(IntegrityError):
            _persist(db_session, _log(user, a, b, status=S.PENDING, resolved_at=NOW))

    @pytest.mark.parametrize("status", [S.IGNORED, S.KEPT_BOTH])
    def test_decisao_humana_sem_resolved_at_e_rejeitada(self, db_session, status):
        user, _account, a, b = _setup(db_session, f"r2{status.value}")

        with pytest.raises(IntegrityError):
            _persist(db_session, _log(user, a, b, status=status, resolved_at=None))

    def test_merged_sem_resolved_at_e_rejeitado(self, db_session):
        user, _account, a, b = _setup(db_session, "r3")

        with pytest.raises(IntegrityError):
            _persist(
                db_session,
                _log(
                    user,
                    a,
                    b,
                    status=S.MERGED,
                    surviving_transaction_id=a,
                    reversed_transaction_id=b,
                    resolved_at=None,
                ),
            )

    @pytest.mark.parametrize("status", [S.IGNORED, S.KEPT_BOTH])
    def test_decisao_humana_com_resolved_at_persiste(self, db_session, status):
        user, _account, a, b = _setup(db_session, f"r4{status.value}")

        log = _persist(db_session, _log(user, a, b, status=status, resolved_at=NOW))

        assert log.status == status

    @pytest.mark.parametrize("resolved_at", [None, NOW])
    def test_stale_aceita_com_ou_sem_resolved_at(self, db_session, resolved_at):
        user, _account, a, b = _setup(db_session, f"r5{resolved_at is None}")

        log = _persist(db_session, _log(user, a, b, status=S.STALE, resolved_at=resolved_at))

        assert log.status == S.STALE


class TestChavesEstrangeirasENulidade:
    @pytest.mark.parametrize("field", ["transaction_a_id", "transaction_b_id", "user_id"])
    def test_fk_inexistente_e_rejeitada(self, db_session, field):
        user, _account, a, b = _setup(db_session, f"f1{field[:6]}")
        ghost = uuid.uuid4()
        # Mantém o par canônico: fantasma em `a` precisa ser o menor, em `b` o maior.
        overrides = {
            "transaction_a_id": {"transaction_a_id": uuid.UUID(int=0)},
            "transaction_b_id": {"transaction_b_id": uuid.UUID(int=2**128 - 1)},
            "user_id": {"user_id": ghost},
        }[field]

        with pytest.raises(IntegrityError):
            _persist(db_session, _log(user, a, b, **overrides))

    def test_match_reason_e_obrigatorio(self, db_session):
        user, _account, a, b = _setup(db_session, "f2")

        with pytest.raises(IntegrityError):
            _persist(db_session, _log(user, a, b, match_reason=None))
