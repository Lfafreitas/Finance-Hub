"""CF-2: o que o BANCO garante na classificação do livro de caixa."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from app.models import CashflowEntry
from app.models.cashflow_classification import (
    CashflowCategory,
    CashflowRule,
    CashflowTag,
    cashflow_entry_tags,
)
from app.models.enums import (
    AccountType,
    CashflowNature,
    RuleMatchType,
    TransactionSource,
)
from tests.cashflow_helpers import make_typed_account
from tests.test_persistence import make_institution, make_user


@pytest.fixture()
def world(db_session):
    user = make_user(db_session, email=f"{uuid.uuid4().hex[:8]}@cf2.example.com")
    inst = make_institution(db_session, name=f"Banco {uuid.uuid4().hex[:8]}")
    checking = make_typed_account(db_session, user, inst, "Corrente")
    return db_session, user, inst, checking


def _category(db, user, name, parent=None):
    category = CashflowCategory(user_id=user.id, name=name, parent_id=parent.id if parent else None)
    db.add(category)
    db.flush()
    return category


def _entry(db, account, **overrides):
    values = {
        "account_id": account.id,
        "entry_date": date(2026, 1, 10),
        "amount": Decimal(-50),
        "currency_code": "BRL",
        "description": "Padaria",
        "source": TransactionSource.MANUAL,
        "nature": CashflowNature.EXPENSE,
    }
    values.update(overrides)
    entry = CashflowEntry(**values)
    db.add(entry)
    db.flush()
    return entry


def _rule(db, user, **overrides):
    values = {
        "user_id": user.id,
        "name": "regra",
        "pattern": "padaria",
        "match_type": RuleMatchType.CONTAINS,
        "set_nature": CashflowNature.EXPENSE,
    }
    values.update(overrides)
    rule = CashflowRule(**values)
    db.add(rule)
    db.flush()
    return rule


class TestCategoriaNoBanco:
    def test_terceiro_nivel_e_rejeitado(self, world):
        db, user, _inst, _checking = world
        root = _category(db, user, "Raiz")
        child = _category(db, user, "Filha", root)

        with pytest.raises(IntegrityError, match="máximo de dois níveis"):
            _category(db, user, "Neta", child)

    def test_categoria_com_filhas_nao_vira_filha(self, world):
        db, user, _inst, _checking = world
        root = _category(db, user, "Raiz")
        _category(db, user, "Filha", root)
        other = _category(db, user, "Outra raiz")

        root.parent_id = other.id

        with pytest.raises(IntegrityError, match="máximo de dois níveis"):
            db.flush()

    def test_pai_de_outro_usuario_e_rejeitado(self, world):
        db, user, _inst, _checking = world
        stranger = make_user(db, email="cf2-db-stranger@example.com")
        foreign = _category(db, stranger, "Alheia")

        with pytest.raises(IntegrityError, match="outro usuário"):
            _category(db, user, "Minha", foreign)

    def test_nome_repetido_no_mesmo_nivel_e_rejeitado(self, world):
        db, user, _inst, _checking = world
        _category(db, user, "Saúde")

        with pytest.raises(IntegrityError, match="uq_cashflow_categories_root_name"):
            _category(db, user, "Saúde")

    def test_nome_repetido_sob_o_mesmo_pai_e_rejeitado_e_sob_outro_pai_e_aceito(self, world):
        db, user, _inst, _checking = world
        a, b = _category(db, user, "A"), _category(db, user, "B")
        _category(db, user, "Outros", a)
        _category(db, user, "Outros", b)

        with pytest.raises(IntegrityError, match="uq_cashflow_categories_child_name"):
            _category(db, user, "Outros", a)


class TestClassificacaoNoBanco:
    def test_transferencia_com_categoria_e_rejeitada(self, world):
        db, user, inst, checking = world
        savings = make_typed_account(db, user, inst, "Reserva", AccountType.SAVINGS)
        category = _category(db, user, "Qualquer")

        with pytest.raises(IntegrityError, match="transfer_has_no_category"):
            _entry(
                db,
                checking,
                nature=CashflowNature.TRANSFER,
                counterparty_account_id=savings.id,
                transfer_group_id=uuid.uuid4(),
                category_id=category.id,
            )

    def test_classificar_nao_esbarra_na_imutabilidade_do_fato(self, world):
        db, user, _inst, checking = world
        category = _category(db, user, "Alimentação")
        rule = _rule(db, user)
        entry = _entry(db, checking, nature=CashflowNature.UNCLASSIFIED)

        entry.nature = CashflowNature.EXPENSE
        entry.category_id = category.id
        entry.classified_by_rule_id = rule.id
        db.flush()
        db.refresh(entry)

        assert (entry.category_id, entry.classified_by_rule_id) == (category.id, rule.id)
        assert entry.amount == Decimal("-50.0000")

    @pytest.mark.parametrize("nature", [CashflowNature.TRANSFER, CashflowNature.UNCLASSIFIED])
    def test_regra_sem_natureza_de_verdade_e_rejeitada(self, world, nature):
        db, user, _inst, _checking = world

        with pytest.raises(IntegrityError, match="sets_a_real_nature"):
            _rule(db, user, set_nature=nature)

    def test_regra_com_padrao_em_branco_e_rejeitada(self, world):
        db, user, _inst, _checking = world

        with pytest.raises(IntegrityError, match="pattern_not_blank"):
            _rule(db, user, pattern="   ")

    def test_excluir_regra_solta_os_lancamentos_sem_tocar_no_fato(self, world):
        db, user, _inst, checking = world
        rule = _rule(db, user)
        entry = _entry(db, checking, classified_by_rule_id=rule.id)

        db.delete(rule)
        db.flush()
        db.refresh(entry)

        assert entry.classified_by_rule_id is None
        assert (entry.nature, entry.amount) == (CashflowNature.EXPENSE, Decimal("-50.0000"))

    def test_excluir_tag_remove_a_marcacao_do_lancamento(self, world):
        db, user, _inst, checking = world
        tag = CashflowTag(user_id=user.id, name="Online", tag_group="canal")
        db.add(tag)
        entry = _entry(db, checking)
        db.execute(insert(cashflow_entry_tags), [{"entry_id": entry.id, "tag_id": tag.id}])

        db.delete(tag)
        db.flush()

        assert db.execute(select(cashflow_entry_tags)).all() == []

    def test_categoria_usada_por_lancamento_nao_e_apagada_pelo_banco(self, world):
        db, user, _inst, checking = world
        category = _category(db, user, "Em uso")
        _entry(db, checking, category_id=category.id)

        db.delete(category)

        with pytest.raises(IntegrityError, match="fk_cashflow_entries_category_id"):
            db.flush()
