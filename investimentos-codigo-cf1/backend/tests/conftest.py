import os

# O TestClient do Starlette usa o host `testserver`. Liberado só aqui,
# ANTES de `app.core.config` ser importado — o padrão de produção
# (`localhost`/`127.0.0.1`) não inclui esse nome.
os.environ.setdefault("ALLOWED_HOSTS", '["localhost", "127.0.0.1", "testserver"]')

# Os testes NUNCA usam o banco do dashboard (investimentos_dev): o
# usuário único de lá já existe e os testes que o criam falhariam — e
# dados reais não são lugar para teste. Banco próprio, trocável por
# TEST_DATABASE_URL, definido ANTES de `app.core.config` ser importado.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/investimentos_test",
)

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.db.session import engine

TEST_DB = make_url(os.environ["DATABASE_URL"])
if not (TEST_DB.database or "").endswith("_test"):
    raise RuntimeError(f"Banco de teste precisa terminar em _test, veio {TEST_DB.database!r}.")


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    """Cria o banco de teste se faltar e aplica as migrações."""
    admin = create_engine(TEST_DB.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB.database}"'))
    admin.dispose()

    # Sem o alembic.ini: o fileConfig dele desligaria os loggers do app
    # (e os testes que conferem o log).
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    command.upgrade(config, "head")


@pytest.fixture()
def db_session():
    """Cada teste roda dentro de uma transação que é revertida no
    final — garante isolamento entre testes sem precisar truncar
    tabelas manualmente, e sem nunca sujar o banco de teste.
    """
    connection = engine.connect()
    transaction = connection.begin()
    TestSession = sessionmaker(bind=connection)
    session: Session = TestSession()

    try:
        yield session
    finally:
        session.close()
        # Um IntegrityError já dispara rollback interno da conexão;
        # nesse caso `transaction` fica inativa e chamar rollback()
        # de novo só gera warning, não erro — mas evitamos mesmo assim.
        if transaction.is_active:
            transaction.rollback()
        connection.close()
