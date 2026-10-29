"""Trava do acesso remoto: cadastrar o iPhone e desbloquear com Face ID.

Gerar código, ver e remover aparelhos e encerrar sessões só pelo próprio
computador: uma sessão do celular nunca mexe nas chaves.
"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.core.remote import client_host, is_remote
from app.schemas.auth import (
    AuthStatus,
    LoginVerifyRequest,
    PairingCodeRead,
    PasskeyRead,
    RegisterOptionsRequest,
    RegisterVerifyRequest,
    WebAuthnOptions,
)
from app.services import auth_service
from app.services.auth_service import SESSION_COOKIE, SESSION_IDLE, SESSION_MAX, AuthError

router = APIRouter(prefix="/auth")


def _status(
    db: Session, user_id: UUID, request: Request, unlocked: bool | None = None
) -> AuthStatus:
    remote = is_remote(request.headers)
    if unlocked is None:
        unlocked = not remote or (
            auth_service.valid_session(db, user_id, request.cookies.get(SESSION_COOKIE)) is not None
        )
    return AuthStatus(
        remote=remote,
        unlocked=unlocked,
        has_passkeys=auth_service.has_passkeys(db, user_id),
        idle_minutes=int(SESSION_IDLE.total_seconds() // 60),
    )


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_MAX.total_seconds()),
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )


def _local_only(request: Request) -> None:
    if is_remote(request.headers):
        raise HTTPException(status_code=403, detail="Só pelo computador (por segurança).")


def _bad(exc: AuthError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _refused(exc: AuthError) -> JSONResponse:
    """Recusa SEM levantar exceção: a sessão do banco é confirmada e o
    contador de tentativas erradas do código não se perde.
    """
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@router.get("/status", response_model=AuthStatus)
def get_status(
    request: Request, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)
):
    return _status(db, user_id, request)


@router.post("/pairing", response_model=PairingCodeRead)
def start_pairing(
    request: Request, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)
):
    """Código para cadastrar um aparelho (10 minutos, 5 tentativas)."""
    _local_only(request)
    code, expires_at = auth_service.start_pairing(db, user_id)
    return PairingCodeRead(code=code, expires_at=expires_at)


@router.post("/register/options", response_model=WebAuthnOptions)
def register_options(
    body: RegisterOptionsRequest,
    request: Request,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        challenge_id, options = auth_service.registration_options(
            db, user_id, body.code, client_host(request.headers)
        )
    except AuthError as exc:
        return _refused(exc)  # sem exceção: a tentativa errada fica gravada
    return WebAuthnOptions(challenge_id=challenge_id, options=json.loads(options))


@router.post("/register/verify", response_model=AuthStatus)
def register_verify(
    body: RegisterVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        _passkey, token = auth_service.finish_registration(
            db, user_id, body.challenge_id, body.code, body.credential, body.name
        )
    except AuthError as exc:
        return _refused(exc)
    _set_cookie(response, token)
    return _status(db, user_id, request, unlocked=True)


@router.post("/login/options", response_model=WebAuthnOptions)
def login_options(
    request: Request, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)
):
    try:
        challenge_id, options = auth_service.login_options(
            db, user_id, client_host(request.headers)
        )
    except AuthError as exc:
        raise _bad(exc) from None
    return WebAuthnOptions(challenge_id=challenge_id, options=json.loads(options))


@router.post("/login/verify", response_model=AuthStatus)
def login_verify(
    body: LoginVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        _passkey, token = auth_service.finish_login(db, user_id, body.challenge_id, body.credential)
    except AuthError as exc:
        raise _bad(exc) from None
    _set_cookie(response, token)
    return _status(db, user_id, request, unlocked=True)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """Bloquear agora (no celular)."""
    auth_service.end_session(db, request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    response.status_code = 204
    return response


@router.get("/passkeys", response_model=list[PasskeyRead])
def list_passkeys(
    request: Request, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)
):
    _local_only(request)
    return auth_service.list_passkeys(db, user_id)


@router.delete("/passkeys/{passkey_id}", status_code=204)
def delete_passkey(
    passkey_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    _local_only(request)
    if not auth_service.delete_passkey(db, user_id, passkey_id):
        raise HTTPException(status_code=404, detail="Aparelho não encontrado.")
    return Response(status_code=204)


@router.post("/sessions/revoke-all")
def revoke_all(
    request: Request, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)
) -> dict[str, int]:
    """Bloqueia na hora todos os aparelhos (pedem Face ID de novo)."""
    _local_only(request)
    return {"revoked": auth_service.revoke_all(db, user_id)}
