import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Portfolio
from tests.test_persistence import make_account, make_institution, make_user


def make_portfolio(session, user, name="Geral") -> Portfolio:
    portfolio = Portfolio(user_id=user.id, name=name)
    session.add(portfolio)
    session.flush()
    return portfolio


class TestPortfolio:
    def test_cria_portfolio_e_associa_account(self, db_session):
        user = make_user(db_session, email="portfolio@example.com")
        institution = make_institution(db_session, name="Inst Portfolio")
        portfolio = make_portfolio(db_session, user, name="Aposentadoria")

        account = make_account(db_session, user, institution, name="Conta Aposentadoria")
        account.portfolio_id = portfolio.id
        db_session.flush()

        db_session.refresh(account)
        assert account.portfolio_id == portfolio.id

    def test_account_sem_portfolio_e_valida(self, db_session):
        """1 Account -> 0 ou 1 Portfolio: nullable, cai na consolidada."""
        user = make_user(db_session, email="sem-portfolio@example.com")
        institution = make_institution(db_session, name="Inst Sem Portfolio")
        account = make_account(db_session, user, institution, name="Conta Consolidada")

        assert account.portfolio_id is None

    def test_nome_de_portfolio_duplicado_no_mesmo_usuario_e_rejeitado(self, db_session):
        user = make_user(db_session, email="dup-portfolio@example.com")
        make_portfolio(db_session, user, name="Brasil")
        db_session.flush()

        with pytest.raises(IntegrityError):
            make_portfolio(db_session, user, name="Brasil")

    def test_mesmo_nome_de_portfolio_em_usuarios_diferentes_e_permitido(self, db_session):
        user1 = make_user(db_session, email="u1-portfolio@example.com")
        user2 = make_user(db_session, email="u2-portfolio@example.com")

        make_portfolio(db_session, user1, name="Brasil")
        make_portfolio(db_session, user2, name="Brasil")
        db_session.flush()  # não deve levantar

    def test_portfolio_exige_user_existente(self, db_session):
        portfolio = Portfolio(user_id=uuid.uuid4(), name="Órfã")
        db_session.add(portfolio)
        with pytest.raises(IntegrityError):
            db_session.flush()
