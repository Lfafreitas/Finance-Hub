from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session() -> Session:
    """Fábrica simples de sessão, usada fora do ciclo de request do
    FastAPI (ex.: scripts, testes que montam sessão manualmente).
    """
    return SessionLocal()


def get_db():
    """Dependency do FastAPI: uma sessão por request. Commita se o
    endpoint terminar sem exceção, reverte caso contrário — é isso que
    garante que uma operação com múltiplos INSERTs/UPDATEs na mesma
    request (ex.: as duas pernas de uma transferência) nunca fique
    parcialmente persistida.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
