"""O usuário único é criado na primeira requisição de uma instalação
nova — não é mais preciso inserir um User no banco à mão.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.core.config import settings
from app.main import app
from app.models.user import User


@pytest.fixture()
def client_sem_usuario(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _owners(db):
    return db.query(User).filter_by(email=settings.single_user_email).all()


def test_primeira_requisicao_cria_o_usuario_unico(client_sem_usuario, db_session):
    assert _owners(db_session) == []

    response = client_sem_usuario.get("/accounts")

    assert response.status_code == 200
    assert response.json() == []
    assert len(_owners(db_session)) == 1


def test_requisicoes_seguintes_reutilizam_o_mesmo_usuario(client_sem_usuario, db_session):
    client_sem_usuario.get("/accounts")
    primeiro = _owners(db_session)[0].id

    client_sem_usuario.get("/portfolios")
    client_sem_usuario.get("/dashboard/summary")

    owners = _owners(db_session)
    assert [o.id for o in owners] == [primeiro]


def test_usuario_criado_nao_tem_senha_utilizavel(client_sem_usuario, db_session):
    client_sem_usuario.get("/accounts")

    assert _owners(db_session)[0].password_hash == "!"
