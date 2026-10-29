from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.remote import is_remote
from app.db.session import get_db
from app.models.user import User

__all__ = ["get_current_user_id", "get_db", "require_unlocked"]

_NO_LOGIN_PASSWORD_HASH = "!"


def get_current_user_id(db: Session = Depends(get_db)) -> UUID:
    """D-A1: sem autenticação real nesta fase. O usuário é resolvido
    aqui — nunca aceito como parâmetro do cliente — a partir de
    `settings.single_user_email`. Quando existir autenticação de
    verdade, só esta função muda (ex.: decodificar um JWT); nenhum
    router ou service precisa ser tocado, porque todos dependem de
    `get_current_user_id`, não de como o usuário foi resolvido.

    O usuário é criado automaticamente se ainda não existir.
    """
    stmt = select(User).where(User.email == settings.single_user_email)
    user = db.execute(stmt).scalar_one_or_none()
    if user is None:
        # Instalação nova: o usuário único é criado na primeira
        # requisição, em vez de exigir um INSERT manual no banco antes
        # de a aplicação poder ser usada. `password_hash` recebe um
        # valor que nenhum hash real produz — não existe login nesta
        # fase, e este registro não vira uma senha válida quando
        # existir. SAVEPOINT: se duas requisições simultâneas tentarem
        # criar, a UNIQUE(email) rejeita a segunda, que relê o registro.
        try:
            with db.begin_nested():
                user = User(
                    email=settings.single_user_email,
                    password_hash=_NO_LOGIN_PASSWORD_HASH,
                    full_name="Owner",
                )
                db.add(user)
                db.flush()
        except IntegrityError:
            user = db.execute(stmt).scalar_one()
    return user.id


# Rotas que o celular precisa ANTES de desbloquear (ou que não mostram
# dado nenhum). Todo o resto exige Face ID quando a chamada é remota.
OPEN_PATHS = frozenset(
    {
        "/health",
        "/auth/status",
        "/auth/register/options",
        "/auth/register/verify",
        "/auth/login/options",
        "/auth/login/verify",
        "/auth/logout",
    }
)


def require_unlocked(
    request: Request,
    db: Session = Depends(get_db),
) -> None:
    """Trava do acesso remoto, aplicada a TODAS as rotas (dependência do
    app). Chamada local (este computador) passa direto; remota (celular)
    precisa de uma sessão aberta com Face ID.
    """
    if request.url.path in OPEN_PATHS or not is_remote(request.headers):
        return
    from app.services.auth_service import SESSION_COOKIE, valid_session

    user_id = get_current_user_id(db)
    if valid_session(db, user_id, request.cookies.get(SESSION_COOKIE)) is None:
        raise HTTPException(status_code=401, detail="Bloqueado: desbloqueie com Face ID.")
