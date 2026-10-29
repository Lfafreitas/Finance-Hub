import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.routers.prices import get_rate_provider
from app.core.config import settings
from app.main import app
from app.models.user import User


class _NoRates:
    def fetch(self, start, end):
        return []


@pytest.fixture()
def api_client(db_session):
    """Sobrescreve get_db para usar a MESMA sessão transacional do
    teste (isolamento via rollback do fixture db_session, não commit
    real) e semeia o usuário único exigido por get_current_user_id.
    """

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    # Nenhum teste fala com o Banco Central: CDI vazio por padrão (quem
    # testa o CDI troca por uma fonte falsa com dados).
    app.dependency_overrides[get_rate_provider] = lambda: _NoRates()

    user = User(email=settings.single_user_email, password_hash="x", full_name="Owner")
    db_session.add(user)
    db_session.flush()

    try:
        yield TestClient(app), user
    finally:
        app.dependency_overrides.clear()
